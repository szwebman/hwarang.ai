"""에이전트 최적화 모듈

1. 모델 메모리 캐시 (GPU 상주)
2. 자동 복구 + 체크포인트
3. 추론 배치 처리
4. HTTP 커넥션 풀링
5. 학습 데이터 글로벌 중복 제거
6. 델타 LoRA 동기화
"""

import hashlib
import json
import logging
import os
import signal
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from queue import Queue, Empty

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 1. 모델 메모리 캐시 (GPU 상주 - 매번 로드 방지)
# ════════════════════════════════════════════════════════════════

class ModelCache:
    """모델을 GPU 메모리에 캐시하여 재사용.

    매번 로드하면 32B 모델 기준 2-3분 걸림.
    캐시하면 즉시 사용 가능.
    """

    def __init__(self, max_models: int = 2):
        self.max_models = max_models
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, model_path: str):
        """캐시에서 모델 가져오기. 없으면 로드."""
        with self._lock:
            if model_path in self._cache:
                self._cache.move_to_end(model_path)
                logger.debug(f"모델 캐시 HIT: {model_path}")
                return self._cache[model_path]

        # 캐시 미스 → 로드
        model_data = self._load_model(model_path)
        if model_data:
            with self._lock:
                if len(self._cache) >= self.max_models:
                    evicted_path, evicted = self._cache.popitem(last=False)
                    self._unload_model(evicted)
                    logger.info(f"모델 캐시 EVICT: {evicted_path}")

                self._cache[model_path] = model_data
                logger.info(f"모델 캐시 LOAD: {model_path}")

        return model_data

    def _load_model(self, model_path: str):
        """모델 로드."""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # GPU 감지
            try:
                from modules.gpu_detector import get_torch_device
                device = get_torch_device()
            except ImportError:
                device = "cuda" if torch.cuda.is_available() else "cpu"

            tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

            load_kwargs = {"trust_remote_code": True, "low_cpu_mem_usage": True}

            if device == "cuda":
                from transformers import BitsAndBytesConfig
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
                )
                load_kwargs["device_map"] = "auto"
            elif device == "mps":
                load_kwargs["torch_dtype"] = torch.float16
                load_kwargs["device_map"] = "auto"
            else:
                load_kwargs["torch_dtype"] = torch.float32
                load_kwargs["device_map"] = "cpu"

            model = AutoModelForCausalLM.from_pretrained(model_path, **load_kwargs)

            return {"model": model, "tokenizer": tokenizer, "device": device, "loaded_at": time.time()}

        except Exception as e:
            logger.error(f"모델 로드 실패: {e}")
            return None

    def _unload_model(self, model_data: dict):
        """모델 메모리 해제."""
        try:
            import torch
            del model_data["model"]
            del model_data["tokenizer"]
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def clear(self):
        """전체 캐시 해제."""
        with self._lock:
            for path, data in self._cache.items():
                self._unload_model(data)
            self._cache.clear()

    def stats(self) -> dict:
        return {
            "cached_models": list(self._cache.keys()),
            "count": len(self._cache),
            "max": self.max_models,
        }


# 전역 캐시 (싱글톤)
_model_cache = ModelCache(max_models=2)

def get_model_cache() -> ModelCache:
    return _model_cache


# ════════════════════════════════════════════════════════════════
# 2. 자동 복구 + 체크포인트
# ════════════════════════════════════════════════════════════════

class AgentWatchdog:
    """에이전트 크래시 감지 및 자동 복구."""

    def __init__(self, state_dir: str = None):
        self.state_dir = state_dir or os.path.expanduser("~/.hwarang/state")
        os.makedirs(self.state_dir, exist_ok=True)
        self.pid_file = os.path.join(self.state_dir, "agent.pid")
        self.state_file = os.path.join(self.state_dir, "agent_state.json")
        self.crash_count_file = os.path.join(self.state_dir, "crash_count")

    def start(self):
        """PID 기록 + 이전 크래시 확인."""
        # 이전 PID 확인 (비정상 종료 감지)
        if os.path.exists(self.pid_file):
            try:
                old_pid = int(open(self.pid_file).read().strip())
                # 프로세스가 없으면 크래시였음
                try:
                    os.kill(old_pid, 0)
                except OSError:
                    self._on_crash_detected(old_pid)
            except (ValueError, IOError):
                pass

        # 현재 PID 기록
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

    def save_checkpoint(self, state: dict):
        """현재 상태 체크포인트 저장."""
        state["checkpoint_at"] = time.time()
        state["pid"] = os.getpid()

        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, self.state_file)

    def load_checkpoint(self):
        """마지막 체크포인트 로드."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    state = json.load(f)
                logger.info(f"체크포인트 복원: {time.ctime(state.get('checkpoint_at', 0))}")
                return state
            except Exception:
                pass
        return None

    def cleanup(self):
        """정상 종료 시 PID 파일 정리."""
        for f in [self.pid_file]:
            if os.path.exists(f):
                os.remove(f)

    def _on_crash_detected(self, old_pid: int):
        """크래시 감지 시 처리."""
        crash_count = self._get_crash_count() + 1
        self._set_crash_count(crash_count)

        logger.warning(f"이전 크래시 감지 (PID: {old_pid}, 총 {crash_count}회)")

        if crash_count >= 5:
            logger.error("연속 크래시 5회 → 안전 모드로 시작")

    def _get_crash_count(self) -> int:
        try:
            return int(open(self.crash_count_file).read().strip())
        except Exception:
            return 0

    def _set_crash_count(self, count: int):
        with open(self.crash_count_file, "w") as f:
            f.write(str(count))

    def reset_crash_count(self):
        """정상 운영 확인 후 크래시 카운트 리셋."""
        self._set_crash_count(0)


# ════════════════════════════════════════════════════════════════
# 3. 추론 배치 처리
# ════════════════════════════════════════════════════════════════

class InferenceBatcher:
    """여러 추론 요청을 배치로 모아서 처리.

    개별 요청: 100ms/건 × 10건 = 1초
    배치 처리: 300ms/10건 = 300ms (3배 빠름)
    """

    def __init__(self, max_batch_size: int = 8, max_wait_ms: float = 100):
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self._queue: Queue = Queue()
        self._running = False
        self._thread = None

    def start(self, model_path: str):
        """배치 처리 시작."""
        self._model_path = model_path
        self._running = True
        self._thread = threading.Thread(target=self._batch_loop, daemon=True, name="batcher")
        self._thread.start()
        logger.info(f"배치 추론 시작 (max_batch={self.max_batch_size}, wait={self.max_wait_ms}ms)")

    def stop(self):
        self._running = False

    def infer(self, prompt: str, max_tokens: int = 512, timeout: float = 30) -> str:
        """추론 요청 (자동 배치)."""
        result_event = threading.Event()
        result_holder = {"output": "", "error": None}

        self._queue.put({
            "prompt": prompt,
            "max_tokens": max_tokens,
            "result": result_holder,
            "event": result_event,
            "submitted_at": time.time(),
        })

        result_event.wait(timeout=timeout)

        if result_holder["error"]:
            raise RuntimeError(result_holder["error"])
        return result_holder["output"]

    def _batch_loop(self):
        """배치 수집 → 일괄 추론."""
        while self._running:
            batch = []
            deadline = time.time() + self.max_wait_ms / 1000

            # 배치 수집
            while len(batch) < self.max_batch_size and time.time() < deadline:
                try:
                    item = self._queue.get(timeout=self.max_wait_ms / 1000)
                    batch.append(item)
                except Empty:
                    break

            if not batch:
                continue

            # 일괄 추론
            try:
                cache = get_model_cache()
                model_data = cache.get(self._model_path)

                if not model_data:
                    for item in batch:
                        item["result"]["error"] = "모델 로드 실패"
                        item["event"].set()
                    continue

                model = model_data["model"]
                tokenizer = model_data["tokenizer"]

                for item in batch:
                    try:
                        messages = [{"role": "user", "content": item["prompt"]}]
                        text = tokenizer.apply_chat_template(
                            messages, tokenize=False, add_generation_prompt=True,
                        )
                        inputs = tokenizer(text, return_tensors="pt", padding=True)

                        import torch
                        device = next(model.parameters()).device
                        inputs = {k: v.to(device) for k, v in inputs.items()}

                        with torch.no_grad():
                            outputs = model.generate(**inputs, max_new_tokens=item["max_tokens"])

                        response = tokenizer.decode(
                            outputs[0][inputs["input_ids"].shape[1]:],
                            skip_special_tokens=True,
                        )
                        item["result"]["output"] = response
                    except Exception as e:
                        item["result"]["error"] = str(e)
                    finally:
                        item["event"].set()

            except Exception as e:
                for item in batch:
                    item["result"]["error"] = str(e)
                    item["event"].set()

    def stats(self) -> dict:
        return {
            "pending": self._queue.qsize(),
            "max_batch": self.max_batch_size,
            "max_wait_ms": self.max_wait_ms,
        }


# ════════════════════════════════════════════════════════════════
# 4. HTTP 커넥션 풀링
# ════════════════════════════════════════════════════════════════

class ConnectionPool:
    """HTTP 커넥션 풀 (Keep-Alive 재사용)."""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._client = None

    def get_client(self):
        """httpx 클라이언트 (커넥션 풀 내장)."""
        if self._client is None:
            try:
                import httpx
                self._client = httpx.Client(
                    timeout=30,
                    limits=httpx.Limits(
                        max_keepalive_connections=5,
                        max_connections=10,
                        keepalive_expiry=300,  # 5분 Keep-Alive
                    ),
                    headers={"User-Agent": "HwarangAgent/1.0"},
                    follow_redirects=True,
                )
            except ImportError:
                return None
        return self._client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None


# ════════════════════════════════════════════════════════════════
# 5. 학습 데이터 글로벌 중복 제거
# ════════════════════════════════════════════════════════════════

class DataDeduplicator:
    """학습 데이터 중복 제거.

    각 에이전트가 수집한 데이터에서 중복을 제거.
    - 로컬: 에이전트 내 중복 제거
    - 글로벌: 마스터에서 전체 에이전트 간 중복 제거
    """

    def __init__(self, bloom_size: int = 1_000_000):
        self._seen_hashes: set[str] = set()
        self._hash_file = os.path.expanduser("~/.hwarang/dedup_hashes.txt")
        self._load_hashes()

    def _load_hashes(self):
        if os.path.exists(self._hash_file):
            with open(self._hash_file) as f:
                self._seen_hashes = set(line.strip() for line in f if line.strip())

    def _save_hashes(self):
        os.makedirs(os.path.dirname(self._hash_file), exist_ok=True)
        # 최근 100K만 유지
        recent = list(self._seen_hashes)[-100_000:]
        with open(self._hash_file, "w") as f:
            f.write("\n".join(recent))

    def is_duplicate(self, text: str) -> bool:
        """텍스트가 중복인지 확인."""
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        if h in self._seen_hashes:
            return True
        self._seen_hashes.add(h)
        return False

    def deduplicate_jsonl(self, input_path: str, output_path: str = None) -> dict:
        """JSONL 파일에서 중복 제거."""
        if output_path is None:
            output_path = input_path + ".dedup"

        total = 0
        unique = 0
        duplicates = 0

        with open(input_path, encoding="utf-8") as fin, \
             open(output_path, "w", encoding="utf-8") as fout:
            for line in fin:
                total += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    item = json.loads(line)
                    # messages의 content를 합쳐서 해시
                    content = " ".join(
                        m.get("content", "")
                        for m in item.get("messages", [])
                    )

                    if not self.is_duplicate(content):
                        fout.write(line + "\n")
                        unique += 1
                    else:
                        duplicates += 1
                except json.JSONDecodeError:
                    continue

        self._save_hashes()

        logger.info(f"중복 제거: {total}건 → {unique}건 (중복 {duplicates}건 제거)")
        return {
            "total": total,
            "unique": unique,
            "duplicates": duplicates,
            "output": output_path,
        }

    def sync_with_master(self, master_url: str, agent_id: str):
        """마스터와 해시 동기화 (글로벌 중복 제거)."""
        try:
            pool = ConnectionPool.get()
            client = pool.get_client()
            if not client:
                return

            # 내 해시 목록 전송
            recent_hashes = list(self._seen_hashes)[-10000:]
            response = client.post(
                f"{master_url}/grid/data/dedup-sync",
                json={"agent_id": agent_id, "hashes": recent_hashes},
            )

            if response.status_code == 200:
                result = response.json()
                # 마스터에서 받은 글로벌 해시 추가
                global_hashes = result.get("global_hashes", [])
                self._seen_hashes.update(global_hashes)
                self._save_hashes()
                logger.info(f"글로벌 중복 동기화: +{len(global_hashes)}개 해시")

        except Exception as e:
            logger.debug(f"중복 동기화 실패: {e}")


# ════════════════════════════════════════════════════════════════
# 6. 델타 LoRA 동기화
# ════════════════════════════════════════════════════════════════

class DeltaSync:
    """변경된 텐서만 전송하는 델타 동기화.

    전체 LoRA (50MB) 대신 변경분만 전송 (1-5MB).
    """

    def __init__(self):
        self._previous_checksums: dict[str, str] = {}
        self._checksum_file = os.path.expanduser("~/.hwarang/lora_checksums.json")
        self._load_checksums()

    def _load_checksums(self):
        if os.path.exists(self._checksum_file):
            with open(self._checksum_file) as f:
                self._previous_checksums = json.load(f)

    def _save_checksums(self, checksums: dict):
        self._previous_checksums = checksums
        os.makedirs(os.path.dirname(self._checksum_file), exist_ok=True)
        with open(self._checksum_file, "w") as f:
            json.dump(checksums, f)

    def compute_delta(self, lora_path: str):
        """변경된 텐서만 추출."""
        try:
            from safetensors.torch import load_file
            state = load_file(os.path.join(lora_path, "adapter_model.safetensors"))
        except Exception:
            return None, {}

        current_checksums = {}
        changed_tensors = {}

        for name, tensor in state.items():
            tensor_bytes = tensor.cpu().numpy().tobytes()
            checksum = hashlib.md5(tensor_bytes).hexdigest()
            current_checksums[name] = checksum

            if checksum != self._previous_checksums.get(name):
                changed_tensors[name] = tensor

        self._save_checksums(current_checksums)

        total = len(state)
        changed = len(changed_tensors)
        logger.info(f"델타 분석: {changed}/{total} 텐서 변경 ({changed/max(total,1)*100:.0f}%)")

        return changed_tensors, current_checksums

    def apply_delta(self, base_lora_path: str, delta_tensors: dict, output_path: str):
        """기존 LoRA에 델타 적용."""
        try:
            from safetensors.torch import load_file, save_file

            state = load_file(os.path.join(base_lora_path, "adapter_model.safetensors"))

            # 변경된 텐서만 교체
            for name, tensor in delta_tensors.items():
                state[name] = tensor

            os.makedirs(output_path, exist_ok=True)
            save_file(state, os.path.join(output_path, "adapter_model.safetensors"))

            logger.info(f"델타 적용: {len(delta_tensors)}개 텐서 교체 → {output_path}")
        except Exception as e:
            logger.error(f"델타 적용 실패: {e}")
