"""화랑 Code Quality Pipeline.

수집된 코드 도메인 KnowledgeFact 들을 LoRA 학습 데이터로 변환하기 위한
5 단계 파이프라인.

  1. ``code_quality_filter``  — 출처/길이/문법/설명 6 요소 가중 합 → 품질 점수
  2. ``code_pair_builder``    — high_quality fact → 자연어 Q&A 페어 생성
  3. ``code_executor``        — 샌드박스 코드 실행 검증 (Python/JS, 10s timeout)
  4. ``code_rlhf_collector``  — 사용자 코드 피드백 4 유형 수집 → ReplaySample
  5. ``korean_style_guide``   — 영어 주석 → 한국어 자동 번역 후처리

cron 통합은 ``workers/hlkm_scheduler.py`` 의 ``code_quality`` /
``code_pair_build`` / ``code_pair_execute`` 잡으로 등록되어 있다.
"""

from __future__ import annotations

__all__ = [
    "code_quality_filter",
    "code_pair_builder",
    "code_executor",
    "code_rlhf_collector",
    "korean_style_guide",
]
