"""6자리 환자 OTP 발급·검증·실패 제한 — KEY-91."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.core import config
from app.core.auth_errors import AuthError as ApiError
from app.models.visits import GuideStatus, PatientGuideLink, PatientOtpChallenge
from app.services.patient_links import digest_link_token

OTP_TTL = timedelta(minutes=3)
OTP_LOCK_DURATION = timedelta(minutes=10)
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
OTP_MAX_FAILURES = 5
OTP_LENGTH = 6


class OtpDelivery(Protocol):
    async def send(self, phone: str, code: str) -> None: ...


class UnavailableOtpDelivery:
    """실제 SMS 공급자를 성공으로 가장하지 않는 안전한 기본 구현."""

    async def send(self, phone: str, code: str) -> None:
        raise ApiError("OTP_DELIVERY_UNAVAILABLE", 503, "인증번호 전송을 사용할 수 없습니다.")


class MockOtpDelivery:
    """local·dev·test 전용 mock 발송 어댑터 — KEY-219.

    실제 SMS를 보내지 않고 발송 성공만 시뮬레이션한다.
    코드 원문은 로그에 남기지 않는다.
    """

    async def send(self, phone: str, code: str) -> None:
        pass


def _otp_digest(code: str, salt: str, secret_key: str) -> str:
    otp_key = hmac.new(secret_key.encode("utf-8"), b"patient-otp-hmac-key-v1", hashlib.sha256).digest()
    payload = bytes.fromhex(salt) + code.encode("ascii")
    return hmac.new(otp_key, payload, hashlib.sha256).hexdigest()


def _as_utc(dt: datetime) -> datetime:
    """Tortoise + MySQL timezone 불일치 보정 — KEY-219.

    TORTOISE_ORM timezone="Asia/Seoul" 설정으로 인해 asyncmy가 DB에서 읽은
    UTC 값에 +09:00 태그를 잘못 붙인다. now()는 +00:00(UTC)을 반환하므로
    모든 timestamp 비교 전에 양쪽 모두 UTC로 정규화한다.
    """
    return dt.replace(tzinfo=UTC)


def _seconds_until(value: datetime, timestamp: datetime) -> int:
    return max(1, int((_as_utc(value) - _as_utc(timestamp)).total_seconds() + 0.999))


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
        if _as_utc(link.expires_at) <= _as_utc(timestamp):
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
        if challenge.locked_until is not None and _as_utc(challenge.locked_until) <= _as_utc(timestamp):
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
        """발송 실패가 뒤따른 발급 상태만 되돌리고 동시 변경은 보존한다."""
        async with in_transaction() as connection:
            challenge = await self._locked_challenge(patient_guide_link_id, connection)
            if challenge is None or challenge.otp_digest != issued_digest or challenge.consumed_at is not None:
                return
            if previous is None:
                await challenge.delete(using_db=connection)
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
                if _as_utc(challenge.issued_at) + OTP_RESEND_COOLDOWN > _as_utc(timestamp):
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
        try:
            await self.delivery.send(patient.phone, code)
        except Exception as exc:
            await self._compensate_failed_delivery(
                link.patient_guide_link_id,
                challenge.otp_digest,
                previous,
            )
            if isinstance(exc, ApiError):
                raise
            raise ApiError("OTP_DELIVERY_UNAVAILABLE", 503, "인증번호 전송을 사용할 수 없습니다.") from exc
        return challenge

    async def verify(self, raw_link_token: str, code: str) -> PatientGuideLink:
        failure: ApiError | None = None
        async with in_transaction() as connection:
            link = await self._active_link(raw_link_token, connection, include_patient=False)
            challenge = await self._locked_challenge(link.patient_guide_link_id, connection)
            timestamp = now()
            if challenge is None:
                raise ApiError("OTP_NOT_ISSUED", 409, "인증번호를 먼저 요청해 주세요.")

            await self._release_elapsed_lock(challenge, timestamp, connection)
            if challenge.locked_until is not None:
                raise _locked(challenge, timestamp)
            if challenge.consumed_at is not None:
                raise ApiError("OTP_ALREADY_USED", 409, "이미 사용한 인증번호입니다. 새 인증번호를 요청해 주세요.")
            if _as_utc(challenge.expires_at) <= _as_utc(timestamp):
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
                else:
                    await challenge.save(using_db=connection, update_fields=["failed_attempts", "updated_at"])
                    failure = ApiError(
                        "OTP_INVALID",
                        401,
                        "인증번호가 올바르지 않습니다.",
                        extra={"remaining_attempts": OTP_MAX_FAILURES - challenge.failed_attempts},
                    )
            else:
                challenge.consumed_at = timestamp
                challenge.failed_attempts = 0
                await challenge.save(
                    using_db=connection,
                    update_fields=["consumed_at", "failed_attempts", "updated_at"],
                )

        # 실패 횟수와 잠금을 먼저 커밋한 뒤 응답 예외를 올린다. 트랜잭션 안에서
        # 예외를 던지면 보안 상태까지 롤백되어 무제한 재시도가 가능해진다.
        if failure is not None:
            raise failure
        return link
