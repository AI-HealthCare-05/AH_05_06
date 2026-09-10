"""KEY-277 must preserve the integrated migration baseline."""

import asyncio
import runpy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aerich.utils import decompress_dict


def test_snapshot_migration_keeps_preceding_tables():
    directory = Path(__file__).resolve().parents[2] / "core/db/migrations/models"
    files = list(directory.glob("[0-9]*_*.py"))
    numbers = [int(path.name.split("_", 1)[0]) for path in files]
    assert len(numbers) == len(set(numbers)), "Duplicate migration numbers"
    migration = next(directory.glob("*_key277_source_snapshots.py"))
    state = decompress_dict(runpy.run_path(str(migration))["MODELS_STATE"])
    tables = {model["table"] for model in state.values()}
    assert {
        "staff_account_event",
        "guide_safety_check",
        "guide_section_source_snapshot",
        "guide_generation_job",
    } <= tables
    caution = next(model for model in state.values() if model["table"] == "drug_caution_content")
    assert "physician_review" in {field["name"] for field in caution["data_fields"]}


def test_downgrade_refuses_to_discard_generation_audits():
    directory = Path(__file__).resolve().parents[2] / "core/db/migrations/models"
    migration = next(directory.glob("*_key277_source_snapshots.py"))
    downgrade = runpy.run_path(str(migration))["downgrade"]
    db = AsyncMock()
    db.execute_query_dict.return_value = [{"retained_records": 1}]
    with pytest.raises(RuntimeError, match="retain generation jobs and source evidence"):
        # Tortoise's session fixture owns the loop. asyncio.run() clears it and
        # breaks later ORM tests in the same pytest worker.
        asyncio.get_event_loop().run_until_complete(downgrade(db))
