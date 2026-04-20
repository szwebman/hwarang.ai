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
        """번역 실행. HTTP 엔드포인트 → 로컬 모델 → 원본 반환 순."""
        import urllib.request

        lang_names = {"en": "영어", "ko": "한국어", "ja": "일본어", "zh": "중국어"}
        src_name = lang_names.get(src, src)
        tgt_name = lang_names.get(tgt, tgt)
        prompt = f"다음 {src_name} 텍스트를 {tgt_name}로 번역하세요. 번역만 출력:\n\n{text}"

        # 방법 1: HTTP 엔드포인트
        if endpoint and endpoint.startswith("http"):
            try:
                req = urllib.request.Request(
                    f"{endpoint}/v1/chat/completions",
                    data=json.dumps({
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2048,
                    }).encode(),
                    headers={"Content-Type": "application/json"},
                )
                resp = urllib.request.urlopen(req, timeout=60)
                return json.loads(resp.read())["choices"][0]["message"]["content"]
            except Exception:
                pass

        # 방법 2: 로컬 모델
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            if not hasattr(self, "_model"):
                model_path = None
                for p in [
                    os.path.expanduser("~/.hwarang/models/qwen2.5-7b"),
                    "/mnt/nvme2/hwarang/models/qwen2.5-32b",
                ]:
                    if os.path.exists(p):
                        model_path = p
                        break

                if model_path:
                    from transformers import BitsAndBytesConfig
                    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
                    self._tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
                    self._model = AutoModelForCausalLM.from_pretrained(
                        model_path, quantization_config=bnb, device_map="auto", trust_remote_code=True)

            if hasattr(self, "_model"):
                messages = [{"role": "user", "content": prompt}]
                chat_text = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = self._tokenizer(chat_text, return_tensors="pt").to(self._model.device)
                outputs = self._model.generate(**inputs, max_new_tokens=2048)
                return self._tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"로컬 번역 실패: {e}")

        # 폴백: 원본 반환
        return text

    def _is_english(self, text: str) -> bool:
        english = sum(1 for c in text if 'a' <= c.lower() <= 'z')
        return english / max(len(text), 1) > 0.5
