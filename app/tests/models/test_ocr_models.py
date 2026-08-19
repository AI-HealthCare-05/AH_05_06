from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from aerich.utils import decompress_dict, import_py_file
from tortoise import Tortoise
from tortoise.exceptions import ValidationError
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


def load_migrations() -> list[ModuleType]:
    migration_dir = Path(__file__).parents[2] / "core" / "db" / "migrations" / "models"
    migration_paths = [next(migration_dir.glob(f"{version}_*_add_ocr_*.py")) for version in range(2, 7)]
    return [import_py_file(path) for path in migration_paths]


def test_ocr_job_is_scoped_to_hospital_and_visit() -> None:
    relation = OcrJob._meta.fields_map["visit"]

    assert OcrJob._meta.pk_attr == "ocr_job_id"
    assert relation.related_model is Visit
    assert relation.source_field == "visit_id"
    assert relation.on_delete is OnDelete.RESTRICT
    assert OcrJob._meta.fields_map["status"].default is OcrJobStatus.PROCESSING
    assert OcrJob._meta.fields_map["started_at"].null is True
    assert ("hospital_id", "status", "created_at") in OcrJob._meta.indexes


def test_result_keeps_raw_text_fields_candidates_and_audit_metadata() -> None:
    assert OcrResult._meta.fields_map["ocr_job"].unique is True
    assert OcrDocumentText._meta.fields_map["raw_text"].null is True
    assert OcrDocumentText._meta.fields_map["raw_text_purged_at"].null is True
    assert OcrField._meta.fields_map["confidence"].decimal_places == 4
    assert OcrField._meta.fields_map["modified_by"].null is True
    assert OcrField._meta.fields_map["confirmed_by"].null is True
    assert OcrFieldCandidate._meta.unique_together == (("ocr_field", "rank"),)


def test_relation_names_generate_expected_source_columns() -> None:
    assert OcrJobDocument._meta.fields_map["ocr_job"].source_field == "ocr_job_id"
    assert OcrDocumentText._meta.fields_map["ocr_result"].source_field == "ocr_result_id"
    assert OcrField._meta.fields_map["ocr_result"].source_field == "ocr_result_id"
    assert OcrFieldCandidate._meta.fields_map["ocr_field"].source_field == "ocr_field_id"
    assert OcrJobDocument._meta.unique_together == (("ocr_job", "document_id"),)
    assert OcrDocumentText._meta.unique_together == (("ocr_result", "document_id"),)
    assert OcrField._meta.indexes == (("ocr_result", "field_type"),)
    assert OcrFieldCandidate._meta.unique_together == (("ocr_field", "rank"),)


def test_job_supports_multiple_source_documents_without_duplicates() -> None:
    relation = OcrJobDocument._meta.fields_map["ocr_job"]

    assert relation.related_model is OcrJob
    assert relation.on_delete is OnDelete.CASCADE


def test_corrected_value_wins_without_erasing_extracted_value() -> None:
    field = OcrField(extracted_value="candidate-a", corrected_value="reviewed-value")
    assert field.value == "reviewed-value"
    assert field.extracted_value == "candidate-a"


def test_unread_expected_field_keeps_an_explicit_row() -> None:
    field = OcrField(field_type="synthetic_required_field", extracted_value=None)

    assert field.field_type == "synthetic_required_field"
    assert field.value is None


def test_raw_text_uses_tortoise_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    purged_at = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
    monkeypatch.setattr("app.models.ocr.now", lambda: purged_at)
    document = OcrDocumentText(raw_text="synthetic OCR text only")

    document.purge_raw_text()

    assert document.raw_text is None
    assert document.raw_text_purged_at == purged_at


def test_numeric_ranges_are_validated_before_write() -> None:
    OcrJob._meta.fields_map["progress"].validate(100)
    OcrField._meta.fields_map["confidence"].validate(Decimal("1.0000"))

    with pytest.raises(ValidationError):
        OcrJob._meta.fields_map["progress"].validate(101)
    with pytest.raises(ValidationError):
        OcrField._meta.fields_map["confidence"].validate(Decimal("1.0001"))
    with pytest.raises(ValidationError):
        OcrFieldCandidate._meta.fields_map["rank"].validate(0)


def test_models_are_registered_for_aerich() -> None:
    assert "app.models.ocr" in TORTOISE_APP_MODELS


@pytest.mark.asyncio
async def test_migration_has_safe_relations_and_rollback_order() -> None:
    migrations = load_migrations()
    upgrade_sql = "\n".join([await migration.upgrade(None) for migration in migrations])
    downgrade_sql = "\n".join([await migration.downgrade(None) for migration in reversed(migrations)])

    assert all(decompress_dict(migration.MODELS_STATE) for migration in migrations)
    assert upgrade_sql.index("CREATE TABLE IF NOT EXISTS `ocr_job`") < upgrade_sql.index(
        "CREATE TABLE IF NOT EXISTS `ocr_result`"
    )
    assert upgrade_sql.index("CREATE TABLE IF NOT EXISTS `ocr_field`") < upgrade_sql.index(
        "CREATE TABLE IF NOT EXISTS `ocr_field_candidate`"
    )
    assert "ON DELETE SET NULL" in upgrade_sql
    assert "(`ocr_job_id`, `document_id`)" in upgrade_sql
    assert "`started_at` DATETIME(6)" in upgrade_sql
    assert "`started_at` DATETIME(6) NOT NULL" not in upgrade_sql
    assert downgrade_sql.index("DROP TABLE IF EXISTS `ocr_field_candidate`") < downgrade_sql.index(
        "DROP TABLE IF EXISTS `ocr_field`"
    )
    assert downgrade_sql.index("DROP TABLE IF EXISTS `ocr_result`") < downgrade_sql.index(
        "DROP TABLE IF EXISTS `ocr_job`"
    )
