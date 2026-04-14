#!/usr/bin/env python3
"""
Hwarang 학습 데이터 다운로드 스크립트.

사용법:
    # 전체 데이터 다운로드
    python scripts/download_data.py --task all --output data/

    # Pretrain 데이터만 (한국어)
    python scripts/download_data.py --task pretrain --lang ko --output data/

    # 코드 데이터만 다운로드
    python scripts/download_data.py --task code --output data/

    # SFT 데이터만 (영어)
    python scripts/download_data.py --task sft --lang en --output data/

    # DPO 데이터만
    python scripts/download_data.py --task dpo --output data/

    # 최대 샘플 수 제한 (빠른 테스트용)
    python scripts/download_data.py --task pretrain --lang ko --max-samples 10000 --output data/

필요 패키지:
    pip install datasets tqdm
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def check_dependencies():
    """필수 패키지 확인."""
    try:
        import datasets
        import tqdm
    except ImportError:
        logger.error("필수 패키지가 없습니다. 다음을 실행하세요:")
        logger.error("  pip install datasets tqdm")
        sys.exit(1)


# ============================================================
# Pretrain 데이터 다운로드
# ============================================================

def download_pretrain_ko_namuwiki(output_dir: Path, max_samples: int | None = None):
    """나무위키 덤프 다운로드 (한국어 최대 텍스트 소스)."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("나무위키 데이터 다운로드 중...")
    out_file = output_dir / "ko_namuwiki.txt"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    max_samples = max_samples or 500_000

    try:
        ds = load_dataset("heegyu/namuwiki-extracted", split="train", streaming=True)
    except Exception:
        try:
            ds = load_dataset("psymon/namuwiki_20210301", split="train", streaming=True)
        except Exception as e:
            logger.warning(f"나무위키 다운로드 실패: {e}")
            return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="NamuWiki", total=max_samples):
            text = row.get("text", row.get("content", "")).strip()
            if not text or len(text) < 100:
                continue
            f.write(text + "\n\n")
            count += 1
            if count >= max_samples:
                break

    size_mb = out_file.stat().st_size / (1024 * 1024)
    logger.info(f"완료: {count:,}개 문서, {size_mb:.1f}MB → {out_file}")


def download_pretrain_ko_book(output_dir: Path, max_samples: int | None = None):
    """한국어 책/문학 데이터 다운로드."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("한국어 도서 데이터 다운로드 중...")
    out_file = output_dir / "ko_books.txt"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    try:
        ds = load_dataset("heegyu/kowikitext", split="train")
    except Exception as e:
        logger.warning(f"한국어 도서 데이터 실패: {e}")
        return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="Korean Books"):
            text = row.get("text", "").strip()
            if not text or len(text) < 100:
                continue
            f.write(text + "\n\n")
            count += 1
            if max_samples and count >= max_samples:
                break

    size_mb = out_file.stat().st_size / (1024 * 1024)
    logger.info(f"완료: {count:,}개, {size_mb:.1f}MB → {out_file}")


def download_pretrain_ko_cc(output_dir: Path, max_samples: int | None = None):
    """한국어 Common Crawl (mC4) 다운로드 - 가장 큰 한국어 데이터."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("한국어 mC4 (Common Crawl) 다운로드 중...")
    out_file = output_dir / "ko_mc4.txt"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    max_samples = max_samples or 1_000_000

    try:
        ds = load_dataset("mc4", "ko", split="train", streaming=True)
    except Exception:
        try:
            ds = load_dataset("allenai/c4", "ko", split="train", streaming=True)
        except Exception as e:
            logger.warning(f"mC4 한국어 다운로드 실패: {e}")
            return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="Korean mC4", total=max_samples):
            text = row.get("text", "").strip()
            if not text or len(text) < 200:
                continue
            f.write(text + "\n\n")
            count += 1
            if count >= max_samples:
                break

    size_mb = out_file.stat().st_size / (1024 * 1024)
    logger.info(f"완료: {count:,}개 문서, {size_mb:.1f}MB → {out_file}")


def download_sft_ko_openorca(output_dir: Path, max_samples: int | None = None):
    """한국어 OpenOrca 번역 데이터."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("한국어 OpenOrca 다운로드 중...")
    out_file = output_dir / "ko_openorca.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    max_samples = max_samples or 100_000

    try:
        ds = load_dataset("kyujinpy/KOR-OpenOrca-Platypus-v3", split="train", streaming=True)
    except Exception:
        try:
            ds = load_dataset("jojo0217/korean_safe_conversation", split="train", streaming=True)
        except Exception as e:
            logger.warning(f"한국어 OpenOrca 다운로드 실패: {e}")
            return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="KO-OpenOrca", total=max_samples):
            instruction = row.get("instruction", row.get("question", "")).strip()
            output_text = row.get("output", row.get("answer", "")).strip()

            if not instruction or not output_text:
                continue

            system = row.get("system", row.get("system_prompt", "")).strip()
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": instruction})
            messages.append({"role": "assistant", "content": output_text})

            f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
            count += 1
            if count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


def download_pretrain_ko(output_dir: Path, max_samples: int | None = None):
    """한국어 Wikipedia 다운로드."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("한국어 Wikipedia 다운로드 중...")
    out_file = output_dir / "ko_wiki.txt"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    ds = load_dataset("graelo/wikipedia", "20230601.ko", split="train")

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="Korean Wikipedia"):
            text = row["text"].strip()
            if len(text) < 100:
                continue
            f.write(text + "\n\n")
            count += 1
            if max_samples and count >= max_samples:
                break

    size_mb = out_file.stat().st_size / (1024 * 1024)
    logger.info(f"완료: {count:,}개 문서, {size_mb:.1f}MB → {out_file}")


def download_pretrain_en(output_dir: Path, max_samples: int | None = None):
    """영어 FineWeb 샘플 다운로드."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("영어 FineWeb 다운로드 중 (sample-10BT)...")
    out_file = output_dir / "en_fineweb.txt"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    max_samples = max_samples or 500_000
    ds = load_dataset(
        "HuggingFaceFW/fineweb",
        name="sample-10BT",
        split="train",
        streaming=True,
    )

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="English FineWeb", total=max_samples):
            text = row["text"].strip()
            if len(text) < 200:
                continue
            f.write(text + "\n\n")
            count += 1
            if count >= max_samples:
                break

    size_mb = out_file.stat().st_size / (1024 * 1024)
    logger.info(f"완료: {count:,}개 문서, {size_mb:.1f}MB → {out_file}")


def download_pretrain_ko_news(output_dir: Path, max_samples: int | None = None):
    """한국어 뉴스 데이터 (KLUE 기반) 다운로드."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("한국어 뉴스 데이터 다운로드 중 (KLUE-MRC)...")
    out_file = output_dir / "ko_news.txt"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    try:
        ds = load_dataset("klue/klue", "mrc", split="train")
    except Exception as e:
        logger.warning(f"KLUE 데이터 다운로드 실패: {e}")
        logger.info("건너뛰기: 한국어 뉴스 데이터")
        return

    seen = set()
    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="Korean News"):
            context = row.get("context", "").strip()
            if not context or len(context) < 100 or context in seen:
                continue
            seen.add(context)
            f.write(context + "\n\n")
            count += 1
            if max_samples and count >= max_samples:
                break

    size_mb = out_file.stat().st_size / (1024 * 1024)
    logger.info(f"완료: {count:,}개 문서, {size_mb:.1f}MB → {out_file}")


# ============================================================
# 코드 데이터 다운로드 (Pretrain + SFT)
# ============================================================

# 지원 언어 목록
CODE_LANGUAGES = [
    "python", "javascript", "typescript", "java", "c", "cpp", "csharp",
    "go", "rust", "ruby", "php", "swift", "kotlin", "scala",
    "shell", "sql", "html", "css", "r", "lua",
]


def download_code_pretrain(output_dir: Path, max_samples: int | None = None):
    """The Stack v2 코드 데이터 다운로드 (pretrain용).

    StarCoder 학습에 사용된 대규모 코드 데이터셋.
    언어별로 다운로드하여 균형 있는 코드 학습 데이터를 구성합니다.
    """
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("=" * 50)
    logger.info("코드 Pretrain 데이터 다운로드 (The Stack v2 sample)")
    logger.info(f"지원 언어: {len(CODE_LANGUAGES)}개")
    logger.info("=" * 50)

    out_file = output_dir / "code_pretrain.txt"
    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    # 언어별 샘플 수 (균형 분배)
    per_lang = (max_samples or 200_000) // len(CODE_LANGUAGES)
    total_count = 0

    with open(out_file, "w", encoding="utf-8") as f:
        for lang in CODE_LANGUAGES:
            logger.info(f"  [{lang}] 다운로드 중 (최대 {per_lang:,}개)...")
            count = 0

            try:
                ds = load_dataset(
                    "bigcode/the-stack-v2-train-smol-ids",
                    split="train",
                    streaming=True,
                )

                # the-stack-v2-train-smol-ids는 ID만 제공하므로
                # 대안으로 starcoderdata 사용
                ds = load_dataset(
                    "bigcode/starcoderdata",
                    data_dir=lang,
                    split="train",
                    streaming=True,
                )
            except Exception:
                try:
                    # Fallback: the-stack-smol
                    ds = load_dataset(
                        "bigcode/the-stack-smol",
                        data_dir=f"data/{lang}",
                        split="train",
                        streaming=True,
                    )
                except Exception as e:
                    logger.warning(f"  [{lang}] 다운로드 실패, 건너뜀: {e}")
                    continue

            for row in ds:
                content = row.get("content", "").strip()
                if not content or len(content) < 50 or len(content) > 50_000:
                    continue

                # 파일 헤더 추가 (언어 식별용)
                f.write(f"```{lang}\n{content}\n```\n\n")
                count += 1
                if count >= per_lang:
                    break

            total_count += count
            logger.info(f"  [{lang}] {count:,}개 완료")

    size_mb = out_file.stat().st_size / (1024 * 1024)
    logger.info(f"코드 Pretrain 완료: {total_count:,}개 파일, {size_mb:.1f}MB → {out_file}")


def download_code_github(output_dir: Path, max_samples: int | None = None):
    """GitHub 코드 데이터 (codeparrot) 다운로드.

    Python 중심의 깨끗한 코드 데이터셋.
    """
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("GitHub Python 코드 다운로드 중 (codeparrot/github-code)...")
    out_file = output_dir / "code_github_python.txt"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    max_samples = max_samples or 300_000

    try:
        ds = load_dataset(
            "codeparrot/github-code",
            languages=["Python"],
            licenses=["mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause"],
            split="train",
            streaming=True,
        )
    except Exception:
        try:
            # Fallback: codeparrot-clean
            ds = load_dataset(
                "codeparrot/codeparrot-clean",
                split="train",
                streaming=True,
            )
        except Exception as e:
            logger.warning(f"GitHub 코드 다운로드 실패: {e}")
            return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="GitHub Python", total=max_samples):
            code = row.get("code", row.get("content", "")).strip()
            if not code or len(code) < 100 or len(code) > 30_000:
                continue

            f.write(f"```python\n{code}\n```\n\n")
            count += 1
            if count >= max_samples:
                break

    size_mb = out_file.stat().st_size / (1024 * 1024)
    logger.info(f"완료: {count:,}개 파일, {size_mb:.1f}MB → {out_file}")


def download_code_sft_evol(output_dir: Path, max_samples: int | None = None):
    """EvolInstruct 코드 지시 데이터 다운로드.

    WizardCoder 학습에 사용된 고품질 코드 지시-응답 데이터.
    """
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("EvolInstruct 코드 지시 데이터 다운로드 중...")
    out_file = output_dir / "code_evol_instructions.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    try:
        ds = load_dataset("nickrosh/Evol-Instruct-Code-80k-v1", split="train")
    except Exception as e:
        logger.warning(f"EvolInstruct 다운로드 실패: {e}")
        return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="EvolInstruct-Code"):
            instruction = row.get("instruction", "").strip()
            output_text = row.get("output", "").strip()

            if not instruction or not output_text:
                continue

            example = {
                "messages": [
                    {"role": "user", "content": instruction},
                    {"role": "assistant", "content": output_text},
                ]
            }
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
            if max_samples and count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


def download_code_sft_magicoder(output_dir: Path, max_samples: int | None = None):
    """Magicoder OSS-Instruct 코드 데이터.

    실제 오픈소스 코드에서 영감을 받은 고품질 코딩 문제.
    """
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("Magicoder OSS-Instruct 다운로드 중...")
    out_file = output_dir / "code_magicoder.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    try:
        ds = load_dataset("ise-uiuc/Magicoder-OSS-Instruct-75K", split="train")
    except Exception as e:
        logger.warning(f"Magicoder 다운로드 실패: {e}")
        return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="Magicoder"):
            problem = row.get("problem", "").strip()
            solution = row.get("solution", "").strip()

            if not problem or not solution:
                continue

            example = {
                "messages": [
                    {"role": "user", "content": problem},
                    {"role": "assistant", "content": solution},
                ]
            }
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
            if max_samples and count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


def download_code_sft_glaive(output_dir: Path, max_samples: int | None = None):
    """Glaive 코드 어시스턴트 데이터.

    함수 호출 + 코드 생성 패턴이 포함된 대화형 코딩 데이터.
    """
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("Glaive Code Assistant 다운로드 중...")
    out_file = output_dir / "code_glaive.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    try:
        ds = load_dataset("glaiveai/glaive-code-assistant-v2", split="train")
    except Exception as e:
        logger.warning(f"Glaive 다운로드 실패: {e}")
        return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="Glaive-Code"):
            # Glaive 형식: system + conversation
            messages = []
            system = row.get("system", "").strip()
            if system:
                messages.append({"role": "system", "content": system})

            conversation = row.get("chat", row.get("conversation", "")).strip()
            if not conversation:
                continue

            # "USER: ... ASSISTANT: ..." 파싱
            parts = conversation.split("ASSISTANT:")
            for i, part in enumerate(parts):
                if i == 0:
                    user_text = part.replace("USER:", "").strip()
                    if user_text:
                        messages.append({"role": "user", "content": user_text})
                else:
                    sub_parts = part.split("USER:")
                    assistant_text = sub_parts[0].strip()
                    if assistant_text:
                        messages.append({"role": "assistant", "content": assistant_text})
                    if len(sub_parts) > 1:
                        user_text = sub_parts[1].strip()
                        if user_text:
                            messages.append({"role": "user", "content": user_text})

            if len(messages) >= 2:
                f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
                count += 1

            if max_samples and count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


def download_code_commits(output_dir: Path, max_samples: int | None = None):
    """CommitPackFT - 커밋 메시지 + 코드 변경 데이터.

    코드 수정/리팩토링 패턴 학습에 유용.
    """
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("CommitPackFT 코드 커밋 데이터 다운로드 중...")
    out_file = output_dir / "code_commits.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    max_samples = max_samples or 100_000

    try:
        ds = load_dataset(
            "bigcode/commitpackft",
            data_dir="python",
            split="train",
            streaming=True,
        )
    except Exception as e:
        logger.warning(f"CommitPackFT 다운로드 실패: {e}")
        return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="CommitPackFT", total=max_samples):
            old_content = row.get("old_contents", "").strip()
            new_content = row.get("new_contents", "").strip()
            message = row.get("message", row.get("subject", "")).strip()

            if not new_content or not message or len(new_content) > 20_000:
                continue

            # 코드 리뷰/수정 형태의 지시 데이터로 변환
            if old_content:
                user_msg = f"다음 코드를 수정해주세요. 변경 사항: {message}\n\n```python\n{old_content}\n```"
            else:
                user_msg = f"{message}\n\nPython으로 구현해주세요."

            example = {
                "messages": [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": f"```python\n{new_content}\n```"},
                ]
            }
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
            if count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


# ============================================================
# 디자인 데이터 다운로드 (UI/UX, CSS, 프론트엔드)
# ============================================================

def download_design_pretrain_css(output_dir: Path, max_samples: int | None = None):
    """CSS/SCSS/TailwindCSS 코드 데이터 (pretrain용).

    디자인 시스템, 컴포넌트 스타일링 패턴 학습.
    """
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("CSS/프론트엔드 코드 다운로드 중...")
    out_file = output_dir / "design_frontend_code.txt"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    max_samples = max_samples or 200_000
    frontend_langs = ["css", "html", "javascript", "typescript"]
    per_lang = max_samples // len(frontend_langs)
    total_count = 0

    with open(out_file, "w", encoding="utf-8") as f:
        for lang in frontend_langs:
            count = 0
            logger.info(f"  [{lang}] 다운로드 중...")

            try:
                ds = load_dataset(
                    "bigcode/starcoderdata",
                    data_dir=lang,
                    split="train",
                    streaming=True,
                )
            except Exception:
                try:
                    ds = load_dataset(
                        "bigcode/the-stack-smol",
                        data_dir=f"data/{lang}",
                        split="train",
                        streaming=True,
                    )
                except Exception as e:
                    logger.warning(f"  [{lang}] 건너뜀: {e}")
                    continue

            for row in ds:
                content = row.get("content", "").strip()
                if not content or len(content) < 50 or len(content) > 30_000:
                    continue

                # 프론트엔드 관련 파일만 필터링
                path = row.get("path", row.get("filename", "")).lower()
                is_design_related = any(kw in content.lower() for kw in [
                    "display:", "flex", "grid", "margin", "padding", "color:",
                    "background", "border-radius", "font-size", "animation",
                    "tailwind", "styled", "className", "sx=", "css-in-js",
                    "component", "button", "modal", "card", "layout", "nav",
                    "@media", "responsive", "dark-mode", "theme",
                ]) or any(ext in path for ext in [
                    ".css", ".scss", ".less", ".styled.", ".module.css",
                    ".tsx", ".jsx", ".vue", ".svelte",
                ])

                if not is_design_related and lang not in ("css", "html"):
                    continue

                f.write(f"```{lang}\n{content}\n```\n\n")
                count += 1
                if count >= per_lang:
                    break

            total_count += count
            logger.info(f"  [{lang}] {count:,}개 완료")

    size_mb = out_file.stat().st_size / (1024 * 1024)
    logger.info(f"프론트엔드/CSS 데이터 완료: {total_count:,}개, {size_mb:.1f}MB → {out_file}")


def download_design_sft_websight(output_dir: Path, max_samples: int | None = None):
    """WebSight - 스크린샷 설명 → HTML/CSS 코드 생성 데이터.

    웹 디자인을 설명하면 코드를 생성하는 능력 학습.
    """
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("WebSight 디자인→코드 데이터 다운로드 중...")
    out_file = output_dir / "design_websight.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    max_samples = max_samples or 50_000

    try:
        ds = load_dataset(
            "HuggingFaceM4/WebSight",
            split="train",
            streaming=True,
        )
    except Exception as e:
        logger.warning(f"WebSight 다운로드 실패: {e}")
        return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="WebSight", total=max_samples):
            text = row.get("text", "").strip()
            code = row.get("code", row.get("html", "")).strip()

            if not text or not code or len(code) < 100:
                continue

            example = {
                "messages": [
                    {"role": "user", "content": f"다음 웹 디자인을 HTML/CSS로 구현해주세요:\n\n{text}"},
                    {"role": "assistant", "content": f"```html\n{code}\n```"},
                ]
            }
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
            if count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


def download_design_sft_ui_components(output_dir: Path, max_samples: int | None = None):
    """UI 컴포넌트 생성 학습 데이터.

    직접 생성하는 합성 데이터: 다양한 UI 컴포넌트 요청 → React/TailwindCSS 코드.
    """
    logger.info("UI 컴포넌트 합성 데이터 생성 중...")
    out_file = output_dir / "design_ui_components.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    # UI 컴포넌트 템플릿 (요청 → 코드 쌍)
    components = [
        {
            "request": "반응형 네비게이션 바를 만들어주세요. 로고, 메뉴 항목, 모바일 햄버거 메뉴가 있어야 합니다.",
            "code": '''import { useState } from "react";

export function Navbar() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <nav className="bg-white shadow-sm border-b">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <span className="text-xl font-bold text-indigo-600">Logo</span>
          </div>

          {/* Desktop menu */}
          <div className="hidden md:flex items-center space-x-8">
            <a href="#" className="text-gray-700 hover:text-indigo-600 transition-colors">Home</a>
            <a href="#" className="text-gray-700 hover:text-indigo-600 transition-colors">About</a>
            <a href="#" className="text-gray-700 hover:text-indigo-600 transition-colors">Services</a>
            <a href="#" className="text-gray-700 hover:text-indigo-600 transition-colors">Contact</a>
            <button className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 transition-colors">
              Get Started
            </button>
          </div>

          {/* Mobile hamburger */}
          <div className="md:hidden flex items-center">
            <button onClick={() => setIsOpen(!isOpen)} className="p-2 rounded-lg hover:bg-gray-100">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {isOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        {isOpen && (
          <div className="md:hidden pb-4 space-y-2">
            <a href="#" className="block px-3 py-2 rounded-lg hover:bg-gray-100">Home</a>
            <a href="#" className="block px-3 py-2 rounded-lg hover:bg-gray-100">About</a>
            <a href="#" className="block px-3 py-2 rounded-lg hover:bg-gray-100">Services</a>
            <a href="#" className="block px-3 py-2 rounded-lg hover:bg-gray-100">Contact</a>
          </div>
        )}
      </div>
    </nav>
  );
}'''
        },
        {
            "request": "다크 모드를 지원하는 프라이싱 카드 3개를 만들어주세요. Free, Pro, Enterprise 플랜으로 구성하고 인기 플랜은 강조해주세요.",
            "code": '''export function PricingCards() {
  const plans = [
    {
      name: "Free",
      price: "$0",
      period: "forever",
      features: ["5 projects", "1GB storage", "Community support", "Basic analytics"],
      cta: "Get Started",
      popular: false,
    },
    {
      name: "Pro",
      price: "$19",
      period: "/month",
      features: ["Unlimited projects", "100GB storage", "Priority support", "Advanced analytics", "Custom domain", "API access"],
      cta: "Start Free Trial",
      popular: true,
    },
    {
      name: "Enterprise",
      price: "$99",
      period: "/month",
      features: ["Everything in Pro", "Unlimited storage", "24/7 support", "Custom integrations", "SSO & SAML", "Dedicated account manager"],
      cta: "Contact Sales",
      popular: false,
    },
  ];

  return (
    <div className="py-16 px-4">
      <div className="text-center mb-12">
        <h2 className="text-3xl font-bold text-gray-900 dark:text-white">Simple, transparent pricing</h2>
        <p className="mt-4 text-lg text-gray-600 dark:text-gray-400">Choose the plan that fits your needs</p>
      </div>

      <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-8">
        {plans.map((plan) => (
          <div
            key={plan.name}
            className={`relative rounded-2xl p-8 ${
              plan.popular
                ? "bg-indigo-600 text-white shadow-xl scale-105 z-10"
                : "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-sm"
            }`}
          >
            {plan.popular && (
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-yellow-400 text-yellow-900 text-xs font-bold px-3 py-1 rounded-full">
                Most Popular
              </span>
            )}

            <h3 className={`text-lg font-semibold ${plan.popular ? "text-white" : "text-gray-900 dark:text-white"}`}>
              {plan.name}
            </h3>
            <div className="mt-4 flex items-baseline">
              <span className="text-4xl font-bold">{plan.price}</span>
              <span className={`ml-1 text-sm ${plan.popular ? "text-indigo-200" : "text-gray-500 dark:text-gray-400"}`}>
                {plan.period}
              </span>
            </div>

            <ul className="mt-8 space-y-3">
              {plan.features.map((feature) => (
                <li key={feature} className="flex items-center gap-2 text-sm">
                  <svg className={`w-4 h-4 shrink-0 ${plan.popular ? "text-indigo-200" : "text-indigo-500"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                  {feature}
                </li>
              ))}
            </ul>

            <button
              className={`mt-8 w-full py-3 rounded-xl font-medium transition-all ${
                plan.popular
                  ? "bg-white text-indigo-600 hover:bg-gray-100"
                  : "bg-indigo-600 text-white hover:bg-indigo-700"
              }`}
            >
              {plan.cta}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}'''
        },
        {
            "request": "모던한 로그인 폼을 만들어주세요. 이메일/비밀번호 입력, 소셜 로그인 버튼 (Google, GitHub), Remember me 체크박스가 있어야 합니다.",
            "code": '''export function LoginForm() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center mx-auto mb-4">
            <span className="text-white text-xl font-bold">H</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Welcome back</h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Sign in to your account</p>
        </div>

        {/* Card */}
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg border border-gray-200 dark:border-gray-700 p-8">
          {/* Social login */}
          <div className="grid grid-cols-2 gap-3 mb-6">
            <button className="flex items-center justify-center gap-2 px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-sm font-medium text-gray-700 dark:text-gray-300">
              <svg className="w-5 h-5" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
              Google
            </button>
            <button className="flex items-center justify-center gap-2 px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-sm font-medium text-gray-700 dark:text-gray-300">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
              GitHub
            </button>
          </div>

          {/* Divider */}
          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200 dark:border-gray-700"></div>
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="px-2 bg-white dark:bg-gray-800 text-gray-500">or continue with email</span>
            </div>
          </div>

          {/* Form */}
          <form className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Email</label>
              <input
                type="email"
                placeholder="you@example.com"
                className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Password</label>
              <input
                type="password"
                placeholder="Enter your password"
                className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all text-sm"
              />
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                <input type="checkbox" className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
                Remember me
              </label>
              <a href="#" className="text-sm text-indigo-600 hover:text-indigo-500">Forgot password?</a>
            </div>

            <button className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-medium transition-colors shadow-sm">
              Sign in
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-sm text-gray-600 dark:text-gray-400">
          Don\'t have an account? <a href="#" className="text-indigo-600 hover:text-indigo-500 font-medium">Sign up</a>
        </p>
      </div>
    </div>
  );
}'''
        },
        {
            "request": "대시보드 통계 카드를 만들어주세요. 총 수익, 사용자 수, 전환율, 활성 세션을 보여주고, 각각 전주 대비 변화율을 표시하세요.",
            "code": '''export function StatsCards() {
  const stats = [
    { label: "Total Revenue", value: "$45,231", change: "+20.1%", positive: true, icon: "dollar" },
    { label: "Users", value: "2,350", change: "+15.3%", positive: true, icon: "users" },
    { label: "Conversion", value: "3.24%", change: "-2.1%", positive: false, icon: "chart" },
    { label: "Active Sessions", value: "573", change: "+8.4%", positive: true, icon: "activity" },
  ];

  const icons = {
    dollar: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />,
    users: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />,
    chart: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />,
    activity: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />,
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 p-6">
      {stats.map((stat) => (
        <div key={stat.label} className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-medium text-gray-600 dark:text-gray-400">{stat.label}</span>
            <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-900/30 flex items-center justify-center">
              <svg className="w-5 h-5 text-indigo-600 dark:text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {icons[stat.icon]}
              </svg>
            </div>
          </div>
          <div className="flex items-end justify-between">
            <span className="text-2xl font-bold text-gray-900 dark:text-white">{stat.value}</span>
            <span className={`text-sm font-medium px-2 py-0.5 rounded-full ${
              stat.positive
                ? "text-green-700 bg-green-100 dark:text-green-400 dark:bg-green-900/30"
                : "text-red-700 bg-red-100 dark:text-red-400 dark:bg-red-900/30"
            }`}>
              {stat.change}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}'''
        },
        {
            "request": "모달 다이얼로그 컴포넌트를 만들어주세요. 오버레이, 부드러운 애니메이션, 닫기 버튼이 있어야 합니다.",
            "code": '''import { useEffect, useRef } from "react";

export function Modal({ isOpen, onClose, title, children }) {
  const overlayRef = useRef(null);

  useEffect(() => {
    const handleEsc = (e) => { if (e.key === "Escape") onClose(); };
    if (isOpen) document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Overlay */}
      <div
        ref={overlayRef}
        className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fadeIn"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-white dark:bg-gray-800 rounded-2xl shadow-2xl animate-scaleIn">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          {children}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-xl hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
          >
            Cancel
          </button>
          <button className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 transition-colors shadow-sm">
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}'''
        },
        {
            "request": "TailwindCSS로 아름다운 히어로 섹션을 만들어주세요. 그라디언트 배경, 큰 제목, 설명 텍스트, CTA 버튼 2개, 그리고 장식적인 요소가 포함되어야 합니다.",
            "code": '''export function HeroSection() {
  return (
    <section className="relative overflow-hidden bg-gradient-to-br from-indigo-600 via-purple-600 to-pink-500 text-white">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-white/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-white/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-white/5 rounded-full blur-3xl" />
      </div>

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 sm:py-32 lg:py-40">
        <div className="text-center max-w-3xl mx-auto">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/20 backdrop-blur-sm text-sm font-medium mb-8 border border-white/30">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            Now available in beta
          </div>

          {/* Title */}
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight">
            Build beautiful apps
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-yellow-200 to-pink-200">
              at lightning speed
            </span>
          </h1>

          {/* Description */}
          <p className="mt-6 text-lg sm:text-xl text-indigo-100 max-w-2xl mx-auto leading-relaxed">
            The modern development platform that helps you ship products faster.
            Beautiful by default, powerful under the hood.
          </p>

          {/* CTA Buttons */}
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <button className="w-full sm:w-auto px-8 py-3.5 bg-white text-indigo-600 rounded-xl font-semibold hover:bg-gray-100 transition-all shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/30 hover:-translate-y-0.5">
              Get Started Free
            </button>
            <button className="w-full sm:w-auto px-8 py-3.5 border-2 border-white/30 rounded-xl font-semibold hover:bg-white/10 transition-all backdrop-blur-sm flex items-center justify-center gap-2">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
              Watch Demo
            </button>
          </div>

          {/* Social proof */}
          <div className="mt-12 flex items-center justify-center gap-6 text-sm text-indigo-200">
            <div className="flex -space-x-2">
              {[1,2,3,4,5].map((i) => (
                <div key={i} className="w-8 h-8 rounded-full bg-indigo-400 border-2 border-indigo-600 flex items-center justify-center text-xs font-bold">
                  {String.fromCharCode(64 + i)}
                </div>
              ))}
            </div>
            <span>Trusted by <strong className="text-white">10,000+</strong> developers</span>
          </div>
        </div>
      </div>
    </section>
  );
}'''
        },
    ]

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for comp in components:
            example = {
                "messages": [
                    {"role": "user", "content": comp["request"]},
                    {"role": "assistant", "content": f"```tsx\n{comp['code']}\n```"},
                ]
            }
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1

    logger.info(f"완료: {count}개 UI 컴포넌트 예제 → {out_file}")
    logger.info("  (프로덕션에서는 이 템플릿을 기반으로 LLM으로 수천 개를 합성 생성하세요)")


def download_design_principles(output_dir: Path, max_samples: int | None = None):
    """디자인 원리/이론 텍스트 데이터.

    UX 원칙, 색상 이론, 타이포그래피, 레이아웃 등.
    """
    logger.info("디자인 원리 텍스트 데이터 생성 중...")
    out_file = output_dir / "design_principles.txt"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    # 디자인 원리/이론 학습 텍스트 (합성)
    principles = [
        """# Visual Hierarchy in UI Design

Visual hierarchy is the arrangement of design elements in order of importance. It guides users' eyes to the most important elements first.

## Key Principles:

1. **Size**: Larger elements attract more attention. Headlines should be significantly larger than body text.
2. **Color and Contrast**: High-contrast elements stand out. Use your primary color for CTAs and important actions.
3. **Spacing**: White space (negative space) helps group related elements and separates unrelated ones. Generous padding improves readability.
4. **Typography**: Use font weight, size, and style to create clear content hierarchy. Limit to 2-3 font sizes per section.
5. **Position**: Elements at the top and left (in LTR layouts) receive more attention. Place key actions in predictable locations.

## Common Patterns:
- F-pattern: Users scan in an F-shape on text-heavy pages
- Z-pattern: Users follow a Z-shape on minimal pages
- Center-stage: Hero sections with centered content for maximum impact""",

        """# Color Theory for Web Design

## Color Psychology:
- **Blue**: Trust, security, professionalism (banks, tech companies)
- **Green**: Growth, health, nature (eco brands, finance)
- **Red**: Urgency, energy, passion (sales, food)
- **Purple**: Luxury, creativity, wisdom (premium brands)
- **Orange**: Friendly, energetic, confidence (CTAs, youth brands)
- **Black**: Elegance, sophistication, power (luxury, fashion)

## Color Systems:
- **60-30-10 Rule**: 60% dominant color, 30% secondary, 10% accent
- **Monochromatic**: Variations of a single hue for cohesive design
- **Complementary**: Opposite colors on the color wheel for high contrast
- **Analogous**: Adjacent colors for harmonious, natural feel

## Accessible Color Contrast:
- WCAG AA: 4.5:1 ratio for normal text, 3:1 for large text
- WCAG AAA: 7:1 ratio for normal text, 4.5:1 for large text
- Always test with color blindness simulators
- Never rely on color alone to convey meaning""",

        """# Responsive Design Best Practices

## Mobile-First Approach:
Design for the smallest screen first, then progressively enhance for larger screens.

## Breakpoints (TailwindCSS):
- sm: 640px (large phones)
- md: 768px (tablets)
- lg: 1024px (laptops)
- xl: 1280px (desktops)
- 2xl: 1536px (large screens)

## Key Techniques:
1. **Fluid Typography**: Use clamp() for responsive font sizes
   ```css
   font-size: clamp(1rem, 2.5vw, 2rem);
   ```

2. **Flexible Grids**: Use CSS Grid and Flexbox
   ```css
   grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
   ```

3. **Responsive Images**: Use srcset and sizes attributes
4. **Touch Targets**: Minimum 44x44px for interactive elements on mobile
5. **Content Priority**: Show essential content first on mobile, expand on desktop

## Testing:
- Test on real devices, not just browser resize
- Check landscape and portrait orientations
- Verify touch interactions work correctly""",

        """# Component Design Patterns

## Atomic Design Methodology:
1. **Atoms**: Basic building blocks (buttons, inputs, labels, icons)
2. **Molecules**: Groups of atoms (search bar = input + button)
3. **Organisms**: Complex components (navigation bar, card grid)
4. **Templates**: Page-level layouts
5. **Pages**: Specific instances of templates with real content

## Common UI Components:

### Button Variants:
- Primary: Main actions (filled, brand color)
- Secondary: Alternative actions (outlined or muted)
- Ghost: Subtle actions (text-only, hover reveals)
- Destructive: Dangerous actions (red, requires confirmation)

### Form Patterns:
- Inline validation with real-time feedback
- Clear error messages near the relevant field
- Progressive disclosure for complex forms
- Floating labels for space efficiency

### Navigation Patterns:
- Top navigation: Best for 5-7 main items
- Side navigation: Best for many items or nested hierarchy
- Bottom navigation (mobile): Best for 3-5 primary destinations
- Breadcrumbs: For deep hierarchical content

### Feedback Patterns:
- Toast notifications: Brief, auto-dismiss messages
- Modal dialogs: Important decisions requiring attention
- Inline alerts: Contextual information or warnings
- Skeleton screens: Loading states that preserve layout""",

        """# Dark Mode Design Guidelines

## Why Dark Mode:
- Reduces eye strain in low-light environments
- Saves battery on OLED screens
- Aesthetic preference for many users
- Improves focus on content

## Implementation Rules:

1. **Don't just invert colors**:
   - Light mode: white (#FFFFFF) background → Dark mode: NOT black (#000000)
   - Use dark gray (#121212 to #1A1A2E) for backgrounds
   - Pure black feels like a "void" - slight color adds depth

2. **Elevation with lighter surfaces**:
   - Higher elevation = lighter surface color
   - Background: #121212
   - Card/Surface: #1E1E1E
   - Elevated: #2C2C2C
   - Overlay: #383838

3. **Reduce contrast for comfort**:
   - Don't use pure white (#FFFFFF) text on dark backgrounds
   - Use off-white (#E0E0E0 to #FAFAFA) for primary text
   - Use muted colors (#A0A0A0) for secondary text

4. **Color adjustments**:
   - Desaturate bright colors slightly for dark mode
   - Use lighter variants of brand colors
   - Shadows are less visible - use lighter borders or elevation instead

5. **Images and media**:
   - Consider darkening images slightly (opacity overlay)
   - Provide dark variants of logos and illustrations
   - Use CSS filter: brightness(0.8) for user-uploaded content

## CSS Implementation:
```css
:root { --bg: #ffffff; --text: #1a1a1a; }
.dark { --bg: #0f0f11; --text: #e4e4e7; }
body { background: var(--bg); color: var(--text); }

@media (prefers-color-scheme: dark) {
  :root { --bg: #0f0f11; --text: #e4e4e7; }
}
```""",

        """# Typography in Web Design

## Type Scale:
A consistent type scale creates visual rhythm. Use a ratio:
- Minor Third (1.2): Subtle, compact
- Major Third (1.25): Balanced, readable
- Perfect Fourth (1.333): Spacious, editorial
- Golden Ratio (1.618): Dramatic, expressive

Example (base 16px, Major Third):
- xs: 12.8px
- sm: 14px
- base: 16px
- lg: 20px
- xl: 25px
- 2xl: 31.25px
- 3xl: 39px

## Font Pairing:
- **Serif + Sans-serif**: Classic combination (Playfair Display + Inter)
- **Geometric + Humanist**: Modern + Warm (Poppins + Source Sans Pro)
- **Monospace + Sans-serif**: Technical + Clean (JetBrains Mono + Inter)

## Line Height:
- Headings: 1.1 - 1.3 (tighter)
- Body text: 1.5 - 1.7 (comfortable)
- Small text: 1.6 - 1.8 (more open)

## Font Weight Usage:
- 400 (Regular): Body text
- 500 (Medium): Labels, captions, emphasis
- 600 (Semibold): Subheadings, interactive elements
- 700 (Bold): Headings, important callouts

## Readability:
- Optimal line length: 50-75 characters per line
- Use max-width on text containers (65ch or ~600px)
- Left-align body text (center only for short headings)
- Sufficient contrast: 4.5:1 minimum for normal text""",

        """# Animation and Micro-interactions

## Principles of UI Animation:

1. **Purpose**: Every animation should serve a purpose
   - Guide attention
   - Show state changes
   - Provide feedback
   - Create spatial awareness

2. **Duration**:
   - Micro-interactions: 100-200ms (button hover, toggle)
   - Transitions: 200-400ms (page transitions, modals)
   - Complex animations: 400-700ms (onboarding, celebrations)
   - Never exceed 1000ms for UI animations

3. **Easing**:
   - ease-out: Elements entering the screen (decelerate)
   - ease-in: Elements leaving the screen (accelerate)
   - ease-in-out: Elements moving on screen
   - spring: Natural, bouncy feel for playful UIs

## CSS Animation Examples:
```css
/* Fade in from below */
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Scale in (for modals) */
@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

/* Skeleton loading shimmer */
@keyframes shimmer {
  0% { background-position: -200px 0; }
  100% { background-position: calc(200px + 100%) 0; }
}
.skeleton {
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200px 100%;
  animation: shimmer 1.5s infinite;
}
```

## Best Practices:
- Use transform and opacity for 60fps animations (GPU-accelerated)
- Avoid animating width, height, top, left (causes layout thrashing)
- Use will-change sparingly for heavy animations
- Respect prefers-reduced-motion for accessibility
```css
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; }
}
```""",
    ]

    with open(out_file, "w", encoding="utf-8") as f:
        for principle in principles:
            f.write(principle.strip() + "\n\n---\n\n")

    size_kb = out_file.stat().st_size / 1024
    logger.info(f"완료: {len(principles)}개 디자인 원리 문서, {size_kb:.1f}KB → {out_file}")
    logger.info("  (프로덕션에서는 MDN, Smashing Magazine 등에서 추가 크롤링 필요)")


# ============================================================
# SFT 데이터 다운로드
# ============================================================

def download_sft_ko(output_dir: Path, max_samples: int | None = None):
    """한국어 KoAlpaca 지시 데이터 다운로드."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("KoAlpaca v1.1a 다운로드 중...")
    out_file = output_dir / "ko_instructions.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    ds = load_dataset("beomi/KoAlpaca-v1.1a", split="train")

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="KoAlpaca"):
            instruction = row.get("instruction", "").strip()
            output_text = row.get("output", "").strip()

            if not instruction or not output_text:
                continue

            example = {
                "messages": [
                    {"role": "user", "content": instruction},
                    {"role": "assistant", "content": output_text},
                ]
            }
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
            if max_samples and count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


def download_sft_ko_vicuna(output_dir: Path, max_samples: int | None = None):
    """한국어 ShareGPT 스타일 데이터 다운로드."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("한국어 대화 데이터 다운로드 중 (KoVicuna)...")
    out_file = output_dir / "ko_conversations.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    try:
        ds = load_dataset("heegyu/ko-chatgpt-dialog", split="train")
    except Exception as e:
        logger.warning(f"KoVicuna 다운로드 실패: {e}")
        return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="KoVicuna"):
            messages = []
            conversations = row.get("conversations", row.get("conversation", []))

            if not conversations:
                continue

            for turn in conversations:
                role_map = {"human": "user", "gpt": "assistant", "user": "user", "assistant": "assistant"}
                from_key = turn.get("from", turn.get("role", ""))
                value = turn.get("value", turn.get("content", ""))
                role = role_map.get(from_key, from_key)
                if role in ("user", "assistant") and value:
                    messages.append({"role": role, "content": value.strip()})

            if len(messages) >= 2:
                f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
                count += 1

            if max_samples and count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 대화 → {out_file}")


def download_sft_en(output_dir: Path, max_samples: int | None = None):
    """영어 SlimOrca 지시 데이터 다운로드."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("SlimOrca 다운로드 중...")
    out_file = output_dir / "en_instructions.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    max_samples = max_samples or 100_000  # SlimOrca가 크므로 기본 제한
    ds = load_dataset("Open-Orca/SlimOrca", split="train", streaming=True)

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="SlimOrca", total=max_samples):
            conversations = row.get("conversations", [])
            messages = []
            for turn in conversations:
                role_map = {"human": "user", "gpt": "assistant", "system": "system"}
                role = role_map.get(turn.get("from", ""), turn.get("from", ""))
                value = turn.get("value", "")
                if role and value:
                    messages.append({"role": role, "content": value})

            if len(messages) >= 2:
                f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
                count += 1

            if count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


def download_sft_en_code(output_dir: Path, max_samples: int | None = None):
    """영어 코드 지시 데이터 다운로드."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("코드 지시 데이터 다운로드 중 (Code-Alpaca)...")
    out_file = output_dir / "en_code_instructions.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    try:
        ds = load_dataset("sahil2801/CodeAlpaca-20k", split="train")
    except Exception as e:
        logger.warning(f"Code-Alpaca 다운로드 실패: {e}")
        return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="Code-Alpaca"):
            instruction = row.get("instruction", "").strip()
            input_text = row.get("input", "").strip()
            output_text = row.get("output", "").strip()

            if not instruction or not output_text:
                continue

            user_content = instruction
            if input_text:
                user_content += f"\n\n{input_text}"

            example = {
                "messages": [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": output_text},
                ]
            }
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
            if max_samples and count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


# ============================================================
# DPO 데이터 다운로드
# ============================================================

def download_dpo(output_dir: Path, max_samples: int | None = None):
    """UltraFeedback 선호도 데이터 다운로드."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("UltraFeedback 선호도 데이터 다운로드 중...")
    out_file = output_dir / "preferences.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    ds = load_dataset(
        "argilla/ultrafeedback-binarized-preferences-cleaned",
        split="train",
    )

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="UltraFeedback"):
            prompt = row.get("prompt", "").strip()
            chosen_msgs = row.get("chosen", [])
            rejected_msgs = row.get("rejected", [])

            if not prompt:
                continue

            # chosen/rejected에서 assistant 응답 추출
            chosen_text = ""
            rejected_text = ""

            if isinstance(chosen_msgs, list):
                for msg in chosen_msgs:
                    if msg.get("role") == "assistant":
                        chosen_text = msg.get("content", "")
                        break
            elif isinstance(chosen_msgs, str):
                chosen_text = chosen_msgs

            if isinstance(rejected_msgs, list):
                for msg in rejected_msgs:
                    if msg.get("role") == "assistant":
                        rejected_text = msg.get("content", "")
                        break
            elif isinstance(rejected_msgs, str):
                rejected_text = rejected_msgs

            if not chosen_text or not rejected_text:
                continue

            example = {
                "prompt": prompt,
                "chosen": chosen_text,
                "rejected": rejected_text,
            }
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
            if max_samples and count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


def download_dpo_hh_rlhf(output_dir: Path, max_samples: int | None = None):
    """Anthropic HH-RLHF 안전성 선호도 데이터."""
    from datasets import load_dataset
    from tqdm import tqdm

    logger.info("HH-RLHF 안전성 데이터 다운로드 중...")
    out_file = output_dir / "safety_preferences.jsonl"

    if out_file.exists():
        logger.info(f"이미 존재합니다: {out_file}")
        return

    try:
        ds = load_dataset("Anthropic/hh-rlhf", split="train")
    except Exception as e:
        logger.warning(f"HH-RLHF 다운로드 실패: {e}")
        return

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in tqdm(ds, desc="HH-RLHF"):
            chosen = row.get("chosen", "").strip()
            rejected = row.get("rejected", "").strip()

            if not chosen or not rejected:
                continue

            # HH-RLHF 형식: "Human: ...\n\nAssistant: ..."
            # 프롬프트와 응답 분리
            def parse_hh(text):
                parts = text.split("\n\nAssistant:")
                if len(parts) >= 2:
                    prompt_part = parts[0].replace("Human: ", "", 1).strip()
                    response_part = parts[-1].strip()
                    return prompt_part, response_part
                return "", ""

            prompt, chosen_resp = parse_hh(chosen)
            _, rejected_resp = parse_hh(rejected)

            if not prompt or not chosen_resp or not rejected_resp:
                continue

            example = {
                "prompt": prompt,
                "chosen": chosen_resp,
                "rejected": rejected_resp,
            }
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1
            if max_samples and count >= max_samples:
                break

    logger.info(f"완료: {count:,}개 예제 → {out_file}")


# ============================================================
# 통합 데이터 스크립트 (SFT 데이터 합치기)
# ============================================================

def merge_sft_data(output_dir: Path):
    """모든 SFT JSONL 파일을 하나로 합칩니다."""
    sft_dir = output_dir
    merged_file = output_dir / "all_sft.jsonl"

    sft_files = list(sft_dir.glob("*.jsonl"))
    if not sft_files:
        logger.info("합칠 SFT 파일이 없습니다")
        return

    count = 0
    with open(merged_file, "w", encoding="utf-8") as out:
        for sft_file in sft_files:
            if sft_file.name == "all_sft.jsonl":
                continue
            with open(sft_file, encoding="utf-8") as f:
                for line in f:
                    out.write(line)
                    count += 1

    logger.info(f"SFT 데이터 병합 완료: {count:,}개 예제 → {merged_file}")


def merge_pretrain_data(output_dir: Path):
    """모든 pretrain 텍스트 파일을 하나로 합칩니다."""
    pretrain_dir = output_dir
    merged_file = output_dir / "corpus.txt"

    txt_files = list(pretrain_dir.glob("*.txt"))
    if not txt_files:
        logger.info("합칠 pretrain 파일이 없습니다")
        return

    total_bytes = 0
    with open(merged_file, "w", encoding="utf-8") as out:
        for txt_file in txt_files:
            if txt_file.name == "corpus.txt":
                continue
            logger.info(f"  병합: {txt_file.name}")
            with open(txt_file, encoding="utf-8") as f:
                for line in f:
                    out.write(line)
                    total_bytes += len(line.encode("utf-8"))

    size_mb = total_bytes / (1024 * 1024)
    logger.info(f"Pretrain 데이터 병합 완료: {size_mb:.1f}MB → {merged_file}")


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hwarang 학습 데이터 다운로드",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python scripts/download_data.py --task all --output data/
  python scripts/download_data.py --task pretrain --lang ko --output data/
  python scripts/download_data.py --task code --output data/            # 20개 프로그래밍 언어
  python scripts/download_data.py --task sft --lang ko --max-samples 5000 --output data/
  python scripts/download_data.py --task dpo --output data/
        """,
    )
    parser.add_argument(
        "--task",
        choices=["pretrain", "sft", "dpo", "code", "design", "all"],
        required=True,
        help="다운로드할 데이터 종류 (code=프로그래밍, design=UI/UX 디자인)",
    )
    parser.add_argument(
        "--lang",
        choices=["ko", "en", "all"],
        default="all",
        help="언어 (default: all)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/",
        help="출력 디렉토리 (default: data/)",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="최대 다운로드 샘플 수 (빠른 테스트용)",
    )
    args = parser.parse_args()

    check_dependencies()

    base_dir = Path(args.output)
    tasks = [args.task] if args.task != "all" else ["pretrain", "code", "design", "sft", "dpo"]
    langs = [args.lang] if args.lang != "all" else ["ko", "en"]

    logger.info("=" * 60)
    logger.info(f"Hwarang 데이터 다운로드")
    logger.info(f"  작업: {', '.join(tasks)}")
    logger.info(f"  언어: {', '.join(langs)}")
    logger.info(f"  출력: {base_dir}")
    if args.max_samples:
        logger.info(f"  최대 샘플: {args.max_samples:,}")
    logger.info("=" * 60)

    # ------ Pretrain ------
    if "pretrain" in tasks:
        pretrain_dir = base_dir / "pretrain"
        pretrain_dir.mkdir(parents=True, exist_ok=True)

        if "ko" in langs:
            download_pretrain_ko(pretrain_dir, args.max_samples)           # 위키피디아 ~1GB
            download_pretrain_ko_namuwiki(pretrain_dir, args.max_samples)  # 나무위키 ~5GB
            download_pretrain_ko_cc(pretrain_dir, args.max_samples)        # mC4 웹텍스트 ~20GB
            download_pretrain_ko_news(pretrain_dir, args.max_samples)      # 뉴스 ~100MB
            download_pretrain_ko_book(pretrain_dir, args.max_samples)      # 도서/문학
        if "en" in langs:
            download_pretrain_en(pretrain_dir, args.max_samples)

        merge_pretrain_data(pretrain_dir)

    # ------ Code ------
    if "code" in tasks:
        code_pretrain_dir = base_dir / "pretrain"
        code_pretrain_dir.mkdir(parents=True, exist_ok=True)
        code_sft_dir = base_dir / "sft"
        code_sft_dir.mkdir(parents=True, exist_ok=True)

        # 코드 Pretrain (대규모 원본 코드)
        download_code_pretrain(code_pretrain_dir, args.max_samples)
        download_code_github(code_pretrain_dir, args.max_samples)

        # 코드 SFT (코딩 지시-응답)
        download_code_sft_evol(code_sft_dir, args.max_samples)
        download_code_sft_magicoder(code_sft_dir, args.max_samples)
        download_code_sft_glaive(code_sft_dir, args.max_samples)
        download_code_commits(code_sft_dir, args.max_samples)

        merge_pretrain_data(code_pretrain_dir)

    # ------ Design ------
    if "design" in tasks:
        design_pretrain_dir = base_dir / "pretrain"
        design_pretrain_dir.mkdir(parents=True, exist_ok=True)
        design_sft_dir = base_dir / "sft"
        design_sft_dir.mkdir(parents=True, exist_ok=True)

        # 디자인 Pretrain (CSS/프론트엔드 코드 + 디자인 이론)
        download_design_pretrain_css(design_pretrain_dir, args.max_samples)
        download_design_principles(design_pretrain_dir, args.max_samples)

        # 디자인 SFT (디자인 요청 → 코드)
        download_design_sft_websight(design_sft_dir, args.max_samples)
        download_design_sft_ui_components(design_sft_dir, args.max_samples)

        merge_pretrain_data(design_pretrain_dir)

    # ------ SFT ------
    if "sft" in tasks:
        sft_dir = base_dir / "sft"
        sft_dir.mkdir(parents=True, exist_ok=True)

        if "ko" in langs:
            download_sft_ko(sft_dir, args.max_samples)            # KoAlpaca 52K
            download_sft_ko_vicuna(sft_dir, args.max_samples)     # KoVicuna ~10K
            download_sft_ko_openorca(sft_dir, args.max_samples)   # KO-OpenOrca ~100K
        if "en" in langs:
            download_sft_en(sft_dir, args.max_samples)
            download_sft_en_code(sft_dir, args.max_samples)

        merge_sft_data(sft_dir)

    # ------ DPO ------
    if "dpo" in tasks:
        dpo_dir = base_dir / "dpo"
        dpo_dir.mkdir(parents=True, exist_ok=True)

        download_dpo(dpo_dir, args.max_samples)
        download_dpo_hh_rlhf(dpo_dir, args.max_samples)

    # ------ 요약 ------
    logger.info("")
    logger.info("=" * 60)
    logger.info("다운로드 완료! 디렉토리 구조:")
    logger.info("")

    for task_dir in sorted(base_dir.rglob("*")):
        if task_dir.is_file():
            size = task_dir.stat().st_size
            if size > 1024 * 1024 * 1024:
                size_str = f"{size / (1024**3):.1f}GB"
            elif size > 1024 * 1024:
                size_str = f"{size / (1024**2):.1f}MB"
            elif size > 1024:
                size_str = f"{size / 1024:.1f}KB"
            else:
                size_str = f"{size}B"
            rel = task_dir.relative_to(base_dir)
            logger.info(f"  {rel}  ({size_str})")

    logger.info("")
    logger.info("다음 단계:")
    logger.info("  1. 토크나이저 학습:")
    logger.info(f"     python modules/hwarang-core/scripts/train_tokenizer.py \\")
    logger.info(f"       --data {base_dir}/pretrain/corpus.txt --output modules/hwarang-core/tokenizer_output")
    logger.info("  2. Pretraining:")
    logger.info(f"     (README.md의 '전체 학습 파이프라인' 참고)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
