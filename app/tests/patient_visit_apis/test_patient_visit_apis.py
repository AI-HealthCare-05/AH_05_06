from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.dependencies.patient_access import ClinicalActor, get_clinical_actor
from app.dependencies.staff_auth import get_current_staff
from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit

BASE_URL = "http://test"
PATIENT_PAYLOAD = {
    "hospital_patient_no": "SYN-12501",
    "name": "합성환자",
    "birth_date": "1994-07-22",
    "gender": "FEMALE",
    "phone": "010-3945-7702",
    "sms_consent": True,
}


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


class TestPatientVisitApis(TestCase):
    staff = ClinicalActor(staff_id=101, hospital_id=1, roles=frozenset({"staff"}))

    async def test_patient_routes_use_current_staff_authentication(self) -> None:
        hospital = await Hospital.create(name="합성테스트병원")
        authenticated_staff = await Staff.create(
            hospital=hospital,
            login_id="syn-key34-staff",
            password_hash="synthetic-not-a-real-password-hash",
            name="합성직원",
            roles=["staff"],
            must_change_password=False,
        )

        async def override_current_staff() -> Staff:
            return authenticated_staff

        app.dependency_overrides[get_current_staff] = override_current_staff
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
                response = await client.get("/api/v1/patients")
        finally:
            app.dependency_overrides.pop(get_current_staff, None)

        assert response.status_code == status.HTTP_200_OK

    async def test_patient_create_search_get_and_update_flow(self) -> None:
        async with client_for(self.staff) as client:
            created = await client.post("/api/v1/patients", json=PATIENT_PAYLOAD)
            patient_id = created.json()["patient_id"]

            searched = await client.get("/api/v1/patients", params={"keyword": "합"})
            fetched = await client.get(f"/api/v1/patients/{patient_id}")
            updated = await client.patch(
                f"/api/v1/patients/{patient_id}",
                json={"phone": "010-0000-0001", "sms_consent": False},
            )

        assert created.status_code == status.HTTP_201_CREATED
        assert created.json()["phone"] == "01039457702"
        assert searched.status_code == status.HTTP_200_OK
        assert [item["patient_id"] for item in searched.json()["items"]] == [patient_id]
        assert fetched.status_code == status.HTTP_200_OK
        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["phone"] == "01000000001"
        assert updated.json()["sms_consent"] is False
        assert updated.json()["sms_opted_out_at"] is not None

    async def test_duplicate_patient_number_returns_frozen_error(self) -> None:
        async with client_for(self.staff) as client:
            first = await client.post("/api/v1/patients", json=PATIENT_PAYLOAD)
            duplicate = await client.post("/api/v1/patients", json=PATIENT_PAYLOAD)

        assert first.status_code == status.HTTP_201_CREATED
        assert duplicate.status_code == status.HTTP_409_CONFLICT
        assert duplicate.json() == {
            "code": "DUPLICATE_HOSPITAL_PATIENT_NO",
            "message": "같은 병원에 이미 등록된 환자번호입니다.",
            "field_errors": None,
        }

    async def test_other_hospital_patient_is_hidden_as_not_found(self) -> None:
        patient = await Patient.create(
            hospital_id=2,
            hospital_patient_no="SYN-OTHER-1",
            name="다른병원합성환자",
            birth_date="1990-01-01",
            phone="01011112222",
            sms_consent=False,
        )

        async with client_for(self.staff) as client:
            response = await client.get(f"/api/v1/patients/{patient.patient_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "PATIENT_NOT_FOUND"

    async def test_other_hospital_visit_is_hidden_as_not_found(self) -> None:
        patient = await Patient.create(
            hospital_id=2,
            hospital_patient_no="SYN-OTHER-2",
            name="다른병원진료환자",
            birth_date="1990-01-01",
            phone="01022223333",
            sms_consent=False,
        )
        visit = await Visit.create(
            hospital_id=2,
            patient=patient,
            visited_at="2026-08-19T01:30:00+00:00",
        )

        async with client_for(self.staff) as client:
            response = await client.get(f"/api/v1/visits/{visit.visit_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "VISIT_NOT_FOUND"

    async def test_admin_only_actor_is_forbidden(self) -> None:
        admin = ClinicalActor(staff_id=201, hospital_id=1, roles=frozenset({"admin"}))

        async with client_for(admin) as client:
            response = await client.get("/api/v1/patients")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "FORBIDDEN"

    async def test_visit_create_list_get_update_and_duplicate_flow(self) -> None:
        async with client_for(self.staff) as client:
            patient = await client.post("/api/v1/patients", json=PATIENT_PAYLOAD)
            patient_id = patient.json()["patient_id"]
            visit_payload = {
                "visited_at": "2026-08-19T10:30:00+09:00",
                "visit_summary": "합성 진료 요약",
                "status": "COMPLETED",
                "planned_stop": False,
            }

            created = await client.post(f"/api/v1/patients/{patient_id}/visits", json=visit_payload)
            visit_id = created.json()["visit_id"]
            duplicate = await client.post(
                f"/api/v1/patients/{patient_id}/visits",
                json={**visit_payload, "visited_at": "2026-08-19T15:00:00+09:00"},
            )
            listed = await client.get(f"/api/v1/patients/{patient_id}/visits")
            fetched = await client.get(f"/api/v1/visits/{visit_id}")
            updated = await client.patch(
                f"/api/v1/visits/{visit_id}",
                json={"status": "CANCELED", "planned_stop": True},
            )

        assert created.status_code == status.HTTP_201_CREATED
        assert duplicate.status_code == status.HTTP_409_CONFLICT
        assert duplicate.json()["code"] == "VISIT_ALREADY_REGISTERED"
        assert listed.status_code == status.HTTP_200_OK
        assert [item["visit_id"] for item in listed.json()["items"]] == [visit_id]
        assert fetched.status_code == status.HTTP_200_OK
        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["status"] == "CANCELED"
        assert updated.json()["planned_stop"] is True

    async def test_phone_search_matches_however_the_number_was_typed(self) -> None:
        """차트에 적힌 대로 하이픈을 넣어 쳐도 찾혀야 한다.

        저장은 숫자만 남기므로(`01039457702`), 검색어를 정규화하지 않으면
        `010-3945-7702` 는 0건이다. 오류가 아니라 「결과 없음」이라 직원은
        미등록 환자로 알고 새로 등록하고, 그러면 차트번호 중복까지 이어진다.
        """
        async with client_for(self.staff) as client:
            created = await client.post("/api/v1/patients", json=PATIENT_PAYLOAD)
            patient_id = created.json()["patient_id"]

            typed = {}
            for label, keyword in {
                "하이픈": "010-3945-7702",
                "숫자만": "01039457702",
                "공백": "010 3945 7702",
                "국가번호": "+82 10-3945-7702",
                "뒷자리": "7702",
            }.items():
                found = await client.get("/api/v1/patients", params={"keyword": keyword})
                typed[label] = [item["patient_id"] for item in found.json()["items"]]

            # 이름 검색이 전화번호 갈래 때문에 넓어지지 않아야 한다
            by_name = await client.get("/api/v1/patients", params={"keyword": "합"})
            # 저장된 번호와 무관한 숫자는 여전히 0건이어야 한다 — 아무거나 찾히면 정규화가 아니라 붕괴다
            unrelated = await client.get("/api/v1/patients", params={"keyword": "010-0000-9999"})

        assert typed == {label: [patient_id] for label in typed}, typed
        assert [item["patient_id"] for item in by_name.json()["items"]] == [patient_id]
        assert unrelated.json()["items"] == []

    async def test_doctor_id_is_stored_while_department_id_stays_blocked(self) -> None:
        """계약 §6 「진료 생성」의 정본 예시가 400 이면 안 된다.

        `doctor_id` 를 저장하지 못하면 목록의 「담당」이 전부 비고, 의사가 자기
        환자만 보는 D1-1 이 성립하지 않는다. `department_id` 는 진료과 표가
        진짜로 없어서 계속 막히는 것이고, 둘은 사정이 다르다.
        """
        async with client_for(self.staff) as client:
            patient = await client.post("/api/v1/patients", json=PATIENT_PAYLOAD)
            patient_id = patient.json()["patient_id"]

            created = await client.post(
                f"/api/v1/patients/{patient_id}/visits",
                json={"doctor_id": 12, "visited_at": "2026-08-19T10:30:00+09:00"},
            )
            visit_id = created.json()["visit_id"]
            fetched = await client.get(f"/api/v1/visits/{visit_id}")
            reassigned = await client.patch(f"/api/v1/visits/{visit_id}", json={"doctor_id": 13})
            cleared = await client.patch(f"/api/v1/visits/{visit_id}", json={"doctor_id": None})

            # 진료과는 저장할 이름 자체가 없다 — 여기는 계속 막혀 있어야 한다
            with_department = await client.post(
                f"/api/v1/patients/{patient_id}/visits",
                json={"department_id": 7, "visited_at": "2026-08-20T10:30:00+09:00"},
            )
            patched_department = await client.patch(f"/api/v1/visits/{visit_id}", json={"department_id": 7})

        assert created.status_code == status.HTTP_201_CREATED
        assert created.json()["doctor_id"] == 12
        assert fetched.json()["doctor_id"] == 12  # 저장까지 갔는지 — 응답에만 실렸을 수 있다
        assert reassigned.json()["doctor_id"] == 13
        assert cleared.json()["doctor_id"] is None

        assert with_department.status_code == status.HTTP_400_BAD_REQUEST
        assert with_department.json()["code"] == "INVALID_DEPARTMENT"
        assert patched_department.status_code == status.HTTP_400_BAD_REQUEST
        assert patched_department.json()["code"] == "INVALID_DEPARTMENT"

    async def test_request_scope_fields_are_rejected(self) -> None:
        async with client_for(self.staff) as client:
            response = await client.post(
                "/api/v1/patients",
                json={**PATIENT_PAYLOAD, "hospital_id": 999},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "INVALID_REQUEST"

    async def test_missing_patient_blocks_visit_creation(self) -> None:
        async with client_for(self.staff) as client:
            response = await client.post(
                "/api/v1/patients/999999/visits",
                json={"visited_at": "2026-08-19T10:30:00+09:00"},
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "PATIENT_NOT_FOUND"
