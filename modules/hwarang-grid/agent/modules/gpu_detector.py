"""GPU 감지 유틸리티 (멀티 벤더)

지원 GPU:
  - NVIDIA (CUDA) - RTX 3060/4090/5090 등
  - AMD (ROCm) - RX 7900 XTX, MI300X 등
  - Intel Arc (OneAPI) - A770 등
  - Apple Silicon (MPS) - M1/M2/M3/M4

사용법:
    from modules.gpu_detector import detect_gpu, get_gpu_metrics

    gpu = detect_gpu()
    print(gpu)
    # {'vendor': 'nvidia', 'name': 'RTX 5090', 'vram_gb': 32.0,
    #  'compute': 'cuda', 'driver': '570.86'}

    metrics = get_gpu_metrics()
    print(metrics)
    # {'usage_percent': 45.0, 'temp_c': 65, 'vram_used_gb': 12.3,
    #  'vram_total_gb': 32.0, 'power_w': 250}
"""

import logging
import os
import platform
import subprocess
import re

logger = logging.getLogger(__name__)


def detect_gpu() -> dict:
    """GPU 감지 (NVIDIA → AMD → Intel → Apple 순으로 시도).

    Returns:
        {
            "vendor": "nvidia" | "amd" | "intel" | "apple" | "none",
            "name": "RTX 5090",
            "vram_gb": 32.0,
            "compute": "cuda" | "rocm" | "oneapi" | "mps" | "cpu",
            "driver": "570.86",
            "device_count": 1,
        }
    """
    # 1. NVIDIA
    gpu = _detect_nvidia()
    if gpu:
        return gpu

    # 2. AMD
    gpu = _detect_amd()
    if gpu:
        return gpu

    # 3. Intel Arc
    gpu = _detect_intel()
    if gpu:
        return gpu

    # 4. Apple Silicon
    gpu = _detect_apple()
    if gpu:
        return gpu

    # 5. PyTorch로 재시도
    gpu = _detect_via_pytorch()
    if gpu:
        return gpu

    return {
        "vendor": "none",
        "name": "CPU only",
        "vram_gb": 0,
        "compute": "cpu",
        "driver": "",
        "device_count": 0,
    }


def get_gpu_metrics() -> dict:
    """현재 GPU 상태 (사용률, 온도, VRAM 등).

    Returns:
        {
            "usage_percent": 45.0,
            "temp_c": 65,
            "vram_used_gb": 12.3,
            "vram_total_gb": 32.0,
            "power_w": 250,
            "vendor": "nvidia",
        }
    """
    metrics = _metrics_nvidia()
    if metrics:
        return metrics

    metrics = _metrics_amd()
    if metrics:
        return metrics

    metrics = _metrics_apple()
    if metrics:
        return metrics

    metrics = _metrics_intel()
    if metrics:
        return metrics

    return {
        "usage_percent": 0,
        "temp_c": 0,
        "vram_used_gb": 0,
        "vram_total_gb": 0,
        "power_w": 0,
        "vendor": "none",
    }


def get_torch_device() -> str:
    """PyTorch용 디바이스 문자열.

    Returns: "cuda", "mps", "xpu", "cpu"
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu"
    except ImportError:
        pass
    return "cpu"


def is_gpu_available() -> bool:
    """GPU 사용 가능 여부."""
    return detect_gpu()["vendor"] != "none"


# ════════════════════════════════════════════════════════════════
# NVIDIA
# ════════════════════════════════════════════════════════════════

def _detect_nvidia():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version,count",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None

        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        name = parts[0] if len(parts) > 0 else "NVIDIA GPU"
        vram_mb = float(parts[1]) if len(parts) > 1 else 0
        driver = parts[2] if len(parts) > 2 else ""

        # 디바이스 수
        device_count = len(result.stdout.strip().split("\n"))

        return {
            "vendor": "nvidia",
            "name": name,
            "vram_gb": round(vram_mb / 1024, 1),
            "compute": "cuda",
            "driver": driver,
            "device_count": device_count,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _metrics_nvidia():
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None

        parts = [p.strip() for p in result.stdout.strip().split("\n")[0].split(",")]

        return {
            "usage_percent": float(parts[0]) if parts[0] != "[N/A]" else 0,
            "temp_c": int(float(parts[1])) if parts[1] != "[N/A]" else 0,
            "vram_used_gb": round(float(parts[2]) / 1024, 1) if parts[2] != "[N/A]" else 0,
            "vram_total_gb": round(float(parts[3]) / 1024, 1) if parts[3] != "[N/A]" else 0,
            "power_w": int(float(parts[4])) if len(parts) > 4 and parts[4] != "[N/A]" else 0,
            "vendor": "nvidia",
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# AMD
# ════════════════════════════════════════════════════════════════

def _detect_amd():
    # rocm-smi (Linux with ROCm)
    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--csv"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and "GPU" in result.stdout:
            name = "AMD GPU"
            vram_gb = 0

            # 이름 추출
            name_result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True, text=True, timeout=5,
            )
            if name_result.returncode == 0:
                for line in name_result.stdout.split("\n"):
                    if "Card" in line or "GPU" in line:
                        name_match = re.search(r':\s*(.+)', line)
                        if name_match:
                            name = name_match.group(1).strip()
                            break

            # VRAM 추출
            mem_result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram"],
                capture_output=True, text=True, timeout=5,
            )
            if mem_result.returncode == 0:
                total_match = re.search(r'Total.*?(\d+)', mem_result.stdout)
                if total_match:
                    vram_gb = round(int(total_match.group(1)) / 1024 / 1024, 1)

            return {
                "vendor": "amd",
                "name": name,
                "vram_gb": vram_gb,
                "compute": "rocm",
                "driver": "",
                "device_count": 1,
            }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Windows: AMD GPU via wmic/PowerShell
    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/format:csv"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if "AMD" in line or "Radeon" in line:
                        parts = [p.strip() for p in line.split(",")]
                        name = next((p for p in parts if "AMD" in p or "Radeon" in p), "AMD GPU")
                        ram = next((p for p in parts if p.isdigit()), "0")
                        vram_gb = round(int(ram) / 1024**3, 1) if ram.isdigit() else 0
                        return {
                            "vendor": "amd",
                            "name": name,
                            "vram_gb": vram_gb,
                            "compute": "rocm",
                            "driver": "",
                            "device_count": 1,
                        }
        except Exception:
            pass

    return None


def _metrics_amd():
    try:
        result = subprocess.run(
            ["rocm-smi", "--showuse", "--showtemp", "--showmemuse", "--csv"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None

        usage = 0
        temp = 0
        vram_used = 0
        vram_total = 0

        # GPU 사용률
        use_result = subprocess.run(["rocm-smi", "--showuse"], capture_output=True, text=True, timeout=5)
        usage_match = re.search(r'(\d+(?:\.\d+)?)%', use_result.stdout)
        if usage_match:
            usage = float(usage_match.group(1))

        # 온도
        temp_result = subprocess.run(["rocm-smi", "--showtemp"], capture_output=True, text=True, timeout=5)
        temp_match = re.search(r'(\d+(?:\.\d+)?)\s*c', temp_result.stdout, re.IGNORECASE)
        if temp_match:
            temp = int(float(temp_match.group(1)))

        return {
            "usage_percent": usage,
            "temp_c": temp,
            "vram_used_gb": vram_used,
            "vram_total_gb": vram_total,
            "power_w": 0,
            "vendor": "amd",
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# Intel Arc
# ════════════════════════════════════════════════════════════════

def _detect_intel():
    # xpu-smi (Linux with OneAPI)
    try:
        result = subprocess.run(
            ["xpu-smi", "discovery"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and "Device" in result.stdout:
            name = "Intel Arc GPU"
            vram_gb = 0

            name_match = re.search(r'Device Name\s*:\s*(.+)', result.stdout)
            if name_match:
                name = name_match.group(1).strip()

            mem_match = re.search(r'Memory Physical Size\s*:\s*(\d+(?:\.\d+)?)\s*(\w+)', result.stdout)
            if mem_match:
                size = float(mem_match.group(1))
                unit = mem_match.group(2).upper()
                if "GIB" in unit or "GB" in unit:
                    vram_gb = size
                elif "MIB" in unit or "MB" in unit:
                    vram_gb = round(size / 1024, 1)

            return {
                "vendor": "intel",
                "name": name,
                "vram_gb": vram_gb,
                "compute": "oneapi",
                "driver": "",
                "device_count": 1,
            }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # PyTorch XPU
    try:
        import torch
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            name = torch.xpu.get_device_name(0) if hasattr(torch.xpu, "get_device_name") else "Intel XPU"
            props = torch.xpu.get_device_properties(0) if hasattr(torch.xpu, "get_device_properties") else None
            vram_gb = round(props.total_memory / 1024**3, 1) if props and hasattr(props, "total_memory") else 0
            return {
                "vendor": "intel",
                "name": name,
                "vram_gb": vram_gb,
                "compute": "oneapi",
                "driver": "",
                "device_count": torch.xpu.device_count(),
            }
    except (ImportError, Exception):
        pass

    return None


def _metrics_intel():
    try:
        result = subprocess.run(
            ["xpu-smi", "stats", "-d", "0"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            usage = 0
            temp = 0
            usage_m = re.search(r'GPU Utilization.*?(\d+)', result.stdout)
            temp_m = re.search(r'GPU Temperature.*?(\d+)', result.stdout)
            if usage_m:
                usage = int(usage_m.group(1))
            if temp_m:
                temp = int(temp_m.group(1))
            return {
                "usage_percent": usage,
                "temp_c": temp,
                "vram_used_gb": 0,
                "vram_total_gb": 0,
                "power_w": 0,
                "vendor": "intel",
            }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# Apple Silicon (MPS)
# ════════════════════════════════════════════════════════════════

def _detect_apple():
    if platform.system() != "Darwin":
        return None

    try:
        # 칩 이름 확인
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=5,
        )
        cpu_name = result.stdout.strip()

        # Apple Silicon 확인
        arch_result = subprocess.run(["uname", "-m"], capture_output=True, text=True, timeout=5)
        is_arm = "arm64" in arch_result.stdout

        if not is_arm:
            return None

        # 칩 모델 확인 (M1/M2/M3/M4)
        chip_name = "Apple Silicon"
        if "M4" in cpu_name:
            chip_name = "Apple M4"
        elif "M3" in cpu_name:
            chip_name = "Apple M3"
        elif "M2" in cpu_name:
            chip_name = "Apple M2"
        elif "M1" in cpu_name:
            chip_name = "Apple M1"
        else:
            # system_profiler에서 칩 이름 확인
            sp_result = subprocess.run(
                ["system_profiler", "SPHardwareDataType"],
                capture_output=True, text=True, timeout=10,
            )
            chip_match = re.search(r'Chip:\s*(.+)', sp_result.stdout)
            if chip_match:
                chip_name = chip_match.group(1).strip()

        # 통합 메모리 (GPU와 공유)
        mem_result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=5,
        )
        total_mem_gb = round(int(mem_result.stdout.strip()) / 1024**3, 0)

        # GPU 코어 수
        gpu_cores = 0
        sp_result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True, text=True, timeout=10,
        )
        cores_match = re.search(r'Total Number of Cores:\s*(\d+)', sp_result.stdout)
        if cores_match:
            gpu_cores = int(cores_match.group(1))

        # MPS 사용 가능 확인
        compute = "cpu"
        try:
            import torch
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                compute = "mps"
        except ImportError:
            # torch 없어도 Apple Silicon이면 mps 가능
            compute = "mps"

        # Apple Silicon은 통합 메모리의 ~75%를 GPU로 사용 가능
        gpu_mem_gb = round(total_mem_gb * 0.75, 0)

        name = chip_name
        if gpu_cores > 0:
            name += f" ({gpu_cores}-core GPU)"

        return {
            "vendor": "apple",
            "name": name,
            "vram_gb": gpu_mem_gb,  # 통합 메모리의 75%
            "compute": compute,
            "driver": f"macOS {platform.mac_ver()[0]}",
            "device_count": 1,
            "total_memory_gb": total_mem_gb,
            "gpu_cores": gpu_cores,
        }

    except Exception:
        return None


def _metrics_apple():
    if platform.system() != "Darwin":
        return None

    try:
        # powermetrics (sudo 필요) 또는 ioreg
        # GPU 사용률은 Activity Monitor 수준으로만 가능

        # 메모리 압박 확인
        result = subprocess.run(
            ["vm_stat"],
            capture_output=True, text=True, timeout=5,
        )

        # 온도 (macOS는 직접 접근 어려움)
        temp = 0
        try:
            # sudo powermetrics --samplers smc -n 1
            # 권한 없으면 스킵
            temp_result = subprocess.run(
                ["sudo", "-n", "powermetrics", "--samplers", "smc", "-n", "1", "--sample-rate", "1000"],
                capture_output=True, text=True, timeout=5,
            )
            temp_match = re.search(r'GPU.*?(\d+(?:\.\d+)?)\s*C', temp_result.stdout)
            if temp_match:
                temp = int(float(temp_match.group(1)))
        except Exception:
            pass

        # 메모리 사용량
        mem_result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=5,
        )
        total_gb = round(int(mem_result.stdout.strip()) / 1024**3, 1)

        # 사용 중인 메모리 (ps 기반 추정)
        import psutil
        used_gb = round(psutil.virtual_memory().used / 1024**3, 1)

        return {
            "usage_percent": round(used_gb / total_gb * 100, 0) if total_gb > 0 else 0,
            "temp_c": temp,
            "vram_used_gb": used_gb,  # 통합 메모리
            "vram_total_gb": total_gb,
            "power_w": 0,
            "vendor": "apple",
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# PyTorch 폴백
# ════════════════════════════════════════════════════════════════

def _detect_via_pytorch():
    """PyTorch로 GPU 감지 (최후 수단)."""
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_mem / 1024**3
            vendor = "nvidia"
            if "AMD" in name or "Radeon" in name:
                vendor = "amd"
            return {
                "vendor": vendor,
                "name": name,
                "vram_gb": round(vram, 1),
                "compute": "cuda",
                "driver": "",
                "device_count": torch.cuda.device_count(),
            }

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return _detect_apple()

        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return _detect_intel()

    except ImportError:
        pass

    return None


# ════════════════════════════════════════════════════════════════
# 편의 함수
# ════════════════════════════════════════════════════════════════

def get_performance_score() -> float:
    """GPU 성능 점수 (RTX 3060 = 1.0 기준).

    에이전트 리워드 계산에 사용.
    """
    gpu = detect_gpu()
    name = gpu["name"].lower()
    vram = gpu["vram_gb"]

    # NVIDIA
    scores = {
        "3060": 1.0, "3070": 1.3, "3080": 1.6, "3090": 2.0,
        "4060": 1.2, "4070": 1.5, "4080": 2.0, "4090": 2.5,
        "5070": 2.0, "5080": 2.5, "5090": 3.5,
        "a100": 4.0, "h100": 6.0, "h200": 8.0,
    }
    for model, score in scores.items():
        if model in name:
            return score

    # AMD
    amd_scores = {
        "7900 xtx": 2.0, "7900 xt": 1.8, "7800 xt": 1.5,
        "mi300": 5.0, "mi250": 3.5, "mi210": 2.5,
        "w7900": 2.5, "w7800": 2.0,
    }
    for model, score in amd_scores.items():
        if model in name:
            return score

    # Apple Silicon
    apple_scores = {
        "m4 max": 2.0, "m4 pro": 1.5, "m4": 1.2,
        "m3 max": 1.8, "m3 pro": 1.3, "m3": 1.0,
        "m2 max": 1.5, "m2 pro": 1.1, "m2": 0.8,
        "m1 max": 1.2, "m1 pro": 0.9, "m1": 0.6,
    }
    for model, score in apple_scores.items():
        if model in name:
            return score

    # Intel Arc
    if "a770" in name:
        return 1.0
    if "a750" in name:
        return 0.8

    # VRAM 기반 추정
    if vram >= 48:
        return 3.0
    if vram >= 24:
        return 2.0
    if vram >= 16:
        return 1.5
    if vram >= 8:
        return 1.0
    if vram >= 4:
        return 0.5
    return 0.3


def print_gpu_info():
    """GPU 정보 출력 (CLI용)."""
    gpu = detect_gpu()
    metrics = get_gpu_metrics()
    score = get_performance_score()

    print(f"GPU: {gpu['name']}")
    print(f"  벤더:    {gpu['vendor']}")
    print(f"  VRAM:    {gpu['vram_gb']}GB")
    print(f"  컴퓨트:  {gpu['compute']}")
    print(f"  드라이버: {gpu['driver']}")
    print(f"  성능점수: {score:.1f}x (RTX 3060 = 1.0)")

    if metrics["vendor"] != "none":
        print(f"  사용률:  {metrics['usage_percent']}%")
        print(f"  온도:    {metrics['temp_c']}°C")
        print(f"  VRAM:    {metrics['vram_used_gb']}/{metrics['vram_total_gb']}GB")
        if metrics['power_w']:
            print(f"  전력:    {metrics['power_w']}W")


if __name__ == "__main__":
    print_gpu_info()
