"""HLKM LLM 보조 함수.

Hwarang LLM (OpenAI 호환 엔드포인트)에 프롬프트를 보내
모순/동등/엔티티/시간관계 등을 판정한다.

환경변수:
  HWARANG_LLM_URL       - base URL (default http://localhost:8000/v1)
  HWARANG_LLM_API_KEY   - Bearer 토큰
  HWARANG_LLM_MODEL     - 모델 이름 (default qwen2.5-72b)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_LLM_URL = os.getenv("HWARANG_LLM_URL", "http://localhost:8000/v1")
_LLM_KEY = os.getenv("HWARANG_LLM_API_KEY", "")
_LLM_MODEL = os.getenv("HWARANG_LLM_MODEL", "qwen2.5-72b")
_LLM_TIMEOUT = float(os.getenv("HWARANG_LLM_TIMEOUT", "30.0"))


async def _chat(prompt: str, system: str | None = None, max_tokens: int = 256) -> str:
    """내부 helper: /chat/completions 호출 후 content 문자열만 반환.

    실패 시 빈 문자열을 반환해 호출측에서 graceful fallback 가능.
    """
    try:
        import httpx
    except Exception:
        return ""

    msgs: list[dict[str, str]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if _LLM_KEY:
        headers["Authorization"] = f"Bearer {_LLM_KEY}"

    try:
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
            r = await client.post(
                f"{_LLM_URL.rstrip('/')}/chat/completions",
                json={
                    "model": _LLM_MODEL,
                    "messages": msgs,
                    "max_tokens": max_tokens,
                    "temperature": 0.0,
                },
                headers=headers,
            )
            if r.status_code != 200:
                return ""
            data: Any = r.json()
            choices = data.get("choices") or []
            if not choices:
                return ""
            return (choices[0].get("message", {}) or {}).get("content", "") or ""
    except Exception:
        return ""


async def llm_check_contradiction(a: str, b: str) -> tuple[bool, str]:
    """두 진술이 모순인지 LLM 에 문의.

    반환: (is_contradiction, reasoning). LLM 실패 시 (False, '').
    프롬프트는 첫 토큰으로 YES|NO 를 받고, 이후 자유기술.
    """
    system = (
        "You are a precise fact-checker. "
        "Answer with YES or NO at the very first word, then a brief reason."
    )
    prompt = f"Do these two statements contradict each other?\nA: {a}\nB: {b}"
    resp = await _chat(prompt, system=system, max_tokens=180)
    if not resp:
        return (False, "")
    head = resp.strip().upper()
    is_contra = head.startswith("YES")
    return (is_contra, resp.strip())


async def llm_check_semantic_equivalence(a: str, b: str) -> tuple[bool, float]:
    """두 문장이 같은 뜻인지 + 확신도(0~1).

    응답 예: `YES 0.92`. 파싱 실패 시 (False, 0.0).
    """
    system = (
        "Reply with 'YES <confidence>' or 'NO <confidence>' where confidence is 0.0 to 1.0. "
        "No extra words."
    )
    prompt = f"Do these two statements have the SAME meaning?\nA: {a}\nB: {b}"
    resp = await _chat(prompt, system=system, max_tokens=20)
    if not resp:
        return (False, 0.0)
    m = re.match(r"^\s*(YES|NO)\s+([0-9.]+)", resp.strip().upper())
    if not m:
        return (resp.strip().upper().startswith("YES"), 0.5)
    same = m.group(1) == "YES"
    try:
        conf = max(0.0, min(1.0, float(m.group(2))))
    except ValueError:
        conf = 0.5
    return (same, conf)


async def llm_extract_entity_candidates(content: str) -> list[str]:
    """본문에서 엔티티(고유명사/주요 개념) 후보 추출.

    JSON 배열 응답 기대. 파싱 실패 시 공백 분리 fallback.
    """
    system = (
        "Extract Korean/English named entities or key concepts from the text. "
        'Reply ONLY as a JSON array of strings, e.g. ["최저시급","근로기준법"].'
    )
    resp = await _chat(content, system=system, max_tokens=200)
    if not resp:
        return []
    # JSON 추출 시도
    try:
        start = resp.find("[")
        end = resp.rfind("]")
        if start != -1 and end != -1 and end > start:
            arr = json.loads(resp[start : end + 1])
            return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    # fallback: 쉼표/줄바꿈 분리
    return [t.strip() for t in re.split(r"[,\n]", resp) if t.strip()]


async def llm_summarize_changes(old: str, new: str) -> str:
    """두 버전 사이의 자연어 변경 요약."""
    system = "Summarize what changed between OLD and NEW in 1-2 Korean sentences. Concise."
    prompt = f"OLD:\n{old}\n\nNEW:\n{new}"
    resp = await _chat(prompt, system=system, max_tokens=220)
    return resp.strip()


async def llm_check_temporal_relation(a: str, b: str) -> tuple[str, float]:
    """A 와 B 사이의 시간/인과 관계 판정.

    반환: (label, confidence). label ∈ {CAUSES, ENABLES, RELATED_TO, NONE}.
    """
    valid = {"CAUSES", "ENABLES", "RELATED_TO", "NONE"}
    system = (
        "Classify the relation from A to B. "
        "Reply with one of: CAUSES, ENABLES, RELATED_TO, NONE, then a space, then confidence 0.0-1.0."
    )
    prompt = f"A: {a}\nB: {b}"
    resp = await _chat(prompt, system=system, max_tokens=20)
    if not resp:
        return ("NONE", 0.0)
    m = re.match(r"^\s*([A-Z_]+)\s+([0-9.]+)", resp.strip().upper())
    if not m:
        for label in valid:
            if resp.strip().upper().startswith(label):
                return (label, 0.5)
        return ("NONE", 0.0)
    label = m.group(1)
    if label not in valid:
        label = "NONE"
    try:
        conf = max(0.0, min(1.0, float(m.group(2))))
    except ValueError:
        conf = 0.5
    return (label, conf)


__all__ = [
    "llm_check_contradiction",
    "llm_check_semantic_equivalence",
    "llm_extract_entity_candidates",
    "llm_summarize_changes",
    "llm_check_temporal_relation",
]
