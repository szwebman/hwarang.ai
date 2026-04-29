"""에이전트 측 HTTP 서버 — Master 의 cognitive consult 수신.

aiohttp 기반의 가벼운 4 엔드포인트:

* ``POST /cognitive/consult``   — 라운드 의향 묻기 (decide_about_round 호출)
* ``POST /cognitive/negotiate`` — 조건 변경 제안 (보상↑ / 시간↓ 등)
* ``GET  /cognitive/state``     — 현재 에이전트 상태 (디버그/모니터링)
* ``POST /cognitive/notify``    — 마스터 알림 (LoRA 업데이트, 라운드 취소 등)

인증
----
``HWARANG_AGENT_CALLBACK_TOKEN`` 환경변수가 설정되면 ``Authorization: Bearer <token>``
헤더 검증. 빈 문자열이면 토큰 검증 비활성 (개발 모드).

기동
----
``agent_main.py`` 가 ``HWARANG_AGENT_COGNITIVE=true`` 일 때
``start_callback_server()`` 를 호출 → ``aiohttp.web.AppRunner`` 가 백그라운드
에서 0.0.0.0:7878 을 바인딩 (포트는 ``HWARANG_AGENT_CALLBACK_PORT``).

종료
----
``stop_callback_server(runner)`` — 에이전트 ``stop()`` 에서 호출.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _callback_token() -> str:
    """현재 토큰 — 매 호출 시 env 재조회 (테스트 편의)."""
    return os.getenv("HWARANG_AGENT_CALLBACK_TOKEN", "")


def _check_token(request) -> bool:
    """간단 Bearer 토큰 검증. 토큰 미설정이면 통과."""
    expected = _callback_token()
    if not expected:
        return True
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        auth = auth[7:].strip()
    return auth == expected


# ───────────────────────────────────────────────────────────────
# Handlers — 모두 aiohttp.web.Request → web.Response.
# 실제 의사결정/상태수집은 cognitive 서브패키지의 decide_about_round /
# collect_state 에 위임.
# ───────────────────────────────────────────────────────────────


async def handle_consult(request):
    """Master 가 라운드 의향 물음.

    Body: ``{round_id, domain, estimated_minutes, estimated_hwr, min_vram_gb, sample_count}``
    Response: ``{action, confidence, reasoning, suggested_alternatives}``
    """
    from aiohttp import web

    if not _check_token(request):
        return web.json_response({"error": "auth"}, status=401)

    try:
        data = await request.json()
    except Exception as exc:
        return web.json_response({"error": f"bad_json: {exc}"}, status=400)

    try:
        from .decision_engine import RoundOffer, decide_about_round
    except Exception as exc:
        logger.warning("decision_engine import 실패: %s", exc)
        return web.json_response(
            {"action": "accept", "confidence": 0.5, "reasoning": "engine 없음 — 기본 수락"},
        )

    try:
        offer = RoundOffer(
            round_id=str(data.get("round_id", "consult")),
            domain=str(data.get("domain", "general")),
            estimated_minutes=int(data.get("estimated_minutes", 30) or 30),
            estimated_hwr=float(data.get("estimated_hwr", 100) or 100),
            min_vram_gb=float(data.get("min_vram_gb", 8) or 8),
            sample_count=int(data.get("sample_count", 1000) or 1000),
        )
        use_llm = os.getenv("HWARANG_AGENT_LLM_DECIDE", "false").lower() in ("1", "true", "yes")
        decision = await decide_about_round(offer, use_llm=use_llm)
        return web.json_response({
            "action": decision.action,
            "confidence": float(decision.confidence),
            "reasoning": decision.reasoning,
            "suggested_alternatives": list(decision.suggested_alternatives or []),
        })
    except Exception as exc:
        logger.exception("consult 처리 실패")
        return web.json_response({"error": str(exc)}, status=500)


async def handle_negotiate(request):
    """Master 가 조건 변경 (보상 ↑ / 시간 ↓) 제안 — 재평가.

    Body: ``{round_id, domain, new_estimated_minutes?, new_estimated_hwr?, ...}``
    Response: ``{accepted, confidence, reasoning}``
    """
    from aiohttp import web

    if not _check_token(request):
        return web.json_response({"error": "auth"}, status=401)

    try:
        data = await request.json()
    except Exception as exc:
        return web.json_response({"error": f"bad_json: {exc}"}, status=400)

    try:
        from .decision_engine import RoundOffer, decide_about_round
    except Exception:
        return web.json_response({"accepted": True, "confidence": 0.5, "reasoning": "engine 없음 — 수락"})

    try:
        offer = RoundOffer(
            round_id=str(data.get("round_id", "negotiate")),
            domain=str(data.get("domain", "general")),
            estimated_minutes=int(
                data.get("new_estimated_minutes", data.get("estimated_minutes", 30)) or 30
            ),
            estimated_hwr=float(
                data.get("new_estimated_hwr", data.get("estimated_hwr", 100)) or 100
            ),
            min_vram_gb=float(data.get("min_vram_gb", 8) or 8),
            sample_count=int(data.get("sample_count", 1000) or 1000),
        )
        decision = await decide_about_round(offer, use_llm=False)
        return web.json_response({
            "accepted": decision.action == "accept",
            "confidence": float(decision.confidence),
            "reasoning": decision.reasoning,
        })
    except Exception as exc:
        logger.exception("negotiate 처리 실패")
        return web.json_response({"error": str(exc)}, status=500)


async def handle_state(request):
    """현재 에이전트 상태 조회 — 디버그/모니터링."""
    from aiohttp import web

    if not _check_token(request):
        return web.json_response({"error": "auth"}, status=401)

    try:
        from .state_collector import collect_state
        state = await collect_state()
        return web.json_response(dataclasses.asdict(state))
    except Exception as exc:
        logger.exception("state 수집 실패")
        return web.json_response({"error": str(exc)}, status=500)


async def handle_notify(request):
    """Master 알림 수신 — 비동기 처리. 즉시 ACK 후 백그라운드에서 작업."""
    from aiohttp import web

    if not _check_token(request):
        return web.json_response({"error": "auth"}, status=401)

    try:
        data = await request.json()
    except Exception as exc:
        return web.json_response({"error": f"bad_json: {exc}"}, status=400)

    notify_type = data.get("type", "unknown")
    message = data.get("message", "")
    logger.info("Master 알림: %s — %s", notify_type, str(message)[:200])

    # 알림 타입별 후속 처리 — 향후 확장.
    # lora_updated:    pull_latest_lora 트리거
    # round_cancelled: 진행 중 라운드 중단
    # config_updated:  config 재로드
    # 현재는 로깅만.

    return web.json_response({"received": True, "type": notify_type})


# ───────────────────────────────────────────────────────────────
# 서버 lifecycle
# ───────────────────────────────────────────────────────────────


async def start_callback_server(
    port: int = 7878,
    host: str = "0.0.0.0",
):
    """callback HTTP 서버 시작 → ``AppRunner`` 반환.

    호출자는 반환된 runner 를 보관했다가 ``stop_callback_server(runner)``
    로 정리한다. 이미 실행 중인 asyncio 루프 안에서 호출 가능.
    """
    try:
        from aiohttp import web
    except ImportError:
        logger.warning("aiohttp 없음 — callback 서버 비활성")
        return None

    app = web.Application()
    app.router.add_post("/cognitive/consult", handle_consult)
    app.router.add_post("/cognitive/negotiate", handle_negotiate)
    app.router.add_get("/cognitive/state", handle_state)
    app.router.add_post("/cognitive/notify", handle_notify)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Cognitive callback 서버 시작: http://%s:%d", host, port)
    return runner


async def stop_callback_server(runner) -> None:
    """callback 서버 정리. runner=None 이면 noop."""
    if runner is None:
        return
    try:
        await runner.cleanup()
        logger.info("Cognitive callback 서버 종료")
    except Exception as exc:  # noqa: BLE001
        logger.debug("callback 서버 종료 중 예외: %s", exc)


def get_local_ip() -> str:
    """LAN IP 추정 — 마스터에 callback_url 등록할 때 사용.

    NAT 환경에서는 외부 노출이 필요하므로 ``HWARANG_AGENT_CALLBACK_PUBLIC_URL``
    환경변수가 우선.
    """
    public = os.getenv("HWARANG_AGENT_CALLBACK_PUBLIC_URL", "").strip()
    if public:
        return public

    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def build_callback_url(port: int) -> str:
    """``HWARANG_AGENT_CALLBACK_PUBLIC_URL`` 우선, 없으면 LAN IP + port."""
    public = os.getenv("HWARANG_AGENT_CALLBACK_PUBLIC_URL", "").strip()
    if public:
        return public.rstrip("/")
    return f"http://{get_local_ip()}:{port}"


__all__ = [
    "start_callback_server",
    "stop_callback_server",
    "get_local_ip",
    "build_callback_url",
    "handle_consult",
    "handle_negotiate",
    "handle_state",
    "handle_notify",
]
