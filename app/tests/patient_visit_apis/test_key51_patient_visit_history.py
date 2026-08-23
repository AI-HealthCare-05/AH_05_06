from datetime import UTC, date, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.dependencies.patient_access import ClinicalActor, get_clinical_actor
from app.dtos.patients import PatientCategory
from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit
from app.services.patients import PatientService
from app.tests.work_category.test_load_signals import CountingQueries

BASE_URL = "http://test"
ACTOR = ClinicalActor(staff_id=7001, hospital_id=1, roles=frozenset({"staff"}))


async def create_patient(number: str, *, sms_consent: bool = True) -> Patient:
    return await Patient.create(
        hospital_id=1,
        hospital_patient_no=number,
        name=f"합성환자-{number}",
        birth_date=date(1994, 8, 24),
        phone="01039457702",
        sms_consent=sms_consent,
        sms_opted_out_at=None if sms_consent else datetime.now(UTC),
    )


class TestPatientListContract(TestCase):
    async def test_envelope_age_and_current_categories(self) -> None:
        active = await create_patient("SYN-KEY51-A")
        opted_out = await create_patient("SYN-KEY51-B", sms_consent=False)
        inactive = await create_patient("SYN-KEY51-C")
        await Visit.create(
            hospital_id=1,
            patient=active,
            visited_at=datetime.now(UTC),
        )
        await Visit.create(
            hospital_id=1,
            patient=inactive,
            visited_at=datetime.now(UTC) - timedelta(days=200),
        )

        async def actor_override() -> ClinicalActor:
            return ACTOR

        app.dependency_overrides[get_clinical_actor] = actor_override
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
                response = await client.get(
                    "/api/v1/patients",
                    params={"category": PatientCategory.SMS_OPT_OUT.value},
                )
        finally:
            app.dependency_overrides.pop(get_clinical_actor, None)

        body = response.json()
        assert response.status_code == 200
        assert body["selected_category"] == "SMS_OPT_OUT"
        assert body["counts"] == {
            "ALL": 3,
            "IN_TREATMENT": 0,
            "NEEDS_ATTENTION": 0,
            "SMS_OPT_OUT": 1,
            "INACTIVE_6_MONTHS": 1,
        }
        assert [item["patient_id"] for item in body["items"]] == [opted_out.patient_id]
        assert body["items"][0]["age"] >= 31
        assert "page" in body

    async def test_latest_visit_query_count_does_not_grow_at_limit_100(self) -> None:
        service = PatientService()
        few = [await create_patient(f"SYN-KEY51-N{i:03}") for i in range(2)]
        for patient in few:
            await Visit.create(hospital_id=1, patient=patient, visited_at=datetime.now(UTC))
        with CountingQueries() as small:
            await service.list(
                ACTOR,
                keyword=None,
                category=PatientCategory.ALL,
                cursor=None,
                limit=100,
            )

        many = [await create_patient(f"SYN-KEY51-M{i:03}") for i in range(98)]
        for patient in many:
            await Visit.create(hospital_id=1, patient=patient, visited_at=datetime.now(UTC))
        with CountingQueries() as large:
            rows, _, _, _ = await service.list(
                ACTOR,
                keyword=None,
                category=PatientCategory.ALL,
                cursor=None,
                limit=100,
            )

        assert len(rows) == 100
        assert large.count == small.count


class TestFrontDeskContract(TestCase):
    async def test_today_list_has_doctor_object_and_no_medical_source(self) -> None:
        hospital = await Hospital.create(name="KEY-51 합성병원")
        doctor = await Staff.create(
            hospital=hospital,
            login_id="key51-doctor",
            password_hash="synthetic-not-a-real-hash",
            name="합성의사",
            roles=["doctor"],
        )
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no="SYN-KEY51-FD",
            name="합성환자",
            birth_date=date(1990, 1, 1),
            phone="01039457702",
            sms_consent=True,
        )
        visit = await Visit.create(
            hospital_id=hospital.hospital_id,
            patient=patient,
            doctor_id=doctor.staff_id,
            visited_at=datetime(2026, 8, 23, 1, 30, tzinfo=UTC),
        )
        actor = ClinicalActor(
            staff_id=doctor.staff_id,
            hospital_id=hospital.hospital_id,
            roles=frozenset({"doctor"}),
        )

        async def actor_override() -> ClinicalActor:
            return actor

        app.dependency_overrides[get_clinical_actor] = actor_override
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
                today = await client.get("/api/v1/front-desk/visits", params={"date": "2026-08-23"})
                detail = await client.get(f"/api/v1/visits/{visit.visit_id}")
        finally:
            app.dependency_overrides.pop(get_clinical_actor, None)

        body = today.json()
        assert today.status_code == 200
        assert body["date"] == "2026-08-23"
        assert body["timezone"] == "Asia/Seoul"
        assert body["items"][0]["doctor"] == {"doctor_id": doctor.staff_id, "name": "합성의사"}
        assert body["items"][0]["detail_status"] == "NO_DOCUMENT"
        assert "raw_text" not in str(body)
        assert detail.json()["doctor"] == body["items"][0]["doctor"]
