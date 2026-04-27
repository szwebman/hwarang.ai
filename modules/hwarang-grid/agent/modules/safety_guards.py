"""에이전트 안전장치 — 공격적 라운드 거부, 리소스 한도, 온도 모니터링.

역할:
  - 마스터가 내려준 라운드 메타를 검사해 악의적 패턴을 탐지.
  - 샤드 파일의 해시/내용 검증으로 변조·페이로드 주입 방어.
  - GPU 온도/VRAM/지속시간 한도를 강제해 하드웨어 보호.
  - 의심 마스터를 peer (p2p_collaboration) 로 경고 방송.

설계 철학:
  - torch, pynvml 등은 선택 의존성. 없으면 nvidia-smi subprocess fallback,
    그마저도 없으면 온도 체크는 skip (로그 경고만).
  - 설정은 YAML (PyYAML 있으면) / JSON (없으면) 자동 선택.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore
    _HAS_YAML = False

try:
    import pynvml  # type: ignore
    _HAS_PYNVML = True
except ImportError:  # pragma: no cover
    pynvml = None  # type: ignore
    _HAS_PYNVML = False

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# 의심 패턴 사전 (경고 메시지 매핑)
# -----------------------------------------------------------------------------

SUSPICION_PATTERNS: dict[str, str] = {
    "unusually_high_reward": "예상 대비 보상이 10배 이상 높음 — 함정 가능성",
    "unknown_master": "등록되지 않은 마스터의 요청",
    "oversized_shard": "샤드 크기가 비정상적으로 큼 (DoS)",
    "invalid_shard_hash": "샤드 해시 불일치 (변조)",
    "extreme_lora_rank": "LoRA rank 가 매우 큼 (자원 고갈 공격)",
    "suspicious_domain": "프로필에 없는 완전 새 도메인",
    "malformed_data": "훈련 데이터가 알 수 없는 형식",
    "prompt_injection": "샤드에 프롬프트 인젝션 패턴 감지",
    "encoded_payload": "base64/hex 인코딩된 의심 페이로드",
    "excessive_repetition": "과도한 반복 — DoS/spam 데이터",
    "overheating": "GPU 온도 한도 초과",
    "vram_overflow": "VRAM 사용량 초과",
    "duration_exceeded": "작업 지속 시간 초과",
    "negative_reward_ratio": "보상 대비 전기료가 비효율적",
}


# -----------------------------------------------------------------------------
# 설정
# -----------------------------------------------------------------------------


@dataclass
class SafetyConfig:
    max_vram_gb: int = 24
    max_duration_minutes: int = 120
    max_temperature_celsius: int = 85
    max_concurrent_rounds: int = 1
    max_shard_size_mb: int = 500
    max_lora_rank: int = 64
    require_master_whitelist: bool = True
    trusted_masters: list[str] = field(default_factory=list)
    min_reward_to_risk_ratio: float = 0.8  # 보상/전기세
    max_reward_multiplier: float = 10.0  # 기준 대비 N배 이상이면 의심
    baseline_reward: int = 100  # 라운드당 기대 HWARANG
    allowed_domains: list[str] = field(default_factory=list)  # 비어 있으면 제한 없음


def _default_path() -> Path:
    return Path(os.path.expanduser("~/.hwarang/safety.yaml"))


def load_safety_config(path: str | None = None) -> SafetyConfig:
    p = Path(os.path.expanduser(path)) if path else _default_path()
    if not p.exists():
        return SafetyConfig()
    try:
        raw = p.read_text(encoding="utf-8")
        if p.suffix in (".yaml", ".yml") and _HAS_YAML:
            data = yaml.safe_load(raw) or {}
        else:
            data = json.loads(raw)
        return SafetyConfig(**{k: v for k, v in data.items() if k in SafetyConfig.__dataclass_fields__})
    except Exception as exc:
        logger.error("safety config 로드 실패 (%s) — 기본값 사용: %s", p, exc)
        return SafetyConfig()


def save_safety_config(config: SafetyConfig, path: str | None = None) -> None:
    p = Path(os.path.expanduser(path)) if path else _default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(config)
    if p.suffix in (".yaml", ".yml") and _HAS_YAML:
        p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    else:
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("safety config 저장: %s", p)


# -----------------------------------------------------------------------------
# 악의적 라운드 탐지
# -----------------------------------------------------------------------------


def verify_master_identity(master_url: str, config: SafetyConfig) -> bool:
    """마스터 URL 이 화이트리스트에 있는지."""
    if not config.require_master_whitelist:
        return True
    if not master_url:
        return False
    normalized = master_url.rstrip("/").lower()
    for trusted in config.trusted_masters:
        if trusted.rstrip("/").lower() == normalized:
            return True
    return False


async def detect_malicious_round(round_meta: dict, config: SafetyConfig) -> list[str]:
    """라운드 메타에서 의심 패턴 감지.

    Return: 감지된 경고 key 리스트. 비어있으면 안전.
    """
    warnings: list[str] = []
    if not isinstance(round_meta, dict):
        return ["malformed_data"]

    # 마스터 검증
    master_url = round_meta.get("master_url") or round_meta.get("origin")
    if master_url and not verify_master_identity(master_url, config):
        warnings.append("unknown_master")

    # 보상 이상치
    reward = round_meta.get("expected_reward") or round_meta.get("reward") or 0
    try:
        reward = int(reward)
    except (TypeError, ValueError):
        reward = 0
    if config.baseline_reward > 0 and reward > config.baseline_reward * config.max_reward_multiplier:
        warnings.append("unusually_high_reward")

    # 샤드 크기
    shard_size_mb = round_meta.get("shard_size_mb") or 0
    if shard_size_mb and shard_size_mb > config.max_shard_size_mb:
        warnings.append("oversized_shard")

    # LoRA rank
    lora_rank = round_meta.get("lora_rank") or round_meta.get("rank") or 0
    if lora_rank and lora_rank > config.max_lora_rank:
        warnings.append("extreme_lora_rank")

    # 도메인 검증
    domain = round_meta.get("domain")
    if config.allowed_domains and domain and domain not in config.allowed_domains:
        warnings.append("suspicious_domain")

    # 예상 지속 시간
    dur_min = round_meta.get("duration_minutes") or 0
    if dur_min and dur_min > config.max_duration_minutes:
        warnings.append("duration_exceeded")

    return warnings


# -----------------------------------------------------------------------------
# 샤드 검증
# -----------------------------------------------------------------------------


async def validate_shard_integrity(shard_path: str, expected_hash: str) -> bool:
    """샤드 파일 SHA256 검증."""
    p = Path(shard_path)
    if not p.exists():
        return False
    if not expected_hash:
        return True  # 검증 스킵 (해시 없음)
    expected = expected_hash.strip().lower().replace("sha256:", "")

    hasher = hashlib.sha256()
    try:
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
    except Exception as exc:
        logger.error("샤드 해시 계산 실패: %s", exc)
        return False

    return hasher.hexdigest().lower() == expected


_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(the\s+)?(previous|above|prior)\s+instructions"),
    re.compile(r"(?i)you\s+are\s+now\s+(a|an)\s+\w+"),
    re.compile(r"(?i)system\s*:\s*you\s+must"),
    re.compile(r"(?i)jailbreak"),
    re.compile(r"(?i)disregard\s+safety"),
]

_BASE64_RE = re.compile(r"(?:[A-Za-z0-9+/]{120,}={0,2})")
_HEX_RE = re.compile(r"(?:[0-9a-fA-F]{200,})")


def _sample_records(shard_path: Path, sample_size: int) -> list[str]:
    """jsonl / json / txt 각각에서 최대 sample_size 개 추출."""
    texts: list[str] = []
    try:
        with shard_path.open("r", encoding="utf-8", errors="ignore") as f:
            if shard_path.suffix in (".jsonl", ".ndjson"):
                for i, line in enumerate(f):
                    if i >= sample_size:
                        break
                    try:
                        obj = json.loads(line)
                        texts.append(json.dumps(obj, ensure_ascii=False)[:4000])
                    except Exception:
                        texts.append(line[:4000])
            elif shard_path.suffix == ".json":
                try:
                    data = json.load(f)
                    if isinstance(data, list):
                        for obj in data[:sample_size]:
                            texts.append(json.dumps(obj, ensure_ascii=False)[:4000])
                    elif isinstance(data, dict):
                        for v in list(data.values())[:sample_size]:
                            texts.append(json.dumps(v, ensure_ascii=False)[:4000])
                except Exception:
                    pass
            else:
                # plain text
                for i, line in enumerate(f):
                    if i >= sample_size:
                        break
                    texts.append(line[:4000])
    except Exception as exc:
        logger.warning("샤드 샘플링 실패: %s", exc)
    return texts


async def validate_shard_content(shard_path: str, sample_size: int = 10) -> list[str]:
    """샤드 내용 샘플 분석 → 의심 데이터 감지.

    - 과도한 반복 (prompt injection)
    - base64 / hex 인코딩된 악성 페이로드
    - 비정상적으로 긴 토큰
    - 유해 콘텐츠 패턴
    """
    warnings: list[str] = []
    p = Path(shard_path)
    if not p.exists():
        return ["shard_missing"]

    texts = _sample_records(p, sample_size)
    if not texts:
        return ["shard_unreadable"]

    # 중복률
    unique_ratio = len(set(texts)) / len(texts)
    if unique_ratio < 0.3:
        warnings.append("excessive_repetition")

    for t in texts:
        for pat in _INJECTION_PATTERNS:
            if pat.search(t):
                warnings.append("prompt_injection")
                break
        if _BASE64_RE.search(t) or _HEX_RE.search(t):
            warnings.append("encoded_payload")
        # 단일 토큰(공백 없이) 길이가 지나치게 긴 경우
        max_token = max((len(tok) for tok in t.split()), default=0)
        if max_token > 2000:
            warnings.append("malformed_data")

    return sorted(set(warnings))


# -----------------------------------------------------------------------------
# GPU 온도 / 리소스 모니터링
# -----------------------------------------------------------------------------


def _smi_temperature() -> int | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
        if not out:
            return None
        return max(int(x) for x in out.splitlines() if x.strip().isdigit())
    except Exception:
        return None


def _smi_vram_used_gb() -> float | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
        if not out:
            return None
        used_mb = max(int(x) for x in out.splitlines() if x.strip().isdigit())
        return round(used_mb / 1024.0, 2)
    except Exception:
        return None


async def monitor_gpu_temperature(max_temp: int = 85) -> dict:
    """현재 GPU 온도 체크. 과열 시 작업 중단 신호."""
    temp: int | None = None

    if _HAS_PYNVML:
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            temps: list[int] = []
            for i in range(count):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                temps.append(pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU))
            if temps:
                temp = max(temps)
            pynvml.nvmlShutdown()
        except Exception:
            temp = None

    if temp is None:
        temp = _smi_temperature()

    if temp is None:
        return {"temperature": None, "safe": True, "source": "unavailable"}

    return {
        "temperature": temp,
        "max_temp": max_temp,
        "safe": temp < max_temp,
        "warning": "overheating" if temp >= max_temp else None,
        "source": "pynvml" if _HAS_PYNVML else "nvidia-smi",
    }


async def enforce_resource_limits(
    round_id: str,
    max_vram_gb: int,
    max_duration_sec: int,
    cancel_callback: Callable[[str, str], Any],
    poll_interval_sec: float = 10.0,
) -> None:
    """백그라운드 모니터. 한계 초과 시 cancel_callback 호출.

    cancel_callback(round_id, reason) — async/sync 둘 다 허용.
    """
    start = time.time()
    while True:
        await asyncio.sleep(poll_interval_sec)
        elapsed = time.time() - start

        if elapsed > max_duration_sec:
            reason = "duration_exceeded"
            logger.warning("round %s 지속시간 초과 — 취소", round_id)
            res = cancel_callback(round_id, reason)
            if asyncio.iscoroutine(res):
                await res
            return

        vram = _smi_vram_used_gb()
        if vram is not None and vram > max_vram_gb:
            reason = f"vram_overflow:{vram:.1f}GB>{max_vram_gb}GB"
            logger.warning("round %s VRAM 초과 — 취소", round_id)
            res = cancel_callback(round_id, reason)
            if asyncio.iscoroutine(res):
                await res
            return

        temp_info = await monitor_gpu_temperature()
        if temp_info.get("warning") == "overheating":
            reason = f"overheating:{temp_info['temperature']}C"
            logger.warning("round %s 과열 — 취소", round_id)
            res = cancel_callback(round_id, reason)
            if asyncio.iscoroutine(res):
                await res
            return


# -----------------------------------------------------------------------------
# 종합 리스크 점수
# -----------------------------------------------------------------------------


async def compute_round_risk_score(round_meta: dict, config: SafetyConfig) -> dict:
    """라운드 종합 리스크 점수 0~1.

    Return: {"risk": 0.3, "factors": [...], "recommendation": "safe|caution|reject"}
    """
    warnings = await detect_malicious_round(round_meta, config)

    # factor 별 가중치
    weights = {
        "unknown_master":          0.45,
        "unusually_high_reward":   0.30,
        "oversized_shard":         0.20,
        "extreme_lora_rank":       0.25,
        "invalid_shard_hash":      0.50,
        "suspicious_domain":       0.15,
        "duration_exceeded":       0.15,
        "prompt_injection":        0.35,
        "encoded_payload":         0.40,
        "excessive_repetition":    0.20,
        "malformed_data":          0.30,
    }

    risk = 0.0
    factors: list[dict] = []
    for w in warnings:
        weight = weights.get(w, 0.1)
        risk = min(1.0, risk + weight)
        factors.append({
            "key": w,
            "weight": weight,
            "message": SUSPICION_PATTERNS.get(w, w),
        })

    if risk < 0.2:
        rec = "safe"
    elif risk < 0.5:
        rec = "caution"
    else:
        rec = "reject"

    return {
        "risk": round(risk, 3),
        "factors": factors,
        "recommendation": rec,
        "evaluated_at": time.time(),
    }


# -----------------------------------------------------------------------------
# 긴급 종료 / 경고 방송
# -----------------------------------------------------------------------------


async def emergency_shutdown(reason: str) -> None:
    """모든 진행 중 작업 중단 + 로그 기록."""
    logger.critical("EMERGENCY SHUTDOWN: %s", reason)
    log_path = Path(os.path.expanduser("~/.hwarang/emergency.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": time.time(),
            "reason": reason,
        }, ensure_ascii=False) + "\n")

    # 현재 asyncio task 중 자신 외 모두 취소
    try:
        current = asyncio.current_task()
        for t in asyncio.all_tasks():
            if t is not current and not t.done():
                t.cancel()
    except Exception:
        pass


async def report_suspicious_master(master_url: str, reason: str) -> None:
    """다른 에이전트들에게 경고 (P2P 방송 — p2p_collaboration.py 활용)."""
    payload = {
        "type": "suspicious_master_alert",
        "master_url": master_url,
        "reason": reason,
        "reported_at": time.time(),
    }
    # 로컬 로그 먼저
    log_path = Path(os.path.expanduser("~/.hwarang/suspicious_masters.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    # p2p 모듈 lazy import (선택 의존성)
    try:
        from . import p2p_collaboration  # type: ignore
        broadcaster = getattr(p2p_collaboration, "broadcast_alert", None)
        if broadcaster is None:
            broadcaster = getattr(p2p_collaboration, "broadcast", None)
        if broadcaster is not None:
            res = broadcaster(payload)
            if asyncio.iscoroutine(res):
                await res
            logger.info("의심 마스터 경고 방송 전송: %s", master_url)
        else:
            logger.info("p2p_collaboration broadcast 미지원 — 로컬 로그만 남김")
    except Exception as exc:
        logger.warning("p2p 경고 방송 실패 (로컬 로그는 완료): %s", exc)


__all__ = [
    "SUSPICION_PATTERNS",
    "SafetyConfig",
    "load_safety_config",
    "save_safety_config",
    "detect_malicious_round",
    "validate_shard_integrity",
    "validate_shard_content",
    "monitor_gpu_temperature",
    "enforce_resource_limits",
    "verify_master_identity",
    "compute_round_risk_score",
    "emergency_shutdown",
    "report_suspicious_master",
]
