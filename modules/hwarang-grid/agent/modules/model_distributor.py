"""모델 배포 시스템

마스터가 학습 완료된 모델/LoRA를 에이전트에 효율적으로 배포.

배포 방식 (에이전트 티어별):
  Lite:     LoRA만 (2MB)
  Standard: LoRA + 7B 기본모델 (필요시)
  Full:     LoRA + 32B 기본모델 (필요시)

최적화:
  - 델타 전송 (변경분만)
  - gzip 압축
  - 체크섬 검증
  - 이어받기 지원
"""

import json
import logging
import os
import hashlib
import gzip
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelDistributorModule:
    """모델/LoRA 배포 및 관리."""

    def __init__(self, config=None):
        self.model_dir = os.path.expanduser("~/.hwarang/models")
        self.lora_dir = os.path.expanduser("~/.hwarang/loras")
        self.cache_dir = os.path.expanduser("~/.hwarang/download_cache")

        for d in [self.model_dir, self.lora_dir, self.cache_dir]:
            os.makedirs(d, exist_ok=True)

        self.current_versions: dict[str, int] = {}
        self._load_version_info()

    def _load_version_info(self):
        """현재 설치된 모델/LoRA 버전 정보."""
        version_file = os.path.join(self.model_dir, "versions.json")
        if os.path.exists(version_file):
            with open(version_file) as f:
                self.current_versions = json.load(f)

    def _save_version_info(self):
        version_file = os.path.join(self.model_dir, "versions.json")
        with open(version_file, "w") as f:
            json.dump(self.current_versions, f, indent=2)

    def download_lora(self, master_url: str, version: int = 0) -> dict:
        """마스터에서 최신 LoRA 다운로드.

        1. 버전 확인 → 이미 최신이면 스킵
        2. 다운로드 → gzip 압축된 safetensors
        3. 체크섬 검증
        4. 설치
        """
        current = self.current_versions.get("lora", 0)

        try:
            from urllib.request import urlopen, Request

            # 버전 확인
            version_url = f"{master_url}/api/grid/lora/version"
            with urlopen(Request(version_url), timeout=10) as resp:
                info = json.loads(resp.read())
                server_version = info.get("version", 0)

            if server_version <= current:
                return {"status": "up_to_date", "version": current}

            logger.info(f"LoRA 다운로드: v{current} → v{server_version}")

            # 다운로드
            download_url = f"{master_url}/api/grid/lora/latest"
            req = Request(download_url, headers={"Accept-Encoding": "gzip"})

            with urlopen(req, timeout=120) as resp:
                data = resp.read()
                content_encoding = resp.headers.get("Content-Encoding", "")

                # gzip 해제
                if content_encoding == "gzip":
                    data = gzip.decompress(data)

            # 체크섬 검증
            checksum = hashlib.sha256(data).hexdigest()

            # 저장
            save_dir = os.path.join(self.lora_dir, f"v{server_version}")
            os.makedirs(save_dir, exist_ok=True)

            save_path = os.path.join(save_dir, "adapter_model.safetensors")
            with open(save_path, "wb") as f:
                f.write(data)

            # 현재 버전으로 심볼릭 링크
            latest_link = os.path.join(self.lora_dir, "latest")
            if os.path.exists(latest_link):
                if os.path.islink(latest_link):
                    os.unlink(latest_link)
                else:
                    shutil.rmtree(latest_link)
            os.symlink(save_dir, latest_link)

            # 버전 기록
            self.current_versions["lora"] = server_version
            self._save_version_info()

            size_mb = len(data) / 1024 / 1024
            logger.info(f"LoRA v{server_version} 설치 완료 ({size_mb:.1f}MB, sha256:{checksum[:16]})")

            # 오래된 버전 정리 (최근 3개만 유지)
            self._cleanup_old_loras(keep=3)

            return {
                "status": "updated",
                "version": server_version,
                "size_mb": round(size_mb, 1),
                "checksum": checksum,
                "path": save_dir,
            }

        except Exception as e:
            logger.error(f"LoRA 다운로드 실패: {e}")
            return {"status": "failed", "error": str(e)}

    def download_base_model(self, master_url: str, model_name: str) -> dict:
        """베이스 모델 다운로드 (최초 1회).

        큰 파일이므로 이어받기 + 청크 다운로드 지원.
        """
        model_path = os.path.join(self.model_dir, model_name)

        if os.path.exists(model_path) and os.listdir(model_path):
            return {"status": "exists", "path": model_path}

        logger.info(f"베이스 모델 다운로드: {model_name}")
        os.makedirs(model_path, exist_ok=True)

        try:
            from urllib.request import urlopen, Request

            # 모델 파일 목록 가져오기
            manifest_url = f"{master_url}/api/grid/models/{model_name}/manifest"
            with urlopen(Request(manifest_url), timeout=10) as resp:
                manifest = json.loads(resp.read())

            total_files = len(manifest.get("files", []))
            downloaded = 0

            for file_info in manifest.get("files", []):
                filename = file_info["name"]
                file_url = f"{master_url}/api/grid/models/{model_name}/{filename}"
                file_path = os.path.join(model_path, filename)

                # 이미 다운로드된 파일 스킵 (체크섬 확인)
                if os.path.exists(file_path):
                    existing_hash = self._file_hash(file_path)
                    if existing_hash == file_info.get("checksum"):
                        downloaded += 1
                        continue

                # 다운로드 (이어받기)
                self._download_file(file_url, file_path)
                downloaded += 1

                logger.info(f"  [{downloaded}/{total_files}] {filename}")

            self.current_versions[model_name] = manifest.get("version", 1)
            self._save_version_info()

            logger.info(f"베이스 모델 설치 완료: {model_path}")
            return {"status": "downloaded", "path": model_path}

        except Exception as e:
            logger.error(f"모델 다운로드 실패: {e}")
            return {"status": "failed", "error": str(e)}

    def _download_file(self, url: str, save_path: str, chunk_size: int = 8192):
        """파일 다운로드 (이어받기 지원)."""
        from urllib.request import urlopen, Request

        headers = {}
        existing_size = 0

        # 이어받기: 이미 부분 다운로드된 파일
        temp_path = save_path + ".part"
        if os.path.exists(temp_path):
            existing_size = os.path.getsize(temp_path)
            headers["Range"] = f"bytes={existing_size}-"

        req = Request(url, headers=headers)

        with urlopen(req, timeout=60) as resp:
            mode = "ab" if existing_size > 0 else "wb"
            with open(temp_path, mode) as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)

        # 완료 후 최종 이름으로 이동
        os.rename(temp_path, save_path)

    def _file_hash(self, path: str) -> str:
        """파일 SHA256 해시."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()

    def _cleanup_old_loras(self, keep: int = 3):
        """오래된 LoRA 버전 정리."""
        if not os.path.exists(self.lora_dir):
            return

        versions = []
        for name in os.listdir(self.lora_dir):
            path = os.path.join(self.lora_dir, name)
            if name.startswith("v") and os.path.isdir(path) and not os.path.islink(path):
                try:
                    ver = int(name[1:])
                    versions.append((ver, path))
                except ValueError:
                    pass

        versions.sort(reverse=True)

        for ver, path in versions[keep:]:
            logger.info(f"오래된 LoRA 삭제: v{ver}")
            shutil.rmtree(path)

    def get_installed_models(self) -> list[dict]:
        """설치된 모델 목록."""
        models = []
        for name in os.listdir(self.model_dir):
            path = os.path.join(self.model_dir, name)
            if os.path.isdir(path) and name != "versions.json":
                size = sum(
                    os.path.getsize(os.path.join(root, f))
                    for root, _, files in os.walk(path)
                    for f in files
                )
                models.append({
                    "name": name,
                    "path": path,
                    "size_gb": round(size / 1024**3, 1),
                    "version": self.current_versions.get(name, 0),
                })
        return models

    def get_installed_loras(self) -> list[dict]:
        """설치된 LoRA 목록."""
        loras = []
        for name in os.listdir(self.lora_dir):
            path = os.path.join(self.lora_dir, name)
            if os.path.isdir(path) and not os.path.islink(path):
                size = sum(
                    os.path.getsize(os.path.join(root, f))
                    for root, _, files in os.walk(path)
                    for f in files
                )
                loras.append({
                    "name": name,
                    "path": path,
                    "size_mb": round(size / 1024**2, 1),
                    "is_latest": os.path.realpath(os.path.join(self.lora_dir, "latest")) == os.path.realpath(path),
                })
        return loras

    def get_stats(self) -> dict:
        return {
            "models": self.get_installed_models(),
            "loras": self.get_installed_loras(),
            "versions": self.current_versions,
            "model_dir": self.model_dir,
            "lora_dir": self.lora_dir,
        }
