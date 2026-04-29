"""Theory of Mind — 사용자 멘탈 모델 (Phase 9.ζ).

사용자별 (전문성/관심사/대화 스타일/믿음/오개념) 을 누적 추적.
Prisma 모델 ``UserMentalModel`` 에 영속화하며, DB 실패 시
인메모리 폴백으로 graceful degrade 한다.

마이그레이션 필요 (schema.prisma 참조):
    model UserMentalModel {
      id                 String   @id @default(cuid())
      userId             String   @unique
      expertise          Json     @default("{}")
      interests          Json     @default("[]")
      communicationStyle String   @default("neutral")
      knownBeliefs       Json     @default("[]")
      misconceptions     Json     @default("[]")
      lastUpdated        DateTime @default(now())
    }
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from hwarang_api.knowledge.llm import _chat

logger = logging.getLogger(__name__)

_VALID_STYLES = {"formal", "casual", "technical", "neutral"}

_DEFAULT_MODEL: dict[str, Any] = {
    "expertise": {},
    "interests": [],
    "communicationStyle": "neutral",
    "knownBeliefs": [],
    "misconceptions": [],
}

# 인메모리 폴백 — DB 가 없어도 세션 내 학습은 보존
_MEM_CACHE: dict[str, dict[str, Any]] = {}


_EXTRACT_SYSTEM = (
    "너는 사용자 모델링 보조자다. 사용자의 질문과 받은 답변을 보고 "
    "사용자 특성을 JSON 으로만 추출하라. 추측은 신호가 강할 때만. "
    "응답은 단일 JSON 객체, 코드펜스 없이."
)

_EXTRACT_PROMPT_TMPL = (
    "다음 상호작용에서 사용자 특성을 추출하라.\n"
    "JSON 스키마:\n"
    "{{\n"
    '  "expertise": {{도메인: 0~1 숙련도, ...}},\n'
    '  "interests": [string],\n'
    '  "communication_style": "formal" | "casual" | "technical" | "neutral",\n'
    '  "beliefs": [{{"topic": string, "belief": string, "confidence": 0~1}}],\n'
    '  "misconceptions": [{{"topic": string, "false_belief": string}}]\n'
    "}}\n\n"
    "질문:\n{question}\n\n"
    "답변:\n{answer}\n\n"
    "피드백:\n{feedback}\n"
)

_PREDICT_SYSTEM = (
    "너는 사용자 의도/기대 예측기다. 사용자 멘탈 모델과 현재 질문을 보고 "
    "기대 답변 깊이/형식/예상 후속 질문을 JSON 으로만 출력하라."
)

_PREDICT_PROMPT_TMPL = (
    "사용자 멘탈 모델 (JSON):\n{model}\n\n"
    "현재 질문:\n{question}\n\n"
    "다음 JSON 으로 응답:\n"
    "{{\n"
    '  "expected_depth": "shallow" | "medium" | "deep",\n'
    '  "preferred_format": "text" | "list" | "code" | "table" | "step-by-step",\n'
    '  "likely_followup": string\n'
    "}}"
)

_TAILOR_SYSTEM = (
    "너는 응답 스타일 개인화기다. 사용자 멘탈 모델에 맞춰 초안 답변을 "
    "재작성하라. 사실은 변경하지 말고, 어휘/길이/예시/전문용어 설명만 조정."
)


def _safe_json(raw: str) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        v = json.loads(text[start : end + 1])
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def _default_model() -> dict[str, Any]:
    return json.loads(json.dumps(_DEFAULT_MODEL))  # deep copy via JSON


def _coerce_style(s: Any) -> str:
    if isinstance(s, str) and s.strip().lower() in _VALID_STYLES:
        return s.strip().lower()
    return "neutral"


def _merge_expertise(old: dict, new: dict) -> dict:
    """동일 도메인 반복 신호 → 점진적 평균 (확신도 누적)."""
    if not isinstance(old, dict):
        old = {}
    if not isinstance(new, dict):
        new = {}
    out = dict(old)
    for k, v in new.items():
        try:
            nv = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            continue
        if k in out:
            try:
                ov = float(out[k])
            except (TypeError, ValueError):
                ov = 0.5
            # 가중 평균 — 새 신호 30% 가중 (점진적 업데이트)
            out[k] = round(ov * 0.7 + nv * 0.3, 3)
        else:
            out[k] = round(nv, 3)
    return out


def _merge_list_unique(old: list, new: list, key: str | None = None) -> list:
    """list 병합 — key 가 있으면 그 키로 dedupe, 없으면 값 자체로 dedupe."""
    if not isinstance(old, list):
        old = []
    if not isinstance(new, list):
        new = []
    seen: set[str] = set()
    out: list[Any] = []
    for item in list(old) + list(new):
        if key and isinstance(item, dict):
            sig = str(item.get(key, "")).strip().lower()
        else:
            sig = str(item).strip().lower()
        if not sig or sig in seen:
            continue
        seen.add(sig)
        out.append(item)
    return out


class TheoryOfMind:
    """사용자 멘탈 모델 추적기."""

    async def _load(self, user_id: str) -> dict[str, Any]:
        """DB 우선, 실패 시 인메모리 캐시, 둘 다 없으면 기본 모델."""
        if not user_id:
            return _default_model()
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception as exc:  # noqa: BLE001
            logger.debug("theory_of_mind: prisma import 실패: %s", exc)
            return dict(_MEM_CACHE.get(user_id, _default_model()))

        try:
            row = await prisma.usermentalmodel.find_unique(where={"userId": user_id})
        except Exception as exc:  # noqa: BLE001
            logger.warning("theory_of_mind: load 실패 user=%s: %s", user_id, exc)
            return dict(_MEM_CACHE.get(user_id, _default_model()))

        if row is None:
            return dict(_MEM_CACHE.get(user_id, _default_model()))

        def _j(v, fallback):
            if isinstance(v, (dict, list)):
                return v
            if isinstance(v, str):
                try:
                    return json.loads(v)
                except Exception:
                    return fallback
            return fallback

        return {
            "expertise": _j(getattr(row, "expertise", {}), {}),
            "interests": _j(getattr(row, "interests", []), []),
            "communicationStyle": getattr(row, "communicationStyle", "neutral") or "neutral",
            "knownBeliefs": _j(getattr(row, "knownBeliefs", []), []),
            "misconceptions": _j(getattr(row, "misconceptions", []), []),
        }

    async def _save(self, user_id: str, model: dict[str, Any]) -> None:
        """DB 영속화 + 인메모리 캐시 갱신."""
        if not user_id:
            return
        _MEM_CACHE[user_id] = dict(model)
        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception as exc:  # noqa: BLE001
            logger.debug("theory_of_mind: prisma import 실패 (cache only): %s", exc)
            return

        payload = {
            "expertise": json.dumps(model.get("expertise", {}), ensure_ascii=False),
            "interests": json.dumps(model.get("interests", []), ensure_ascii=False),
            "communicationStyle": _coerce_style(model.get("communicationStyle")),
            "knownBeliefs": json.dumps(model.get("knownBeliefs", []), ensure_ascii=False),
            "misconceptions": json.dumps(model.get("misconceptions", []), ensure_ascii=False),
        }
        try:
            await prisma.usermentalmodel.upsert(
                where={"userId": user_id},
                data={
                    "create": {"userId": user_id, **payload},
                    "update": payload,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("theory_of_mind: save 실패 user=%s: %s", user_id, exc)

    async def get_model(self, user_id: str) -> dict[str, Any]:
        """공개 조회 — 폴백 포함."""
        return await self._load(user_id)

    async def update_from_interaction(
        self,
        user_id: str,
        question: str,
        answer: str,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        """LLM 으로 사용자 신호 추출 후 기존 모델에 점진적 머지."""
        prompt = _EXTRACT_PROMPT_TMPL.format(
            question=(question or "").strip()[:3000],
            answer=(answer or "").strip()[:4000],
            feedback=(feedback or "(없음)")[:1500],
        )
        try:
            raw = await _chat(prompt, system=_EXTRACT_SYSTEM, max_tokens=600)
        except Exception as exc:  # noqa: BLE001
            logger.warning("update_from_interaction LLM 실패: %s", exc)
            raw = ""

        signal = _safe_json(raw) or {}
        existing = await self._load(user_id)

        merged: dict[str, Any] = {
            "expertise": _merge_expertise(
                existing.get("expertise", {}),
                signal.get("expertise", {}) if isinstance(signal.get("expertise"), dict) else {},
            ),
            "interests": _merge_list_unique(
                existing.get("interests", []),
                signal.get("interests", []) if isinstance(signal.get("interests"), list) else [],
            ),
            "communicationStyle": _coerce_style(
                signal.get("communication_style")
                if signal.get("communication_style")
                else existing.get("communicationStyle")
            ),
            "knownBeliefs": _merge_list_unique(
                existing.get("knownBeliefs", []),
                signal.get("beliefs", []) if isinstance(signal.get("beliefs"), list) else [],
                key="topic",
            ),
            "misconceptions": _merge_list_unique(
                existing.get("misconceptions", []),
                signal.get("misconceptions", [])
                if isinstance(signal.get("misconceptions"), list)
                else [],
                key="topic",
            ),
        }

        await self._save(user_id, merged)
        return merged

    async def predict_user_need(
        self, user_id: str, current_question: str
    ) -> dict[str, Any]:
        """사용자 기대 깊이/형식/후속질문 예측."""
        model = await self._load(user_id)
        prompt = _PREDICT_PROMPT_TMPL.format(
            model=json.dumps(model, ensure_ascii=False)[:3000],
            question=(current_question or "").strip()[:2000],
        )
        try:
            raw = await _chat(prompt, system=_PREDICT_SYSTEM, max_tokens=300)
        except Exception as exc:  # noqa: BLE001
            logger.warning("predict_user_need LLM 실패: %s", exc)
            raw = ""

        data = _safe_json(raw) or {}
        depth = data.get("expected_depth")
        if depth not in {"shallow", "medium", "deep"}:
            depth = "medium"
        fmt = data.get("preferred_format")
        if fmt not in {"text", "list", "code", "table", "step-by-step"}:
            fmt = "text"
        followup = data.get("likely_followup")
        if not isinstance(followup, str):
            followup = ""

        return {
            "expected_depth": depth,
            "preferred_format": fmt,
            "likely_followup": followup.strip()[:500],
        }

    async def tailor_response(self, user_id: str, draft_answer: str) -> str:
        """초안을 사용자 스타일에 맞춰 재작성. 사실 변경 금지."""
        if not draft_answer:
            return ""
        model = await self._load(user_id)
        prompt = (
            f"사용자 멘탈 모델 (JSON):\n{json.dumps(model, ensure_ascii=False)[:2500]}\n\n"
            f"초안 답변:\n{draft_answer[:6000]}\n\n"
            "지시: 초안을 사용자에게 맞게 재작성하라. "
            "전문성이 낮으면 전문용어를 풀어 설명, 'casual' 스타일이면 격식 낮춤, "
            "'technical' 이면 정확한 용어 사용. 사실은 변경하지 말 것. "
            "재작성된 답변만 출력하라."
        )
        try:
            raw = await _chat(prompt, system=_TAILOR_SYSTEM, max_tokens=900)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tailor_response LLM 실패: %s", exc)
            return draft_answer
        out = (raw or "").strip()
        return out or draft_answer


__all__ = ["TheoryOfMind"]
