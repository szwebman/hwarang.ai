"""모듈 4: 시스템 모니터링 에이전트

GPU 온도/전력/VRAM/에러 실시간 리포트.
이상 감지 → 마스터에 알림 → 장애 예측.
"""

import time, json, logging, subprocess

logger = logging.getLogger(__name__)


class SystemMonitorModule:
    def __init__(self, config):
        self.config = config
        self.history = []

    def collect_metrics(self) -> dict:
        """현재 시스템 메트릭 수집."""
        metrics = {
            "timestamp": time.time(),
            "gpu": self._get_gpu_metrics(),
            "cpu": self._get_cpu_metrics(),
            "memory": self._get_memory_metrics(),
            "disk": self._get_disk_metrics(),
            "alerts": [],
        }

        # 알림 체크
        gpu = metrics["gpu"]
        if gpu.get("temperature", 0) > self.config.alert_gpu_temp:
            metrics["alerts"].append(f"GPU 온도 경고: {gpu['temperature']}°C")
        if gpu.get("utilization", 0) > self.config.alert_gpu_util * 100:
            metrics["alerts"].append(f"GPU 사용률 경고: {gpu['utilization']}%")
        if gpu.get("vram_used_pct", 0) > self.config.alert_vram_percent * 100:
            metrics["alerts"].append(f"VRAM 경고: {gpu['vram_used_pct']}%")

        self.history.append(metrics)
        if len(self.history) > 1000:
            self.history = self.history[-500:]

        return metrics

    def _get_gpu_metrics(self) -> dict:
        """GPU 메트릭 (NVIDIA/AMD/Intel/Apple Silicon 지원)."""
        try:
            from modules.gpu_detector import detect_gpu, get_gpu_metrics
            gpu_info = detect_gpu()
            metrics = get_gpu_metrics()

            vram_total = metrics.get("vram_total_gb", 0) * 1024
            vram_used = metrics.get("vram_used_gb", 0) * 1024

            return {
                "temperature": metrics.get("temp_c", 0),
                "utilization": metrics.get("usage_percent", 0),
                "vram_used_mb": vram_used,
                "vram_total_mb": vram_total,
                "vram_used_pct": round(vram_used / max(vram_total, 1) * 100, 1) if vram_total > 0 else 0,
                "power_watts": metrics.get("power_w", 0),
                "name": gpu_info.get("name", "unknown"),
                "vendor": gpu_info.get("vendor", "none"),
                "compute": gpu_info.get("compute", "cpu"),
            }
        except ImportError:
            pass

        # 폴백: nvidia-smi 직접 호출
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 6:
                vram_used = float(parts[2])
                vram_total = float(parts[3])
                return {
                    "temperature": int(parts[0]),
                    "utilization": float(parts[1]),
                    "vram_used_mb": vram_used,
                    "vram_total_mb": vram_total,
                    "vram_used_pct": round(vram_used / max(vram_total, 1) * 100, 1),
                    "power_watts": float(parts[4]),
                    "name": parts[5].strip(),
                    "vendor": "nvidia",
                }
        except Exception:
            pass

        return {"temperature": 0, "utilization": 0, "name": "unknown", "vendor": "none"}

    def _get_cpu_metrics(self) -> dict:
        try:
            import psutil
            return {"percent": psutil.cpu_percent(), "count": psutil.cpu_count()}
        except:
            return {"percent": 0, "count": 0}

    def _get_memory_metrics(self) -> dict:
        try:
            import psutil
            mem = psutil.virtual_memory()
            return {"total_gb": round(mem.total / 1e9, 1), "used_pct": mem.percent}
        except:
            return {"total_gb": 0, "used_pct": 0}

    def _get_disk_metrics(self) -> dict:
        try:
            import psutil
            disk = psutil.disk_usage("/")
            return {"total_gb": round(disk.total / 1e9, 1), "used_pct": round(disk.percent, 1)}
        except:
            return {"total_gb": 0, "used_pct": 0}
