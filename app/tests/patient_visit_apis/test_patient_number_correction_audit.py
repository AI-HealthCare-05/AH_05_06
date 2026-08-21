"""환자번호 정정이 **왜 고쳤는지까지** 남기는지 — KEY-121.

계약 §6 은 `hospital_patient_no` 와 `correction_reason` 을 짝으로 강제한다.
그런데 그 사유가 어디에도 저장되지 않고 `200` 이 나갔다(`#39` 리뷰). 직원은
사유를 적었고 성공했으니 기록된 줄 안다 — 의무기록 정정이라 이 간극이 특히 나쁘다.

여기서 확인하는 것은 넷이다.

    ① 성공하면 변경 전후·사유·수행자·시각이 **한 건** 남는다
    ② 실패한 정정은 감사 기록을 남기지 않는다 (권한·진료 존재·중복·타 병원)
    ③ 감사 저장이 실패하면 **번호도 안 바뀐다** — 한 트랜잭션이다
    ④ 번호를 안 건드리는 수정은 감사 기록을 만들지 않는다
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.dependencies.patient_access import ClinicalActor, get_clinical_actor
from app.main import app
from app.models.patients import Patient, PatientNumberCorrection
from app.models.visits import Visit

BASE_URL = "http://test"
HOSPITAL = 1
OTHER_HOSPITAL = 2

#: 번호를 고칠 수 있는 사람. 계약 §6 이 `admin` 으로 정해 두었다.
ADMIN = ClinicalActor(staff_id=101, hospital_id=HOSPITAL, roles=frozenset({"admin", "staff"}))
#: 못 고치는 사람. 스탭 권한만으로는 의무기록 정정을 못 한다.
STAFF = ClinicalActor(staff_id=102, hospital_id=HOSPITAL, roles=frozenset({"staff"}))

PAYLOAD = {
    "hospital_patient_no": "SYN-40001",
    "name": "합성정정대상",
    "birth_date": "1991-02-03",
    "gender": "FEMALE",
    "phone": "010-0000-4001",
    "sms_consent": True,
}
REASON = "접수 창구에서 차트번호를 잘못 입력해 정정합니다."


@asynccontextmanager
async def client_for(actor: ClinicalActor) -> AsyncIterator[AsyncClient]:
    async def override_actor() -> ClinicalActor:
        return actor

    app.dependency_overrides[get_clinical_actor] = override_actor
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_clinical_actor, None)


async def _make_patient(**overrides: Any) -> Patient:
    values: dict[str, Any] = {
        "hospital_id": HOSPITAL,
        "hospital_patient_no": PAYLOAD["hospital_patient_no"],
        "name": PAYLOAD["name"],
        "birth_date": PAYLOAD["birth_date"],
        "gender": PAYLOAD["gender"],
        "phone": "01000004001",
        "sms_consent": True,
    }
    values.update(overrides)
    return await Patient.create(**values)


class TestCorrectionLeavesAnAuditTrail(TestCase):
    async def test_success_records_before_after_reason_actor_and_time(self) -> None:
        """성공한 정정 하나가 감사 기록 **한 건**을 남긴다."""
        patient = await _make_patient()

        async with client_for(ADMIN) as client:
            response = await client.patch(
                f"/api/v1/patients/{patient.patient_id}",
                json={"hospital_patient_no": "SYN-40002", "correction_reason": REASON},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["hospital_patient_no"] == "SYN-40002"

        rows = await PatientNumberCorrection.filter(patient_id=patient.patient_id)
        assert len(rows) == 1, "정정 한 번에 감사 기록은 정확히 한 건이어야 한다"
        row = rows[0]
        assert row.before_no == "SYN-40001"  # 바뀌기 전 값을 붙잡았는가
        assert row.after_no == "SYN-40002"
        assert row.reason == REASON  # 직원이 적은 문장 그대로
        assert row.corrected_by == ADMIN.staff_id
        assert row.hospital_id == HOSPITAL
        assert row.created_at is not None

    async def test_the_stored_number_actually_changed(self) -> None:
        """응답에만 실리고 저장이 안 되는 경우를 가른다."""
        patient = await _make_patient(hospital_patient_no="SYN-40010")

        async with client_for(ADMIN) as client:
            await client.patch(
                f"/api/v1/patients/{patient.patient_id}",
                json={"hospital_patient_no": "SYN-40011", "correction_reason": REASON},
            )

        stored = await Patient.get(patient_id=patient.patient_id)
        assert stored.hospital_patient_no == "SYN-40011"

    async def test_two_corrections_leave_two_rows_in_order(self) -> None:
        """이력이다 — 덮어쓰지 않고 쌓인다."""
        patient = await _make_patient(hospital_patient_no="SYN-40020")

        async with client_for(ADMIN) as client:
            for after in ("SYN-40021", "SYN-40022"):
                await client.patch(
                    f"/api/v1/patients/{patient.patient_id}",
                    json={"hospital_patient_no": after, "correction_reason": REASON},
                )

        rows = await PatientNumberCorrection.filter(patient_id=patient.patient_id).order_by("correction_id")
        assert [(r.before_no, r.after_no) for r in rows] == [
            ("SYN-40020", "SYN-40021"),
            ("SYN-40021", "SYN-40022"),
        ]


class TestFailedCorrectionsLeaveNothing(TestCase):
    """실패한 정정이 감사 기록을 남기면 「했다」는 거짓 근거가 생긴다."""

    async def test_forbidden_actor_leaves_no_row(self) -> None:
        patient = await _make_patient(hospital_patient_no="SYN-41001")

        async with client_for(STAFF) as client:
            response = await client.patch(
                f"/api/v1/patients/{patient.patient_id}",
                json={"hospital_patient_no": "SYN-41002", "correction_reason": REASON},
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert await PatientNumberCorrection.filter(patient_id=patient.patient_id).count() == 0
        stored = await Patient.get(patient_id=patient.patient_id)
        assert stored.hospital_patient_no == "SYN-41001"

    async def test_patient_with_visits_leaves_no_row(self) -> None:
        patient = await _make_patient(hospital_patient_no="SYN-41010")
        await Visit.create(
            patient_id=patient.patient_id,
            hospital_id=HOSPITAL,
            visited_at="2026-08-20T10:30:00+09:00",
        )

        async with client_for(ADMIN) as client:
            response = await client.patch(
                f"/api/v1/patients/{patient.patient_id}",
                json={"hospital_patient_no": "SYN-41011", "correction_reason": REASON},
            )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "PATIENT_NUMBER_LOCKED"
        assert await PatientNumberCorrection.filter(patient_id=patient.patient_id).count() == 0

    async def test_duplicate_number_leaves_no_row(self) -> None:
        patient = await _make_patient(hospital_patient_no="SYN-41020")
        await _make_patient(hospital_patient_no="SYN-41021", phone="01000004002")

        async with client_for(ADMIN) as client:
            response = await client.patch(
                f"/api/v1/patients/{patient.patient_id}",
                json={"hospital_patient_no": "SYN-41021", "correction_reason": REASON},
            )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert await PatientNumberCorrection.filter(patient_id=patient.patient_id).count() == 0
        stored = await Patient.get(patient_id=patient.patient_id)
        assert stored.hospital_patient_no == "SYN-41020"

    async def test_other_hospital_patient_leaves_no_row(self) -> None:
        stranger = await _make_patient(hospital_id=OTHER_HOSPITAL, hospital_patient_no="SYN-41030", phone="01000004003")

        async with client_for(ADMIN) as client:
            response = await client.patch(
                f"/api/v1/patients/{stranger.patient_id}",
                json={"hospital_patient_no": "SYN-41031", "correction_reason": REASON},
            )

        # 남의 의원 것은 없는 것과 같게 답한다 — 잠금 여부로 존재가 새면 안 된다.
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert await PatientNumberCorrection.filter(patient_id=stranger.patient_id).count() == 0

    async def test_reason_without_number_is_rejected_before_anything_happens(self) -> None:
        """사유만 보내는 것도 계약 위반이다 — 짝이어야 한다.

        `422` 가 아니라 `400 INVALID_REQUEST` 다. `ContractRoute` 가
        `RequestValidationError` 를 계약 §7 의 고정 봉투로 바꾼다 —
        화면이 오류 모양을 하나만 알면 되게 하려는 것이다.
        """
        patient = await _make_patient(hospital_patient_no="SYN-41040")

        async with client_for(ADMIN) as client:
            response = await client.patch(
                f"/api/v1/patients/{patient.patient_id}",
                json={"correction_reason": REASON},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "INVALID_REQUEST"
        assert await PatientNumberCorrection.filter(patient_id=patient.patient_id).count() == 0


class TestAtomicity(TestCase):
    async def test_number_does_not_change_when_the_audit_write_fails(self) -> None:
        """감사 기록이 실패하면 **번호도 되돌아간다.**

        이것이 갈라져 있으면 「번호는 바뀌었는데 왜 바꿨는지는 없는」 행이
        생긴다. 나중에 메울 수 없는 간극이다.
        """
        patient = await _make_patient(hospital_patient_no="SYN-42001")

        async def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("감사 기록 저장이 실패했다고 치자")

        with patch.object(PatientNumberCorrection, "create", side_effect=boom):
            async with client_for(ADMIN) as client:
                try:
                    await client.patch(
                        f"/api/v1/patients/{patient.patient_id}",
                        json={"hospital_patient_no": "SYN-42002", "correction_reason": REASON},
                    )
                except RuntimeError:
                    pass  # 봉투 없이 그대로 올라오는 것은 이 검사의 관심사가 아니다

        stored = await Patient.get(patient_id=patient.patient_id)
        assert stored.hospital_patient_no == "SYN-42001", "감사 기록이 실패하면 번호도 안 바뀌어야 한다"
        assert await PatientNumberCorrection.filter(patient_id=patient.patient_id).count() == 0


class TestUnrelatedUpdatesStayQuiet(TestCase):
    async def test_changing_only_the_name_records_nothing(self) -> None:
        """번호를 안 건드리면 감사 기록도 없다 — 잠금이 과하게 걸리지 않는 것."""
        patient = await _make_patient(hospital_patient_no="SYN-43001")

        async with client_for(ADMIN) as client:
            response = await client.patch(
                f"/api/v1/patients/{patient.patient_id}",
                json={"name": "합성이름수정"},
            )

        assert response.status_code == status.HTTP_200_OK
        assert await PatientNumberCorrection.filter(patient_id=patient.patient_id).count() == 0


class TestTheRecordIsAppendOnly(TestCase):
    async def test_no_api_route_can_reach_the_audit_table(self) -> None:
        """감사 이벤트를 고치거나 지우는 경로가 **없다.**

        이 검사는 화면이 아니라 라우터 표를 본다. 나중에 누가 편의로 정정
        이력 수정 경로를 열면 여기서 죽는다 — append-only 가 규칙이라는 것을
        코드에 박아 두는 자리다.
        """
        reachable = [
            f"{method} {path}"
            for route in app.routes
            # `app.routes` 는 `BaseRoute` 라 `path` 가 타입에 없다. 실제로는
            # `APIRoute` 에 있으므로 `getattr` 로 읽는다.
            for path in [getattr(route, "path", "")]
            for method in getattr(route, "methods", set())
            if "correction" in path and method in {"PATCH", "PUT", "DELETE"}
        ]
        assert reachable == [], f"감사 기록을 고칠 수 있는 경로가 생겼다: {reachable}"
