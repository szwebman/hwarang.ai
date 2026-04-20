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
        lora_r: int = 8,
        lora_alpha: int = 16,
        lr: float = 2e-4,
        max_seq_length: int = 2048,
    ) -> dict:
        """로컬 LoRA 학습.

        별도 스크립트 없이 에이전트 내장 학습 엔진으로 실행.
        GPU가 있으면 QLoRA(4bit), 없으면 실패.
        """
        output_dir = os.path.join(self.lora_path, lora_name)
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"로컬 LoRA 학습 시작: {lora_name}")
        logger.info(f"  모델: {model_path}")
        logger.info(f"  데이터: {data_path}")
        logger.info(f"  설정: r={lora_r}, alpha={lora_alpha}, lr={lr}, epochs={epochs}")

        try:
            import torch
            from transformers import (
                AutoModelForCausalLM, AutoTokenizer,
                TrainingArguments, BitsAndBytesConfig,
            )
            from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
            from trl import SFTTrainer
            from datasets import Dataset
        except ImportError as e:
            logger.error(f"학습 패키지 없음: {e}")
            logger.error("설치: pip install hwarang-agent[gpu]")
            return {"status": "failed", "error": f"패키지 없음: {e}"}

        try:
            # 1. 데이터 로드
            conversations = []
            with open(data_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        messages = item.get("messages", [])
                        if len(messages) >= 2:
                            conversations.append(messages)
                    except json.JSONDecodeError:
                        continue

            if not conversations:
                return {"status": "failed", "error": "학습 데이터 없음"}

            logger.info(f"  데이터: {len(conversations)}건 로드")

            # ChatML 형식으로 변환
            def format_conversation(messages):
                text = ""
                for msg in messages:
                    text += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
                return text

            formatted = [{"text": format_conversation(conv)} for conv in conversations]
            dataset = Dataset.from_list(formatted)

            # 2. 모델 로드 (4bit 양자화)
            logger.info("  모델 로드 중 (INT4 양자화)...")
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )

            model = AutoModelForCausalLM.from_pretrained(
                model_path,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True,
            )

            tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            logger.info(f"  VRAM 사용: {torch.cuda.memory_allocated() / 1e9:.1f}GB")

            # 3. LoRA 설정
            model = prepare_model_for_kbit_training(model)
            lora_config = LoraConfig(
                r=lora_r,
                lora_alpha=lora_alpha,
                lora_dropout=0.05,
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                "gate_proj", "up_proj", "down_proj"],
                bias="none",
                task_type="CAUSAL_LM",
            )
            model = get_peft_model(model, lora_config)

            trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
            total = sum(p.numel() for p in model.parameters())
            logger.info(f"  학습 파라미터: {trainable:,} ({trainable/total*100:.2f}%)")

            # 4. 학습 실행
            training_args = TrainingArguments(
                output_dir=output_dir,
                num_train_epochs=epochs,
                per_device_train_batch_size=1,
                gradient_accumulation_steps=8,
                learning_rate=lr,
                warmup_ratio=0.1,
                lr_scheduler_type="cosine",
                bf16=True,
                logging_steps=10,
                save_steps=500,
                save_total_limit=2,
                optim="paged_adamw_8bit",
                gradient_checkpointing=True,
                gradient_checkpointing_kwargs={"use_reentrant": False},
                report_to="none",
            )

            trainer = SFTTrainer(
                model=model,
                args=training_args,
                train_dataset=dataset,
                processing_class=tokenizer,
                max_seq_length=max_seq_length,
            )

            logger.info("  학습 실행 중...")
            train_result = trainer.train()
            final_loss = train_result.training_loss

            # 5. 저장
            model.save_pretrained(output_dir)
            tokenizer.save_pretrained(output_dir)

            # 메타데이터
            metadata = {
                "base_model": model_path,
                "data": data_path,
                "data_count": len(conversations),
                "epochs": epochs,
                "lora_r": lora_r,
                "lora_alpha": lora_alpha,
                "final_loss": final_loss,
                "training_steps": trainer.state.global_step,
                "trainable_params": trainable,
                "trained_at": time.time(),
            }
            with open(os.path.join(output_dir, "metadata.json"), "w") as f:
                json.dump(metadata, f, indent=2)

            self.trained_loras.append({
                "name": lora_name,
                "path": output_dir,
                "trained_at": time.time(),
                "final_loss": final_loss,
                "steps": trainer.state.global_step,
            })

            logger.info(f"✅ 로컬 LoRA 완료: {output_dir} (loss: {final_loss:.4f})")

            # GPU 메모리 해제
            del model, trainer
            torch.cuda.empty_cache()

            return {"status": "success", "path": output_dir, "loss": final_loss}

        except torch.cuda.OutOfMemoryError:
            logger.error("GPU 메모리 부족! 모델 크기를 줄이거나 batch_size를 줄여주세요.")
            torch.cuda.empty_cache()
            return {"status": "failed", "error": "GPU OOM"}

        except Exception as e:
            logger.error(f"학습 에러: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "failed", "error": str(e)}

    def share_lora(self, lora_name: str, master_url: str,
                    agent_id: str = "", round_id: str = "") -> dict:
        """학습된 LoRA를 Grid 마스터에 업로드 (코인 보상).

        에이전트가 학습 완료 후 호출 → 마스터가 수집 → 통합 → 재배포.
        데이터가 아닌 LoRA 가중치(~2-50MB)만 전송 (프라이버시 유지).
        """
        lora_info = next((l for l in self.trained_loras if l["name"] == lora_name), None)
        if not lora_info:
            return {"error": "LoRA 없음"}

        lora_path = lora_info["path"]
        adapter_file = os.path.join(lora_path, "adapter_model.safetensors")

        if not os.path.exists(adapter_file):
            return {"error": f"LoRA 파일 없음: {adapter_file}"}

        logger.info(f"LoRA 업로드 시작: {lora_name} → {master_url}")

        try:
            import httpx

            # 메타데이터 수집
            metadata = {
                "lora_name": lora_name,
                "trained_at": lora_info.get("trained_at", 0),
                "training_steps": lora_info.get("steps", 0),
                "final_loss": lora_info.get("final_loss", 0),
            }

            # 마스터에 LoRA 파일 업로드
            submit_url = f"{master_url}/hfl/submit/{round_id}" if round_id else f"{master_url}/hfl/submit/manual"

            with open(adapter_file, "rb") as f:
                response = httpx.post(
                    submit_url,
                    data={
                        "agent_id": agent_id,
                        "metadata": json.dumps(metadata),
                    },
                    files={"lora_file": ("adapter_model.safetensors", f)},
                    timeout=300,  # 대용량 파일 업로드 대기
                )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"✅ LoRA 업로드 성공: {lora_name} "
                    f"(검증: {result.get('verified')}, "
                    f"품질: {result.get('quality_score', 0):.2f})"
                )
                return {
                    "status": "uploaded",
                    "lora": lora_name,
                    "server_response": result,
                }
            else:
                logger.error(f"업로드 실패: HTTP {response.status_code}")
                return {"status": "failed", "http_code": response.status_code}

        except ImportError:
            logger.error("httpx 패키지 필요: pip install httpx")
            return {"error": "httpx 패키지 없음"}
        except Exception as e:
            logger.error(f"업로드 에러: {e}")
            return {"status": "failed", "error": str(e)}

    def pull_latest_lora(self, master_url: str) -> dict:
        """마스터에서 최신 통합 LoRA 다운로드.

        마스터가 여러 에이전트의 LoRA를 통합(FedAvg)한 결과를 받아옴.
        """
        try:
            import httpx

            # 버전 확인
            version_resp = httpx.get(f"{master_url}/hfl/lora/version", timeout=10)
            version_info = version_resp.json()
            server_version = version_info.get("version", 0)

            local_version_file = os.path.join(self.lora_path, ".current_version")
            local_version = 0
            if os.path.exists(local_version_file):
                local_version = int(open(local_version_file).read().strip())

            if server_version <= local_version:
                return {"status": "up_to_date", "version": local_version}

            # 새 LoRA 다운로드
            logger.info(f"새 LoRA 다운로드: v{local_version} → v{server_version}")
            lora_resp = httpx.get(f"{master_url}/hfl/lora/latest", timeout=120)

            if lora_resp.status_code != 200:
                return {"error": f"다운로드 실패: HTTP {lora_resp.status_code}"}

            # 저장
            save_dir = os.path.join(self.lora_path, f"grid_v{server_version}")
            os.makedirs(save_dir, exist_ok=True)

            save_path = os.path.join(save_dir, "adapter_model.safetensors")
            with open(save_path, "wb") as f:
                f.write(lora_resp.content)

            # 버전 기록
            with open(local_version_file, "w") as f:
                f.write(str(server_version))

            size_mb = len(lora_resp.content) / 1024 / 1024
            logger.info(f"✅ LoRA v{server_version} 다운로드 완료 ({size_mb:.1f}MB)")

            return {
                "status": "updated",
                "version": server_version,
                "path": save_dir,
                "size_mb": round(size_mb, 1),
            }

        except Exception as e:
            logger.error(f"다운로드 에러: {e}")
            return {"error": str(e)}

    def list_loras(self) -> list[dict]:
        """로컬 LoRA 목록."""
        return self.trained_loras
