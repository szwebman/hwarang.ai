"""모듈 10: 번역 에이전트

다국어 학습 데이터 자동 번역.
영어 데이터 → 한국어 변환 (로컬 모델 사용).

보상: 번역 100건당 5 HWR
"""

import json, os, time, logging

logger = logging.getLogger(__name__)


class TranslatorModule:
    def __init__(self, config=None):
        self.translated_count = 0

    def translate_dataset(
        self,
        input_path: str,
        output_path: str,
        model_endpoint: str,
        source_lang: str = "en",
        target_lang: str = "ko",
        max_items: int = 1000,
    ) -> dict:
        """데이터셋 번역."""
        import urllib.request

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        translated = 0

        with open(input_path, encoding="utf-8") as fin, open(output_path, "w", encoding="utf-8") as fout:
            for line in fin:
                if translated >= max_items:
                    break
                try:
                    item = json.loads(line.strip())
                    messages = item.get("messages", [])

                    translated_messages = []
                    for msg in messages:
                        content = msg.get("content", "")
                        if source_lang == "en" and self._is_english(content):
                            translated_content = self._translate(model_endpoint, content, source_lang, target_lang)
                            translated_messages.append({**msg, "content": translated_content})
                        else:
                            translated_messages.append(msg)

                    fout.write(json.dumps({"messages": translated_messages}, ensure_ascii=False) + "\n")
                    translated += 1
                except Exception:
                    continue

        self.translated_count += translated
        return {"translated": translated, "output": output_path}

    def _translate(self, endpoint: str, text: str, src: str, tgt: str) -> str:
        import urllib.request
        prompt = f"다음 {src} 텍스트를 {tgt}로 번역하세요. 번역만 출력:\n\n{text}"
        try:
            req = urllib.request.Request(
                f"{endpoint}/v1/chat/completions",
                data=json.dumps({"messages": [{"role": "user", "content": prompt}], "max_tokens": 2048}).encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read())["choices"][0]["message"]["content"]
        except:
            return text

    def _is_english(self, text: str) -> bool:
        english = sum(1 for c in text if 'a' <= c.lower() <= 'z')
        return english / max(len(text), 1) > 0.5
