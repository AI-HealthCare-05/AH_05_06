import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from tortoise import Tortoise
from tortoise.fields import OnDelete

from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.ocr import (
    OcrDocumentText,
    OcrField,
    OcrFieldCandidate,
    OcrJob,
    OcrJobDocument,
    OcrJobStatus,
    OcrResult,
)
from app.models.visits import Visit


@pytest.fixture(scope="module", autouse=True)
def initialize_models() -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")


def load_migration() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "app"
        / "core"
        / "db"
        / "migrations"
        / "models"
        / "2_20260819173000_add_ocr_models.py"
    )
    spec = importlib.util.spec_from_file_location("ocr_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ocr_job_is_scoped_to_hospital_and_visit() -> None:
    relation = OcrJob._meta.fields_map["visit"]

    assert OcrJob._meta.pk_attr == "ocr_job_id"
    assert relation.related_model is Visit
    assert relation.source_field == "visit_id"
    assert relation.on_delete is OnDelete.RESTRICT
    assert OcrJob._meta.fields_map["status"].default is OcrJobStatus.PROCESSING
    assert ("hospital_id", "status", "created_at") in OcrJob._meta.indexes


def test_result_keeps_raw_text_fields_candidates_and_audit_metadata() -> None:
    assert OcrResult._meta.fields_map["job"].unique is True
    assert OcrDocumentText._meta.fields_map["raw_text"].null is True
    assert OcrDocumentText._meta.fields_map["raw_text_purged_at"].null is True
    assert OcrField._meta.fields_map["confidence"].decimal_places == 4
    assert OcrField._meta.fields_map["modified_by"].null is True
    assert OcrField._meta.fields_map["confirmed_by"].null is True
    assert OcrFieldCandidate._meta.unique_together == (("field", "rank"),)


def test_job_supports_multiple_source_documents_without_duplicates() -> None:
    relation = OcrJobDocument._meta.fields_map["job"]

    assert relation.related_model is OcrJob
    assert relation.on_delete is OnDelete.CASCADE
    assert OcrJobDocument._meta.unique_together == (("job", "document_id"),)


def test_corrected_value_wins_without_erasing_extracted_value() -> None:
    field = OcrField(extracted_value="candidate-a", corrected_value="reviewed-value")
    assert field.value == "reviewed-value"
    assert field.extracted_value == "candidate-a"


def test_raw_text_can_be_purged_with_timestamp() -> None:
    purged_at = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
    document = OcrDocumentText(raw_text="synthetic OCR text only")

    document.purge_raw_text(purged_at=purged_at)

    assert document.raw_text is None
    assert document.raw_text_purged_at == purged_at


def test_models_are_registered_for_aerich() -> None:
    assert "app.models.ocr" in TORTOISE_APP_MODELS


@pytest.mark.asyncio
async def test_migration_has_constraints_and_safe_rollback_order() -> None:
    migration = load_migration()
    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    assert upgrade_sql.index("CREATE TABLE IF NOT EXISTS `ocr_job`") < upgrade_sql.index(
        "CREATE TABLE IF NOT EXISTS `ocr_result`"
    )
    assert upgrade_sql.index("CREATE TABLE IF NOT EXISTS `ocr_field`") < upgrade_sql.index(
        "CREATE TABLE IF NOT EXISTS `ocr_field_candidate`"
    )
    assert "CHECK (`progress` BETWEEN 0 AND 100)" in upgrade_sql
    assert "`confidence` >= 0 AND `confidence` <= 1" in upgrade_sql
    assert "ON DELETE SET NULL" in upgrade_sql
    assert "UNIQUE KEY `uid_ocr_job_document` (`ocr_job_id`, `document_id`)" in upgrade_sql
    assert downgrade_sql.index("DROP TABLE IF EXISTS `ocr_field_candidate`") < downgrade_sql.index(
        "DROP TABLE IF EXISTS `ocr_field`"
    )
    assert downgrade_sql.index("DROP TABLE IF EXISTS `ocr_result`") < downgrade_sql.index(
        "DROP TABLE IF EXISTS `ocr_job`"
    )
