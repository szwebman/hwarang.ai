"""법률/세무 도메인 SFT 데이터 수집 스크립트.

소스:
  1. 한국 법률 공개 데이터 (법제처 API, 판례 등)
  2. 세무 관련 Q&A 데이터셋
  3. HuggingFace 한국어 법률 데이터
  4. 커스텀 법률/세무 Q&A 템플릿

사용법:
    python scripts/data/collect_legal_tax.py \
        --output data/sft/legal_tax.jsonl \
        --max-samples 30000

필요 패키지:
    pip install datasets requests beautifulsoup4
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SYSTEM_PROMPT_LEGAL = "당신은 화랑 AI 법률 어시스턴트입니다. 한국 법률에 대해 정확하고 이해하기 쉽게 설명합니다. 중요: 법률 상담은 참고용이며, 구체적인 사안은 반드시 변호사와 상담하세요."

SYSTEM_PROMPT_TAX = "당신은 화랑 AI 세무 어시스턴트입니다. 한국 세법에 대해 정확하고 이해하기 쉽게 설명합니다. 중요: 세무 상담은 참고용이며, 구체적인 사안은 반드시 세무사와 상담하세요."


def convert_to_chatml(question: str, answer: str, system: str) -> dict:
    """Q&A → ChatML 포맷."""
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    }


# ─── 1. HuggingFace 법률 데이터셋 ───────────────────────────────

HF_LEGAL_DATASETS = [
    {"name": "lbox/lbox_open", "type": "legal"},
    {"name": "joonhok/korean-law-open-data-precedents", "type": "precedent"},
    {"name": "AI-Hub/korean_law_qa", "type": "qa"},
]


def collect_hf_legal(max_per_dataset: int = 5000) -> list[dict]:
    """HuggingFace에서 법률 데이터 수집."""
    all_data = []

    try:
        from datasets import load_dataset
    except ImportError:
        logger.warning("datasets 패키지 없음 - HuggingFace 수집 건너뜀")
        return all_data

    for ds_info in HF_LEGAL_DATASETS:
        name = ds_info["name"]
        logger.info(f"수집 중: {name}")

        try:
            ds = load_dataset(name, split="train", streaming=True, trust_remote_code=True)
            count = 0
            for item in ds:
                if count >= max_per_dataset:
                    break

                # 다양한 포맷 처리
                question = item.get("question", item.get("instruction", item.get("input", "")))
                answer = item.get("answer", item.get("output", item.get("response", "")))

                if not question or not answer:
                    # 판례 데이터인 경우 요약 생성
                    text = item.get("text", item.get("content", ""))
                    if text and len(text) > 200:
                        question = "다음 판례의 핵심 내용을 요약해주세요."
                        answer = text[:2000]  # 최대 2000자

                if question and answer:
                    all_data.append(convert_to_chatml(question, answer, SYSTEM_PROMPT_LEGAL))
                    count += 1

            logger.info(f"  → {count}개 수집")
        except Exception as e:
            logger.warning(f"  → 실패: {e}")

    return all_data


# ─── 2. 법제처 공개 법률 데이터 ──────────────────────────────────

def collect_law_data_from_api(api_key: str = "", max_items: int = 1000) -> list[dict]:
    """법제처 Open API에서 법률 데이터 수집.

    API 키는 https://open.law.go.kr 에서 발급.
    API 키가 없으면 건너뜀.
    """
    if not api_key:
        logger.info("법제처 API 키 없음 - 건너뜀 (https://open.law.go.kr 에서 발급)")
        return []

    import requests

    all_data = []
    base_url = "http://www.law.go.kr/DRF/lawSearch.do"

    try:
        params = {
            "OC": api_key,
            "target": "law",
            "type": "JSON",
            "display": min(max_items, 100),
            "query": "민법",
        }
        resp = requests.get(base_url, params=params, timeout=30)
        if resp.ok:
            data = resp.json()
            laws = data.get("LawSearch", {}).get("law", [])
            for law in laws[:max_items]:
                name = law.get("법령명한글", "")
                if name:
                    q = f"'{name}'의 주요 내용을 설명해주세요."
                    a = f"'{name}'은(는) 한국 법률로, 해당 법률의 구체적인 내용은 법제처(law.go.kr)에서 전문을 확인하실 수 있습니다."
                    all_data.append(convert_to_chatml(q, a, SYSTEM_PROMPT_LEGAL))
            logger.info(f"법제처 API: {len(all_data)}개 수집")
    except Exception as e:
        logger.warning(f"법제처 API 실패: {e}")

    return all_data


# ─── 3. 법률/세무 Q&A 템플릿 ────────────────────────────────────

LEGAL_QA_TEMPLATES = [
    # 민법
    {"q": "계약 해제와 해지의 차이가 뭐야?",
     "a": "**계약 해제**와 **해지**는 모두 계약을 종료시키는 것이지만 효과가 다릅니다.\n\n**계약 해제 (민법 제543조~제553조)**\n- 계약이 처음부터 없었던 것으로 되돌림 (소급효)\n- 이미 이행한 것은 원상회복해야 함\n- 예: 물건을 사고 하자가 있어서 해제 → 물건 반환 + 대금 반환\n\n**계약 해지**\n- 계약을 장래에 향하여 종료 (장래효)\n- 이미 이행한 부분은 그대로 유지\n- 예: 월세 계약 해지 → 이미 살았던 기간의 월세는 돌려받지 않음\n\n⚠️ 구체적인 법률 문제는 변호사와 상담하시기 바랍니다."},

    {"q": "내용증명이 뭐야? 어떻게 보내?",
     "a": "**내용증명**은 누가, 언제, 누구에게, 어떤 내용을 보냈는지를 우체국이 증명해주는 제도입니다.\n\n**용도:**\n- 채무 이행 촉구 (돈 갚으라는 통보)\n- 계약 해제/해지 의사 통보\n- 손해배상 청구 사전 통보\n\n**보내는 방법:**\n1. 같은 내용의 문서 3부 준비 (수신인, 발신인, 우체국 보관)\n2. 가까운 우체국 방문\n3. 내용증명 발송 신청 (비용: 약 2,000~5,000원)\n4. 또는 인터넷 우체국(epost.kr)에서 온라인 발송\n\n**작성 팁:**\n- 육하원칙에 따라 명확하게 작성\n- 요구 사항과 기한을 구체적으로 명시\n- 감정적 표현은 자제\n\n⚠️ 내용증명 자체에 법적 구속력은 없지만, 분쟁 시 강력한 증거가 됩니다."},

    {"q": "전세 보증금을 못 돌려받으면 어떻게 해?",
     "a": "전세 보증금을 돌려받지 못할 때 단계별 대응 방법입니다.\n\n**1단계: 내용증명 발송**\n- 보증금 반환 요청 내용증명 발송 (기한 설정)\n\n**2단계: 임차권등기명령 신청**\n- 관할 법원에 임차권등기명령 신청\n- 이사 나가도 대항력·우선변제권 유지\n- 비용: 약 5만원, 처리기간: 1~2주\n\n**3단계: 지급명령 신청**\n- 법원에 지급명령 신청 (소장보다 간단)\n- 인지대 저렴 (소송의 1/10)\n- 상대방이 2주 내 이의 안 하면 확정\n\n**4단계: 소액사건 소송**\n- 보증금 3,000만원 이하: 소액사건 (1회 변론)\n- 3,000만원 초과: 민사소송\n\n**활용 가능한 지원:**\n- 대한법률구조공단 (무료 법률상담)\n- 주택도시보증공사 (HUG) 보증보험 가입 시 대위변제\n- 전세사기피해지원센터\n\n⚠️ 구체적인 상황에 따라 절차가 달라질 수 있으니 법률 전문가와 상담하세요."},

    # 노동법
    {"q": "퇴직금은 어떻게 계산해?",
     "a": "**퇴직금 계산법** (근로자퇴직급여 보장법 제8조)\n\n**기본 공식:**\n```\n퇴직금 = 1일 평균임금 × 30일 × (재직일수 / 365)\n```\n\n**1일 평균임금 계산:**\n```\n퇴직 전 3개월간 총 임금 ÷ 해당 기간의 총 일수\n\n총 임금 = 기본급 + 고정수당 + 상여금(연간 1/12) + 연차수당\n```\n\n**예시:** 월급 300만원, 3년 근무\n- 3개월 임금: 300만 × 3 = 900만원\n- 평균임금: 900만 ÷ 92일 = 약 97,826원/일\n- 퇴직금: 97,826 × 30 × (1,095/365) = **약 880만원**\n\n**주의사항:**\n- 1년 미만 근무 시 퇴직금 없음\n- 4주 평균 15시간 미만 단시간 근로자는 제외\n- 퇴직일로부터 14일 이내 지급 의무\n\n⚠️ 정확한 계산은 고용노동부 퇴직금 계산기를 활용하세요."},

    {"q": "부당해고 당하면 어떻게 해야 해?",
     "a": "**부당해고 대응 절차:**\n\n**1. 해고 사유 확인**\n- 서면으로 해고 통보를 받았는지 확인\n- 근로기준법 제27조: 해고는 서면으로 해고사유와 시기를 통지해야 함\n- 서면 통지 없으면 그 자체로 부당해고\n\n**2. 부당해고 구제신청 (가장 중요!)**\n- 해고일로부터 **3개월 이내** 지방노동위원회에 구제신청\n- 비용: 무료\n- 기간: 약 2~3개월\n- 인정되면: 복직 + 해고기간 임금 전액 지급\n\n**3. 고용노동부 진정/고소**\n- 가까운 고용노동청에 진정 접수\n- 근로감독관이 조사 후 시정명령\n\n**4. 민사소송**\n- 해고무효확인 소송\n- 임금지급청구 소송\n\n**무료 지원:**\n- 고용노동부 상담센터: 1350\n- 대한법률구조공단: 132\n- 근로자 무료 법률상담\n\n⚠️ 3개월 기한을 놓치면 구제신청이 불가하니 빠른 대응이 중요합니다."},
]

TAX_QA_TEMPLATES = [
    # 소득세
    {"q": "종합소득세 신고는 어떻게 해?",
     "a": "**종합소득세 신고 가이드**\n\n**신고 대상:**\n- 사업소득 (프리랜서, 자영업자)\n- 근로소득 2곳 이상\n- 금융소득 2,000만원 초과\n- 연금소득, 기타소득\n\n**신고 기간:** 매년 5월 1일 ~ 5월 31일\n\n**신고 방법:**\n1. **홈택스** (hometax.go.kr) - 가장 편리\n2. **손택스** (모바일 앱)\n3. 세무서 방문 신고\n4. 세무사 대리 신고\n\n**홈택스 신고 절차:**\n1. 홈택스 로그인 (공동인증서)\n2. 신고/납부 → 종합소득세 → 정기신고\n3. 기본정보 입력\n4. 소득금액 확인 (자동 불러오기)\n5. 공제항목 입력 (인적공제, 보험료, 의료비 등)\n6. 세액 계산 → 신고서 제출\n7. 납부 (계좌이체, 카드, 가상계좌)\n\n**절세 팁:**\n- 사업소득: 경비처리 철저히 (영수증 보관)\n- 세액공제: 연금저축, IRP, 기부금 등 활용\n- 성실신고확인: 매출 일정 규모 이상 시 필수\n\n⚠️ 정확한 세금 계산은 세무사와 상담하시기 바랍니다."},

    {"q": "부가가치세 신고 기간이 언제야?",
     "a": "**부가가치세 신고 기간:**\n\n| 구분 | 과세기간 | 신고·납부기한 |\n|------|----------|---------------|\n| 1기 확정 | 1.1~6.30 | **7월 25일** |\n| 2기 확정 | 7.1~12.31 | **다음해 1월 25일** |\n| 1기 예정 | 1.1~3.31 | 4월 25일 (개인은 고지) |\n| 2기 예정 | 7.1~9.30 | 10월 25일 (개인은 고지) |\n\n**간이과세자:** 연 1회 (1.1~12.31 → 다음해 1월 25일)\n\n**신고 방법:**\n- 홈택스 전자신고 (hometax.go.kr)\n- 매입/매출 세금계산서 자동 불러오기 가능\n\n**주의사항:**\n- 기한 초과 시 가산세 부과 (무신고 20%, 납부지연 일 0.022%)\n- 영세율 적용 시에도 반드시 신고해야 함\n\n⚠️ 구체적인 신고는 세무사와 상담하시기 바랍니다."},

    {"q": "개인사업자 절세 방법 알려줘",
     "a": "**개인사업자 절세 전략:**\n\n**1. 경비 처리 철저히**\n- 사업 관련 모든 지출 영수증 보관\n- 사업용 신용카드 사용 (자동 경비 인정)\n- 차량유지비, 통신비, 사무실 임대료 등\n\n**2. 사업용 계좌 분리**\n- 개인/사업 계좌 반드시 분리\n- 복식부기 의무자는 사업용 계좌 신고 필수\n\n**3. 세액공제 활용**\n- 연금저축: 연 400만원까지 공제\n- IRP: 연 700만원까지 공제\n- 기부금: 필요경비 또는 세액공제\n- 중소기업 특별세액감면\n\n**4. 감가상각 활용**\n- 사업용 자산 (컴퓨터, 차량 등) 감가상각\n- 즉시상각 특례 (소규모 자산)\n\n**5. 가족 인건비**\n- 실제 근무하는 배우자/가족에게 급여 지급\n- 4대보험 가입 필수\n\n**6. 법인 전환 검토**\n- 과세표준 4,600만원 이상이면 법인이 유리할 수 있음\n- 법인세율 vs 소득세율 비교 필요\n\n⚠️ 절세와 탈세는 다릅니다. 정확한 절세 전략은 세무사와 상담하세요."},

    {"q": "양도소득세는 어떻게 계산해?",
     "a": "**양도소득세 계산 구조:**\n\n```\n양도가액 (팔 때 가격)\n- 취득가액 (살 때 가격)\n- 필요경비 (취득세, 중개수수료, 인테리어 등)\n= 양도차익\n- 장기보유특별공제 (2년 이상 보유 시)\n= 양도소득금액\n- 기본공제 (250만원)\n= 과세표준\n× 세율\n= 양도소득세\n```\n\n**세율 (2024년 기준):**\n- 1년 미만 보유: 70% (주택) / 50% (기타)\n- 1~2년 보유: 60% (주택) / 40% (기타)\n- 2년 이상: 기본세율 (6%~45%)\n- 다주택자 중과: +20~30%p\n\n**장기보유특별공제 (1세대 1주택):**\n- 3년 이상: 보유 연 4% + 거주 연 4%\n- 최대 80% (10년 보유+거주)\n\n**1세대 1주택 비과세:**\n- 2년 이상 보유 (조정지역: 2년 거주 필요)\n- 양도가액 12억원 이하 전액 비과세\n- 12억원 초과 시 초과분만 과세\n\n⚠️ 부동산 세금은 복잡하므로 반드시 세무사와 상담하세요."},

    {"q": "연말정산에서 공제받을 수 있는 항목이 뭐가 있어?",
     "a": "**연말정산 주요 공제 항목:**\n\n**1. 인적공제 (기본공제)**\n- 본인: 150만원\n- 배우자: 150만원 (소득 100만원 이하)\n- 부양가족: 1인당 150만원\n\n**2. 소득공제**\n- 국민연금: 전액 공제\n- 건강보험: 전액 공제\n- 신용카드 등: 총급여 25% 초과분\n  - 신용카드: 15%\n  - 체크카드/현금영수증: 30%\n  - 전통시장/대중교통: 40%\n- 주택자금: 청약저축, 주택담보대출 이자\n\n**3. 세액공제**\n- 의료비: 총급여 3% 초과분의 15%\n- 교육비: 15% (대학생 연 900만원 한도)\n- 기부금: 15~30%\n- 보험료: 12% (연 100만원 한도)\n- 연금저축: 13.2~16.5% (400만원 한도)\n- IRP: 13.2~16.5% (700만원 한도)\n- 월세: 15~17% (750만원 한도, 총급여 7천만원 이하)\n\n**놓치기 쉬운 공제:**\n- 안경/콘택트렌즈 구입비 (의료비)\n- 중고생 교복 구입비 (교육비)\n- 취학 전 아동 학원비 (교육비)\n\n⚠️ 공제 한도와 조건은 매년 바뀔 수 있으니 국세청 홈택스에서 확인하세요."},
]


def generate_legal_tax_templates() -> list[dict]:
    """법률/세무 템플릿에서 SFT 데이터 생성."""
    data = []
    for tmpl in LEGAL_QA_TEMPLATES:
        data.append(convert_to_chatml(tmpl["q"], tmpl["a"], SYSTEM_PROMPT_LEGAL))
    for tmpl in TAX_QA_TEMPLATES:
        data.append(convert_to_chatml(tmpl["q"], tmpl["a"], SYSTEM_PROMPT_TAX))
    return data


# ─── 메인 ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="법률/세무 도메인 SFT 데이터 수집")
    parser.add_argument("--output", required=True, help="출력 JSONL 파일 경로")
    parser.add_argument("--max-samples", type=int, default=30000)
    parser.add_argument("--law-api-key", default="", help="법제처 Open API 키")
    parser.add_argument("--skip-hf", action="store_true", help="HuggingFace 수집 건너뛰기")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("법률/세무 도메인 SFT 데이터 수집")
    logger.info("=" * 60)

    all_data = []

    # 1. 템플릿 데이터
    logger.info("\n[1/3] 법률/세무 Q&A 템플릿 생성...")
    templates = generate_legal_tax_templates()
    all_data.extend(templates)
    logger.info(f"  → 템플릿: {len(templates)}개")

    # 2. 법제처 API
    logger.info("\n[2/3] 법제처 공개 데이터...")
    law_data = collect_law_data_from_api(args.law_api_key)
    all_data.extend(law_data)

    # 3. HuggingFace
    if not args.skip_hf:
        logger.info("\n[3/3] HuggingFace 법률 데이터셋...")
        hf_data = collect_hf_legal(max_per_dataset=args.max_samples // 3)
        all_data.extend(hf_data)

    # 저장
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"\n총 {len(all_data)}개 저장 → {args.output}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
