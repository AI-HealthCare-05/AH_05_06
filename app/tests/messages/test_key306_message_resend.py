"""KEY-306 message-history resend API regression tests."""

import asyncio
from datetime import date, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TruncationTestCase
from tortoise.timezone import now

from app.core.redis_client import get_redis
from app.core.utils.security import hash_password
from app.main import app
from app.models.patients import Patient, PatientGender
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideMessage,
    GuideMessageKind,
    GuideMessageStatus,
    GuideStatus,
    PatientGuideLink,
    PatientOtpChallenge,
    Visit,
)
from app.services.message_dispatch import _body_for_storage, _finish_failed, _finish_sent
from app.services.patient_links import PatientLinkService, digest_link_token
from app.services.sms_sender import SmsDeliveryStatus, SmsProvider, SmsSendResult
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

#: secrets.token_urlsafe(32)와 같은 길이(43자)로 맞춘다 — 마스킹 정규식이
#: 정확한 길이만 보므로(경계 추측 대신), 실제보다 짧은 합성 문자열을 쓰면
#: test_a_sent_message_never_stores_the_raw_link_token 같은 검사가 매칭
#: 자체가 안 되는 채로 통과해 버린다.
OLD_LINK_TOKEN = "synthetic-old-link-token-43-chars-long-xxxx"
assert len(OLD_LINK_TOKEN) == 43, f"OLD_LINK_TOKEN이 43자가 아니다: {len(OLD_LINK_TOKEN)}"


class MessageResendTestCase(TruncationTestCase):
    async def _setUpDB(self) -> None:  # noqa: N802 — tortoise가 정한 이름 그대로 override한다.
        await super()._setUpDB()
        # 여기서 미리 잡아 둔다 — 이 시점엔 테스트가 쓸 연결이 확실히
        # 서 있다(_setUpDB()의 존재 이유 자체가 그거다). _tearDownDB()
        # 시점에 새로 조회하면 pytest-xdist(-n auto)에서 가끔 레지스트리가
        # 비어 KeyError가 났다(로컬 단일 프로세스에서는 재현 안 됨) —
        # 원인을 못 좁혀서, 대신 확실히 되는 시점의 참조를 그대로 들고
        # 있다가 나중에 재사용한다.
        self._db_connection = PatientGuideLink._meta.db

    async def _tearDownDB(self) -> None:  # noqa: N802 — tortoise가 정한 이름 그대로 override한다.
        # tortoise.contrib.test.truncate_all_models()는 모델 등록 순서로
        # 테이블을 지운다(자기 docstring이 "non-cascade foreign keys에서
        # 실패할 수 있다"고 적어 둔 그대로) — patient가 visit보다 먼저
        # 지워지려 들면 ON DELETE RESTRICT에 막힌다. 이 저장소에서
        # TruncationTestCase를 쓰는 파일이 이 파일뿐이라(동시 요청
        # 검사에 실제 커밋이 필요해서) 지금까지 안 드러났던 문제다.
        # FK 검사를 잠깐 끄고 지운 뒤 되살린다 — 순서를 일일이 안
        # 맞춰도 된다.
        connection = getattr(self, "_db_connection", None)
        if connection is None:
            # _setUpDB()에서 못 잡았다면(있을 수 없지만) 이 우회 자체를
            # 포기한다 — 최악의 경우 원래 있던 FK 문제로 돌아갈 뿐,
            # 매번 실패하는 새 문제를 만들지는 않는다.
            await super()._tearDownDB()
            return

        await connection.execute_script("SET FOREIGN_KEY_CHECKS=0")
        try:
            await super()._tearDownDB()
        finally:
            await connection.execute_script("SET FOREIGN_KEY_CHECKS=1")

    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def a_hospital(self, name: str) -> Hospital:
        return await Hospital.create(name=name)

    async def a_staff(self, hospital: Hospital, role: str, login_id: str) -> Staff:
        return await Staff.create(
            hospital=hospital,
            login_id=login_id,
            password_hash=hash_password("synthetic-password"),
            name="합성 사용자",
            roles=[role],
            must_change_password=False,
        )

    async def headers(self, staff: Staff) -> dict[str, str]:
        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        return {"Authorization": f"Bearer {access}"}

    async def a_sent_message(self, hospital: Hospital) -> GuideMessage:
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no="SYN-306",
            name="합성 환자",
            birth_date=date(1990, 1, 1),
            gender=PatientGender.FEMALE,
            phone="01000000000",
        )
        visit = await Visit.create(hospital_id=hospital.hospital_id, patient=patient, visited_at=now())
        guide = await GuideDocument.create(
            hospital_id=hospital.hospital_id,
            visit=visit,
            status=GuideStatus.SCHEDULED_TO_SEND,
            approved_at=now(),
        )
        return await GuideMessage.create(
            guide_document=guide,
            kind=GuideMessageKind.GUIDE,
            status=GuideMessageStatus.SENT,
            scheduled_at=now() - timedelta(minutes=1),
            sent_at=now(),
        )

    async def an_active_link(self, message: GuideMessage) -> tuple[PatientGuideLink, PatientOtpChallenge]:
        link = await PatientGuideLink.create(
            guide_document_id=message.guide_document_id,
            token_digest=digest_link_token(OLD_LINK_TOKEN),
            expires_at=now() + timedelta(hours=72),
            issued_by=0,
            issued_at=now(),
            last_message_id=message.guide_message_id,
        )
        challenge = await PatientOtpChallenge.create(
            patient_guide_link=link,
            otp_digest="0" * 64,
            otp_salt="0" * 32,
            expires_at=now() + timedelta(minutes=3),
            issued_at=now(),
        )
        return link, challenge

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def resend(self, staff: Staff, message_id: int):
        async with self.client() as client:
            return await client.post(
                f"/api/v1/messages/history/{message_id}/resend",
                headers=await self.headers(staff),
            )

    async def test_staff_request_revokes_the_active_link_and_otp(self) -> None:
        hospital = await self.a_hospital("합성 병원")
        staff = await self.a_staff(hospital, "staff", "key306-staff")
        source = await self.a_sent_message(hospital)
        link, challenge = await self.an_active_link(source)

        response = await self.resend(staff, source.guide_message_id)

        assert response.status_code == 202, response.text
        assert set(response.json()) == {"guide_message_id", "status"}
        assert response.json()["status"] == "SCHEDULED"

        replacement = await GuideMessage.get(guide_message_id=response.json()["guide_message_id"])
        assert replacement.resend_of_message_id == source.guide_message_id
        assert replacement.resend_sequence == 1
        assert replacement.kind is source.kind

        await link.refresh_from_db()
        await challenge.refresh_from_db()
        assert link.token_digest != digest_link_token(OLD_LINK_TOKEN)
        assert link.expires_at <= now()
        assert challenge.expires_at <= now()
        assert challenge.consumed_at is not None

        event = await GuideEvent.get(
            guide_document_id=source.guide_document_id,
            event_type=GuideEventType.LINK_REVOKED,
        )
        assert event.actor_id == staff.staff_id
        assert event.reason == "RESEND_REQUESTED"
        assert OLD_LINK_TOKEN not in response.text
        assert OLD_LINK_TOKEN not in (event.reason or "")

    async def test_doctor_can_request_a_resend(self) -> None:
        hospital = await self.a_hospital("의사 권한 병원")
        doctor = await self.a_staff(hospital, "doctor", "key306-doctor")
        source = await self.a_sent_message(hospital)

        response = await self.resend(doctor, source.guide_message_id)

        assert response.status_code == 202, response.text

    async def test_admin_only_role_is_forbidden(self) -> None:
        hospital = await self.a_hospital("관리자 권한 병원")
        admin = await self.a_staff(hospital, "admin", "key306-admin")
        source = await self.a_sent_message(hospital)

        response = await self.resend(admin, source.guide_message_id)

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
        assert await GuideMessage.filter(resend_of_message_id=source.guide_message_id).count() == 0

    async def test_another_hospital_sees_the_same_not_found_as_a_missing_row(self) -> None:
        owner_hospital = await self.a_hospital("소유 병원")
        other_hospital = await self.a_hospital("다른 병원")
        other_staff = await self.a_staff(other_hospital, "staff", "key306-other")
        source = await self.a_sent_message(owner_hospital)

        hidden = await self.resend(other_staff, source.guide_message_id)
        missing = await self.resend(other_staff, source.guide_message_id + 9999)

        assert hidden.status_code == missing.status_code == 404
        assert hidden.json() == missing.json()

    async def test_repeated_and_concurrent_requests_return_one_job(self) -> None:
        hospital = await self.a_hospital("중복 요청 병원")
        staff = await self.a_staff(hospital, "staff", "key306-idempotent")
        source = await self.a_sent_message(hospital)

        first, second = await asyncio.gather(
            self.resend(staff, source.guide_message_id),
            self.resend(staff, source.guide_message_id),
        )

        assert first.status_code == second.status_code == 202
        assert first.json() == second.json()
        assert await GuideMessage.filter(resend_of_message_id=source.guide_message_id).count() == 1

    async def test_an_inactive_link_keeps_its_existing_end_state(self) -> None:
        hospital = await self.a_hospital("종료 링크 병원")
        staff = await self.a_staff(hospital, "staff", "key306-inactive")
        source = await self.a_sent_message(hospital)
        link, challenge = await self.an_active_link(source)
        ended_at = now() - timedelta(hours=1)
        await PatientGuideLink.filter(patient_guide_link_id=link.patient_guide_link_id).update(expires_at=ended_at)
        original_digest = link.token_digest

        response = await self.resend(staff, source.guide_message_id)

        assert response.status_code == 202, response.text
        await link.refresh_from_db()
        await challenge.refresh_from_db()
        assert link.token_digest == original_digest
        assert link.expires_at == ended_at
        assert challenge.consumed_at is None
        assert not await GuideEvent.filter(
            guide_document_id=source.guide_document_id,
            event_type=GuideEventType.LINK_REVOKED,
        ).exists()

    async def test_only_history_rows_can_be_resent(self) -> None:
        hospital = await self.a_hospital("상태 차단 병원")
        staff = await self.a_staff(hospital, "staff", "key306-status")
        source = await self.a_sent_message(hospital)
        await GuideMessage.filter(guide_message_id=source.guide_message_id).update(
            status=GuideMessageStatus.SCHEDULED,
            sent_at=None,
        )

        response = await self.resend(staff, source.guide_message_id)

        assert response.status_code == 409
        assert response.json()["code"] == "MESSAGE_NOT_RESENDABLE"

    async def test_a_sent_message_never_stores_the_raw_link_token(self) -> None:
        hospital = await self.a_hospital("본문 마스킹 병원")
        message = await self.a_sent_message(hospital)
        await GuideMessage.filter(guide_message_id=message.guide_message_id).update(
            status=GuideMessageStatus.SCHEDULED,
            sent_at=None,
            claim_token="key306-claim",
        )
        await message.refresh_from_db()
        body = f"안내 보기: https://patient.example/otp.html#t={OLD_LINK_TOKEN}"

        await _finish_sent(
            message,
            "key306-claim",
            now(),
            body,
            SmsSendResult(
                status=SmsDeliveryStatus.SENT,
                provider=SmsProvider.MOCK,
                provider_message_id="synthetic-provider-message",
            ),
        )

        await message.refresh_from_db()
        assert message.sent_body is not None
        assert OLD_LINK_TOKEN not in message.sent_body
        assert "#t=[REDACTED]" in message.sent_body

    async def test_delivery_failure_does_not_restore_the_old_link(self) -> None:
        hospital = await self.a_hospital("발송 실패 병원")
        staff = await self.a_staff(hospital, "staff", "key306-failure")
        source = await self.a_sent_message(hospital)
        await self.an_active_link(source)
        response = await self.resend(staff, source.guide_message_id)
        replacement = await GuideMessage.get(guide_message_id=response.json()["guide_message_id"])

        new_raw_token, _ = await PatientLinkService().issue_for_dispatch(
            replacement.guide_document_id,
            replacement.guide_message_id,
            replacement.kind,
        )
        await GuideMessage.filter(guide_message_id=replacement.guide_message_id).update(claim_token="failed-claim")
        await replacement.refresh_from_db()

        await _finish_failed(replacement, "failed-claim", provider_detail="synthetic_failure")

        link = await PatientGuideLink.get(guide_document_id=replacement.guide_document_id)
        assert link.token_digest == digest_link_token(new_raw_token)
        assert link.token_digest != digest_link_token(OLD_LINK_TOKEN)


def test_sent_body_storage_redacts_the_patient_link_token() -> None:
    # secrets.token_urlsafe(32)는 항상 정확히 43자다 — 짧은 합성 문자열이
    # 아니라 실제 길이와 같은 값으로 잰다(길이 기반 매칭이라 길이가 달라지면
    # 이 검사 자체가 그 차이를 놓친다).
    token = "a" * 43
    body = f"안내 보기: https://patient.example/otp.html#t={token}"

    stored = _body_for_storage(body)

    assert token not in stored
    assert stored == "안내 보기: https://patient.example/otp.html#t=[REDACTED]"


def test_sent_body_storage_does_not_swallow_a_trailing_character_glued_to_the_token() -> None:
    """[KEY-306, 2heej 리뷰] 토큰 뒤에 구분자 없이 글자가 바로 붙어도 그 글자는 안 삼킨다.

    병원이 문구를 "...확인: {링크}1회용"처럼 저장하면 렌더링 후
    `#t=<TOKEN>1회용`이 된다. 예전 정규식(`[A-Za-z0-9_-]+`, 열린 길이)은
    토큰 뒤의 "1"까지 같이 삼켰다 — 토큰 자체는 가려지지만 저장된 문구가
    실제 발송문과 달라졌다. `app/core/masking.py`의 URLSAFE_TOKEN으로
    바꾸는 것도 시도해 봤지만, 그쪽은 한글이 Python 정규식에서 단어
    문자로 잡혀 경계(\\b)를 아예 못 찾고 **매칭 자체가 실패**한다(재현
    확인) — 지금 구현은 정확히 43자만 보므로 이 문제가 둘 다 없다.
    """
    token = "b" * 43
    body = f"확인: #t={token}1회용"

    stored = _body_for_storage(body)

    assert token not in stored
    assert stored == "확인: #t=[REDACTED]1회용", f"뒤 글자가 삼켜지거나 마스킹 자체가 실패했다: {stored!r}"
