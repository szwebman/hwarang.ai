"""실제 GPU 학습 워커 — 별도 프로세스로 실행.

API 메인 프로세스와 GPU 공유 어려워서 격리.
file watch 로 trigger 받으면 PEFT + LoRA 학습 1 batch.

실행:
    python -m hwarang_api.learning.online.actual_trainer
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


_LORA_BASE = Path(os.getenv("HWARANG_ONLINE_LORA_DIR", "/var/hwarang/online_lora"))
SAMPLE_FILE = _LORA_BASE / "pending_samples.jsonl"
TRIGGER_FILE = _LORA_BASE / "trigger.flag"
LORA_DIR = _LORA_BASE / "current"


async def trainer_loop() -> None:
    """무한 루프 — trigger flag 감시."""
    _LORA_BASE.mkdir(parents=True, exist_ok=True)
    logger.info(f"Online trainer loop 시작 — watching {TRIGGER_FILE}")
    while True:
        if TRIGGER_FILE.exists():
            try:
                await _train_one_batch()
                try:
                    TRIGGER_FILE.unlink()
                except FileNotFoundError:
                    pass
            except Exception as e:  # pragma: no cover
                logger.exception(f"trainer 실패: {e}")
                # trigger 는 남겨둠 (재시도 위해)

        await asyncio.sleep(10)


async def _train_one_batch() -> None:
    """누적 sample → LoRA 1 batch 학습."""
    if not SAMPLE_FILE.exists():
        return

    samples: list[dict] = []
    try:
        with open(SAMPLE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    samples.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:  # pragma: no cover
        logger.warning(f"pending_samples 읽기 실패: {e}")
        return

    if len(samples) < 5:
        logger.debug(f"sample 부족 ({len(samples)}) — skip")
        return  # 너무 적음

    logger.info(f"Online LoRA 배치 학습 — {len(samples)} samples")

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        # 베이스 모델 + 현재 LoRA 로드
        base_path = os.getenv(
            "HWARANG_BASE_MODEL_PATH",
            "/mnt/nvme2/hwarang/models/hwarang-v5-awq",
        )

        tokenizer = AutoTokenizer.from_pretrained(base_path)
        model = AutoModelForCausalLM.from_pretrained(
            base_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )

        if LORA_DIR.exists():
            model = PeftModel.from_pretrained(model, str(LORA_DIR), is_trainable=True)

        model.train()
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-5)  # 낮은 lr (online 안전)

        from hwarang_api.learning.online.forgetting_prevention import GradientClipper

        clipper = GradientClipper()

        applied = 0
        skipped = 0
        for sample in samples:
            try:
                inputs = tokenizer(
                    sample["prompt"],
                    return_tensors="pt",
                    truncation=True,
                    max_length=2048,
                ).to(model.device)

                labels = tokenizer(
                    sample["completion"],
                    return_tensors="pt",
                    truncation=True,
                    max_length=2048,
                ).input_ids.to(model.device)

                outputs = model(**inputs, labels=labels)
                loss = outputs.loss * float(sample.get("weight", 1.0))

                loss.backward()

                # Gradient clipping — 명시 norm clip + 폭주 차단
                grad_norm = torch.nn.utils.clip_grad_norm_(
                    model.parameters(), max_norm=1.0
                )

                if clipper.should_apply(float(grad_norm)):
                    optimizer.step()
                    applied += 1
                else:
                    skipped += 1
                optimizer.zero_grad()
            except Exception as e:  # pragma: no cover
                logger.warning(f"sample 1건 학습 실패: {e}")
                skipped += 1

        # baseline backup → 현재 저장
        if LORA_DIR.exists():
            import shutil

            baseline = LORA_DIR.parent / "baseline"
            if baseline.exists():
                shutil.rmtree(baseline)
            shutil.copytree(LORA_DIR, baseline)

        model.save_pretrained(str(LORA_DIR))

        # samples 파일 비움
        try:
            SAMPLE_FILE.unlink()
            SAMPLE_FILE.touch()
        except Exception:  # pragma: no cover
            pass

        logger.info(
            f"Online LoRA 업데이트 완료 — total={len(samples)} applied={applied} skipped={skipped}"
        )

        # vLLM hot reload 트리거
        await _trigger_vllm_reload()

    except ImportError as e:
        logger.warning(f"학습 의존성 미설치: {e}")
    except Exception as e:  # pragma: no cover
        logger.exception(f"학습 실패: {e}")


async def _trigger_vllm_reload() -> None:
    """vLLM 의 LoRA hot-swap API 호출."""
    try:
        import httpx
    except ImportError:  # pragma: no cover
        logger.warning("httpx 미설치 — vLLM reload skip")
        return

    vllm_url = os.getenv("HWARANG_VLLM_URL", "http://localhost:8001")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # vLLM 0.7+ 의 LoRA load 엔드포인트
            resp = await client.post(
                f"{vllm_url}/v1/load_lora_adapter",
                json={
                    "lora_name": "hwarang-online",
                    "lora_path": str(LORA_DIR),
                },
            )
        logger.info(f"vLLM LoRA hot-reload 응답: {resp.status_code}")
    except Exception as e:  # pragma: no cover
        logger.warning(f"vLLM reload 실패 (수동 재시작 필요): {e}")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(trainer_loop())


if __name__ == "__main__":
    main()


__all__ = ["trainer_loop", "main"]
