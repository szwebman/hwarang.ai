"""EWC (Elastic Weight Consolidation) — Phase 2.

새 task 학습 시 옛 task 의 중요한 가중치를 보호한다.

수식 (Kirkpatrick et al., 2017):

    L_total(θ) = L_new(θ) + λ/2 · Σ_i F_i · (θ_i − θ*_i)²

- ``F_i`` : Fisher 정보 행렬 (대각 근사) i 번째 원소.
            옛 task 의 log-likelihood 의 ∂/∂θ_i 의 제곱 평균.
            "그 가중치가 옛 task 에 얼마나 중요했나" 의 척도.
- ``θ*_i``: 옛 task 학습 직후 가중치 i 의 값 (snapshot).
- ``λ``   : 정규화 강도. 보통 100 ~ 10000. 우리 기본값 1000.

LoRA 만 학습 (~10MB) 이라 베이스 모델 가중치는 어차피 안 바뀐다 →
Fisher / θ* 는 ``requires_grad=True`` 인 LoRA A,B 행렬에만 적용한다.

Phase 2 의 EWC 구현은 **실제 학습 가능 (production-ready)**:
- ``compute_fisher`` 는 dataloader 를 직접 forward → backward → grad² 평균.
- ``ewc_penalty`` 는 학습 step 마다 호출해 일반 loss 에 더하면 끝.
- 디스크 저장은 torch.save → torch.load 로 stateless.

torch / transformers / peft 가 import 가능해야 한다 (학습 환경 전용).
API 서버 메인 루프에서는 절대 import 되지 않는다 (lazy import 패턴).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# Lazy torch import — API 컨테이너에서는 torch 가 없을 수 있음
# ────────────────────────────────────────────────────────────


def _torch():
    """torch 를 lazy import. 학습 노드에서만 사용."""
    try:
        import torch  # type: ignore

        return torch
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "torch 가 설치되지 않았습니다. 학습 노드에서만 EWC 모듈을 사용하세요."
        ) from e


# ────────────────────────────────────────────────────────────
# Fisher 정보 행렬 계산
# ────────────────────────────────────────────────────────────
def compute_fisher(
    model: Any,
    dataloader: Iterable[dict],
    device: str = "cuda",
    samples: int = 200,
) -> dict:
    """Fisher 정보 행렬 (대각 근사) 계산.

    각 sample 의 log-likelihood (= -loss) 의 gradient 의 제곱을 평균.
    F_i 가 클수록 그 가중치가 옛 task 에 중요했다는 뜻.

    Parameters
    ----------
    model : torch.nn.Module
        PEFT 로 LoRA 가 붙은 ``PeftModel`` 권장.
    dataloader : iterable of dict
        각 element 는 ``model(**batch)`` 로 들어갈 수 있는 dict (input_ids, labels …).
    device : str
        "cuda" 또는 "cpu".
    samples : int
        몇 개 sample 로 Fisher 를 추정할지. 200 정도면 안정.

    Returns
    -------
    dict[str, torch.Tensor]
        파라미터 이름 → Fisher 대각 텐서.
    """
    torch = _torch()
    model.eval()
    fisher = {
        n: torch.zeros_like(p) for n, p in model.named_parameters() if p.requires_grad
    }

    count = 0
    for batch in dataloader:
        if count >= samples:
            break
        try:
            model.zero_grad()
            # device 이동 (이미 device 인 텐서면 no-op)
            inputs = {
                k: (v.to(device) if hasattr(v, "to") else v) for k, v in batch.items()
            }
            outputs = model(**inputs)
            loss = outputs.loss
            if loss is None:  # pragma: no cover
                continue
            loss.backward()
            for n, p in model.named_parameters():
                if p.grad is not None and n in fisher:
                    fisher[n] += p.grad.detach() ** 2
            count += 1
        except Exception as e:  # pragma: no cover
            logger.warning(f"Fisher 계산 sample {count} 실패: {e}")
            continue

    denom = max(count, 1)
    for n in fisher:
        fisher[n] /= denom

    logger.info(f"Fisher 계산 완료: params={len(fisher)} samples={count}")
    return fisher


# ────────────────────────────────────────────────────────────
# 디스크 직렬화
# ────────────────────────────────────────────────────────────
def save_fisher_snapshot(
    fisher: dict,
    optimal_params: dict,
    output_dir: str,
) -> dict[str, str]:
    """Fisher 행렬 + 최적 가중치 디스크 저장.

    Parameters
    ----------
    fisher : dict[str, torch.Tensor]
        ``compute_fisher`` 결과.
    optimal_params : dict[str, torch.Tensor]
        학습 직후 ``model.named_parameters`` 의 detach().clone() 사본.
    output_dir : str
        저장 디렉토리. 자동 생성.

    Returns
    -------
    dict
        ``{"fisher": fisher_path, "optimal": optimal_path}``
    """
    torch = _torch()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    fisher_path = os.path.join(output_dir, "fisher.pt")
    optimal_path = os.path.join(output_dir, "optimal.pt")
    torch.save(fisher, fisher_path)
    torch.save(optimal_params, optimal_path)
    logger.info(
        f"Fisher snapshot 저장: {fisher_path} ({_size_mb(fisher_path)} MB), "
        f"{optimal_path} ({_size_mb(optimal_path)} MB)"
    )
    return {"fisher": fisher_path, "optimal": optimal_path}


def load_fisher_snapshot(
    fisher_path: str, optimal_path: str, device: str = "cuda"
) -> tuple[dict, dict]:
    """디스크에서 Fisher / 최적 가중치 복원."""
    torch = _torch()
    fisher = torch.load(fisher_path, map_location=device)
    optimal = torch.load(optimal_path, map_location=device)
    return fisher, optimal


# ────────────────────────────────────────────────────────────
# EWC penalty — 학습 loop 안에서 매 step 호출
# ────────────────────────────────────────────────────────────
def ewc_penalty(
    model: Any,
    fisher: dict,
    optimal: dict,
    lam: float = 1000.0,
) -> Any:
    """EWC 정규화 항 계산.

        penalty = (λ/2) · Σ F_i · (θ_i − θ*_i)²

    학습 loop 에서 ``loss = ce_loss + ewc_penalty(...)`` 로 합산하면
    옛 task 의 중요한 가중치가 보호된다.

    Parameters
    ----------
    model : torch.nn.Module
        현재 학습 중인 모델 (LoRA 가 붙은 PeftModel).
    fisher : dict[str, torch.Tensor]
        옛 task 의 Fisher snapshot.
    optimal : dict[str, torch.Tensor]
        옛 task 학습 직후의 최적 θ*.
    lam : float
        정규화 강도. 너무 크면 새 task 못 배우고, 너무 작으면 망각.

    Returns
    -------
    torch.Tensor
        scalar penalty (현재 모델 device 의 텐서).
    """
    torch = _torch()
    device = next(model.parameters()).device
    penalty = torch.tensor(0.0, device=device)

    for n, p in model.named_parameters():
        if n in fisher and n in optimal:
            f = fisher[n].to(device)
            o = optimal[n].to(device)
            penalty = penalty + (f * (p - o) ** 2).sum()

    return (lam / 2.0) * penalty


# ────────────────────────────────────────────────────────────
# 헬퍼
# ────────────────────────────────────────────────────────────
def snapshot_optimal_params(model: Any) -> dict:
    """현재 모델의 학습 가능 파라미터를 detach().clone() 으로 복제.

    학습 직후 호출해서 ``save_fisher_snapshot`` 의 ``optimal_params`` 인자로 사용.
    """
    return {
        n: p.detach().clone().cpu()
        for n, p in model.named_parameters()
        if p.requires_grad
    }


def _size_mb(path: str) -> float:
    try:
        return round(os.path.getsize(path) / (1024 * 1024), 2)
    except OSError:
        return 0.0


__all__ = [
    "compute_fisher",
    "save_fisher_snapshot",
    "load_fisher_snapshot",
    "ewc_penalty",
    "snapshot_optimal_params",
]
