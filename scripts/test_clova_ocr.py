"""CLOVA OCR 어댑터 직접 테스트 스크립트 — KEY-56.

사용법:
  DB_HOST=localhost uv run python scripts/test_clova_ocr.py <이미지_경로> [문서_유형]

문서_유형 선택지: EMR | LAB_RESULT | PRESCRIPTION  (기본값: LAB_RESULT)

예시:
  DB_HOST=localhost uv run python scripts/test_clova_ocr.py ~/Downloads/lab_result.jpg LAB_RESULT
  DB_HOST=localhost uv run python scripts/test_clova_ocr.py ~/Downloads/emr.pdf EMR
"""

import asyncio
import sys
from pathlib import Path

# seed.py 와 같은 방식으로 프로젝트 루트를 경로에 추가한다
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_MIME_BY_SUFFIX: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".pdf": "application/pdf",
}


def _resolve_mime(path: Path) -> str:
    mime = _MIME_BY_SUFFIX.get(path.suffix.lower())
    if mime is None:
        print(f"[ERROR] 지원하지 않는 파일 형식: {path.suffix}  (jpg·png·pdf만 가능)")
        sys.exit(1)
    return mime


def _print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print("─" * 60)


async def run(image_path: Path, doc_type_str: str) -> None:
    # 임포트를 여기서 해서 config 로드 오류를 먼저 잡는다
    from ai_worker.adapters.clova import ClovaOcrError, call_clova_ocr
    from ai_worker.core import config
    from ai_worker.tasks.field_extractor import extract_fields
    from app.models.ocr import OcrDocumentType

    # ── 사전 확인 ────────────────────────────────────────────────────────────
    if not config.clova_enabled:
        print("[ERROR] CLOVA 키가 설정되지 않았습니다.")
        print("  .env 에 CLOVA_OCR_INVOKE_URL 과 CLOVA_OCR_SECRET_KEY 를 채워 주세요.")
        sys.exit(1)

    try:
        doc_type = OcrDocumentType(doc_type_str)
    except ValueError:
        valid = [e.value for e in OcrDocumentType]
        print(f"[ERROR] 알 수 없는 문서 유형: {doc_type_str}  (선택지: {valid})")
        sys.exit(1)

    if not image_path.exists():
        print(f"[ERROR] 파일 없음: {image_path}")
        sys.exit(1)

    mime = _resolve_mime(image_path)
    content = image_path.read_bytes()

    print(f"\n파일   : {image_path.name}  ({len(content):,} bytes, {mime})")
    print(f"문서   : {doc_type_str}")
    print(f"URL    : {config.CLOVA_OCR_INVOKE_URL[:60]}...")
    print(f"타임아웃: {config.CLOVA_OCR_TIMEOUT_SECONDS}s")
    print("\n[→] CLOVA OCR 호출 중...")

    # ── CLOVA 호출 ───────────────────────────────────────────────────────────
    try:
        result = await call_clova_ocr(content, mime)
    except ClovaOcrError as exc:
        print(f"\n[FAIL] {exc.code}: {exc}")
        sys.exit(1)

    # ── raw_text ─────────────────────────────────────────────────────────────
    _print_section("CLOVA raw_text")
    print(result.raw_text if result.raw_text else "(비어 있음)")

    # ── 텍스트 블록 목록 ──────────────────────────────────────────────────────
    _print_section(f"텍스트 블록 {len(result.fields)}개 (inferText / inferConfidence)")
    for i, f in enumerate(result.fields, 1):
        bar = "█" * int(f.confidence * 10)
        print(f"  {i:3}. [{bar:<10}] {f.confidence:.2f}  {f.text}")

    # ── 필드 추출 결과 ────────────────────────────────────────────────────────
    extracted = extract_fields(result, doc_type)
    _print_section(f"field_extractor 추출 결과 ({doc_type_str}) — {len(extracted)}개 매칭")
    if extracted:
        for ef in extracted:
            print(f"  {ef.field_type:<28} {ef.extracted_value}  (신뢰도 {float(ef.confidence):.2f})")
    else:
        print("  매칭된 필드 없음 — 패턴이 실제 CLOVA 출력과 다를 수 있습니다.")
        print("  raw_text를 확인하고 field_extractor.py 패턴을 보정해 주세요.")

    print()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    image_path = Path(sys.argv[1]).expanduser()
    doc_type_str = sys.argv[2].upper() if len(sys.argv) >= 3 else "LAB_RESULT"

    asyncio.run(run(image_path, doc_type_str))


if __name__ == "__main__":
    main()
