"""환자 관리 표 — KEY-234, 와이어프레임 S2-1.

원문 주석: 「상태 체계는 세 축이다 — ① 기본 상태 … ② 질환 · 담당 컬럼:
목록(S1 · D1)에서는 이름 우측 칩으로, 표인 여기서는 독립 컬럼으로 — **같은
속성, 표기만 서식에 맞춘다** ③ 세부 상태」.

그래서 여기서 가장 크게 재는 것은 **접수대 목록과 같은 값이 나오는가** 다.
두 화면이 같은 환자를 다르게 부르면 어느 쪽이 맞는지 알 수 없다.
"""

from datetime import date, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.time import DISPLAY_TIMEZONE
from app.core.utils.security import hash_password
from app.dtos.patients import PatientCategory
from app.main import app
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient, PatientGender
from app.models.staffs import Hospital, Staff
from app.models.visits import GuideDocument, Visit
from app.services.patient_flags import PatientFlag
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

TODAY = datetime.now(DISPLAY_TIMEZONE).date()


class PatientTableTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def a_clinic(self, name: str = "도로시여성의원") -> Hospital:
        return await Hospital.create(name=name)

    async def a_staff(self, hospital: Hospital, roles: list[str], login: str, name: str = "서지현") -> Staff:
        return await Staff.create(
            hospital=hospital,
            login_id=login,
            password_hash=hash_password("pw"),
            name=name,
            roles=roles,
            must_change_password=False,
        )

    async def a_patient(
        self,
        hospital: Hospital,
        *,
        name: str,
        chart: str,
        doctor: Staff | None = None,
        visited_days_ago: int | None = 0,
        diagnosis: str | None = None,
    ) -> Patient:
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no=chart,
            name=name,
            birth_date=date(1996, 4, 10),
            gender=PatientGender.FEMALE,
            phone=f"010{abs(hash(chart)) % 90000000 + 10000000}",
            sms_consent=True,
            # 실제 등록은 `PatientService.create` 가 이 시각을 함께 남긴다.
            # 표의 「동의 · 05-20」이 그 날짜다.
            sms_consented_at=datetime.now(DISPLAY_TIMEZONE),
        )
        if visited_days_ago is None:
            return patient
        when = datetime.combine(
            TODAY - timedelta(days=visited_days_ago), datetime.min.time(), tzinfo=DISPLAY_TIMEZONE
        ).replace(hour=10)
        visit = await Visit.create(
            hospital_id=hospital.hospital_id,
            patient=patient,
            doctor_id=doctor.staff_id if doctor else None,
            visited_at=when,
        )
        await GuideDocument.create(hospital_id=hospital.hospital_id, visit=visit)
        if diagnosis is not None:
            result = await self.a_reading(hospital, visit, doctor.staff_id if doctor else 1)
            await OcrField.create(
                ocr_result=result,
                field_type="DIAGNOSIS",
                extracted_value=diagnosis,
                is_confirmed=True,
            )
        return patient

    @staticmethod
    async def a_reading(hospital: Hospital, visit: Visit, by: int) -> OcrResult:
        job = await OcrJob.create(
            ocr_job_id=f"job-{visit.visit_id}",
            hospital_id=hospital.hospital_id,
            visit_id=visit.visit_id,
            status=OcrJobStatus.COMPLETED,
            requested_by=by,
        )
        return await OcrResult.create(ocr_job=job, model_name="synthetic")

    async def fetch(self, staff: Staff, **params) -> dict:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/patients", headers={"Authorization": f"Bearer {access}"}, params=params
            )
        assert response.status_code == 200, response.text
        return response.json()

    # ── 한 줄이 담는 것 ──────────────────────────────────

    async def test_a_row_carries_every_column_the_table_shows(self) -> None:
        clinic = await self.a_clinic()
        doctor = await self.a_staff(clinic, ["doctor"], "row-doctor", name="김연우")
        staff = await self.a_staff(clinic, ["staff"], "row-staff")
        await self.a_patient(clinic, name="유지수", chart="10118", doctor=doctor, diagnosis="자궁내막증")

        item = (await self.fetch(staff))["items"][0]

        assert item["hospital_patient_no"] == "10118"
        assert item["name"] == "유지수"
        assert item["gender"] == "FEMALE" and item["birth_date"] == "1996-04-10" and item["age"] >= 29
        assert item["diagnosis_name"] == "자궁내막증"
        assert item["doctor"]["name"] == "김연우"
        assert item["phone"].startswith("010")
        assert item["sms_consent"] is True and item["sms_consented_at"]
        assert item["latest_visit"]["visited_at"]
        assert item["work_category"], "기본 상태가 없으면 표의 열 하나가 빈다"
        assert item["detail_status"]
        assert item["flags"] == [], "빈 목록이 정상이다"

    async def test_a_patient_who_never_came_has_no_visit_columns(self) -> None:
        """**등록만 하고 진료가 없는 환자.** 지어내지 않고 비워 둔다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "novisit")
        await self.a_patient(clinic, name="장소윤", chart="99999", visited_days_ago=None)

        item = (await self.fetch(staff))["items"][0]

        assert item["latest_visit"] is None
        assert item["work_category"] is None and item["detail_status"] is None
        assert item["diagnosis_name"] is None and item["doctor"] is None

    async def test_an_unconfirmed_diagnosis_does_not_reach_the_table(self) -> None:
        """의사가 아직 안 본 글자가 「이 환자의 진단」으로 읽히면 안 된다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "unconfirmed")
        patient = await self.a_patient(clinic, name="김서연", chart="12345")
        visit = await Visit.get(patient_id=patient.patient_id)
        result = await self.a_reading(clinic, visit, staff.staff_id)
        await OcrField.create(
            ocr_result=result, field_type="DIAGNOSIS", extracted_value="자궁내막증", is_confirmed=False
        )

        item = (await self.fetch(staff))["items"][0]

        assert item["diagnosis_name"] is None

    # ── 칩 ───────────────────────────────────────────────

    async def test_the_chips_count_the_whole_clinic_not_the_page(self) -> None:
        """**보이는 쪽만 세면 스탭이 일이 없다고 믿는다.**

        원문은 「전체 128명 · 진행 중 34」인데, 한 쪽에 20명만 보인다.
        """
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "chips")
        for index in range(25):
            await self.a_patient(clinic, name=f"환자{index}", chart=f"C{index:03}")

        body = await self.fetch(staff, limit=5)

        assert len(body["items"]) == 5
        assert body["counts"][PatientCategory.ALL.value] == 25
        assert body["counts"][PatientCategory.IN_TREATMENT.value] == 25, "쪽이 아니라 의원 전체를 센다"

    async def test_a_finished_patient_is_not_in_treatment(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "done")
        await self.a_patient(clinic, name="옛환자", chart="OLD1", visited_days_ago=200)

        body = await self.fetch(staff)

        assert body["counts"][PatientCategory.INACTIVE_6_MONTHS.value] == 1

    async def test_filtering_by_a_chip_narrows_the_rows(self) -> None:
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "narrow")
        await self.a_patient(clinic, name="진료함", chart="HAS1")
        await self.a_patient(clinic, name="진료없음", chart="NON1", visited_days_ago=None)

        body = await self.fetch(staff, category=PatientCategory.IN_TREATMENT.value)

        assert [item["name"] for item in body["items"]] == ["진료함"]

    # ── 검색 · 격리 ──────────────────────────────────────

    async def test_search_covers_the_three_things_the_box_promises(self) -> None:
        """원문 검색창: 「🔍 이름 · 차트번호 · 휴대폰」."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "search")
        await self.a_patient(clinic, name="유지수", chart="10118")
        await self.a_patient(clinic, name="백소라", chart="09660")

        found = await Patient.get(hospital_patient_no="10118")
        for keyword in ("유지수", "10118", found.phone):
            body = await self.fetch(staff, keyword=keyword)
            assert [item["name"] for item in body["items"]] == ["유지수"], f"{keyword} 로 못 찾는다"

    async def test_another_clinic_is_invisible(self) -> None:
        mine = await self.a_clinic("도로시여성의원")
        theirs = await self.a_clinic("다른의원")
        staff = await self.a_staff(mine, ["staff"], "scope")
        await self.a_patient(mine, name="우리환자", chart="M001")
        await self.a_patient(theirs, name="남의환자", chart="T001")

        body = await self.fetch(staff)

        assert [item["name"] for item in body["items"]] == ["우리환자"]
        assert body["counts"][PatientCategory.ALL.value] == 1

    async def test_a_doctor_from_another_clinic_is_not_named(self) -> None:
        """담당 이름을 의원 밖에서 끌어오면 남의 의원 직원 이름이 표에 뜬다."""
        mine = await self.a_clinic("도로시여성의원")
        theirs = await self.a_clinic("다른의원")
        outsider = await self.a_staff(theirs, ["doctor"], "outsider", name="남의의사")
        staff = await self.a_staff(mine, ["staff"], "scope-doctor")
        await self.a_patient(mine, name="우리환자", chart="M002", doctor=outsider)

        item = (await self.fetch(staff))["items"][0]

        assert item["doctor"] is None

    # ── 배지가 표에 닿는가 ──────────────────────────────

    async def test_a_stopped_answer_reaches_the_row_and_the_chip(self) -> None:
        from app.models.visits import CheckIn, CheckInMedication

        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "flagrow")
        patient = await self.a_patient(clinic, name="백소라", chart="09660")
        document = await GuideDocument.get(visit__patient_id=patient.patient_id)
        await CheckIn.create(guide_document=document, medication=CheckInMedication.STOPPED_SIDE_EFFECT)

        body = await self.fetch(staff)

        assert body["items"][0]["flags"] == [PatientFlag.STOPPED_DOSING]
        assert body["counts"][PatientCategory.NEEDS_ATTENTION.value] == 1, (
            "원문에서 「완료 · 열람」인 줄에 ⚠ 배지가 붙어 있다 — 이탈도 챙길 일이다"
        )
