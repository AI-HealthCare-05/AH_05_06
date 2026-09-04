"""CLOVA OCR General API 어댑터 — KEY-56 · KEY-175.

호출 계약:
  - 성공 시 ClovaOcrResult 반환 (elapsed_ms: 실제 HTTP 호출 시간)
  - 실패 시 ClovaOcrError 발생 (code로 실패 종류 구분)
  - API 키가 없는 경우 호출 전에 확인하고 호출하지 않는다 (config.clova_enabled)

CLOVA API 레퍼런스:
  https://api.ncloud-docs.com/docs/ai-application-service-ocr-general
"""

import base64
import uuid
from dataclasses import dataclass, field
from time import perf_counter, time

import httpx

from ai_worker.core import config

_MIME_TO_FORMAT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "application/pdf": "pdf",
}

# 기본값은 config.CLOVA_OCR_TIMEOUT_SECONDS로 덮어쓴다 — .env에서 조정 가능
_TIMEOUT_SECONDS = 30.0


class ClovaOcrError(Exception):
    """CLOVA OCR 호출 또는 응답 파싱 실패."""

    def __init__(self, code: str, message: str, elapsed_ms: int | None = None) -> None:
        self.code = code
        self.elapsed_ms = elapsed_ms  # HTTP 호출 시간 — HTTP I/O 전에 실패하면 None
        super().__init__(message)


@dataclass
class ClovaTextField:
    """CLOVA가 인식한 텍스트 블록 하나."""

    text: str
    confidence: float
    left: float = 0.0  # boundingPoly 최소 X
    top: float = 0.0  # boundingPoly 최소 Y
    right: float = 0.0  # boundingPoly 최대 X
    bottom: float = 0.0  # boundingPoly 최대 Y


@dataclass
class ClovaOcrResult:
    """CLOVA OCR 호출 결과 — Worker가 OcrResult/OcrField로 변환한다."""

    raw_text: str
    fields: list[ClovaTextField] = field(default_factory=list)
    rows: list[list[ClovaTextField]] = field(default_factory=list)  # Y축 기준 행 그룹
    elapsed_ms: int = 0  # 실제 CLOVA HTTP 호출 시간 (KEY-175 관측용)


_ROW_MERGE_TOLERANCE = 15.0  # px — 같은 행으로 묶을 Y 중심 허용 오차


def _parse_clova_field(f: dict) -> ClovaTextField:
    vertices = f.get("boundingPoly", {}).get("vertices", [])
    if vertices:
        xs = [v.get("x", 0.0) for v in vertices]
        ys = [v.get("y", 0.0) for v in vertices]
        left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
    else:
        left = top = right = bottom = 0.0
    return ClovaTextField(
        text=f["inferText"],
        confidence=float(f.get("inferConfidence", 0.0)),
        left=left,
        top=top,
        right=right,
        bottom=bottom,
    )


def _group_fields_by_row(fields: list[ClovaTextField]) -> list[list[ClovaTextField]]:
    """Y축 중심을 기준으로 블록을 행으로 묶고, 행 내부는 X 순으로 정렬한다.

    바운딩 박스가 없는 경우(모두 0) 빈 리스트를 반환한다.
    """
    if not fields or not any(f.top or f.bottom for f in fields):
        return []
    rows: list[list[ClovaTextField]] = []
    for block in sorted(fields, key=lambda f: (f.top + f.bottom) / 2):
        center_y = (block.top + block.bottom) / 2
        for row in rows:
            row_cy = sum((b.top + b.bottom) / 2 for b in row) / len(row)
            if abs(center_y - row_cy) <= _ROW_MERGE_TOLERANCE:
                row.append(block)
                break
        else:
            rows.append([block])
    for row in rows:
        row.sort(key=lambda f: f.left)
    return rows


async def call_clova_ocr(content: bytes, mime_type: str) -> ClovaOcrResult:
    """파일 바이트를 CLOVA OCR General API에 전송하고 결과를 반환한다.

    Args:
        content: 업로드된 파일의 원본 바이트.
        mime_type: 파일 MIME 타입 (image/jpeg, image/png, application/pdf).

    Raises:
        ClovaOcrError: 네트워크 오류, HTTP 오류, 인식 실패 등 모든 외부 오류.
    """
    fmt = _MIME_TO_FORMAT.get(mime_type)
    if fmt is None:
        raise ClovaOcrError("UNSUPPORTED_FORMAT", f"지원하지 않는 파일 형식: {mime_type}")

    payload = {
        "version": "V2",
        "requestId": uuid.uuid4().hex,
        "timestamp": int(time() * 1000),
        "lang": "ko",
        "images": [
            {
                "format": fmt,
                "name": "document",
                "data": base64.b64encode(content).decode(),
            }
        ],
    }

    timeout = config.CLOVA_OCR_TIMEOUT_SECONDS or _TIMEOUT_SECONDS
    t_http = perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                config.CLOVA_OCR_INVOKE_URL,
                json=payload,
                headers={"X-OCR-SECRET": config.CLOVA_OCR_SECRET_KEY.get_secret_value()},
            )
    except httpx.TimeoutException as exc:
        raise ClovaOcrError(
            "CLOVA_TIMEOUT",
            "CLOVA OCR 요청 시간 초과",
            elapsed_ms=round((perf_counter() - t_http) * 1000),
        ) from exc
    except httpx.RequestError as exc:
        raise ClovaOcrError(
            "CLOVA_NETWORK_ERROR",
            "CLOVA OCR 네트워크 오류",
            elapsed_ms=round((perf_counter() - t_http) * 1000),
        ) from exc
    http_elapsed_ms = round((perf_counter() - t_http) * 1000)

    if response.status_code != 200:
        code = (
            "CLOVA_SERVER_ERROR" if (response.status_code >= 500 or response.status_code == 429) else "CLOVA_HTTP_ERROR"
        )
        raise ClovaOcrError(
            code,
            f"CLOVA OCR HTTP {response.status_code}",
            elapsed_ms=http_elapsed_ms,
        )

    try:
        data: dict = response.json()
    except Exception as exc:
        raise ClovaOcrError("CLOVA_PARSE_ERROR", "CLOVA OCR 응답 파싱 실패", elapsed_ms=http_elapsed_ms) from exc

    images: list[dict] = data.get("images", [])
    if not images:
        raise ClovaOcrError("CLOVA_PARSE_ERROR", "CLOVA OCR 응답에 이미지 데이터 없음", elapsed_ms=http_elapsed_ms)

    image = images[0]
    if image.get("inferResult") != "SUCCESS":
        raise ClovaOcrError(
            "CLOVA_INFER_FAILED",
            f"CLOVA OCR 인식 실패: {image.get('message', '')}",
            elapsed_ms=http_elapsed_ms,
        )

    raw_fields = image.get("fields", [])
    text_fields = [_parse_clova_field(f) for f in raw_fields if "inferText" in f]

    rows = _group_fields_by_row(text_fields)
    if rows:
        raw_text = "\n".join("\t".join(f.text for f in row) for row in rows)
    else:
        raw_text = "\n".join(f.text for f in text_fields)

    return ClovaOcrResult(raw_text=raw_text, fields=text_fields, rows=rows, elapsed_ms=http_elapsed_ms)
