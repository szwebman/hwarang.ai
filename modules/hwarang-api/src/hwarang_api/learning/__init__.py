"""HSEE Phase 1 — 복리 루프 (Compounding Loop).

채팅 응답 직후 4 개의 자기개선 루프를 동시에 트리거한다:

- A. RLHF       : 명시/암묵 피드백 → ``RLHFFeedback`` 테이블 누적
- B. HLKM       : 응답에서 사실 추출 → ``ingest_fact`` 로 지식 그래프 주입
- C. 라우팅     : 도메인×모델 단위 시간 윈도우 통계 → HNTL 가중치 입력
- D. HFL/LoRA   : 도메인별 1000 건 누적 시 학습 라운드 자동 시작

외부에서는 보통 :func:`on_chat_response` 만 호출한다.
"""

from hwarang_api.learning.compounding_loop import (
    ChatContext,
    on_chat_response,
)
from hwarang_api.learning.rlhf_collector import (
    record_explicit_feedback,
    record_feedback,
)
from hwarang_api.learning.routing_stats import (
    get_domain_quality,
    record_routing,
)
from hwarang_api.learning.satisfaction_scorer import (
    score_explicit,
    score_implicit,
)
from hwarang_api.learning.fact_extractor import extract_and_ingest_facts
from hwarang_api.learning.auto_trigger import maybe_trigger_training

# Phase 2 — Online Continual Learning (EWC + Replay)
from hwarang_api.learning.auto_trainer import (
    maybe_enqueue_training,
    process_queue,
    training_jobs_status,
)
from hwarang_api.learning.replay_buffer import (
    add_to_replay,
    sample_replay_batch,
)

# Phase 3 — Self-Growing Architecture
from hwarang_api.learning import (
    auto_spawn,
    capability_monitor,
    domain_clustering,
    growth_planner,
    scale_decision,
)

# Phase 5 — Self-Adversarial + Multi-Agent Synthesis
from hwarang_api.learning.adversarial_tester import (
    list_adversarial_findings,
    run_adversarial_self_play,
)
from hwarang_api.learning.federated_inference import federated_inference

# Phase 5.5 — Self-Questioning Engine (능동 질문 → 자체 답변 → 약점 자각)
from hwarang_api.learning.self_questioner import (
    child_questioning_cycle,
    manual_question_about,
    self_answer,
    socratic_dive,
)

__all__ = [
    "ChatContext",
    "on_chat_response",
    "record_feedback",
    "record_explicit_feedback",
    "record_routing",
    "get_domain_quality",
    "score_explicit",
    "score_implicit",
    "extract_and_ingest_facts",
    "maybe_trigger_training",
    # Phase 2
    "maybe_enqueue_training",
    "process_queue",
    "training_jobs_status",
    "add_to_replay",
    "sample_replay_batch",
    # Phase 3
    "capability_monitor",
    "domain_clustering",
    "auto_spawn",
    "scale_decision",
    "growth_planner",
    # Phase 5
    "run_adversarial_self_play",
    "list_adversarial_findings",
    "federated_inference",
    # Phase 5.5
    "child_questioning_cycle",
    "self_answer",
    "socratic_dive",
    "manual_question_about",
]
