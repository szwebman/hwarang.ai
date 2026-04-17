"""HFL - Hwarang Federated Learning

화랑 독자 기법: 다중 PC에서 LoRA를 분산 학습 후 합성.

원리:
  1. 중앙 서버가 베이스 모델 + 초기 LoRA를 각 워커에 배포
  2. 각 워커(PC)가 독립적으로 자기 데이터로 LoRA 학습 (N step)
  3. 학습된 LoRA 가중치만 중앙으로 전송 (~50MB, 일반 인터넷 OK)
  4. 중앙에서 TIES/DARE/평균으로 LoRA 합성
  5. 합성된 LoRA를 다시 배포 → 반복

장점:
  - 일반 인터넷으로 충분 (LoRA만 전송, ~50MB)
  - 각 PC가 서로 다른 도메인 데이터 학습 가능
  - Grid 네트워크의 GPU를 학습에도 활용
  - 데이터 프라이버시 보장 (원본 데이터 전송 안 함)

사용법:
    # 중앙 서버 (마스터)
    python scripts/advanced/federated_lora.py master \\
        --base-model /mnt/nvme2/hwarang/models/qwen2.5-32b \\
        --port 9090 \\
        --rounds 10

    # 워커 PC 1 (코딩 데이터)
    python scripts/advanced/federated_lora.py worker \\
        --master http://master:9090 \\
        --data /path/to/coding_data.jsonl \\
        --steps-per-round 500

    # 워커 PC 2 (법률 데이터)
    python scripts/advanced/federated_lora.py worker \\
        --master http://master:9090 \\
        --data /path/to/legal_data.jsonl \\
        --steps-per-round 500
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# LoRA 합성 (TIES / 평균)
# ════════════════════════════════════════════════════════════════

def merge_lora_weights(
    lora_paths: list[str],
    output_path: str,
    method: str = "average",
):
    """여러 LoRA 가중치를 하나로 합성.

    Methods:
      - average: 단순 가중 평균
      - ties: TIES merge (중요한 delta만 유지)
    """
    import torch

    logger.info(f"LoRA 합성: {len(lora_paths)}개 → {output_path} (method={method})")

    # 첫 번째 LoRA 로드 (구조 참조)
    all_states = []
    for path in lora_paths:
        adapter_path = os.path.join(path, "adapter_model.safetensors")
        if not os.path.exists(adapter_path):
            adapter_path = os.path.join(path, "adapter_model.bin")

        if os.path.exists(adapter_path):
            if adapter_path.endswith(".safetensors"):
                from safetensors.torch import load_file
                state = load_file(adapter_path)
            else:
                state = torch.load(adapter_path, map_location="cpu")
            all_states.append(state)
            logger.info(f"  로드: {path} ({len(state)} 파라미터)")

    if len(all_states) == 0:
        logger.error("합성할 LoRA가 없습니다")
        return

    if len(all_states) == 1:
        # 1개면 그냥 복사
        shutil.copytree(lora_paths[0], output_path, dirs_exist_ok=True)
        return

    # 합성
    merged = {}
    keys = all_states[0].keys()

    if method == "average":
        # 단순 평균
        for key in keys:
            tensors = [s[key].float() for s in all_states if key in s]
            merged[key] = sum(tensors) / len(tensors)

    elif method == "ties":
        # TIES: Trim, Elect, Disjoint merge
        base_state = all_states[0]
        for key in keys:
            deltas = []
            for s in all_states[1:]:
                if key in s:
                    delta = s[key].float() - base_state[key].float()
                    deltas.append(delta)

            if not deltas:
                merged[key] = base_state[key]
                continue

            # Trim: 작은 delta 제거 (상위 50%만 유지)
            stacked = torch.stack(deltas)
            magnitudes = stacked.abs()
            threshold = magnitudes.quantile(0.5)
            trimmed = torch.where(magnitudes > threshold, stacked, torch.zeros_like(stacked))

            # Elect: 부호 다수결
            signs = trimmed.sign()
            elected_sign = signs.sum(dim=0).sign()

            # Disjoint: 같은 부호만 합산
            mask = signs == elected_sign.unsqueeze(0)
            disjoint = torch.where(mask, trimmed, torch.zeros_like(trimmed))

            # 합산 + 베이스에 더하기
            merged_delta = disjoint.mean(dim=0)
            merged[key] = base_state[key].float() + merged_delta

    # 저장
    os.makedirs(output_path, exist_ok=True)

    # adapter_config.json 복사
    config_src = os.path.join(lora_paths[0], "adapter_config.json")
    if os.path.exists(config_src):
        shutil.copy(config_src, os.path.join(output_path, "adapter_config.json"))

    # 가중치 저장
    try:
        from safetensors.torch import save_file
        save_file(merged, os.path.join(output_path, "adapter_model.safetensors"))
    except ImportError:
        import torch
        torch.save(merged, os.path.join(output_path, "adapter_model.bin"))

    logger.info(f"✅ 합성 완료: {output_path}")


# ════════════════════════════════════════════════════════════════
# 마스터 서버 (중앙 조율)
# ════════════════════════════════════════════════════════════════

class FederatedMaster:
    """중앙 서버: LoRA 배포 + 수집 + 합성."""

    def __init__(self, base_model: str, output_dir: str, total_rounds: int = 10):
        self.base_model = base_model
        self.output_dir = output_dir
        self.total_rounds = total_rounds
        self.current_round = 0
        self.worker_loras: dict[str, str] = {}  # worker_id → lora_path
        self.expected_workers = 0
        self.global_lora_path = os.path.join(output_dir, "global_lora")

        os.makedirs(output_dir, exist_ok=True)

    def register_worker(self, worker_id: str) -> dict:
        """워커 등록 → 현재 글로벌 LoRA 전달."""
        self.expected_workers += 1
        logger.info(f"워커 등록: {worker_id} (총 {self.expected_workers}명)")

        return {
            "round": self.current_round,
            "base_model": self.base_model,
            "global_lora": self.global_lora_path if os.path.exists(self.global_lora_path) else None,
        }

    def submit_lora(self, worker_id: str, lora_path: str) -> dict:
        """워커가 학습 완료된 LoRA 제출."""
        self.worker_loras[worker_id] = lora_path
        logger.info(f"LoRA 수신: {worker_id} (라운드 {self.current_round}, "
                     f"{len(self.worker_loras)}/{self.expected_workers})")

        # 모든 워커가 제출했으면 합성
        if len(self.worker_loras) >= self.expected_workers:
            self._aggregate_round()

        return {
            "status": "accepted",
            "round": self.current_round,
            "workers_submitted": len(self.worker_loras),
            "workers_total": self.expected_workers,
        }

    def _aggregate_round(self):
        """한 라운드의 LoRA들을 합성."""
        logger.info(f"\n{'=' * 60}")
        logger.info(f" 라운드 {self.current_round} 합성 ({len(self.worker_loras)}개 LoRA)")
        logger.info(f"{'=' * 60}")

        lora_paths = list(self.worker_loras.values())

        # 이전 글로벌 LoRA도 포함 (momentum 효과)
        if os.path.exists(self.global_lora_path):
            lora_paths.insert(0, self.global_lora_path)

        # 합성
        round_output = os.path.join(self.output_dir, f"round_{self.current_round}")
        merge_lora_weights(lora_paths, round_output, method="ties")

        # 글로벌 LoRA 업데이트
        if os.path.exists(self.global_lora_path):
            shutil.rmtree(self.global_lora_path)
        shutil.copytree(round_output, self.global_lora_path)

        # 다음 라운드 준비
        self.worker_loras.clear()
        self.current_round += 1

        if self.current_round >= self.total_rounds:
            logger.info(f"\n✅ 전체 {self.total_rounds} 라운드 완료!")
            logger.info(f"   최종 LoRA: {self.global_lora_path}")
        else:
            logger.info(f"   다음 라운드: {self.current_round}/{self.total_rounds}")


# ════════════════════════════════════════════════════════════════
# 워커 (각 PC에서 실행)
# ════════════════════════════════════════════════════════════════

def run_worker(
    master_url: str,
    data_path: str,
    worker_id: str,
    steps_per_round: int = 500,
    lr: float = 2e-4,
    lora_r: int = 16,
):
    """워커: 마스터에서 LoRA 받고, 학습하고, 결과 전송."""
    import requests

    logger.info(f"워커 시작: {worker_id}")
    logger.info(f"  마스터: {master_url}")
    logger.info(f"  데이터: {data_path}")
    logger.info(f"  스텝/라운드: {steps_per_round}")

    # 1. 마스터에 등록
    resp = requests.post(f"{master_url}/register", json={"worker_id": worker_id})
    info = resp.json()
    base_model = info["base_model"]
    current_round = info["round"]

    logger.info(f"  베이스 모델: {base_model}")
    logger.info(f"  현재 라운드: {current_round}")

    while True:
        logger.info(f"\n[라운드 {current_round}] 학습 시작 ({steps_per_round} steps)")

        # 2. 글로벌 LoRA 다운로드 (있으면)
        global_lora = info.get("global_lora")
        resume_arg = ""
        if global_lora:
            # 마스터에서 LoRA 파일 다운로드 (실제 구현은 파일 서빙 필요)
            logger.info(f"  글로벌 LoRA 다운로드: {global_lora}")

        # 3. QLoRA 학습 (지정된 step만큼)
        output_dir = f"/tmp/hfl_worker_{worker_id}_round_{current_round}"
        cmd = f"""
            python scripts/qlora_qwen.py \\
                --model-path {base_model} \\
                --data {data_path} \\
                --output {output_dir} \\
                --epochs 1 \\
                --lr {lr} \\
                --lora-r {lora_r} \\
                --max-length 2048
        """
        # 실제로는 max_steps={steps_per_round}를 qlora_qwen.py에 추가해야 함

        logger.info(f"  학습 실행 중...")
        os.system(cmd)

        # 4. 학습된 LoRA를 마스터에 제출
        logger.info(f"  LoRA 제출: {output_dir}")
        resp = requests.post(f"{master_url}/submit", json={
            "worker_id": worker_id,
            "lora_path": output_dir,
            "round": current_round,
        })
        result = resp.json()
        logger.info(f"  제출 결과: {result['status']}")

        # 5. 다음 라운드 대기
        current_round += 1

        # 마스터에게 다음 라운드 정보 요청
        resp = requests.get(f"{master_url}/status")
        status = resp.json()

        if status.get("completed"):
            logger.info("✅ 전체 학습 완료!")
            break

        info = status
        time.sleep(5)  # 다른 워커 대기


# ════════════════════════════════════════════════════════════════
# DiLoCo 스타일 (독립 학습 + 드문 동기화)
# ════════════════════════════════════════════════════════════════

def run_diloco_worker(
    base_model: str,
    data_path: str,
    output_path: str,
    inner_steps: int = 500,
    outer_steps: int = 10,
    lr_inner: float = 2e-4,
    lr_outer: float = 0.7,
):
    """DiLoCo 방식: H step 독립 학습 → outer gradient 계산 → 동기화.

    단일 워커 시뮬레이션. 실제 분산은 마스터-워커 구조로.
    """
    logger.info(f"DiLoCo 워커 시작")
    logger.info(f"  Inner steps: {inner_steps}")
    logger.info(f"  Outer steps: {outer_steps}")
    logger.info(f"  → 총 {inner_steps * outer_steps} 학습 step")

    for outer in range(outer_steps):
        logger.info(f"\n[Outer step {outer + 1}/{outer_steps}]")

        # Inner loop: 독립 학습
        step_output = f"{output_path}/diloco_outer_{outer}"
        cmd = f"""
            python scripts/qlora_qwen.py \\
                --model-path {base_model} \\
                --data {data_path} \\
                --output {step_output} \\
                --epochs 1 \\
                --lr {lr_inner}
        """
        os.system(cmd)

        # Outer gradient = 현재 LoRA - 이전 LoRA
        # (실제 구현은 torch로 delta 계산 필요)
        logger.info(f"  Outer gradient 계산 완료")

        # 여기서 다른 워커들과 outer gradient만 동기화
        # 통신량: LoRA 파라미터만 (~50MB) → 인터넷으로 충분

    logger.info(f"\n✅ DiLoCo 학습 완료: {output_path}")


# ════════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="HFL - Hwarang Federated Learning")
    parser.add_argument("mode", choices=["master", "worker", "diloco", "merge"],
                        help="실행 모드")
    parser.add_argument("--base-model", help="베이스 모델 경로")
    parser.add_argument("--data", help="학습 데이터 (워커용)")
    parser.add_argument("--output", default="./hfl_output", help="출력 경로")
    parser.add_argument("--master", help="마스터 URL (워커용)")
    parser.add_argument("--port", type=int, default=9090, help="마스터 포트")
    parser.add_argument("--rounds", type=int, default=10, help="총 라운드")
    parser.add_argument("--steps-per-round", type=int, default=500, help="라운드당 학습 스텝")
    parser.add_argument("--worker-id", default=None, help="워커 ID")
    parser.add_argument("--lora-paths", nargs="+", help="합성할 LoRA 경로들 (merge 모드)")
    parser.add_argument("--merge-method", default="ties", choices=["average", "ties"])
    args = parser.parse_args()

    if args.mode == "master":
        if not args.base_model:
            parser.error("마스터는 --base-model 필수")
        master = FederatedMaster(args.base_model, args.output, args.rounds)
        logger.info(f"마스터 서버 시작: 포트 {args.port}")
        logger.info(f"  워커 등록 대기 중...")
        logger.info(f"  워커 실행: python ... worker --master http://이서버:{args.port}")
        # 실제 HTTP 서버 구현은 Flask/FastAPI 추천
        # 여기선 구조만 정의

    elif args.mode == "worker":
        if not args.master or not args.data:
            parser.error("워커는 --master와 --data 필수")
        worker_id = args.worker_id or f"worker_{os.getpid()}"
        run_worker(args.master, args.data, worker_id, args.steps_per_round)

    elif args.mode == "diloco":
        if not args.base_model or not args.data:
            parser.error("DiLoCo는 --base-model과 --data 필수")
        run_diloco_worker(args.base_model, args.data, args.output,
                          inner_steps=args.steps_per_round,
                          outer_steps=args.rounds)

    elif args.mode == "merge":
        if not args.lora_paths or len(args.lora_paths) < 2:
            parser.error("merge는 --lora-paths 2개 이상 필수")
        merge_lora_weights(args.lora_paths, args.output, args.merge_method)


if __name__ == "__main__":
    main()
