"""감사 로그 조회 — A1-6 · A1-7 (KEY-322).

이벤트는 이미 쌓이고 있었고 **읽을 길이 없던 것**이 이 티켓이다. 그래서 재는
것은 「읽히는가」가 아니라 **무엇이 새지 않는가 · 무엇이 안 빠지는가**다.

    울타리      남의 의원 이벤트가 결과에 없다
    새지 않음   링크 토큰 · OTP 코드 · 환자 이름·전화가 응답에 없다
    섞임        표 다섯이 한 목록에 시간순으로 섞인다
    거르개      기간 · 행위자 · 유형 · 진료 넷이 각각 듣는다
    쪽 나눔     같은 커서로 다시 물으면 같은 답이다
    읽기 전용   조회가 아무것도 안 쓴다
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff, StaffAccountEvent, StaffAccountEventType
from app.models.visits import (
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideMessage,
    GuideMessageEvent,
    GuideMessageEventType,
    GuideMessageKind,
    PatientGuideLink,
    PatientOtpEvent,
    PatientOtpEventType,
    PatientUsageEvent,
    PatientUsageEventType,
    Visit,
)
from app.tests.auth_base import AuthTestCase, login_headers, make_clinic, make_staff_account

AUDIT_URL = "/api/v1/admin/audit-logs"

#: 합성 링크 토큰·전화번호. **이 값들이 응답에 나오면 안 된다.**
SECRET_TOKEN_DIGEST = "a" * 64
SECRET_PHONE = "01044521234"
SECRET_PATIENT_NAME = "새어나오면안되는환자"


async def _at(model: Any, pk_name: str, pk: int, when: datetime) -> None:
    """`auto_now_add` 를 우회해 시각을 못 박는다 — 순서를 재려면 시각이 내 손에
    있어야 한다. 모델을 거치지 않고 표를 직접 고친다."""
    await model.filter(**{pk_name: pk}).update(created_at=when)


class AuditTestCase(AuthTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.base = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)

        #: **코드와 함께 만든다** (KEY-324). 코드가 없는 의원의 직원은 어떤
        #: 코드로도 못 들어온다 — 이 파일의 검사는 전부 로그인부터 시작한다.
        self.hospital = await make_clinic("도로시여성의원", "clinic0001")
        self.other = await make_clinic("옆집여성의원", "clinic0002")
        self.admin = await make_staff_account(self.hospital, "admin01", ["admin"], name="관리자")
        self.doctor = await make_staff_account(self.hospital, "doctor01", ["doctor"], name="박연")
        self.other_admin = await make_staff_account(self.other, "admin21", ["admin"], name="옆집관리자")

        self.visit = await self._visit(self.hospital, "12345")
        self.second_visit = await self._visit(self.hospital, "12346")
        self.foreign_visit = await self._visit(self.other, "99999")

    async def _visit(self, hospital: Hospital, chart: str) -> Visit:
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no=chart,
            name=SECRET_PATIENT_NAME,
            phone=SECRET_PHONE,
            birth_date="1990-01-01",
        )
        return await Visit.create(hospital_id=hospital.hospital_id, patient=patient, visited_at=self.base)

    async def _guide(self, visit: Visit) -> GuideDocument:
        return await GuideDocument.create(hospital_id=visit.hospital_id, visit=visit)

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def _get(self, params: dict[str, Any] | None = None, who: str = "admin01") -> Any:
        #: 의원 코드를 **그 사람의 의원에서** 읽는다 (KEY-324). 하나로 박으면
        #: 옆집 관리자(`admin21`)가 그 코드로는 아예 못 들어와, 울타리를 재는
        #: 검사가 `401` 로 죽는다.
        staff = await Staff.get(login_id=who).select_related("hospital")
        async with self.client() as client:
            headers = await login_headers(client, who, clinic_code=staff.hospital.code or "")
            return await client.get(AUDIT_URL, params=params or {}, headers=headers)


class TestOnlyAdminsRead(AuditTestCase):
    async def test_an_admin_reads(self) -> None:
        response = await self._get()
        assert response.status_code == 200, response.text

    async def test_a_doctor_is_refused(self) -> None:
        """`AUDIT_READ` 는 `admin` 만 여는 권한이다 — 의사도 못 본다."""
        response = await self._get(who="doctor01")
        assert response.status_code == 403, response.text

    async def test_no_token_no_read(self) -> None:
        async with self.client() as client:
            response = await client.get(AUDIT_URL)
        assert response.status_code == 401, response.text


class TestTheHospitalFenceHolds(AuditTestCase):
    async def test_another_clinics_events_are_not_listed(self) -> None:
        mine = await self._guide(self.visit)
        theirs = await self._guide(self.foreign_visit)
        await GuideEvent.create(guide_document=mine, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id)
        await GuideEvent.create(
            guide_document=theirs, event_type=GuideEventType.APPROVED, actor_id=self.other_admin.staff_id
        )

        response = await self._get()
        visits = {row["visit_id"] for row in response.json()["entries"]}

        assert visits == {self.visit.visit_id}, f"옆집 진료가 섞였다: {visits}"

    async def test_each_clinic_sees_only_its_own(self) -> None:
        """옆집 관리자가 물으면 옆집 것만 — 울타리가 양방향인지 본다."""
        mine = await self._guide(self.visit)
        theirs = await self._guide(self.foreign_visit)
        await GuideEvent.create(guide_document=mine, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id)
        await GuideEvent.create(
            guide_document=theirs, event_type=GuideEventType.APPROVED, actor_id=self.other_admin.staff_id
        )

        response = await self._get(who="admin21")
        visits = {row["visit_id"] for row in response.json()["entries"]}

        assert visits == {self.foreign_visit.visit_id}, f"내 의원 진료가 섞였다: {visits}"

    async def test_the_otp_table_is_fenced_too(self) -> None:
        """**이 표만 조인이 없다** — 링크 id 를 모아 거는 길이라 따로 잰다."""
        mine, theirs = await self._guide(self.visit), await self._guide(self.foreign_visit)
        for guide, digest in ((mine, "b" * 64), (theirs, "c" * 64)):
            link = await PatientGuideLink.create(
                guide_document=guide,
                token_digest=digest,
                expires_at=self.base + timedelta(days=7),
                issued_by=self.doctor.staff_id,
            )
            await PatientOtpEvent.create(
                patient_guide_link_id=link.patient_guide_link_id, event_type=PatientOtpEventType.VERIFIED
            )

        response = await self._get({"source": "otp"})
        visits = {row["visit_id"] for row in response.json()["entries"]}

        assert visits == {self.visit.visit_id}, f"옆집 OTP 이벤트가 섞였다: {visits}"


class TestNothingSecretLeaks(AuditTestCase):
    async def test_no_token_phone_or_patient_name_in_the_response(self) -> None:
        """인수조건 — **링크 토큰·OTP 코드·환자 식별정보가 응답에 없다.**

        요약 문자열만 나간다. 담을 칸을 만들지 않았으므로 새어 나갈 자리가
        없지만, 계약이 바뀌면 그 순간 여기가 운다.
        """
        guide = await self._guide(self.visit)
        link = await PatientGuideLink.create(
            guide_document=guide,
            token_digest=SECRET_TOKEN_DIGEST,
            expires_at=self.base + timedelta(days=7),
            issued_by=self.doctor.staff_id,
        )
        await PatientOtpEvent.create(
            patient_guide_link_id=link.patient_guide_link_id, event_type=PatientOtpEventType.ISSUED
        )
        await GuideEvent.create(guide_document=guide, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id)
        await PatientUsageEvent.create(guide_document=guide, event_type=PatientUsageEventType.GUIDE_VIEWED)

        response = await self._get()
        body = response.text

        assert SECRET_TOKEN_DIGEST not in body, "링크 토큰 해시가 응답에 있다"
        assert SECRET_PHONE not in body, "환자 전화번호가 응답에 있다"
        assert SECRET_PATIENT_NAME not in body, "환자 이름이 응답에 있다"
        assert "token" not in body, "토큰이라는 칸이 응답에 있다"

    async def test_the_reason_a_person_typed_is_not_carried(self) -> None:
        """반려 사유는 사람이 적은 글이다 — 감사 목록에 그대로 실으면 그 목록이
        곧 사람이 쓴 문장의 사본이 된다. 요약은 서버가 짓는다."""
        guide = await self._guide(self.visit)
        await GuideEvent.create(
            guide_document=guide,
            event_type=GuideEventType.RETURNED,
            actor_id=self.doctor.staff_id,
            reason="환자 이름이 틀렸습니다 01044521234",
        )

        response = await self._get()
        entry = response.json()["entries"][0]

        assert "01044521234" not in response.text
        assert entry["summary"] == "안내문을 스탭에게 되돌렸습니다"


class TestAllFiveTablesLandInOneList(AuditTestCase):
    async def _one_of_each(self) -> None:
        guide = await self._guide(self.visit)
        event = await GuideEvent.create(
            guide_document=guide, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id
        )
        await _at(GuideEvent, "guide_event_id", event.guide_event_id, self.base + timedelta(minutes=1))

        link = await PatientGuideLink.create(
            guide_document=guide,
            token_digest=SECRET_TOKEN_DIGEST,
            expires_at=self.base + timedelta(days=7),
            issued_by=self.doctor.staff_id,
        )
        otp = await PatientOtpEvent.create(
            patient_guide_link_id=link.patient_guide_link_id, event_type=PatientOtpEventType.VERIFIED
        )
        await _at(PatientOtpEvent, "patient_otp_event_id", otp.patient_otp_event_id, self.base + timedelta(minutes=2))

        message = await GuideMessage.create(guide_document=guide, kind=GuideMessageKind.GUIDE, scheduled_at=self.base)
        sent = await GuideMessageEvent.create(guide_message=message, event_type=GuideMessageEventType.SENT)
        await _at(
            GuideMessageEvent, "guide_message_event_id", sent.guide_message_event_id, self.base + timedelta(minutes=3)
        )

        used = await PatientUsageEvent.create(guide_document=guide, event_type=PatientUsageEventType.GUIDE_VIEWED)
        await _at(
            PatientUsageEvent, "patient_usage_event_id", used.patient_usage_event_id, self.base + timedelta(minutes=4)
        )

        made = await StaffAccountEvent.create(
            hospital_id=self.hospital.hospital_id,
            actor_staff_id=self.admin.staff_id,
            subject_staff_id=self.doctor.staff_id,
            event_type=StaffAccountEventType.STAFF_CREATED,
            roles=["doctor"],
        )
        await _at(
            StaffAccountEvent, "staff_account_event_id", made.staff_account_event_id, self.base + timedelta(minutes=5)
        )

    async def test_five_sources_are_mixed_newest_first(self) -> None:
        await self._one_of_each()

        response = await self._get()
        entries = response.json()["entries"]

        assert [row["source"] for row in entries] == [
            "staff_account",
            "patient_usage",
            "message",
            "otp",
            "guide",
        ], [row["source"] for row in entries]
        times = [row["occurred_at"] for row in entries]
        assert times == sorted(times, reverse=True), "시간순이 아니다"

    async def test_every_row_says_what_happened_in_words(self) -> None:
        await self._one_of_each()

        response = await self._get()
        for row in response.json()["entries"]:
            assert row["summary"], f"{row['source']}/{row['event_type']} 이 빈 말을 한다"
            assert row["summary"] != row["event_type"], f"{row['event_type']} 이 사람 말로 안 옮겨졌다"

    async def test_the_actor_is_named(self) -> None:
        await self._one_of_each()

        response = await self._get({"source": "guide"})
        entry = response.json()["entries"][0]

        assert entry["actor_staff_id"] == self.doctor.staff_id
        assert entry["actor_name"] == "박연", "누가 했는지가 번호로만 남았다"

    async def test_what_the_patient_did_has_no_actor(self) -> None:
        await self._one_of_each()

        response = await self._get({"source": "patient_usage"})
        entry = response.json()["entries"][0]

        assert entry["actor_staff_id"] is None
        assert entry["actor_name"] is None


class TestEachFilterBites(AuditTestCase):
    async def test_the_source_filter(self) -> None:
        guide = await self._guide(self.visit)
        await GuideEvent.create(guide_document=guide, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id)
        await PatientUsageEvent.create(guide_document=guide, event_type=PatientUsageEventType.GUIDE_VIEWED)

        response = await self._get({"source": "guide"})
        sources = {row["source"] for row in response.json()["entries"]}

        assert sources == {"guide"}, sources

    async def test_the_actor_filter(self) -> None:
        """**행위자로 물으면 사람이 한 일만 온다.** 환자·발송기 이벤트에는
        행위자가 없으므로 섞이면 그 목록은 답이 아니다."""
        guide = await self._guide(self.visit)
        await GuideEvent.create(guide_document=guide, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id)
        await GuideEvent.create(guide_document=guide, event_type=GuideEventType.EDITED, actor_id=self.admin.staff_id)
        await PatientUsageEvent.create(guide_document=guide, event_type=PatientUsageEventType.GUIDE_VIEWED)

        response = await self._get({"actor_staff_id": self.doctor.staff_id})
        entries = response.json()["entries"]

        assert len(entries) == 1, entries
        assert entries[0]["actor_staff_id"] == self.doctor.staff_id
        assert entries[0]["event_type"] == "APPROVED"

    async def test_the_time_window(self) -> None:
        guide = await self._guide(self.visit)
        old = await GuideEvent.create(
            guide_document=guide, event_type=GuideEventType.GENERATED, actor_id=self.doctor.staff_id
        )
        new = await GuideEvent.create(
            guide_document=guide, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id
        )
        await _at(GuideEvent, "guide_event_id", old.guide_event_id, self.base)
        await _at(GuideEvent, "guide_event_id", new.guide_event_id, self.base + timedelta(days=2))

        response = await self._get({"occurred_from": (self.base + timedelta(days=1)).isoformat()})
        types = [row["event_type"] for row in response.json()["entries"]]
        assert types == ["APPROVED"], types

        response = await self._get({"occurred_to": (self.base + timedelta(days=1)).isoformat()})
        types = [row["event_type"] for row in response.json()["entries"]]
        assert types == ["GENERATED"], types

    async def test_the_visit_filter_is_a1_7(self) -> None:
        """인수조건 — **그 진료 건의 모든 유형이 시간순으로.**"""
        first, second = await self._guide(self.visit), await self._guide(self.second_visit)
        await GuideEvent.create(guide_document=first, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id)
        await PatientUsageEvent.create(guide_document=first, event_type=PatientUsageEventType.GUIDE_VIEWED)
        await GuideEvent.create(
            guide_document=second, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id
        )

        response = await self._get({"visit_id": self.visit.visit_id})
        entries = response.json()["entries"]

        assert {row["visit_id"] for row in entries} == {self.visit.visit_id}
        assert {row["source"] for row in entries} == {"guide", "patient_usage"}, "한 유형만 왔다 — 합치는 뜻이 없다"

    async def test_account_events_stay_out_of_a_visit(self) -> None:
        """계정 생성은 어느 진료의 일도 아니다 — 진료로 물으면 안 나온다."""
        guide = await self._guide(self.visit)
        await GuideEvent.create(guide_document=guide, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id)
        await StaffAccountEvent.create(
            hospital_id=self.hospital.hospital_id,
            actor_staff_id=self.admin.staff_id,
            subject_staff_id=self.doctor.staff_id,
            event_type=StaffAccountEventType.STAFF_CREATED,
            roles=["doctor"],
        )

        response = await self._get({"visit_id": self.visit.visit_id})
        sources = {row["source"] for row in response.json()["entries"]}

        assert "staff_account" not in sources, sources


class TestTheActorNameStaysInsideTheFence(AuditTestCase):
    """**이름도 울타리 안에서만 찾는다** (이희진 님 `#287` 리뷰 ⑤).

    `GuideEvent.actor_id` 는 FK 가 아니라 그냥 `BigIntField` 다. 어떤 사정으로
    남의 의원 직원 번호가 들어 있으면 그 사람 **이름이 이 목록에 뜬다.**
    실제로 그럴 일은 없어야 하지만, 없어야 하는 것과 못 하는 것은 다르다.
    """

    async def test_a_foreign_actor_name_is_not_revealed(self) -> None:
        guide = await self._guide(self.visit)
        await GuideEvent.create(
            guide_document=guide,
            event_type=GuideEventType.APPROVED,
            #: 옆집 의원 관리자의 번호. 우리 의원 사건에 붙어 있다.
            actor_id=self.other_admin.staff_id,
        )

        response = await self._get()
        entry = response.json()["entries"][0]

        assert "옆집관리자" not in response.text, "남의 의원 직원 이름이 새어 나온다"
        assert entry["actor_name"] is None, entry
        #: **줄은 남는다.** 「누가 했는지 모르는 일이 있었다」가 「아무 일도
        #: 없었다」보다 낫다.
        assert entry["actor_staff_id"] == self.other_admin.staff_id
        assert entry["summary"] == "안내문을 승인했습니다"

    async def test_our_own_actor_is_still_named(self) -> None:
        """울타리를 치면서 제 의원 이름까지 잃으면 안 된다."""
        guide = await self._guide(self.visit)
        await GuideEvent.create(guide_document=guide, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id)

        response = await self._get()
        assert response.json()["entries"][0]["actor_name"] == "박연"


class TestPagingIsStable(AuditTestCase):
    async def _many(self, count: int) -> None:
        guide = await self._guide(self.visit)
        for index in range(count):
            event = await GuideEvent.create(
                guide_document=guide, event_type=GuideEventType.EDITED, actor_id=self.doctor.staff_id
            )
            await _at(GuideEvent, "guide_event_id", event.guide_event_id, self.base + timedelta(minutes=index))

    async def test_walking_the_pages_sees_everything_once(self) -> None:
        await self._many(7)

        seen: list[str] = []
        cursor = None
        for _ in range(10):
            params: dict[str, Any] = {"limit": 3}
            if cursor:
                params["cursor"] = cursor
            page = (await self._get(params)).json()
            seen += [row["event_id"] for row in page["entries"]]
            cursor = page["next_cursor"]
            if not cursor:
                break

        assert len(seen) == 7, f"{len(seen)} 줄을 봤다"
        assert len(set(seen)) == 7, "같은 줄을 두 번 봤다"
        assert cursor is None, "끝났는데 다음 쪽 열쇠를 준다"

    async def test_the_same_cursor_gives_the_same_answer(self) -> None:
        """인수조건 — **동일 커서 재요청이 멱등하다.**"""
        await self._many(7)

        first = (await self._get({"limit": 3})).json()
        again = (await self._get({"limit": 3})).json()
        assert first == again, "첫 쪽이 두 번 다르다"

        cursor = first["next_cursor"]
        second = (await self._get({"limit": 3, "cursor": cursor})).json()
        second_again = (await self._get({"limit": 3, "cursor": cursor})).json()
        assert second == second_again, "같은 커서가 다른 답을 준다"

    async def test_a_made_up_cursor_is_refused(self) -> None:
        """조용히 첫 쪽을 주면 부르는 쪽은 그것을 다음 쪽이라 믿는다."""
        response = await self._get({"cursor": "손으로지어낸값"})
        assert response.status_code == 400, response.text
        assert response.json()["code"] == "INVALID_CURSOR"

    async def test_a_dozen_at_the_same_instant_still_page_cleanly(self) -> None:
        """**번호가 9 → 10 을 넘는 자리를 잰다.**

        처음에는 순서 열쇠가 `"guide:9"` 같은 문자열이었다. 문자열로 견주면
        `"guide:9" > "guide:10"` 이라 **열 번째 줄부터 순서가 뒤집힌다.** SQL 은
        번호를 숫자로 자르는데 파이썬은 글자로 줄을 세우니 둘이 어긋나, 어떤
        줄은 두 번 보이고 어떤 줄은 영영 안 보인다.

        시각을 모두 같게 두어 **번호만으로 갈리게** 만든다 — 시각이 다르면
        문자열이든 튜플이든 답이 같아서 이 결함이 안 드러난다(실제로 안 드러났다).
        """
        guide = await self._guide(self.visit)
        #: **번호를 손으로 못 박는다.** 자동 증가에 맡기면 두 자리 수부터 시작해
        #: `9 → 10` 경계를 안 지나고, 그러면 이 검사가 헛돈다(실제로 그랬다).
        made = list(range(5, 17))
        for pk in made:
            await GuideEvent.create(
                guide_event_id=pk,
                guide_document=guide,
                event_type=GuideEventType.EDITED,
                actor_id=self.doctor.staff_id,
            )
            await _at(GuideEvent, "guide_event_id", pk, self.base)

        seen: list[str] = []
        cursor = None
        for _ in range(20):
            params: dict[str, Any] = {"limit": 5}
            if cursor:
                params["cursor"] = cursor
            page = (await self._get(params)).json()
            seen += [row["event_id"] for row in page["entries"]]
            cursor = page["next_cursor"]
            if not cursor:
                break

        assert made[0] < 10 < made[-1], "번호가 9 → 10 을 안 지난다 — 이 검사가 헛돈다"
        assert len(seen) == 12, f"{len(seen)} 줄을 봤다 — {seen}"
        assert len(set(seen)) == 12, f"같은 줄을 두 번 봤다 — {sorted(seen)}"
        assert seen == [f"guide:{pk}" for pk in sorted(made, reverse=True)], f"번호 순서가 뒤집혔다 — {seen}"

    async def test_the_last_page_says_it_is_the_last(self) -> None:
        await self._many(3)
        page = (await self._get({"limit": 10})).json()
        assert page["has_more"] is False
        assert page["next_cursor"] is None


class TestReadingWritesNothing(AuditTestCase):
    async def test_the_counts_do_not_move(self) -> None:
        """인수조건 — **조회는 append-only 저장에 어떤 쓰기도 하지 않는다.**"""
        guide = await self._guide(self.visit)
        await GuideEvent.create(guide_document=guide, event_type=GuideEventType.APPROVED, actor_id=self.doctor.staff_id)
        await PatientUsageEvent.create(guide_document=guide, event_type=PatientUsageEventType.GUIDE_VIEWED)

        async def counts() -> dict[str, int]:
            return {
                "guide": await GuideEvent.all().count(),
                "usage": await PatientUsageEvent.all().count(),
                "otp": await PatientOtpEvent.all().count(),
                "message": await GuideMessageEvent.all().count(),
                "account": await StaffAccountEvent.all().count(),
                "staff": await Staff.all().count(),
            }

        before = await counts()
        await self._get()
        await self._get({"visit_id": self.visit.visit_id})
        await self._get({"source": "guide"})
        assert await counts() == before, "읽기만 했는데 무언가 바뀌었다"

    async def test_the_service_never_calls_a_write(self) -> None:
        """규칙으로도 못 박는다 — 나중에 「읽으면서 표시해 두자」가 들어오는 것을
        막는다. 감사 기록을 읽는 길이 쓰는 길을 겸하면 그것은 감사 기록이 아니다.
        """
        from pathlib import Path

        source = Path(__file__).parents[3] / "app" / "services" / "admin_audit.py"
        code = source.read_text(encoding="utf-8")
        body = "\n".join(line for line in code.splitlines() if not line.strip().startswith("#"))

        for forbidden in (".create(", ".save(", ".update(", ".delete(", "in_transaction"):
            assert forbidden not in body, f"조회 서비스가 {forbidden} 를 부른다"
