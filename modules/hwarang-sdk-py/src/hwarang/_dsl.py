"""``/v1/hwarang/do`` DSL 헬퍼.

OpenAI 스펙을 모르는 사용자도 한 번의 호출로 결과를 받을 수 있도록
DSL → HP-Request 변환 유틸을 제공한다. 클라이언트는 이 모듈을
거치지 않아도 ``Hwarang.do(**req)`` 로 직접 사용 가능하다.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Union

from ._types import DoRequest, HwarangExtension, Intent

# 사전 정의 워크플로우 카탈로그 (docs/hp-protocol.md §6)
_KNOWN_WORKFLOWS = {
    "deploy-mobile",
    "add-api",
    "bug-fix",
    "code-review",
    "db-migrate",
}


def build_do_request(
    intent: Intent,
    *,
    input: str,
    scope: Optional[str] = None,
    target: Optional[str] = None,
    language: str = "ko",
    constraints: Optional[List[str]] = None,
    workflow: Optional[Union[str, List[str], Dict[str, Any]]] = None,
) -> DoRequest:
    """DSL 인자를 ``/v1/hwarang/do`` 요청 dict 로 정규화."""
    req: Dict[str, Any] = {
        "intent": intent,
        "input": input,
        "language": language,
    }
    if scope:
        req["scope"] = scope
    if target:
        req["target"] = target
    if constraints:
        req["constraints"] = list(constraints)
    if workflow is not None:
        req["workflow"] = workflow
    return req  # type: ignore[return-value]


def do_to_chat_extension(req: DoRequest) -> HwarangExtension:
    """``/v1/hwarang/do`` 요청을 ``@hwarang`` 확장으로 변환.

    서버가 ``/v1/hwarang/do`` 미지원이거나 클라이언트가 강제로
    ``/v1/chat/completions`` 로 보내고 싶을 때 사용.
    """
    ext: Dict[str, Any] = {
        "intent": req.get("intent"),
        "language": req.get("language") or "ko",
        "format": "markup",
        "include": ["plan", "diff", "summary"],
        "identity": "strict",
    }
    if req.get("scope"):
        ext["scope"] = req["scope"]
    if req.get("target"):
        ext["target"] = req["target"]
    if req.get("constraints"):
        ext["constraints"] = list(req["constraints"])

    workflow = req.get("workflow")
    if workflow is not None:
        ext["workflow"] = _normalize_workflow(workflow)

    return ext  # type: ignore[return-value]


def _normalize_workflow(
    workflow: Union[str, Iterable[str], Dict[str, Any]],
) -> Dict[str, Any]:
    """워크플로우 인자를 ``@hwarang.workflow`` 규격으로 정규화."""
    if isinstance(workflow, str):
        if workflow in _KNOWN_WORKFLOWS:
            return {"name": workflow}
        return {"name": "ad-hoc", "steps": [{"id": workflow}]}

    if isinstance(workflow, dict):
        return dict(workflow)

    # iterable of step ids
    steps = [{"id": str(s)} for s in workflow]
    return {"name": "ad-hoc", "steps": steps}
