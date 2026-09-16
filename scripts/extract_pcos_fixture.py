#!/usr/bin/env python3
"""PCOS Monash 2023 v1 PDF에서 페이지별 원시 텍스트를 추출해 픽스처로 저장한다.

원본 PDF(key276-sources/pcos-monash-2023-v1.pdf)가 있는 환경에서 한 번 실행한다.
생성된 JSON 픽스처는 저장소에 커밋하면 CI에서도 콘텐츠 계약 테스트가 실행된다.

사용법:
    uv run python scripts/extract_pcos_fixture.py

출처: International Evidence-based Guideline for the Assessment and Management
      of Polycystic Ovary Syndrome 2023, Monash University · International PCOS Network
원본 DOI: https://doi.org/10.26180/24003834.v1
라이선스: CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
변경 사항: 33~40쪽 원시 텍스트를 pypdf로 추출, JSON 직렬화하여 저장.
          저자·제목·라이선스는 픽스처 메타데이터에 명기한다.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = REPO_ROOT / "key276-sources" / "pcos-monash-2023-v1.pdf"
FIXTURE_PATH = REPO_ROOT / "app" / "tests" / "rag" / "fixtures" / "pcos_monash_2023_raw_pages.json"

EXPECTED_MD5 = "75bb875708c151846416e225adfc54e0"

# 범위 밖 페이지(33~34, 39~40)를 포함해야 페이지 선택 오류를 감지할 수 있다.
# 35~38쪽만 넣으면 page_from/page_to가 잘못돼도 테스트가 통과한다.
PAGE_RANGE = range(33, 41)  # 33~40쪽 (1-indexed)


def main() -> None:
    try:
        import pypdf
    except ImportError:
        print("pypdf 가 없습니다. uv run python scripts/extract_pcos_fixture.py 로 실행하세요.", file=sys.stderr)
        sys.exit(1)

    if not PDF_PATH.exists():
        print(f"PDF 없음: {PDF_PATH}", file=sys.stderr)
        print("key276-sources/pcos-monash-2023-v1.pdf 를 배치한 뒤 다시 실행하세요.", file=sys.stderr)
        sys.exit(1)

    pdf_bytes = PDF_PATH.read_bytes()
    actual_md5 = hashlib.md5(pdf_bytes).hexdigest()
    if actual_md5 != EXPECTED_MD5:
        print(f"MD5 불일치: 기대 {EXPECTED_MD5}, 실제 {actual_md5}", file=sys.stderr)
        print("확정 버전의 PDF 파일인지 확인하세요.", file=sys.stderr)
        sys.exit(1)

    reader = pypdf.PdfReader(PDF_PATH)
    total_pages = len(reader.pages)
    pages: dict[str, str] = {}
    for page_num in PAGE_RANGE:
        if page_num > total_pages:
            print(f"  {page_num}쪽: PDF 범위 초과 (전체 {total_pages}쪽), 건너뜀")
            continue
        page = reader.pages[page_num - 1]  # 0-indexed
        text = page.extract_text() or ""
        pages[str(page_num)] = text
        print(f"  {page_num}쪽: {len(text)}자 추출")

    fixture = {
        "source": (
            "International Evidence-based Guideline for the Assessment and Management of Polycystic Ovary Syndrome 2023"
        ),
        "source_org": "Monash University · International PCOS Network",
        "doi": "https://doi.org/10.26180/24003834.v1",
        "license": "CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/",
        "extracted_by": f"pypdf {pypdf.__version__}",
        "original_md5": EXPECTED_MD5,
        "page_range_extracted": f"{min(PAGE_RANGE)}–{max(PAGE_RANGE)}",
        "note": (
            "정제 전 원시 텍스트. 머리글·표 헤더·쪽번호가 남아 있어야 "
            "extract_text_pdf()의 제거 기능을 검사할 수 있다. "
            "범위 밖 페이지(33~34, 39~40)를 포함해 페이지 선택 오류를 감지한다. "
            "변경 사항: 원본 PDF 대비 텍스트 추출(pypdf) 및 JSON 직렬화."
        ),
        "pages": pages,
    }

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n픽스처 저장: {FIXTURE_PATH}")
    print("이 파일을 저장소에 커밋하면 CI에서 PCOS 콘텐츠 계약 테스트가 실행됩니다.")


if __name__ == "__main__":
    main()
