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


class PatientTableBase(TestCase):
    """**재료만 담는 바닥.** 검사는 안 담는다 — KEY-327.

    처음에는 아래 `PatientTableTestCase` 를 그대로 물려받아 새 검사를 썼다.
    그랬더니 **여기 있는 검사 열넷이 자식마다 한 번씩 더 돌았다** — 자식 다섯이면
    일흔이다. 오래 걸리는 것도 문제지만, 무엇이 어디서 깨졌는지가 흐려진다.
    """

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


class PatientTableTestCase(PatientTableBase):
    """표 한 줄이 담는 것과 칩·검색·배지."""

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

    async def test_the_chips_follow_the_search_word(self) -> None:
        """**검색어를 넣으면 배지도 같이 좁아진다** — KEY-303, 이희진 님 `#270` 리뷰 ②.

        진료에서 나오는 조각(진행 중 · 챙겨주세요)의 셈은 의원의 최근 진료를 훑어
        낸다. 그 셈이 검색어를 모르면 **표는 걸러졌는데 배지는 안 걸러진다** —
        배지가 표보다 커지고, 그 값이 쪽 나눔의 총수라 「다음」에 빈 표가 뜬다.

        위 `test_the_chips_count_the_whole_clinic_not_the_page` 와 짝이다. 검색어가
        **없을** 때는 의원 전체를 세는 것이 맞다 — 둘은 다른 물음이다.
        """
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "chip-search")
        for index in range(6):
            await self.a_patient(clinic, name=f"윤지아{index}", chart=f"Y{index:03}")
        #: 검색어에는 걸리지만 진료가 없어 「진행 중」이 아닌 둘 — 조각마다 총수가
        #: 갈려야 한다. 이것이 없으면 「전체」로 세는 잘못을 못 잡는다.
        for index in range(2):
            await self.a_patient(clinic, name=f"윤지아없{index}", chart=f"YN{index:03}", visited_days_ago=None)
        for index in range(4):
            await self.a_patient(clinic, name=f"박수빈{index}", chart=f"P{index:03}")

        body = await self.fetch(staff, keyword="윤지아", category=PatientCategory.IN_TREATMENT.value)

        assert len(body["items"]) == 6, "표는 검색어와 조각으로 걸러진다"
        assert body["counts"][PatientCategory.ALL.value] == 8, "검색어에 걸리는 사람은 여덟"
        assert body["counts"][PatientCategory.IN_TREATMENT.value] == 6, "배지가 의원 전체(12)를 세면 표(6)보다 커진다"
        assert body["roster"]["total"] == 6, "고른 조각의 총수여야 한다 — 「전체」(8)로 세면 있지도 않은 쪽이 생긴다"
        assert body["roster"]["has_next"] is False

    async def test_a_padded_total_never_offers_an_empty_next_page(self) -> None:
        """총수와 실제 줄이 맞아야 「다음」이 빈 표를 안 준다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "chip-page")
        for index in range(5):
            await self.a_patient(clinic, name=f"윤지아{index}", chart=f"YY{index:03}")
        for index in range(9):
            await self.a_patient(clinic, name=f"딴사람{index}", chart=f"D{index:03}")

        body = await self.fetch(staff, keyword="윤지아", category=PatientCategory.IN_TREATMENT.value, limit=3)

        assert len(body["items"]) == 3
        assert body["roster"]["total"] == 5, "5명인데 14로 세면 두 쪽이 아니라 다섯 쪽이 된다"
        assert body["roster"]["has_next"] is True

        last = await self.fetch(staff, keyword="윤지아", category=PatientCategory.IN_TREATMENT.value, limit=3, offset=3)
        assert len(last["items"]) == 2, "마지막 쪽에 남은 둘"
        assert last["roster"]["has_next"] is False, "여기서 「다음」이 열리면 빈 표가 뜬다"

    async def test_asking_by_cursor_and_by_page_at_once_is_refused(self) -> None:
        """**자리를 옮기는 말은 둘 중 하나만.**

        `cursor` 는 등록 화면의 찾기가 쓰는 「이 뒤로 더」, `offset` 은 관리 표가
        쓰는 「몇 쪽」이다. 함께 주면 `patient_id > cursor` 를 건 **뒤에** 다시
        `offset` 만큼 건너뛴다 — 부른 사람이 뜻한 자리가 아니다. 조용히 한쪽을
        이기게 두면 그 어긋남이 화면에서야 드러난다.
        """
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "both-ways")
        for index in range(4):
            await self.a_patient(clinic, name=f"한서연{index}", chart=f"HS{index:03}")

        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            head = await client.get(
                "/api/v1/patients",
                headers={"Authorization": f"Bearer {access}"},
                #: **커서를 받으려면 `id_asc` 로 물어야 한다** (KEY-327). 다른
                #: 차례의 응답에는 `next_cursor` 가 실리지 않는다 — 값이
                #: `patient_id` 하나뿐이라 그 차례에서는 뜻이 안 맞는다.
                params={"limit": 2, "sort": "id_asc"},
            )
            assert head.status_code == 200, head.text
            cursor = head.json()["page"]["next_cursor"]
            assert cursor, "커서가 안 온다 — 검사가 헛돈다"

            both = await client.get(
                "/api/v1/patients",
                headers={"Authorization": f"Bearer {access}"},
                params={"limit": 2, "cursor": cursor, "offset": 2},
            )

        assert both.status_code == 400, f"둘을 함께 받고도 답을 준다 — {both.text}"
        body = both.json()
        assert body["code"] == "INVALID_REQUEST"
        assert {item["field"] for item in body["field_errors"]} == {"cursor", "offset"}, (
            "어느 인자가 문제인지 말하지 않는다"
        )

    async def test_each_way_on_its_own_still_works(self) -> None:
        """막는 것이 지나쳐 한쪽까지 닫으면 등록 화면의 찾기가 죽는다."""
        clinic = await self.a_clinic()
        staff = await self.a_staff(clinic, ["staff"], "one-way")
        for index in range(4):
            await self.a_patient(clinic, name=f"조하늘{index}", chart=f"CH{index:03}")

        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        headers = {"Authorization": f"Bearer {access}"}
        walking: dict[str, str | int] = {"limit": 2, "sort": "id_asc"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            #: 이어 보기 — 환자 번호 차례로 두 쪽 (KEY-327)
            head = await client.get("/api/v1/patients", headers=headers, params=walking)
            tail = await client.get(
                "/api/v1/patients", headers=headers, params={**walking, "cursor": head.json()["page"]["next_cursor"]}
            )
            #: 쪽 번호 — 관리 표의 기본인 최근 등록순으로 두 쪽
            first = await client.get("/api/v1/patients", headers=headers, params={"limit": 2})
            second = await client.get("/api/v1/patients", headers=headers, params={"limit": 2, "offset": 2})

        for answer in (head, tail, first, second):
            assert answer.status_code == 200, answer.text

        names = lambda answer: [row["name"] for row in answer.json()["items"]]  # noqa: E731

        #: **두 길이 각자 온전하다.** 예전에는 둘이 같은 사람을 준다고 쟀는데,
        #: 그건 둘 다 `patient_id` 오름차순이던 때의 우연이다 — 관리 표가 최근
        #: 등록순으로 서면서(KEY-327) 갈렸다. 각 길이 **제 차례로 한 번씩**
        #: 모두를 보여 주는지가 재야 할 것이다.
        assert names(head) + names(tail) == ["조하늘0", "조하늘1", "조하늘2", "조하늘3"], (
            "이어 보기가 번호 차례로 안 간다 — 건너뛰거나 겹친다"
        )
        assert names(first) + names(second) == ["조하늘3", "조하늘2", "조하늘1", "조하늘0"], (
            "쪽 번호가 등록일 최근순으로 안 간다"
        )

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
