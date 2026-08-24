"""안내문 승인·반려가 규칙대로 도는가 — KEY-111 (`KEY-76` 인수조건).

여기서 지키려는 것은 대부분 **막는 일**이라 눈으로 확인하기 어렵다.
그래서 하나씩 검사로 못 박는다.

`KEY-87`(유가은)이 감사 이벤트의 내용과 재승인 흐름을 더 깊게 볼 예정이라,
이 파일은 **API 단위의 정상·예외까지만** 본다.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    Visit,
)
from app.services.guides import GuideService
from app.services.session_store import SessionStore
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

#: 병원 표시 시간대. 발송 시각은 이 시간대로 재야 뜻이 맞는다(계약 §4).
SEOUL = ZoneInfo("Asia/Seoul")

BASE = "/api/v1/visits"


async def make_clinic(name: str = "여성의원") -> Hospital:
    return await Hospital.create(name=name)


async def make_staff(hospital: Hospital, login_id: str, roles: list[str]) -> Staff:
    return await Staff.create(
        hospital=hospital,
        login_id=login_id,
        password_hash=hash_password("Password123!"),
        name="합성직원",
        roles=roles,
        must_change_password=False,
    )


async def make_guide(hospital: Hospital, status: GuideStatus = GuideStatus.APPROVAL_PENDING) -> GuideDocument:
    patient = await Patient.create(
        hospital_id=hospital.hospital_id,
        hospital_patient_no="SYN-12345",
        name="합성환자",
        birth_date="1990-01-01",
        phone="01044524085",
        sms_consent=True,
    )
    visit = await Visit.create(
        hospital_id=hospital.hospital_id,
        patient=patient,
        visited_at="2026-08-13T01:32:00+00:00",
    )
    guide = await GuideDocument.create(
        hospital_id=hospital.hospital_id,
        visit=visit,
        status=status,
    )
    await GuideSection.create(
        guide_document=guide,
        section_key=GuideSectionKey.MEDICATION,
        generated_body="합성 복약지도 본문",
        warn="합성 확인 부탁 문구",
    )
    await GuideSection.create(
        guide_document=guide,
        section_key=GuideSectionKey.CAUTION,
        # 일반 주의 문구. **잠그지 않는다** — 원장님이 환자에 맞춰 고치는 자리다.
        generated_body="합성 주의사항 본문",
    )
    await GuideSection.create(
        guide_document=guide,
        section_key=GuideSectionKey.EMERGENCY,
        # 🚨 응급 문장. 식약처 정보 기준이라 사람이 고칠 수 없다.
        generated_body="합성 응급 연락 문장",
        locked=True,
    )
    return guide


class GuideTestCase(TestCase):
    """토큰을 만드는 쪽과 앱이 보는 쪽이 **같은 Redis** 여야 한다.

    처음에는 `sign_in()` 안에서만 `FakeRedis()` 를 새로 만들었다. 그러면 토큰의
    `jti` 는 그 일회용 저장소에만 남고, 앱은 `get_redis` 로 **진짜 Redis** 에
    붙는다. 결과가 둘이었다.

      * CI 에는 Redis 서비스가 없어서 15건이 통째로 연결 오류로 죽었다.
      * 로컬은 도커 Redis 가 떠 있어 통과했는데, 폐기 여부를 **다른 저장소에서**
        확인하고 있었다 — 초록불인데 아무것도 안 보는 상태였다.

    그래서 인스턴스 하나를 만들어 토큰 발급과 앱 양쪽에 물린다.
    """

    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def sign_in(self, staff: Staff) -> dict[str, str]:
        """로그인을 거치지 않고 토큰을 만든다.

        이 검사가 보려는 것은 **승인 규칙**이지 로그인이 아니다. 로그인 계약이
        바뀔 때마다 상관없는 검사가 함께 깨지면 무엇이 진짜 고장인지 안 보인다.
        """
        access, _ = await StaffSessionService(self.redis).start(staff, False)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestOnlyDoctorsApprove(GuideTestCase):
    """`admin` 은 역할이 아니라 권한이다 — 켠다고 의료 판단이 열리지 않는다."""

    async def _try_approve(self, roles: list[str], login_id: str) -> Any:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        staff = await make_staff(clinic, login_id, roles)

        async with self.client() as client:
            return await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=await self.sign_in(staff))

    async def test_a_doctor_can_approve(self) -> None:
        response = await self._try_approve(["doctor"], "doctor01")
        assert response.status_code == 200
        assert response.json()["status"] == GuideStatus.SCHEDULED_TO_SEND

    async def test_a_staff_cannot(self) -> None:
        response = await self._try_approve(["staff"], "staff01")
        assert response.status_code == 403

    async def test_an_admin_alone_cannot(self) -> None:
        """운영 권한만으로는 안내문을 환자에게 내보낼 수 없다."""
        response = await self._try_approve(["admin"], "admin01")
        assert response.status_code == 403

    async def test_a_staff_who_is_also_admin_cannot(self) -> None:
        response = await self._try_approve(["staff", "admin"], "adminstaff01")
        assert response.status_code == 403

    async def test_a_doctor_who_is_also_admin_can(self) -> None:
        """admin 을 겸해도 의사는 의사다 — admin 이 승인을 방해하지 않는다."""
        response = await self._try_approve(["doctor", "admin"], "admindoc01")
        assert response.status_code == 200


class TestApprovalSchedulesTheSend(GuideTestCase):
    """승인이 곧 발송 예약이다 — 스탭이 발송 버튼을 누르지 않는다(D1-5)."""

    async def test_approving_fills_the_schedule(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=await self.sign_in(doctor))

        body = response.json()
        assert body["status"] == GuideStatus.SCHEDULED_TO_SEND
        assert body["approved_at"], "누가 언제 승인했는지가 비어 있다"
        assert body["scheduled_at"], "승인했는데 발송 예정 시각이 없다"

        saved = await GuideDocument.get(guide_document_id=guide.guide_document_id)
        assert saved.approved_by == doctor.staff_id

        # 있는지가 아니라 **몇 시인지**를 잰다. 이걸 안 재서 예약이 UTC 18시로
        # 잡히던 것을 놓쳤다 — 한국에서는 다음 날 새벽 3시였다(`#50` 리뷰).
        assert saved.scheduled_at is not None
        local = saved.scheduled_at.astimezone(SEOUL)
        assert local.hour == 18, f"병원 시간으로 18시여야 한다 (받은 값 {local})"
        assert (local.minute, local.second) == (0, 0), f"정각이어야 한다 (받은 값 {local})"

    async def test_the_send_time_is_measured_in_clinic_time(self) -> None:
        """UTC 로 재면 18시가 아니다.

        `use_tz: True` 라 `tortoise.timezone.now()` 는 늘 UTC 를 돌려준다.
        시간대를 안 옮기고 `replace(hour=18)` 하면 UTC 18시가 되고, 한국에서는
        **다음 날 새벽 3시**다. 환자가 복약 안내를 자다가 받는다.
        """
        morning = datetime(2026, 8, 20, 4, 50, tzinfo=UTC)  # 한국 13:50
        evening = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)  # 한국 19:00 — 이미 지났다
        midnightish = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)  # 한국 23:30

        picked = {
            label: GuideService._send_at(m).astimezone(SEOUL)
            for label, m in (("낮", morning), ("저녁", evening), ("밤", midnightish))
        }

        for label, at in picked.items():
            assert at.hour == 18, f"{label}에 승인했는데 {at.hour}시로 잡혔다 ({at})"

        assert picked["낮"].date() == date(2026, 8, 20), "낮에 승인하면 그날 저녁이다"
        assert picked["저녁"].date() == date(2026, 8, 21), "18시가 지난 뒤면 다음 날이어야 한다"
        assert picked["밤"].date() == date(2026, 8, 21), "밤도 다음 날이다"

    async def test_approving_twice_is_refused(self) -> None:
        """두 번 승인을 조용히 넘기면 발송 예정 시각이 밀린다."""
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            first = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=headers)
            again = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=headers)

        assert first.status_code == 200
        assert again.status_code == 409
        assert again.json()["code"] == "ALREADY_APPROVED"

    async def test_a_draft_cannot_be_approved(self) -> None:
        """스탭이 아직 확인 중인 것을 건너뛰어 승인할 수 없다."""
        clinic = await make_clinic()
        guide = await make_guide(clinic, status=GuideStatus.STAFF_REVIEW)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=await self.sign_in(doctor))

        assert response.status_code == 409
        assert response.json()["code"] == "GUIDE_NOT_PENDING"


class TestReturnNeedsAReason(GuideTestCase):
    """사유가 스탭 알림에 그대로 뜬다 — 비어 있으면 무엇을 고칠지 모른다."""

    async def test_a_reason_is_required(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            empty = await client.post(f"{BASE}/{guide.visit_id}/guide/return", json={"reason": "   "}, headers=headers)
            missing = await client.post(f"{BASE}/{guide.visit_id}/guide/return", json={}, headers=headers)

        assert empty.status_code == 422
        assert missing.status_code == 422

    async def test_the_reason_is_kept(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.post(
                f"{BASE}/{guide.visit_id}/guide/return",
                json={"reason": "진료기록 재업로드 필요"},
                headers=await self.sign_in(doctor),
            )

        assert response.status_code == 200
        assert response.json()["status"] == GuideStatus.APPROVAL_RETURNED
        assert response.json()["returned_reason"] == "진료기록 재업로드 필요"

        event = await GuideEvent.filter(guide_document_id=guide.guide_document_id).first()
        assert event is not None
        assert event.event_type is GuideEventType.RETURNED
        assert event.reason == "진료기록 재업로드 필요", "이력에 사유가 안 남으면 나중에 되짚을 수 없다"


class TestHistoryIsKept(GuideTestCase):
    """상태만 바뀌고 이력이 비면 「누가 내보냈나」에 답할 수 없다."""

    async def test_approving_leaves_a_trace(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=await self.sign_in(doctor))

        events = await GuideEvent.filter(guide_document_id=guide.guide_document_id)
        assert len(events) == 1
        assert events[0].event_type is GuideEventType.APPROVED
        assert events[0].actor_id == doctor.staff_id

    async def test_editing_leaves_a_trace_and_keeps_the_original(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.patch(
                f"{BASE}/{guide.visit_id}/guide/sections/medication",
                json={"body": "원장님이 고친 본문"},
                headers=await self.sign_in(doctor),
            )

        assert response.status_code == 200
        assert response.json()["body"] == "원장님이 고친 본문"
        assert response.json()["edited"] is True

        section = await GuideSection.get(
            guide_document_id=guide.guide_document_id, section_key=GuideSectionKey.MEDICATION
        )
        assert section.generated_body == "합성 복약지도 본문", "생성 원문이 지워졌다 — 다음 초안 개선에 쓸 수 없다"

        event = await GuideEvent.filter(guide_document_id=guide.guide_document_id).first()
        assert event is not None
        assert event.event_type is GuideEventType.EDITED
        assert event.section_key is GuideSectionKey.MEDICATION


class TestLockedSectionStaysLocked(GuideTestCase):
    """🚨 응급 문장은 식약처 정보 기준이라 사람이 고칠 수 없다(D1-2).

    KEY-161 로 잠금이 `caution` 에서 `emergency` 로 옮겨 갔다. **두 검사를 함께
    둔다** — 응급이 막히는 것만 보면, 실수로 `caution` 까지 잠근 코드도 통과한다.
    """

    async def test_editing_the_emergency_line_is_refused(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.patch(
                f"{BASE}/{guide.visit_id}/guide/sections/emergency",
                json={"body": "고쳐 보겠습니다"},
                headers=await self.sign_in(doctor),
            )

        assert response.status_code == 409
        assert response.json()["code"] == "SECTION_LOCKED"

    async def test_the_general_caution_is_still_editable(self) -> None:
        """일반 주의 문구는 고쳐진다 — 잠금이 옆칸으로 번지지 않았다."""
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.patch(
                f"{BASE}/{guide.visit_id}/guide/sections/caution",
                json={"body": "환자분께 맞춰 고친 주의 문구"},
                headers=await self.sign_in(doctor),
            )

        assert response.status_code == 200, "일반 주의 문구가 막혔다 — KEY-161 이 풀려던 자리다"
        assert response.json()["body"] == "환자분께 맞춰 고친 주의 문구"
        assert response.json()["locked"] is False

    async def test_the_emergency_body_survives_an_edit_attempt(self) -> None:
        """막은 뒤에도 **원문이 그대로**다.

        409 만 재면, 거절하면서 본문을 덮어쓰는 코드를 못 잡는다. 응급 문장은
        완화·누락되면 안 되는 문장이라 값 자체를 확인한다.
        """
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            await client.patch(
                f"{BASE}/{guide.visit_id}/guide/sections/emergency",
                json={"body": "덮어써 보겠습니다"},
                headers=await self.sign_in(doctor),
            )
            read = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=await self.sign_in(doctor))

        sections = {s["key"]: s for s in read.json()["sections"]}
        assert sections[GuideSectionKey.EMERGENCY]["body"] == "합성 응급 연락 문장"
        assert sections[GuideSectionKey.EMERGENCY]["edited"] is False


class TestOtherClinicIsHidden(GuideTestCase):
    """타 병원 것은 `403` 이 아니라 `404` 다 — 존재 여부를 감춘다(계약 §5)."""

    async def test_it_answers_not_found(self) -> None:
        mine = await make_clinic("우리의원")
        theirs = await make_clinic("옆의원")
        guide = await make_guide(theirs)
        doctor = await make_staff(mine, "doctor01", ["doctor"])

        async with self.client() as client:
            headers = await self.sign_in(doctor)
            read = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=headers)
            approve = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=headers)

        assert read.status_code == 404
        assert approve.status_code == 404, "남의 의원 것을 승인 시도했을 때 403 이면 존재가 새어 나간다"


class TestReadingTheGuide(GuideTestCase):
    async def test_it_returns_what_the_screen_needs(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=await self.sign_in(doctor))

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == GuideStatus.APPROVAL_PENDING
        keys = [s["key"] for s in body["sections"]]
        assert keys == [
            GuideSectionKey.MEDICATION,
            GuideSectionKey.CAUTION,
            GuideSectionKey.EMERGENCY,
        ], "차례까지 계약이다 — 응급 문장은 주의 문구 **바로 뒤**에 온다"

        medication = body["sections"][0]
        assert medication["warn"] == "합성 확인 부탁 문구", "⚠ 는 서버가 판정한다 — 화면이 알 수 없다"
        assert body["sections"][1]["locked"] is False, "일반 주의 문구는 잠기지 않는다"
        assert body["sections"][2]["locked"] is True


class TestTheScreenKnowsWhoseGuideItIs(GuideTestCase):
    """머리에 환자가 서야 한다.

    승인은 곧 그 환자에게 발송이다. 화면에 이름 없이 본문만 뜨면 원장님은
    **누구 것인지 모르고 누르게 된다.** `#48` 화면이 목업으로 이 자리를 채우고
    있었는데 서버가 주지 않아, 목업을 끄면 머리가 빈다.
    """

    async def test_the_head_carries_the_patient(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=await self.sign_in(doctor))

        head = response.json()["patient"]
        assert head["name"] == "합성환자"
        assert head["hospital_patient_no"] == "SYN-12345"
        assert head["birth_date"] == "1990-01-01"

    async def test_the_phone_never_rides_along(self) -> None:
        """발송 번호는 서버가 안다. 승인할 때마다 화면과 로그를 지날 이유가 없다."""
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        async with self.client() as client:
            response = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=await self.sign_in(doctor))

        assert "01044524085" not in response.text, "안내문 응답에 환자 전화번호가 실렸다"

    async def test_age_is_counted_not_stored(self) -> None:
        """계약 §4 — `age` 는 저장값이 아니라 **조회 시점의 현지 날짜**로 센다.

        생일이 아직 안 지난 환자를 하나 만들어, 한 살을 빼는지까지 본다. 여기서
        구현과 같은 식을 다시 쓰면 검사가 자기 자신을 확인하게 되므로, **날짜를
        오늘에서 만들어** 기대값을 사람이 셀 수 있게 둔다.
        """
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        tomorrow = today + timedelta(days=1)

        clinic = await make_clinic()
        guide = await make_guide(clinic)
        # 생일이 내일인 서른 살 — 오늘 기준으로는 아직 스물아홉이다.
        not_yet = tomorrow.replace(year=tomorrow.year - 30)
        visit = await Visit.get(visit_id=guide.visit_id).prefetch_related("patient")
        visit.patient.birth_date = not_yet
        await visit.patient.save(update_fields=["birth_date"])

        doctor = await make_staff(clinic, "doctor01", ["doctor"])
        async with self.client() as client:
            response = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=await self.sign_in(doctor))

        assert response.json()["patient"]["age"] == 29, "생일이 안 지났으면 한 살 뺀다"


class TestRevokedSessionCannotReachTheGuide(GuideTestCase):
    """세션을 끊으면 안내문에도 못 닿는다.

    이 검사가 여기 있는 이유는 승인 규칙이 아니라 **배선**이다. 토큰을 만든
    Redis 와 앱이 보는 Redis 가 다르면 폐기해도 통과한다 — 실제로 그랬다.
    여기가 빨간불이면 `get_redis` 재정의가 풀린 것이다.
    """

    async def test_it_is_refused_after_the_session_is_revoked(self) -> None:
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "doctor01", ["doctor"])
        guide = await make_guide(clinic)
        headers = await self.sign_in(doctor)

        async with self.client() as client:
            before = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=headers)

            await SessionStore(self.redis).revoke_all(doctor.staff_id)  # type: ignore[arg-type]

            after = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=headers)

        assert before.status_code == 200, "끊기 전에는 열려야 한다"
        assert after.status_code == 401, "세션을 끊었는데 통과했다 — 토큰을 만든 Redis 와 앱이 보는 Redis 가 다르다"


class TestTheDecisionIsReadUnderALock(GuideTestCase):
    """승인·반려·수정이 **잠근 채로** 상태를 읽는지 본다 — `#50` 리뷰.

    예전에는 `get()` 으로 읽고 확인한 **뒤에** 트랜잭션을 열었다. 그 사이가
    비어 있어서 승인과 반려가 동시에 들어오면 둘 다 `APPROVAL_PENDING` 을
    읽고 둘 다 통과할 수 있었다 — 승인 이벤트와 반려 이벤트가 함께 남고,
    **의사가 승인한 것과 실제로 나가는 것이 달라진다.**

    ⚠️ **진짜 동시 요청은 이 하네스에서 못 만든다.** `tortoise.contrib.test.
    TestCase` 가 검사 하나를 트랜잭션으로 감싸고 커넥션 하나를 공유해서,
    두 요청을 `asyncio.gather` 로 보내면 MySQL 소켓에서 먼저 깨진다
    (`readexactly() called while another coroutine is already waiting`).

    그래서 **경합을 재현하는 대신 잠금이 걸리는지를 잰다.** 두 가지다.
      ① 읽는 질의에 `FOR UPDATE` 가 붙는가
      ② 결정을 두 번 하면 두 번째가 409 인가 (순차)

    ①이 빠지면 ②는 통과하면서도 동시 요청은 뚫린다 — 그래서 둘 다 본다.
    """

    async def test_the_read_takes_a_row_lock(self) -> None:
        """`_lock()` 이 실제로 행을 잠그는지 본다.

        직접 만든 질의에 `.select_for_update()` 를 붙여 SQL 을 보는 것으로는
        모자란다 — 그건 Tortoise 를 시험하는 것이지 이 서비스를 시험하는 게
        아니다. `_lock()` 에서 그 호출이 빠져도 통과해 버린다.
        """
        import inspect

        source = inspect.getsource(GuideService._lock)
        assert "select_for_update()" in source, "`_lock()` 이 행을 잠그지 않고 읽는다"

        # 그 호출이 만드는 SQL 이 정말 `FOR UPDATE` 인지도 함께 확인한다.
        sql = GuideDocument.filter(visit_id=1).select_for_update().sql()
        assert "FOR UPDATE" in sql.upper(), f"select_for_update() 가 잠금을 만들지 않는다 — {sql}"

    async def test_the_service_reads_inside_the_transaction(self) -> None:
        """읽는 자리가 트랜잭션 밖으로 나가면 잠금이 의미를 잃는다.

        `approve` · `return_to_staff` · `edit_section` 이 모두 `_lock()` 을
        `in_transaction()` 블록 **안에서** 부르는지 원문으로 확인한다.
        """
        import inspect

        for name in ("approve", "return_to_staff", "edit_section"):
            body = inspect.getsource(getattr(GuideService, name))
            assert "self._lock(" in body, f"{name} 이 잠그지 않고 읽는다"
            opened = body.index("in_transaction()")
            locked = body.index("self._lock(")
            assert opened < locked, f"{name} 이 트랜잭션을 열기 전에 읽는다 — 그 사이가 비어 있다"

    async def test_generate_reads_under_a_lock(self) -> None:
        """`generate` 도 잠근 채로 중복을 확인하는지 본다.

        `generate` 는 `_lock()` 대신 `select_for_update()` 를 인라인으로 쓴다.
        순차 중복(409)만으로는 모자라다 — 위 클래스 docstring 참고.
          ① `in_transaction()` 블록 **안에서** `select_for_update()` 를 부르는가
          ② 그 순서가 바뀌면(트랜잭션 밖에서 잠금) 잠금이 의미를 잃는다
        """
        import inspect

        body = inspect.getsource(GuideService.generate)
        assert "select_for_update()" in body, "generate 가 잠그지 않고 중복을 확인한다"
        opened = body.index("in_transaction()")
        locked = body.index("select_for_update()")
        assert opened < locked, "generate 가 트랜잭션을 열기 전에 잠근다 — 그 사이가 비어 있다"

    async def test_a_second_decision_is_refused(self) -> None:
        clinic = await make_clinic()
        doctor = await make_staff(clinic, "doctor01", ["doctor"])
        guide = await make_guide(clinic)
        headers = await self.sign_in(doctor)

        async with self.client() as client:
            first = await client.post(f"{BASE}/{guide.visit_id}/guide/approve", headers=headers)
            second = await client.post(
                f"{BASE}/{guide.visit_id}/guide/return",
                headers=headers,
                json={"reason": "검사 수치를 다시 확인해 주세요"},
            )

        decisions = [
            event
            for event in await GuideEvent.filter(guide_document=guide).all()
            if event.event_type in (GuideEventType.APPROVED, GuideEventType.RETURNED)
        ]

        assert first.status_code == 200
        assert second.status_code == 409
        assert len(decisions) == 1, "결정 기록이 둘 남았다 — 상태와 기록이 어긋난다"


class TestTheOrderComesFromTheContract(GuideTestCase):
    """차례를 **삽입 순서에 맡기지 않는다** — KEY-161.

    예전에는 `guide_section_id` 로 정렬했다. 지금 생성 경로가 계약 순서대로
    넣으니 결과가 같아서 **우연히 맞는 것**을 계약이라 착각하기 쉽다.

    행 하나를 나중에 끼워 넣으면(기존 안내문에 `emergency` 를 채워 넣는
    backfill 이 그렇다) 그 행의 `id` 가 가장 커서 **응급 문장이 문자 설정
    뒤로 밀린다.** 그래서 일부러 거꾸로 심고 잰다.
    """

    async def test_a_late_inserted_section_still_lands_in_its_place(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        # `make_guide()` 는 medication · caution · emergency 를 심는다.
        # 나머지 둘을 **뒤에** 붙여도 차례는 계약을 따라야 한다.
        await GuideSection.create(
            guide_document=guide,
            section_key=GuideSectionKey.MESSAGES,
            generated_body="합성 문자 설정 본문",
        )
        await GuideSection.create(
            guide_document=guide,
            section_key=GuideSectionKey.LIFE,
            generated_body="합성 생활 안내 본문",
        )

        async with self.client() as client:
            response = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=await self.sign_in(doctor))

        assert [s["key"] for s in response.json()["sections"]] == [
            GuideSectionKey.MEDICATION,
            GuideSectionKey.CAUTION,
            GuideSectionKey.EMERGENCY,
            GuideSectionKey.LIFE,
            GuideSectionKey.MESSAGES,
        ], "심은 순서가 그대로 나왔다 — 차례를 DB 가 정하고 있다"


class TestCautionEmergencySeparation(GuideTestCase):
    """시드 경로에서도 주의/응급이 **두 행**인가 — KEY-150 이희진 코멘트, KEY-161.

    `make_guide()` 는 DB 를 직접 심는 경로다. 여기서 한 행으로 뭉쳐 두면
    잠금 회귀 검사들이 실제와 다른 데이터를 보게 된다.
    generate() API 경로 검증은 test_guide_generate.py 에 있다.
    """

    async def test_seed_keeps_them_apart(self) -> None:
        clinic = await make_clinic()
        guide = await make_guide(clinic)
        await guide.fetch_related("sections")

        sections = {s.section_key: s for s in guide.sections}
        assert GuideSectionKey.EMERGENCY in sections, "응급 문장이 별도 행으로 심기지 않았다"
        assert sections[GuideSectionKey.EMERGENCY].locked is True
        assert sections[GuideSectionKey.CAUTION].locked is False
        assert sections[GuideSectionKey.MEDICATION].locked is False
