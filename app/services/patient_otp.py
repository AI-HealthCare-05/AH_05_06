"""6자리 환자 OTP 발급·검증·실패 제한 — KEY-91."""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.core import config
from app.core.auth_errors import AuthError as ApiError
from app.core.time import as_utc
from app.models.staffs import Hospital
from app.models.visits import GuideStatus, PatientGuideLink, PatientOtpChallenge, PatientOtpEvent, PatientOtpEventType
from app.services.message_templates import SYSTEM_BODY
from app.services.patient_links import digest_link_token
from app.services.sms_sender import SmsDeliveryStatus, SmsSender, SmsSendError

OTP_TTL = timedelta(minutes=3)
OTP_LOCK_DURATION = timedelta(minutes=10)
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
OTP_MAX_FAILURES = 5
OTP_LENGTH = 6
LOGGER = logging.getLogger("app.patient_otp")


async def _record_otp_event(
    patient_guide_link_id: int,
    event_type: PatientOtpEventType,
) -> None:
    """Record audit data without changing the OTP operation's outcome."""
    try:
        await PatientOtpEvent.create(
            patient_guide_link_id=patient_guide_link_id,
            event_type=event_type,
        )
    except Exception:
        # The OTP state or external delivery may already be committed. Do not
        # report a false authentication result when only audit storage failed.
        LOGGER.error(
            "patient OTP audit event could not be stored: event_type=%s",
            event_type.value,
        )


class OtpDelivery(Protocol):
    async def send(self, phone: str, code: str, hospital_name: str) -> None: ...


class UnavailableOtpDelivery:
    """실제 SMS 공급자를 성공으로 가장하지 않는 안전한 기본 구현."""

    async def send(self, phone: str, code: str, hospital_name: str) -> None:
        raise ApiError("OTP_DELIVERY_UNAVAILABLE", 503, "인증번호 전송을 사용할 수 없습니다.")


class MockOtpDelivery:
    """local·dev·test 전용 mock 발송 어댑터 — KEY-219.

    실제 SMS를 보내지 않고 발송 성공만 시뮬레이션한다.
    코드 원문은 로그에 남기지 않는다.
    """

    async def send(self, phone: str, code: str, hospital_name: str) -> None:
        pass


class SolapiOtpDelivery:
    """OTP 인증번호를 실제 SmsSender로 보낸다 — KEY-284.

    KEY-91의 기존 발급·검증·잠금·보상 로직을 복제하지 않는다 — 이 클래스는
    문구를 조립해서 보내기만 한다. 발송이 SENT로 확인되지 않으면 예외를
    던지는데, 그 예외를 여기서 잡지 않는다: PatientOtpService.issue()가
    이미 delivery.send()의 모든 예외를 잡아서 발급 상태를 보상하고
    OTP_DELIVERY_UNAVAILABLE로 감싸는 로직을 갖고 있다(KEY-91) — 같은 일을
    또 하지 않는다.

    문구는 message_templates.SYSTEM_BODY 하나만 쓴다 — 예전엔 이 클래스가
    독자적인 문자열을 따로 갖고 있어서, 스탭이 문구 관리 화면에서 보는
    "이게 나갑니다"와 실제로 나가는 문구가 달랐다(iljun-sys 리뷰로 실제
    전선을 수집해서 확인). 인증문구는 코드에 한 곳에만 있어야 한다.
    """

    def __init__(self, sender: SmsSender) -> None:
        self._sender = sender

    async def send(self, phone: str, code: str, hospital_name: str) -> None:
        body = SYSTEM_BODY.format(의원명=hospital_name, 번호=code)
        try:
            result = await self._sender.send(phone, body)
        except SmsSendError as exc:
            # exc.reason은 "provider_timeout"·"provider_http_401" 같은 기계
            # 판독용 코드다 — 전화번호·OTP·예외 원문이 아니라 masking.scrub()을
            # 그대로 통과한다(iljun-sys 리뷰로 확인). 이걸 안 남기면 성공과
            # 실패가 INFO 로그에서 구분이 안 된다(같은 리뷰로 재현됨).
            LOGGER.warning("otp delivery failed: reason=%s", exc.reason)
            raise
        if result.status is not SmsDeliveryStatus.SENT:
            # 원문·공급자 응답 문장을 예외 메시지에 담지 않는다 — 상위(issue())가
            # 이 예외를 그대로 OTP_DELIVERY_UNAVAILABLE로 바꾼다. provider_code
            # (예: "3035" 발신번호 미등록)는 기계 판독용 코드라 로그에만 남긴다.
            LOGGER.warning("otp delivery not confirmed sent: provider_code=%s", result.provider_code)
            raise RuntimeError("otp delivery not confirmed sent")


class ApprovedPhonesOnlyDelivery:
    """실제 발송을 승인된 테스트 번호로만 좁힌다 — KEY-284.

    운영 활성화 승인(KEY-6)이 따로 생기기 전까지는 환경과 무관하게 항상
    이 래퍼를 씌운다 — Pilot도 ENV=prod로 뜨기 때문에(KEY-264), "prod면
    안 씌운다"고 두면 Pilot에서 좁은문을 여는 순간 임의 번호로 나간다
    (yugaeun821 리뷰로 발견, `_otp_service()`에서 고쳤다).

    목록에 없는 번호는 UnavailableOtpDelivery와 같은 방식으로 막는다
    (발송기가 있는데 왜 안 되는지 겉으로는 구분되지 않는다). **목록이
    비어 있으면 전부 막힌다** — "빈 목록 = 전부 허용"이 아니다. 좁은문을
    열면서 이 목록을 안 채우면 모든 번호가 공급자 장애와 구분 안 되는
    503을 받는다(iljun-sys 리뷰로 실제 재현) — `_otp_service()`가 이
    조합을 부팅 시점에 경고한다.
    """

    def __init__(self, delivery: OtpDelivery, approved_phones: frozenset[str]) -> None:
        self._delivery = delivery
        self._approved_phones = approved_phones

    async def send(self, phone: str, code: str, hospital_name: str) -> None:
        if phone not in self._approved_phones:
            raise ApiError("OTP_DELIVERY_UNAVAILABLE", 503, "인증번호 전송을 사용할 수 없습니다.")
        await self._delivery.send(phone, code, hospital_name)


def _otp_digest(code: str, salt: str, secret_key: str) -> str:
    otp_key = hmac.new(secret_key.encode("utf-8"), b"patient-otp-hmac-key-v1", hashlib.sha256).digest()
    payload = bytes.fromhex(salt) + code.encode("ascii")
    return hmac.new(otp_key, payload, hashlib.sha256).hexdigest()


def _seconds_until(value: datetime, timestamp: datetime) -> int:
    return max(1, int((as_utc(value) - as_utc(timestamp)).total_seconds() + 0.999))


def _locked(challenge: PatientOtpChallenge, timestamp: datetime) -> ApiError:
    if challenge.locked_until is None:
        raise RuntimeError("locked OTP challenge has no locked_until")
    retry_after = _seconds_until(challenge.locked_until, timestamp)
    return ApiError(
        "OTP_LOCKED",
        429,
        "인증번호 입력 횟수를 초과했습니다. 잠시 뒤 다시 시도해 주세요.",
        extra={"retry_after_seconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


def _resend_too_soon(challenge: PatientOtpChallenge, timestamp: datetime) -> ApiError:
    retry_after = _seconds_until(challenge.issued_at + OTP_RESEND_COOLDOWN, timestamp)
    return ApiError(
        "OTP_RESEND_TOO_SOON",
        429,
        "인증번호는 잠시 뒤 다시 요청해 주세요.",
        extra={"retry_after_seconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


async def invalidate_otp_challenge(
    patient_guide_link_id: int,
    connection: BaseDBAsyncClient,
    timestamp: datetime,
) -> None:
    """링크가 회전할 때 기존 OTP를 소비 처리한다.

    OTP digest·salt 생성 규칙은 이 모듈만 소유한다. 링크 폐기·재발급에서는
    원문 검증을 더 시도할 수 없게 만료·소비 시각만 닫고, 실패 횟수와 잠금은
    그대로 보존한다.
    """

    await (
        PatientOtpChallenge.filter(patient_guide_link_id=patient_guide_link_id)
        .using_db(connection)
        .update(expires_at=timestamp, consumed_at=timestamp)
    )


@dataclass(frozen=True)
class _PreviousOtp:
    otp_digest: str
    otp_salt: str
    expires_at: datetime
    consumed_at: datetime | None
    issued_at: datetime


class PatientOtpService:
    def __init__(
        self,
        delivery: OtpDelivery,
        *,
        secret_key: str | None = None,
        fixed_otp_code: str | None = None,
    ) -> None:
        self.delivery = delivery
        self.secret_key = secret_key or config.SECRET_KEY
        self.fixed_otp_code = fixed_otp_code

    async def _active_link(
        self,
        raw_link_token: str,
        connection: BaseDBAsyncClient,
        *,
        include_patient: bool,
    ) -> PatientGuideLink:
        query = (
            PatientGuideLink.filter(token_digest=digest_link_token(raw_link_token))
            .using_db(connection)
            .select_for_update()
        )
        relation = "guide_document__visit__patient" if include_patient else "guide_document"
        link = await query.prefetch_related(relation).first()
        if link is None:
            raise ApiError("LINK_NOT_FOUND", 404, "환자 링크를 찾을 수 없습니다.")
        timestamp = now()
        if as_utc(link.expires_at) <= as_utc(timestamp):
            raise ApiError("LINK_EXPIRED", 410, "환자 링크가 만료되었습니다.")
        guide = link.guide_document
        if guide.status is not GuideStatus.SCHEDULED_TO_SEND or guide.approved_at is None:
            raise ApiError("LINK_NOT_FOUND", 404, "환자 링크를 찾을 수 없습니다.")
        return link

    @staticmethod
    async def _locked_challenge(
        patient_guide_link_id: int,
        connection: BaseDBAsyncClient,
    ) -> PatientOtpChallenge | None:
        return (
            await PatientOtpChallenge.filter(patient_guide_link_id=patient_guide_link_id)
            .using_db(connection)
            .select_for_update()
            .first()
        )

    @staticmethod
    async def _release_elapsed_lock(
        challenge: PatientOtpChallenge,
        timestamp: datetime,
        connection: BaseDBAsyncClient,
    ) -> None:
        if challenge.locked_until is not None and as_utc(challenge.locked_until) <= as_utc(timestamp):
            challenge.locked_until = None
            challenge.failed_attempts = 0
            await challenge.save(
                using_db=connection,
                update_fields=["locked_until", "failed_attempts", "updated_at"],
            )

    async def _compensate_failed_delivery(
        self,
        patient_guide_link_id: int,
        issued_digest: str,
        previous: _PreviousOtp | None,
    ) -> None:
        """발송 실패가 뒤따른 발급 상태만 되돌리고 동시 변경은 보존한다.

        `previous is None`(이 링크의 첫 발급)이어도 행을 지우지 않는다.
        예전엔 지웠는데, 그러면 다음 issue()가 "행이 없다"로 보고 재발송
        쿨다운 검사를 아예 건너뛴다 — 실제 HTTP 경로로 25번 연속 호출해
        감사 행이 25줄 쌓이는 것으로 재현됐다(iljun-sys 리뷰, 쿨다운이
        걸렸다면 1줄이어야 한다). 지금 이 행의 digest는 환자가 받은 적
        없는 값이라(발송이 실패했으므로) 그대로 둬도 아무 코드와도
        안 맞는다 — issued_at만 살아 있으면 쿨다운은 정상 작동한다.
        """
        async with in_transaction() as connection:
            challenge = await self._locked_challenge(patient_guide_link_id, connection)
            if challenge is None or challenge.otp_digest != issued_digest or challenge.consumed_at is not None:
                return
            if previous is None:
                return
            challenge.otp_digest = previous.otp_digest
            challenge.otp_salt = previous.otp_salt
            challenge.expires_at = previous.expires_at
            challenge.consumed_at = previous.consumed_at
            challenge.issued_at = previous.issued_at
            await challenge.save(
                using_db=connection,
                update_fields=[
                    "otp_digest",
                    "otp_salt",
                    "expires_at",
                    "consumed_at",
                    "issued_at",
                    "updated_at",
                ],
            )

    async def issue(self, raw_link_token: str) -> PatientOtpChallenge:
        previous: _PreviousOtp | None = None
        async with in_transaction() as connection:
            link = await self._active_link(raw_link_token, connection, include_patient=True)
            patient = link.guide_document.visit.patient
            if not patient.sms_consent:
                raise ApiError(
                    "SMS_OPT_OUT",
                    409,
                    "문자 수신에 동의하지 않아 인증번호를 전송할 수 없습니다.",
                )
            challenge = await self._locked_challenge(link.patient_guide_link_id, connection)
            # 행 잠금 대기 시간이 만료·잠금·재발급 계산에 섞이지 않게
            # 필요한 잠금을 모두 획득한 뒤 판정 기준 시각을 읽는다.
            timestamp = now()
            if challenge is not None:
                await self._release_elapsed_lock(challenge, timestamp, connection)
                if challenge.locked_until is not None:
                    raise _locked(challenge, timestamp)
                if as_utc(challenge.issued_at) + OTP_RESEND_COOLDOWN > as_utc(timestamp):
                    raise _resend_too_soon(challenge, timestamp)

                previous = _PreviousOtp(
                    otp_digest=challenge.otp_digest,
                    otp_salt=challenge.otp_salt,
                    expires_at=challenge.expires_at,
                    consumed_at=challenge.consumed_at,
                    issued_at=challenge.issued_at,
                )
                code = self.fixed_otp_code or f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"
                salt = secrets.token_hex(16)
                challenge.otp_digest = _otp_digest(code, salt, self.secret_key)
                challenge.otp_salt = salt
                challenge.expires_at = timestamp + OTP_TTL
                challenge.consumed_at = None
                challenge.issued_at = timestamp
                await challenge.save(
                    using_db=connection,
                    update_fields=[
                        "otp_digest",
                        "otp_salt",
                        "expires_at",
                        "consumed_at",
                        "issued_at",
                        "updated_at",
                    ],
                )
            else:
                code = self.fixed_otp_code or f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"
                salt = secrets.token_hex(16)
                challenge = await PatientOtpChallenge.create(
                    patient_guide_link=link,
                    otp_digest=_otp_digest(code, salt, self.secret_key),
                    otp_salt=salt,
                    expires_at=timestamp + OTP_TTL,
                    issued_at=timestamp,
                    using_db=connection,
                )
        # 외부 공급자 지연 중 DB 행 잠금과 커넥션을 점유하지 않는다.
        hospital = await Hospital.filter(hospital_id=link.guide_document.hospital_id).first()
        try:
            await self.delivery.send(patient.phone, code, hospital.name if hospital else "")
        except Exception as exc:
            await self._compensate_failed_delivery(
                link.patient_guide_link_id,
                challenge.otp_digest,
                previous,
            )
            await _record_otp_event(
                link.patient_guide_link_id,
                PatientOtpEventType.DELIVERY_FAILED,
            )
            if isinstance(exc, ApiError):
                raise
            raise ApiError("OTP_DELIVERY_UNAVAILABLE", 503, "인증번호 전송을 사용할 수 없습니다.") from exc
        await _record_otp_event(link.patient_guide_link_id, PatientOtpEventType.ISSUED)
        return challenge

    async def verify(self, raw_link_token: str, code: str) -> PatientGuideLink:
        failure: ApiError | None = None
        event_type = PatientOtpEventType.VERIFIED
        async with in_transaction() as connection:
            link = await self._active_link(raw_link_token, connection, include_patient=False)
            challenge = await self._locked_challenge(link.patient_guide_link_id, connection)
            timestamp = now()
            if challenge is None:
                # 발급된 적 없는 링크로의 검증 시도 — VERIFICATION_FAILED로 남긴다.
                # 아래 정상 경로들과 달리 여기서부터는 함수 끝의
                # _record_otp_event() 호출까지 안 가고 바로 raise하므로,
                # 이 네 이른 종료 경로마다 직접 기록한다(iljun-sys 리뷰 —
                # 예전엔 이 네 경로가 감사 이력에 한 줄도 안 남았다).
                await _record_otp_event(link.patient_guide_link_id, PatientOtpEventType.VERIFICATION_FAILED)
                raise ApiError("OTP_NOT_ISSUED", 409, "인증번호를 먼저 요청해 주세요.")

            await self._release_elapsed_lock(challenge, timestamp, connection)
            if challenge.locked_until is not None:
                await _record_otp_event(link.patient_guide_link_id, PatientOtpEventType.LOCKED)
                raise _locked(challenge, timestamp)
            if challenge.consumed_at is not None:
                await _record_otp_event(link.patient_guide_link_id, PatientOtpEventType.VERIFICATION_FAILED)
                raise ApiError("OTP_ALREADY_USED", 409, "이미 사용한 인증번호입니다. 새 인증번호를 요청해 주세요.")
            if as_utc(challenge.expires_at) <= as_utc(timestamp):
                await _record_otp_event(link.patient_guide_link_id, PatientOtpEventType.VERIFICATION_FAILED)
                raise ApiError("OTP_EXPIRED", 410, "인증번호가 만료되었습니다. 새 인증번호를 요청해 주세요.")

            valid_format = len(code) == OTP_LENGTH and code.isascii() and code.isdigit()
            expected = _otp_digest(code, challenge.otp_salt, self.secret_key) if valid_format else ""
            if not valid_format or not hmac.compare_digest(challenge.otp_digest, expected):
                challenge.failed_attempts += 1
                if challenge.failed_attempts >= OTP_MAX_FAILURES:
                    challenge.locked_until = timestamp + OTP_LOCK_DURATION
                    await challenge.save(
                        using_db=connection,
                        update_fields=["failed_attempts", "locked_until", "updated_at"],
                    )
                    failure = _locked(challenge, timestamp)
                    event_type = PatientOtpEventType.LOCKED
                else:
                    await challenge.save(using_db=connection, update_fields=["failed_attempts", "updated_at"])
                    failure = ApiError(
                        "OTP_INVALID",
                        401,
                        "인증번호가 올바르지 않습니다.",
                        extra={"remaining_attempts": OTP_MAX_FAILURES - challenge.failed_attempts},
                    )
                    event_type = PatientOtpEventType.VERIFICATION_FAILED
            else:
                challenge.consumed_at = timestamp
                challenge.failed_attempts = 0
                await challenge.save(
                    using_db=connection,
                    update_fields=["consumed_at", "failed_attempts", "updated_at"],
                )

        # 실패 횟수와 잠금을 먼저 커밋한 뒤 응답 예외를 올린다. 트랜잭션 안에서
        # 예외를 던지면 보안 상태까지 롤백되어 무제한 재시도가 가능해진다.
        await _record_otp_event(link.patient_guide_link_id, event_type)
        if failure is not None:
            raise failure
        return link
