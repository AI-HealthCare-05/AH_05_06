"""Opt-in clean/legacy migration verification on dedicated local MySQL only.

Creates two fresh databases, never drops existing data. Run with the KEY-238
local test credentials and KEY238_MIGRATION_TEST=1. No credentials are printed.
"""

import asyncio
import os
import shutil
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from aerich import Command  # noqa: E402
from tortoise import Tortoise  # noqa: E402

from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.visits import CheckIn, CheckInSignal, GuideStatus  # noqa: E402
from app.tests.patient_links.test_patient_links import make_guide, make_hospital  # noqa: E402


async def assert_append_only(db, event):
    for sql in (
        "UPDATE check_in_signal SET answer_key='missing' WHERE signal_id=%s",
        "DELETE FROM check_in_signal WHERE signal_id=%s",
    ):
        try:
            await db.execute_query(sql, [event.pk])
        except Exception as error:
            assert "append-only" in str(error)
        else:
            raise AssertionError("append-only trigger did not block mutation")


async def run():
    cfg = deepcopy(TORTOISE_ORM)
    credentials = cfg["connections"]["default"]["credentials"]
    if (
        os.environ.get("KEY238_MIGRATION_TEST") != "1"
        or credentials["host"] != "127.0.0.1"
        or credentials["port"] != 18377
    ):
        raise RuntimeError("Dedicated KEY-238 local database required")
    await Tortoise.init(config=cfg)
    connection = Tortoise.get_connection("default")
    for name in ("key238_v63_clean", "key238_v63_existing"):
        # No IF NOT EXISTS: a rerun must not quietly consume somebody else's DB.
        await connection.execute_script(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
    await Tortoise.close_connections()
    migrations = ROOT / "app/core/db/migrations"
    for name in ("key238_v63_clean", "key238_v63_existing"):
        credentials["database"] = name
        legacy_id = None
        if name == "key238_v63_existing":
            with tempfile.TemporaryDirectory(prefix="key238-migrations-") as scratch:
                dest = Path(scratch) / "models"
                dest.mkdir()
                for source in (migrations / "models").glob("*.py"):
                    if source.name.split("_")[0].isdigit() and int(source.name.split("_")[0]) < 63:
                        shutil.copy2(source, dest / source.name)
                command = Command(cfg, location=scratch)
                await command.init()
                await command.upgrade()
                guide = await make_guide(
                    await make_hospital("KEY238 이전 스키마 합성의원"), GuideStatus.SCHEDULED_TO_SEND
                )
                legacy_id = guide.pk
                await Tortoise.get_connection("default").execute_insert(
                    "INSERT INTO check_in (guide_document_id, medication, pain_types) VALUES (%s, %s, %s)",
                    [guide.pk, "taking", "[]"],
                )
                await Tortoise.close_connections()
        command = Command(cfg, location=str(migrations))
        await command.init()
        applied = await command.upgrade()
        assert any(filename.startswith("63_") for filename in applied)
        assert await command.upgrade() == []
        if legacy_id is not None:
            saved = await CheckIn.get(guide_document_id=legacy_id)
            assert saved.medication == "taking" and saved.note is None
            guide_id = legacy_id
        else:
            guide = await make_guide(await make_hospital("KEY238 신규 스키마 합성의원"), GuideStatus.SCHEDULED_TO_SEND)
            guide_id = guide.pk
        event = await CheckInSignal.create(
            guide_document_id=guide_id,
            answer_key="taking",
            client_id="synthetic",
            client_session_id="tab",
            client_sequence=1,
        )
        db = Tortoise.get_connection("default")
        await assert_append_only(db, event)
        print(f"PASS {name}: upgrade, rerun, legacy preservation, append-only")
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(run())
