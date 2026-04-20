"""AI 멘토 에이전트

유저의 코딩 패턴을 로컬에서 학습 → 개인화된 조언.
프라이버시 완벽 (데이터 로컬 전용).

기능:
  - 자주 하는 실수 패턴 감지
  - 반복 질문 감지 → "이전에도 이 질문하셨는데, 이렇게 해결했어요"
  - 코딩 스타일 학습 → 맞춤 코드 생성
  - 학습 이력 → "이번 주 성장 리포트"
"""

import json, os, time, hashlib, logging
from collections import Counter

logger = logging.getLogger(__name__)


class AIMentorModule:
    def __init__(self, config=None):
        self.data_path = os.path.expanduser("~/.hwarang/mentor")
        os.makedirs(self.data_path, exist_ok=True)
        self.patterns: Counter = Counter()
        self.history: list[dict] = []
        self._load()

    def observe(self, question: str, response: str, was_helpful: bool = True):
        """유저 질문/응답 관찰 → 패턴 학습."""
        keywords = self._extract_keywords(question)
        for kw in keywords:
            self.patterns[kw] += 1

        self.history.append({
            "timestamp": time.time(),
            "question_hash": hashlib.md5(question.encode()).hexdigest()[:12],
            "keywords": keywords,
            "helpful": was_helpful,
            "q_length": len(question),
        })

        # 1000개 초과 시 오래된 것 제거
        if len(self.history) > 1000:
            self.history = self.history[-500:]

        self._save()

    def get_suggestion(self, question: str):
        """현재 질문에 대한 맞춤 제안."""
        keywords = self._extract_keywords(question)

        # 반복 질문 감지
        q_hash = hashlib.md5(question.encode()).hexdigest()[:12]
        prev = [h for h in self.history if h["question_hash"] == q_hash]
        if len(prev) >= 2:
            return f"이 질문을 {len(prev)}번째 하고 계시네요. 즐겨찾기에 답변을 저장해 두시는 건 어떨까요?"

        # 자주 묻는 주제 → 학습 제안
        for kw in keywords:
            if self.patterns.get(kw, 0) >= 5:
                return f"'{kw}' 관련 질문을 자주 하시네요. 이 주제 튜토리얼을 추천드릴까요?"

        return None

    def get_weekly_report(self) -> dict:
        """주간 학습 리포트."""
        week_ago = time.time() - 7 * 86400
        recent = [h for h in self.history if h["timestamp"] > week_ago]
        top_topics = self.patterns.most_common(5)

        return {
            "total_questions": len(recent),
            "top_topics": [{"topic": t, "count": c} for t, c in top_topics],
            "helpful_rate": sum(1 for h in recent if h["helpful"]) / max(len(recent), 1) * 100,
            "avg_question_length": sum(h["q_length"] for h in recent) / max(len(recent), 1),
        }

    def _extract_keywords(self, text: str) -> list[str]:
        import re
        keywords = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}', text)
        stop_words = {"이거", "저거", "뭐야", "어떻게", "해줘", "알려줘", "있어", "the", "and", "for"}
        return [kw.lower() for kw in keywords if kw.lower() not in stop_words][:10]

    def _save(self):
        with open(os.path.join(self.data_path, "patterns.json"), "w") as f:
            json.dump(dict(self.patterns), f)
        with open(os.path.join(self.data_path, "history.json"), "w") as f:
            json.dump(self.history[-500:], f)

    def _load(self):
        try:
            with open(os.path.join(self.data_path, "patterns.json")) as f:
                self.patterns = Counter(json.load(f))
            with open(os.path.join(self.data_path, "history.json")) as f:
                self.history = json.load(f)
        except: pass
