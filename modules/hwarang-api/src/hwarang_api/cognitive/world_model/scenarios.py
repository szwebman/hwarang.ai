"""한국 정책/경제/법률 시나리오 라이브러리.

각 ``Scenario`` 는 LLM 시뮬레이터에 입력되는 초기 상태와 규칙을 담는다.
한국 거시경제/제도 환경에 특화된 변수 (USD/KRW, 한미금리차, 청년층 실업률,
국회 정당지지율 등) 를 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Scenario:
    """단일 시나리오 정의.

    Attributes
    ----------
    name : str
        한국어 식별자 (예: "부동산 시장").
    domain : str
        ``economy`` / ``policy`` / ``law`` / ``finance`` / ``labor``.
    initial_state : dict
        시작 상태 — 키-값으로 LLM 에 그대로 전달.
    possible_actions : list[str]
        시뮬레이션 가능한 액션 후보 (정책/의사결정).
    rules : list[str]
        한국어 자연어 인과 규칙 — LLM 프롬프트에 포함.
    description : str
        관리자 UI/문서용 한국어 설명.
    """

    name: str
    domain: str
    initial_state: dict
    possible_actions: list[str]
    rules: list[str]
    description: str = ""


# ────────────────────────────────────────────────────────────
# 사전 정의된 5 개 한국 시나리오
# ────────────────────────────────────────────────────────────
_SCENARIOS: dict[str, Scenario] = {
    "부동산 시장": Scenario(
        name="부동산 시장",
        domain="economy",
        initial_state={
            "기준금리_pct": 3.5,
            "주담대_LTV_pct": 70,
            "주담대_DSR_pct": 40,
            "서울_아파트_평당가_만원": 5500,
            "전국_미분양_호": 65000,
            "신규_분양_월간_호": 18000,
            "전세가율_pct": 55,
            "거래량_index_100base": 78,
        },
        possible_actions=[
            "기준금리 0.25%p 인상",
            "기준금리 0.25%p 인하",
            "DSR 규제 강화 (35%)",
            "DSR 규제 완화 (50%)",
            "재건축 안전진단 완화",
            "신규 공공분양 5만호 공급",
            "다주택자 양도세 중과 폐지",
        ],
        rules=[
            "기준금리가 오르면 주담대 이자가 오르고 거래량은 줄어든다.",
            "DSR 강화는 신규 대출 가능액을 줄여 가격 하방 압력을 만든다.",
            "공급 확대는 6~12개월 시차로 매매가에 반영된다.",
            "전세가율이 70% 이상이면 갭투자 수요가 늘어난다.",
            "양도세 중과 폐지는 매물 출회를 늘려 단기 가격 안정화에 기여한다.",
        ],
        description="한국 주택시장 — 금리·규제·공급 3축 상호작용.",
    ),
    "환율": Scenario(
        name="환율",
        domain="finance",
        initial_state={
            "USD_KRW": 1350,
            "한미금리차_pp": -2.0,
            "무역수지_억달러_월간": 30,
            "외환보유액_억달러": 4150,
            "VIX_index": 18,
            "원유_WTI_달러": 82,
        },
        possible_actions=[
            "외환시장 구두개입",
            "외환시장 실개입 (USD 매도)",
            "기준금리 0.25%p 인상",
            "한미 통화스왑 체결",
            "수출 보조금 확대",
            "무대응",
        ],
        rules=[
            "한미금리차가 -2.0%p 이하로 벌어지면 자본 유출 압력이 커진다.",
            "무역수지 흑자 전환 시 원화 강세 압력.",
            "VIX 25 이상이면 안전자산 선호 → USD 강세, KRW 약세.",
            "구두개입 효과는 단기 (1~3일) 지속, 실개입은 1~2주.",
            "원유 가격 급등은 무역적자를 통해 원화 약세를 유발한다.",
        ],
        description="USD/KRW 환율 — 금리차·무역수지·글로벌 리스크.",
    ),
    "청년 실업률": Scenario(
        name="청년 실업률",
        domain="labor",
        initial_state={
            "청년실업률_pct": 6.4,
            "청년고용률_pct": 46.5,
            "최저시급_원": 9860,
            "제조업_신규채용_index": 92,
            "IT_신규채용_index": 110,
            "공무원_정원_변화_pct": -1.5,
            "대졸_니트_비율_pct": 18.0,
        },
        possible_actions=[
            "최저시급 5% 인상",
            "최저시급 동결",
            "청년 고용장려금 월 80만원 확대",
            "직무 재교육 바우처 100만원 지급",
            "공무원 채용 1만명 확대",
            "AI/SW 인재 5만명 양성 사업",
        ],
        rules=[
            "최저시급 급등은 단기 자영업 고용 위축을 유발한다.",
            "청년 고용장려금은 6개월 시차로 청년고용률을 1~2%p 끌어올린다.",
            "IT 채용지수가 100 이상이면 대졸 니트 비율이 감소한다.",
            "직무 재교육은 12개월 이상 누적되어야 효과가 측정된다.",
            "공공부문 채용 확대는 즉시 통계 개선이지만 재정부담이 누적된다.",
        ],
        description="한국 청년 노동시장 — 임금·일자리·교육 정책.",
    ),
    "법안 통과": Scenario(
        name="법안 통과",
        domain="policy",
        initial_state={
            "법안명": "AI 기본법",
            "발의정당": "여당",
            "여당_지지율_pct": 38,
            "야당_지지율_pct": 41,
            "여론_찬성_pct": 52,
            "여론_반대_pct": 33,
            "이해관계자_찬성": ["스타트업협회", "대기업IT"],
            "이해관계자_반대": ["시민단체", "노동조합"],
            "본회의_상정_여부": False,
            "법사위_통과": False,
        },
        possible_actions=[
            "여야 협상 테이블 구성",
            "공청회 3회 추가 개최",
            "수정안 발의 (규제 완화)",
            "수정안 발의 (안전장치 강화)",
            "본회의 직권상정",
            "법안 철회 후 재발의",
        ],
        rules=[
            "여론 찬성이 60% 이상이면 야당이 협상 테이블에 응할 가능성 증가.",
            "이해관계자 반대 진영이 노조를 포함하면 야당 결속이 강해진다.",
            "직권상정은 단기 통과율은 높이지만 차기 선거 지지율을 깎는다.",
            "공청회는 여론 변동 ±3%p 범위에서 영향을 준다.",
            "법사위 통과 없이 본회의 직행은 절차적 위헌 시비를 낳는다.",
        ],
        description="국회 법안 통과 시뮬레이션 — 여론·정당·이해관계자.",
    ),
    "기업 IPO": Scenario(
        name="기업 IPO",
        domain="finance",
        initial_state={
            "기업명": "가상AI㈜",
            "예상_시총_조원": 5.0,
            "최근_매출_증가율_yoy_pct": 65,
            "영업이익률_pct": 8,
            "코스피_index": 2680,
            "VIX_index": 18,
            "동종업계_PER": 35,
            "주관사": "대형증권사",
            "수요예측_경쟁률_x": 0,
            "공모가_밴드_하단_원": 32000,
            "공모가_밴드_상단_원": 38000,
        },
        possible_actions=[
            "공모가 밴드 상단 채택",
            "공모가 밴드 하단 채택",
            "공모가 밴드 상회 (오버 프라이싱)",
            "상장 일정 1개월 연기",
            "IR 로드쇼 해외 추가",
            "구주매출 비중 축소",
        ],
        rules=[
            "VIX 25 이상 또는 코스피 -3% 주간 하락 시 수요예측 경쟁률이 급락한다.",
            "동종업계 PER 보다 20% 이상 비싸게 책정하면 청약 미달 위험.",
            "구주매출 비중이 30% 이상이면 기관 수요가 위축된다.",
            "해외 IR 추가는 외국인 수요예측 참여를 5~15%p 끌어올린다.",
            "상장 직후 의무보유확약 비율이 낮으면 첫 주 변동성이 커진다.",
        ],
        description="국내 IPO — 시장상황·재무·공모구조.",
    ),
}


def list_scenarios() -> list[dict]:
    """모든 시나리오의 메타데이터 목록.

    UI 드롭다운/라우터 응답용. 큰 ``initial_state`` 는 키만 반환.
    """
    return [
        {
            "name": s.name,
            "domain": s.domain,
            "description": s.description,
            "state_keys": list(s.initial_state.keys()),
            "actions": s.possible_actions,
            "rule_count": len(s.rules),
        }
        for s in _SCENARIOS.values()
    ]


def get_scenario(name: str) -> Optional[Scenario]:
    """이름으로 시나리오 조회. 없으면 ``None``."""
    return _SCENARIOS.get(name)


__all__ = ["Scenario", "list_scenarios", "get_scenario"]
