"""세 가지 의료지식 입력을 같은 청크 계약으로 정규화한다 — KEY-276."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol

MAX_CHUNK_CHARS = 800
MAX_OVERLAP_CHARS = 120
EXTRACTOR_VERSION = "key276-v1"


@dataclass(frozen=True)
class OcrTextBlock:
    text: str
    page_number: int
    bounding_boxes: tuple[dict[str, float], ...] = ()
    confidence: float | None = None


class OcrExtractor(Protocol):
    async def extract(self, payload: bytes, mime_type: str) -> tuple[OcrTextBlock, ...]: ...


@dataclass(frozen=True)
class ExtractedChunk:
    section_key: str
    body: str
    position: int
    page_number: int | None = None
    bounding_boxes: tuple[dict[str, float], ...] = ()
    ocr_confidence: float | None = None


def _normalized_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def _split_long_unit(unit: str, limit: int) -> list[str]:
    if len(unit) <= limit:
        return [unit]
    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？다요])\s+", unit) if part.strip()]
    if len(sentences) == 1:
        return [unit[start : start + limit] for start in range(0, len(unit), limit)]
    result: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                result.append(current)
            result.extend(_split_long_unit(sentence, limit))
            current = ""
    if current:
        result.append(current)
    return result


def chunk_text(
    text: str,
    *,
    section_key: str,
    page_number: int | None = None,
    bounding_boxes: tuple[dict[str, float], ...] = (),
    ocr_confidence: float | None = None,
    start_position: int = 0,
) -> tuple[ExtractedChunk, ...]:
    """문단·표 행·경고 행을 먼저 보존하고 800자 상한으로 나눈다.

    겹침은 앞 청크 끝 문장 최대 120자를 다음 청크에 붙인다. 같은 입력이면 같은
    경계가 나오므로 버전 재처리 결과도 안정적이다.
    """

    normalized = _normalized_text(text)
    if not normalized:
        return ()
    units: list[str] = []
    for line in normalized.split("\n"):
        units.extend(_split_long_unit(line, MAX_CHUNK_CHARS))

    bodies: list[str] = []
    current = ""
    for unit in units:
        candidate = unit if not current else f"{current}\n{unit}"
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            bodies.append(current)
        overlap = current[-MAX_OVERLAP_CHARS:].lstrip() if current else ""
        candidate = f"{overlap}\n{unit}" if overlap else unit
        current = candidate if len(candidate) <= MAX_CHUNK_CHARS else unit
    if current:
        bodies.append(current)

    return tuple(
        ExtractedChunk(
            section_key=section_key,
            body=body,
            position=start_position + index,
            page_number=page_number,
            bounding_boxes=bounding_boxes,
            ocr_confidence=ocr_confidence,
        )
        for index, body in enumerate(bodies)
    )


def extract_text_pdf(payload: bytes) -> tuple[ExtractedChunk, ...]:
    """텍스트 PDF를 페이지별로 추출한다. 암호화/빈 PDF는 안전하게 실패한다."""

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - 이미지 빌드 계약 테스트가 검증
        raise RuntimeError("PDF_EXTRACTOR_NOT_INSTALLED") from exc

    try:
        reader = PdfReader(BytesIO(payload))
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise ValueError("PDF_ENCRYPTED")
        chunks: list[ExtractedChunk] = []
        for page_index, page in enumerate(reader.pages, start=1):
            chunks.extend(
                chunk_text(
                    page.extract_text() or "",
                    section_key=f"page-{page_index}",
                    page_number=page_index,
                    start_position=len(chunks),
                )
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF_EXTRACTION_FAILED") from exc
    if not chunks:
        raise ValueError("PDF_TEXT_EMPTY")
    return tuple(chunks)


async def extract_scanned_document(
    payload: bytes,
    mime_type: str,
    ocr_extractor: OcrExtractor,
) -> tuple[ExtractedChunk, ...]:
    blocks = await ocr_extractor.extract(payload, mime_type)
    chunks: list[ExtractedChunk] = []
    for block in blocks:
        chunks.extend(
            chunk_text(
                block.text,
                section_key=f"page-{block.page_number}",
                page_number=block.page_number,
                bounding_boxes=block.bounding_boxes,
                ocr_confidence=block.confidence,
                start_position=len(chunks),
            )
        )
    if not chunks:
        raise ValueError("OCR_TEXT_EMPTY")
    return tuple(chunks)


def _flatten_json(value: Any, path: str = "root") -> list[tuple[str, str]]:
    if isinstance(value, dict):
        rows: list[tuple[str, str]] = []
        for key in sorted(value):
            rows.extend(_flatten_json(value[key], f"{path}.{key}"))
        return rows
    if isinstance(value, list):
        rows = []
        for index, item in enumerate(value):
            rows.extend(_flatten_json(item, f"{path}[{index}]"))
        return rows
    scalar = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return [(path, scalar)]


def extract_structured_api_snapshot(payload: bytes) -> tuple[ExtractedChunk, ...]:
    """API 응답을 키 정렬된 경로=값 행으로 바꿔 재현 가능한 청크를 만든다."""

    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("API_SNAPSHOT_INVALID_JSON") from exc
    rows = _flatten_json(parsed)
    if not rows:
        raise ValueError("API_SNAPSHOT_EMPTY")
    return chunk_text("\n".join(f"{path} = {value}" for path, value in rows), section_key="api-snapshot")
