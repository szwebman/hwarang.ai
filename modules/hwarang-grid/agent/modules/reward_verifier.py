"""모듈 8: 리워드 검증 에이전트

가짜 GPU 기여 감지 → 코인 부정 수급 방지.
다른 에이전트의 작업 증명을 검증.

검증 방법:
  1. GPU 벤치마크 진위 확인 (실제 연산 테스트)
  2. 작업 증명 해시 검증
  3. 응답 시간 정상 범위 확인
  4. 패턴 분석 (반복 제출, 복사 제출 감지)

보상: 검증 1건당 2 HWR, 부정 발견 시 보너스 20 HWR
"""

import hashlib, time, json, logging

logger = logging.getLogger(__name__)


class RewardVerifierModule:
    def __init__(self, config):
        self.config = config
        self.verified_count = 0
        self.suspicious_count = 0
        self.seen_hashes: set[str] = set()

    def verify_gpu_claim(self, claimed_gpu: str, benchmark_result: dict) -> dict:
        """GPU 성능 주장 검증."""
        expected_ranges = {
            "RTX 4060": (10, 25),
            "RTX 4090": (40, 70),
            "RTX 5090": (60, 120),
        }
        expected = expected_ranges.get(claimed_gpu, (5, 200))
        actual_tps = benchmark_result.get("tokens_per_sec", 0)

        legitimate = expected[0] <= actual_tps <= expected[1]
        if not legitimate:
            self.suspicious_count += 1

        return {
            "legitimate": legitimate,
            "claimed_gpu": claimed_gpu,
            "actual_tps": actual_tps,
            "expected_range": expected,
            "reason": "" if legitimate else f"성능 {actual_tps} tps는 {claimed_gpu} 범위 밖",
        }

    def verify_work_proof(self, worker_id: str, work_hash: str, claimed_steps: int, elapsed_sec: float) -> dict:
        """작업 증명 검증."""
        issues = []

        # 해시 중복 체크 (같은 결과 재제출 감지)
        if work_hash in self.seen_hashes:
            issues.append("중복 해시 (이전에 제출된 작업)")
            self.suspicious_count += 1
        self.seen_hashes.add(work_hash)

        # 시간 대비 step 수 검증 (너무 빠르면 의심)
        if claimed_steps > 0 and elapsed_sec > 0:
            steps_per_sec = claimed_steps / elapsed_sec
            if steps_per_sec > 10:  # 초당 10 step 이상은 비현실적
                issues.append(f"비현실적 속도: {steps_per_sec:.1f} steps/sec")

        # 너무 짧은 학습 시간
        if elapsed_sec < 10 and claimed_steps > 100:
            issues.append("의심: 10초 미만에 100+ step 완료")

        self.verified_count += 1
        legitimate = len(issues) == 0

        return {
            "legitimate": legitimate,
            "worker_id": worker_id,
            "issues": issues,
            "work_hash": work_hash[:16],
        }

    def verify_response_quality(self, response: str, expected_min_length: int = 50) -> dict:
        """서빙 응답 품질 검증 (무의미한 응답 감지)."""
        issues = []

        if len(response) < expected_min_length:
            issues.append("응답 너무 짧음")

        # 반복 패턴 감지
        words = response.split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:
                issues.append(f"반복 패턴 감지 (유니크 비율 {unique_ratio:.1%})")

        # 의미없는 응답 감지
        if response.strip() in ("", ".", "...", "없음", "모름", "I don't know"):
            issues.append("무의미한 응답")

        return {"legitimate": len(issues) == 0, "issues": issues}

    def get_stats(self) -> dict:
        return {
            "verified": self.verified_count,
            "suspicious": self.suspicious_count,
            "seen_hashes": len(self.seen_hashes),
        }
