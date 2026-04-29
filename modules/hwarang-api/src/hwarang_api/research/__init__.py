"""화랑 Research Engine — Group A.

매일 arXiv 논문 수집 + PDF 파싱 + 화랑 도메인 필터링.

서브모듈:
  - arxiv_crawler: arxiv API 어댑터 (daily_arxiv_cycle)
  - paper_parser:  PDF → 구조화 (parse_pending_papers)
  - filters:       LLM 기반 정밀 관련성 평가
"""

from hwarang_api.research.arxiv_crawler import (
    daily_arxiv_cycle,
    fetch_recent_papers,
    is_hwarang_relevant,
)
from hwarang_api.research.paper_parser import parse_pending_papers
from hwarang_api.research.filters import evaluate_relevance
from hwarang_api.research.auto_summarizer import (
    summarize_one,
    summarize_pending_papers,
)
from hwarang_api.research.trend_tracker import (
    get_recent_trends,
    weekly_trend_analysis,
)
from hwarang_api.research.application_engine import (
    analyze_summarized_papers,
    approve_application,
    list_pending_applications,
    reject_application,
)

__all__ = [
    "daily_arxiv_cycle",
    "fetch_recent_papers",
    "is_hwarang_relevant",
    "parse_pending_papers",
    "evaluate_relevance",
    "summarize_one",
    "summarize_pending_papers",
    "weekly_trend_analysis",
    "get_recent_trends",
    "analyze_summarized_papers",
    "approve_application",
    "reject_application",
    "list_pending_applications",
]
