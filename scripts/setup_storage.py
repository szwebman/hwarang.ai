#!/usr/bin/env python3
"""
디스크 초기화 스크립트.

워크스테이션 조립 후 첫 실행 시:
1. 디스크 마운트 확인
2. 디렉토리 구조 생성
3. 심볼릭 링크 설정
4. 권한 확인

사용법:
    # 현재 storage.yaml 설정대로 초기화
    python scripts/setup_storage.py

    # 설정 확인만 (생성 안 함)
    python scripts/setup_storage.py --dry-run

    # 단일 디스크 모드
    python scripts/setup_storage.py --single ./data
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def check_disk_mounts() -> dict[str, dict]:
    """마운트된 디스크 확인."""
    disks = {}
    try:
        result = subprocess.run(
            ["df", "-h", "--type=ext4", "--type=xfs", "--type=btrfs", "--type=nvme"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            # macOS or different format
            result = subprocess.run(["df", "-h"], capture_output=True, text=True)

        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 6:
                mount = parts[-1]
                size = parts[1]
                used = parts[2]
                avail = parts[3]
                use_pct = parts[4]
                disks[mount] = {
                    "size": size,
                    "used": used,
                    "available": avail,
                    "use_percent": use_pct,
                }
    except Exception as e:
        logger.warning(f"디스크 확인 실패: {e}")

    return disks


def setup_multi_disk(config_path: str | None = None, dry_run: bool = False):
    """멀티 디스크 설정."""
    # 프로젝트 루트 찾기
    project_root = Path(__file__).parent.parent.resolve()

    # 스토리지 모듈 임포트
    import sys
    sys.path.insert(0, str(project_root / "modules" / "hwarang-core" / "src"))
    from hwarang_core.config.storage import get_storage, StorageConfig

    storage = get_storage(config_path)

    logger.info("=" * 60)
    logger.info("Hwarang 스토리지 초기화")
    logger.info("=" * 60)

    # 디스크 마운트 상태
    logger.info("")
    logger.info("[마운트된 디스크]")
    disks = check_disk_mounts()
    for mount, info in disks.items():
        logger.info(f"  {mount}: {info['size']} (사용: {info['use_percent']}, 남음: {info['available']})")

    # 경로 확인
    logger.info("")
    logger.info(storage.summary())

    if dry_run:
        logger.info("")
        logger.info("(--dry-run: 디렉토리 생성 안 함)")
        return

    # 디렉토리 생성
    logger.info("")
    logger.info("[디렉토리 생성]")
    for field_name in storage.__dataclass_fields__:
        path = getattr(storage, field_name)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            logger.info(f"  ✅ 생성: {path}")
        else:
            logger.info(f"  ⏭️  존재: {path}")

    # 프로젝트 루트에 심볼릭 링크 생성 (편의용)
    logger.info("")
    logger.info("[심볼릭 링크 생성]")
    symlinks = {
        "data": storage.downloads.parent,
        "checkpoints": storage.checkpoints,
        "exported": storage.models,
        "tokenizer_output": storage.tokenizer,
    }
    for link_name, target in symlinks.items():
        link_path = project_root / link_name
        if link_path.is_symlink():
            link_path.unlink()
        if not link_path.exists():
            try:
                link_path.symlink_to(target)
                logger.info(f"  ✅ {link_name} → {target}")
            except OSError as e:
                logger.warning(f"  ⚠️  링크 실패 ({link_name}): {e}")
        else:
            logger.info(f"  ⏭️  존재: {link_name}")

    # 권한 확인
    logger.info("")
    logger.info("[쓰기 권한 확인]")
    for field_name in storage.__dataclass_fields__:
        path = getattr(storage, field_name)
        if path.exists():
            writable = os.access(path, os.W_OK)
            status = "✅" if writable else "❌ 쓰기 불가!"
            logger.info(f"  {status} {path}")

    logger.info("")
    logger.info("=" * 60)
    logger.info("초기화 완료!")
    logger.info("")
    logger.info("다음 단계:")
    logger.info("  1. configs/storage.yaml 경로 확인/수정")
    logger.info("  2. make download-data  (데이터 다운로드)")
    logger.info("  3. make train-tokenizer (토크나이저 학습)")
    logger.info("=" * 60)


def setup_single_disk(base_dir: str, dry_run: bool = False):
    """단일 디스크 설정."""
    import sys
    project_root = Path(__file__).parent.parent.resolve()
    sys.path.insert(0, str(project_root / "modules" / "hwarang-core" / "src"))
    from hwarang_core.config.storage import StorageConfig

    base = Path(base_dir)
    storage = StorageConfig(
        train_data=base / "train_data",
        checkpoints=base / "checkpoints",
        tokenizer=base / "tokenizer",
        downloads=base / "downloads",
        github_raw=base / "raw" / "github",
        blog_raw=base / "raw" / "blogs",
        aihub_raw=base / "raw" / "aihub",
        processed=base / "processed",
        sft_data=base / "sft",
        dpo_data=base / "dpo",
        models=base / "models",
        lora_adapters=base / "lora_adapters",
        vectordb=base / "vectordb",
        backup=base / "backup",
    )

    logger.info("단일 디스크 모드")
    logger.info(f"기본 디렉토리: {base}")
    logger.info("")
    logger.info(storage.summary())

    if not dry_run:
        storage.ensure_dirs()
        logger.info("")
        logger.info("모든 디렉토리 생성 완료!")


def main():
    parser = argparse.ArgumentParser(description="Hwarang 스토리지 초기화")
    parser.add_argument("--config", default=None, help="storage.yaml 경로")
    parser.add_argument("--single", default=None, help="단일 디스크 기본 경로")
    parser.add_argument("--dry-run", action="store_true", help="확인만 (생성 안 함)")
    args = parser.parse_args()

    if args.single:
        setup_single_disk(args.single, args.dry_run)
    else:
        setup_multi_disk(args.config, args.dry_run)


if __name__ == "__main__":
    main()
