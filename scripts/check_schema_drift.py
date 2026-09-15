#!/usr/bin/env python3
"""**모델과 DB 가 맞는지 한 번에 본다** — KEY-198.

`docker compose up` 만 한 기계는 스키마가 조용히 밀려 있어도 아무 말을 안 한다.
`/api/v1/health` 는 `SELECT 1` 만 보기 때문에 **밀린 채로도 `ok`** 를 준다.

실제로 그렇게 됐다. 2026-08-27 에 내 기계에서 OCR 을 재려다 이렇게 죽었다.

    asyncmy.errors.OperationalError: (1054, "Unknown column 'unit' in 'field list'")

그때 표 개수만 세고 「25 개니까 맞다」고 했는데, 다시 칸 단위로 재 보니
`guide_section.drug_caution_content_id` 하나가 빠져 있었다. **표 개수는 맞는데
칸이 빈 상태**가 실제로 있고, 개수만 세는 확인은 그걸 못 잡는다.

사용법

    uv run python scripts/check_schema_drift.py

    맞으면   종료 0 · "드리프트 없음"
    다르면 종료 1 · 양방향으로 없는 표와 칸을 이름으로 찍는다

비교 범위는 표·컬럼 이름이다. 타입·인덱스 비교는 KEY-230 범위 밖이다.

`aerich upgrade` 를 돌린 뒤 이것으로 확인한다. 스키마를 실제로 맞추는 것은
`aerich` 의 일이고(KEY-196), 이 스크립트는 **재기만 한다.**
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tortoise import Tortoise  # noqa: E402

from app.core.db.databases import TORTOISE_ORM  # noqa: E402

SchemaGaps = tuple[list[str], list[tuple[str, list[str]]], list[str], list[tuple[str, list[str]]]]


def compare_schemas(expected: dict[str, set[str]], live: dict[str, set[str]]) -> SchemaGaps:
    """DB에서 빠진 표/칸, DB에만 있는 표/칸. DB는 변경하지 않는다."""
    common = sorted(expected.keys() & live.keys())
    missing = [(table, sorted(expected[table] - live[table])) for table in common if expected[table] - live[table]]
    extra = [(table, sorted(live[table] - expected[table])) for table in common if live[table] - expected[table]]
    return sorted(expected.keys() - live.keys()), missing, sorted(live.keys() - expected.keys()), extra


async def _gaps() -> SchemaGaps:
    try:
        await Tortoise.init(config=TORTOISE_ORM)
        connection = Tortoise.get_connection("default")
        database = (await connection.execute_query_dict("SELECT DATABASE() AS name"))[0]["name"]
        if not database:
            raise RuntimeError("검사할 DB가 선택되지 않았습니다")
        rows = await connection.execute_query_dict(
            "SELECT table_name AS t, column_name AS c FROM information_schema.columns WHERE table_schema = %s",
            [database],
        )
        live: dict[str, set[str]] = {}
        for row in rows:
            live.setdefault(row["t"], set()).add(row["c"])
        expected = {
            model._meta.db_table: set(model._meta.db_fields)
            for models in Tortoise.apps.values()
            for model in models.values()
        }
        # Aerich도 TORTOISE_ORM의 정식 모델이므로 임의 ignore 목록이 필요 없다.
        return compare_schemas(expected, live)
    finally:
        await Tortoise.close_connections()


async def main() -> int:
    tables, columns, extra_tables, extra_columns = await _gaps()
    if not any((tables, columns, extra_tables, extra_columns)):
        print("드리프트 없음 — 모델과 DB의 표·컬럼 이름이 맞습니다 (타입·인덱스 제외).")
        return 0

    print("🔴 모델과 DB의 표·컬럼 이름이 다릅니다.", file=sys.stderr)
    if tables:
        print(f"  없는 표 {len(tables)}: {', '.join(tables)}", file=sys.stderr)
    for table, gap in columns:
        print(f"  빠진 칸 {table}: {', '.join(gap)}", file=sys.stderr)
    if extra_tables:
        print(f"  DB에만 있는 표 {len(extra_tables)}: {', '.join(extra_tables)}", file=sys.stderr)
    for table, gap in extra_columns:
        print(f"  DB에만 있는 칸 {table}: {', '.join(gap)}", file=sys.stderr)
    print("\n  migration 이력과 모델을 확인하세요. 이 검사는 표·컬럼을 삭제하거나 변경하지 않습니다.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
