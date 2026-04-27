"""동료 기여 평가 — FedAvg 전 다른 에이전트의 LoRA 품질을 로컬 벤치마크로 평가해
마스터에게 투표 제출. 가짜 에이전트/무작위 LoRA 방어 핵심.

역할:
  - 라운드 종료 시 마스터에서 peer 에이전트들의 LoRA 어댑터를 받아온다.
  - 공통 검증 샤드로 forward pass 수행, loss/accuracy 측정.
  - 가중치 이상 (NaN/Inf/비정상 norm) 탐지 → Sybil 공격 방어.
  - 0~1 점수를 마스터에 투표 제출. 집계된 점수가 보상 가중치에 반영.

설계 철학:
  - torch/peft/transformers 는 선택 의존성. 없으면 파일 무결성 + 파일 크기
    기반의 저신뢰 평가만 수행 (graceful degradation).
  - 평가 중 사용한 베이스 모델은 즉시 해제 (GPU 메모리 압박 회피).
  - 5명까지만 샘플링 (모두 평가하면 내 라운드에 지장).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import random
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

try:
    import torch  # type: ignore
    _HAS_TORCH = True
except ImportError:  # pragma: no cover
    torch = None  # type: ignore
    _HAS_TORCH = False

try:
    from peft import PeftModel  # type: ignore
    _HAS_PEFT = True
except ImportError:  # pragma: no cover
    PeftModel = None  # type: ignore
    _HAS_PEFT = False

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    _HAS_TRANSFORMERS = True
except ImportError:  # pragma: no cover
    AutoModelForCausalLM = None  # type: ignore
    AutoTokenizer = None  # type: ignore
    _HAS_TRANSFORMERS = False

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------


@dataclass
class PeerEvalResult:
    """한 에이전트의 LoRA 기여 평가 결과."""

    peer_agent_id: str
    peer_lora_path: str
    base_model: str
    eval_dataset: list[dict]
    quality_score: float  # 0~1
    loss: float | None = None
    accuracy: float | None = None
    issues: list[str] = field(default_factory=list)
    evaluation_time_sec: float = 0.0
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "peer_agent_id": self.peer_agent_id,
            "quality_score": round(self.quality_score, 4),
            "loss": self.loss,
            "accuracy": self.accuracy,
            "issues": self.issues,
            "evaluation_time_sec": round(self.evaluation_time_sec, 2),
            "evaluated_at": self.evaluated_at.isoformat(),
        }


# -----------------------------------------------------------------------------
# HTTP helpers — peer LoRA 다운로드 / 평가 샤드 / 투표 제출
# -----------------------------------------------------------------------------


async def fetch_peer_lora(
    master_url: str,
    round_id: str,
    peer_agent_id: str,
    api_key: str,
    cache_dir: str = "/tmp/hwarang/peer_loras",
) -> str | None:
    """마스터에서 peer LoRA 어댑터 다운로드. Return local path."""
    if httpx is None:
        logger.warning("httpx 미설치 — peer LoRA 다운로드 불가")
        return None

    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    local_path = Path(cache_dir) / f"{round_id}_{peer_agent_id}.safetensors"

    url = f"{master_url.rstrip('/')}/api/grid/rounds/{round_id}/peer-lora/{peer_agent_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code != 200:
                    logger.warning(
                        "peer LoRA 다운로드 실패 agent=%s status=%d",
                        peer_agent_id, resp.status_code,
                    )
                    return None
                with local_path.open("wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
    except Exception as exc:
        logger.error("peer LoRA 스트리밍 오류 agent=%s err=%s", peer_agent_id, exc)
        return None

    if not local_path.exists() or local_path.stat().st_size == 0:
        return None

    return str(local_path)


async def load_eval_shard(
    master_url: str,
    round_id: str,
    api_key: str,
) -> list[dict]:
    """마스터에서 검증용 공통 데이터 샤드 받기 (peer 결과 비교용)."""
    if httpx is None:
        return []

    url = f"{master_url.rstrip('/')}/api/grid/rounds/{round_id}/eval-shard"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data.get("samples", [])
            return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("eval shard 다운로드 실패: %s", exc)
        return []


# -----------------------------------------------------------------------------
# Core evaluation
# -----------------------------------------------------------------------------


def _file_stat_based_score(lora_path: str) -> tuple[float, list[str]]:
    """torch 미설치 시 fallback — 파일 크기/확장자만으로 저신뢰 점수."""
    issues: list[str] = []
    p = Path(lora_path)
    if not p.exists():
        return 0.0, ["lora_file_missing"]

    size_mb = p.stat().st_size / (1024 * 1024)
    if size_mb < 0.1:
        issues.append("lora_suspiciously_small")
        return 0.1, issues
    if size_mb > 2048:
        issues.append("lora_oversized")
        return 0.2, issues

    # 0.3 ~ 0.6 구간에서 크기 기반 heuristic 점수
    score = 0.3 + min(0.3, size_mb / 400.0)
    return score, issues


def detect_anomalies(lora_weights: Any) -> list[str]:
    """LoRA 가중치가 정상 범위 벗어나는지 체크 → Sybil/공격 탐지.

    체크 항목:
      - NaN / Inf 포함
      - 전부 0 (학습 안 함)
      - norm 이 극단적으로 크거나 작음 (random 가까움)
    """
    issues: list[str] = []
    if not _HAS_TORCH or lora_weights is None:
        return issues

    try:
        iterator = lora_weights.items() if hasattr(lora_weights, "items") else enumerate(lora_weights)
        total_norm = 0.0
        param_count = 0
        zero_params = 0
        nan_params = 0

        for key, tensor in iterator:
            if not hasattr(tensor, "detach"):
                continue
            t = tensor.detach().float()
            if torch.isnan(t).any().item():
                nan_params += 1
                issues.append(f"nan_in_{key}")
            if torch.isinf(t).any().item():
                issues.append(f"inf_in_{key}")
            if float(t.abs().sum().item()) < 1e-8:
                zero_params += 1
            total_norm += float(t.norm().item())
            param_count += 1

        if param_count == 0:
            issues.append("no_trainable_params")
            return issues

        avg_norm = total_norm / max(1, param_count)
        if avg_norm > 1000.0:
            issues.append(f"extreme_weight_norm_{avg_norm:.1f}")
        if avg_norm < 1e-5:
            issues.append(f"near_zero_norm_{avg_norm:.2e}")
        if zero_params / param_count > 0.8:
            issues.append("mostly_zero_weights")
        if nan_params > 0:
            issues.append(f"nan_param_count_{nan_params}")
    except Exception as exc:
        issues.append(f"anomaly_check_error:{exc}")

    return issues


def load_base_model_lightweight(base_model_path: str, device: str):
    """LoRA 평가를 위한 베이스 모델 lazy load. 평가 끝나면 해제.

    torch/transformers 없으면 None 반환 → 상위에서 fallback.
    """
    if not (_HAS_TORCH and _HAS_TRANSFORMERS):
        return None, None
    try:
        dtype = torch.float16 if "cuda" in device else torch.float32
        tokenizer = AutoTokenizer.from_pretrained(base_model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            base_model_path, torch_dtype=dtype, trust_remote_code=True,
        ).to(device)
        model.eval()
        return model, tokenizer
    except Exception as exc:
        logger.error("베이스 모델 로드 실패: %s", exc)
        return None, None


def _unload_model(model) -> None:
    if model is None:
        return
    try:
        del model
        if _HAS_TORCH and torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


async def quick_sanity_check(lora_path: str) -> bool:
    """빠른 파일 무결성 체크 (전체 평가 전 필터링용)."""
    p = Path(lora_path)
    if not p.exists():
        return False
    size = p.stat().st_size
    if size < 1024:  # < 1KB
        return False
    if size > 5 * 1024 * 1024 * 1024:  # > 5GB
        return False
    # 매직 바이트 읽기 (safetensors / bin 구별 없이 파일이 읽히는지만)
    try:
        with p.open("rb") as f:
            head = f.read(16)
        return len(head) == 16
    except Exception:
        return False


async def evaluate_peer_contribution(
    peer_agent_id: str,
    peer_lora_path: str,
    base_model_path: str,
    eval_dataset: list[dict],
    max_samples: int = 100,
    device: str = "cuda:0",
) -> PeerEvalResult:
    """다른 에이전트의 LoRA를 로컬 GPU로 평가.

    - LoRA 어댑터 로드 → 평가 셋으로 forward pass
    - loss 측정
    - 간단한 이상 감지 (NaN, 무한대, 랜덤에 가까운 출력 → 0점)
    - weight norm 분석 (정상 범위인지)
    """
    start = time.time()
    issues: list[str] = []

    # 0. sanity
    if not await quick_sanity_check(peer_lora_path):
        return PeerEvalResult(
            peer_agent_id=peer_agent_id,
            peer_lora_path=peer_lora_path,
            base_model=base_model_path,
            eval_dataset=[],
            quality_score=0.0,
            issues=["sanity_check_failed"],
            evaluation_time_sec=time.time() - start,
        )

    # 1. torch/peft 없으면 fallback
    if not (_HAS_TORCH and _HAS_PEFT and _HAS_TRANSFORMERS):
        score, issues = _file_stat_based_score(peer_lora_path)
        return PeerEvalResult(
            peer_agent_id=peer_agent_id,
            peer_lora_path=peer_lora_path,
            base_model=base_model_path,
            eval_dataset=eval_dataset[:5],
            quality_score=score,
            issues=issues + ["torch_or_peft_unavailable"],
            evaluation_time_sec=time.time() - start,
        )

    # 2. 실제 평가
    model, tokenizer = load_base_model_lightweight(base_model_path, device)
    if model is None or tokenizer is None:
        score, fallback_issues = _file_stat_based_score(peer_lora_path)
        return PeerEvalResult(
            peer_agent_id=peer_agent_id,
            peer_lora_path=peer_lora_path,
            base_model=base_model_path,
            eval_dataset=eval_dataset[:5],
            quality_score=score,
            issues=fallback_issues + ["base_model_load_failed"],
            evaluation_time_sec=time.time() - start,
        )

    loss_val: float | None = None
    acc_val: float | None = None
    quality = 0.0

    try:
        peft_model = PeftModel.from_pretrained(model, peer_lora_path)
        peft_model.eval()

        # 이상 감지
        state = {k: v for k, v in peft_model.state_dict().items() if "lora_" in k}
        issues.extend(detect_anomalies(state))

        # forward pass
        samples = eval_dataset[:max_samples] if eval_dataset else []
        total_loss = 0.0
        total_correct = 0
        total = 0

        with torch.no_grad():
            for sample in samples:
                prompt = sample.get("prompt") or sample.get("input") or ""
                target = sample.get("completion") or sample.get("output") or ""
                if not prompt or not target:
                    continue
                text = f"{prompt}\n{target}"
                enc = tokenizer(
                    text, return_tensors="pt", truncation=True, max_length=1024,
                ).to(device)
                labels = enc["input_ids"].clone()
                out = peft_model(**enc, labels=labels)
                if hasattr(out, "loss") and out.loss is not None:
                    l = float(out.loss.item())
                    if not (math.isnan(l) or math.isinf(l)):
                        total_loss += l
                        total += 1
                # 단순 top-1 예측 비교
                if hasattr(out, "logits"):
                    pred = out.logits.argmax(dim=-1)
                    correct = (pred[:, :-1] == labels[:, 1:]).float().mean().item()
                    total_correct += correct

        if total > 0:
            loss_val = total_loss / total
            acc_val = total_correct / total
            # loss → 점수 (낮을수록 좋음). e^-loss 로 맵핑.
            quality = max(0.0, min(1.0, math.exp(-loss_val)))
            # 이상 있으면 감점
            if issues:
                quality *= 0.5 if len(issues) < 3 else 0.1
        else:
            quality = 0.3
            issues.append("no_valid_samples_evaluated")

        _unload_model(peft_model)
    except Exception as exc:
        logger.error("peer %s 평가 중 예외: %s", peer_agent_id, exc)
        issues.append(f"eval_exception:{type(exc).__name__}")
        quality = 0.0
    finally:
        _unload_model(model)

    return PeerEvalResult(
        peer_agent_id=peer_agent_id,
        peer_lora_path=peer_lora_path,
        base_model=base_model_path,
        eval_dataset=eval_dataset[: min(5, len(eval_dataset))],
        quality_score=quality,
        loss=loss_val,
        accuracy=acc_val,
        issues=issues,
        evaluation_time_sec=time.time() - start,
    )


# -----------------------------------------------------------------------------
# 마스터 투표 제출
# -----------------------------------------------------------------------------


async def submit_peer_vote(
    master_url: str,
    round_id: str,
    my_agent_id: str,
    peer_agent_id: str,
    score: float,
    api_key: str,
    rationale: str | None = None,
) -> dict:
    """POST /api/grid/rounds/{round_id}/peer-vote
    {peer_agent_id, score, rationale}"""
    if httpx is None:
        return {"ok": False, "error": "httpx_unavailable"}

    url = f"{master_url.rstrip('/')}/api/grid/rounds/{round_id}/peer-vote"
    payload = {
        "voter_agent_id": my_agent_id,
        "peer_agent_id": peer_agent_id,
        "score": round(max(0.0, min(1.0, score)), 4),
        "rationale": rationale or "",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            return {"ok": resp.status_code < 300, "status": resp.status_code,
                    "body": resp.text[:500]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# -----------------------------------------------------------------------------
# 전체 피어 평가 플로우
# -----------------------------------------------------------------------------


async def _list_peers_in_round(
    master_url: str, round_id: str, api_key: str,
) -> list[str]:
    if httpx is None:
        return []
    url = f"{master_url.rstrip('/')}/api/grid/rounds/{round_id}/participants"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return [p if isinstance(p, str) else p.get("agent_id", "") for p in data]
            if isinstance(data, dict):
                return data.get("agent_ids", [])
    except Exception as exc:
        logger.error("참여자 리스트 조회 실패: %s", exc)
    return []


async def evaluate_all_peers(
    master_url: str,
    round_id: str,
    my_agent_id: str,
    api_key: str,
    base_model_path: str,
    max_peers: int = 5,
) -> list[PeerEvalResult]:
    """라운드 참여 에이전트 전체 평가 (랜덤 샘플)."""
    peers = await _list_peers_in_round(master_url, round_id, api_key)
    peers = [p for p in peers if p and p != my_agent_id]
    if not peers:
        logger.info("평가할 peer 가 없음 round=%s", round_id)
        return []

    random.shuffle(peers)
    peers = peers[:max_peers]

    eval_shard = await load_eval_shard(master_url, round_id, api_key)
    results: list[PeerEvalResult] = []

    for peer_id in peers:
        lora_path = await fetch_peer_lora(master_url, round_id, peer_id, api_key)
        if not lora_path:
            results.append(PeerEvalResult(
                peer_agent_id=peer_id,
                peer_lora_path="",
                base_model=base_model_path,
                eval_dataset=[],
                quality_score=0.0,
                issues=["peer_lora_download_failed"],
            ))
            continue
        try:
            r = await evaluate_peer_contribution(
                peer_agent_id=peer_id,
                peer_lora_path=lora_path,
                base_model_path=base_model_path,
                eval_dataset=eval_shard,
            )
            results.append(r)
            # 결과 즉시 투표 제출
            await submit_peer_vote(
                master_url=master_url,
                round_id=round_id,
                my_agent_id=my_agent_id,
                peer_agent_id=peer_id,
                score=r.quality_score,
                api_key=api_key,
                rationale=";".join(r.issues[:3]) if r.issues else "ok",
            )
        except Exception as exc:
            logger.error("peer %s 평가 루프 예외: %s", peer_id, exc)
            results.append(PeerEvalResult(
                peer_agent_id=peer_id,
                peer_lora_path=lora_path,
                base_model=base_model_path,
                eval_dataset=[],
                quality_score=0.0,
                issues=[f"loop_exception:{exc}"],
            ))

    return results


async def collective_verdict(results: list[PeerEvalResult]) -> dict:
    """내 평가 결과 종합 → 마스터에 요약 제출용."""
    if not results:
        return {"evaluated_count": 0, "average_score": 0.0, "flagged_peers": []}

    scores = [r.quality_score for r in results]
    flagged = [r.peer_agent_id for r in results if r.quality_score < 0.3 or r.issues]
    return {
        "evaluated_count": len(results),
        "average_score": round(sum(scores) / len(scores), 4),
        "min_score": round(min(scores), 4),
        "max_score": round(max(scores), 4),
        "flagged_peers": flagged,
        "total_issues": sum(len(r.issues) for r in results),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "PeerEvalResult",
    "fetch_peer_lora",
    "load_eval_shard",
    "evaluate_peer_contribution",
    "detect_anomalies",
    "submit_peer_vote",
    "evaluate_all_peers",
    "collective_verdict",
    "load_base_model_lightweight",
    "quick_sanity_check",
]
