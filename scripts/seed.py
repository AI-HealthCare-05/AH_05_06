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

건너뛰는 항목 (미구현 모델):
    - lab_result, visit_flag 테이블 — KEY-1, KEY-2 이후 활성화
    - DERIVED·EVENT·OCR_INPUT·DOC_ONLY 칸 (mapping.py 참조)
"""

import argparse
import asyncio
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAFF_CSV = ROOT / "docs" / "data" / "synthetic-staff.csv"
PATIENTS_CSV = ROOT / "docs" / "data" / "synthetic-patients.csv"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tortoise import Tortoise  # noqa: E402

from app.core.config import Config  # noqa: E402
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.core.utils.security import hash_password  # noqa: E402
from app.models.patients import Patient  # noqa: E402
from app.models.staffs import Hospital, Staff, StaffStatus  # noqa: E402
from app.models.visits import Visit, VisitStatus  # noqa: E402
from app.tests.fixtures.staff import StaffDataError, all_staff  # noqa: E402
from app.tests.fixtures.validation import validate_canonical_patient_data  # noqa: E402

_CONFIG = Config()

SEED_PASSWORD_ENV = "SEED_STAFF_PASSWORD"

# CSV 의 H1/H2 레이블 → seed 전용 병원 이름
_HOSPITAL_NAMES: dict[str, str] = {
    "H1": "기준의원",
    "H2": "격리의원",
}


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

    건너뜀:
        lab_result, visit_flag 모델 미구현 → KEY-1, KEY-2 이후 활성화
    """
    _require_csv(
        PATIENTS_CSV,
        hint="저장소를 최신화하세요.",
    )
    validate_canonical_patient_data()

    h1 = hospitals["H1"]

    # H1 소속 직원 이름 → staff_id 매핑
    h1_staff = await Staff.filter(hospital_id=h1.hospital_id).all()
    doctor_map: dict[str, int] = {s.name: s.staff_id for s in h1_staff if "doctor" in (s.roles or [])}

    with PATIENTS_CSV.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # 1단계: 환자 upsert
    # 동일 차트번호가 여러 진료 행에 반복될 수 있으므로 첫 행만 처리한다.
    patient_map: dict[str, Patient] = {}
    created_p = updated_p = 0

    for row in rows:
        chart_no = row["차트번호"].strip()
        if chart_no in patient_map:
            continue

        sms_consent = row["문자수신동의"].strip() == "Y"
        patient, was_created = await Patient.get_or_create(
            hospital_id=h1.hospital_id,
            hospital_patient_no=chart_no,
            defaults={
                "name": row["이름"].strip(),
                "birth_date": row["생년월일"].strip(),
                "phone": row["휴대폰"].strip(),
                "sms_consent": sms_consent,
            },
        )
        patient_map[chart_no] = patient
        if was_created:
            created_p += 1
        else:
            await Patient.filter(
                hospital_id=h1.hospital_id,
                hospital_patient_no=chart_no,
            ).update(
                name=row["이름"].strip(),
                birth_date=row["생년월일"].strip(),
                phone=row["휴대폰"].strip(),
                sms_consent=sms_consent,
            )
            updated_p += 1

    print(f"[patients] created={created_p} updated={updated_p} total={len(patient_map)}")

    # 2단계: 진료 upsert
    created_v = skipped_v = error_v = 0

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
        if doctor_name and doctor_id is None:
            print(
                f"[visits] 경고: 담당의 {doctor_name!r} 를 H1 직원에서 찾을 수 없음 (시나리오 {row['시나리오ID']})",
                file=sys.stderr,
            )

        planned_stop = row["진료상태"].strip() == "계획된 중단"

        _, was_created = await Visit.get_or_create(
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

    print(f"[visits] created={created_v} skipped={skipped_v} error={error_v} total={len(rows)}")


async def main(mode: str) -> None:
    _guard_environment()
    await Tortoise.init(config=TORTOISE_ORM)

    match mode:
        case "empty":
            print("[seed] 빈 상태 — 아무것도 적재하지 않습니다.")
        case "staff":
            password = _require_password()
            await seed_staff(password)
        case "full":
            password = _require_password()
            hospitals = await seed_staff(password)
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
