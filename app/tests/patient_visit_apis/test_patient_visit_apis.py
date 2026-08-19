from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.dependencies.patient_access import ClinicalActor, get_clinical_actor
from app.main import app
from app.models.patients import Patient
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
    staff = ClinicalActor(user_id=101, hospital_id=1, roles=frozenset({"staff"}))

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
        admin = ClinicalActor(user_id=201, hospital_id=1, roles=frozenset({"admin"}))

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
