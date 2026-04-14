#!/usr/bin/env python3
"""
Hwarang 학습용 데이터 통합 다운로더.

공개된 고품질 데이터셋만 사용해서 7B 학습용 데이터셋을 구성합니다.
크롤링 없이도 충분한 데이터를 확보할 수 있습니다.

구성:
- Stage 1: 한국어 대규모 (Pretrain) - mC4, CulturaX, 위키, 나무위키
- Stage 2: 코드 (Pretrain) - StarCoderData (한국 관련 + Python/JS/TS)
- Stage 3: 명령어/대화 (SFT) - KoAlpaca, KO-OpenOrca, KoVicuna, SlimOrca
- Stage 4: 도메인 (옵션) - 법률, 세무 (공개 API)

사용법:
    # 전체 다운로드 (~150GB, 1~2일)
    python scripts/data/download_all.py --stage all

    # 단계별 다운로드
    python scripts/data/download_all.py --stage pretrain-ko
    python scripts/data/download_all.py --stage pretrain-code
    python scripts/data/download_all.py --stage sft
    python scripts/data/download_all.py --stage domain

    # 빠른 테스트 (소량)
    python scripts/data/download_all.py --stage all --max-samples 1000

필요 패키지:
    pip install datasets huggingface_hub tqdm
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# 데이터셋 정의
# ============================================================

# Stage 1: 한국어 Pretrain (대규모 텍스트) - 가능한 모든 한국어 소스 포함
KOREAN_PRETRAIN_DATASETS = [
    # ===== 위키피디아 계열 =====
    {
        "name": "korean_wiki",
        "hf_repo": "graelo/wikipedia",
        "config": "20230601.ko",
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 1.0,
        "min_length": 100,
        "description": "한국어 위키피디아 (전체)",
    },
    {
        "name": "wikipedia_ko_latest",
        "hf_repo": "wikimedia/wikipedia",
        "config": "20231101.ko",
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 1.2,
        "min_length": 100,
        "description": "한국어 위키피디아 (최신)",
    },

    # ===== 나무위키 =====
    {
        "name": "namuwiki_extracted",
        "hf_repo": "heegyu/namuwiki-extracted",
        "config": None,
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 5.0,
        "min_length": 100,
        "description": "나무위키 정제본",
    },
    {
        "name": "namuwiki_psymon",
        "hf_repo": "psymon/namuwiki_20210301",
        "config": None,
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 4.0,
        "min_length": 100,
        "description": "나무위키 2021년 덤프",
    },

    # ===== 정제된 위키 텍스트 =====
    {
        "name": "kowiki_text",
        "hf_repo": "heegyu/kowikitext",
        "config": None,
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 0.5,
        "min_length": 100,
        "description": "한국어 위키 정제본",
    },

    # ===== 뉴스 =====
    {
        "name": "klue_news",
        "hf_repo": "klue/klue",
        "config": "mrc",
        "split": "train",
        "text_field": "context",
        "size_estimate_gb": 0.1,
        "min_length": 100,
        "description": "KLUE 뉴스 본문",
    },
    {
        "name": "ko_news_corpus",
        "hf_repo": "daekeun-ml/naver-news-summarization-ko",
        "config": None,
        "split": "train",
        "text_field": "document",
        "size_estimate_gb": 0.5,
        "min_length": 100,
        "description": "네이버 뉴스 요약 데이터",
    },

    # ===== 대규모 웹 코퍼스 =====
    {
        "name": "culturax_ko",
        "hf_repo": "uonlp/CulturaX",
        "config": "ko",
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 100.0,
        "min_length": 200,
        "streaming": True,
        "max_samples_default": 10_000_000,
        "description": "CulturaX 한국어 (대규모 정제 웹)",
    },
    {
        "name": "mc4_ko",
        "hf_repo": "mc4",
        "config": "ko",
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 200.0,
        "min_length": 200,
        "streaming": True,
        "max_samples_default": 5_000_000,
        "description": "mC4 한국어 (Common Crawl 다국어)",
    },
    {
        "name": "oscar_ko_2301",
        "hf_repo": "oscar-corpus/OSCAR-2301",
        "config": "ko",
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 80.0,
        "min_length": 200,
        "streaming": True,
        "max_samples_default": 3_000_000,
        "description": "OSCAR 2023 한국어",
        "requires_auth": True,
    },
    {
        "name": "oscar_ko_2201",
        "hf_repo": "oscar-corpus/OSCAR-2201",
        "config": "ko",
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 60.0,
        "min_length": 200,
        "streaming": True,
        "max_samples_default": 2_000_000,
        "description": "OSCAR 2022 한국어",
        "requires_auth": True,
    },
    {
        "name": "fineweb2_ko",
        "hf_repo": "HuggingFaceFW/fineweb-2",
        "config": "kor_Hang",
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 150.0,
        "min_length": 200,
        "streaming": True,
        "max_samples_default": 5_000_000,
        "description": "FineWeb-2 한국어 (최신 고품질)",
    },

    # ===== 한국어 도서/문학 =====
    {
        "name": "korean_textbooks",
        "hf_repo": "maywell/korean_textbooks",
        "config": None,
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 2.0,
        "min_length": 100,
        "description": "한국어 교재/문학 합성 데이터",
    },

    # ===== 한국어 종합 코퍼스 =====
    {
        "name": "korean_pretrain_pack",
        "hf_repo": "HAERAE-HUB/Korean-Pretrain-Pack",
        "config": None,
        "split": "train",
        "text_field": "text",
        "size_estimate_gb": 30.0,
        "min_length": 100,
        "streaming": True,
        "max_samples_default": 2_000_000,
        "description": "HAERAE Korean Pretrain Pack",
    },
    {
        "name": "kowiki_madlad",
        "hf_repo": "allenai/MADLAD-400",
        "config": "ko",
        "split": "clean",
        "text_field": "text",
        "size_estimate_gb": 50.0,
        "min_length": 200,
        "streaming": True,
        "max_samples_default": 2_000_000,
        "description": "MADLAD-400 한국어 (Google)",
    },

    # ===== 한국어 Q&A 텍스트 =====
    {
        "name": "korquad_v2",
        "hf_repo": "KETI-AIR/korquad",
        "config": "v2.1",
        "split": "train",
        "text_field": "context",
        "size_estimate_gb": 0.5,
        "min_length": 100,
        "description": "KorQuAD v2 (한국어 위키 기반 QA)",
    },

    # ===== 한국어 청년/공식 문서 =====
    {
        "name": "ko_legal_corpus",
        "hf_repo": "lawcompany/KLAID",
        "config": None,
        "split": "train",
        "text_field": "fact",
        "size_estimate_gb": 0.5,
        "min_length": 100,
        "description": "한국 법률 문서 (KLAID)",
    },
]

# Stage 2: 코드 Pretrain
CODE_PRETRAIN_DATASETS = [
    {
        "name": "starcoder_python",
        "hf_repo": "bigcode/starcoderdata",
        "config": "python",
        "split": "train",
        "text_field": "content",
        "size_estimate_gb": 50.0,
        "min_length": 100,
        "streaming": True,
        "max_samples_default": 1_000_000,
        "description": "StarCoder Python 코드",
    },
    {
        "name": "starcoder_js",
        "hf_repo": "bigcode/starcoderdata",
        "config": "javascript",
        "split": "train",
        "text_field": "content",
        "size_estimate_gb": 30.0,
        "streaming": True,
        "max_samples_default": 500_000,
        "description": "StarCoder JavaScript",
    },
    {
        "name": "starcoder_ts",
        "hf_repo": "bigcode/starcoderdata",
        "config": "typescript",
        "split": "train",
        "text_field": "content",
        "size_estimate_gb": 20.0,
        "streaming": True,
        "max_samples_default": 500_000,
        "description": "StarCoder TypeScript",
    },
    {
        "name": "codeparrot_clean",
        "hf_repo": "codeparrot/codeparrot-clean",
        "config": None,
        "split": "train",
        "text_field": "content",
        "size_estimate_gb": 30.0,
        "streaming": True,
        "max_samples_default": 500_000,
        "description": "CodeParrot 정제 Python",
    },
    {
        "name": "code_search_net",
        "hf_repo": "code_search_net",
        "config": "python",
        "split": "train",
        "text_field": "func_code_string",
        "size_estimate_gb": 2.0,
        "description": "함수 + 자연어 설명 페어",
    },
]

# Stage 3: SFT 데이터 (명령어/대화) - 한국어 우선, 모든 가용 데이터셋
SFT_DATASETS = [
    # ===== 한국어 명령어 데이터 =====
    {
        "name": "ko_alpaca",
        "hf_repo": "beomi/KoAlpaca-v1.1a",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 50,
        "description": "KoAlpaca v1.1 한국어 지시",
    },
    {
        "name": "ko_alpaca_v1",
        "hf_repo": "beomi/KoAlpaca-v1.0",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 30,
        "description": "KoAlpaca v1.0",
    },
    {
        "name": "ko_openorca",
        "hf_repo": "kyujinpy/KOR-OpenOrca-Platypus-v3",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 200,
        "description": "한국어 OpenOrca + Platypus",
    },
    {
        "name": "ko_orca_dpo",
        "hf_repo": "kyujinpy/orca_math_korean_preference",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 50,
        "description": "한국어 Orca 수학 (선호도 데이터)",
    },
    {
        "name": "ko_evolve_instruct",
        "hf_repo": "lcw99/evolve-instruct",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 100,
        "description": "한국어 Evolve Instruct",
    },
    {
        "name": "ko_platypus",
        "hf_repo": "kyujinpy/KOpen-platypus",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 80,
        "description": "한국어 Open-Platypus (추론)",
    },

    # ===== 한국어 대화 =====
    {
        "name": "ko_chatgpt_dialog",
        "hf_repo": "heegyu/ko-chatgpt-dialog",
        "split": "train",
        "format": "sharegpt",
        "size_estimate_mb": 30,
        "description": "한국어 ChatGPT 대화",
    },
    {
        "name": "ko_ultrafeedback",
        "hf_repo": "maywell/ko_Ultrafeedback_binarized",
        "split": "train",
        "format": "sharegpt",
        "size_estimate_mb": 100,
        "description": "한국어 UltraFeedback",
    },
    {
        "name": "ko_no_robots",
        "hf_repo": "maywell/ko_wikidata_QA",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 50,
        "description": "한국어 위키데이터 QA",
    },

    # ===== 한국어 안전성 =====
    {
        "name": "ko_safe_conversation",
        "hf_repo": "jojo0217/korean_safe_conversation",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 50,
        "description": "한국어 안전 대화",
    },

    # ===== 한국어 평가/추론 =====
    {
        "name": "kmmlu_cs",
        "hf_repo": "HAERAE-HUB/KMMLU",
        "config": "Computer-Science",
        "split": "train",
        "format": "qa",
        "size_estimate_mb": 5,
        "description": "KMMLU 컴퓨터 과학",
    },
    {
        "name": "kmmlu_law",
        "hf_repo": "HAERAE-HUB/KMMLU",
        "config": "Law",
        "split": "train",
        "format": "qa",
        "size_estimate_mb": 5,
        "description": "KMMLU 법률",
    },
    {
        "name": "kmmlu_accounting",
        "hf_repo": "HAERAE-HUB/KMMLU",
        "config": "Accounting",
        "split": "train",
        "format": "qa",
        "size_estimate_mb": 5,
        "description": "KMMLU 회계",
    },
    {
        "name": "kmmlu_taxation",
        "hf_repo": "HAERAE-HUB/KMMLU",
        "config": "Taxation",
        "split": "train",
        "format": "qa",
        "size_estimate_mb": 5,
        "description": "KMMLU 세무",
    },
    {
        "name": "ko_arc_challenge",
        "hf_repo": "HAERAE-HUB/HAE-RAE-BENCH",
        "split": "train",
        "format": "qa",
        "size_estimate_mb": 10,
        "description": "HAE-RAE 추론 벤치마크",
    },

    # ===== 한국어 코딩 =====
    {
        "name": "ko_code_alpaca",
        "hf_repo": "junelee/wizard_vicuna_70k",
        "split": "train",
        "format": "sharegpt",
        "size_estimate_mb": 100,
        "description": "WizardVicuna (한영 혼합)",
    },

    # ===== 영어 SFT (한국어 베이스 보강) =====
    {
        "name": "slim_orca",
        "hf_repo": "Open-Orca/SlimOrca",
        "split": "train",
        "format": "sharegpt",
        "streaming": True,
        "max_samples_default": 200_000,
        "size_estimate_mb": 500,
        "description": "SlimOrca (영어 GPT-4)",
    },
    {
        "name": "ultrachat_200k",
        "hf_repo": "HuggingFaceH4/ultrachat_200k",
        "split": "train_sft",
        "format": "sharegpt",
        "streaming": True,
        "max_samples_default": 100_000,
        "size_estimate_mb": 800,
        "description": "UltraChat 200K (영어 다중 턴)",
    },

    # ===== 코드 SFT (영어) =====
    {
        "name": "code_evol_instruct",
        "hf_repo": "nickrosh/Evol-Instruct-Code-80k-v1",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 200,
        "description": "EvolInstruct Code (80K)",
    },
    {
        "name": "magicoder_oss",
        "hf_repo": "ise-uiuc/Magicoder-OSS-Instruct-75K",
        "split": "train",
        "format": "magicoder",
        "size_estimate_mb": 200,
        "description": "Magicoder OSS (75K)",
    },
    {
        "name": "code_alpaca_20k",
        "hf_repo": "sahil2801/CodeAlpaca-20k",
        "split": "train",
        "format": "alpaca",
        "size_estimate_mb": 30,
        "description": "Code Alpaca 20K",
    },
    {
        "name": "glaive_code",
        "hf_repo": "glaiveai/glaive-code-assistant-v2",
        "split": "train",
        "format": "sharegpt",
        "streaming": True,
        "max_samples_default": 50_000,
        "size_estimate_mb": 300,
        "description": "Glaive Code Assistant",
    },
]

# Stage 4: 도메인 데이터 (DPO + 선호도)
DPO_DATASETS = [
    {
        "name": "ultrafeedback_ko",
        "hf_repo": "argilla/ultrafeedback-binarized-preferences-cleaned",
        "split": "train",
        "format": "dpo",
        "size_estimate_mb": 200,
        "description": "UltraFeedback 정제 (DPO)",
    },
    {
        "name": "hh_rlhf",
        "hf_repo": "Anthropic/hh-rlhf",
        "split": "train",
        "format": "hh",
        "size_estimate_mb": 500,
        "description": "Anthropic HH-RLHF (안전성)",
    },
]


# ============================================================
# 다운로더 클래스
# ============================================================

class DatasetDownloader:
    """공개 데이터셋 통합 다운로더."""

    def __init__(self, output_dir: Path, max_samples: int | None = None):
        self.output_dir = output_dir
        self.max_samples = max_samples
        self.stats = {
            "datasets_downloaded": 0,
            "total_samples": 0,
            "total_size_gb": 0.0,
            "failed": [],
        }

    def download_pretrain_korean(self):
        """한국어 Pretrain 데이터."""
        logger.info("=" * 60)
        logger.info("Stage 1: 한국어 Pretrain 데이터")
        logger.info("=" * 60)

        out_dir = self.output_dir / "pretrain" / "korean"
        out_dir.mkdir(parents=True, exist_ok=True)

        for ds in KOREAN_PRETRAIN_DATASETS:
            self._download_text_dataset(ds, out_dir)

    def download_pretrain_code(self):
        """코드 Pretrain 데이터."""
        logger.info("=" * 60)
        logger.info("Stage 2: 코드 Pretrain 데이터")
        logger.info("=" * 60)

        out_dir = self.output_dir / "pretrain" / "code"
        out_dir.mkdir(parents=True, exist_ok=True)

        for ds in CODE_PRETRAIN_DATASETS:
            self._download_text_dataset(ds, out_dir)

    def download_sft(self):
        """SFT 데이터."""
        logger.info("=" * 60)
        logger.info("Stage 3: SFT (명령어/대화) 데이터")
        logger.info("=" * 60)

        out_dir = self.output_dir / "sft"
        out_dir.mkdir(parents=True, exist_ok=True)

        for ds in SFT_DATASETS:
            self._download_sft_dataset(ds, out_dir)

    def download_dpo(self):
        """DPO 데이터."""
        logger.info("=" * 60)
        logger.info("Stage 4: DPO (선호도 정렬) 데이터")
        logger.info("=" * 60)

        out_dir = self.output_dir / "dpo"
        out_dir.mkdir(parents=True, exist_ok=True)

        for ds in DPO_DATASETS:
            self._download_dpo_dataset(ds, out_dir)

    def _download_text_dataset(self, ds: dict, out_dir: Path):
        """텍스트 데이터셋 다운로드."""
        try:
            from datasets import load_dataset
            from tqdm import tqdm
        except ImportError:
            logger.error("datasets, tqdm 패키지 필요")
            return

        out_file = out_dir / f"{ds['name']}.txt"
        if out_file.exists() and out_file.stat().st_size > 0:
            logger.info(f"  [{ds['name']}] 이미 존재: {out_file}")
            return

        logger.info(f"  [{ds['name']}] {ds['description']}")
        logger.info(f"    예상 크기: {ds['size_estimate_gb']:.1f}GB")

        try:
            kwargs = {
                "path": ds["hf_repo"],
                "split": ds["split"],
            }
            if ds.get("config"):
                kwargs["name"] = ds["config"]
            if ds.get("streaming", False):
                kwargs["streaming"] = True
            if ds.get("requires_auth"):
                logger.warning(f"    ⚠️  인증 필요. 'huggingface-cli login' 후 재시도")

            dataset = load_dataset(**kwargs)
        except Exception as e:
            logger.error(f"    실패: {e}")
            self.stats["failed"].append(ds["name"])
            return

        # 다운로드 + 저장
        max_samples = self.max_samples or ds.get("max_samples_default")
        text_field = ds.get("text_field", "text")
        min_length = ds.get("min_length", 50)

        count = 0
        with open(out_file, "w", encoding="utf-8") as f:
            iterator = dataset
            if max_samples:
                if hasattr(dataset, "take"):
                    iterator = dataset.take(max_samples)

            try:
                for row in tqdm(iterator, desc=f"    {ds['name']}",
                                total=max_samples):
                    text = row.get(text_field, "")
                    if isinstance(text, str) and len(text) >= min_length:
                        f.write(text + "\n\n")
                        count += 1
                        if max_samples and count >= max_samples:
                            break
            except Exception as e:
                logger.warning(f"    다운로드 중단: {e}")

        size_mb = out_file.stat().st_size / 1e6
        logger.info(f"    완료: {count:,}개, {size_mb:.1f}MB")

        self.stats["datasets_downloaded"] += 1
        self.stats["total_samples"] += count
        self.stats["total_size_gb"] += size_mb / 1024

    def _download_sft_dataset(self, ds: dict, out_dir: Path):
        """SFT 데이터셋 다운로드 + 변환."""
        try:
            from datasets import load_dataset
            from tqdm import tqdm
        except ImportError:
            return

        out_file = out_dir / f"{ds['name']}.jsonl"
        if out_file.exists() and out_file.stat().st_size > 0:
            logger.info(f"  [{ds['name']}] 이미 존재")
            return

        logger.info(f"  [{ds['name']}] {ds['description']}")

        try:
            kwargs = {"path": ds["hf_repo"], "split": ds["split"]}
            if ds.get("config"):
                kwargs["name"] = ds["config"]
            if ds.get("streaming", False):
                kwargs["streaming"] = True

            dataset = load_dataset(**kwargs)
        except Exception as e:
            logger.error(f"    실패: {e}")
            self.stats["failed"].append(ds["name"])
            return

        max_samples = self.max_samples or ds.get("max_samples_default")
        format_type = ds.get("format", "alpaca")

        count = 0
        with open(out_file, "w", encoding="utf-8") as f:
            try:
                for row in tqdm(dataset, desc=f"    {ds['name']}", total=max_samples):
                    converted = self._convert_to_messages(row, format_type)
                    if converted:
                        f.write(json.dumps({"messages": converted}, ensure_ascii=False) + "\n")
                        count += 1
                        if max_samples and count >= max_samples:
                            break
            except Exception as e:
                logger.warning(f"    중단: {e}")

        logger.info(f"    완료: {count:,}개")
        self.stats["datasets_downloaded"] += 1

    def _download_dpo_dataset(self, ds: dict, out_dir: Path):
        """DPO 데이터셋 다운로드."""
        try:
            from datasets import load_dataset
            from tqdm import tqdm
        except ImportError:
            return

        out_file = out_dir / f"{ds['name']}.jsonl"
        if out_file.exists():
            logger.info(f"  [{ds['name']}] 이미 존재")
            return

        logger.info(f"  [{ds['name']}] {ds['description']}")

        try:
            dataset = load_dataset(ds["hf_repo"], split=ds["split"])
        except Exception as e:
            logger.error(f"    실패: {e}")
            return

        format_type = ds.get("format", "dpo")
        count = 0
        max_samples = self.max_samples

        with open(out_file, "w", encoding="utf-8") as f:
            for row in tqdm(dataset, desc=f"    {ds['name']}"):
                example = self._convert_dpo(row, format_type)
                if example:
                    f.write(json.dumps(example, ensure_ascii=False) + "\n")
                    count += 1
                    if max_samples and count >= max_samples:
                        break

        logger.info(f"    완료: {count:,}개")

    def _convert_to_messages(self, row: dict, format_type: str) -> list | None:
        """다양한 SFT 포맷을 통일된 messages 형식으로 변환."""
        try:
            if format_type == "alpaca":
                instruction = row.get("instruction", "").strip()
                input_text = row.get("input", "").strip()
                output = row.get("output", "").strip()
                if not instruction or not output:
                    return None

                user_content = instruction
                if input_text:
                    user_content += f"\n\n{input_text}"

                return [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": output},
                ]

            elif format_type == "sharegpt":
                conversations = row.get("conversations", row.get("conversation", []))
                if not conversations:
                    return None

                role_map = {"human": "user", "gpt": "assistant",
                           "system": "system", "user": "user", "assistant": "assistant"}
                messages = []
                for turn in conversations:
                    from_key = turn.get("from", turn.get("role", ""))
                    value = turn.get("value", turn.get("content", ""))
                    role = role_map.get(from_key, from_key)
                    if role and value:
                        messages.append({"role": role, "content": value.strip()})

                return messages if len(messages) >= 2 else None

            elif format_type == "magicoder":
                problem = row.get("problem", "").strip()
                solution = row.get("solution", "").strip()
                if not problem or not solution:
                    return None
                return [
                    {"role": "user", "content": problem},
                    {"role": "assistant", "content": solution},
                ]

            elif format_type == "qa":
                question = row.get("question", row.get("Question", "")).strip()
                answer = row.get("answer", row.get("Answer", "")).strip()
                if not question or not answer:
                    return None
                return [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ]
        except Exception:
            return None

        return None

    def _convert_dpo(self, row: dict, format_type: str) -> dict | None:
        """DPO 데이터 변환."""
        try:
            if format_type == "dpo":
                prompt = row.get("prompt", "").strip()

                # chosen/rejected가 list of messages 형식
                chosen = row.get("chosen", "")
                rejected = row.get("rejected", "")

                if isinstance(chosen, list):
                    chosen = next((m["content"] for m in chosen
                                  if m.get("role") == "assistant"), "")
                if isinstance(rejected, list):
                    rejected = next((m["content"] for m in rejected
                                    if m.get("role") == "assistant"), "")

                if not prompt or not chosen or not rejected:
                    return None

                return {"prompt": prompt, "chosen": chosen, "rejected": rejected}

            elif format_type == "hh":
                # HH-RLHF: "Human: ... Assistant: ..."
                chosen = row.get("chosen", "").strip()
                rejected = row.get("rejected", "").strip()

                def parse(text):
                    parts = text.split("\n\nAssistant:")
                    if len(parts) >= 2:
                        return (parts[0].replace("Human: ", "", 1).strip(),
                                parts[-1].strip())
                    return "", ""

                prompt, chosen_resp = parse(chosen)
                _, rejected_resp = parse(rejected)

                if not prompt or not chosen_resp or not rejected_resp:
                    return None
                return {"prompt": prompt, "chosen": chosen_resp, "rejected": rejected_resp}
        except Exception:
            return None

        return None

    def print_summary(self):
        logger.info("=" * 60)
        logger.info("다운로드 완료!")
        logger.info(f"  데이터셋: {self.stats['datasets_downloaded']}개")
        logger.info(f"  총 샘플: {self.stats['total_samples']:,}개")
        logger.info(f"  총 크기: {self.stats['total_size_gb']:.2f}GB")
        if self.stats["failed"]:
            logger.warning(f"  실패: {', '.join(self.stats['failed'])}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Hwarang 학습 데이터 통합 다운로더",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 전체 다운로드 (~150GB, 1~2일)
  python scripts/data/download_all.py --stage all

  # 한국어만
  python scripts/data/download_all.py --stage pretrain-ko

  # 빠른 테스트
  python scripts/data/download_all.py --stage all --max-samples 1000
        """,
    )
    parser.add_argument(
        "--stage",
        choices=["all", "pretrain-ko", "pretrain-code", "sft", "dpo"],
        default="all",
    )
    parser.add_argument("--output", default="data", help="출력 디렉토리")
    parser.add_argument("--max-samples", type=int, default=None,
                       help="데이터셋당 최대 샘플 수 (테스트용)")
    args = parser.parse_args()

    # 패키지 확인
    try:
        import datasets
        import tqdm
    except ImportError:
        logger.error("필수 패키지: pip install datasets tqdm huggingface_hub")
        return

    downloader = DatasetDownloader(
        output_dir=Path(args.output),
        max_samples=args.max_samples,
    )

    if args.stage in ("all", "pretrain-ko"):
        downloader.download_pretrain_korean()
    if args.stage in ("all", "pretrain-code"):
        downloader.download_pretrain_code()
    if args.stage in ("all", "sft"):
        downloader.download_sft()
    if args.stage in ("all", "dpo"):
        downloader.download_dpo()

    downloader.print_summary()


if __name__ == "__main__":
    main()
