"""RAG 문서 재적재 후 5가지 품질 검사 스크립트.

실행 예시:
    # 승인 전 DRAFT 검사 (승인 전 관문 — 이 방법이 맞는 순서)
    docker cp scripts/check_rag_ingest.py fastapi:/tmp/
    docker compose exec -T fastapi sh -c "PYTHONPATH=/app uv run --no-sync python /tmp/check_rag_ingest.py --version-id <판ID>"

    # 권고 번호별 첫 문장을 로컬 파일에 저장 (stdout 에는 요약만)
    docker compose exec -T fastapi sh -c "PYTHONPATH=/app uv run --no-sync python /tmp/check_rag_ingest.py --version-id <판ID> --dump /tmp/recs.json"
    docker cp fastapi:/tmp/recs.json ./recs.json

    # 승인된 현재 버전 검사 (--version-id 생략)
    docker compose exec -T fastapi sh -c "PYTHONPATH=/app uv run --no-sync python /tmp/check_rag_ingest.py"

종료 코드:
    0  모든 검사 통과
    1  검사는 돌았으나 내용이 잘못됨 (권고 누락·쓰레기·약물 용어·청크 오탐 등)
    2  버전을 찾을 수 없거나 아직 검사할 수 없는 상태 (승인 전이고 --version-id 미지정 등)
"""

from __future__ import annotations

import argparse
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

PCOS_TITLE_KEYWORD = "Polycystic Ovary Syndrome"
ESHRE_SOURCE_URL = "https://academic.oup.com/hropen/article/2022/2/hoac009/6537540"
PCOS_SECTION_KEY = "life"
DRAFT_DATE = date(2026, 9, 11)
EXPECTED_DEPRECATED_DRAFT_COUNT = 2

EXIT_PASS = 0
EXIT_CONTENT_FAIL = 1
EXIT_CANNOT_CHECK = 2

# Monash v1 35~38쪽 권고 번호 전체 목록 (3.1.1~3.6.5, 총 31개)
_EXPECTED_RECOMMENDATION_NUMBERS = frozenset(
    [
        "3.1.1",
        "3.1.2",
        "3.1.3",
        "3.1.4",
        "3.1.5",
        "3.1.6",
        "3.1.7",
        "3.1.8",
        "3.1.9",
        "3.1.10",
        "3.2.1",
        "3.2.2",
        "3.2.3",
        "3.3.1",
        "3.3.2",
        "3.3.3",
        "3.3.4",
        "3.4.1",
        "3.4.2",
        "3.4.3",
        "3.4.4",
        "3.4.5",
        "3.4.6",
        "3.4.7",
        "3.5.1",
        "3.5.2",
        "3.6.1",
        "3.6.2",
        "3.6.3",
        "3.6.4",
        "3.6.5",
    ]
)
_RECOMMENDATION_PATTERN = re.compile(r"3\.[1-6]\.\d+")

# Monash 원문에서 걸러야 할 머리글·표 헤더 패턴
_GARBAGE_PATTERNS = [
    re.compile(r"International Evidence-based Guideline", re.IGNORECASE),
    re.compile(r"Living#\s*Type\s*Recommendation", re.IGNORECASE),
    re.compile(r"^Grade[/\s]", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^Quality\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^No\.\s*$", re.MULTILINE),
]

# 생활관리 절에 섞이면 안 되는 약물 용어 (orlistat·오를리스타트 포함)
_DRUG_TERMS = re.compile(
    r"메트포르민|클로미펜|레트로졸|이노시톨|피임약|경구피임|OCP\b|GnRH|"
    r"metformin|clomiphene|letrozole|inositol|spironolactone|스피로노락톤|"
    r"orlistat|오를리스타트|"
    r"프로게스테론|에스트로겐|progesterone|estrogen|berberine|베르베린|"
    r"\bmg\b.{0,10}(?:하루|1일|2회|복용)|처방.{0,5}(?:약|의약|제제)",
    re.IGNORECASE,
)


def _check_garbage(body: str) -> list[str]:
    return [p.pattern for p in _GARBAGE_PATTERNS if p.search(body)]


async def _lookup_pcos_version(version_id: str | None) -> KnowledgeVersion | None:
    """version_id 지정 시 상태 무관하게 조회, 미지정 시 APPROVED+is_current 조회."""
    if version_id:
        return await KnowledgeVersion.filter(version_id=version_id).select_related("document").first()
    pcos_doc = await KnowledgeDocument.filter(title__contains=PCOS_TITLE_KEYWORD).first()
    if pcos_doc is None:
        return None
    return (
        await KnowledgeVersion.filter(
            document=pcos_doc,
            approval_status=ApprovalStatus.APPROVED,
            is_current=True,
        )
        .select_related("document")
        .first()
    )


def _version_meta(version: KnowledgeVersion, doc: KnowledgeDocument, chunk_count: int) -> dict:
    return {
        "version_id": str(version.version_id),
        "document_title": doc.title,
        "source_org": doc.source_org,
        "source_url": doc.source_url,
        "version_label": version.version_label,
        "license_basis": version.license_basis,
        "source_grade": str(version.source_grade),
        "license_verified": version.license_verified,
        "section_key": PCOS_SECTION_KEY,
        "chunk_count": chunk_count,
        "chunk_optional": version.chunk_optional,
        "source_sha256": version.source_sha256,
        "approval_status": str(version.approval_status),
        "is_current": version.is_current,
    }


def _build_content_checks(life_chunks: list, meta: dict) -> tuple[dict, int]:
    """check1~3 결과를 반환. exit_code 포함."""
    exit_code = EXIT_PASS
    results: dict = {}

    full_text = " ".join(c.body for c in life_chunks)
    found_numbers = frozenset(_RECOMMENDATION_PATTERN.findall(full_text))
    missing = sorted(_EXPECTED_RECOMMENDATION_NUMBERS - found_numbers)
    results["check1_pcos_count"] = {
        "passed": len(missing) == 0,
        **meta,
        "found_count": len(found_numbers & _EXPECTED_RECOMMENDATION_NUMBERS),
        "expected_count": len(_EXPECTED_RECOMMENDATION_NUMBERS),
        "missing": missing,
    }
    if missing:
        exit_code = max(exit_code, EXIT_CONTENT_FAIL)

    garbage_hits = [
        {"position": c.position, "patterns": _check_garbage(c.body)} for c in life_chunks if _check_garbage(c.body)
    ]
    results["check2_garbage_lines"] = {
        "passed": len(garbage_hits) == 0,
        **meta,
        "garbage_chunk_count": len(garbage_hits),
        "hits": garbage_hits,
    }
    if garbage_hits:
        exit_code = max(exit_code, EXIT_CONTENT_FAIL)

    drug_hits = [
        {"position": c.position, "matched_term": m.group()} for c in life_chunks if (m := _DRUG_TERMS.search(c.body))
    ]
    results["check3_drug_terms"] = {
        "passed": len(drug_hits) == 0,
        **meta,
        "drug_hit_count": len(drug_hits),
        "hits": drug_hits,
    }
    if drug_hits:
        exit_code = max(exit_code, EXIT_CONTENT_FAIL)

    return results, exit_code


def _write_dump(version_id: str, life_chunks: list, dump_path: Path) -> str:
    """권고 번호별 첫 문장을 로컬 파일에 저장. 파일 경로 반환."""
    rec_snippets: dict[str, str] = {}
    for chunk in life_chunks:
        for m in _RECOMMENDATION_PATTERN.finditer(chunk.body):
            num = m.group()
            if num not in rec_snippets:
                start = max(0, m.start() - 5)
                line = chunk.body[start : start + 200].split("\n")[0]
                rec_snippets[num] = line.strip()
    dump_data = {
        "version_id": version_id,
        "recommendations": {k: rec_snippets.get(k, "") for k in sorted(_EXPECTED_RECOMMENDATION_NUMBERS)},
    }
    dump_path.write_text(json.dumps(dump_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(dump_path)


async def _check_pcos(
    version_id: str | None,
    dump_path: Path | None,
) -> tuple[dict, int, KnowledgeVersion | None]:
    """check1~3 실행. (결과 dict, exit_code, version 객체) 반환."""
    pcos_version = await _lookup_pcos_version(version_id)
    if pcos_version is None:
        msg = (
            f"version_id={version_id} 버전을 찾을 수 없음"
            if version_id
            else "승인된 현재 PCOS 버전 없음 — DRAFT 검사는 --version-id <판ID> 사용"
        )
        results = {
            k: {"passed": False, "error": msg}
            for k in ("check1_pcos_count", "check2_garbage_lines", "check3_drug_terms")
        }
        return results, EXIT_CANNOT_CHECK, None

    doc = pcos_version.document
    life_chunks = list(
        await KnowledgeChunkRecord.filter(version=pcos_version, section_key=PCOS_SECTION_KEY).order_by("position")
    )
    meta = _version_meta(pcos_version, doc, len(life_chunks))
    results, exit_code = _build_content_checks(life_chunks, meta)

    if dump_path:
        results["check1_pcos_count"]["dump_file"] = _write_dump(str(pcos_version.version_id), life_chunks, dump_path)

    return results, exit_code, pcos_version


async def _check_eshre() -> tuple[dict, int, KnowledgeVersion | None]:
    """check4 실행. (결과 dict, exit_code, version 객체) 반환."""
    eshre_version = (
        await KnowledgeVersion.filter(
            document__source_url=ESHRE_SOURCE_URL,
            approval_status=ApprovalStatus.APPROVED,
            is_current=True,
        )
        .select_related("document")
        .first()
    )
    if eshre_version is None:
        return {"check4_eshre": {"passed": False, "error": "승인된 현재 ESHRE 버전 없음"}}, EXIT_CANNOT_CHECK, None

    eshre_doc = eshre_version.document
    eshre_chunk_count = await KnowledgeChunkRecord.filter(version=eshre_version).count()
    today = date.today()
    review_due = (
        eshre_version.review_due_at.date()
        if isinstance(eshre_version.review_due_at, datetime)
        else eshre_version.review_due_at
    )
    cond_url = eshre_doc.source_url == ESHRE_SOURCE_URL
    cond_approved = eshre_version.approval_status == ApprovalStatus.APPROVED
    cond_current = eshre_version.is_current
    cond_optional = eshre_version.chunk_optional
    cond_review = review_due is None or review_due >= today
    fallback_ready = all([cond_url, cond_approved, cond_current, cond_optional, cond_review])
    chunks_ok = eshre_chunk_count == 0

    result = {
        "check4_eshre": {
            "passed": chunks_ok and fallback_ready,
            "version_id": str(eshre_version.version_id),
            "document_title": eshre_doc.title,
            "source_org": eshre_doc.source_org,
            "source_url": eshre_doc.source_url,
            "version_label": eshre_version.version_label,
            "license_basis": eshre_version.license_basis,
            "source_grade": str(eshre_version.source_grade),
            "license_verified": eshre_version.license_verified,
            "chunk_count": eshre_chunk_count,
            "chunk_optional": eshre_version.chunk_optional,
            "source_sha256": eshre_version.source_sha256,
            "approval_status": str(eshre_version.approval_status),
            "is_current": eshre_version.is_current,
            "fallback_conditions": {
                "source_url_exact_match": cond_url,
                "approval_status_approved": cond_approved,
                "is_current": cond_current,
                "chunk_optional": cond_optional,
                "review_due_at_ok": cond_review,
                "review_due_at_value": str(review_due) if review_due else None,
            },
            "fallback_ready": fallback_ready,
        }
    }
    exit_code = EXIT_PASS if (chunks_ok and fallback_ready) else EXIT_CONTENT_FAIL
    return result, exit_code, eshre_version


async def _check_deprecated_drafts() -> tuple[dict, int]:
    """check5 실행."""
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

    passed = len(deprecated_drafts) == EXPECTED_DEPRECATED_DRAFT_COUNT and searchable_drafts == 0
    result = {
        "check5_deprecated_drafts": {
            "passed": passed,
            "deprecated_count": len(deprecated_drafts),
            "expected_deprecated": EXPECTED_DEPRECATED_DRAFT_COUNT,
            "searchable_non_deprecated_count": searchable_drafts,
            "deprecated_version_ids": [str(v.version_id) for v in deprecated_drafts],
        }
    }
    return result, EXIT_PASS if passed else EXIT_CONTENT_FAIL


async def run_checks(version_id: str | None, dump_path: Path | None) -> tuple[dict, int]:
    pcos_results, pcos_exit, pcos_version = await _check_pcos(version_id, dump_path)
    eshre_results, eshre_exit, eshre_version = await _check_eshre()
    draft_results, draft_exit = await _check_deprecated_drafts()

    results = {**pcos_results, **eshre_results, **draft_results}
    exit_code = max(pcos_exit, eshre_exit, draft_exit)

    approval_commands: list[dict] = []
    if pcos_version is not None and pcos_version.approval_status != ApprovalStatus.APPROVED:
        approval_commands.append(
            {
                "label": "PCOS Monash 승인 (복붙 후 --approved-by·--note 수정)",
                "command": (
                    f"uv run python scripts/ingest_approved_knowledge.py"
                    f" --approve-version {pcos_version.version_id}"
                    f" --approved-by <승인자>"
                    f" --review-days 365"
                    f' --note "<PCOS 판별 비고>"'
                ),
            }
        )
    if eshre_version is not None and eshre_version.approval_status != ApprovalStatus.APPROVED:
        approval_commands.append(
            {
                "label": "ESHRE 자궁내막증 승인 (복붙 후 수정)",
                "command": (
                    f"uv run python scripts/ingest_approved_knowledge.py"
                    f" --approve-version {eshre_version.version_id}"
                    f" --approved-by <승인자>"
                    f" --review-days 365"
                    f' --note "<ESHRE 판별 비고 — 자문 내용 구체적으로>"'
                ),
            }
        )

    all_passed = all(v.get("passed", False) for v in results.values())
    report: dict = {"passed": all_passed, "exit_code": exit_code, "checks": results}
    if approval_commands:
        report["approval_commands"] = approval_commands
    return report, exit_code


async def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 문서 재적재 후 품질 검사")
    parser.add_argument(
        "--version-id",
        metavar="UUID",
        help="검사할 PCOS KnowledgeVersion ID (DRAFT 포함 — 생략 시 APPROVED+is_current 버전 사용)",
    )
    parser.add_argument(
        "--dump",
        metavar="FILE",
        type=Path,
        help="권고 번호별 첫 문장을 로컬 파일에 저장 (stdout 에는 요약만 출력됨)",
    )
    args = parser.parse_args()

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        report, exit_code = await run_checks(args.version_id, args.dump)
        if args.dump:
            check1 = report.get("checks", {}).get("check1_pcos_count", {})
            found = check1.get("found_count", 0)
            total = check1.get("expected_count", 31)
            missing = check1.get("missing", [])
            missing_str = f" 누락={missing}" if missing else ""
            print(f"check1: {found}/{total}개{missing_str}, 본문은 {args.dump}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(exit_code)
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
