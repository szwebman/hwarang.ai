"""LoRA → 정확도 평가 워커.

vLLM 의 LoRA hot-swap 활용:

1. 평가셋 jsonl 로드 (eval_set_builder.build_or_load_eval_set)
2. 각 instruction 을 vLLM 에 전송 (``model=lora_name``)
3. 응답 수신
4. expected 와 비교:
   - exact_match : 정확히 일치 → 0/1
   - bleu (사실은 token-level F1) : ngram 일치도 0~1
   - execution  : 응답에 들어 있는 코드가 Docker 안에서 정상 실행되는지
5. 가중 합산:
   final = 0.3 * exact + 0.4 * bleu + 0.3 * execution

평균을 0~1 사이 점수로 반환. ``code_round_quality.validate_completed_round`` 에서
사용.

한계:
* ``_compute_bleu`` 는 진짜 BLEU(n-gram brevity penalty 포함) 가 아니라 token-level
  F1. 코드 길이 차이에 민감하지 않게 의도된 단순 휴리스틱.
* exact_match 는 답이 마크다운 코드펜스 등으로 감싸져 있으면 0 으로 깎이기 쉽다.
* execution 은 Docker 가 없는 환경에서는 관대하게 ``True`` 로 반환 — CI/dev 보호용.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# 화랑 vLLM 메인 (LoRA hot-swap 가능한 OpenAI 호환 엔드포인트)
VLM_URL = os.getenv(
    "HWARANG_EVAL_VLLM_URL",
    os.getenv("HWARANG_API_URL", "http://localhost:8001"),
)
DEFAULT_MAX_SAMPLES = int(os.getenv("HWARANG_EVAL_MAX_SAMPLES", "100"))
EVAL_TIMEOUT_SEC = int(os.getenv("HWARANG_EVAL_TIMEOUT_SEC", "60"))
EVAL_BATCH = int(os.getenv("HWARANG_EVAL_BATCH", "10"))

# 점수 가중치 (총합 = 1.0)
W_EXACT = 0.3
W_BLEU = 0.4
W_EXEC = 0.3

DEFAULT_FALLBACK_SCORE = 0.5


@dataclass
class EvalResult:
    """LoRA 평가 결과."""

    total: int
    exact_match: float  # 평균 0~1
    bleu_avg: float  # 평균 0~1
    execution_pass_rate: float  # 평균 0~1
    final_score: float  # W_EXACT*exact + W_BLEU*bleu + W_EXEC*exec
    sample_results: list[dict[str, Any]] = field(default_factory=list)


def _empty_result(score: float = DEFAULT_FALLBACK_SCORE) -> EvalResult:
    return EvalResult(
        total=0,
        exact_match=0.0,
        bleu_avg=0.0,
        execution_pass_rate=0.0,
        final_score=score,
        sample_results=[],
    )


# ─────────────────────────────────────────────────────────────────
# 외부 진입점
# ─────────────────────────────────────────────────────────────────
async def evaluate_lora(
    lora_name: str,
    eval_set_path: str,
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> EvalResult:
    """LoRA → 평가셋 → 점수.

    ``lora_name`` 은 vLLM 에 등록된 LoRA adapter 이름 (또는 베이스 모델명).
    """
    if not eval_set_path or not os.path.exists(eval_set_path):
        logger.warning("eval_set_path 없음 (%s) — fallback 0.5", eval_set_path)
        return _empty_result()

    samples = _load_samples(eval_set_path, max_samples)
    if not samples:
        logger.warning("eval_set 비어 있음 — fallback 0.5")
        return _empty_result()

    results: list[dict[str, Any]] = []
    sample_results: list[dict[str, Any]] = []

    for i in range(0, len(samples), EVAL_BATCH):
        batch = samples[i : i + EVAL_BATCH]
        batch_results = await asyncio.gather(
            *[_evaluate_one(s, lora_name) for s in batch],
            return_exceptions=True,
        )

        for s, r in zip(batch, batch_results):
            if isinstance(r, Exception):
                logger.debug("sample %s 평가 실패: %s", s.get("id"), r)
                continue
            results.append(r)
            if len(sample_results) < 5:
                sample_results.append(
                    {
                        "id": s.get("id"),
                        "instruction": (s.get("instruction") or "")[:200],
                        "expected": (s.get("expected") or "")[:300],
                        "actual": (r.get("actual") or "")[:300],
                        "exact_match": r.get("exact_match", 0),
                        "bleu": r.get("bleu", 0),
                        "execution_pass": r.get("execution_pass", False),
                    }
                )

    if not results:
        logger.warning("LoRA 평가 결과 0건 — vLLM 호출이 모두 실패했을 가능성")
        return _empty_result()

    exact_match = sum(r["exact_match"] for r in results) / len(results)
    bleu_avg = sum(r["bleu"] for r in results) / len(results)
    exec_pass = sum(1 for r in results if r["execution_pass"]) / len(results)
    final = W_EXACT * exact_match + W_BLEU * bleu_avg + W_EXEC * exec_pass

    return EvalResult(
        total=len(results),
        exact_match=exact_match,
        bleu_avg=bleu_avg,
        execution_pass_rate=exec_pass,
        final_score=max(0.0, min(1.0, final)),
        sample_results=sample_results,
    )


# ─────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────
def _load_samples(path: str, max_samples: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    samples.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    except OSError as exc:
        logger.warning("eval_set 로드 실패 (%s): %s", path, exc)
        return []
    return samples[:max_samples]


async def _evaluate_one(sample: dict[str, Any], lora_name: str) -> dict[str, Any]:
    """단일 sample 평가 — vLLM 호출 + 채점."""
    actual = await _call_vllm(sample.get("instruction", ""), lora_name)
    expected = sample.get("expected", "") or ""

    exact = 1.0 if actual.strip() == expected.strip() else 0.0
    bleu = _compute_bleu(actual, expected)
    execution_pass = await _check_execution(actual, sample.get("language") or "python")

    return {
        "actual": actual,
        "exact_match": exact,
        "bleu": bleu,
        "execution_pass": execution_pass,
    }


async def _call_vllm(instruction: str, lora_name: str) -> str:
    """vLLM OpenAI 호환 엔드포인트 호출. 실패 시 빈 문자열."""
    if not instruction:
        return ""
    try:
        import httpx  # type: ignore
    except ImportError:
        logger.warning("httpx 미설치 — vLLM 호출 불가")
        return ""

    try:
        async with httpx.AsyncClient(timeout=EVAL_TIMEOUT_SEC) as client:
            resp = await client.post(
                f"{VLM_URL.rstrip('/')}/v1/chat/completions",
                json={
                    "model": lora_name,
                    "messages": [{"role": "user", "content": instruction}],
                    "max_tokens": 1000,
                    "temperature": 0.1,  # 평가는 deterministic
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("vLLM 호출 예외 (%s): %s", lora_name, exc)
        return ""

    if resp.status_code != 200:
        logger.debug("vLLM 응답 %d: %s", resp.status_code, resp.text[:200])
        return ""

    try:
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
    except Exception as exc:  # noqa: BLE001
        logger.debug("vLLM 응답 파싱 실패: %s", exc)
        return ""


def _compute_bleu(actual: str, expected: str) -> float:
    """token-level F1 (BLEU 대용). 0~1.

    진짜 BLEU 아닌 점 주의 — 코드 길이 페널티 없이 단순 token 일치도만 본다.
    """
    actual_tokens = set(re.findall(r"\w+", (actual or "").lower()))
    expected_tokens = set(re.findall(r"\w+", (expected or "").lower()))
    if not expected_tokens:
        return 0.0
    common = actual_tokens & expected_tokens
    if not common:
        return 0.0
    precision = len(common) / max(len(actual_tokens), 1)
    recall = len(common) / len(expected_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


_CODE_FENCE_RE = re.compile(r"```(?:[\w+-]*\n)?(.*?)```", re.DOTALL)


async def _check_execution(code_response: str, language: str) -> bool:
    """응답에서 코드 추출 → Docker 실행. Docker 없으면 관대하게 True."""
    try:
        from hwarang_api.research.quality.sandbox.docker_runner import (
            is_docker_available,
            run_in_docker,
        )
        from hwarang_api.research.quality.sandbox.language_detector import (
            detect_language,
        )
    except ImportError as exc:
        logger.debug("sandbox 모듈 임포트 실패: %s", exc)
        return True

    if not is_docker_available():
        return True  # docker 없으면 기본 통과

    if not code_response:
        return False

    match = _CODE_FENCE_RE.search(code_response)
    if not match:
        # 코드 블록 없는 경우 — 응답 자체를 코드로 시도
        candidate = code_response.strip()
        if not candidate or len(candidate) > 8000:
            return False
        code = candidate
    else:
        code = match.group(1)

    detected = detect_language(code, hint=language)

    try:
        result = await run_in_docker(code, detected, timeout_sec=10)
    except Exception as exc:  # noqa: BLE001
        logger.debug("run_in_docker 예외: %s", exc)
        return False

    return getattr(result, "status", "") == "passed"


__all__ = [
    "EvalResult",
    "evaluate_lora",
    "VLM_URL",
    "DEFAULT_MAX_SAMPLES",
    "W_EXACT",
    "W_BLEU",
    "W_EXEC",
]
