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
from tortoise.timezone import now  # noqa: E402

from app.core.config import Config  # noqa: E402
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.core.utils.common import normalize_phone_number  # noqa: E402
from app.core.utils.security import hash_password  # noqa: E402
from app.models.catalog import ApprovalStatus, CautionSectionKey, DrugCautionContent, PrescriptionSet  # noqa: E402
from app.models.patients import Patient  # noqa: E402
from app.models.prescriptions import Prescription, PrescriptionItem  # noqa: E402
from app.models.staffs import Hospital, Staff, StaffStatus  # noqa: E402
from app.models.visits import (  # noqa: E402
    CheckIn,
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    PatientGuideLink,
    Visit,
    VisitStatus,
)
from app.services.drug_caution import DrugCautionService  # noqa: E402
from app.services.guides import GuideService  # noqa: E402
from app.services.patient_links import LINK_TTL, digest_link_token  # noqa: E402
from app.tests.fixtures.catalog import DRUG_CAUTION_CONTENTS, PRESCRIPTION_SETS  # noqa: E402
from app.tests.fixtures.prescriptions import PrescriptionRowError, items_from_row  # noqa: E402
from app.tests.fixtures.staff import (  # noqa: E402
    StaffDataError,
    all_staff,
    read_staff_csv_for_seed_override,
)
from app.tests.fixtures.validation import (  # noqa: E402
    read_patient_rows,
    validate_patient_rows,
)

_CONFIG = Config()

SEED_PASSWORD_ENV = "SEED_STAFF_PASSWORD"

#: **`Config` 를 거치지 않는다** — 가드레일 ①. `Config` 는 `extra="allow"` 라
#: `.env` 에 적어 둔 아무 이름이나 **소문자로** 빨아들인다 (`c.seed_allow_prod`
#: · `c.model_extra["seed_allow_prod"]` · `c.model_dump()["seed_allow_prod"]`
#: 셋 다 값이 나온다 — 실측). 그리고 `scripts/deployment.sh:133` 이
#: `envs/.prod.env` 를 그대로 `~/project/.env` 로 올린다. 즉 한 번 파일에
#: 적히면 **배포될 때마다 따라 올라가** 서버에 영구히 켜져 있게 된다.
#: `os.environ` 만 보면 그 길이 막힌다 — 명령줄에 그때그때 적어야만 켜진다.
SEED_ALLOW_PROD_ENV = "SEED_ALLOW_PROD"

#: 정확히 이 둘만 켠다. `yes` · `Y` · `2` · `true ` 는 안 켜진다 — 「대충 참으로
#: 보이는 값」을 받아 주면 오타가 운영 DB 를 여는 열쇠가 된다.
SEED_ALLOW_PROD_TRUE = frozenset({"1", "true"})

#: **조작자가 값을 준다 — 시드가 만들지 않는다.**
#:
#: 환자 링크 토큰은 DB 에 sha256 만 남고 원문은 발급 응답 한 번뿐이다
#: (`app/services/patient_links.py`). 시드가 원문을 만들어 찍으면 그 순간
#: **로그에 환자 링크 토큰이 남는다** — `AGENTS.md` 가 금지한 자리다.
#: 그래서 값을 밖에서 받고, 저장은 해시만 한다. smoke 를 돌리는 사람은 이미 그
#: 값을 알고 있으므로(`PATIENT_SMOKE_LINK_TOKEN` 에 같은 값을 넣는다) 잃는 것이 없다.
SMOKE_LINK_TOKEN_ENV = "SEED_SMOKE_LINK_TOKEN"

#: KEY-176 smoke 전용 진료. **시연이 쓰는 `SYN-EMS-01` 과 일부러 다르다** —
#: smoke 는 제출로 fixture 를 소진하므로, 같은 건을 쓰면 시연 시나리오가 오염된다.
#:
#: 이 행을 고른 이유는 CSV 가 이미 그렇게 적어 두었기 때문이다.
#:
#:     진료상태   발송 완료      승인까지 끝난 안내라는 뜻
#:     확인문자회차 D+7 · D+15   D+7 이 이미 나갔다
#:     열람여부   미열람        아직 아무것도 제출하지 않았다
#:     이탈표시   (없음)
#:
#: 처방세트(`자궁내막증 · 비잔 (계속)`)에 승인된 caution·emergency 문구가 둘 다
#: 있어서 안내가 폴백 없이 선다.
SMOKE_SCENARIO_ID = "SYN-BULK-020"
SMOKE_CHART_NO = "08424"

#: **승인 카탈로그 밖 문구는 `guides.generate` 가 쓰는 말만 쓴다.**
#: 새 의학 문장을 지어내지 않는다.
#:
#: 한 줄은 뺐다 — `generate` 의 MEDICATION 본문에는
#:
#:     [합성 복약 안내]
#:     확정된 항목: {field_label}          ← 이 줄
#:     복약 지시에 따라 정해진 시간에 복용해 주세요.
#:
#: 가운데 줄이 더 있는데, 그 값은 **확정된 `OcrField`** 에서 온다
#: (`guides.py` 의 `field_label`). 이 fixture 는 판독을 거치지 않고 안내문을
#: 바로 세우므로 확정된 항목이 없다 — 채울 값이 없는데 줄만 넣으면 빈
#: 「확정된 항목: 」이 환자 화면에 나간다. 그래서 **뺐다.**
#:
#: 앞서 이 주석은 「그대로 옮긴 것」이라고 적혀 있었는데 사실이 아니었다
#: (이희진 님 `#158` ⑤). 지어낸 말은 없지만, 같지도 않았다.
_SMOKE_MEDICATION_BODY = "[합성 복약 안내]\n복약 지시에 따라 정해진 시간에 복용해 주세요."
_SMOKE_LIFE_BODY = "처방 기간 중 음주는 피해 주세요. 충분한 수분 섭취와 규칙적인 수면을 유지해 주세요."
_SMOKE_MESSAGES_BODY = "복약 안내가 발송될 예정입니다. 궁금한 점은 진료실로 문의해 주세요."

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


def _prod_override_granted() -> bool:
    """**`os.environ` 만 본다.** `Config`·`.env` 는 쳐다보지 않는다 (가드레일 ①).

    값은 정확히 `1` 또는 `true` 여야 한다. 앞뒤 공백은 털고 대소문자는 안 가리지만,
    그 밖의 무엇도 참으로 치지 않는다.
    """
    raw = os.environ.get(SEED_ALLOW_PROD_ENV)
    return raw is not None and raw.strip().lower() in SEED_ALLOW_PROD_TRUE


def _guard_environment() -> None:
    """운영 환경에서는 막는다 — 다만 **명령줄로 한 번 열 수 있다**.

    Pilot 은 「운영처럼 뜨지만 합성 데이터로 도는 환경」이라 이 가드와 정면으로
    부딪힌다 (KEY-192). 가드를 없애는 대신 **좁은 문 하나**를 낸 것이 KEY-200 이다.
    문이 좁아야 하는 이유는 이 스크립트가 하는 일이 `Staff` · `Patient` · `Visit`
    을 실제로 만드는 것이기 때문이다 — 진짜 운영 DB 에서 돌면 합성 환자가 섞인다.

    좁게 만드는 장치가 셋이다.

        os.environ 만 본다      `.env` 에 적어 두면 안 켜진다. `deployment.sh` 가
                                그 파일을 서버로 나르므로, 파일로 켜지면 영구히 켜진다
        값을 1·true 로 못박음    오타가 열쇠가 되지 않는다
        stderr 로 크게 알림      로그를 보는 사람이 「지금 prod 에 붓고 있다」를 안다
    """
    if str(_CONFIG.ENV).lower() != "prod":
        return

    if not _prod_override_granted():
        print(
            "오류: 운영 환경(ENV=prod)에서는 seed 를 실행할 수 없습니다.\n"
            f"  Pilot/합성 환경이라면 {SEED_ALLOW_PROD_ENV}=1 을 **명령줄에** 붙여 주세요.\n"
            f"  .env 파일에 적으면 켜지지 않습니다 — 배포 때마다 따라 올라가기 때문입니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"⚠ ENV=prod 시딩 허용됨 ({SEED_ALLOW_PROD_ENV}) — Pilot/합성 전용",
        file=sys.stderr,
    )


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
        # **문이 열려 있을 때만 가드를 건너뛴다** — 이희진 님 `#158` B안.
        #
        # `all_staff()` 는 `_refuse_in_production()` 을 거치는데, 그것은 이
        # 스크립트 전용이 아니라 **합성 계정을 부르는 모든 자리**에 걸리는
        # 범용 안전핀이다. 거기에 조건을 넣으면 「운영에서 절대 안 읽는다」가
        # 조건부로 바뀌므로, 그 함수는 한 글자도 안 건드리고 여기서 갈랐다.
        #
        # 순서가 중요하다 — `_guard_environment()` 가 `main()` 첫 줄에서
        # `SEED_ALLOW_PROD` 를 이미 확인했다. 그 확인 없이 아래 함수를 부르면
        # 운영에서 아무 문턱 없이 합성 계정을 읽게 된다.
        staff_rows = read_staff_csv_for_seed_override() if _prod_override_granted() else all_staff()
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
    # **여기서도 좁은 문으로 간다** — `validate_canonical_patient_data()` 는
    # 안에서 `all_staff()` 를 부르고, 그것은 운영에서 멈춘다. 검증 함수는
    # 이미 `staff=` 를 받게 되어 있으므로 **그 함수도 안 건드리고** 읽어 둔
    # 것을 넘긴다.
    validate_patient_rows(
        read_patient_rows(),
        staff=read_staff_csv_for_seed_override() if _prod_override_granted() else all_staff(),
    )

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


async def seed_smoke_fixture(hospitals: dict[str, Hospital]) -> None:
    """KEY-176 smoke 가 쓸 **승인 완료 안내 1건 + 미제출 D+7 상태**를 만든다.

    두 건이 아니라 **한 진료 건의 두 성질**이다. smoke 스크립트가 받는 식별자가
    `PATIENT_SMOKE_LINK_TOKEN` 하나와 `PATIENT_SMOKE_VISIT_ID` 하나뿐이고,
    ⑤ 가 그 토큰 뒤의 안내에 `CheckIn` 을 만들면 ⑦ 이 `visit_id` 로 되찾는다
    (`app/services/checkins.py`). 두 진료로 나누면 ⑦ 이 404 다.

    ## 의학 문구를 지어내지 않는다

    caution·emergency 는 `DrugCautionService.get_approved_content` 로 **이미
    승인된 카탈로그 문구**를 그대로 가져온다 — `app/services/guides.py` 의
    `generate` 가 하는 것과 같은 길이다. 「확정 승인 지식 외 내용 추가 금지」
    (이희진 님, PR #150)를 코드로 지키는 자리다. 승인 문구가 없는 세트를 고르면
    폴백으로 서기 때문에, 세트에 둘 다 있는 행을 골라 두었다.

    ## 다시 돌릴 수 있다

    smoke 는 ⑤ 에서 제출하며 fixture 를 **소진한다** — `CheckIn` 은 안내문당
    하나뿐이라(OneToOne) 두 번째 제출은 409 다. 그래서 이 함수는 매번
    **그 `CheckIn` 을 지우고** 링크 만료도 다시 72 시간으로 민다. 지우는 대상은
    이 fixture 안내문 하나뿐이다.
    """
    raw_token = os.environ.get(SMOKE_LINK_TOKEN_ENV)
    if not raw_token:
        print(
            f"[smoke] {SMOKE_LINK_TOKEN_ENV} 가 없어 건너뜁니다.\n"
            f"  KEY-176 smoke 를 돌리려면 링크 토큰을 직접 정해 넘겨 주세요 —\n"
            f"  시드는 토큰을 만들지 않습니다(만들면 로그에 남습니다).",
            file=sys.stderr,
        )
        return

    h1 = hospitals["H1"]
    patient = await Patient.filter(hospital_id=h1.hospital_id, hospital_patient_no=SMOKE_CHART_NO).first()
    if patient is None:
        print(f"[smoke] 차트 {SMOKE_CHART_NO} 환자가 없습니다 — --mode full 로 먼저 적재하세요.", file=sys.stderr)
        return

    visit = await Visit.filter(hospital_id=h1.hospital_id, patient=patient).order_by("-visited_at").first()
    if visit is None:
        print(f"[smoke] 차트 {SMOKE_CHART_NO} 의 진료가 없습니다.", file=sys.stderr)
        return

    doctor_id = visit.doctor_id
    prescription = await Prescription.filter(visit_id=visit.visit_id).first()
    set_name = prescription.prescription_set if prescription else None

    caution = await DrugCautionService.get_approved_content(set_name, CautionSectionKey.CAUTION)
    emergency = await DrugCautionService.get_approved_content(set_name, CautionSectionKey.EMERGENCY)
    if caution is None or emergency is None:
        print(
            f"[smoke] 처방세트 {set_name!r} 에 승인된 주의·응급 문구가 없습니다 — "
            "폴백 문구로 서게 되므로 멈춥니다. 세트를 바꾸거나 카탈로그를 먼저 적재하세요.",
            file=sys.stderr,
        )
        return

    # **승인자가 없으면 만들지 않는다** — 이희진 님 `#158` ②.
    #
    # 예전에는 `doctor_id` 가 `None` 이어도 `approved_by=None` · `issued_by=0` 으로
    # 조용히 지나갔다. CSV 담당의 칸이 비면 **승인한 사람 없이 「승인·발급」된
    # 안내문**이 생긴다. 바로 위 승인 문구 검사는 명시적으로 멈추는데 이 자리만
    # 안 멈추던 것이라 같은 모양으로 맞춘다.
    if doctor_id is None:
        print(
            f"[smoke] 진료 {visit.visit_id} 에 담당의가 없습니다 — 승인자 없이 승인 상태를 "
            "만들 수 없어 멈춥니다. CSV 의 담당의 칸을 확인해 주세요.",
            file=sys.stderr,
        )
        return

    # **실제 승인이 채우는 것을 빠짐없이 맞춘다** — 이희진 님 `#158` ①③.
    #
    # `GuideService.approve()` 는 한 트랜잭션에서 다섯을 함께 쓰고 감사로그를
    # 남긴다. 앞서는 `status`·`approved_by`·`approved_at` 셋만 써서, **실제
    # 승인 흐름으로는 나올 수 없는 상태**(승인됐는데 예약시각도 감사로그도 없음)
    # 를 만들고 있었다. `docs/api/hospital.md` 가 「승인은 `scheduled_at` 을
    # 채우는 데까지다」라고 적어 두었고 `test_guide_approval.py` 가 그것을
    # 이미 단언한다.
    #
    # `returned_reason` 도 지운다(③) — 반려 이력이 있는 진료를 다시 시드하면
    # 「승인됨인데 반려 사유가 화면에 남는」 상태가 된다.
    approved_moment = now()
    approved_fields = {
        # **승인 완료 = SCHEDULED_TO_SEND.** `APPROVED` 라는 상태는 없다 —
        # 승인이 곧 발송 예약이다(`GuideStatus` docstring).
        "status": GuideStatus.SCHEDULED_TO_SEND,
        "approved_by": doctor_id,
        "approved_at": approved_moment,
        "scheduled_at": GuideService.send_at(approved_moment),
        "returned_reason": None,
    }

    guide, guide_created = await GuideDocument.get_or_create(
        visit_id=visit.visit_id,
        defaults={"hospital_id": h1.hospital_id, **approved_fields},
    )
    if not guide_created:
        await GuideDocument.filter(guide_document_id=guide.guide_document_id).update(
            **{**approved_fields, "approved_at": guide.approved_at or approved_moment},
        )
        guide = await GuideDocument.get(guide_document_id=guide.guide_document_id)

    # 감사로그 — 누가 언제 승인했는지가 남아야 한다. 다시 시드해도 하나만 둔다.
    if not await GuideEvent.filter(
        guide_document_id=guide.guide_document_id,
        event_type=GuideEventType.APPROVED,
    ).exists():
        await GuideEvent.create(
            guide_document=guide,
            event_type=GuideEventType.APPROVED,
            actor_id=doctor_id,
        )

    sections: tuple[tuple[GuideSectionKey, str, int | None, bool], ...] = (
        (GuideSectionKey.MEDICATION, _SMOKE_MEDICATION_BODY, None, False),
        (GuideSectionKey.CAUTION, caution.body, caution.drug_caution_content_id, False),
        # 🚨 응급 문장은 사람이 못 고친다 (KEY-150, KEY-165).
        (GuideSectionKey.EMERGENCY, emergency.body, emergency.drug_caution_content_id, True),
        (GuideSectionKey.LIFE, _SMOKE_LIFE_BODY, None, False),
        (GuideSectionKey.MESSAGES, _SMOKE_MESSAGES_BODY, None, False),
    )
    for key, body, content_id, locked in sections:
        await GuideSection.get_or_create(
            guide_document=guide,
            section_key=key,
            defaults={"generated_body": body, "drug_caution_content_id": content_id, "locked": locked},
        )

    digest = digest_link_token(raw_token)
    link = await PatientGuideLink.filter(guide_document_id=guide.guide_document_id).first()
    if link is None:
        await PatientGuideLink.create(
            guide_document=guide,
            token_digest=digest,
            expires_at=now() + LINK_TTL,
            issued_by=doctor_id,  # 위에서 None 을 이미 막았다 — 0 으로 메우지 않는다
        )
    else:
        # 다시 돌릴 때 **만료를 되민다** — TTL 이 72 시간이라 이틀 뒤 QA 에서 410 이 난다.
        await PatientGuideLink.filter(patient_guide_link_id=link.patient_guide_link_id).update(
            token_digest=digest,
            expires_at=now() + LINK_TTL,
        )

    # **미제출로 되돌린다.** smoke 가 제출하면 `CheckIn` 이 생기고 두 번째 제출은
    # 409 다 — 이 한 줄이 「재시드 가능」의 전부다.
    cleared = await CheckIn.filter(guide_document_id=guide.guide_document_id).delete()

    print(
        f"[smoke] 시나리오={SMOKE_SCENARIO_ID} 차트={SMOKE_CHART_NO} "
        f"visit_id={visit.visit_id} 안내문={guide.guide_document_id} "
        f"제출초기화={cleared} 처방세트={set_name}"
    )
    print(f"[smoke] PATIENT_SMOKE_VISIT_ID={visit.visit_id} 로 쓰세요 (토큰은 넣어 주신 값 그대로).")


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
            # KEY-176 smoke fixture 는 **환자·진료·카탈로그가 다 있어야** 선다.
            # 토큰을 안 넘기면 조용히 건너뛴다 — smoke 를 안 돌리는 사람에게
            # 없던 요구를 만들지 않는다.
            await seed_smoke_fixture(hospitals)
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
        default=None,
        help="empty=적재 없음 | staff=직원만(로컬 기본값) | full=전체",
    )
    args = parser.parse_args()

    # **운영에서는 `--mode` 를 손으로 적게 한다** — 가드레일 ②.
    #
    # 예전에는 `default="staff"` 라 인자를 안 주면 조용히 `staff` 가 돌았다.
    # 로컬에서는 편한 기본값이지만, `SEED_ALLOW_PROD` 로 문을 연 자리에서는
    # 「무엇을 부을지」를 사람이 한 번 더 적어야 한다. 안 적으면 무엇이 들어갔는지
    # 나중에 아무도 모른다.
    mode = args.mode
    if mode is None:
        if str(_CONFIG.ENV).lower() == "prod":
            print(
                "오류: 운영 환경(ENV=prod)에서는 --mode 를 명시해야 합니다.\n"
                "  --mode empty | --mode staff | --mode full",
                file=sys.stderr,
            )
            sys.exit(1)
        mode = "staff"

    asyncio.run(main(mode))
