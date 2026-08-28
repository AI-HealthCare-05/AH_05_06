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
    밀렸으면 종료 1 · 없는 표와 빠진 칸을 이름으로 찍는다

`aerich upgrade` 를 돌린 뒤 이것으로 확인한다. 스키마를 실제로 맞추는 것은
`aerich` 의 일이고(KEY-196), 이 스크립트는 **재기만 한다.**
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tortoise import Tortoise  # noqa: E402

from app.core.db.databases import TORTOISE_ORM  # noqa: E402


async def _gaps() -> tuple[list[str], list[tuple[str, list[str]]]]:
    """(없는 표, [(표, 빠진 칸들)]) 을 돌려준다."""
    await Tortoise.init(config=TORTOISE_ORM)
    connection = Tortoise.get_connection("default")

    database = (await connection.execute_query_dict("SELECT DATABASE() AS name"))[0]["name"]
    rows = await connection.execute_query_dict(
        "SELECT table_name AS t, column_name AS c FROM information_schema.columns WHERE table_schema = %s",
        [database],
    )

    live: dict[str, set[str]] = {}
    for row in rows:
        live.setdefault(row["t"], set()).add(row["c"])

    missing_tables: list[str] = []
    missing_columns: list[tuple[str, list[str]]] = []
    for models in Tortoise.apps.values():
        for model in models.values():
            table = model._meta.db_table
            if table not in live:
                missing_tables.append(table)
                continue
            # **칸 단위로 본다.** 표만 세면 위 사고를 못 잡는다.
            gap = set(model._meta.db_fields) - live[table]
            if gap:
                missing_columns.append((table, sorted(gap)))

    await Tortoise.close_connections()
    return sorted(missing_tables), sorted(missing_columns)


async def main() -> int:
    tables, columns = await _gaps()
    if not tables and not columns:
        print("드리프트 없음 — 모델과 DB 가 맞습니다.")
        return 0

    print("🔴 스키마가 모델보다 밀려 있습니다.", file=sys.stderr)
    if tables:
        print(f"  없는 표 {len(tables)}: {', '.join(tables)}", file=sys.stderr)
    for table, gap in columns:
        print(f"  빠진 칸 {table}: {', '.join(gap)}", file=sys.stderr)
    print("\n  `uv run aerich upgrade` 를 먼저 돌려 주세요 (KEY-196).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
