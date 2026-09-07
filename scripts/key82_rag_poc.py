"""MySQL 8 후보 조회 + Python 코사인 검색 재현 스크립트 — KEY-82.

실행 예시(로컬 Docker FastAPI 컨테이너):
    docker compose exec -T fastapi uv run --no-sync python scripts/key82_rag_poc.py

임시 테이블과 합성 청크만 사용한다. 연결이 닫히면 테이블도 사라지며 기존 DB
스키마와 데이터는 변경하지 않는다.
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter
from typing import Any

import asyncmy  # type: ignore[import-untyped]
from asyncmy.cursors import DictCursor  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.catalog import ApprovalStatus, SourceGrade  # noqa: E402
from app.services.knowledge_search import (  # noqa: E402
    EMBEDDING_DIMENSION,
    KnowledgeChunk,
    KnowledgeSearchOutcome,
    KnowledgeSearchResult,
    KnowledgeSearchScope,
    search_approved_knowledge,
)

FIXTURE_PATH = ROOT / "docs" / "data" / "key82-rag-poc-chunks.json"
TEMP_TABLE = "key82_rag_poc_chunk"
ALLOWED_SECTIONS = frozenset({"medication", "caution", "emergency", "life"})
EXPECTED_HIT_IDS = ("synthetic-medication-current",)


def _poc_embedding(values: list[float]) -> tuple[float, ...]:
    """3차원 합성값을 운영 검색 계약의 384차원 벡터로 확장한다."""

    embedding = tuple(float(value) for value in values)
    if len(embedding) > EMBEDDING_DIMENSION:
        raise ValueError("PoC embedding exceeds the fixed embedding dimension")
    return embedding + (0.0,) * (EMBEDDING_DIMENSION - len(embedding))


def _chunk(row: dict[str, Any]) -> KnowledgeChunk:
    embedding = row["embedding_json"]
    if isinstance(embedding, str):
        embedding = json.loads(embedding)
    return KnowledgeChunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        hospital_id=row["hospital_id"],
        section_key=row["section_key"],
        body=row["body"],
        embedding=_poc_embedding(embedding),
        approval_status=ApprovalStatus(row["approval_status"]),
        is_current=bool(row["is_current"]),
        source_grade=SourceGrade(row["source_grade"]),
        license_verified=bool(row["license_verified"]),
        verified_at=date.fromisoformat(str(row["verified_at"])),
        review_due_at=date.fromisoformat(str(row["review_due_at"])) if row["review_due_at"] else None,
        claim_key=row["claim_key"],
        claim_value=row["claim_value"],
    )


def _poc_passed(result: KnowledgeSearchResult) -> bool:
    return (
        result.outcome is KnowledgeSearchOutcome.FOUND
        and tuple(hit.chunk.chunk_id for hit in result.hits) == EXPECTED_HIT_IDS
    )


async def _run(iterations: int, hospital_id: int) -> bool:
    from app.core.config import Config

    settings = Config()
    connection = await asyncmy.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        autocommit=True,
    )
    try:
        async with connection.cursor(DictCursor) as cursor:
            await cursor.execute("SELECT VERSION() AS version")
            version_row = await cursor.fetchone()
            mysql_version = str(version_row["version"])
            if not mysql_version.startswith("8."):
                raise RuntimeError(f"KEY-82 PoC requires MySQL 8.x, got {mysql_version}")
            await cursor.execute(
                f"""
                CREATE TEMPORARY TABLE {TEMP_TABLE} (
                    chunk_id VARCHAR(64) PRIMARY KEY,
                    document_id VARCHAR(64) NOT NULL,
                    hospital_id BIGINT NULL,
                    section_key VARCHAR(32) NOT NULL,
                    body TEXT NOT NULL,
                    embedding_json JSON NOT NULL,
                    approval_status VARCHAR(16) NOT NULL,
                    is_current BOOLEAN NOT NULL,
                    source_grade VARCHAR(1) NOT NULL,
                    license_verified BOOLEAN NOT NULL,
                    verified_at DATE NOT NULL,
                    review_due_at DATE NULL,
                    claim_key VARCHAR(100) NULL,
                    claim_value VARCHAR(100) NULL,
                    INDEX idx_key82_candidates
                      (hospital_id, approval_status, is_current, section_key)
                ) ENGINE=InnoDB
                """
            )
            fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
            await cursor.executemany(
                f"""
                INSERT INTO {TEMP_TABLE} (
                    chunk_id, document_id, hospital_id, section_key, body,
                    embedding_json, approval_status, is_current, source_grade,
                    license_verified, verified_at, review_due_at, claim_key, claim_value
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        row["chunk_id"],
                        row["document_id"],
                        row["hospital_id"],
                        row["section_key"],
                        row["body"],
                        json.dumps(row["embedding"]),
                        row["approval_status"],
                        row["is_current"],
                        row["source_grade"],
                        row["license_verified"],
                        row["verified_at"],
                        row["review_due_at"],
                        row.get("claim_key"),
                        row.get("claim_value"),
                    )
                    for row in fixtures
                ],
            )

            placeholders = ",".join(["%s"] * len(ALLOWED_SECTIONS))
            candidate_sql = f"""
                SELECT * FROM {TEMP_TABLE}
                WHERE approval_status = %s
                  AND is_current = TRUE
                  AND source_grade = %s
                  AND license_verified = TRUE
                  AND (hospital_id IS NULL OR hospital_id = %s)
                  AND section_key IN ({placeholders})
                  AND (review_due_at IS NULL OR review_due_at >= %s)
            """
            params = (
                ApprovalStatus.APPROVED.value,
                SourceGrade.A.value,
                hospital_id,
                *sorted(ALLOWED_SECTIONS),
                date.today().isoformat(),
            )
            scope = KnowledgeSearchScope(
                hospital_id=hospital_id,
                allowed_sections=ALLOWED_SECTIONS,
                searched_at=date.today(),
            )
            elapsed_ms: list[float] = []
            result = None
            for _ in range(iterations):
                started = perf_counter()
                await cursor.execute(candidate_sql, params)
                rows = await cursor.fetchall()
                result = search_approved_knowledge(
                    _poc_embedding([1.0, 0.0, 0.0]),
                    [_chunk(row) for row in rows],
                    scope,
                )
                elapsed_ms.append((perf_counter() - started) * 1000)

        assert result is not None
        p95 = quantiles(elapsed_ms, n=20, method="inclusive")[18] if len(elapsed_ms) > 1 else elapsed_ms[0]
        passed = _poc_passed(result)
        print(
            json.dumps(
                {
                    "mysql": mysql_version,
                    "fixture_rows": len(fixtures),
                    "iterations": iterations,
                    "outcome": result.outcome.value,
                    "hit_ids": [hit.chunk.chunk_id for hit in result.hits],
                    "scores": [round(hit.score, 4) for hit in result.hits],
                    "latency_ms": {"p50": round(median(elapsed_ms), 3), "p95": round(p95, 3)},
                    "passed": passed,
                },
                ensure_ascii=False,
            )
        )
        return passed
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--hospital-id", type=int, default=1)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be at least 1")
    if not asyncio.run(_run(args.iterations, args.hospital_id)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
