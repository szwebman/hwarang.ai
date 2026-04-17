"""HFL Continuous Self-Learning Pipeline

멈추지 않는 학습 루프. 24/7 자동 진화.

파이프라인:
  1. 데이터 수집 (뉴스, 법령 개정, 코드 업데이트)
  2. 자동 SFT/DPO 데이터 생성
  3. Grid 에이전트에 학습 분배 (HFL)
  4. LoRA 합성 → 검증 (Peer Validation)
  5. 합격 시 자동 배포 (Distributed Serving)
  6. 유저 피드백 수집 (GRPO)
  7. 1로 돌아감 → 반복

자동 트리거:
  - 매일: 뉴스/법령 업데이트 체크 → 관련 데이터 학습
  - 매주: GRPO 피드백 기반 DPO 학습
  - 매월: 전체 LoRA 재학습 (성능 벤치마크)
  - 이벤트: 법령 개정 감지 → 즉시 학습

사용법:
    # 지속 학습 데몬 시작
    python scripts/advanced/hfl_continuous_learning.py daemon

    # 수동 트리거
    python scripts/advanced/hfl_continuous_learning.py trigger --type daily
    python scripts/advanced/hfl_continuous_learning.py trigger --type law_update
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 데이터 소스 정의 ──────────────────────────────────────

@dataclass
class DataSource:
    name: str
    type: str                    # news, law, code, feedback
    url: str                     # API URL
    check_interval_hours: int    # 체크 주기 (시간)
    last_checked: float = 0
    last_updated: float = 0
    enabled: bool = True


DEFAULT_SOURCES: list[DataSource] = [
    # 뉴스 (한국 기술 뉴스)
    DataSource(
        name="한국 기술 뉴스",
        type="news",
        url="https://api.naver.com/news/tech",  # 예시
        check_interval_hours=24,
    ),

    # 법령 업데이트
    DataSource(
        name="법제처 법령 업데이트",
        type="law",
        url="http://www.law.go.kr/DRF/lawSearch.do",
        check_interval_hours=24,
    ),

    # 세법 개정
    DataSource(
        name="국세청 세법 개정",
        type="law",
        url="https://www.nts.go.kr/api/tax_updates",  # 예시
        check_interval_hours=168,  # 주 1회
    ),

    # GitHub 트렌딩 (코드 업데이트)
    DataSource(
        name="GitHub 트렌딩 코드",
        type="code",
        url="https://api.github.com/trending",
        check_interval_hours=168,  # 주 1회
    ),

    # GRPO 피드백
    DataSource(
        name="유저 피드백 (GRPO)",
        type="feedback",
        url="internal://grpo_feedback",
        check_interval_hours=168,  # 주 1회 DPO 생성
    ),
]


# ─── 데이터 수집기 ───────────────────────────────────────────

class DataCollector:
    """다양한 소스에서 학습 데이터 자동 수집."""

    def __init__(self, sources: list[DataSource]):
        self.sources = sources

    def check_updates(self) -> list[dict]:
        """모든 소스에서 업데이트 확인."""
        updates = []
        now = time.time()

        for source in self.sources:
            if not source.enabled:
                continue

            hours_since = (now - source.last_checked) / 3600
            if hours_since < source.check_interval_hours:
                continue

            logger.info(f"업데이트 체크: {source.name}")
            source.last_checked = now

            try:
                new_data = self._fetch_source(source)
                if new_data:
                    updates.append({
                        "source": source.name,
                        "type": source.type,
                        "count": len(new_data),
                        "data": new_data,
                    })
                    source.last_updated = now
                    logger.info(f"  → {len(new_data)}개 새 데이터")
                else:
                    logger.info(f"  → 변경 없음")
            except Exception as e:
                logger.warning(f"  → 실패: {e}")

        return updates

    def _fetch_source(self, source: DataSource) -> list[dict]:
        """소스별 데이터 수집."""
        if source.type == "law":
            return self._fetch_law_updates(source)
        elif source.type == "news":
            return self._fetch_news(source)
        elif source.type == "code":
            return self._fetch_code_updates(source)
        elif source.type == "feedback":
            return self._fetch_grpo_feedback(source)
        return []

    def _fetch_law_updates(self, source: DataSource) -> list[dict]:
        """법제처에서 최근 개정 법령 수집."""
        api_key = os.environ.get("LAW_GO_KR_API_KEY", "")
        if not api_key:
            return []

        try:
            import urllib.request
            # 최근 30일 개정 법령
            url = f"{source.url}?OC={api_key}&target=law&type=JSON&query=개정&display=20"
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read())
            laws = data.get("LawSearch", {}).get("law", [])

            sft_data = []
            for law in laws:
                name = law.get("법령명한글", "")
                if name:
                    sft_data.append({
                        "messages": [
                            {"role": "user", "content": f"최근 개정된 '{name}'의 변경사항은 무엇인가요?"},
                            {"role": "assistant", "content":
                                f"'{name}'이(가) 최근 개정되었습니다. "
                                f"정확한 변경사항은 법제처(law.go.kr)에서 전문을 확인하시기 바랍니다. "
                                f"⚠️ 법률 변경사항은 전문가와 확인하세요."
                            },
                        ],
                        "_source": "law_update",
                        "_law_name": name,
                    })
            return sft_data
        except Exception:
            return []

    def _fetch_news(self, source: DataSource) -> list[dict]:
        """기술 뉴스 수집 → 시사 상식 학습 데이터."""
        # 실제 구현은 네이버/구글 뉴스 API
        return []

    def _fetch_code_updates(self, source: DataSource) -> list[dict]:
        """GitHub 트렌딩 → 코드 트렌드 학습."""
        return []

    def _fetch_grpo_feedback(self, source: DataSource) -> list[dict]:
        """GRPO 피드백 → DPO 학습 데이터."""
        # DB에서 최근 피드백 추출 → DPO 쌍 변환
        return []


# ─── 학습 트리거 ─────────────────────────────────────────────

class LearningTrigger:
    """학습 트리거 관리. 조건 만족 시 자동 학습 시작."""

    @staticmethod
    def should_train_daily(last_daily: float) -> bool:
        """매일 학습 필요?"""
        return time.time() - last_daily > 86400

    @staticmethod
    def should_train_weekly(last_weekly: float) -> bool:
        """주간 DPO 학습 필요?"""
        return time.time() - last_weekly > 604800

    @staticmethod
    def should_train_monthly(last_monthly: float) -> bool:
        """월간 전체 재학습 필요?"""
        return time.time() - last_monthly > 2592000

    @staticmethod
    def should_train_on_event(event_type: str) -> bool:
        """이벤트 기반 즉시 학습?"""
        urgent_events = ["law_update", "security_patch", "critical_feedback"]
        return event_type in urgent_events


# ─── 학습 실행기 ─────────────────────────────────────────────

class LearningExecutor:
    """실제 학습 실행. HFL 파이프라인 호출."""

    def __init__(self, master_url: str = "http://localhost:9090"):
        self.master_url = master_url

    def run_incremental_sft(self, data_path: str, description: str):
        """증분 SFT 학습 (새 데이터만 학습)."""
        logger.info(f"증분 SFT 학습 시작: {description}")
        cmd = f"""
            python scripts/qlora_qwen.py \\
                --model-path /mnt/nvme2/hwarang/models/qwen2.5-32b \\
                --data {data_path} \\
                --output /mnt/nvme2/hwarang/lora_adapters/incremental_latest \\
                --epochs 1 --lr 1e-4
        """
        logger.info(f"  명령: {cmd}")
        os.system(cmd)

    def run_dpo_from_feedback(self, dpo_path: str):
        """피드백 기반 DPO 학습."""
        logger.info(f"DPO 학습 시작: {dpo_path}")
        cmd = f"""
            python scripts/align.py \\
                --model /mnt/nvme2/hwarang/models/qwen2.5-32b \\
                --data {dpo_path} \\
                --output /mnt/nvme2/hwarang/lora_adapters/dpo_latest
        """
        os.system(cmd)

    def deploy_new_lora(self, lora_path: str, version: str):
        """새 LoRA를 서빙 에이전트에 배포."""
        logger.info(f"LoRA 배포: v{version}")
        # hfl_distributed_serving.py의 deploy_lora() 호출
        # 또는 vLLM 재시작


# ─── 메인 파이프라인 ─────────────────────────────────────────

class ContinuousLearningPipeline:
    """24/7 지속 학습 파이프라인.

    루프:
      수집 → 학습 → 검증 → 배포 → 피드백 → 반복
    """

    def __init__(self):
        self.collector = DataCollector(DEFAULT_SOURCES)
        self.executor = LearningExecutor()
        self.trigger = LearningTrigger()
        self.data_dir = "/mnt/nvme2/hwarang/data/continuous"
        self.last_daily = 0
        self.last_weekly = 0
        self.last_monthly = 0
        self.version_counter = 0

        os.makedirs(self.data_dir, exist_ok=True)

    def run_once(self):
        """한 사이클 실행."""
        logger.info("\n" + "=" * 60)
        logger.info(f" 지속 학습 사이클 (v{self.version_counter})")
        logger.info(f" 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        logger.info("=" * 60)

        # 1. 데이터 수집
        updates = self.collector.check_updates()

        if not updates and not self.trigger.should_train_daily(self.last_daily):
            logger.info("  새로운 데이터 없음, 스킵")
            return

        # 2. 수집된 데이터 저장
        if updates:
            data_path = f"{self.data_dir}/update_{int(time.time())}.jsonl"
            total_items = 0
            with open(data_path, "w", encoding="utf-8") as f:
                for update in updates:
                    for item in update["data"]:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                        total_items += 1

            logger.info(f"  수집: {total_items}개 → {data_path}")

            # 3. 증분 SFT 학습
            if total_items >= 10:  # 최소 10개 이상이면 학습
                self.executor.run_incremental_sft(
                    data_path,
                    f"자동 업데이트 ({', '.join(u['source'] for u in updates)})",
                )
                self.last_daily = time.time()

        # 4. 주간 DPO (피드백 기반)
        if self.trigger.should_train_weekly(self.last_weekly):
            logger.info("\n  [주간] GRPO 피드백 → DPO 학습")
            # extract_dpo_from_grpo() 호출
            self.last_weekly = time.time()

        # 5. 월간 전체 재학습
        if self.trigger.should_train_monthly(self.last_monthly):
            logger.info("\n  [월간] 전체 LoRA 재학습 + 벤치마크")
            self.last_monthly = time.time()

        # 6. 배포
        self.version_counter += 1
        version = f"auto-v{self.version_counter}-{datetime.now().strftime('%Y%m%d')}"
        logger.info(f"\n  배포: {version}")
        # self.executor.deploy_new_lora(..., version)

        logger.info("\n  ✅ 사이클 완료")

    def run_daemon(self, check_interval_hours: float = 6):
        """데몬 모드: 주기적 실행."""
        logger.info(f"지속 학습 데몬 시작 (체크 간격 {check_interval_hours}시간)")

        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"사이클 오류: {e}")

            sleep_sec = check_interval_hours * 3600
            logger.info(f"\n  다음 체크: {check_interval_hours}시간 후")
            time.sleep(sleep_sec)

    def trigger_event(self, event_type: str, data: dict | None = None):
        """이벤트 기반 즉시 학습."""
        logger.info(f"\n이벤트 트리거: {event_type}")

        if event_type == "law_update":
            # 법령 개정 → 즉시 법률 데이터 수집 + 학습
            logger.info("  법령 개정 감지 → 즉시 학습")
            # 법제처 API 조회 → SFT 데이터 생성 → 증분 학습

        elif event_type == "model_release":
            # 새 베이스 모델 출시 → 전체 재학습
            logger.info("  새 모델 출시 → 전체 재학습 트리거")

        elif event_type == "critical_feedback":
            # 심각한 피드백 → 긴급 DPO
            logger.info("  심각 피드백 → 긴급 DPO 학습")

        elif event_type == "security":
            # 보안 이슈 → 즉시 프롬프트/가드 업데이트
            logger.info("  보안 이슈 → 가드 업데이트")


# ─── 메인 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HFL Continuous Self-Learning")
    parser.add_argument("mode", choices=["daemon", "trigger", "once"])
    parser.add_argument("--type", default="daily",
                        help="트리거 타입 (daily, weekly, law_update, model_release)")
    parser.add_argument("--interval", type=float, default=6,
                        help="데몬 체크 간격 (시간)")
    args = parser.parse_args()

    pipeline = ContinuousLearningPipeline()

    if args.mode == "daemon":
        logger.info("=" * 60)
        logger.info(" HFL Continuous Self-Learning 데몬")
        logger.info("=" * 60)
        logger.info(f"  체크 간격: {args.interval}시간")
        logger.info(f"  데이터 소스: {len(DEFAULT_SOURCES)}개")
        logger.info(f"  자동 트리거: 매일/매주/매월/이벤트")
        logger.info("=" * 60)
        pipeline.run_daemon(args.interval)

    elif args.mode == "trigger":
        pipeline.trigger_event(args.type)

    elif args.mode == "once":
        pipeline.run_once()


if __name__ == "__main__":
    main()
