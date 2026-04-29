"""hwarang-agent CLI — 에이전트 소유자를 위한 명령어 모음.

모든 명령은 내부적으로 agent/modules/ 의 해당 모듈 함수로 위임하며,
의존성이 없어도 도움말/상태 조회는 graceful 하게 동작한다.

예시:
    hwarang-agent init --preset law_specialist
    hwarang-agent link-account --email user@example.com
    hwarang-agent start --auto
    hwarang-agent pause --minutes 60
    hwarang-agent status
    hwarang-agent earnings --since 2025-01-01 --csv earnings.csv
    hwarang-agent profile show
    hwarang-agent presets list
    hwarang-agent safety set --max-vram 20
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("hwarang-agent-cli")

# ────────────────────────────────────────────────────────────────────────
# 경로/상수
# ────────────────────────────────────────────────────────────────────────

HOME_DIR = Path.home() / ".hwarang"
PROFILE_PATH = HOME_DIR / "agent_profile.yaml"
ACCOUNT_PATH = HOME_DIR / "account.json"
PAUSE_FLAG = HOME_DIR / "pause.flag"
SAFETY_PATH = HOME_DIR / "safety.json"
LOG_DIR = HOME_DIR / "logs"
PRESET_DIR = Path(__file__).parent / "config" / "presets"


# ────────────────────────────────────────────────────────────────────────
# Graceful imports
# ────────────────────────────────────────────────────────────────────────


def _load_yaml():
    try:
        import yaml  # type: ignore
        return yaml
    except ImportError:
        return None


def _load_httpx():
    try:
        import httpx  # type: ignore
        return httpx
    except ImportError:
        return None


def _load_gpu_detector():
    try:
        from modules import gpu_detector  # type: ignore
        return gpu_detector
    except Exception:
        try:
            from agent.modules import gpu_detector  # type: ignore
            return gpu_detector
        except Exception as exc:
            logger.debug("gpu_detector 로드 실패: %s", exc)
            return None


def _collect_device_info() -> dict[str, str]:
    """CLI 기기 식별 정보 수집. nvidia-smi/sysctl/rocm-smi 우선순위."""
    import platform
    import socket
    import subprocess
    import hashlib

    hostname = socket.gethostname()
    os_name = platform.system().lower()  # "linux" / "darwin" / "windows"
    arch = platform.machine().lower()    # "x86_64" / "arm64" / "aarch64"

    # GPU 감지: 1) gpu_detector 모듈 우선 시도
    gpu = "Unknown"
    gpu_mod = _load_gpu_detector()
    if gpu_mod is not None:
        try:
            info = gpu_mod.detect_gpu()
            if isinstance(info, dict):
                name = info.get("name") or ""
                vendor = info.get("vendor") or ""
                if name and name.lower() != "none":
                    gpu = name
                elif vendor and vendor.lower() != "none":
                    gpu = vendor
        except Exception as exc:
            logger.debug("gpu_detector.detect_gpu 실패: %s", exc)

    # 2) nvidia-smi
    if gpu == "Unknown":
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=3,
            )
            if out.returncode == 0 and out.stdout.strip():
                gpu = out.stdout.strip().splitlines()[0].strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception:
            pass

    # 3) macOS Apple Silicon
    if gpu == "Unknown" and os_name == "darwin":
        try:
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=3,
            )
            if out.returncode == 0:
                gpu = out.stdout.strip()
        except Exception:
            pass

    # 4) AMD rocm
    if gpu == "Unknown":
        try:
            out = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True, text=True, timeout=3,
            )
            if out.returncode == 0 and "GPU" in out.stdout:
                gpu = "AMD GPU"
        except Exception:
            pass

    fingerprint = hashlib.sha256(
        f"{hostname}|{os_name}|{arch}".encode()
    ).hexdigest()

    return {
        "deviceHostname": hostname,
        "deviceOs": os_name,
        "deviceArch": arch,
        "deviceGpu": gpu,
        "deviceFingerprint": fingerprint,
    }


def _load_domain_spec():
    try:
        from modules import domain_specialization as ds  # type: ignore
        return ds
    except Exception:
        try:
            # 설치 후 패키지 형태
            from agent.modules import domain_specialization as ds  # type: ignore
            return ds
        except Exception as exc:
            logger.debug("domain_specialization 임포트 실패: %s", exc)
            return None


def _load_earnings_tracker():
    try:
        from modules import earnings_tracker as et  # type: ignore
        return et
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────────────────────────────


def _read_json(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_json(p: Path, data: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_yaml_or_json(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {}
    yaml = _load_yaml()
    if p.suffix in (".yaml", ".yml") and yaml is not None:
        with p.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return _read_json(p)


def _load_account() -> dict[str, Any]:
    return _read_json(ACCOUNT_PATH)


def _save_account(data: dict[str, Any]) -> None:
    _write_json(ACCOUNT_PATH, data)


def _load_safety() -> dict[str, Any]:
    data = _read_json(SAFETY_PATH)
    if not data:
        data = {
            "max_vram_gb": 24,
            "max_duration_minutes": 120,
            "allow_cpu_fallback": False,
            "max_cpu_percent": 80,
        }
        _write_json(SAFETY_PATH, data)
    return data


# ────────────────────────────────────────────────────────────────────────
# 명령어 구현
# ────────────────────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    """프로필 초기화. --preset 지정 또는 대화형."""
    preset = args.preset or "general"

    # 1. 내장 프리셋 (domain_specialization.SUPPORTED_PRESETS)
    ds = _load_domain_spec()
    if ds is None:
        print("domain_specialization 모듈 로드 실패 — YAML 프리셋만 사용 가능", file=sys.stderr)
        return _init_from_yaml(preset)

    try:
        profile = ds.apply_preset(preset)
    except ValueError:
        # 2. YAML 프리셋 파일 폴백
        return _init_from_yaml(preset)

    # YAML 프리셋 파일 값으로 보강
    yaml_data = _read_yaml_or_json(PRESET_DIR / f"{preset}.yaml")
    if yaml_data:
        for key in (
            "primary_domains", "excluded_domains", "expertise_level",
            "languages", "min_data_quality_tier", "active_hours",
            "max_concurrent_rounds", "auto_participate",
        ):
            if key in yaml_data:
                setattr(profile, key, yaml_data[key])

    ds.save_profile(profile, path=str(PROFILE_PATH))
    print(f"[OK] 프로필 초기화 완료 (preset={preset})")
    print(f"  primary_domains : {profile.primary_domains}")
    print(f"  excluded_domains: {profile.excluded_domains}")
    print(f"  expertise_level : {profile.expertise_level}")
    print(f"  파일: {PROFILE_PATH}")
    return 0


def _init_from_yaml(preset: str) -> int:
    """YAML 프리셋 파일 기반으로 프로필 생성."""
    yaml_path = PRESET_DIR / f"{preset}.yaml"
    data = _read_yaml_or_json(yaml_path)
    if not data:
        print(f"[ERROR] 프리셋을 찾을 수 없음: {preset}", file=sys.stderr)
        return 2
    # 프로필로 저장 (JSON fallback)
    profile_data = {k: v for k, v in data.items() if k not in (
        "display_name", "description", "recommended_gpu", "notes",
        "required_credentials", "reward_expectations", "safety",
    )}
    profile_data.setdefault("preset", preset)
    _write_json(PROFILE_PATH.with_suffix(".json"), profile_data)
    # safety 설정도 별도로 저장
    if "safety" in data:
        _write_json(SAFETY_PATH, data["safety"])
    print(f"[OK] YAML 프리셋 적용: {preset}")
    return 0


def cmd_link_account(args: argparse.Namespace) -> int:
    """계정 연결 — email 로 소유자 식별."""
    email = args.email
    if not email or "@" not in email:
        print("[ERROR] 올바른 이메일 필요", file=sys.stderr)
        return 2
    acc = _load_account()
    acc["email"] = email
    acc["linked_at"] = datetime.utcnow().isoformat()
    _save_account(acc)
    print(f"[OK] 계정 연결: {email}")
    if args.credential:
        acc.setdefault("expert_credentials", []).append(args.credential)
        _save_account(acc)
        print(f"  전문가 자격 추가: {args.credential}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    """에이전트 시작 (agent_main 실행)."""
    if PAUSE_FLAG.exists():
        PAUSE_FLAG.unlink()
        print("[INFO] 이전 pause 해제")
    cmd = [sys.executable, str(Path(__file__).parent / "agent_main.py")]
    if args.preset:
        cmd += ["--preset", args.preset]
    if args.daemon:
        cmd.append("--daemon")
    print(f"[START] {' '.join(cmd)}")
    os.execvp(cmd[0], cmd)
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    """일시 중지. --minutes 지정 시 자동 해제 타이머."""
    minutes = args.minutes
    PAUSE_FLAG.parent.mkdir(parents=True, exist_ok=True)
    until = None
    if minutes > 0:
        until = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()
    payload = {"paused_at": datetime.utcnow().isoformat(), "until": until}
    with PAUSE_FLAG.open("w", encoding="utf-8") as f:
        json.dump(payload, f)
    print(f"[OK] 에이전트 일시중지 ({minutes or '무기한'}분)")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """일시 중지 해제."""
    if PAUSE_FLAG.exists():
        PAUSE_FLAG.unlink()
        print("[OK] 에이전트 재개")
    else:
        print("[INFO] pause 상태 아님")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """상태 출력: 프로필 + pause + 최근 수익."""
    print("═" * 60)
    print(" 화랑 Grid 에이전트 상태")
    print("═" * 60)

    # 프로필
    ds = _load_domain_spec()
    if ds is not None:
        try:
            profile = ds.load_profile(str(PROFILE_PATH))
            print(f"프리셋        : {profile.preset}")
            print(f"primary       : {profile.primary_domains}")
            print(f"excluded      : {profile.excluded_domains}")
            print(f"expertise     : {profile.expertise_level}")
            print(f"auto          : {profile.auto_participate}")
        except Exception as exc:
            print(f"[WARN] 프로필 로드 실패: {exc}")

    # 계정
    acc = _load_account()
    if acc:
        print(f"계정          : {acc.get('email', '(미연결)')}")
        if acc.get("expert_credentials"):
            print(f"자격          : {acc['expert_credentials']}")

    # pause
    if PAUSE_FLAG.exists():
        p = _read_json(PAUSE_FLAG)
        print(f"상태          : PAUSED (until={p.get('until', '무기한')})")
    else:
        print("상태          : RUNNING (또는 중지됨)")

    # safety
    safety = _load_safety()
    print(f"safety.vram   : {safety.get('max_vram_gb')} GB")
    print(f"safety.max_min: {safety.get('max_duration_minutes')}")

    print("═" * 60)
    return 0


def cmd_join(args: argparse.Namespace) -> int:
    """특정 라운드 수동 참여."""
    master = args.master or _get_master_url()
    agent_id, api_key = _get_agent_creds()
    httpx = _load_httpx()
    if httpx is None:
        print("[ERROR] httpx 미설치", file=sys.stderr)
        return 2
    url = f"{master}/api/grid/rounds/{args.round_id}/join"
    headers = {"X-Agent-Id": agent_id, "X-Agent-Key": api_key}
    try:
        resp = httpx.post(url, headers=headers, timeout=10)
        print(f"[{resp.status_code}] {resp.text}")
        return 0 if resp.status_code < 400 else 1
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


def cmd_decline(args: argparse.Namespace) -> int:
    """특정 라운드 거절."""
    master = args.master or _get_master_url()
    agent_id, api_key = _get_agent_creds()
    httpx = _load_httpx()
    if httpx is None:
        print("[ERROR] httpx 미설치", file=sys.stderr)
        return 2
    url = f"{master}/api/grid/rounds/{args.round_id}/decline"
    headers = {"X-Agent-Id": agent_id, "X-Agent-Key": api_key}
    try:
        resp = httpx.post(url, headers=headers, json={"reason": args.reason}, timeout=10)
        print(f"[{resp.status_code}] {resp.text}")
        return 0 if resp.status_code < 400 else 1
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


def cmd_earnings(args: argparse.Namespace) -> int:
    """수익 조회. --csv 지정 시 CSV 출력."""
    master = args.master or _get_master_url()
    agent_id, api_key = _get_agent_creds()
    since = args.since or ""
    httpx = _load_httpx()
    if httpx is None:
        print("[ERROR] httpx 미설치", file=sys.stderr)
        return 2

    params = {}
    if since:
        params["since"] = since
    url = f"{master}/api/grid/agents/{agent_id}/earnings"
    headers = {"X-Agent-Id": agent_id, "X-Agent-Key": api_key}

    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    total = data.get("total_hwr", 0)
    items = data.get("items", [])
    print(f"총 수익: {total:,} HWR (항목 {len(items)}건)")
    for it in items[-20:]:
        print(f"  {it.get('at', '')[:10]} | {it.get('reward', it.get('amount', 0)):>8} HWR"
              f" | {it.get('domain', it.get('source', ''))}")

    if args.csv:
        out_path = Path(args.csv)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["at", "amount", "domain", "round_id", "source"])
            for it in items:
                writer.writerow([
                    it.get("at", ""),
                    it.get("reward", it.get("amount", 0)),
                    it.get("domain", ""),
                    it.get("round_id", ""),
                    it.get("source", ""),
                ])
        print(f"[OK] CSV 저장: {out_path}")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    """profile show/edit/reset."""
    ds = _load_domain_spec()
    if args.subaction == "show":
        if ds is not None:
            try:
                prof = ds.load_profile(str(PROFILE_PATH))
                data = prof.__dict__
            except Exception:
                data = _read_yaml_or_json(PROFILE_PATH) or _read_json(
                    PROFILE_PATH.with_suffix(".json")
                )
        else:
            data = _read_yaml_or_json(PROFILE_PATH) or _read_json(
                PROFILE_PATH.with_suffix(".json")
            )
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.subaction == "edit":
        editor = os.environ.get("EDITOR", "vi")
        target = PROFILE_PATH if PROFILE_PATH.exists() else PROFILE_PATH.with_suffix(".json")
        if not target.exists():
            print(f"[ERROR] 프로필 없음. 먼저 'init' 실행", file=sys.stderr)
            return 2
        os.execvp(editor, [editor, str(target)])
        return 0

    if args.subaction == "reset":
        if PROFILE_PATH.exists():
            PROFILE_PATH.unlink()
        j = PROFILE_PATH.with_suffix(".json")
        if j.exists():
            j.unlink()
        print("[OK] 프로필 초기화")
        return 0

    print("[ERROR] show|edit|reset 중 하나 선택", file=sys.stderr)
    return 2


def cmd_presets(args: argparse.Namespace) -> int:
    """프리셋 목록."""
    ds = _load_domain_spec()

    rows: list[tuple[str, str]] = []
    if ds is not None:
        for p in ds.list_presets():
            rows.append((p["name"], p["description"]))

    # YAML 프리셋도 추가
    if PRESET_DIR.exists():
        for yp in sorted(PRESET_DIR.glob("*.yaml")):
            name = yp.stem
            if any(r[0] == name for r in rows):
                continue
            data = _read_yaml_or_json(yp)
            rows.append((name, data.get("description", "")))

    print("사용 가능한 프리셋:")
    for name, desc in rows:
        print(f"  {name:22s} — {desc}")
    return 0


def cmd_safety(args: argparse.Namespace) -> int:
    """safety show / set."""
    data = _load_safety()
    if args.subaction == "show":
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    if args.subaction == "set":
        if args.max_vram is not None:
            data["max_vram_gb"] = args.max_vram
        if args.max_duration is not None:
            data["max_duration_minutes"] = args.max_duration
        if args.allow_cpu is not None:
            data["allow_cpu_fallback"] = args.allow_cpu
        _write_json(SAFETY_PATH, data)
        print(f"[OK] safety 업데이트: {data}")
        return 0
    print("[ERROR] show|set 중 하나 선택", file=sys.stderr)
    return 2


def cmd_version(args: argparse.Namespace) -> int:
    print("hwarang-agent 1.0.0 (HWARANG Grid)")
    return 0


def cmd_crawl_only(args: argparse.Namespace) -> int:
    """크롤링 워커만 단독 실행 (학습/추론 없이).

    분산 크롤 워커를 foreground 로 띄워 마스터 큐에서 작업을 임대하고
    URL fetch → 결과 제출만 수행한다.

    환경변수:
      HWARANG_AGENT_KEY  — 에이전트 API 키
      HWARANG_AGENT_ID   — 에이전트 ID
      HWARANG_MASTER_URL — 마스터 URL
    """
    # 설정 로드
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from config.agent_config import AgentConfig  # type: ignore
    except Exception as exc:
        print(f"[ERROR] agent_config 로드 실패: {exc}", file=sys.stderr)
        return 2

    cfg = AgentConfig.load()
    agent_id, api_key = _get_agent_creds()
    if cfg.agent_id:
        agent_id = cfg.agent_id

    master_url = args.master or cfg.network.master_url

    try:
        from modules.crawler_agent import CrawlerAgent, CrawlerConfig  # type: ignore
    except Exception as exc:
        print(f"[ERROR] crawler_agent 임포트 실패: {exc}", file=sys.stderr)
        return 2

    crawl_cfg = cfg.modules.crawling
    domain_filter = list(getattr(crawl_cfg, "domain_filter", []) or []) or None
    if args.domain:
        domain_filter = [d.strip() for d in args.domain.split(",") if d.strip()]

    cc = CrawlerConfig(
        master_url=master_url,
        api_key=api_key,
        agent_id=agent_id,
        domain_filter=domain_filter,
        max_concurrent=args.concurrent or getattr(crawl_cfg, "max_concurrent", 3),
        poll_interval_seconds=getattr(crawl_cfg, "poll_interval_seconds", 30),
        request_timeout_sec=getattr(crawl_cfg, "request_timeout", 15),
        respect_robots=getattr(crawl_cfg, "respect_robots", True),
    )

    crawler = CrawlerAgent(cc)

    # SIGTERM/SIGINT → graceful stop
    def _sig_handler(_sig, _frame):
        crawler.stop()

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass

    print(
        f"[CRAWL] agent={agent_id} master={master_url} "
        f"concurrent={cc.max_concurrent} domain_filter={cc.domain_filter}"
    )
    try:
        asyncio.run(crawler.run())
    except KeyboardInterrupt:
        crawler.stop()
    return 0


# ────────────────────────────────────────────────────────────────────────
# daemon / stop
# ────────────────────────────────────────────────────────────────────────


def _load_pid_manager():
    try:
        from modules import pid_manager  # type: ignore
        return pid_manager
    except Exception:
        try:
            from agent.modules import pid_manager  # type: ignore
            return pid_manager
        except Exception as exc:
            logger.debug("pid_manager 로드 실패: %s", exc)
            return None


def _load_status_writer():
    try:
        from modules import status_writer  # type: ignore
        return status_writer
    except Exception:
        try:
            from agent.modules import status_writer  # type: ignore
            return status_writer
        except Exception as exc:
            logger.debug("status_writer 로드 실패: %s", exc)
            return None


def _attach_log_file() -> Path:
    """일자별 로그 파일 핸들러 추가."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"agent-{today}.log"

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s")
    )
    root = logging.getLogger()
    # 중복 핸들러 방지
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == str(log_path):
            return log_path
    root.addHandler(handler)
    return log_path


def cmd_daemon(args: argparse.Namespace) -> int:
    """백그라운드 데몬 모드 (Tauri 사이드카로부터 호출됨).

    동작:
      1. PID 파일 작성 (이미 실행 중이면 중단)
      2. 로그 파일 핸들러 추가
      3. agent_main.HwarangAgent 시작
      4. status_writer 백그라운드 태스크 시작 (30초 갱신)
      5. SIGTERM/SIGINT → graceful shutdown

    주의:
      - macOS/Linux 만 지원. 이 함수는 fork 하지 않고 foreground 로 실행되며
        Tauri 사이드카 또는 systemd/launchd 가 백그라운드화를 담당한다.
      - Windows 는 `pythonw.exe -m agent daemon` 또는 NSSM 서비스 래퍼로 처리.
        SIGTERM 미지원이므로 stop 은 taskkill /PID 로 강제 종료된다.
    """
    HOME_DIR.mkdir(parents=True, exist_ok=True)

    pid_mgr = _load_pid_manager()
    status_w = _load_status_writer()

    # 1. 기존 데몬 확인
    if pid_mgr is not None:
        if pid_mgr.cleanup_stale():
            logger.info("stale PID 정리 완료")
        if pid_mgr.is_running():
            print("[ERROR] 이미 실행 중인 에이전트 감지", file=sys.stderr)
            print(f"        중지하려면: hwarang-agent stop", file=sys.stderr)
            return 1
        pid_mgr.write_pid()

    # 2. 로그 파일
    log_path = _attach_log_file()
    logger.info("데몬 모드 시작 — 로그 파일: %s", log_path)

    # 3. agent_main 위임 — agent.start() 자체가 메인 루프
    exit_code = 0
    try:
        # graceful import
        try:
            import agent_main  # type: ignore
        except ImportError:
            sys.path.insert(0, str(Path(__file__).parent))
            import agent_main  # type: ignore

        # 설정 로드 (preset 옵션 지원)
        try:
            from config.agent_config import (  # type: ignore
                AgentConfig,
                preset_minimal,
                preset_full,
                preset_learning_focused,
                preset_night_only,
            )
        except Exception as exc:
            logger.error("agent_config 로드 실패: %s", exc)
            return 2

        if args.preset:
            presets_map = {
                "minimal": preset_minimal,
                "full": preset_full,
                "learning": preset_learning_focused,
                "night": preset_night_only,
            }
            cfg = presets_map.get(args.preset, AgentConfig.load)()
        else:
            cfg = AgentConfig.load()

        agent = agent_main.HwarangAgent(cfg)
        agent._daemon_mode = True  # agent_main 이 status_writer 스레드를 구동

        # 4. status_writer 는 agent_main 가 자체적으로 띄운다 (_daemon_mode=True 일 때)
        #    여기선 interval 만 환경변수로 전달
        os.environ.setdefault(
            "HWARANG_STATUS_INTERVAL", str(args.status_interval)
        )

        # 5. SIGTERM/SIGINT 핸들러
        def _signal_handler(sig, frame):
            logger.warning("시그널 %s 수신 → graceful shutdown", sig)
            try:
                if status_w is not None:
                    status_w.write_status_sync({"status": "stopped"})
            except Exception:
                pass
            try:
                agent.stop()
            finally:
                if pid_mgr is not None:
                    pid_mgr.remove_pid()
                sys.exit(0)

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        # 6. 메인 루프 (블로킹)
        agent.start()

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt → 종료")
    except Exception as exc:
        logger.exception("데몬 실행 실패: %s", exc)
        if status_w is not None:
            try:
                status_w.write_status_sync({"status": "error", "last_error": str(exc)})
            except Exception:
                pass
        exit_code = 1
    finally:
        if pid_mgr is not None:
            pid_mgr.remove_pid()

    return exit_code


def cmd_decide_test(args: argparse.Namespace) -> int:
    """가상 RoundOffer 로 인지(자율 결정) 모듈 테스트.

    예:
        hwarang-agent decide-test --domain legal --minutes 25 --hwr 120 --vram 12
        hwarang-agent decide-test --llm   # 로컬 LLM 사용
    """
    try:
        from modules.cognitive.decision_engine import (  # type: ignore
            decide_about_round,
            RoundOffer,
        )
    except Exception as exc:
        print(f"[ERROR] cognitive 모듈 로드 실패: {exc}", file=sys.stderr)
        return 2

    offer = RoundOffer(
        round_id="test_001",
        domain=args.domain or "code",
        estimated_minutes=int(args.minutes or 30),
        estimated_hwr=float(args.hwr or 100),
        min_vram_gb=float(args.vram or 8),
        sample_count=int(args.samples or 1000),
    )

    decision = asyncio.run(decide_about_round(offer, use_llm=bool(args.llm)))
    print(f"행동: {decision.action}")
    print(f"신뢰도: {decision.confidence:.2f}")
    print(f"이유: {decision.reasoning}")
    if decision.suggested_alternatives:
        print(f"대안: {', '.join(decision.suggested_alternatives)}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """실행 중인 데몬을 PID 파일로 종료."""
    pid_mgr = _load_pid_manager()
    if pid_mgr is None:
        print("[ERROR] pid_manager 모듈 로드 실패", file=sys.stderr)
        return 2
    ok = pid_mgr.stop_running_agent(timeout_sec=args.timeout)
    if ok:
        print("[OK] 에이전트 종료")
        return 0
    print("[ERROR] 에이전트 종료 실패", file=sys.stderr)
    return 1


# ────────────────────────────────────────────────────────────────────────
# 다중 기기 로그인 (cli-init / cli-poll)
# ────────────────────────────────────────────────────────────────────────


def cmd_login(args: argparse.Namespace) -> int:
    """헤드리스 기기에서 다중 기기 로그인.

    흐름:
        1. cli-init 호출 (device meta 전달)
        2. URL + QR 출력
        3. 자동으로 브라우저 열기 (--no-browser 면 skip)
        4. cli-poll 폴링 (3초 간격, 최대 10분)
        5. approved → ~/.hwarang/account.json 저장
    """
    httpx = _load_httpx()
    if httpx is None:
        print("[ERROR] httpx 미설치. pip install httpx", file=sys.stderr)
        return 2

    api_url = args.api_url or os.getenv("HWARANG_API_URL", "https://hwarang.ai")
    api_url = api_url.rstrip("/")

    # 1. 기존 로그인 확인
    existing = _load_account()
    if existing.get("api_key") and not args.force:
        print(f"[INFO] 이미 로그인 됨: {existing.get('email', '?')}")
        print("       다시 로그인하려면 --force 또는 hwarang-agent logout 후 시도")
        return 0

    # 2. device info 수집
    device = _collect_device_info()

    # 3. cli-init
    print(f"[1/3] {api_url}/api/auth/agent/cli-init 호출 중...")
    try:
        resp = httpx.post(
            f"{api_url}/api/auth/agent/cli-init",
            json=device,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[ERROR] cli-init 실패: {exc}", file=sys.stderr)
        return 1

    nonce = data["nonce"]
    login_url = data["login_url"]
    poll_url = data.get("poll_url") or f"{api_url}/api/auth/agent/cli-poll?nonce={nonce}"
    expires_in = data.get("expires_in", 600)
    interval = data.get("interval", 3)

    # 4. URL 출력
    print()
    print("=" * 60)
    print(" 화랑 그리드 - CLI 로그인")
    print("=" * 60)
    print(f"  기기명     : {device['deviceHostname']}")
    print(f"  OS / 아키텍처: {device['deviceOs']} / {device['deviceArch']}")
    print(f"  GPU       : {device['deviceGpu']}")
    print()
    print("  다음 URL 을 브라우저에서 열어 인증을 승인하세요:")
    print()
    print(f"    {login_url}")
    print()
    print(f"  ({expires_in // 60}분 안에 완료해주세요)")
    print("=" * 60)

    # 5. 자동 브라우저 열기
    if not args.no_browser:
        try:
            import webbrowser
            if webbrowser.open(login_url):
                print("\n[INFO] 브라우저가 열렸습니다.")
            else:
                print("\n[INFO] 브라우저 자동 열기 실패 — URL 을 수동으로 복사하세요.")
        except Exception:
            pass

    # 6. 폴링
    print("\n[2/3] 인증 대기 중", end="", flush=True)

    deadline = time.monotonic() + expires_in
    while time.monotonic() < deadline:
        time.sleep(interval)
        print(".", end="", flush=True)
        try:
            resp = httpx.get(poll_url, timeout=10)
        except Exception as exc:
            logger.debug("poll 실패 (재시도): %s", exc)
            continue

        if resp.status_code == 410:
            print()
            try:
                body = resp.json()
                status = body.get("status", "?")
            except Exception:
                status = "expired"
            print(f"[ERROR] 로그인 요청 만료/소비됨: {status}", file=sys.stderr)
            print("        다시 hwarang-agent login 을 실행하세요.", file=sys.stderr)
            return 1

        if resp.status_code != 200:
            continue

        try:
            body = resp.json()
        except Exception:
            continue
        status = body.get("status")

        if status == "pending":
            continue

        if status == "approved":
            print(" 완료!")
            # 7. account.json 저장
            account = {
                "email": body.get("email"),
                "user_id": body.get("user_id"),
                "api_key": body.get("api_key"),
                "device_id": body.get("device_id"),
                "device_name": body.get("device_name"),
                "device_fingerprint": device["deviceFingerprint"],
                "tier": body.get("tier", "BRONZE"),
                "kyc_verified": body.get("kyc_verified", False),
                "last_synced_at": datetime.utcnow().isoformat(),
                "master_url": api_url,
            }
            _save_account(account)
            print()
            print("[3/3] 로그인 완료")
            print(f"    email      : {account['email']}")
            print(f"    device     : {account['device_name']} ({account['device_id']})")
            print(f"    tier       : {account['tier']}")
            print(f"    KYC        : {'✓' if account['kyc_verified'] else '미인증'}")
            print(f"    저장 위치   : {ACCOUNT_PATH}")
            return 0

        # 알 수 없는 상태 → 그냥 계속 폴링
        continue

    print()
    print("[ERROR] 시간 초과 — 인증을 받지 못했습니다.", file=sys.stderr)
    return 1


def cmd_logout(args: argparse.Namespace) -> int:
    """현재 기기 로그아웃. --all-devices 면 모든 기기 폐기."""
    acc = _load_account()
    api_key = acc.get("api_key")
    device_id = acc.get("device_id")
    api_url = acc.get("master_url") or os.getenv("HWARANG_API_URL", "https://hwarang.ai")
    api_url = api_url.rstrip("/")

    httpx = _load_httpx()

    # 서버측 폐기 (실패해도 로컬은 삭제)
    if httpx is not None and api_key:
        try:
            if args.all_devices:
                # 전체 기기 목록 받아서 차례로 DELETE
                devices_resp = httpx.get(
                    f"{api_url}/api/auth/agent/devices",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10,
                )
                if devices_resp.status_code == 200:
                    body = devices_resp.json()
                    devices = body.get("devices", body) if isinstance(body, dict) else body
                    for d in devices:
                        try:
                            httpx.delete(
                                f"{api_url}/api/auth/agent/devices/{d.get('id') or d.get('device_id')}",
                                headers={"Authorization": f"Bearer {api_key}"},
                                timeout=10,
                            )
                        except Exception:
                            pass
                    print(f"[OK] {len(devices)}개 기기 폐기")
            elif device_id:
                resp = httpx.delete(
                    f"{api_url}/api/auth/agent/devices/{device_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10,
                )
                if resp.status_code < 400:
                    print(f"[OK] 서버측 기기 폐기: {device_id}")
                else:
                    print(f"[WARN] 서버 폐기 실패: HTTP {resp.status_code}")
        except Exception as exc:
            print(f"[WARN] 서버 폐기 실패 (로컬은 정리됨): {exc}")

    # 로컬 삭제
    if ACCOUNT_PATH.exists():
        ACCOUNT_PATH.unlink()
        print(f"[OK] 로컬 계정 삭제: {ACCOUNT_PATH}")
    else:
        print("[INFO] 로컬 계정 없음")
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    """등록된 기기 목록 조회 (서버에서)."""
    acc = _load_account()
    api_key = acc.get("api_key")
    if not api_key:
        print("[ERROR] 로그인 필요 (hwarang-agent login)", file=sys.stderr)
        return 2

    api_url = acc.get("master_url") or os.getenv("HWARANG_API_URL", "https://hwarang.ai")
    api_url = api_url.rstrip("/")

    httpx = _load_httpx()
    if httpx is None:
        print("[ERROR] httpx 미설치", file=sys.stderr)
        return 2

    try:
        resp = httpx.get(
            f"{api_url}/api/auth/agent/devices",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
        devices = body.get("devices", body) if isinstance(body, dict) else body
    except Exception as exc:
        print(f"[ERROR] 기기 목록 조회 실패: {exc}", file=sys.stderr)
        return 1

    if not devices:
        print("등록된 기기 없음")
        return 0

    print(f"등록된 기기 ({len(devices)}개):")
    print()
    for d in devices:
        marker = "★" if d.get("isCurrent") else " "
        active = "🟢" if d.get("isActive", True) else "○"
        name = d.get("deviceName") or d.get("device_name") or "(이름 없음)"
        os_str = d.get("deviceOs") or d.get("device_os") or "?"
        gpu = d.get("deviceGpu") or d.get("device_gpu") or "?"
        last = d.get("lastSeenAt") or d.get("lastUsedAt") or d.get("last_seen_at") or "-"
        print(f"  {marker} {active} {name:30s} | {os_str:8s} | {gpu:25s} | {last}")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    """현재 로그인 상태 + 사용자 정보 조회."""
    acc = _load_account()
    api_key = acc.get("api_key")

    if not api_key:
        print("[INFO] 로그인 안 됨")
        print("       hwarang-agent login 으로 시작하세요.")
        return 0

    api_url = acc.get("master_url") or os.getenv("HWARANG_API_URL", "https://hwarang.ai")
    api_url = api_url.rstrip("/")

    httpx = _load_httpx()
    if httpx is not None:
        try:
            resp = httpx.get(
                f"{api_url}/api/auth/whoami",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=8,
            )
            if resp.status_code == 200:
                body = resp.json()
                print(f"email      : {body.get('email')}")
                print(f"user_id    : {body.get('user_id')}")
                print(f"device_id  : {body.get('device_id')}")
                print(f"device_name: {body.get('device_name')}")
                print(f"tier       : {body.get('tier')}")
                print(f"KYC        : {'✓' if body.get('kyc_verified') else '미인증'}")
                print(f"권한       : {body.get('permissions')}")
                return 0
            elif resp.status_code == 401:
                print("[ERROR] 토큰 만료/무효 — hwarang-agent login 재시도", file=sys.stderr)
                return 1
        except Exception as exc:
            print(f"[WARN] 서버 조회 실패, 로컬 정보 표시: {exc}")

    # 로컬 fallback
    print("(로컬 캐시)")
    print(f"email      : {acc.get('email')}")
    print(f"device_id  : {acc.get('device_id')}")
    print(f"device_name: {acc.get('device_name')}")
    print(f"tier       : {acc.get('tier')}")
    print(f"KYC        : {'✓' if acc.get('kyc_verified') else '미인증'}")
    return 0


# ────────────────────────────────────────────────────────────────────────
# 내부 helper
# ────────────────────────────────────────────────────────────────────────


def _get_master_url() -> str:
    env = os.getenv("HWARANG_MASTER_URL")
    if env:
        return env.rstrip("/")
    acc = _load_account()
    return (acc.get("master_url") or "http://localhost:8000").rstrip("/")


def _get_agent_creds() -> tuple[str, str]:
    acc = _load_account()
    agent_id = acc.get("agent_id") or os.getenv("HWARANG_AGENT_ID", "anonymous")
    api_key = acc.get("api_key") or os.getenv("HWARANG_AGENT_KEY", "devkey")
    return agent_id, api_key


# ────────────────────────────────────────────────────────────────────────
# argparse
# ────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hwarang-agent",
        description="화랑 Grid 에이전트 CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p = sub.add_parser("init", help="프로필 초기화")
    p.add_argument(
        "--preset",
        default="general",
        help="general | law_specialist | medical_specialist | tax_specialist | night_only | legal_and_tax",
    )
    p.set_defaults(func=cmd_init)

    # link-account
    p = sub.add_parser("link-account", help="계정(email) 연결")
    p.add_argument("--email", required=True)
    p.add_argument("--credential", help="예: BAR_KR:12345")
    p.set_defaults(func=cmd_link_account)

    # start
    p = sub.add_parser("start", help="에이전트 시작")
    p.add_argument("--auto", action="store_true", help="자동 참여 모드")
    p.add_argument("--preset", help="agent_main --preset 값")
    p.add_argument("--daemon", action="store_true")
    p.set_defaults(func=cmd_start)

    # pause
    p = sub.add_parser("pause", help="일시중지")
    p.add_argument("--minutes", type=int, default=0, help="0=무기한")
    p.set_defaults(func=cmd_pause)

    # resume
    p = sub.add_parser("resume", help="재개")
    p.set_defaults(func=cmd_resume)

    # status
    p = sub.add_parser("status", help="상태 조회")
    p.set_defaults(func=cmd_status)

    # join / decline
    p = sub.add_parser("join", help="라운드 수동 참여")
    p.add_argument("--round-id", required=True, dest="round_id")
    p.add_argument("--master", help="master_url override")
    p.set_defaults(func=cmd_join)

    p = sub.add_parser("decline", help="라운드 거절")
    p.add_argument("--round-id", required=True, dest="round_id")
    p.add_argument("--reason", default="user_declined")
    p.add_argument("--master")
    p.set_defaults(func=cmd_decline)

    # earnings
    p = sub.add_parser("earnings", help="수익 조회")
    p.add_argument("--since", help="YYYY-MM-DD")
    p.add_argument("--csv", help="CSV 저장 경로")
    p.add_argument("--master")
    p.set_defaults(func=cmd_earnings)

    # profile
    p = sub.add_parser("profile", help="프로필 관리")
    p.add_argument("subaction", choices=["show", "edit", "reset"])
    p.set_defaults(func=cmd_profile)

    # presets
    p = sub.add_parser("presets", help="프리셋 관리")
    p.add_argument("subaction", nargs="?", choices=["list"], default="list")
    p.set_defaults(func=cmd_presets)

    # safety
    p = sub.add_parser("safety", help="안전 가드 설정")
    p.add_argument("subaction", choices=["show", "set"])
    p.add_argument("--max-vram", type=int, dest="max_vram")
    p.add_argument("--max-duration", type=int, dest="max_duration")
    p.add_argument("--allow-cpu", type=lambda v: v.lower() == "true", dest="allow_cpu")
    p.set_defaults(func=cmd_safety)

    # version
    p = sub.add_parser("version", help="버전 정보")
    p.set_defaults(func=cmd_version)

    # crawl-only (분산 크롤 워커만 단독 실행)
    p = sub.add_parser(
        "crawl-only",
        help="분산 크롤 워커만 단독 실행 (학습/추론 없음)",
    )
    p.add_argument("--master", help="master_url override")
    p.add_argument("--concurrent", type=int, default=0, help="동시 작업 수 (0=설정값 사용)")
    p.add_argument(
        "--domain",
        help="도메인 필터 (콤마 구분, 예: legal,medical). 미지정 시 설정값/전체",
    )
    p.set_defaults(func=cmd_crawl_only)

    # daemon (Tauri 사이드카에서 호출)
    p = sub.add_parser(
        "daemon",
        help="백그라운드 데몬 모드 (Tauri 사이드카 진입점)",
    )
    p.add_argument(
        "--preset",
        choices=["minimal", "full", "learning", "night"],
        help="시작 시 적용할 프리셋",
    )
    p.add_argument(
        "--status-interval",
        type=int,
        default=30,
        help="agent_status.json 갱신 주기 초 (기본 30)",
    )
    p.set_defaults(func=cmd_daemon)

    # decide-test (인지 결정 모듈 테스트)
    p = sub.add_parser(
        "decide-test",
        help="가상 RoundOffer 로 인지(자율 결정) 모듈 테스트",
    )
    p.add_argument("--domain", help="도메인 (예: legal, medical, code, general)")
    p.add_argument("--minutes", type=int, help="예상 학습 시간 (분)")
    p.add_argument("--hwr", type=float, help="예상 보상 (HWR)")
    p.add_argument("--vram", type=float, help="필요 VRAM (GB)")
    p.add_argument("--samples", type=int, help="샘플 수")
    p.add_argument("--llm", action="store_true", help="LLM 사용 (없으면 규칙 폴백)")
    p.set_defaults(func=cmd_decide_test)

    # stop (실행 중인 데몬 종료)
    p = sub.add_parser("stop", help="실행 중인 데몬 종료 (PID 파일 사용)")
    p.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="SIGTERM 후 SIGKILL 까지 대기 초 (기본 10)",
    )
    p.set_defaults(func=cmd_stop)

    # ─── 다중 기기 로그인 ───────────────────────────────────────────────
    # login
    p = sub.add_parser("login", help="다중 기기 로그인 (브라우저 인증)")
    p.add_argument("--no-browser", action="store_true", help="브라우저 자동 열기 비활성화")
    p.add_argument("--api-url", help="API 서버 URL override")
    p.add_argument("--force", action="store_true", help="이미 로그인 돼 있어도 재인증")
    p.set_defaults(func=cmd_login)

    # logout
    p = sub.add_parser("logout", help="현재 기기 로그아웃")
    p.add_argument("--all-devices", action="store_true", help="모든 기기 폐기")
    p.set_defaults(func=cmd_logout)

    # devices
    p = sub.add_parser("devices", help="등록된 기기 목록")
    p.set_defaults(func=cmd_devices)

    # whoami
    p = sub.add_parser("whoami", help="현재 사용자/기기 정보")
    p.set_defaults(func=cmd_whoami)

    return parser


# ────────────────────────────────────────────────────────────────────────
# 진입점
# ────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.getenv("HWARANG_LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        return int(result or 0)
    except KeyboardInterrupt:
        print("\n[중단]")
        return 130
    except Exception as exc:
        logger.exception("명령 실행 실패: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
