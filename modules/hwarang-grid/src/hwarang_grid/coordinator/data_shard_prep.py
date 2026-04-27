"""HLKM 데이터 → 훈련 샤드 변환.

각 에이전트에게 배정할 shard 와 peer 평가 공통 eval shard 를 생성한다.

파이프라인:
    1. query_hlkm_facts(filter_criteria) — HLKM에서 도메인/상태/품질 필터
    2. facts_to_sft / facts_to_qa_pairs — SFT 형식 변환
    3. split_into_shards — N 에이전트용 샤드 분할 (10% overlap)
    4. upload_shard_to_storage — 로컬 저장 + URL 생성
    5. prepare_round_shards — 위 단계를 한 번에 수행

의존성 (graceful):
    - hwarang_api.knowledge.search: HLKM 접근 (없으면 목업 반환)
    - hwarang_api.knowledge.types.SearchQuery: 타입
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# 내부 유틸
# ────────────────────────────────────────────────────────────────────────


_STORAGE_ROOT = Path.home() / ".hwarang" / "master" / "shards"


def _storage_dir(round_id: str) -> Path:
    p = _STORAGE_ROOT / round_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def compute_shard_hash(shard_path: str) -> str:
    """SHA-256 헥사다이제스트. 무결성 검증용."""
    p = Path(shard_path)
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ────────────────────────────────────────────────────────────────────────
# HLKM 조회
# ────────────────────────────────────────────────────────────────────────


async def query_hlkm_facts(
    filter_criteria: dict[str, Any],
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """HLKM 에서 조건 맞는 팩트들 조회.

    filter_criteria 키:
        domain:              "law" 등 도메인 prefix
        status:              "CONFIRMED" 등
        stance:              "for"/"against"/"neutral"
        source_tier:         "PEER_REVIEWED" 이상
        arbitrated_score_min: 0.7 등 최소 arbitrated 점수
        retracted:           기본 False (재량: True 로 포함 가능)
        language:            "ko" 등

    graceful: hwarang_api 미설치 환경에서는 빈 리스트.
    """
    try:
        from hwarang_api.knowledge.search import temporal_search  # type: ignore
        from hwarang_api.knowledge.types import SearchQuery  # type: ignore
    except Exception as exc:
        logger.warning("HLKM 임포트 실패 — 목업 모드: %s", exc)
        return _mock_facts(filter_criteria, limit)

    try:
        query = SearchQuery(
            text=filter_criteria.get("query", ""),
            domain=filter_criteria.get("domain"),
            language=filter_criteria.get("language", "ko"),
            top_k=limit,
        )
        result = await temporal_search(query)
        facts = []
        for f in getattr(result, "facts", []) or []:
            d = f.model_dump() if hasattr(f, "model_dump") else dict(f)
            # 후처리 필터 (SearchQuery 가 지원하지 않는 조건들)
            if filter_criteria.get("retracted", False) is False:
                if d.get("status") == "RETRACTED":
                    continue
            if filter_criteria.get("source_tier"):
                if d.get("source_type") not in _acceptable_source_tiers(
                    filter_criteria["source_tier"]
                ):
                    continue
            facts.append(d)
        logger.info("HLKM 조회: %d 건 (필터 후)", len(facts))
        return facts
    except Exception as exc:
        logger.warning("HLKM 조회 실패 — 목업: %s", exc)
        return _mock_facts(filter_criteria, limit)


_TIER_ORDER = [
    "PRIMARY_OFFICIAL",
    "PEER_REVIEWED",
    "SPECIALIZED_MEDIA",
    "GENERAL_MEDIA",
    "USER_GENERATED",
]


def _acceptable_source_tiers(min_tier: str) -> set[str]:
    if min_tier not in _TIER_ORDER:
        return set(_TIER_ORDER)
    idx = _TIER_ORDER.index(min_tier)
    return set(_TIER_ORDER[: idx + 1])


def _mock_facts(filter_criteria: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """HLKM 없을 때 개발용 목업."""
    domain = filter_criteria.get("domain", "general")
    out: list[dict[str, Any]] = []
    for i in range(min(limit, 50)):
        out.append({
            "id": f"mock_{domain}_{i}",
            "content": f"[mock {domain}] 사실 #{i} — 실제 HLKM 미연결.",
            "domain": domain,
            "source": "mock",
            "source_type": "PEER_REVIEWED",
            "status": "CONFIRMED",
            "language": filter_criteria.get("language", "ko"),
        })
    return out


# ────────────────────────────────────────────────────────────────────────
# SFT 변환
# ────────────────────────────────────────────────────────────────────────


_DOMAIN_SYSTEM_PROMPTS: dict[str, str] = {
    "law": "당신은 한국 법률 전문가입니다. 판례·법령에 근거한 정확한 답변을 하세요.",
    "medical": "당신은 의료 전문가입니다. 근거 기반 의학(EBM)에 따라 신중히 답변하세요.",
    "tax": "당신은 세무 전문가입니다. 한국 세법에 근거하여 정확히 답변하세요.",
    "finance": "당신은 재무·회계 전문가입니다. 기업회계기준에 근거해 답변하세요.",
    "general": "당신은 신뢰할 수 있는 한국어 AI 어시스턴트입니다.",
}


def _system_prompt(domain: str) -> str:
    # 도메인 prefix 가장 긴 매치
    candidates = sorted(_DOMAIN_SYSTEM_PROMPTS.keys(), key=len, reverse=True)
    for c in candidates:
        if domain.startswith(c):
            return _DOMAIN_SYSTEM_PROMPTS[c]
    return _DOMAIN_SYSTEM_PROMPTS["general"]


async def facts_to_sft(
    facts: list[dict[str, Any]],
    domain: str,
) -> list[dict[str, Any]]:
    """사실 → SFT 메시지 포맷 변환.

    출력: [{"messages": [system, user, assistant]}, ...]
    """
    sys_prompt = _system_prompt(domain)
    out: list[dict[str, Any]] = []
    for f in facts:
        content = f.get("content", "")
        if not content:
            continue
        entity = f.get("entity") or domain
        source = f.get("source", "")
        user_q = f"{entity}에 대해 설명해 주세요."
        assistant_a = content
        if source:
            assistant_a += f"\n\n[출처] {source}"
        out.append({
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_q},
                {"role": "assistant", "content": assistant_a},
            ],
            "_fact_id": f.get("id"),
        })
    return out


async def facts_to_qa_pairs(
    facts: list[dict[str, Any]],
    llm_expand: bool = True,
) -> list[dict[str, Any]]:
    """LLM으로 Q&A 쌍 생성 (Optional).

    llm_expand=True 이고 hwarang_api LLM 클라이언트가 있으면 질문을
    자동 생성, 아니면 간단한 템플릿으로 3개 확장.
    """
    if llm_expand:
        try:
            expanded = await _llm_expand(facts)
            if expanded:
                return expanded
        except Exception as exc:
            logger.info("LLM 확장 실패, 템플릿 fallback: %s", exc)

    # 템플릿 fallback
    out: list[dict[str, Any]] = []
    templates = [
        "{entity}이(가) 무엇인가요?",
        "{entity}에 대해 알려주세요.",
        "{entity}의 핵심을 요약해 주세요.",
    ]
    for f in facts:
        entity = f.get("entity") or "해당 주제"
        content = f.get("content", "")
        if not content:
            continue
        for tmpl in templates:
            out.append({
                "question": tmpl.format(entity=entity),
                "answer": content,
                "domain": f.get("domain"),
                "source": f.get("source"),
            })
    return out


async def _llm_expand(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """hwarang_api LLM 클라이언트로 질문 자동 생성 (가능할 때)."""
    try:
        from hwarang_api.services.llm_client import generate_text  # type: ignore
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for f in facts[:200]:  # 너무 많으면 과금 방지
        prompt = (
            "다음 사실에 대해 학습용 Q&A 쌍 3개를 한국어로 생성하세요.\n"
            f"사실: {f.get('content', '')}\n"
            "형식: Q: ...\\nA: ..."
        )
        try:
            text = await generate_text(prompt, max_tokens=300)
        except Exception:
            continue
        # 파싱 (Q/A 쌍)
        for line in text.split("Q:")[1:]:
            parts = line.split("A:", 1)
            if len(parts) != 2:
                continue
            q, a = parts[0].strip(), parts[1].strip()
            out.append({
                "question": q,
                "answer": a,
                "domain": f.get("domain"),
                "source": f.get("source"),
            })
    return out


# ────────────────────────────────────────────────────────────────────────
# 분할
# ────────────────────────────────────────────────────────────────────────


def split_into_shards(
    all_samples: list[dict[str, Any]],
    num_shards: int,
    overlap_ratio: float = 0.1,
) -> list[list[dict[str, Any]]]:
    """전체 샘플을 N 샤드로 분할. overlap_ratio 만큼 교차 포함.

    교차 샘플은 agent 간 일관성 검증(peer-vote)의 공통 앵커가 된다.
    """
    if num_shards <= 0:
        return []
    samples = list(all_samples)
    random.shuffle(samples)

    if num_shards == 1:
        return [samples]

    total = len(samples)
    base = total // num_shards
    overlap_count = int(base * overlap_ratio)

    shards: list[list[dict[str, Any]]] = []
    for i in range(num_shards):
        start = i * base
        end = start + base if i < num_shards - 1 else total
        core = samples[start:end]
        # overlap: 뒤 샤드에서 앞쪽 일부 가져오기
        if overlap_count > 0:
            pool = samples[:start] + samples[end:]
            if pool:
                extra = random.sample(pool, min(overlap_count, len(pool)))
                core = core + extra
        shards.append(core)
    logger.info("%d 샤드 분할 완료 (base=%d, overlap=%d)", num_shards, base, overlap_count)
    return shards


# ────────────────────────────────────────────────────────────────────────
# 저장
# ────────────────────────────────────────────────────────────────────────


async def upload_shard_to_storage(
    shard_data: list[dict[str, Any]],
    round_id: str,
    slot: int,
) -> str:
    """로컬 파일 저장 + URL 반환 (S3 는 추후).

    URL 형식: file:///{절대경로} — 마스터 서버가 동일 파일시스템에서 serve.
    HTTP endpoint (e.g. /api/grid/rounds/{round_id}/shard/{slot}) 로 노출 가능.
    """
    directory = _storage_dir(round_id)
    fname = f"shard_{slot:03d}.jsonl"
    path = directory / fname
    with path.open("w", encoding="utf-8") as f:
        for sample in shard_data:
            f.write(json.dumps(sample, ensure_ascii=False))
            f.write("\n")
    url = f"file://{path.absolute()}"
    logger.info("샤드 저장: slot=%d, samples=%d → %s", slot, len(shard_data), path)
    return url


# ────────────────────────────────────────────────────────────────────────
# 최상위 진입점
# ────────────────────────────────────────────────────────────────────────


async def prepare_round_shards(
    round_id: str,
    domain: str,
    filter_criteria: dict[str, Any],
    num_agents: int,
    samples_per_agent: int = 500,
    eval_size: int = 100,
    overlap_ratio: float = 0.1,
    llm_expand: bool = False,
) -> dict[str, Any]:
    """라운드에 필요한 샤드 전체를 준비.

    Return:
        {
            "round_id": str,
            "total_samples": int,
            "shards": [{agent_slot, shard_url, hash, count}],
            "eval_shard_url": str,
            "eval_hash": str,
        }
    """
    started = time.time()
    target_total = samples_per_agent * max(num_agents, 1) + eval_size

    facts = await query_hlkm_facts(filter_criteria, limit=target_total)
    if not facts:
        logger.warning("HLKM 팩트 0건, 빈 샤드 반환")

    sft = await facts_to_sft(facts, domain)
    if llm_expand:
        qa = await facts_to_qa_pairs(facts, llm_expand=True)
        sft.extend([{"messages": [
            {"role": "system", "content": _system_prompt(domain)},
            {"role": "user", "content": p["question"]},
            {"role": "assistant", "content": p["answer"]},
        ]} for p in qa])

    random.shuffle(sft)

    # eval set 먼저 떼기
    eval_samples = sft[:eval_size]
    train_samples = sft[eval_size:]

    eval_url = await upload_shard_to_storage(eval_samples, round_id, slot=999)
    # eval 파일 경로 변환
    eval_path = eval_url.replace("file://", "")
    eval_hash = compute_shard_hash(eval_path)

    # 트레인 샤드 분할
    shards = split_into_shards(train_samples, num_agents, overlap_ratio=overlap_ratio)
    shard_info: list[dict[str, Any]] = []
    for slot, shard in enumerate(shards):
        url = await upload_shard_to_storage(shard, round_id, slot=slot)
        path = url.replace("file://", "")
        shard_info.append({
            "agent_slot": slot,
            "shard_url": url,
            "hash": compute_shard_hash(path),
            "count": len(shard),
        })

    elapsed = time.time() - started
    logger.info(
        "샤드 준비 완료: round=%s, total=%d, agents=%d, %.1fs",
        round_id, len(sft), num_agents, elapsed,
    )
    return {
        "round_id": round_id,
        "total_samples": len(sft),
        "shards": shard_info,
        "eval_shard_url": eval_url,
        "eval_hash": eval_hash,
        "elapsed_sec": round(elapsed, 2),
    }


__all__ = [
    "query_hlkm_facts",
    "facts_to_sft",
    "facts_to_qa_pairs",
    "split_into_shards",
    "upload_shard_to_storage",
    "compute_shard_hash",
    "prepare_round_shards",
]
