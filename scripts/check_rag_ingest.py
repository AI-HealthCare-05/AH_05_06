"""RAG 문서 재적재 후 5가지 품질 검사 스크립트.

실행 예시:
    docker compose exec -T fastapi uv run --no-sync python scripts/check_rag_ingest.py

검사 항목:
    1. PCOS 권고 31개가 다 들어왔나 (Monash v1 35~38쪽, 3.1.1~3.6.5)
    2. 머리글·표 헤더 쓰레기 줄이 안 섞였나
    3. 생활관리 절에 약물 용어 0건인가
    4. 자궁내막증(ESHRE) 청크가 0건인가
    5. 폐기된 9/11 draft 둘이 검색에 안 잡히는가
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tortoise import Tortoise  # noqa: E402

from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.catalog import ApprovalStatus  # noqa: E402
from app.models.knowledge import KnowledgeChunkRecord, KnowledgeDocument, KnowledgeVersion  # noqa: E402

# 검사 기준값
PCOS_TITLE_KEYWORD = "Polycystic Ovary Syndrome"
ESHRE_TITLE_KEYWORD = "ESHRE"
PCOS_SECTION_KEY = "life"
EXPECTED_PCOS_CHUNK_COUNT = 31
DRAFT_DATE = date(2026, 9, 11)
EXPECTED_DEPRECATED_DRAFT_COUNT = 2

# Monash 원문에서 걸러야 할 머리글·표 헤더 패턴
_GARBAGE_PATTERNS = [
    re.compile(r"International Evidence-based Guideline", re.IGNORECASE),
    re.compile(r"Living#\s*Type\s*Recommendation", re.IGNORECASE),
    re.compile(r"^Grade[/\s]", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^Quality\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^No\.\s*$", re.MULTILINE),
]

# 생활관리 절에 섞이면 안 되는 약물 용어
_DRUG_TERMS = re.compile(
    r"메트포르민|클로미펜|레트로졸|이노시톨|피임약|경구피임|OCP\b|GnRH|"
    r"metformin|clomiphene|letrozole|inositol|spironolactone|스피로노락톤|"
    r"프로게스테론|에스트로겐|progesterone|estrogen|berberine|베르베린|"
    r"\bmg\b.{0,10}(?:하루|1일|2회|복용)|처방.{0,5}(?:약|의약|제제)",
    re.IGNORECASE,
)


def _check_garbage(body: str) -> list[str]:
    return [p.pattern for p in _GARBAGE_PATTERNS if p.search(body)]


async def run_checks() -> dict:
    results: dict = {}

    # ── 1. PCOS Monash 문서 조회 ────────────────────────────────────────────
    pcos_doc = await KnowledgeDocument.filter(title__contains=PCOS_TITLE_KEYWORD).first()
    if pcos_doc is None:
        results["check1_pcos_count"] = {"passed": False, "error": "PCOS 문서를 찾을 수 없음"}
        results["check2_garbage_lines"] = {"passed": False, "error": "PCOS 문서 없음"}
        results["check3_drug_terms"] = {"passed": False, "error": "PCOS 문서 없음"}
    else:
        pcos_version = (
            await KnowledgeVersion.filter(
                document=pcos_doc,
                approval_status=ApprovalStatus.APPROVED,
                is_current=True,
            )
            .prefetch_related("chunks")
            .first()
        )
        if pcos_version is None:
            results["check1_pcos_count"] = {"passed": False, "error": "승인된 현재 PCOS 버전 없음"}
            results["check2_garbage_lines"] = {"passed": False, "error": "승인된 PCOS 버전 없음"}
            results["check3_drug_terms"] = {"passed": False, "error": "승인된 PCOS 버전 없음"}
        else:
            life_chunks = await KnowledgeChunkRecord.filter(
                version=pcos_version,
                section_key=PCOS_SECTION_KEY,
            ).order_by("position")

            chunk_count = len(life_chunks)

            # 검사 1: PCOS 권고 31개
            results["check1_pcos_count"] = {
                "passed": chunk_count == EXPECTED_PCOS_CHUNK_COUNT,
                "version_id": str(pcos_version.version_id),
                "version_label": pcos_version.version_label,
                "chunk_count": chunk_count,
                "expected": EXPECTED_PCOS_CHUNK_COUNT,
            }

            # 검사 2: 머리글·표 헤더 쓰레기 줄
            garbage_hits: list[dict] = []
            for chunk in life_chunks:
                matched = _check_garbage(chunk.body)
                if matched:
                    garbage_hits.append({"position": chunk.position, "patterns": matched})
            results["check2_garbage_lines"] = {
                "passed": len(garbage_hits) == 0,
                "garbage_chunk_count": len(garbage_hits),
                "hits": garbage_hits,
            }

            # 검사 3: 생활관리 절 약물 용어
            drug_hits: list[dict] = []
            for chunk in life_chunks:
                match = _DRUG_TERMS.search(chunk.body)
                if match:
                    drug_hits.append({"position": chunk.position, "matched_term": match.group()})
            results["check3_drug_terms"] = {
                "passed": len(drug_hits) == 0,
                "drug_hit_count": len(drug_hits),
                "hits": drug_hits,
            }

    # ── 4. ESHRE 자궁내막증 청크 0건 ────────────────────────────────────────
    eshre_doc = await KnowledgeDocument.filter(title__contains=ESHRE_TITLE_KEYWORD).first()
    if eshre_doc is None:
        results["check4_eshre_chunks"] = {"passed": False, "error": "ESHRE 문서를 찾을 수 없음"}
    else:
        eshre_chunk_count = await KnowledgeChunkRecord.filter(
            version__document=eshre_doc,
        ).count()
        results["check4_eshre_chunks"] = {
            "passed": eshre_chunk_count == 0,
            "chunk_count": eshre_chunk_count,
            "expected": 0,
        }

    # ── 5. 9/11 draft 폐기 확인 ─────────────────────────────────────────────
    draft_day_start = datetime.combine(DRAFT_DATE, datetime.min.time())
    draft_day_end = draft_day_start + timedelta(days=1)

    deprecated_drafts = await KnowledgeVersion.filter(
        approval_status=ApprovalStatus.DEPRECATED,
        created_at__gte=draft_day_start,
        created_at__lt=draft_day_end,
    ).all()

    searchable_drafts = await KnowledgeVersion.filter(
        created_at__gte=draft_day_start,
        created_at__lt=draft_day_end,
        approval_status__not=ApprovalStatus.DEPRECATED,
        is_current=True,
    ).count()

    results["check5_deprecated_drafts"] = {
        "passed": (len(deprecated_drafts) == EXPECTED_DEPRECATED_DRAFT_COUNT and searchable_drafts == 0),
        "deprecated_count": len(deprecated_drafts),
        "expected_deprecated": EXPECTED_DEPRECATED_DRAFT_COUNT,
        "searchable_non_deprecated_count": searchable_drafts,
        "deprecated_version_ids": [str(v.version_id) for v in deprecated_drafts],
    }

    # ── 전체 통과 여부 ────────────────────────────────────────────────────────
    all_passed = all(v.get("passed", False) for v in results.values())
    return {"passed": all_passed, "checks": results}


async def main() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        report = await run_checks()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["passed"]:
            raise SystemExit(1)
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
