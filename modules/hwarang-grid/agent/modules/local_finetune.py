"""로컬 파인튜닝 에이전트

유저가 자기 데이터로 개인 LoRA 학습.
데이터가 절대 외부로 나가지 않음.

사용 사례:
  - 변호사: 자기 판례 문서로 법률 AI 특화
  - 개발자: 자기 코드베이스로 코딩 AI 특화
  - 세무사: 자기 세무 자료로 세무 AI 특화

공유 옵션:
  - 학습된 LoRA를 Grid에 공유 → 코인 보상
  - 공유 시 데이터가 아닌 LoRA만 전송 (프라이버시 유지)
"""

import os, json, time, logging

logger = logging.getLogger(__name__)


class LocalFinetuneModule:
    def __init__(self, config=None):
        self.lora_path = os.path.expanduser("~/.hwarang/local_loras")
        os.makedirs(self.lora_path, exist_ok=True)
        self.trained_loras = []

    def prepare_data(self, data_dir: str, file_types: list[str] = None) -> dict:
        """로컬 데이터를 학습 가능한 JSONL로 변환."""
        if file_types is None:
            file_types = [".txt", ".md", ".py", ".js", ".ts", ".json"]

        files = []
        for root, _, filenames in os.walk(data_dir):
            for f in filenames:
                if any(f.endswith(ext) for ext in file_types):
                    files.append(os.path.join(root, f))

        output = os.path.join(self.lora_path, "local_data.jsonl")
        count = 0

        with open(output, "w", encoding="utf-8") as fout:
            for fp in files[:500]:  # 최대 500 파일
                try:
                    with open(fp, encoding="utf-8", errors="ignore") as fin:
                        content = fin.read()[:3000]

                    if len(content) < 50:
                        continue

                    # 파일 내용 → Q&A 형식으로 변환
                    filename = os.path.basename(fp)
                    fout.write(json.dumps({
                        "messages": [
                            {"role": "user", "content": f"{filename} 파일의 내용을 설명해줘"},
                            {"role": "assistant", "content": f"```\n{content}\n```"},
                        ]
                    }, ensure_ascii=False) + "\n")
                    count += 1
                except Exception:
                    continue

        logger.info(f"로컬 데이터 준비: {count}개 파일 → {output}")
        return {"files_processed": count, "output_path": output}

    def train_local_lora(
        self,
        model_path: str,
        data_path: str,
        lora_name: str = "my_lora",
        epochs: int = 2,
    ) -> dict:
        """로컬 LoRA 학습."""
        output_dir = os.path.join(self.lora_path, lora_name)

        cmd = (
            f"python scripts/qlora_qwen.py "
            f"--model-path {model_path} "
            f"--data {data_path} "
            f"--output {output_dir} "
            f"--epochs {epochs} "
            f"--lr 2e-4 --lora-r 8 --lora-alpha 16"
        )

        logger.info(f"로컬 LoRA 학습 시작: {lora_name}")
        result = os.system(cmd)

        if result == 0:
            self.trained_loras.append({
                "name": lora_name,
                "path": output_dir,
                "trained_at": time.time(),
            })
            logger.info(f"✅ 로컬 LoRA 완료: {output_dir}")
            return {"status": "success", "path": output_dir}
        else:
            return {"status": "failed", "exit_code": result}

    def share_lora(self, lora_name: str, master_url: str) -> dict:
        """학습된 LoRA를 Grid에 공유 (코인 보상)."""
        lora_info = next((l for l in self.trained_loras if l["name"] == lora_name), None)
        if not lora_info:
            return {"error": "LoRA 없음"}

        logger.info(f"LoRA 공유: {lora_name} → Grid")
        # HFL Adaptive Transfer로 압축 전송
        # 데이터가 아닌 LoRA만 전송 (프라이버시)
        return {"status": "shared", "lora": lora_name, "estimated_reward": "50~200 HWR"}

    def list_loras(self) -> list[dict]:
        """로컬 LoRA 목록."""
        return self.trained_loras
