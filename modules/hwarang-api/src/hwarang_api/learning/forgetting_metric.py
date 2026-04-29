"""망각 측정 — Phase 2.

학습 직후 다른 도메인 벤치마크에서 정확도가 얼마나 떨어졌는지 측정.

지표: ``forgetting_score ∈ [0, 1]`` — 낮을수록 좋음.

    forgetting_score = mean over other_domains of (1 − accuracy_d)

벤치마크 셋은 도메인별 100~200 샘플의 ground truth (jsonl).
경로: ``BENCHMARK_DIR/<domain>_eval.jsonl``
포맷: ``{"prompt": "...", "expected": "..."}``  (한 줄에 하나)

현재 구현 상태:
- 디스크 jsonl 로딩 / 모델 generate / 단순 매칭 까지 **완전 구현**.
- 매칭은 exact match + token-level F1 (난이도 낮음).
- semantic similarity (sentence-transformers) 는 TODO.
- 벤치마크 셋 자체는 별도 데이터 작업 필요 (이 파일은 채점 엔진).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

BENCHMARK_DIR = os.getenv(
    "HSEE_BENCHMARK_DIR", "/var/hwarang/benchmarks"
)

# 알려진 도메인 (벤치마크가 없으면 자동 skip)
KNOWN_DOMAINS = ["legal", "tax", "medical", "coding", "general", "reasoning"]


# ────────────────────────────────────────────────────────────
# 메인 API
# ────────────────────────────────────────────────────────────
async def measure_forgetting(
    model: Any,
    current_domain: str,
    tokenizer: Any = None,
    max_samples_per_domain: int = 50,
) -> float:
    """다른 도메인 벤치마크에서 정확도 떨어진 정도.

    Returns
    -------
    float
        0~1. 낮을수록 좋음. 벤치마크 파일이 하나도 없으면 0 반환.
    """
    other_domains = [d for d in KNOWN_DOMAINS if d != current_domain]

    losses: list[float] = []
    for d in other_domains:
        try:
            score = await _run_benchmark(
                model, d, tokenizer=tokenizer, max_samples=max_samples_per_domain
            )
            losses.append(1.0 - score)
            logger.info(f"forgetting bench[{d}] accuracy={score:.3f}")
        except FileNotFoundError:
            logger.debug(f"forgetting bench[{d}] 벤치마크 없음 — skip")
            continue
        except Exception as e:  # pragma: no cover
            logger.warning(f"forgetting bench[{d}] 실패: {e}")
            continue

    if not losses:
        return 0.0
    return sum(losses) / len(losses)


# ────────────────────────────────────────────────────────────
# 벤치마크 1 도메인 실행
# ────────────────────────────────────────────────────────────
async def _run_benchmark(
    model: Any,
    domain: str,
    tokenizer: Any = None,
    max_samples: int = 50,
) -> float:
    """단순 정확도 — exact + F1 평균."""
    items = _load_benchmark(domain, limit=max_samples)
    if not items:
        raise FileNotFoundError(f"benchmark for {domain} not found")

    total = 0.0
    n = 0
    for item in items:
        try:
            generated = _generate(model, item["prompt"], tokenizer)
        except Exception as e:  # pragma: no cover
            logger.debug(f"generate 실패 ({domain}): {e}")
            continue
        score = _score_answer(generated, item["expected"])
        total += score
        n += 1

    return total / n if n > 0 else 0.0


# ────────────────────────────────────────────────────────────
# 벤치마크 jsonl 로딩
# ────────────────────────────────────────────────────────────
def _load_benchmark(domain: str, limit: int = 50) -> list[dict]:
    path = Path(BENCHMARK_DIR) / f"{domain}_eval.jsonl"
    if not path.exists():
        raise FileNotFoundError(str(path))

    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "prompt" in row and "expected" in row:
                out.append(row)
            if len(out) >= limit:
                break
    return out


# ────────────────────────────────────────────────────────────
# 모델 호출 — torch / transformers lazy import
# ────────────────────────────────────────────────────────────
def _generate(model: Any, prompt: str, tokenizer: Any = None) -> str:
    """모델로 답변 생성. tokenizer 가 없으면 model.generate 만 시도."""
    if tokenizer is None:
        return ""

    try:
        import torch  # type: ignore
    except ImportError:  # pragma: no cover
        return ""

    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        out_ids = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
            num_beams=1,
            pad_token_id=tokenizer.eos_token_id,
        )
    text = tokenizer.decode(out_ids[0], skip_special_tokens=True)
    # prompt 부분 제거
    if text.startswith(prompt):
        text = text[len(prompt) :]
    return text.strip()


# ────────────────────────────────────────────────────────────
# 스코어링 — exact match + token F1
# ────────────────────────────────────────────────────────────
def _score_answer(generated: str, expected: str) -> float:
    """0~1 스코어. exact match 면 1, 아니면 token F1."""
    g = (generated or "").strip().lower()
    e = (expected or "").strip().lower()
    if not e:
        return 0.0
    if g == e:
        return 1.0
    return _token_f1(g, e)


def _token_f1(a: str, b: str) -> float:
    """단어 단위 F1."""
    ta = a.split()
    tb = b.split()
    if not ta or not tb:
        return 0.0
    common = set(ta) & set(tb)
    if not common:
        return 0.0
    # multiset 일치 수
    overlap = sum(min(ta.count(w), tb.count(w)) for w in common)
    if overlap == 0:
        return 0.0
    p = overlap / len(ta)
    r = overlap / len(tb)
    return 2 * p * r / (p + r)


__all__ = ["measure_forgetting"]
