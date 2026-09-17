"""Recovery migration preserves old messages and uses recorded hold time."""

import runpy
from pathlib import Path

from aerich.utils import decompress_dict

from app.tests.migrations.test_upgrade_builds_the_whole_schema import (
    _aerich,
    _make_scratch_database,
    _one_session,
    _sql,
)

SCRATCH = "test_key362_source_recovery_probe"
MIGRATION = (
    Path(__file__).resolve().parents[2] / "core/db/migrations/models/69_20260917120000_key362_source_recovery.py"
)


def test_snapshot_has_recovery_fields_and_events():
    state = decompress_dict(runpy.run_path(str(MIGRATION))["MODELS_STATE"])
    fields = {field["name"] for field in state["models.GuideMessage"]["data_fields"]}
    assert {"source_failure_type", "source_failure_at", "source_retry_requested", "source_retry_generation"} <= fields
    events = str(state["models.GuideMessageEvent"]["data_fields"])
    assert "SOURCE_RETRY" in events and "SOURCE_VERIFIED" in events and "SOURCE_REQUEUED" in events


async def test_existing_schema_upgrade_keeps_messages_and_backfills_only_recorded_time():
    await _make_scratch_database(SCRATCH)
    try:
        before = _aerich(SCRATCH, "upgrade")
        assert before.returncode == 0, before.stderr[-1000:]
        migration = runpy.run_path(str(MIGRATION))
        await _sql(SCRATCH, await migration["downgrade"](None))
        # No patient data needed: temporarily relax FKs in this isolated fixture.
        await _one_session(
            SCRATCH,
            [
                "SET FOREIGN_KEY_CHECKS=0",
                "INSERT INTO guide_message (guide_message_id,guide_document_id,kind,status,scheduled_at,hold_reason,attempt_count,resend_sequence,created_at,updated_at) VALUES (1,999,'GUIDE','HELD','2026-09-17 10:00:00','SOURCE_NOT_DELETED',4,0,NOW(),NOW())",
                "INSERT INTO guide_message_event (guide_message_id,event_type,reason,created_at) VALUES (1,'HELD','SOURCE_NOT_DELETED','2026-09-17 10:05:00')",
                "SET FOREIGN_KEY_CHECKS=1",
            ],
        )
        upgrade_sql = await migration["upgrade"](None)
        await _one_session(SCRATCH, [part.strip() for part in upgrade_sql.split(";") if part.strip()])
        rows = await _sql(
            SCRATCH,
            "SELECT status,source_failure_type,source_failure_at,source_retry_requested,source_retry_generation,attempt_count FROM guide_message WHERE guide_message_id=1",
        )
        assert rows[0][0] == "HELD" and rows[0][1] is None
        assert str(rows[0][2]) == "2026-09-17 10:05:00"
        assert rows[0][3:] == (0, 0, 4)
        again = _aerich(SCRATCH, "upgrade")
        assert again.returncode == 0 and "Success upgrading" not in again.stdout
    finally:
        await _sql(None, f"DROP DATABASE IF EXISTS {SCRATCH}")
