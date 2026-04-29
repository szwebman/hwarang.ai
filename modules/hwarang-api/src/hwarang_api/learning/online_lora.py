"""LoRA 점진 학습 — Phase 2 메인 함수.

흐름:
1. TrainingJob 을 running 으로 마킹
2. base + LoRA 어댑터 로드 (transformers + peft)
3. 옛 Fisher snapshot 로드 (있으면)
4. 신규 + 리플레이 배치 합치기
5. 학습 loop: CE loss + EWC penalty
6. 새 Fisher / optimal 스냅샷 → DB upsert
7. 새 LoRA 어댑터 디스크 저장 (버전 suffix)
8. 망각 점수 측정 → DB done 으로 마킹

torch / transformers / peft 가 학습 노드에만 설치되므로 모두 lazy import.
API 컨테이너에서 import 만 해도 fail 하지 않도록 격리.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from hwarang_api.learning.replay_buffer import sample_replay_batch
from hwarang_api.learning import training_state
from hwarang_api.learning.training_state import (
    get_fisher_snapshot,
    mark_done,
    mark_failed,
    mark_running,
    upsert_fisher_snapshot,
)

logger = logging.getLogger(__name__)


# 환경변수
FISHER_SNAPSHOT_DIR = os.getenv(
    "HSEE_FISHER_SNAPSHOT_DIR", "/var/hwarang/fisher_snapshots"
)
LORA_OUTPUT_DIR = os.getenv(
    "HSEE_LORA_OUTPUT_DIR", "/mnt/nvme2/hwarang/lora_adapters"
)


# ────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────
async def train_online_lora(
    job_id: str,
    domain: str,
    base_model: str,
    target_lora_path: str,
    *,
    epochs: int = 1,
    learning_rate: float = 1e-4,
    batch_size: int = 64,
    new_data_ratio: float = 0.7,
    ewc_lambda: float = 1000.0,
) -> dict:
    """LoRA 점진 학습 1 라운드.

    Returns
    -------
    dict
        성공: ``{"success": True, "adapter": "...", "forgetting": 0.0X}``
        실패: ``{"success": False, "error": "..."}``
    """
    await mark_running(job_id)
    started = time.time()

    try:
        # ── 0. 데이터 먼저 (모델 로딩 비용 회피) ──
        batch = await sample_replay_batch(
            domain=domain,
            batch_size=batch_size,
            new_data_ratio=new_data_ratio,
        )
        all_samples = batch["new"] + batch["replay"]
        if not all_samples:
            await mark_failed(job_id, "no_data")
            return {"success": False, "error": "no_data"}

        # ── 1. 모델 / 토크나이저 로드 (lazy import) ──
        model, tokenizer = _load_model_with_lora(base_model, target_lora_path)

        # ── 2. 옛 Fisher snapshot 로드 ──
        from hwarang_api.learning.ewc import (
            compute_fisher,
            ewc_penalty,
            load_fisher_snapshot,
            save_fisher_snapshot,
            snapshot_optimal_params,
        )

        lora_name = Path(target_lora_path).name
        snap_meta = await get_fisher_snapshot(lora_name, domain)
        old_fisher, old_optimal = None, None
        if snap_meta:
            try:
                old_fisher, old_optimal = load_fisher_snapshot(
                    snap_meta["fisherPath"],
                    snap_meta["optimalPath"],
                    device=str(_device(model)),
                )
                logger.info(
                    f"Fisher snapshot 로드: lora={lora_name} domain={domain} "
                    f"taskCount={snap_meta['taskCount']}"
                )
            except Exception as e:
                logger.warning(f"Fisher 로드 실패 (무시하고 진행): {e}")

        # ── 3. 학습 loop ──
        import torch  # type: ignore

        model.train()
        optimizer = torch.optim.AdamW(
            [p for p in model.parameters() if p.requires_grad], lr=learning_rate
        )

        total_loss = 0.0
        steps = 0
        for epoch in range(epochs):
            for sample in all_samples:
                prompt = sample.get("prompt", "")
                completion = sample.get("completion", "")
                if not prompt or not completion:
                    continue

                # tokenize prompt + completion (causal LM)
                full = prompt + "\n" + completion
                enc = tokenizer(
                    full,
                    return_tensors="pt",
                    truncation=True,
                    max_length=1024,
                )
                input_ids = enc["input_ids"].to(_device(model))
                attention_mask = enc["attention_mask"].to(_device(model))

                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=input_ids,
                )
                loss = outputs.loss

                # EWC penalty
                if old_fisher is not None and old_optimal is not None:
                    loss = loss + ewc_penalty(
                        model, old_fisher, old_optimal, lam=ewc_lambda
                    )

                loss.backward()
                optimizer.step()
                optimizer.zero_grad()

                total_loss += float(loss.detach().cpu().item())
                steps += 1

        avg_loss = total_loss / max(steps, 1)
        logger.info(f"학습 완료: steps={steps} avg_loss={avg_loss:.4f}")

        # ── 4. 새 Fisher snapshot ──
        # dataloader 형태로 바꾸기 — 간단 wrap
        fisher_dataloader = _make_fisher_dataloader(all_samples, tokenizer, model)
        new_fisher = compute_fisher(
            model, fisher_dataloader, device=str(_device(model)), samples=100
        )
        new_optimal = snapshot_optimal_params(model)

        snapshot_dir = os.path.join(FISHER_SNAPSHOT_DIR, domain, lora_name)
        paths = save_fisher_snapshot(new_fisher, new_optimal, snapshot_dir)
        await upsert_fisher_snapshot(
            lora_name=lora_name,
            domain=domain,
            fisher_path=paths["fisher"],
            optimal_path=paths["optimal"],
        )

        # ── 5. 새 LoRA 어댑터 저장 ──
        version_tag = int(time.time())
        new_adapter_path = os.path.join(
            LORA_OUTPUT_DIR, f"{lora_name}_v{version_tag}"
        )
        Path(new_adapter_path).mkdir(parents=True, exist_ok=True)
        model.save_pretrained(new_adapter_path)
        logger.info(f"새 어댑터 저장: {new_adapter_path}")

        # ── 6. 망각 측정 ──
        from hwarang_api.learning.forgetting_metric import measure_forgetting

        try:
            forgetting = await measure_forgetting(
                model, current_domain=domain, tokenizer=tokenizer
            )
        except Exception as e:
            logger.warning(f"forgetting 측정 실패 (0.0 처리): {e}")
            forgetting = 0.0

        # ── 7. DB done ──
        await mark_done(
            job_id,
            new_adapter_path=new_adapter_path,
            forgetting_score=forgetting,
            quality_score=max(0.0, min(1.0, 1.0 - avg_loss / 10.0)),
            sample_count=len(all_samples),
        )

        return {
            "success": True,
            "adapter": new_adapter_path,
            "forgetting": forgetting,
            "avg_loss": avg_loss,
            "samples": len(all_samples),
            "steps": steps,
            "elapsed_sec": round(time.time() - started, 1),
        }

    except Exception as e:  # pragma: no cover
        logger.exception(f"train_online_lora 실패 (job={job_id}): {e}")
        await mark_failed(job_id, str(e))
        return {"success": False, "error": str(e)}


# ────────────────────────────────────────────────────────────
# Helpers — 모두 학습 노드에서만 호출
# ────────────────────────────────────────────────────────────
def _load_model_with_lora(base_model: str, lora_path: str) -> tuple[Any, Any]:
    """transformers + peft 로 base + LoRA 로드."""
    try:
        import torch  # type: ignore
        from peft import PeftModel  # type: ignore
        from transformers import (  # type: ignore
            AutoModelForCausalLM,
            AutoTokenizer,
        )
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "transformers / peft / torch 가 설치되지 않았습니다. "
            "학습 노드에서 'pip install transformers peft torch' 후 재시도하세요."
        ) from e

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model = PeftModel.from_pretrained(base, lora_path, is_trainable=True)
    return model, tokenizer


def _device(model: Any) -> Any:
    """모델의 첫 파라미터 device."""
    return next(model.parameters()).device


def _make_fisher_dataloader(
    samples: list[dict], tokenizer: Any, model: Any
) -> list[dict]:
    """compute_fisher 가 받는 dict iterable 형태 생성."""
    out = []
    for s in samples:
        full = (s.get("prompt") or "") + "\n" + (s.get("completion") or "")
        if not full.strip():
            continue
        enc = tokenizer(
            full, return_tensors="pt", truncation=True, max_length=1024
        )
        out.append(
            {
                "input_ids": enc["input_ids"],
                "attention_mask": enc["attention_mask"],
                "labels": enc["input_ids"].clone(),
            }
        )
    return out


__all__ = ["train_online_lora"]
