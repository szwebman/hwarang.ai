"""HFL Peer Validation Agent

마스터 단독 검증 → 워커끼리 분산 검증으로 확장.
악성 참여자(poisoning attack) 방어 + 마스터 부하 감소.

프로세스:
  1. 워커 A가 LoRA 제출
  2. 마스터가 랜덤 워커 B, C를 검증자로 선정
  3. B, C가 자기 validation 데이터로 A의 LoRA 테스트
  4. 검증 결과 (점수 + 합격 여부) 마스터에 보고
  5. 다수결로 합격/불합격 판정
  6. 합격한 LoRA만 TIES 합성에 포함
  7. 검증 참여자에게도 토큰 보상

보안 이점:
  - 악성 LoRA 자동 필터링 (성능 악화 시 거부)
  - 단일 마스터 의존 제거 (탈중앙 검증)
  - Sybil attack 방어 (검증자 랜덤 선정)

사용법:
    # 마스터 모드: 검증 오케스트레이션
    python scripts/advanced/hfl_peer_validation.py master --port 9091

    # 검증자 모드: 다른 워커의 LoRA 검증
    python scripts/advanced/hfl_peer_validation.py validator \\
        --master http://master:9091 \\
        --validation-data /path/to/val.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import hashlib
from dataclasses import dataclass, asdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 검증 결과 ───────────────────────────────────────────────

@dataclass
class ValidationResult:
    validator_id: str
    worker_id: str           # 검증 대상 워커
    round_num: int
    passed: bool
    score: float             # 0~1 (baseline 대비 성능)
    baseline_loss: float     # LoRA 적용 전 loss
    lora_loss: float         # LoRA 적용 후 loss
    improvement: float       # (baseline - lora) / baseline
    samples_tested: int
    details: str


# ─── 검증 로직 ───────────────────────────────────────────────

def validate_lora(
    base_model_path: str,
    lora_path: str,
    validation_data: str,
    max_samples: int = 100,
) -> ValidationResult:
    """다른 워커의 LoRA를 내 validation 데이터로 검증.

    기준:
      1. LoRA 적용 전(baseline) loss 측정
      2. LoRA 적용 후 loss 측정
      3. loss가 악화되면 불합격
      4. loss가 개선되면 합격 (개선도 리포트)
    """
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except ImportError:
        return ValidationResult(
            validator_id="", worker_id="", round_num=0,
            passed=False, score=0, baseline_loss=0, lora_loss=0,
            improvement=0, samples_tested=0,
            details="필수 패키지 없음 (transformers, peft)",
        )

    logger.info(f"검증 시작: {lora_path}")

    # 토크나이저
    tokenizer = AutoTokenizer.from_pretrained(base_model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Validation 데이터 로드
    val_texts = []
    with open(validation_data, encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line.strip())
                messages = item.get("messages", [])
                if len(messages) >= 2:
                    text = " ".join(m["content"] for m in messages)
                    val_texts.append(text[:512])  # 길이 제한
            except Exception:
                continue
            if len(val_texts) >= max_samples:
                break

    if len(val_texts) == 0:
        return ValidationResult(
            validator_id="", worker_id="", round_num=0,
            passed=False, score=0, baseline_loss=0, lora_loss=0,
            improvement=0, samples_tested=0,
            details="검증 데이터 없음",
        )

    logger.info(f"  검증 샘플: {len(val_texts)}개")

    # Baseline loss (LoRA 없이)
    logger.info("  Baseline loss 측정 중...")
    model = AutoModelForCausalLM.from_pretrained(
        base_model_path, torch_dtype=torch.float16,
        device_map="auto", trust_remote_code=True,
    )

    baseline_loss = _compute_avg_loss(model, tokenizer, val_texts)
    logger.info(f"  Baseline loss: {baseline_loss:.4f}")

    # LoRA 적용 후 loss
    logger.info(f"  LoRA 적용 중: {lora_path}")
    try:
        model = PeftModel.from_pretrained(model, lora_path)
        lora_loss = _compute_avg_loss(model, tokenizer, val_texts)
    except Exception as e:
        return ValidationResult(
            validator_id="", worker_id="", round_num=0,
            passed=False, score=0, baseline_loss=baseline_loss, lora_loss=999,
            improvement=0, samples_tested=len(val_texts),
            details=f"LoRA 로드 실패: {e}",
        )

    logger.info(f"  LoRA loss: {lora_loss:.4f}")

    # 판정
    improvement = (baseline_loss - lora_loss) / max(baseline_loss, 1e-6)
    passed = lora_loss <= baseline_loss * 1.05  # 5% 이내 악화까지 허용

    # 점수 (0~1, 개선도 기반)
    score = max(0.0, min(1.0, 0.5 + improvement * 5))

    result = ValidationResult(
        validator_id="",
        worker_id="",
        round_num=0,
        passed=passed,
        score=score,
        baseline_loss=baseline_loss,
        lora_loss=lora_loss,
        improvement=improvement,
        samples_tested=len(val_texts),
        details=f"{'✅ 합격' if passed else '❌ 불합격'}: "
                f"loss {baseline_loss:.4f} → {lora_loss:.4f} "
                f"({improvement * 100:+.1f}%)",
    )

    logger.info(f"  결과: {result.details}")
    return result


def _compute_avg_loss(model, tokenizer, texts: list[str]) -> float:
    """평균 perplexity/loss 계산."""
    import torch

    model.eval()
    total_loss = 0.0
    count = 0

    with torch.no_grad():
        for text in texts:
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
            inputs = {k: v.to(model.device) for k, v in inputs.items()}

            try:
                outputs = model(**inputs, labels=inputs["input_ids"])
                total_loss += outputs.loss.item()
                count += 1
            except Exception:
                continue

    return total_loss / max(count, 1)


# ─── 마스터: 검증 오케스트레이션 ──────────────────────────────

class PeerValidationOrchestrator:
    """마스터에서 실행. 검증자 선정 + 다수결 판정."""

    def __init__(self, min_validators: int = 2, pass_threshold: float = 0.5):
        self.min_validators = min_validators
        self.pass_threshold = pass_threshold  # 합격 비율 임계값
        self.registered_validators: dict[str, dict] = {}
        self.pending_validations: dict[str, list[ValidationResult]] = {}

    def register_validator(self, validator_id: str, info: dict):
        """검증 참여 가능한 워커 등록."""
        self.registered_validators[validator_id] = {
            "id": validator_id,
            **info,
            "validations_done": 0,
        }
        logger.info(f"검증자 등록: {validator_id} (총 {len(self.registered_validators)}명)")

    def select_validators(self, worker_id: str, n: int = 2) -> list[str]:
        """LoRA 제출한 워커를 제외하고 랜덤 검증자 선정."""
        candidates = [
            vid for vid in self.registered_validators
            if vid != worker_id  # 자기 자신 제외
        ]
        if len(candidates) < n:
            logger.warning(f"검증자 부족: {len(candidates)}명 (필요 {n}명)")
            return candidates

        selected = random.sample(candidates, n)
        logger.info(f"검증자 선정: {selected} (대상 워커: {worker_id})")
        return selected

    def submit_validation(self, result: ValidationResult) -> dict:
        """검증 결과 수신."""
        key = f"{result.worker_id}_round{result.round_num}"
        if key not in self.pending_validations:
            self.pending_validations[key] = []

        self.pending_validations[key].append(result)
        logger.info(
            f"검증 결과 수신: {result.validator_id} → {result.worker_id} "
            f"({'합격' if result.passed else '불합격'}, 점수 {result.score:.2f})"
        )

        # 충분한 검증 결과가 모이면 다수결
        results = self.pending_validations[key]
        if len(results) >= self.min_validators:
            return self._judge(key, results)

        return {
            "status": "pending",
            "validations_received": len(results),
            "validations_needed": self.min_validators,
        }

    def _judge(self, key: str, results: list[ValidationResult]) -> dict:
        """다수결로 최종 판정."""
        pass_count = sum(1 for r in results if r.passed)
        total = len(results)
        pass_ratio = pass_count / total

        final_passed = pass_ratio >= self.pass_threshold
        avg_score = sum(r.score for r in results) / total

        # 보상 계산 (검증 참여자)
        validator_rewards = {}
        for r in results:
            # 다수결과 일치한 검증자에게 보상 (정확한 판단)
            agreed = r.passed == final_passed
            reward = 30 if agreed else 10  # 일치: 30토큰, 불일치: 10토큰
            validator_rewards[r.validator_id] = reward

        verdict = {
            "status": "judged",
            "worker_id": results[0].worker_id,
            "passed": final_passed,
            "pass_ratio": pass_ratio,
            "avg_score": avg_score,
            "validators": total,
            "pass_count": pass_count,
            "validator_rewards": validator_rewards,
            "details": [asdict(r) for r in results],
        }

        status = "✅ 합격" if final_passed else "❌ 불합격"
        logger.info(
            f"\n{'=' * 40}\n"
            f" 최종 판정: {status}\n"
            f" 대상: {results[0].worker_id}\n"
            f" 검증: {pass_count}/{total} 합격 ({pass_ratio * 100:.0f}%)\n"
            f" 평균 점수: {avg_score:.2f}\n"
            f"{'=' * 40}"
        )

        # 정리
        del self.pending_validations[key]

        return verdict


# ─── 메인 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HFL Peer Validation")
    parser.add_argument("mode", choices=["master", "validator", "test"])
    parser.add_argument("--port", type=int, default=9091)
    parser.add_argument("--master", default="http://localhost:9091")
    parser.add_argument("--validation-data", help="검증용 데이터 JSONL")
    parser.add_argument("--base-model", help="베이스 모델 경로 (검증자)")
    parser.add_argument("--lora-path", help="검증할 LoRA 경로 (테스트)")
    args = parser.parse_args()

    if args.mode == "master":
        orch = PeerValidationOrchestrator(min_validators=2)
        logger.info(f"Peer Validation 마스터 시작 (포트 {args.port})")
        # 실제 HTTP 서버 구현은 Flask/FastAPI 권장

    elif args.mode == "validator":
        logger.info("Peer Validator 시작")
        logger.info(f"  마스터: {args.master}")
        logger.info(f"  검증 데이터: {args.validation_data}")
        # 마스터에 등록 → 검증 요청 대기 → validate_lora() 실행

    elif args.mode == "test":
        if not args.base_model or not args.lora_path or not args.validation_data:
            parser.error("test 모드: --base-model, --lora-path, --validation-data 필수")

        result = validate_lora(
            args.base_model, args.lora_path,
            args.validation_data, max_samples=50,
        )
        logger.info(f"\n검증 결과: {result.details}")
        logger.info(f"  점수: {result.score:.2f}")
        logger.info(f"  개선도: {result.improvement * 100:+.1f}%")


if __name__ == "__main__":
    main()
