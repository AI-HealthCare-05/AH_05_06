"""환자 이력 — KEY-234, 와이어프레임 S2-2 「환자 이력 모달 ★ 신설」.

**환자 단위다.** 이미 있는 진료 타임라인(D1-6)은 진료 하나짜리라 「이 환자가
지난 세 번 어떻게 했나」를 물을 수 없었다. 묻는 것이 다르다 — 저쪽은 「이
진료가 어떻게 흘러갔나」이고 이쪽은 「이 환자가 계속 하고 있나」다.

원문 주석이 층을 못박는다: 관리에 필요한 만큼(**발송 · 열람 · 응답**)은 이
모달로 스탭 · 의사 모두에게, 감사 수준(누가 열어봤나 · 토큰 · 버전 이력)은
A1-7 로 관리자에게만. **그래서 여기에 직원 열람도 토큰도 담지 않는다.**
"""

from datetime import date, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.time import DISPLAY_TIMEZONE
from app.core.utils.security import hash_password
from app.main import app
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient, PatientGender
from app.models.prescriptions import Prescription, PrescriptionItem
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    CheckIn,
    CheckInMedication,
    GuideDocument,
    GuideMessage,
    GuideMessageKind,
    GuideMessageStatus,
    PatientUsageEvent,
    PatientUsageEventType,
    Visit,
)
from app.services.patient_history import DEFAULT_VISITS
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

TODAY = date(2026, 5, 20)


def at(day: date, hour: int = 10, minute: int = 0) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=DISPLAY_TIMEZONE).replace(hour=hour, minute=minute)


class PatientHistoryTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def a_clinic(self, name: str = "도로시여성의원") -> Hospital:
        return await Hospital.create(name=name)

    async def a_staff(self, clinic: Hospital, roles: list[str], login: str, name: str = "서지현") -> Staff:
        return await Staff.create(
            hospital=clinic,
            login_id=login,
            password_hash=hash_password("pw"),
            name=name,
            roles=roles,
            must_change_password=False,
        )

    async def a_patient(self, clinic: Hospital, name: str = "유지수", chart: str = "10118") -> Patient:
        return await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no=chart,
            name=name,
            birth_date=date(1996, 4, 10),
            gender=PatientGender.FEMALE,
            phone="01031414410",
        )

    async def a_visit(
        self,
        clinic: Hospital,
        patient: Patient,
        *,
        on: date,
        doctor: Staff | None = None,
        prescription_set: str | None = "자궁내막증 · 비잔 (계속)",
        days: int | None = 84,
    ) -> GuideDocument:
        visit = await Visit.create(
            hospital_id=clinic.hospital_id,
            patient=patient,
            doctor_id=doctor.staff_id if doctor else None,
            visited_at=at(on),
        )
        if prescription_set is not None:
            course = await Prescription.create(visit=visit, prescription_set=prescription_set)
            await PrescriptionItem.create(
                prescription=course, name="비잔정 2mg", frequency="1일 1회", duration_days=days
            )
            # 일수가 빈 줄이 섞여도 긴 쪽을 잡아야 한다
            await PrescriptionItem.create(prescription=course, name="진통제", frequency="필요시")
        return await GuideDocument.create(hospital_id=clinic.hospital_id, visit=visit)

    async def a_message(
        self,
        document: GuideDocument,
        kind: GuideMessageKind,
        *,
        on: date,
        sent: bool = True,
    ) -> GuideMessage:
        when = at(on, 18 if kind is GuideMessageKind.GUIDE else 10)
        return await GuideMessage.create(
            guide_document=document,
            kind=kind,
            status=GuideMessageStatus.SENT if sent else GuideMessageStatus.SCHEDULED,
            scheduled_at=when,
            sent_at=when if sent else None,
        )

    async def a_view(self, document: GuideDocument, when: datetime) -> None:
        row = await PatientUsageEvent.create(guide_document=document, event_type=PatientUsageEventType.GUIDE_VIEWED)
        # `created_at` 은 auto_now_add 라 만든 뒤 밀어 넣는다
        await PatientUsageEvent.filter(patient_usage_event_id=row.patient_usage_event_id).update(created_at=when)

    async def fetch(self, staff: Staff, patient: Patient, **params) -> dict:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/patients/{patient.patient_id}/history",
                headers={"Authorization": f"Bearer {access}"},
                params=params,
            )
        assert response.status_code == 200, response.text
        return response.json()

    # ── 머리말 ───────────────────────────────────────────

    async def test_the_header_says_who_this_is(self) -> None:
        """원문 「유지수 님 이력 / 차트 10118 · 자궁내막증 · 김연우 원장 · 010-…」."""
        clinic = await self.a_clinic()
        doctor = await self.a_staff(clinic, ["doctor"], "hist-doc", name="김연우")
        staff = await self.a_staff(clinic, ["staff"], "hist-staff")
        patient = await self.a_patient(clinic)
        await self.a_visit(clinic, patient, on=TODAY, doctor=doctor)

        body = await self.fetch(staff, patient)

        assert body["name"] == "유지수"
        assert body["hospital_patient_no"] == "10118"
        assert body["phone"] == "01031414410"
        assert body["doctor"]["name"] == "김연우"

    async def a_diagnosis(self, clinic: Hospital, visit_id: int, name: str, job_id: str, by: Staff) -> None:
        """그 진료에 **확정된 진단** 하나를 붙인다."""
        job = await OcrJob.create(
            ocr_job_id=job_id,
            hospital_id=clinic.hospital_id,
            visit_id=visit_id,
            status=OcrJobStatus.COMPLETED,
            requested_by=by.staff_id,
        )
        result = await OcrResult.create(ocr_job=job, model_name="fixture")
        await OcrField.create(
            ocr_result=result, field_type="DIAGNOSIS", extracted_value=name, is_confirmed=True
        )

    async def test_the_diagnosis_comes_from_the_newest_visit(self) -> None:
        """**옆의 `_doctor` 와 같은 규칙이다** — 가장 최근 진료의 것.

        `visit_id__in` 으로 한꺼번에 가져와 첫 줄을 쓰고 있었다. MySQL 은
        `ORDER BY` 없이 차례를 보장하지 않아, 과거 진료에서 확정한 진단이
        최신 진료에서 고친 진단보다 먼저 나올 수 있었다 — 모달 맨 위에 옛
        진단이 뜬다. 2heej 님이 `#183` 리뷰에서 찾아 주셨다.

        **옛 진료를 먼저 넣는다.** 넣은 차례대로 나오면 옛것이 이기므로,
        정렬을 안 하면 여기서 걸린다.
        """
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "dx")
        patient = await self.a_patient(clinic)

        old = await self.a_visit(clinic, patient, on=date(2025, 11, 7))
        new = await self.a_visit(clinic, patient, on=TODAY)
        await self.a_diagnosis(clinic, old.visit_id, "다낭성난소증후군", "job-old", staff)
        await self.a_diagnosis(clinic, new.visit_id, "자궁내막증", "job-new", staff)

        body = await self.fetch(staff, patient)

        assert body["diagnosis_name"] == "자궁내막증", "옛 진료의 진단이 이겼다"

    async def test_an_unconfirmed_diagnosis_is_not_used(self) -> None:
        """**확정 안 한 값은 진단이 아니다.** 판독이 읽어 놓기만 한 글자를
        모달 맨 위에 「이 환자의 진단」으로 세우면 안 된다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "dx-unconfirmed")
        patient = await self.a_patient(clinic)
        visit = await self.a_visit(clinic, patient, on=TODAY)

        job = await OcrJob.create(
            ocr_job_id="job-raw",
            hospital_id=clinic.hospital_id,
            visit_id=visit.visit_id,
            status=OcrJobStatus.COMPLETED,
            requested_by=staff.staff_id,
        )
        result = await OcrResult.create(ocr_job=job, model_name="fixture")
        await OcrField.create(
            ocr_result=result, field_type="DIAGNOSIS", extracted_value="자궁내막증", is_confirmed=False
        )

        body = await self.fetch(staff, patient)

        assert body["diagnosis_name"] is None

    # ── 블록 차례 ────────────────────────────────────────

    async def test_the_newest_visit_is_on_top(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "order")
        patient = await self.a_patient(clinic)
        for on in (date(2025, 11, 7), TODAY, date(2026, 2, 14)):
            await self.a_visit(clinic, patient, on=on)

        body = await self.fetch(staff, patient)

        days = [item["visited_at"][:10] for item in body["visits"]]
        assert days == ["2026-05-20", "2026-02-14", "2025-11-07"]

    async def test_only_the_first_few_blocks_come_but_the_count_is_whole(self) -> None:
        """원문 「지난 안내문 4건 중 3건」 — 잘라도 몇 건인지는 말한다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "trunc")
        patient = await self.a_patient(clinic)
        for index in range(4):
            await self.a_visit(clinic, patient, on=TODAY - timedelta(days=90 * index))

        body = await self.fetch(staff, patient)

        assert len(body["visits"]) == DEFAULT_VISITS == 3
        assert body["total"] == 4

    # ── 한 블록 안 ───────────────────────────────────────

    async def test_a_block_carries_the_course_and_the_guide(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "block")
        patient = await self.a_patient(clinic)
        document = await self.a_visit(clinic, patient, on=TODAY)
        await self.a_message(document, GuideMessageKind.GUIDE, on=TODAY)
        await self.a_view(document, at(date(2026, 5, 27), 9))

        block = (await self.fetch(staff, patient))["visits"][0]

        assert block["prescription_set"] == "자궁내막증 · 비잔 (계속)"
        assert block["course_days"] == 84, "약이 여럿이고 일수가 빈 줄이 섞여도 긴 쪽을 잡는다"
        assert block["guide_sent_at"].startswith("2026-05-20T18:00")
        assert block["guide_viewed_at"].startswith("2026-05-27T09:00")
        assert block["runs_out_on"] == "2026-08-12", "원문 「소진 08-12」"

    async def test_an_unsent_guide_has_no_sent_time(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "unsent")
        patient = await self.a_patient(clinic)
        document = await self.a_visit(clinic, patient, on=TODAY)
        await self.a_message(document, GuideMessageKind.GUIDE, on=TODAY, sent=False)

        block = (await self.fetch(staff, patient))["visits"][0]

        assert block["guide_sent_at"] is None, "예약만 잡힌 것을 「발송」이라 적으면 안 된다"

    async def test_an_unknown_course_length_gives_no_run_out_day(self) -> None:
        """**모르면 셈하지 않는다.** 지어낸 날짜가 제일 나쁘다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "noday")
        patient = await self.a_patient(clinic)
        await self.a_visit(clinic, patient, on=TODAY, days=None)

        block = (await self.fetch(staff, patient))["visits"][0]

        assert block["course_days"] is None and block["runs_out_on"] is None

    async def test_an_older_visit_knows_the_patient_came_back(self) -> None:
        """원문의 「재진 예약 없음」이 이 값이다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "again")
        patient = await self.a_patient(clinic)
        await self.a_visit(clinic, patient, on=date(2026, 2, 14))
        await self.a_visit(clinic, patient, on=TODAY)

        blocks = (await self.fetch(staff, patient))["visits"]

        assert blocks[0]["revisited"] is False, "가장 최근 진료 뒤에는 아직 아무것도 없다"
        assert blocks[1]["revisited"] is True

    # ── 확인 문자 ────────────────────────────────────────

    async def test_the_checks_line_up_in_order(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "checks")
        patient = await self.a_patient(clinic)
        document = await self.a_visit(clinic, patient, on=TODAY)
        await self.a_message(document, GuideMessageKind.CHECK_D30, on=date(2026, 6, 19))
        await self.a_message(document, GuideMessageKind.CHECK_D7, on=date(2026, 5, 27))
        await self.a_message(document, GuideMessageKind.CHECK_D15, on=date(2026, 6, 4))

        checks = (await self.fetch(staff, patient))["visits"][0]["checks"]

        assert [row["kind"] for row in checks] == ["CHECK_D7", "CHECK_D15", "CHECK_D30"]
        assert all(row["viewed_at"] is None for row in checks), "원문 「일주일 뒤 05-27 미열람」"

    async def test_a_view_belongs_to_the_message_that_came_before_it(self) -> None:
        """**열람은 안내문에 달리지 문자에 달리지 않는다.**

        그래도 시각이 남으므로, 이 문자가 나간 뒤 다음 문자 전까지 열었으면
        이 문자를 보고 연 것으로 읽는다 — 「어느 문자가 환자를 다시 데려왔나」에
        답할 수 있는 유일한 방법이다.
        """
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "attrib")
        patient = await self.a_patient(clinic)
        document = await self.a_visit(clinic, patient, on=TODAY)
        await self.a_message(document, GuideMessageKind.CHECK_D7, on=date(2026, 5, 27))
        await self.a_message(document, GuideMessageKind.CHECK_D15, on=date(2026, 6, 4))
        await self.a_view(document, at(date(2026, 6, 5), 9))

        checks = (await self.fetch(staff, patient))["visits"][0]["checks"]

        assert checks[0]["viewed_at"] is None, "일주일 뒤 문자 다음 열람이 아니다"
        assert checks[1]["viewed_at"].startswith("2026-06-05"), "보름 뒤 문자가 데려왔다"

    async def test_the_answer_hangs_on_the_first_check_only(self) -> None:
        """`check_in` 은 안내문당 한 건이고 D+7 것이다 — 회차를 가를 수 없다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "answer")
        patient = await self.a_patient(clinic)
        document = await self.a_visit(clinic, patient, on=TODAY)
        await self.a_message(document, GuideMessageKind.CHECK_D7, on=date(2026, 5, 27))
        await self.a_message(document, GuideMessageKind.CHECK_D15, on=date(2026, 6, 4))
        await CheckIn.create(guide_document=document, medication=CheckInMedication.UNCOMFORTABLE)

        checks = (await self.fetch(staff, patient))["visits"][0]["checks"]

        assert checks[0]["answer"] == "uncomfortable", "원문 「응답 「먹고 있는데 불편해요」」"
        assert checks[1]["answer"] is None

    # ── 담지 않는 것 ─────────────────────────────────────

    async def test_the_modal_carries_no_staff_or_token_trail(self) -> None:
        """원문: 「직원 열람 기록과 토큰 이력은 담지 않습니다」.

        **담을 칸을 만들지 않는 것이 담지 않겠다는 약속을 지키는 방법이다.**
        """
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "quiet")
        patient = await self.a_patient(clinic)
        await self.a_visit(clinic, patient, on=TODAY)

        body = await self.fetch(staff, patient)

        text = str(body)
        for word in ("token", "staff_id", "actor", "viewer", "version"):
            assert word not in text, f"{word} 가 모달 응답에 새어 있다"

    # ── 격리 · 권한 ──────────────────────────────────────

    async def test_another_clinic_patient_is_not_found(self) -> None:
        mine = await self.a_clinic("도로시여성의원")
        theirs = await self.a_clinic("다른의원")
        staff = await self.a_staff(mine, ["staff"], "hist-scope")
        outsider = await self.a_patient(theirs, name="남의환자", chart="T001")

        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/patients/{outsider.patient_id}/history",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert response.status_code == 404, "있고 없고가 새면 그 자체가 정보다"

    async def test_both_staff_and_doctor_can_open_it(self) -> None:
        clinic = await self.a_clinic()
        patient = await self.a_patient(clinic)
        await self.a_visit(clinic, patient, on=TODAY)

        for roles, login in ((["staff"], "open-staff"), (["doctor"], "open-doctor")):
            staff = await self.a_staff(clinic, roles, login)
            body = await self.fetch(staff, patient)
            assert body["patient_id"] == patient.patient_id, f"{roles} 가 못 연다"
