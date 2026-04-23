"""HLKM - 멀티모달 사실 처리 (이미지/영상/오디오).

이미지·영상·오디오로 전달된 사실을 등록하고, perceptual hash 로 복사본/
재사용을 감지하며, OCR·전사(transcription)·딥페이크 휴리스틱을 통해
메타 정보를 추출한다.

의존성은 최소화:
    - Pillow, numpy 는 선택 의존성 (없으면 fallback 해싱 사용)
    - OCR 은 tesseract CLI, 전사는 whisper CLI 를 subprocess 로 호출
      (없으면 None 반환, 절대 크래시 금지)

의존:
    - hwarang_api.db.prisma
    - .types.KnowledgeFact
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import subprocess
import tempfile
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


_VALID_MEDIA_TYPES = {"TEXT", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT", "MIXED"}


# ─────────────────────────────────────────────
# Lazy imports
# ─────────────────────────────────────────────
def get_pillow():  # type: ignore[no-untyped-def]
    """Pillow 를 lazy import. 없으면 None."""
    try:
        from PIL import Image  # type: ignore

        return Image
    except Exception:  # noqa: BLE001
        return None


def get_numpy():  # type: ignore[no-untyped-def]
    """numpy 를 lazy import. 없으면 None."""
    try:
        import numpy as np  # type: ignore

        return np
    except Exception:  # noqa: BLE001
        return None


def get_httpx():  # type: ignore[no-untyped-def]
    """httpx 를 lazy import. 없으면 None."""
    try:
        import httpx  # type: ignore

        return httpx
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────
# 파일 다운로드
# ─────────────────────────────────────────────
async def _download_media(media_url: str) -> bytes | None:
    """미디어 URL 에서 바이트를 받아온다. 실패 시 None."""
    if not media_url:
        return None
    if media_url.startswith("file://"):
        path = media_url[len("file://") :]
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception as exc:  # noqa: BLE001
            logger.debug("_download_media local read failed: %s", exc)
            return None
    if media_url.startswith("/") and os.path.exists(media_url):
        try:
            with open(media_url, "rb") as f:
                return f.read()
        except Exception as exc:  # noqa: BLE001
            logger.debug("_download_media path read failed: %s", exc)
            return None

    httpx = get_httpx()
    if httpx is None:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(media_url, follow_redirects=True)
            if r.status_code == 200:
                return r.content
    except Exception as exc:  # noqa: BLE001
        logger.debug("_download_media http failed: %s", exc)
    return None


# ─────────────────────────────────────────────
# Perceptual / difference hash
# ─────────────────────────────────────────────
def _sha_fallback(data: bytes, bits: int = 64) -> str:
    """Pillow 미설치 fallback: SHA-256 상위 비트를 16진 문자열로."""
    h = hashlib.sha256(data).hexdigest()
    # bits=64 → 16 hex chars
    return h[: bits // 4]


def _dct_1d(vec: list[float]) -> list[float]:
    """순수 Python 1D DCT-II (작은 크기 전용)."""
    n = len(vec)
    result: list[float] = []
    for k in range(n):
        s = 0.0
        for i in range(n):
            s += vec[i] * math.cos(math.pi * (i + 0.5) * k / n)
        result.append(s)
    return result


def _dct_2d(matrix: list[list[float]]) -> list[list[float]]:
    """2D DCT = 행 DCT 후 열 DCT."""
    # 행
    rows = [_dct_1d(row) for row in matrix]
    # 열
    n = len(rows)
    m = len(rows[0])
    cols: list[list[float]] = [[0.0] * m for _ in range(n)]
    for j in range(m):
        col = [rows[i][j] for i in range(n)]
        dct_col = _dct_1d(col)
        for i in range(n):
            cols[i][j] = dct_col[i]
    return cols


def compute_phash(image_bytes: bytes) -> str:
    """64bit perceptual hash (8x8 grayscale DCT 기반).

    Pillow 가 없으면 SHA-256 fallback. 반환 형식: 16자리 hex 문자열.
    """
    if not image_bytes:
        return "0" * 16

    Image = get_pillow()
    if Image is None:
        return _sha_fallback(image_bytes, bits=64)

    try:
        import io

        img = Image.open(io.BytesIO(image_bytes))
        # 32x32 로 축소 후 grayscale 변환
        img = img.convert("L").resize((32, 32), Image.LANCZOS)
        pixels = list(img.getdata())
        matrix = [pixels[i * 32 : (i + 1) * 32] for i in range(32)]
        # float 화
        matrix_f = [[float(v) for v in row] for row in matrix]
        # numpy 가 있으면 빠르게
        np = get_numpy()
        if np is not None:
            try:
                from numpy.fft import fft  # noqa: F401

                arr = np.asarray(matrix_f, dtype=np.float32)
                # 2D DCT via real cosine basis (간단 구현)
                dct_rows = np.zeros_like(arr)
                for k in range(32):
                    basis = np.cos(math.pi * (np.arange(32) + 0.5) * k / 32.0)
                    dct_rows[:, k] = arr @ basis
                dct_full = np.zeros_like(arr)
                for k in range(32):
                    basis = np.cos(math.pi * (np.arange(32) + 0.5) * k / 32.0)
                    dct_full[k, :] = basis @ dct_rows
                low = dct_full[:8, :8]
                median = float(np.median(low[1:, 1:]))  # DC 제외
                bits = (low >= median).astype(int).flatten().tolist()
            except Exception:  # noqa: BLE001
                dct2 = _dct_2d(matrix_f)
                low = [row[:8] for row in dct2[:8]]
                flat = [low[i][j] for i in range(1, 8) for j in range(1, 8)]
                flat_sorted = sorted(flat)
                median = flat_sorted[len(flat_sorted) // 2] if flat_sorted else 0.0
                bits = []
                for i in range(8):
                    for j in range(8):
                        bits.append(1 if low[i][j] >= median else 0)
        else:
            dct2 = _dct_2d(matrix_f)
            low = [row[:8] for row in dct2[:8]]
            flat = [low[i][j] for i in range(1, 8) for j in range(1, 8)]
            flat_sorted = sorted(flat)
            median = flat_sorted[len(flat_sorted) // 2] if flat_sorted else 0.0
            bits = []
            for i in range(8):
                for j in range(8):
                    bits.append(1 if low[i][j] >= median else 0)

        # 64bit → hex 16
        val = 0
        for b in bits[:64]:
            val = (val << 1) | int(b)
        return f"{val:016x}"
    except Exception as exc:  # noqa: BLE001
        logger.debug("compute_phash failed, falling back: %s", exc)
        return _sha_fallback(image_bytes, bits=64)


def compute_dhash(image_bytes: bytes) -> str:
    """difference hash (9x8 grayscale, 인접 픽셀 비교)."""
    if not image_bytes:
        return "0" * 16

    Image = get_pillow()
    if Image is None:
        return _sha_fallback(image_bytes, bits=64)

    try:
        import io

        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("L").resize((9, 8), Image.LANCZOS)
        pixels = list(img.getdata())
        bits: list[int] = []
        for row in range(8):
            for col in range(8):
                left = pixels[row * 9 + col]
                right = pixels[row * 9 + col + 1]
                bits.append(1 if left > right else 0)
        val = 0
        for b in bits[:64]:
            val = (val << 1) | b
        return f"{val:016x}"
    except Exception as exc:  # noqa: BLE001
        logger.debug("compute_dhash failed: %s", exc)
        return _sha_fallback(image_bytes, bits=64)


def hamming_distance_hash(hash_a: str, hash_b: str) -> int:
    """두 hex 해시의 해밍 거리 (bit 차이 수).

    길이 다르면 짧은 쪽 기준으로 계산.
    """
    if not hash_a or not hash_b:
        return 64
    n = min(len(hash_a), len(hash_b))
    try:
        a = int(hash_a[:n], 16)
        b = int(hash_b[:n], 16)
    except ValueError:
        return 64
    return bin(a ^ b).count("1")


# ─────────────────────────────────────────────
# 등록 / 파이프라인
# ─────────────────────────────────────────────
async def register_media_fact(fact_id: str, media_url: str, media_type: str) -> dict:
    """MediaFact 레코드를 생성하고 KnowledgeFact 에 미디어 정보를 연결.

    실제 분석(perceptual hash, OCR 등)은 백그라운드 process_media 로 큐잉.
    """
    mt = (media_type or "").upper()
    if mt not in _VALID_MEDIA_TYPES:
        mt = "DOCUMENT"

    try:
        existing = await prisma.mediafact.find_unique(where={"factId": fact_id})
    except Exception as exc:  # noqa: BLE001
        logger.debug("register_media_fact lookup failed: %s", exc)
        existing = None

    if existing:
        media_fact_id = existing.id
    else:
        try:
            row = await prisma.mediafact.create(
                data={
                    "factId": fact_id,
                    "mediaType": mt,
                    "fileUrl": media_url,
                }
            )
            media_fact_id = row.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("register_media_fact create failed: %s", exc)
            return {"media_fact_id": None, "status": "error", "error": str(exc)}

    try:
        await prisma.knowledgefact.update(
            where={"id": fact_id},
            data={"mediaType": mt, "mediaUrl": media_url},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("register_media_fact fact update failed: %s", exc)

    # 백그라운드 분석 큐잉
    try:
        asyncio.create_task(process_media(media_fact_id))
    except Exception as exc:  # noqa: BLE001
        logger.debug("register_media_fact queue failed: %s", exc)

    return {"media_fact_id": media_fact_id, "status": "queued"}


async def process_media(media_fact_id: str) -> dict:
    """MediaFact 를 다운로드/분석해 메타 데이터를 업데이트."""
    try:
        row = await prisma.mediafact.find_unique(where={"id": media_fact_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("process_media lookup failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    if not row:
        return {"status": "not_found"}

    media_url = getattr(row, "fileUrl", "") or ""
    media_type = (getattr(row, "mediaType", "") or "").upper()
    data = await _download_media(media_url)
    if data is None:
        return {"status": "download_failed"}

    update: dict[str, Any] = {"originalSize": len(data)}
    ocr_text: str | None = None
    transcription: str | None = None
    phash: str | None = None

    try:
        if media_type == "IMAGE":
            phash = compute_phash(data)
            update["perceptualHash"] = phash
            update["simHash"] = compute_dhash(data)
            # 해상도
            Image = get_pillow()
            if Image is not None:
                try:
                    import io

                    img = Image.open(io.BytesIO(data))
                    update["resolution"] = f"{img.width}x{img.height}"
                    exif = None
                    try:
                        exif = img.getexif()
                    except Exception:  # noqa: BLE001
                        exif = None
                    if exif:
                        update["exifData"] = {str(k): str(v) for k, v in exif.items()}
                except Exception as exc:  # noqa: BLE001
                    logger.debug("process_media image meta failed: %s", exc)
            ocr_text = await extract_text_from_image(media_url)
            if ocr_text:
                update["ocrText"] = ocr_text
            manipulation = await detect_manipulation(data, "IMAGE")
            if manipulation:
                update["manipulationFlags"] = manipulation
            update["deepfakeScore"] = await detect_deepfake_heuristic(media_url, "IMAGE")

        elif media_type == "VIDEO":
            phash = compute_phash(data[: 1024 * 1024])  # 앞 1MB 기준 러프 해시
            update["perceptualHash"] = phash
            update["simHash"] = compute_dhash(data[: 1024 * 1024])
            transcription = await transcribe_audio_video(media_url)
            if transcription:
                update["transcription"] = transcription
            update["deepfakeScore"] = await detect_deepfake_heuristic(media_url, "VIDEO")

        elif media_type == "AUDIO":
            update["perceptualHash"] = _sha_fallback(data, bits=64)
            transcription = await transcribe_audio_video(media_url)
            if transcription:
                update["transcription"] = transcription

        else:  # DOCUMENT / MIXED / TEXT
            update["perceptualHash"] = _sha_fallback(data, bits=64)
    except Exception as exc:  # noqa: BLE001
        logger.warning("process_media analysis failed: %s", exc)

    try:
        await prisma.mediafact.update(where={"id": media_fact_id}, data=update)
    except Exception as exc:  # noqa: BLE001
        logger.warning("process_media update failed: %s", exc)

    # KnowledgeFact 에도 media hash 저장
    fact_id = getattr(row, "factId", None)
    if fact_id and phash:
        try:
            await prisma.knowledgefact.update(
                where={"id": fact_id},
                data={"mediaHash": phash, "mediaMetadata": {
                    "resolution": update.get("resolution"),
                    "size": update.get("originalSize"),
                    "ocr": bool(ocr_text),
                    "transcription": bool(transcription),
                }},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("process_media fact update failed: %s", exc)

    return {"status": "ok", "media_fact_id": media_fact_id, "update": update}


# ─────────────────────────────────────────────
# 유사 미디어 검색
# ─────────────────────────────────────────────
async def find_similar_media(phash: str, max_distance: int = 10) -> list[dict]:
    """DB 의 MediaFact 중 perceptualHash 가 주어진 해시와 가까운 항목 반환."""
    if not phash:
        return []
    try:
        rows = await prisma.mediafact.find_many(
            where={"perceptualHash": {"not": None}}, take=1000
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("find_similar_media list failed: %s", exc)
        return []

    out: list[dict] = []
    for row in rows:
        other = getattr(row, "perceptualHash", None)
        if not other:
            continue
        dist = hamming_distance_hash(phash, other)
        if dist <= max_distance:
            out.append(
                {
                    "media_fact_id": row.id,
                    "fact_id": getattr(row, "factId", None),
                    "perceptualHash": other,
                    "distance": dist,
                    "mediaType": getattr(row, "mediaType", "UNKNOWN"),
                    "fileUrl": getattr(row, "fileUrl", ""),
                }
            )
    out.sort(key=lambda x: x["distance"])
    return out


# ─────────────────────────────────────────────
# 딥페이크 휴리스틱
# ─────────────────────────────────────────────
async def detect_deepfake_heuristic(media_url: str, media_type: str) -> float:
    """해상도 / EXIF / 압축 메타를 이용한 간이 딥페이크 의심도.

    실제 딥페이크 탐지 모델은 추후 연동. 반환값 0.0 ~ 1.0.
    """
    data = await _download_media(media_url)
    if data is None:
        return 0.0

    score = 0.0
    mt = (media_type or "").upper()

    if mt == "IMAGE":
        Image = get_pillow()
        if Image is None:
            return 0.3  # 분석 불가 시 중립 낮음
        try:
            import io

            img = Image.open(io.BytesIO(data))
            w, h = img.width, img.height
            try:
                exif = img.getexif()
            except Exception:  # noqa: BLE001
                exif = None
            has_exif = bool(exif and len(dict(exif)) > 0)
            # EXIF 없음 → +0.2
            if not has_exif:
                score += 0.25
            # 고해상도인데 파일 크기가 비정상적으로 작음 → 재인코딩/생성물 의심
            pixels = max(w * h, 1)
            bytes_per_pixel = len(data) / pixels
            if pixels > 500_000 and bytes_per_pixel < 0.3:
                score += 0.3
            # 정사각 + 특이 해상도 (512x512, 1024x1024 등 흔한 생성 AI 사이즈)
            if w == h and w in (256, 512, 768, 1024, 2048):
                score += 0.25
            # JPEG 인데 EXIF 아예 없고 원본크기 정보 누락
            if img.format == "JPEG" and not has_exif:
                score += 0.1
        except Exception as exc:  # noqa: BLE001
            logger.debug("detect_deepfake_heuristic image failed: %s", exc)
            score = 0.2

    elif mt == "VIDEO":
        # 용량 대비 길이 추정이 불가하므로 파일 크기만 참고
        if len(data) < 200_000:  # 작은 영상은 재인코딩/짧은 생성물 의심
            score += 0.3
        score += 0.2  # 분석 불가 영역 보정
    else:
        score = 0.1

    return round(min(1.0, max(0.0, score)), 3)


# ─────────────────────────────────────────────
# OCR
# ─────────────────────────────────────────────
async def extract_text_from_image(media_url: str) -> str | None:
    """tesseract CLI 가 있으면 OCR 수행, 없으면 None."""
    data = await _download_media(media_url)
    if data is None:
        return None

    # tesseract 존재 체크
    try:
        probe = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            timeout=5.0,
        )
        if probe.returncode != 0:
            return None
    except Exception:  # noqa: BLE001
        return None

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(data)
        tmp_path = f.name

    try:
        proc = subprocess.run(
            ["tesseract", tmp_path, "-", "-l", "kor+eng"],
            capture_output=True,
            timeout=30.0,
        )
        if proc.returncode != 0:
            return None
        text = proc.stdout.decode("utf-8", errors="ignore").strip()
        return text or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("extract_text_from_image failed: %s", exc)
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass


# ─────────────────────────────────────────────
# 전사 (Whisper)
# ─────────────────────────────────────────────
async def transcribe_audio_video(media_url: str) -> str | None:
    """whisper CLI 가 있으면 전사, 없으면 None."""
    data = await _download_media(media_url)
    if data is None:
        return None

    # whisper 존재 체크 (openai-whisper 또는 whisper.cpp main)
    whisper_cmd: list[str] | None = None
    for candidate in (["whisper", "--help"], ["whisper-cpp", "--help"], ["main", "--help"]):
        try:
            probe = subprocess.run(candidate, capture_output=True, timeout=5.0)
            if probe.returncode == 0:
                whisper_cmd = [candidate[0]]
                break
        except Exception:  # noqa: BLE001
            continue
    if whisper_cmd is None:
        return None

    suffix = ".wav" if media_url.lower().endswith(".wav") else ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        tmp_path = f.name

    try:
        # openai-whisper 기준
        cmd = whisper_cmd + [tmp_path, "--model", "tiny", "--output_format", "txt", "--language", "Korean"]
        proc = subprocess.run(cmd, capture_output=True, timeout=120.0)
        if proc.returncode != 0:
            return None
        out = proc.stdout.decode("utf-8", errors="ignore").strip()
        # 결과 파일이 있으면 그 내용 우선
        txt_path = tmp_path.rsplit(".", 1)[0] + ".txt"
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as rf:
                    content = rf.read().strip()
                os.unlink(txt_path)
                if content:
                    return content
            except Exception:  # noqa: BLE001
                pass
        return out or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("transcribe_audio_video failed: %s", exc)
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass


# ─────────────────────────────────────────────
# Manipulation 감지 (ELA 간이)
# ─────────────────────────────────────────────
async def detect_manipulation(media_bytes: bytes, media_type: str) -> list[str]:
    """Error Level Analysis (ELA) 간이 구현 및 메타 검사.

    반환 flag 예: ``["ela_suspicious", "metadata_stripped", "resized"]``.
    Pillow 가 없으면 메타 기반 검사만 수행.
    """
    flags: list[str] = []
    mt = (media_type or "").upper()
    if not media_bytes:
        return flags

    if mt != "IMAGE":
        # 이미지 외에는 간단 메타 플래그만
        if len(media_bytes) < 10_000:
            flags.append("tiny_file")
        return flags

    Image = get_pillow()
    if Image is None:
        return flags

    try:
        import io

        img = Image.open(io.BytesIO(media_bytes)).convert("RGB")
        # ELA: 95 품질로 재저장 → 원본과 픽셀 차이
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        resaved = Image.open(buf).convert("RGB")

        np = get_numpy()
        if np is not None:
            a = np.asarray(img, dtype=np.int16)
            b = np.asarray(resaved, dtype=np.int16)
            if a.shape == b.shape:
                diff = np.abs(a - b)
                max_diff = float(diff.max())
                mean_diff = float(diff.mean())
                # 픽셀별 차이가 부분적으로 크고 평균은 작으면 부분 조작 의심
                if max_diff > 40 and mean_diff < 6:
                    flags.append("ela_suspicious")
                if mean_diff > 15:
                    flags.append("high_compression")
        else:
            # 순수 Python: 샘플링해 비교
            w, h = img.size
            samples = min(2000, w * h // 10)
            step = max(1, (w * h) // max(samples, 1))
            pix_a = list(img.getdata())
            pix_b = list(resaved.getdata())
            total = 0
            hit = 0
            maxd = 0
            for i in range(0, min(len(pix_a), len(pix_b)), step):
                ra, ga, ba = pix_a[i]
                rb, gb, bb = pix_b[i]
                d = abs(ra - rb) + abs(ga - gb) + abs(ba - bb)
                total += d
                hit += 1
                if d > maxd:
                    maxd = d
            if hit > 0:
                mean_diff = total / hit
                if maxd > 120 and mean_diff < 18:
                    flags.append("ela_suspicious")

        # EXIF 삭제 여부
        try:
            exif = img.getexif()
            if not exif or len(dict(exif)) == 0:
                flags.append("metadata_stripped")
        except Exception:  # noqa: BLE001
            flags.append("metadata_stripped")
    except Exception as exc:  # noqa: BLE001
        logger.debug("detect_manipulation failed: %s", exc)

    return flags


# ─────────────────────────────────────────────
# 요약 / 조회
# ─────────────────────────────────────────────
async def media_fact_summary(fact_id: str) -> dict:
    """MediaFact 와 KnowledgeFact 조인 요약."""
    try:
        mf = await prisma.mediafact.find_unique(where={"factId": fact_id})
    except Exception as exc:  # noqa: BLE001
        logger.debug("media_fact_summary mf failed: %s", exc)
        mf = None
    try:
        kf = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    except Exception as exc:  # noqa: BLE001
        logger.debug("media_fact_summary kf failed: %s", exc)
        kf = None

    if not mf and not kf:
        return {"fact_id": fact_id, "status": "not_found"}

    return {
        "fact_id": fact_id,
        "content": getattr(kf, "content", "") if kf else "",
        "media": {
            "mediaType": getattr(mf, "mediaType", None) if mf else None,
            "fileUrl": getattr(mf, "fileUrl", None) if mf else None,
            "thumbnailUrl": getattr(mf, "thumbnailUrl", None) if mf else None,
            "perceptualHash": getattr(mf, "perceptualHash", None) if mf else None,
            "simHash": getattr(mf, "simHash", None) if mf else None,
            "ocrText": getattr(mf, "ocrText", None) if mf else None,
            "transcription": getattr(mf, "transcription", None) if mf else None,
            "deepfakeScore": float(getattr(mf, "deepfakeScore", 0.0) or 0.0) if mf else 0.0,
            "manipulationFlags": list(getattr(mf, "manipulationFlags", []) or []) if mf else [],
            "resolution": getattr(mf, "resolution", None) if mf else None,
            "duration": getattr(mf, "duration", None) if mf else None,
            "originalSize": getattr(mf, "originalSize", None) if mf else None,
        }
        if mf
        else None,
    }


async def list_suspect_media(min_deepfake_score: float = 0.6) -> list[dict]:
    """deepfakeScore 가 임계값 이상인 MediaFact 목록."""
    try:
        rows = await prisma.mediafact.find_many(
            where={"deepfakeScore": {"gte": min_deepfake_score}},
            take=500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("list_suspect_media failed: %s", exc)
        return []

    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "media_fact_id": row.id,
                "fact_id": getattr(row, "factId", None),
                "mediaType": getattr(row, "mediaType", "UNKNOWN"),
                "deepfakeScore": float(getattr(row, "deepfakeScore", 0.0) or 0.0),
                "manipulationFlags": list(getattr(row, "manipulationFlags", []) or []),
                "fileUrl": getattr(row, "fileUrl", ""),
            }
        )
    out.sort(key=lambda x: -x["deepfakeScore"])
    return out


async def scan_media_for_copies(media_fact_id: str) -> list[dict]:
    """해당 미디어와 유사한 다른 미디어를 찾아 provenance 로 기록.

    유사도는 perceptual hash 의 해밍 거리 기준 (<=10).
    """
    try:
        row = await prisma.mediafact.find_unique(where={"id": media_fact_id})
    except Exception as exc:  # noqa: BLE001
        logger.debug("scan_media_for_copies fetch failed: %s", exc)
        return []
    if not row:
        return []

    phash = getattr(row, "perceptualHash", None)
    if not phash:
        return []

    similar = await find_similar_media(phash, max_distance=10)
    # 자기 자신 제외
    similar = [s for s in similar if s.get("media_fact_id") != media_fact_id]

    # provenance 기록은 best-effort (테이블 스키마가 있을 때만)
    for s in similar:
        try:
            await prisma.provenance.create(
                data={
                    "sourceFactId": getattr(row, "factId", None),
                    "relatedFactId": s.get("fact_id"),
                    "relationship": "MEDIA_COPY",
                    "confidence": max(0.0, 1.0 - s["distance"] / 10.0),
                    "notes": f"perceptual hash distance={s['distance']}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("scan_media_for_copies provenance skip: %s", exc)
    return similar


__all__ = [
    "register_media_fact",
    "process_media",
    "compute_phash",
    "compute_dhash",
    "hamming_distance_hash",
    "find_similar_media",
    "detect_deepfake_heuristic",
    "extract_text_from_image",
    "transcribe_audio_video",
    "detect_manipulation",
    "media_fact_summary",
    "list_suspect_media",
    "scan_media_for_copies",
    "get_pillow",
    "get_numpy",
    "get_httpx",
]
