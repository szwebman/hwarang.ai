"""HLKM ⑧ Temporal GNN — PENDING → CONFIRMED 전이 예측.

과거에 PENDING 으로 들어왔다가 CONFIRMED/EXPIRED 로 넘어간 팩트들의
이력을 학습 데이터로 삼아, 새 PENDING 팩트의 확정 확률을 추정한다.

본 모듈은 두 가지 구현을 함께 제공한다.

    1. **SimplePredictor** (기본, 의존성 없음)
       - 6차원 수치 피처 + 로지스틱 회귀 분류기.
       - scikit-learn 이 있으면 그것을 쓰고, 없으면 순수 파이썬 GD 로 학습.
       - 배포 환경에서 즉시 동작.

    2. **PyGPredictor** (옵션, torch_geometric 필요)
       - 그래프 전체 구조와 시간 축을 이용하는 진짜 TGNN.
       - torch 와 torch_geometric 미설치 시 ImportError.

공개 인터페이스(`TemporalGNNModel`)는 impl 스위치로 두 구현을 감싼다.
`prediction.py` 의 베이지안 추론과 병렬적으로 사용 가능 — ensemble 하면 좋음.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from hwarang_api.db import prisma
from hwarang_api.knowledge.types import KnowledgeStatus

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(os.getenv("HLKM_MODEL_DIR", "/var/hlkm"))
_MODEL_DIR.mkdir(parents=True, exist_ok=True)

_FEATURE_DIM = 6  # [n_causes, n_supports, mean_src_rep, entity_hist, days_old, domain_rate]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ────────────────────────────────────────────
# 피처 추출
# ────────────────────────────────────────────
def feature_vector_for_fact(
    fact: dict, edges_count: dict, source_rep: float
) -> list[float]:
    """단일 팩트의 6차원 피처 벡터.

    Args:
        fact: {"id", "domain", "entity", "createdAt" 또는 "valid_from"} 등.
        edges_count: {"CAUSES", "SUPPORTS", "CONTRADICTS", "entity_history"} 카운트.
        source_rep: 출처 평판 0~1.

    Returns:
        길이 6 의 float 리스트.
    """
    n_causes = float(edges_count.get("CAUSES", 0))
    n_supports = float(edges_count.get("SUPPORTS", 0))
    entity_hist = float(edges_count.get("entity_history", 0))
    domain_rate = float(edges_count.get("domain_base_rate", 0.5))

    created = fact.get("createdAt") or fact.get("valid_from") or _utcnow()
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except Exception:
            created = _utcnow()
    days_since = max(0.0, (_utcnow() - _as_aware(created)).total_seconds() / 86400.0)

    # 정규화: 큰 값 압축.
    return [
        math.log1p(n_causes),
        math.log1p(n_supports),
        max(0.0, min(1.0, source_rep)),
        math.log1p(entity_hist),
        math.log1p(days_since),
        max(0.0, min(1.0, domain_rate)),
    ]


# ────────────────────────────────────────────
# 학습 데이터 구축
# ────────────────────────────────────────────
async def build_training_data(min_examples: int = 100) -> list[dict]:
    """DB 에서 PENDING → (CONFIRMED|EXPIRED) 로 전이 완료된 팩트들을
    피처·라벨 튜플 리스트로 반환한다.

    label = 1 → CONFIRMED, label = 0 → EXPIRED.
    """
    rows = await prisma.knowledgefact.find_many(
        where={
            "status": {
                "in": [KnowledgeStatus.CONFIRMED.value, KnowledgeStatus.EXPIRED.value]
            }
        },
        take=max(min_examples * 4, 1000),
    )
    samples: list[dict] = []
    entity_counts: dict[str, int] = {}
    domain_stats: dict[str, list[int]] = {}
    for r in rows:
        ent = getattr(r, "entity", None) or "∅"
        entity_counts[ent] = entity_counts.get(ent, 0) + 1
        domain_stats.setdefault(r.domain, []).append(
            1 if r.status == KnowledgeStatus.CONFIRMED.value else 0
        )

    domain_rates = {
        d: (sum(v) / len(v)) if v else 0.5 for d, v in domain_stats.items()
    }

    # edge 집계는 대량 조회 부담이 크므로 fact 당 개별 쿼리로.
    for r in rows:
        fact_id = r.id
        try:
            edges_from = await prisma.knowledgeedge.find_many(
                where={"fromFactId": fact_id}, take=100
            )
        except Exception:
            edges_from = []
        counts = {"CAUSES": 0, "SUPPORTS": 0, "CONTRADICTS": 0}
        for e in edges_from:
            rt = getattr(e, "relationType", None) or getattr(e, "relation_type", None)
            if rt in counts:
                counts[rt] += 1
        counts["entity_history"] = entity_counts.get(
            getattr(r, "entity", None) or "∅", 0
        )
        counts["domain_base_rate"] = domain_rates.get(r.domain, 0.5)

        # source_rep 가져오기 (없으면 0.7 중립).
        src_rep = 0.7
        try:
            rep_row = await prisma.sourcereputation.find_first(
                where={"source": r.source}
            )
            if rep_row is not None:
                src_rep = float(getattr(rep_row, "reputation", 0.7) or 0.7)
        except Exception:
            pass

        features = feature_vector_for_fact(
            {
                "id": r.id,
                "domain": r.domain,
                "entity": getattr(r, "entity", None),
                "createdAt": getattr(r, "createdAt", None)
                or getattr(r, "validFrom", None),
            },
            counts,
            src_rep,
        )
        label = 1 if r.status == KnowledgeStatus.CONFIRMED.value else 0
        samples.append(
            {"fact_id": fact_id, "features": features, "label": label}
        )

    return samples


# ────────────────────────────────────────────
# SimplePredictor — 로지스틱 회귀
# ────────────────────────────────────────────
class SimplePredictor:
    """순수 파이썬 / scikit-learn 하이브리드 로지스틱 회귀 예측기.

    - sklearn 가용 시 sklearn.linear_model.LogisticRegression 사용.
    - 아니면 직접 구현한 GD 로 학습.
    - 출력: 확정 확률 (0~1) + 예상 확정일 (도메인 기본 지연 기반).
    """

    def __init__(self) -> None:
        self.weights: list[float] = [0.0] * _FEATURE_DIM
        self.bias: float = 0.0
        self.backend: str = "pure"  # 또는 "sklearn"
        self._sklearn_model: Any = None

    # ---- 학습 ----
    def fit(self, X: list[list[float]], y: list[int]) -> dict:
        if not X:
            return {"trained": False, "reason": "empty"}

        try:
            from sklearn.linear_model import LogisticRegression  # type: ignore

            model = LogisticRegression(max_iter=500, C=1.0)
            model.fit(X, y)
            self._sklearn_model = model
            self.backend = "sklearn"
            self.weights = [float(w) for w in model.coef_[0]]
            self.bias = float(model.intercept_[0])
            return {"trained": True, "backend": "sklearn", "n": len(X)}
        except Exception as exc:
            logger.debug("sklearn unavailable (%s), fallback to pure-python GD", exc)

        # 순수 GD
        lr = 0.05
        epochs = 200
        n_features = len(X[0])
        self.weights = [0.0] * n_features
        self.bias = 0.0
        n = len(X)
        for ep in range(epochs):
            grad_w = [0.0] * n_features
            grad_b = 0.0
            loss = 0.0
            for xi, yi in zip(X, y):
                z = sum(w * x for w, x in zip(self.weights, xi)) + self.bias
                p = 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, z))))
                err = p - yi
                for j in range(n_features):
                    grad_w[j] += err * xi[j]
                grad_b += err
                # log-loss
                pe = max(1e-9, min(1.0 - 1e-9, p))
                loss -= yi * math.log(pe) + (1 - yi) * math.log(1 - pe)
            for j in range(n_features):
                self.weights[j] -= lr * grad_w[j] / n
            self.bias -= lr * grad_b / n
            if ep == epochs - 1:
                logger.debug("GD final loss=%.4f", loss / max(1, n))
        self.backend = "pure"
        return {"trained": True, "backend": "pure", "n": n}

    # ---- 예측 ----
    def predict_proba(self, x: list[float]) -> float:
        if self._sklearn_model is not None:
            try:
                return float(self._sklearn_model.predict_proba([x])[0][1])
            except Exception:
                pass
        z = sum(w * xi for w, xi in zip(self.weights, x)) + self.bias
        z = max(-50.0, min(50.0, z))
        return 1.0 / (1.0 + math.exp(-z))

    # ---- 영속화 ----
    def to_dict(self) -> dict:
        return {
            "weights": self.weights,
            "bias": self.bias,
            "backend": self.backend,
            "feature_dim": _FEATURE_DIM,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SimplePredictor:
        obj = cls()
        obj.weights = [float(w) for w in data.get("weights", [])]
        obj.bias = float(data.get("bias", 0.0))
        obj.backend = data.get("backend", "pure")
        return obj


# ────────────────────────────────────────────
# PyGPredictor — 옵션 스켈레톤
# ────────────────────────────────────────────
class PyGPredictor:
    """torch_geometric 기반 Temporal GNN (옵션).

    # TODO(pyg-impl): 아래 아키텍처를 torch_geometric 로 구현.
    # ─────────────────────────────────────────────────────────
    # 입력: (x: node_features[N, F], edge_index[2, E], edge_time[E], batch)
    # 1. Node embedding: Linear(F → 128)
    # 2. Temporal encoding: sin/cos(Δt) concat
    # 3. 2× TGConv/GCNConv with edge-time attention
    # 4. Target-node readout → Linear(128 → 1) → sigmoid
    # Loss: BCE. Optimizer: AdamW, lr=1e-3, weight_decay=1e-4.
    # 샘플링: k-hop temporal subgraph around target fact.
    # ─────────────────────────────────────────────────────────
    의존성(torch, torch_geometric) 이 없으면 ImportError 를 내어
    상위 레이어가 SimplePredictor 로 fallback 하도록 유도한다.
    """

    def __init__(self) -> None:
        try:
            import torch  # noqa: F401
            import torch_geometric  # noqa: F401
        except Exception as exc:
            raise ImportError(
                "PyGPredictor 는 torch + torch_geometric 이 필요합니다. "
                "설치: pip install torch torch_geometric. "
                f"원인: {exc}"
            ) from exc
        self._ready = True

    def fit(self, X: list[list[float]], y: list[int]) -> dict:  # pragma: no cover
        raise NotImplementedError("PyG 구현은 TODO — SimplePredictor 를 사용하세요.")

    def predict_proba(self, x: list[float]) -> float:  # pragma: no cover
        raise NotImplementedError("PyG 구현은 TODO — SimplePredictor 를 사용하세요.")


# ────────────────────────────────────────────
# 공통 Wrapper
# ────────────────────────────────────────────
class TemporalGNNModel:
    """SimplePredictor / PyGPredictor 를 impl 스위치로 감싼다."""

    def __init__(self, impl: Literal["simple", "pyg"] = "simple") -> None:
        self.impl = impl
        if impl == "pyg":
            self.predictor: Any = PyGPredictor()
        else:
            self.predictor = SimplePredictor()

    async def fit(self, training_data: list[dict]) -> dict:
        """training_data: [{features:[...], label: 0|1}, ...]."""
        X = [list(d["features"]) for d in training_data]
        y = [int(d["label"]) for d in training_data]
        metrics = self.predictor.fit(X, y)
        if X:
            preds = [1 if self.predictor.predict_proba(x) >= 0.5 else 0 for x in X]
            correct = sum(1 for p, t in zip(preds, y) if p == t)
            metrics["train_accuracy"] = correct / len(y)
        return metrics

    async def predict(self, fact_id: str) -> tuple[float, datetime | None]:
        """fact_id 의 확정 확률과 예상 확정일."""
        row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
        if row is None:
            return (0.0, None)

        try:
            edges_from = await prisma.knowledgeedge.find_many(
                where={"fromFactId": fact_id}, take=100
            )
        except Exception:
            edges_from = []
        counts: dict[str, Any] = {"CAUSES": 0, "SUPPORTS": 0, "CONTRADICTS": 0}
        for e in edges_from:
            rt = getattr(e, "relationType", None) or getattr(e, "relation_type", None)
            if rt in counts:
                counts[rt] += 1

        try:
            entity_hist = await prisma.knowledgefact.count(
                where={"entity": getattr(row, "entity", None)}
            )
        except Exception:
            entity_hist = 0
        counts["entity_history"] = entity_hist
        counts["domain_base_rate"] = 0.5

        src_rep = 0.7
        try:
            rep_row = await prisma.sourcereputation.find_first(
                where={"source": row.source}
            )
            if rep_row is not None:
                src_rep = float(getattr(rep_row, "reputation", 0.7) or 0.7)
        except Exception:
            pass

        x = feature_vector_for_fact(
            {
                "id": row.id,
                "domain": row.domain,
                "entity": getattr(row, "entity", None),
                "createdAt": getattr(row, "createdAt", None)
                or getattr(row, "validFrom", None),
            },
            counts,
            src_rep,
        )
        prob = self.predictor.predict_proba(x)

        default_days = {"law": 90, "regulation": 60, "technology": 30, "general": 45}
        delay = default_days.get(row.domain, 45)
        # 확률이 높을수록 더 빨리 확정.
        adj = int(delay * (1.4 - 0.8 * prob))
        eta = _utcnow() + timedelta(days=max(1, adj))
        return (prob, eta)

    # ---- 저장/로드 ----
    def save(self, path: str) -> None:
        if not isinstance(self.predictor, SimplePredictor):
            raise NotImplementedError("PyG 모델 저장은 TODO.")
        data = {"impl": self.impl, "predictor": self.predictor.to_dict()}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2))

    @classmethod
    def load(cls, path: str) -> TemporalGNNModel:
        data = json.loads(Path(path).read_text())
        obj = cls(impl=data.get("impl", "simple"))
        if isinstance(obj.predictor, SimplePredictor):
            obj.predictor = SimplePredictor.from_dict(data["predictor"])
        return obj


# ────────────────────────────────────────────
# 평가
# ────────────────────────────────────────────
def evaluate_predictor(predictor: Any, test_data: list[dict]) -> dict:
    """precision/recall/F1 + calibration (Brier score)."""
    if not test_data:
        return {"n": 0}
    tp = fp = tn = fn = 0
    brier = 0.0
    for d in test_data:
        x = list(d["features"])
        y = int(d["label"])
        p = predictor.predict_proba(x)
        pred = 1 if p >= 0.5 else 0
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 0:
            tn += 1
        else:
            fn += 1
        brier += (p - y) ** 2
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = (
        2 * precision * recall / max(1e-9, precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "n": len(test_data),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "brier": brier / len(test_data),
        "accuracy": (tp + tn) / len(test_data),
    }


# ────────────────────────────────────────────
# 고수준 파이프라인
# ────────────────────────────────────────────
async def train_tgnn(
    impl: str = "simple", output_path: str = "/var/hlkm/tgnn_model.json"
) -> dict:
    """데이터 구축 → 학습 → 홀드아웃 평가 → 저장."""
    data = await build_training_data(min_examples=50)
    if len(data) < 10:
        return {"trained": False, "reason": "insufficient_data", "n": len(data)}

    # 80/20 분할
    random.seed(42)
    shuffled = list(data)
    random.shuffle(shuffled)
    split = int(len(shuffled) * 0.8)
    train, test = shuffled[:split], shuffled[split:]

    model = TemporalGNNModel(impl=impl)  # type: ignore[arg-type]
    fit_metrics = await model.fit(train)
    eval_metrics = evaluate_predictor(model.predictor, test)

    try:
        model.save(output_path)
    except Exception as exc:
        logger.warning("model save failed: %s", exc)

    return {
        "trained": True,
        "n_train": len(train),
        "n_test": len(test),
        "fit": fit_metrics,
        "eval": eval_metrics,
        "path": output_path,
    }


async def predict_pending_fact_outcome(
    fact_id: str, model_path: str = "/var/hlkm/tgnn_model.json"
) -> tuple[float, datetime | None]:
    """저장된 모델을 로드해 단일 PENDING 팩트를 예측.

    모델 파일이 없으면 즉석에서 초기화된 SimplePredictor (prior=0.5) 로 폴백.
    """
    try:
        model = TemporalGNNModel.load(model_path)
    except Exception as exc:
        logger.debug("tgnn model load failed (%s), using uninitialized", exc)
        model = TemporalGNNModel(impl="simple")
    return await model.predict(fact_id)


__all__ = [
    "TemporalGNNModel",
    "SimplePredictor",
    "PyGPredictor",
    "build_training_data",
    "train_tgnn",
    "predict_pending_fact_outcome",
    "feature_vector_for_fact",
    "evaluate_predictor",
]
