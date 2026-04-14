"""스토리지 설정 관리.

configs/storage.yaml을 읽어서 각 용도별 경로를 반환합니다.
디스크가 여러 개면 분산, 1개면 하나의 디렉토리에 모두 저장.

사용법:
    from hwarang_core.config.storage import get_storage

    storage = get_storage()
    print(storage.train_data)      # /mnt/nvme0/hwarang/train_data
    print(storage.checkpoints)     # /mnt/nvme0/hwarang/checkpoints
    print(storage.downloads)       # /mnt/nvme1/hwarang/downloads
    print(storage.models)          # /mnt/nvme2/hwarang/models

    # 또는 환경변수로 오버라이드
    # HWARANG_TRAIN_DATA_DIR=/fast/data python train.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class StorageConfig:
    """모든 스토리지 경로를 한 곳에서 관리."""

    # 디스크 1: 학습 (빠른 NVMe)
    train_data: Path = Path("./data/train_data")
    checkpoints: Path = Path("./checkpoints")
    tokenizer: Path = Path("./tokenizer_output")

    # 디스크 2: Raw 데이터 (대용량)
    downloads: Path = Path("./data/downloads")
    github_raw: Path = Path("./data/raw/github")
    blog_raw: Path = Path("./data/raw/blogs")
    aihub_raw: Path = Path("./data/raw/aihub")
    processed: Path = Path("./data/processed")
    sft_data: Path = Path("./data/sft")
    dpo_data: Path = Path("./data/dpo")

    # 디스크 3: 서빙 + 백업 (안정적)
    models: Path = Path("./exported")
    lora_adapters: Path = Path("./lora_adapters")
    vectordb: Path = Path("./vectordb")
    backup: Path = Path("./backup")

    def ensure_dirs(self) -> None:
        """모든 디렉토리 생성."""
        for field_name in self.__dataclass_fields__:
            path = getattr(self, field_name)
            path.mkdir(parents=True, exist_ok=True)

    def summary(self) -> str:
        """디스크 사용량 요약."""
        lines = ["Hwarang 스토리지 경로:"]
        lines.append("")
        lines.append("  [학습]")
        lines.append(f"    학습 데이터:    {self.train_data}")
        lines.append(f"    체크포인트:     {self.checkpoints}")
        lines.append(f"    토크나이저:     {self.tokenizer}")
        lines.append("")
        lines.append("  [데이터]")
        lines.append(f"    다운로드:       {self.downloads}")
        lines.append(f"    GitHub:        {self.github_raw}")
        lines.append(f"    블로그:         {self.blog_raw}")
        lines.append(f"    AI Hub:        {self.aihub_raw}")
        lines.append(f"    정제 데이터:    {self.processed}")
        lines.append(f"    SFT:           {self.sft_data}")
        lines.append(f"    DPO:           {self.dpo_data}")
        lines.append("")
        lines.append("  [서빙]")
        lines.append(f"    모델:          {self.models}")
        lines.append(f"    LoRA 어댑터:   {self.lora_adapters}")
        lines.append(f"    Vector DB:     {self.vectordb}")
        lines.append(f"    백업:          {self.backup}")

        # 실제 사용량
        lines.append("")
        lines.append("  [디스크 사용량]")
        seen_disks: dict[str, int] = {}
        for field_name in self.__dataclass_fields__:
            path = getattr(self, field_name)
            if path.exists():
                size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                # 디스크별 그룹화 (마운트 포인트 기준)
                mount = _get_mount_point(path)
                seen_disks[mount] = seen_disks.get(mount, 0) + size

        for mount, size in sorted(seen_disks.items()):
            size_gb = size / (1024 ** 3)
            lines.append(f"    {mount}: {size_gb:.1f} GB")

        return "\n".join(lines)


def _get_mount_point(path: Path) -> str:
    """파일 경로의 마운트 포인트 추출."""
    path = path.resolve()
    while not path.is_mount() and path != path.parent:
        path = path.parent
    return str(path)


def _load_yaml_config(config_path: Path) -> dict:
    """storage.yaml 파일 로드."""
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def get_storage(config_path: str | Path | None = None) -> StorageConfig:
    """스토리지 설정 로드.

    우선순위:
    1. 환경변수 (HWARANG_TRAIN_DATA_DIR 등)
    2. storage.yaml 파일
    3. 기본값 (현재 디렉토리 하위)

    Args:
        config_path: storage.yaml 경로. None이면 자동 탐색.
    """
    # 1. YAML 설정 로드
    if config_path is None:
        # 프로젝트 루트에서 configs/storage.yaml 탐색
        candidates = [
            Path("configs/storage.yaml"),
            Path("../../configs/storage.yaml"),  # modules/hwarang-core에서 실행 시
            Path.home() / ".hwarang" / "storage.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break

    yaml_config = {}
    if config_path and Path(config_path).exists():
        yaml_config = _load_yaml_config(Path(config_path))

    # 2. 단일 디스크 모드 체크
    single = yaml_config.get("single_disk", {})
    if single and single.get("base_dir"):
        base = Path(single["base_dir"])
        return StorageConfig(
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

    # 3. 멀티 디스크 모드 - YAML + 환경변수
    train = yaml_config.get("train", {})
    data = yaml_config.get("data", {})
    serve = yaml_config.get("serve", {})

    def resolve(env_var: str, yaml_val: str | None, default: str) -> Path:
        """환경변수 > YAML > 기본값 순서."""
        env = os.environ.get(env_var)
        if env:
            return Path(env)
        if yaml_val:
            return Path(yaml_val)
        return Path(default)

    return StorageConfig(
        # 디스크 1: 학습
        train_data=resolve("HWARANG_TRAIN_DATA_DIR",
                          train.get("data_dir"), "./data/train_data"),
        checkpoints=resolve("HWARANG_CHECKPOINT_DIR",
                           train.get("checkpoint_dir"), "./checkpoints"),
        tokenizer=resolve("HWARANG_TOKENIZER_DIR",
                         train.get("tokenizer_dir"), "./tokenizer_output"),

        # 디스크 2: Raw 데이터
        downloads=resolve("HWARANG_DOWNLOAD_DIR",
                         data.get("download_dir"), "./data/downloads"),
        github_raw=resolve("HWARANG_GITHUB_DIR",
                          data.get("github_dir"), "./data/raw/github"),
        blog_raw=resolve("HWARANG_BLOG_DIR",
                        data.get("blog_dir"), "./data/raw/blogs"),
        aihub_raw=resolve("HWARANG_AIHUB_DIR",
                         data.get("aihub_dir"), "./data/raw/aihub"),
        processed=resolve("HWARANG_PROCESSED_DIR",
                         data.get("processed_dir"), "./data/processed"),
        sft_data=resolve("HWARANG_SFT_DIR",
                        data.get("sft_dir"), "./data/sft"),
        dpo_data=resolve("HWARANG_DPO_DIR",
                        data.get("dpo_dir"), "./data/dpo"),

        # 디스크 3: 서빙
        models=resolve("HWARANG_MODEL_DIR",
                      serve.get("model_dir"), "./exported"),
        lora_adapters=resolve("HWARANG_LORA_DIR",
                             serve.get("lora_dir"), "./lora_adapters"),
        vectordb=resolve("HWARANG_VECTORDB_DIR",
                        serve.get("vectordb_dir"), "./vectordb"),
        backup=resolve("HWARANG_BACKUP_DIR",
                      serve.get("backup_dir"), "./backup"),
    )


def init_storage(config_path: str | None = None) -> StorageConfig:
    """스토리지 초기화: 설정 로드 + 모든 디렉토리 생성."""
    storage = get_storage(config_path)
    storage.ensure_dirs()
    return storage
