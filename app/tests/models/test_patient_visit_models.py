import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from aerich.utils import decompress_dict
from tortoise import Tortoise
from tortoise.fields import OnDelete

from app.core.db.databases import TORTOISE_APP_MODELS, TORTOISE_ORM
from app.models.patients import Patient, PatientGender
from app.models.visits import Visit, VisitStatus


@pytest.fixture(scope="module", autouse=True)
def initialize_models() -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")


def load_migration() -> ModuleType:
    migration_dir = Path(__file__).parents[2] / "core" / "db" / "migrations" / "models"
    migration_paths = list(migration_dir.glob("1_*_add_patient_visit.py"))
    assert len(migration_paths) == 1
    migration_path = migration_paths[0]
    spec = importlib.util.spec_from_file_location("patient_visit_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_patient_model_matches_frozen_contract() -> None:
    assert Patient._meta.db_table == "patient"
    assert Patient._meta.pk_attr == "patient_id"
    assert set(PatientGender) == {
        PatientGender.FEMALE,
        PatientGender.MALE,
        PatientGender.OTHER,
        PatientGender.UNKNOWN,
    }
    assert Patient._meta.fields_map["gender"].default is PatientGender.UNKNOWN
    assert "age" not in Patient._meta.fields_map
    assert Patient._meta.unique_together == (("hospital_id", "hospital_patient_no"),)
    assert ("hospital_id", "name", "birth_date") in Patient._meta.indexes
    assert ("hospital_id", "phone") in Patient._meta.indexes


def test_visit_model_keeps_patient_one_to_many_relation() -> None:
    relation = Visit._meta.fields_map["patient"]

    assert Visit._meta.db_table == "visit"
    assert Visit._meta.pk_attr == "visit_id"
    assert relation.related_model is Patient
    assert relation.source_field == "patient_id"
    assert relation.on_delete is OnDelete.RESTRICT
    assert Patient._meta.fields_map["visits"].related_model is Visit
    assert set(VisitStatus) == {
        VisitStatus.SCHEDULED,
        VisitStatus.COMPLETED,
        VisitStatus.CANCELED,
    }
    assert Visit._meta.fields_map["planned_stop"].default is False
    assert Visit._meta.fields_map["status"].default is VisitStatus.COMPLETED


def test_models_are_registered_for_aerich() -> None:
    assert "app.models.patients" in TORTOISE_APP_MODELS
    assert "app.models.visits" in TORTOISE_APP_MODELS
    assert TORTOISE_ORM["use_tz"] is True
    assert TORTOISE_ORM["timezone"] == "Asia/Seoul"


@pytest.mark.asyncio
async def test_migration_creates_and_rolls_back_in_dependency_order() -> None:
    migration = load_migration()
    models_state = decompress_dict(migration.MODELS_STATE)
    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    assert upgrade_sql.index("CREATE TABLE IF NOT EXISTS `patient`") < upgrade_sql.index(
        "CREATE TABLE IF NOT EXISTS `visit`"
    )
    assert models_state
    assert "FOREIGN KEY (`patient_id`) REFERENCES `patient` (`patient_id`) ON DELETE RESTRICT" in upgrade_sql
    assert "`planned_stop` BOOL NOT NULL DEFAULT 0" in upgrade_sql
    assert "UNIQUE KEY" in upgrade_sql
    assert "(`hospital_id`, `hospital_patient_no`)" in upgrade_sql
    assert downgrade_sql.index("DROP TABLE IF EXISTS `visit`") < downgrade_sql.index("DROP TABLE IF EXISTS `patient`")
