"""HLKM 알림 송출 — Slack webhook + SMTP email + (옵션) Discord webhook.

각 채널은 환경변수 있을 때만 동작 (없으면 logger.info 만 기록).

환경변수:
  HWARANG_SLACK_WEBHOOK_URL     — Slack 인커밍 webhook URL
  HWARANG_DISCORD_WEBHOOK_URL   — Discord webhook URL (optional)
  HWARANG_SMTP_HOST             — SMTP 서버
  HWARANG_SMTP_PORT             — default 587
  HWARANG_SMTP_USER             — SMTP login user
  HWARANG_SMTP_PASSWORD         — SMTP password
  HWARANG_SMTP_FROM             — 보낸이 (default = SMTP_USER)
  HWARANG_ADMIN_EMAILS          — 콤마 구분 관리자 이메일 목록
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """매 호출마다 env 를 조회 — 테스트 / 런타임 갱신을 위해."""
    return os.getenv(name, default)


def _admin_emails() -> list[str]:
    raw = _env("HWARANG_ADMIN_EMAILS", "") or ""
    return [e.strip() for e in raw.split(",") if e.strip()]


_SEVERITY_COLOR = {
    "info": "#36a64f",
    "warn": "#ffae42",
    "error": "#d11212",
    "critical": "#7c1818",
}


async def notify_slack(
    text: str,
    *,
    channel: Optional[str] = None,
    severity: str = "info",
) -> bool:
    """Slack 인커밍 webhook 으로 메시지 전송.

    Returns: 전송 성공 여부 (webhook 미설정 시 False).
    """
    webhook = _env("HWARANG_SLACK_WEBHOOK_URL")
    if not webhook:
        logger.info("notify_slack skipped (no webhook): %s", text[:200])
        return False
    color = _SEVERITY_COLOR.get(severity, _SEVERITY_COLOR["info"])
    payload: dict = {
        "attachments": [
            {"color": color, "text": text, "mrkdwn_in": ["text"]}
        ]
    }
    if channel:
        payload["channel"] = channel
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json=payload)
    except httpx.HTTPError as e:
        logger.warning("notify_slack http error: %s", e)
        return False
    return resp.status_code == 200


async def notify_discord(text: str) -> bool:
    """Discord webhook 으로 메시지 전송 (옵션)."""
    webhook = _env("HWARANG_DISCORD_WEBHOOK_URL")
    if not webhook:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json={"content": text[:1900]})
    except httpx.HTTPError as e:
        logger.warning("notify_discord http error: %s", e)
        return False
    return resp.status_code in (200, 204)


def send_email(
    subject: str,
    body: str,
    *,
    recipients: Optional[list[str]] = None,
    html: bool = False,
) -> bool:
    """SMTP 메일 송출 (동기). 관리자 알림 기본 ADMIN_EMAILS.

    Returns: 송출 성공 여부.
    """
    smtp_host = _env("HWARANG_SMTP_HOST")
    smtp_user = _env("HWARANG_SMTP_USER")
    smtp_password = _env("HWARANG_SMTP_PASSWORD")
    if not (smtp_host and smtp_user and smtp_password):
        logger.info("send_email skipped (SMTP not configured): %s", subject)
        return False
    try:
        smtp_port = int(_env("HWARANG_SMTP_PORT", "587") or 587)
    except ValueError:
        smtp_port = 587
    smtp_from = _env("HWARANG_SMTP_FROM") or smtp_user

    to_list = recipients or _admin_emails()
    if not to_list:
        logger.info("send_email skipped (no recipients): %s", subject)
        return False

    msg = MIMEText(body, "html" if html else "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = ", ".join(to_list)
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        logger.warning("send_email failed: %s", e)
        return False


async def notify_admin(
    text: str,
    *,
    severity: str = "info",
    subject: Optional[str] = None,
) -> dict:
    """관리자 알림 통합 — Slack + Discord + email 동시 전송.

    Returns: 채널별 송출 성공 여부 dict.
    """
    slack_ok = await notify_slack(text, severity=severity)
    discord_ok = await notify_discord(text)
    email_ok = send_email(subject or f"[HLKM {severity}]", text)
    result = {"slack": slack_ok, "discord": discord_ok, "email": email_ok}
    logger.info("notify_admin: %s — %s", severity, result)
    return result


__all__ = [
    "notify_slack",
    "notify_discord",
    "send_email",
    "notify_admin",
]
