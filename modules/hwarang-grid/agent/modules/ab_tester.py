"""모듈 5: A/B 테스트 에이전트

새 LoRA vs 기존 LoRA 자동 비교 → 어느 것이 나은지 판정.
마스터가 신규 배포 결정에 활용.

보상: A/B 테스트 1회 15 HWR
"""

import time, json, logging, random

logger = logging.getLogger(__name__)


class ABTestModule:
    def __init__(self, config):
        self.config = config

    def run_ab_test(self, endpoint_a: str, endpoint_b: str, test_prompts: list[str] = None) -> dict:
        """A vs B 모델 비교 테스트."""
        if not test_prompts:
            test_prompts = [
                "Python으로 퀵소트 구현해줘",
                "계약 해제와 해지의 차이는?",
                "종합소득세 신고 방법 알려줘",
                "React에서 useEffect 설명해줘",
                "부당해고 당하면 어떻게 해?",
            ]

        results = {"a_wins": 0, "b_wins": 0, "ties": 0, "details": []}

        for prompt in test_prompts[:self.config.samples_per_test]:
            resp_a = self._query(endpoint_a, prompt)
            resp_b = self._query(endpoint_b, prompt)

            # 품질 비교 (길이 + 구조 + 한국어 비율)
            score_a = self._score(resp_a)
            score_b = self._score(resp_b)

            if score_a > score_b + 0.5:
                results["a_wins"] += 1
                winner = "A"
            elif score_b > score_a + 0.5:
                results["b_wins"] += 1
                winner = "B"
            else:
                results["ties"] += 1
                winner = "tie"

            results["details"].append({
                "prompt": prompt[:50], "score_a": score_a, "score_b": score_b, "winner": winner
            })

        total = results["a_wins"] + results["b_wins"] + results["ties"]
        results["recommendation"] = "A" if results["a_wins"] > results["b_wins"] else "B" if results["b_wins"] > results["a_wins"] else "동일"
        results["confidence"] = abs(results["a_wins"] - results["b_wins"]) / max(total, 1)

        logger.info(f"A/B 결과: A={results['a_wins']}, B={results['b_wins']}, 추천={results['recommendation']}")
        return results

    def _query(self, endpoint: str, prompt: str) -> str:
        import urllib.request
        try:
            req = urllib.request.Request(
                f"{endpoint}/v1/chat/completions",
                data=json.dumps({"messages": [{"role": "user", "content": prompt}], "max_tokens": 500}).encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read())["choices"][0]["message"]["content"]
        except: return ""

    def _score(self, response: str) -> float:
        if not response: return 0
        score = 0
        if len(response) > 200: score += 2
        if "```" in response: score += 2
        if "**" in response: score += 1
        korean = sum(1 for c in response if '\uac00' <= c <= '\ud7af')
        if korean / max(len(response), 1) > 0.3: score += 2
        if any(w in response for w in ["주의", "참고", "권장"]): score += 1
        return score
