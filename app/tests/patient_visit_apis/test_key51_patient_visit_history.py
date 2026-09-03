from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.dependencies.patient_access import ClinicalActor, get_clinical_actor
from app.dtos.patients import PatientCategory
from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit
from app.services.front_desk import FrontDeskService
from app.services.patients import PatientService
from app.services.visits import VisitService
from app.services.work_category import VisitSignals
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
        # 「진행 중」은 최근 진료가 완료가 아닌 환자다. 여기서는 둘 다 진료기록도
        # 안내문도 없어 「작성 중」에 머물러 있으므로 2 다 — S2-1 이 이 칩을
        # 요구하기 전에는 0 으로 굳어 있었다(KEY-234).
        assert body["counts"] == {
            "ALL": 3,
            "IN_TREATMENT": 2,
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

    async def test_page_only_loads_latest_visits_for_the_requested_rows(self) -> None:
        service = PatientService()
        for index in range(25):
            await create_patient(f"SYN-KEY51-P{index:03}")

        with patch.object(service.repo, "latest_visits", wraps=service.repo.latest_visits) as latest_visits:
            rows, counts, _, has_next = await service.list(
                ACTOR,
                keyword=None,
                category=PatientCategory.ALL,
                cursor=None,
                limit=20,
            )

        recorded_call = latest_visits.await_args
        assert recorded_call is not None
        requested_ids = recorded_call.args[0]
        assert len(rows) == 20
        assert len(requested_ids) == 20
        assert counts[PatientCategory.ALL] == 25
        assert has_next is True

    async def test_event_categories_now_answer(self) -> None:
        """**예전에는 400 이었다.**

        「진행 중」과 「챙겨주세요」는 환자에 붙은 값이 아니라 최근 진료에서
        나오는 값이라, 표를 걸러 셀 자리가 없어 막아 두고 0 으로 세고 있었다.
        S2-1 환자 관리 화면이 이 둘을 칩으로 요구하므로 열었다 (KEY-234).

        진료가 없는 환자만 있으면 둘 다 0 이다 — 그것이 맞는 답이다.
        """

        async def actor_override() -> ClinicalActor:
            return ACTOR

        await create_patient("SYN-KEY51-EVT")

        app.dependency_overrides[get_clinical_actor] = actor_override
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
                response = await client.get(
                    "/api/v1/patients",
                    params={"category": PatientCategory.NEEDS_ATTENTION.value},
                )
        finally:
            app.dependency_overrides.pop(get_clinical_actor, None)

        assert response.status_code == 200
        body = response.json()
        assert body["selected_category"] == PatientCategory.NEEDS_ATTENTION.value
        assert body["items"] == [], "진료가 없으면 챙길 일도 없다"
        assert body["counts"][PatientCategory.NEEDS_ATTENTION.value] == 0
        assert body["counts"][PatientCategory.IN_TREATMENT.value] == 0

    async def test_inactive_cutoff_uses_the_hospital_calendar_day(self) -> None:
        patient = await create_patient("SYN-KEY51-KST")
        # 2월 23일 23:59 KST. 8월 24일 00:30 KST 기준으로는 6개월 경계보다
        # 하루 전이지만, UTC 날짜로 계산하면 같은 2월 23일이라 빠졌던 값이다.
        await Visit.create(
            hospital_id=1,
            patient=patient,
            visited_at=datetime(2026, 2, 23, 14, 59, tzinfo=UTC),
        )
        with patch(
            "app.services.patients.now",
            return_value=datetime(2026, 8, 23, 15, 30, tzinfo=UTC),
        ):
            rows, _, _, _ = await PatientService().list(
                ACTOR,
                keyword=None,
                category=PatientCategory.INACTIVE_6_MONTHS,
                cursor=None,
                limit=20,
            )

        assert [row.patient.patient_id for row in rows] == [patient.patient_id]


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

    async def test_candidate_query_does_not_load_irrelevant_old_history(self) -> None:
        old_normal = await create_patient("SYN-KEY51-OLD")
        old_attention = await create_patient("SYN-KEY51-ATTN", sms_consent=False)
        today_patient = await create_patient("SYN-KEY51-TODAY")
        irrelevant = await Visit.create(
            hospital_id=1,
            patient=old_normal,
            visited_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        attention = await Visit.create(
            hospital_id=1,
            patient=old_attention,
            visited_at=datetime(2025, 1, 2, tzinfo=UTC),
        )
        today = await Visit.create(
            hospital_id=1,
            patient=today_patient,
            visited_at=datetime(2026, 8, 23, 1, 30, tzinfo=UTC),
        )

        result = await FrontDeskService().list_visits(
            ACTOR,
            target_date=date(2026, 8, 23),
            categories=None,
            cursor=None,
            limit=20,
        )

        returned = {item.visit_id for item in result.items}
        assert irrelevant.visit_id not in returned
        assert returned == {attention.visit_id, today.visit_id}

    async def test_missing_signal_visit_is_excluded_without_losing_the_remaining_counts(self) -> None:
        """`load_signals()`가 돌려주지 않은 ID는 조회 불가능한 진료로 제외한다."""
        visible_patient = await create_patient("SYN-KEY51-SIGNAL-A")
        missing_patient = await create_patient("SYN-KEY51-SIGNAL-B")
        visible = await Visit.create(
            hospital_id=1,
            patient=visible_patient,
            visited_at=datetime(2026, 8, 23, 1, 30, tzinfo=UTC),
        )
        missing = await Visit.create(
            hospital_id=1,
            patient=missing_patient,
            visited_at=datetime(2026, 8, 23, 2, 30, tzinfo=UTC),
        )

        async def actor_override() -> ClinicalActor:
            return ACTOR

        app.dependency_overrides[get_clinical_actor] = actor_override
        try:
            with patch(
                "app.services.front_desk.load_signals",
                new_callable=AsyncMock,
                return_value={
                    visible.visit_id: VisitSignals(
                        has_document=False,
                        ocr_status=None,
                        guide_status=None,
                        phone=visible_patient.phone,
                        sms_opted_out_at=None,
                    )
                },
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
                    response = await client.get(
                        "/api/v1/front-desk/visits",
                        params={"date": "2026-08-23"},
                    )
        finally:
            app.dependency_overrides.pop(get_clinical_actor, None)

        assert response.status_code == 200
        body = response.json()
        assert [item["visit_id"] for item in body["items"]] == [visible.visit_id]
        assert missing.visit_id not in {item["visit_id"] for item in body["items"]}
        assert body["counts"] == {
            "IN_PROGRESS": 1,
            "NEEDS_ATTENTION": 0,
            "APPROVAL_REQUESTED": 0,
            "SEND_PENDING": 0,
            "COMPLETED": 0,
        }

    async def test_same_date_other_hospital_is_excluded_from_items_and_counts(self) -> None:
        mine_hospital = await Hospital.create(name="KEY-51 병원 격리 A")
        other_hospital = await Hospital.create(name="KEY-51 병원 격리 B")
        mine_patient = await Patient.create(
            hospital_id=mine_hospital.hospital_id,
            hospital_patient_no="SYN-KEY51-SCOPE-A",
            name="합성환자A",
            birth_date=date(1990, 1, 1),
            phone="01039457702",
            sms_consent=True,
        )
        other_patient = await Patient.create(
            hospital_id=other_hospital.hospital_id,
            hospital_patient_no="SYN-KEY51-SCOPE-B",
            name="합성환자B",
            birth_date=date(1990, 1, 1),
            phone="01039457702",
            sms_consent=True,
        )
        mine = await Visit.create(
            hospital_id=mine_hospital.hospital_id,
            patient=mine_patient,
            visited_at=datetime(2026, 8, 23, 1, 30, tzinfo=UTC),
        )
        other = await Visit.create(
            hospital_id=other_hospital.hospital_id,
            patient=other_patient,
            visited_at=datetime(2026, 8, 23, 2, 30, tzinfo=UTC),
        )
        actor = ClinicalActor(
            staff_id=7002,
            hospital_id=mine_hospital.hospital_id,
            roles=frozenset({"staff"}),
        )

        async def actor_override() -> ClinicalActor:
            return actor

        app.dependency_overrides[get_clinical_actor] = actor_override
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
                response = await client.get(
                    "/api/v1/front-desk/visits",
                    params={"date": "2026-08-23"},
                )
        finally:
            app.dependency_overrides.pop(get_clinical_actor, None)

        assert response.status_code == 200
        body = response.json()
        assert [item["visit_id"] for item in body["items"]] == [mine.visit_id]
        assert other.visit_id not in {item["visit_id"] for item in body["items"]}
        assert body["counts"] == {
            "IN_PROGRESS": 1,
            "NEEDS_ATTENTION": 0,
            "APPROVAL_REQUESTED": 0,
            "SEND_PENDING": 0,
            "COMPLETED": 0,
        }

    async def test_visit_response_with_no_doctor_does_not_query_staff(self) -> None:
        patient = await create_patient("SYN-KEY51-NODOCTOR")
        visit = await Visit.create(
            hospital_id=1,
            patient=patient,
            doctor_id=None,
            visited_at=datetime(2026, 8, 23, 1, 30, tzinfo=UTC),
        )

        with CountingQueries() as queries:
            responses = await VisitService().responses(ACTOR, [visit])

        assert responses[0].doctor is None
        assert queries.count == 0
