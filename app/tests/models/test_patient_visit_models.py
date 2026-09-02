from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from aerich.utils import decompress_dict, import_py_file
from tortoise import Tortoise
from tortoise.fields import OnDelete
from tortoise.fields.relational import BackwardFKRelation, ForeignKeyFieldInstance

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
    return import_py_file(migration_paths[0])


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
    relation = cast(ForeignKeyFieldInstance, Visit._meta.fields_map["patient"])

    assert Visit._meta.db_table == "visit"
    assert Visit._meta.pk_attr == "visit_id"
    assert relation.related_model is Patient
    assert relation.source_field == "patient_id"
    assert relation.on_delete is OnDelete.RESTRICT
    reverse = cast(BackwardFKRelation, Patient._meta.fields_map["visits"])
    assert reverse.related_model is Visit
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
    #: **`use_tz` 는 꺼져 있어야 한다.** 켜면 `tortoise.timezone.now()` 가 UTC 를
    #: 주는데, asyncmy 는 넣을 때 tzinfo 를 버리고 벽시계만 적고(KEY-181) 읽을
    #: 때는 아래 `timezone` 으로 도장을 찍는다 — `auto_now_add` 가 전부 아홉
    #: 시간 어긋나고, 링크 만료와 인증번호 잠금이 즉시 풀린다.
    #: 자세한 것은 `app/tests/clock/test_stored_times.py`.
    assert TORTOISE_ORM["use_tz"] is False
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
