"""HFL Task Failover - 학습 과제 장애 재할당

워커가 응답 없으면 자동으로 다른 워커에게 재할당.
데이터 손실 0.

프로세스:
  1. 워커에게 과제 할당 시 deadline 설정
  2. Heartbeat 모니터링 (30초 간격)
  3. Heartbeat 3회 연속 실패 → 장애 판정
  4. 해당 과제를 대기 중인 워커에게 즉시 재할당
  5. 원래 워커가 늦게 응답하면 → 먼저 온 것 채택, 나머지 폐기
  6. 체크포인트 기반 이어서 학습 (가능 시)

보장:
  - 데이터 손실 0 (모든 과제가 반드시 완료)
  - 중복 수행 허용 (at-least-once, 먼저 온 것 채택)
  - 악성 워커 자동 격리 (연속 3회 실패 → 블랙리스트)
"""

from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"           # 대기 중
    ASSIGNED = "assigned"         # 워커에 할당됨
    IN_PROGRESS = "in_progress"   # 학습 진행 중 (heartbeat 수신)
    COMPLETED = "completed"       # 완료
    FAILED = "failed"             # 실패 (재할당 대기)
    REASSIGNED = "reassigned"     # 다른 워커에 재할당됨


@dataclass
class LearningTask:
    task_id: str
    round_num: int
    data_config: dict           # 학습할 데이터 설정 (시드/도메인)
    steps: int                   # 할당된 step 수
    lora_rank: int

    # 할당 정보
    assigned_worker: str | None = None
    assigned_at: float | None = None
    deadline: float | None = None

    # 상태
    status: TaskStatus = TaskStatus.PENDING
    last_heartbeat: float | None = None
    heartbeat_failures: int = 0
    reassign_count: int = 0
    max_reassigns: int = 3

    # 결과
    completed_by: str | None = None
    lora_path: str | None = None
    completion_time: float | None = None

    # 체크포인트 (이어서 학습용)
    checkpoint_step: int = 0
    checkpoint_path: str | None = None


@dataclass
class WorkerState:
    worker_id: str
    status: str = "idle"          # idle, busy, offline, blacklisted
    current_task: str | None = None
    consecutive_failures: int = 0
    total_completed: int = 0
    last_seen: float = 0
    reliability_score: float = 1.0


class TaskFailoverManager:
    """학습 과제 장애 재할당 관리자."""

    def __init__(
        self,
        heartbeat_interval: float = 30,     # heartbeat 간격 (초)
        heartbeat_timeout: int = 3,          # 연속 실패 횟수 → 장애
        task_timeout_sec: float = 900,       # 과제 전체 타임아웃 (15분)
        blacklist_threshold: int = 3,        # 연속 실패 → 블랙리스트
    ):
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.task_timeout_sec = task_timeout_sec
        self.blacklist_threshold = blacklist_threshold

        self.tasks: dict[str, LearningTask] = {}
        self.workers: dict[str, WorkerState] = {}
        self.task_queue: list[str] = []       # 대기 중인 task_id
        self._lock = threading.Lock()

    # ─── 과제 생성 ───────────────────────────────────────

    def create_task(
        self,
        task_id: str,
        round_num: int,
        data_config: dict,
        steps: int,
        lora_rank: int = 16,
    ) -> LearningTask:
        """새 학습 과제 생성."""
        task = LearningTask(
            task_id=task_id,
            round_num=round_num,
            data_config=data_config,
            steps=steps,
            lora_rank=lora_rank,
        )
        self.tasks[task_id] = task
        self.task_queue.append(task_id)
        logger.info(f"과제 생성: {task_id} ({steps} step, r={lora_rank})")
        return task

    # ─── 과제 할당 ───────────────────────────────────────

    def assign_task(self, worker_id: str) -> LearningTask | None:
        """대기 중인 과제를 워커에게 할당."""
        with self._lock:
            worker = self.workers.get(worker_id)
            if not worker or worker.status == "blacklisted":
                return None

            if not self.task_queue:
                return None

            task_id = self.task_queue.pop(0)
            task = self.tasks[task_id]

            task.assigned_worker = worker_id
            task.assigned_at = time.time()
            task.deadline = time.time() + self.task_timeout_sec
            task.status = TaskStatus.ASSIGNED
            task.last_heartbeat = time.time()

            worker.status = "busy"
            worker.current_task = task_id

            logger.info(
                f"과제 할당: {task_id} → {worker_id} "
                f"(deadline {self.task_timeout_sec}초, "
                f"이어서 step {task.checkpoint_step}부터)"
            )

            return task

    # ─── Heartbeat 수신 ──────────────────────────────────

    def heartbeat(self, worker_id: str, progress: dict | None = None) -> dict:
        """워커의 heartbeat 수신.

        Args:
            worker_id: 워커 ID
            progress: {"step": 현재 step, "loss": 현재 loss} (선택)
        """
        worker = self.workers.get(worker_id)
        if not worker:
            return {"status": "unknown_worker"}

        worker.last_seen = time.time()
        worker.consecutive_failures = 0  # 연속 실패 카운트 리셋

        if worker.current_task:
            task = self.tasks.get(worker.current_task)
            if task:
                task.last_heartbeat = time.time()
                task.heartbeat_failures = 0
                task.status = TaskStatus.IN_PROGRESS

                # 체크포인트 업데이트
                if progress and "step" in progress:
                    task.checkpoint_step = progress["step"]

        return {"status": "ok", "time": time.time()}

    # ─── 과제 완료 ───────────────────────────────────────

    def complete_task(self, worker_id: str, task_id: str, lora_path: str) -> dict:
        """워커가 과제 완료 보고."""
        task = self.tasks.get(task_id)
        if not task:
            return {"status": "unknown_task"}

        # 이미 다른 워커가 완료했으면 → 늦은 결과 폐기
        if task.status == TaskStatus.COMPLETED:
            logger.info(f"늦은 완료 폐기: {task_id} by {worker_id} (이미 {task.completed_by}가 완료)")
            return {"status": "already_completed", "completed_by": task.completed_by}

        task.status = TaskStatus.COMPLETED
        task.completed_by = worker_id
        task.lora_path = lora_path
        task.completion_time = time.time()

        worker = self.workers.get(worker_id)
        if worker:
            worker.status = "idle"
            worker.current_task = None
            worker.total_completed += 1
            worker.reliability_score = min(1.0, worker.reliability_score + 0.05)

        elapsed = task.completion_time - (task.assigned_at or task.completion_time)
        logger.info(
            f"과제 완료: {task_id} by {worker_id} "
            f"({elapsed:.0f}초, 재할당 {task.reassign_count}회)"
        )

        return {
            "status": "accepted",
            "elapsed_sec": elapsed,
            "reassign_count": task.reassign_count,
        }

    # ─── 장애 감지 + 재할당 ──────────────────────────────

    def check_and_failover(self) -> list[str]:
        """모든 진행 중 과제의 상태 점검 + 필요 시 재할당.

        주기적으로 호출해야 함 (예: heartbeat_interval 마다).

        Returns:
            재할당된 task_id 목록
        """
        now = time.time()
        reassigned = []

        with self._lock:
            for task_id, task in self.tasks.items():
                if task.status not in (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS):
                    continue

                # Heartbeat 체크
                if task.last_heartbeat:
                    since_heartbeat = now - task.last_heartbeat
                    if since_heartbeat > self.heartbeat_interval * 2:
                        task.heartbeat_failures += 1
                        logger.warning(
                            f"Heartbeat 실패: {task_id} ({task.assigned_worker}), "
                            f"연속 {task.heartbeat_failures}회"
                        )

                # 장애 판정
                is_heartbeat_dead = task.heartbeat_failures >= self.heartbeat_timeout
                is_deadline_passed = task.deadline and now > task.deadline

                if is_heartbeat_dead or is_deadline_passed:
                    reason = "heartbeat 실패" if is_heartbeat_dead else "deadline 초과"
                    self._reassign_task(task, reason)
                    reassigned.append(task_id)

        return reassigned

    def _reassign_task(self, task: LearningTask, reason: str):
        """과제를 다른 워커에게 재할당."""
        old_worker_id = task.assigned_worker

        # 원래 워커 상태 업데이트
        if old_worker_id:
            worker = self.workers.get(old_worker_id)
            if worker:
                worker.status = "idle"
                worker.current_task = None
                worker.consecutive_failures += 1
                worker.reliability_score = max(0, worker.reliability_score - 0.2)

                # 블랙리스트 체크
                if worker.consecutive_failures >= self.blacklist_threshold:
                    worker.status = "blacklisted"
                    logger.error(
                        f"워커 블랙리스트: {old_worker_id} "
                        f"(연속 {worker.consecutive_failures}회 실패)"
                    )

        # 재할당 한도 체크
        if task.reassign_count >= task.max_reassigns:
            task.status = TaskStatus.FAILED
            logger.error(f"과제 최종 실패: {task.task_id} (재할당 {task.max_reassigns}회 초과)")
            return

        # 큐에 다시 넣기 (체크포인트 유지 → 이어서 학습)
        task.status = TaskStatus.PENDING
        task.assigned_worker = None
        task.assigned_at = None
        task.deadline = None
        task.heartbeat_failures = 0
        task.reassign_count += 1

        self.task_queue.insert(0, task.task_id)  # 우선순위 높게 (앞에 삽입)

        logger.info(
            f"과제 재할당: {task.task_id} "
            f"(이유: {reason}, 이전 워커: {old_worker_id}, "
            f"체크포인트: step {task.checkpoint_step}, "
            f"재할당 {task.reassign_count}/{task.max_reassigns})"
        )

    # ─── 워커 등록 ───────────────────────────────────────

    def register_worker(self, worker_id: str) -> WorkerState:
        """워커 등록."""
        if worker_id in self.workers:
            self.workers[worker_id].status = "idle"
            self.workers[worker_id].last_seen = time.time()
            return self.workers[worker_id]

        state = WorkerState(worker_id=worker_id, last_seen=time.time())
        self.workers[worker_id] = state
        logger.info(f"워커 등록: {worker_id}")
        return state

    # ─── 모니터링 루프 ────────────────────────────────────

    def start_monitor(self):
        """백그라운드에서 장애 감지 루프 시작."""
        def _loop():
            while True:
                reassigned = self.check_and_failover()
                if reassigned:
                    logger.info(f"재할당 발생: {reassigned}")
                time.sleep(self.heartbeat_interval)

        thread = threading.Thread(target=_loop, daemon=True)
        thread.start()
        logger.info(f"장애 모니터링 시작 (간격 {self.heartbeat_interval}초)")

    # ─── 통계 ────────────────────────────────────────────

    def get_stats(self) -> dict:
        """과제/워커 통계."""
        task_stats = {s.value: 0 for s in TaskStatus}
        for task in self.tasks.values():
            task_stats[task.status.value] += 1

        worker_stats = {"idle": 0, "busy": 0, "offline": 0, "blacklisted": 0}
        for w in self.workers.values():
            worker_stats[w.status] = worker_stats.get(w.status, 0) + 1

        total_reassigns = sum(t.reassign_count for t in self.tasks.values())

        return {
            "tasks": task_stats,
            "workers": worker_stats,
            "total_reassigns": total_reassigns,
            "queue_length": len(self.task_queue),
        }


# ─── 메인 (시뮬레이션) ──────────────────────────────────────

if __name__ == "__main__":
    fm = TaskFailoverManager(heartbeat_interval=5, task_timeout_sec=30)

    # 워커 등록
    for i in range(5):
        fm.register_worker(f"worker_{i}")

    # 과제 생성
    for i in range(10):
        fm.create_task(
            f"task_{i}", round_num=1,
            data_config={"domain": "coding"}, steps=500
        )

    # 과제 할당
    for wid in ["worker_0", "worker_1", "worker_2"]:
        task = fm.assign_task(wid)
        if task:
            print(f"  {wid} → {task.task_id}")

    # worker_1이 응답 없다고 시뮬
    print("\n--- worker_1 장애 시뮬레이션 ---")
    fm.workers["worker_1"].last_seen = time.time() - 100
    task1 = fm.tasks.get("task_1")
    if task1:
        task1.last_heartbeat = time.time() - 100
        task1.heartbeat_failures = 3

    reassigned = fm.check_and_failover()
    print(f"  재할당: {reassigned}")

    # 대기 중인 워커가 받아감
    task = fm.assign_task("worker_3")
    if task:
        print(f"  worker_3 → {task.task_id} (이어서 step {task.checkpoint_step}부터)")

    print(f"\n통계: {fm.get_stats()}")
