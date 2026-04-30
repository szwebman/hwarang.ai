"""음성 STT — faster-whisper 로 한국어 + 영어 혼용 음성 → 텍스트.

화랑 정체성 유지 위해 OpenAI Whisper API 안 쓰고 local 모델 사용.
RTX 3090 의 VLM 과 GPU 공유 (~3GB VRAM 추가).

흐름:
  1. multipart/form-data 로 음성 파일 받음
  2. 임시 파일에 저장
  3. faster-whisper 로 transcribe (한국어 우선, 영어 자동 감지)
  4. 텍스트 + 언어 + 신뢰도 반환

엔드포인트:
  POST /api/audio/transcribe
    multipart: file (audio/*)
    optional: language (default "ko")
    optional: prompt (이전 컨텍스트, hint 용)

  Response:
    {
      "text": "변환된 텍스트",
      "language": "ko",
      "duration_sec": 5.3,
      "segments": [...]
    }
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audio", tags=["Audio/STT"])


# Lazy 로드 — 서버 시작 시 모델 로드 안 함, 첫 요청 시 로드.
# 이렇게 해야 startup 빨라지고, STT 안 쓰는 환경에서는 메모리 절약.
_WHISPER_MODEL = None
_MODEL_NAME = os.getenv("HWARANG_WHISPER_MODEL", "large-v3")
_DEVICE = os.getenv("HWARANG_WHISPER_DEVICE", "cuda")
_COMPUTE_TYPE = os.getenv("HWARANG_WHISPER_COMPUTE", "int8_float16")


def _get_model():
    """Lazy 로드 + 캐싱. 첫 호출만 ~5초, 이후 즉시 반환."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is not None:
        return _WHISPER_MODEL

    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        # graceful: 미설치 환경에서는 503 + 안내 (서버 자체는 동작)
        raise HTTPException(
            status_code=503,
            detail="faster-whisper 미설치. 서버 관리자에게 문의: poetry add faster-whisper",
        )

    logger.info(
        "Whisper 모델 로드 중: %s (device=%s, compute=%s)",
        _MODEL_NAME, _DEVICE, _COMPUTE_TYPE,
    )
    try:
        _WHISPER_MODEL = WhisperModel(
            _MODEL_NAME,
            device=_DEVICE,
            compute_type=_COMPUTE_TYPE,
        )
    except Exception as e:
        # CUDA 없거나 모델 다운로드 실패 등
        logger.error("Whisper 모델 로드 실패: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"Whisper 모델 로드 실패: {e}",
        )
    logger.info("Whisper 모델 로드 완료")
    return _WHISPER_MODEL


# 허용 audio 확장자 — 일반적인 컨테이너 + Web 녹음 (webm) 포함
ALLOWED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac", ".aac", ".mp4",
}

# 50MB 상한 — 서버 메모리 보호 (large-v3 이 처리 가능한 현실 길이)
MAX_FILE_SIZE = 50 * 1024 * 1024
MIN_FILE_SIZE = 1024


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: Optional[str] = Form("ko"),
    prompt: Optional[str] = Form(None),
):
    """음성 파일 → 텍스트.

    - 한국어 우선 (language="ko"), 영어 혼용 자동 처리
    - prompt 로 이전 대화 hint 가능 (도메인 용어 인식 향상)
    - language="auto" 면 Whisper 가 자동 감지
    """
    # 1. 파일 검증
    if not file.filename:
        raise HTTPException(400, "파일이 없습니다")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"지원하지 않는 형식: {ext}. 허용: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # 2. 본문 읽기 + 크기 검증
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "파일이 너무 큽니다 (최대 50MB)")
    if len(content) < MIN_FILE_SIZE:
        raise HTTPException(400, "파일이 너무 작습니다")

    # 3. 임시 파일 저장 → Whisper 호출 → 정리
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        model = _get_model()
        segments, info = model.transcribe(
            tmp_path,
            language=language if language and language != "auto" else None,
            initial_prompt=prompt,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        # segments 는 generator — 한 번 소비
        seg_list = list(segments)
        text = "".join(s.text for s in seg_list).strip()

        return {
            "text": text,
            "language": info.language,
            "language_probability": round(float(info.language_probability), 3),
            "duration_sec": round(float(info.duration), 2),
            "segments": [
                {
                    "start": round(float(s.start), 2),
                    "end": round(float(s.end), 2),
                    "text": s.text.strip(),
                }
                for s in seg_list
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Whisper transcribe 실패")
        raise HTTPException(500, f"음성 변환 실패: {e}")
    finally:
        # 임시 파일은 항상 정리
        if tmp_path and Path(tmp_path).exists():
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.get("/health")
async def health():
    """모델 로드 상태 확인 (모델 로드는 일으키지 않음)."""
    return {
        "loaded": _WHISPER_MODEL is not None,
        "model": _MODEL_NAME,
        "device": _DEVICE,
        "compute_type": _COMPUTE_TYPE,
    }
