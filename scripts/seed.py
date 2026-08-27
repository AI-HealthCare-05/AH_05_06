#!/usr/bin/env python3
"""합성 데이터 seed 명령 — KEY-29

고정 데이터로 개발 DB 를 채운다. 같은 명령을 반복 실행해도 데이터가 쌓이지 않는다.

사용법:
    SEED_STAFF_PASSWORD=<pw> uv run python scripts/seed.py [--mode MODE]

옵션:
    --mode empty   아무것도 적재하지 않음 (S1-1 빈 화면 확인용)
    --mode staff   직원 계정 17개와 병원 2개만 적재 (기본값)
    --mode full    직원 + 환자·진료 데이터 전체 적재

전제:
    - docs/data/synthetic-staff.csv 가 있어야 한다.
    - docs/data/synthetic-patients.csv 가 있어야 한다 (--mode full 시).
    - SEED_STAFF_PASSWORD 환경변수가 없으면 실행을 거부한다.
    - 운영 환경(ENV=prod)에서는 실행을 거부한다.

건너뛰는 항목 (표가 아직 없다):
    - lab_result, visit_flag — KEY-136 이 「계획」으로 가른 것들.
      왜 아직 없는지는 mapping.py 의 PLANNED_TABLES 에 이유와 함께 있다.
    - DERIVED·EVENT·OCR_INPUT·DOC_ONLY 칸 (mapping.py 참조)

처방(prescription · prescription_item)은 KEY-137 에서 적재하기 시작했다.
"""

import argparse
import asyncio
import csv
import os
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parent.parent
STAFF_CSV = ROOT / "docs" / "data" / "synthetic-staff.csv"
PATIENTS_CSV = ROOT / "docs" / "data" / "synthetic-patients.csv"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tortoise import Tortoise  # noqa: E402

from app.core.config import Config  # noqa: E402
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.core.utils.common import normalize_phone_number  # noqa: E402
from app.core.utils.security import hash_password  # noqa: E402
from app.models.catalog import ApprovalStatus, DrugCautionContent, PrescriptionSet  # noqa: E402
from app.models.patients import Patient  # noqa: E402
from app.models.prescriptions import Prescription, PrescriptionItem  # noqa: E402
from app.models.staffs import Hospital, Staff, StaffStatus  # noqa: E402
from app.models.visits import Visit, VisitStatus  # noqa: E402
from app.tests.fixtures.catalog import DRUG_CAUTION_CONTENTS, PRESCRIPTION_SETS  # noqa: E402
from app.tests.fixtures.prescriptions import PrescriptionRowError, items_from_row  # noqa: E402
from app.tests.fixtures.staff import StaffDataError, all_staff  # noqa: E402
from app.tests.fixtures.validation import validate_canonical_patient_data  # noqa: E402

_CONFIG = Config()

SEED_PASSWORD_ENV = "SEED_STAFF_PASSWORD"

# CSV 의 H1/H2 레이블 → seed 전용 병원 이름
_HOSPITAL_NAMES: dict[str, str] = {
    "H1": "기준의원",
    "H2": "격리의원",
}


class SeedDataError(ValueError):
    """합성 데이터 관계나 값이 계약과 맞지 않을 때 발생한다."""


class SeedStaffRow(Protocol):
    staff_id: int
    name: str
    roles: list[str]


def _patient_values(row: dict[str, str]) -> dict[str, object]:
    """CSV 환자 값을 API 저장 계약과 같은 형식으로 정규화한다."""
    phone = normalize_phone_number(row["휴대폰"].strip())
    if not 10 <= len(phone) <= 11:
        raise SeedDataError(f"휴대폰 형식이 올바르지 않음 (시나리오 {row['시나리오ID']})")
    return {
        "name": row["이름"].strip(),
        "birth_date": row["생년월일"].strip(),
        "phone": phone,
        "sms_consent": row["문자수신동의"].strip() == "Y",
    }


def _doctor_ids_by_name(staff_rows: Iterable[SeedStaffRow]) -> dict[str, int]:
    """의사 역할만 이름으로 연결하고, 같은 병원 내 동명이인은 거부한다."""
    result: dict[str, int] = {}
    for staff in staff_rows:
        if "doctor" not in (staff.roles or []):
            continue
        if staff.name in result:
            raise SeedDataError(f"같은 병원에 동명이인 의사가 있어 이름만으로 연결할 수 없음: {staff.name}")
        result[staff.name] = staff.staff_id
    return result


def _validate_patient_rows(
    rows: list[dict[str, str]],
    doctor_map: dict[str, int],
) -> dict[str, dict[str, object]]:
    """DB 쓰기 전에 환자 값과 진료 담당의 관계를 모두 검증한다."""
    patient_values_by_chart: dict[str, dict[str, object]] = {}
    for row in rows:
        chart_no = row["차트번호"].strip()
        patient_values = _patient_values(row)
        previous = patient_values_by_chart.setdefault(chart_no, patient_values)
        if previous != patient_values:
            raise SeedDataError(f"같은 차트번호의 환자 정보가 서로 다름: {chart_no}")

        if not row["진료일"].strip():
            continue
        doctor_name = row["담당의"].strip()
        if doctor_name and doctor_name not in doctor_map:
            raise SeedDataError(f"담당의 {doctor_name!r} 를 H1 의사에서 찾을 수 없음 (시나리오 {row['시나리오ID']})")
    return patient_values_by_chart


def _guard_environment() -> None:
    if str(_CONFIG.ENV).lower() == "prod":
        print("오류: 운영 환경(ENV=prod)에서는 seed 를 실행할 수 없습니다.", file=sys.stderr)
        sys.exit(1)


def _require_password() -> str:
    password = os.environ.get(SEED_PASSWORD_ENV)
    if not password:
        print(
            f"오류: {SEED_PASSWORD_ENV} 환경변수가 없습니다.\n"
            f"  SEED_STAFF_PASSWORD=<개발용 비밀번호> uv run python scripts/seed.py",
            file=sys.stderr,
        )
        sys.exit(1)
    return password


def _require_csv(path: Path, hint: str) -> None:
    if not path.exists():
        print(
            f"오류: {path} 파일이 없습니다.\n  {hint}",
            file=sys.stderr,
        )
        sys.exit(1)


def _parse_dt(value: str, label: str = "") -> datetime | None:
    """'YYYY-MM-DD HH:MM' 문자열을 KST timezone-aware datetime 으로 변환한다."""
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return datetime.strptime(stripped, "%Y-%m-%d %H:%M").replace(tzinfo=_CONFIG.TIMEZONE)
    except ValueError:
        print(f"[seed] 경고: 날짜 파싱 실패 {label!r} = {stripped!r}", file=sys.stderr)
        return None


async def _seed_hospitals() -> dict[str, Hospital]:
    """H1/H2 두 병원을 생성(또는 조회)하고 레이블 → Hospital 매핑을 반환한다."""
    result: dict[str, Hospital] = {}
    created = 0
    for label, name in _HOSPITAL_NAMES.items():
        hospital, was_created = await Hospital.get_or_create(name=name)
        result[label] = hospital
        if was_created:
            created += 1
    print(f"[hospitals] created={created} existing={len(result) - created} total={len(result)}")
    return result


async def seed_staff(password: str) -> dict[str, Hospital]:
    """직원 계정을 Staff 테이블에 적재한다.

    멱등성: login_id 기준 upsert.
    반환:   H1/H2 레이블 → Hospital 매핑 (seed_patients 가 이어받는다).
    """
    _require_csv(
        STAFF_CSV,
        hint="저장소를 최신화하세요.",
    )

    try:
        staff_rows = all_staff()
    except StaffDataError as exc:
        print(f"오류: CSV 검증 실패 — {exc}", file=sys.stderr)
        sys.exit(1)

    hashed = hash_password(password)
    hospitals = await _seed_hospitals()
    created = updated = 0

    for s in staff_rows:
        hospital = hospitals[s.hospital]
        status = StaffStatus.LEFT if s.status == "left" else StaffStatus.ACTIVE

        _, was_created = await Staff.get_or_create(
            login_id=s.login_id,
            defaults={
                "hospital_id": hospital.hospital_id,
                "password_hash": hashed,
                "name": s.name,
                "roles": list(s.roles),
                "must_change_password": s.must_change_password,
                "status": status,
                "left_at": _parse_dt(s.left_at, f"{s.login_id}.left_at"),
                "last_login_at": _parse_dt(s.last_login_at, f"{s.login_id}.last_login_at"),
            },
        )

        if was_created:
            created += 1
        else:
            staff_obj = await Staff.get(login_id=s.login_id)
            staff_obj.hospital_id = hospital.hospital_id  # type: ignore[assignment]
            staff_obj.password_hash = hashed
            staff_obj.name = s.name
            staff_obj.roles = list(s.roles)
            staff_obj.must_change_password = s.must_change_password
            staff_obj.status = status
            staff_obj.left_at = _parse_dt(s.left_at, f"{s.login_id}.left_at")
            staff_obj.last_login_at = _parse_dt(s.last_login_at, f"{s.login_id}.last_login_at")
            await staff_obj.save()
            updated += 1

    print(f"[staff] created={created} updated={updated} total={len(staff_rows)}")
    return hospitals


async def seed_patients(hospitals: dict[str, Hospital]) -> None:
    """환자·진료 데이터를 patient·visit 테이블에 적재한다.

    멱등성:
        patient: (hospital_id, hospital_patient_no) 기준 get_or_create
        visit:   (hospital_id, patient_id, visited_at) 기준 get_or_create

    담당의 이름 해석:
        H1 소속 Staff.name 으로 조회한다.
        H2 에 동명이인(SYN-STAFF-16 박연)이 있으므로 반드시 hospital 로 필터한다.

    처방:
        prescription: (visit) 기준 get_or_create — 진료당 한 묶음
        prescription_item: 처방이 새로 생길 때만 함께 만든다

    건너뜀:
        lab_result, visit_flag — 표가 없다. KEY-136 이 「계획」으로 가른 것들
    """
    _require_csv(
        PATIENTS_CSV,
        hint="저장소를 최신화하세요.",
    )
    validate_canonical_patient_data()

    h1 = hospitals["H1"]

    # H1 소속 의사 이름 → staff_id 매핑
    h1_staff = await Staff.filter(hospital_id=h1.hospital_id).all()
    doctor_map = _doctor_ids_by_name(h1_staff)

    with PATIENTS_CSV.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # 검증 오류가 나도 DB 가 일부 적재된 상태로 남지 않게 전체 행을 먼저 확인한다.
    patient_values_by_chart = _validate_patient_rows(rows, doctor_map)

    # 1단계: 환자 upsert
    # 동일 차트번호가 여러 진료 행에 반복될 수 있으므로 첫 행만 처리한다.
    patient_map: dict[str, Patient] = {}
    created_p = updated_p = 0

    for row in rows:
        chart_no = row["차트번호"].strip()
        if chart_no in patient_map:
            continue

        patient_values = patient_values_by_chart[chart_no]
        patient, was_created = await Patient.get_or_create(
            hospital_id=h1.hospital_id,
            hospital_patient_no=chart_no,
            defaults=patient_values,
        )
        patient_map[chart_no] = patient
        if was_created:
            created_p += 1
        else:
            await Patient.filter(
                hospital_id=h1.hospital_id,
                hospital_patient_no=chart_no,
            ).update(**patient_values)
            updated_p += 1

    print(f"[patients] created={created_p} updated={updated_p} total={len(patient_map)}")

    # 2단계: 진료 upsert
    created_v = skipped_v = error_v = 0
    created_presc = created_item = 0

    for row in rows:
        visit_date_str = row["진료일"].strip()
        if not visit_date_str:
            skipped_v += 1
            continue

        chart_no = row["차트번호"].strip()
        patient = patient_map[chart_no]

        try:
            # 병원 시간(KST)으로 생성해야 get_or_create 조회와 저장 값이 일치한다.
            # UTC로 만들면 Tortoise use_tz=True가 저장 시 KST로 변환하는데,
            # 조회는 UTC로 해서 매 실행마다 새 행이 쌓인다.
            visited_at = datetime.strptime(visit_date_str, "%Y-%m-%d").replace(
                hour=12, minute=0, second=0, tzinfo=_CONFIG.TIMEZONE
            )
        except ValueError:
            print(
                f"[visits] 날짜 파싱 실패: {visit_date_str!r} (시나리오 {row['시나리오ID']})",
                file=sys.stderr,
            )
            error_v += 1
            continue

        doctor_name = row["담당의"].strip()
        doctor_id = doctor_map.get(doctor_name)

        planned_stop = row["진료상태"].strip() == "계획된 중단"

        visit, was_created = await Visit.get_or_create(
            hospital_id=h1.hospital_id,
            patient=patient,
            visited_at=visited_at,
            defaults={
                "doctor_id": doctor_id,
                "planned_stop": planned_stop,
                "status": VisitStatus.COMPLETED,
            },
        )
        if was_created:
            created_v += 1

        created_p, created_i = await _seed_prescription(visit, row)
        created_presc += created_p
        created_item += created_i

    print(f"[visits] created={created_v} skipped={skipped_v} error={error_v} total={len(rows)}")
    print(f"[prescriptions] created={created_presc} items={created_item}")


async def _seed_prescription(visit: Visit, row: dict[str, str]) -> tuple[int, int]:
    """한 진료의 처방을 적재한다 — KEY-137.

    행을 어떻게 가르는지는 `app/tests/fixtures/prescriptions.py` 가 안다.
    거기 두는 이유는 **검사가 닿아야 하기 때문**이다 — 규칙이 이 함수 안에 있으면
    DB 를 띄우고 스크립트를 통째로 돌려야만 확인할 수 있다.
    """
    prescription_set = row["처방세트"].strip()
    if not prescription_set:
        return 0, 0

    try:
        items = items_from_row(row["약"], row["용법"], row["처방일수"])
    except PrescriptionRowError as error:
        print(f"[prescriptions] {error} (시나리오 {row['시나리오ID']}) — 건너뛴다", file=sys.stderr)
        return 0, 0
    if not items:
        return 0, 0

    prescription, was_created = await Prescription.get_or_create(
        visit=visit,
        defaults={"prescription_set": prescription_set},
    )
    if not was_created:
        return 0, 0  # 이미 넣은 진료다. 다시 실행해도 쌓이지 않는다

    for item in items:
        await PrescriptionItem.create(
            prescription=prescription,
            name=item.name,
            frequency=item.frequency,
            duration_days=item.duration_days,
        )
    return 1, len(items)


async def seed_catalog() -> None:
    """처방 세트 8종과 주의·응급 문구 마스터를 적재한다 — KEY-165.

    같은 명령을 반복 실행해도 데이터가 쌓이지 않는다(name 기준 get_or_create).
    APPROVED 문구는 `approved_key` 를 채워 "세트·섹션당 하나" 제약을 DB 가 지키게 한다.
    """
    # 처방 세트 8종
    created_sets = 0
    for row in PRESCRIPTION_SETS:
        _, was_created = await PrescriptionSet.get_or_create(name=row.name)
        if was_created:
            created_sets += 1
    print(f"[catalog] prescription_set created={created_sets} skipped={len(PRESCRIPTION_SETS) - created_sets}")

    # 세트 이름 → id 역색인 (콘텐츠 삽입에 사용)
    sets_by_name: dict[str, PrescriptionSet] = {ps.name: ps async for ps in PrescriptionSet.all()}

    created_contents = 0
    skipped_contents = 0
    for content_row in DRUG_CAUTION_CONTENTS:
        ps = sets_by_name.get(content_row.prescription_set_name)
        if ps is None:
            print(
                f"[catalog] 알 수 없는 세트: {content_row.prescription_set_name!r} — 건너뛴다",
                file=sys.stderr,
            )
            continue

        approved_key = (
            f"{ps.prescription_set_id}:{content_row.section_key.value}"
            if content_row.approval_status == ApprovalStatus.APPROVED
            else None
        )

        # (세트, 섹션, 버전) 단위로 중복 방지 — content_version 이 같으면 건너뛴다
        exists = await DrugCautionContent.filter(
            prescription_set=ps,
            section_key=content_row.section_key,
            content_version=content_row.content_version,
        ).exists()
        if exists:
            skipped_contents += 1
            continue

        await DrugCautionContent.create(
            prescription_set=ps,
            section_key=content_row.section_key,
            body=content_row.body,
            source_name=content_row.source_name,
            source_org=content_row.source_org,
            source_url=content_row.source_url,
            verified_at=content_row.verified_at,
            content_version=content_row.content_version,
            source_grade=content_row.source_grade,
            approval_status=content_row.approval_status,
            approved_key=approved_key,
        )
        created_contents += 1

    print(f"[catalog] drug_caution_content created={created_contents} skipped={skipped_contents}")


async def main(mode: str) -> None:
    _guard_environment()
    await Tortoise.init(config=TORTOISE_ORM)

    match mode:
        case "empty":
            print("[seed] 빈 상태 — 아무것도 적재하지 않습니다.")
        case "staff":
            password = _require_password()
            await seed_staff(password)
            await seed_catalog()
        case "full":
            password = _require_password()
            hospitals = await seed_staff(password)
            await seed_catalog()
            await seed_patients(hospitals)
        case _:
            print(f"알 수 없는 mode: {mode}", file=sys.stderr)
            await Tortoise.close_connections()
            sys.exit(1)

    await Tortoise.close_connections()
    print("[seed] 완료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="합성 데이터 seed — KEY-29",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  SEED_STAFF_PASSWORD=devpass uv run python scripts/seed.py --mode=staff\n"
            "  SEED_STAFF_PASSWORD=devpass uv run python scripts/seed.py --mode=full\n"
            "  uv run python scripts/seed.py --mode=empty"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["empty", "staff", "full"],
        default="staff",
        help="empty=적재 없음 | staff=직원만(기본값) | full=전체",
    )
    args = parser.parse_args()
    asyncio.run(main(args.mode))
