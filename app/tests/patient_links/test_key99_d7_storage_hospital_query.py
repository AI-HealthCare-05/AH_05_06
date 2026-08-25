"""D+7 응답 저장과 병원 조회의 회귀 계약을 한 흐름으로 검증한다 — KEY-99."""

from datetime import datetime

from app.models.patients import Patient
from app.models.visits import CheckIn, Visit
from app.tests.patient_links.test_key151_checkins import TOKEN, CheckInTestCase, make_linked_guide
from app.tests.patient_links.test_patient_links import make_hospital, make_staff


class TestD7StorageAndHospitalQuery(CheckInTestCase):
    async def test_patient_submission_is_linked_to_visit_and_safely_returned_to_its_hospital(self) -> None:
        hospital = await make_hospital("KEY-99 정상 합성의원")
        guide = await make_linked_guide(hospital)
        staff = await make_staff(hospital, "key99-staff", ["staff"])
        visit = await guide.visit
        patient = await visit.patient

        async with self.client() as client:
            saved = await client.post(
                f"/api/v1/checkins/{TOKEN}",
                json={
                    "medication": "uncomfortable",
                    "pain": {"had": True, "score": 6, "types": ["menstrual", "chronic_pelvic"]},
                },
            )
            hospital_read = await client.get(
                f"/api/v1/visits/{visit.visit_id}/checkin",
                headers=await self.headers(staff),
            )

        assert saved.status_code == 201
        check_in = await CheckIn.get(check_in_id=saved.json()["check_in_id"])
        assert check_in.guide_document_id == guide.guide_document_id
        assert (await check_in.guide_document).visit_id == visit.visit_id

        assert hospital_read.status_code == 200
        body = hospital_read.json()
        assert set(body) == {
            "check_in_id",
            "visit_id",
            "medication",
            "pain",
            "submitted_at",
            "demo_only",
        }
        assert body["check_in_id"] == check_in.check_in_id
        assert body["visit_id"] == visit.visit_id
        assert body["medication"] == "uncomfortable"
        assert body["pain"] == {"had": True, "score": 6, "types": ["menstrual", "chronic_pelvic"]}
        assert datetime.fromisoformat(body["submitted_at"]) == check_in.created_at

        serialized = hospital_read.text
        for forbidden in (
            TOKEN,
            patient.name,
            patient.phone,
            patient.hospital_patient_no,
            "token_digest",
            "guide_document_id",
        ):
            assert forbidden not in serialized

    async def test_duplicate_submission_is_rejected_without_overwriting_the_first_answer(self) -> None:
        hospital = await make_hospital("KEY-99 중복 합성의원")
        await make_linked_guide(hospital)

        async with self.client() as client:
            first = await client.post(
                f"/api/v1/checkins/{TOKEN}",
                json={"medication": "taking", "pain": None},
            )
            duplicate = await client.post(
                f"/api/v1/checkins/{TOKEN}",
                json={"medication": "missing", "pain": {"had": False, "score": None, "types": []}},
            )

        assert first.status_code == 201
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "CHECKIN_ALREADY_ANSWERED"
        assert TOKEN not in duplicate.text

        stored = await CheckIn.all().get()
        assert stored.check_in_id == first.json()["check_in_id"]
        assert stored.medication == "taking"
        assert await CheckIn.all().count() == 1

    async def test_other_hospital_cannot_distinguish_a_private_visit_from_a_missing_one(self) -> None:
        owner = await make_hospital("KEY-99 소유 합성의원")
        outsider = await make_hospital("KEY-99 외부 합성의원")
        guide = await make_linked_guide(owner)
        outside_staff = await make_staff(outsider, "key99-outsider", ["staff"])

        async with self.client() as client:
            saved = await client.post(
                f"/api/v1/checkins/{TOKEN}",
                json={"medication": "taking", "pain": None},
            )
            private_visit = await client.get(
                f"/api/v1/visits/{guide.visit_id}/checkin",
                headers=await self.headers(outside_staff),
            )
            missing_visit = await client.get(
                "/api/v1/visits/999999999/checkin",
                headers=await self.headers(outside_staff),
            )

        assert saved.status_code == 201
        for response in (private_visit, missing_visit):
            assert response.status_code == 404
            assert response.json() == {
                "code": "CHECKIN_NOT_FOUND",
                "message": "D+7 응답을 찾을 수 없습니다.",
            }
            assert TOKEN not in response.text

        assert private_visit.text == missing_visit.text

    async def test_a_visit_cannot_read_another_visit_answer_in_the_same_hospital(self) -> None:
        hospital = await make_hospital("KEY-99 두 진료 합성의원")
        answered_guide = await make_linked_guide(hospital)
        staff = await make_staff(hospital, "key99-two-visits", ["staff"])
        other_patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no="SYN-KEY99-02",
            name="합성환자 둘",
            birth_date="1992-03-04",
            phone="01000009902",
            sms_consent=True,
        )
        unanswered_visit = await Visit.create(
            hospital_id=hospital.hospital_id,
            patient=other_patient,
            visited_at="2026-08-25T09:00:00+09:00",
        )

        async with self.client() as client:
            saved = await client.post(
                f"/api/v1/checkins/{TOKEN}",
                json={"medication": "taking", "pain": None},
            )
            answered = await client.get(
                f"/api/v1/visits/{answered_guide.visit_id}/checkin",
                headers=await self.headers(staff),
            )
            unanswered = await client.get(
                f"/api/v1/visits/{unanswered_visit.visit_id}/checkin",
                headers=await self.headers(staff),
            )

        assert saved.status_code == 201
        assert answered.status_code == 200
        assert answered.json()["visit_id"] == answered_guide.visit_id
        assert answered.json()["medication"] == "taking"
        assert unanswered.status_code == 404
        assert unanswered.json()["code"] == "CHECKIN_NOT_FOUND"
