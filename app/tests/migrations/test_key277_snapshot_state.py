"""KEY-277 must preserve the integrated migration baseline."""

import runpy
from pathlib import Path

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
    } <= tables
    caution = next(model for model in state.values() if model["table"] == "drug_caution_content")
    assert "physician_review" in {field["name"] for field in caution["data_fields"]}
