import re
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from app.patient.contracts import ApprovedGuidanceBundle, ApprovedGuidanceProvider
from app.patient.messaging import MessageKind, PatientMessageGateway, SentMessage
from app.patient.models import (
    AccessPurpose,
    AdherenceStatus,
    FollowUpAlert,
    FollowUpResponse,
    LinkState,
    OtpChallenge,
    PainType,
    PatientLink,
    PatientSession,
    PendingDelivery,
)
from app.patient.security import PatientSecretCodec
from app.patient.store import PatientFlowStore

LINK_LIFETIME = timedelta(hours=72)
OTP_LIFETIME = timedelta(minutes=3)
SESSION_LIFETIME = timedelta(minutes=30)
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
FALLBACK_LOCK_TIME = timedelta(minutes=10)


class PatientFlowError(Exception):
    def __init__(self, code: str, message: str, status_code: int, retry_after_seconds: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


def utc_now() -> datetime:
    return datetime.now(UTC)


class PatientFlowService:
    def __init__(
        self,
        store: PatientFlowStore,
        guidance_provider: ApprovedGuidanceProvider,
        message_gateway: PatientMessageGateway,
        codec: PatientSecretCodec,
        now: Callable[[], datetime] = utc_now,
        public_patient_url: str = "/patient/",
    ) -> None:
        self.store = store
        self.guidance_provider = guidance_provider
        self.message_gateway = message_gateway
        self.codec = codec
        self.now = now
        self.public_patient_url = public_patient_url

    @staticmethod
    def normalize_phone(value: str) -> str:
        normalized = re.sub(r"\D", "", value)
        if not re.fullmatch(r"01\d{8,9}", normalized):
            raise PatientFlowError("invalid_identity", "휴대폰 번호 형식이 올바르지 않습니다.", 422)
        return normalized

    async def issue_link(
        self,
        care_episode_id: str,
        phone_number: str,
        birth_date: date,
        send_at: datetime | None = None,
        purpose: AccessPurpose = AccessPurpose.GUIDANCE,
    ) -> PatientLink:
        bundle = await self.guidance_provider.get_approved_bundle(care_episode_id)
        if bundle is None:
            raise PatientFlowError(
                "approved_guidance_required",
                "승인 완료된 안내가 없어 링크를 발급할 수 없습니다.",
                409,
            )
        return await self._issue_from_bundle(bundle, phone_number, birth_date, send_at, purpose)

    async def _issue_from_bundle(
        self,
        bundle: ApprovedGuidanceBundle,
        phone_number: str,
        birth_date: date | None,
        send_at: datetime | None,
        purpose: AccessPurpose,
        birth_date_digest: str | None = None,
    ) -> PatientLink:
        now = self.now()
        normalized_phone = self.normalize_phone(phone_number)
        scheduled = send_at or now
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)
        if birth_date_digest is None:
            if birth_date is None:
                raise ValueError("birth_date or birth_date_digest is required")
            birth_date_digest = self.codec.digest(birth_date.strftime("%y%m%d"))
        raw_token = self.codec.random_token()
        link = PatientLink(
            id=str(uuid.uuid4()),
            care_episode_id=bundle.care_episode_id,
            purpose=purpose,
            bundle=bundle,
            token_digest=self.codec.digest(raw_token),
            phone_ciphertext=self.codec.encrypt(normalized_phone),
            phone_last4=normalized_phone[-4:],
            birth_date_digest=birth_date_digest,
            encounter_date=bundle.encounter_date,
            created_at=now,
            send_at=scheduled,
            expires_at=scheduled + LINK_LIFETIME,
            state=LinkState.SCHEDULED,
        )
        self.store.save_link(link)
        self.store.pending_deliveries[link.id] = PendingDelivery(link.id, self.codec.encrypt(raw_token))
        if scheduled <= now:
            await self.dispatch_due_links()
        return link

    async def dispatch_due_links(self) -> int:
        now = self.now()
        sent = 0
        for link_id, pending in list(self.store.pending_deliveries.items()):
            link = self.store.links[link_id]
            if link.state is not LinkState.SCHEDULED or link.send_at > now:
                continue
            token = self.codec.decrypt(pending.token_ciphertext)
            phone = self.codec.decrypt(link.phone_ciphertext)
            url = f"{self.public_patient_url}#access={token}"
            await self.message_gateway.send(SentMessage(MessageKind.ACCESS_LINK, phone, url))
            link.state = LinkState.SENT
            link.sent_at = now
            del self.store.pending_deliveries[link_id]
            sent += 1
        return sent

    def revoke_link(self, link_id: str) -> PatientLink:
        link = self.store.links.get(link_id)
        if link is None:
            raise PatientFlowError("link_not_found", "링크를 찾을 수 없습니다.", 404)
        link.state = LinkState.REVOKED
        link.revoked_at = self.now()
        self.store.pending_deliveries.pop(link_id, None)
        self._revoke_sessions(link_id)
        return link

    def inspect_link(self, raw_token: str) -> PatientLink:
        link = self.store.find_link_by_digest(self.codec.digest(raw_token))
        if link is None:
            raise PatientFlowError("link_invalid", "유효하지 않은 링크입니다.", 404)
        self._assert_link_open(link)
        return link

    def _assert_link_open(self, link: PatientLink) -> None:
        now = self.now()
        if link.state is LinkState.REVOKED:
            raise PatientFlowError("link_revoked", "폐기된 링크입니다. 안내문 문자를 다시 받아 주세요.", 410)
        if now >= link.expires_at:
            link.state = LinkState.EXPIRED
            self._revoke_sessions(link.id)
            raise PatientFlowError("link_expired", "진료 후 3일이 지나 링크가 닫혔어요.", 410)
        if link.state is LinkState.SCHEDULED:
            raise PatientFlowError("link_not_sent", "아직 발송되지 않은 링크입니다.", 409)

    async def request_otp(self, raw_token: str) -> OtpChallenge:
        link = self.inspect_link(raw_token)
        now = self.now()
        previous = self._latest_challenge(link.id)
        if previous and previous.locked_at:
            raise PatientFlowError("otp_locked", "인증번호를 5회 잘못 입력해 링크가 잠겼어요.", 429)
        resend_count = 0
        if previous:
            elapsed = now - previous.created_at
            if elapsed < OTP_RESEND_COOLDOWN:
                retry = int((OTP_RESEND_COOLDOWN - elapsed).total_seconds()) + 1
                raise PatientFlowError("otp_resend_wait", "잠시 뒤 다시 시도해 주세요.", 429, retry)
            resend_count = previous.resend_count + 1
            if resend_count >= 3:
                raise PatientFlowError("otp_resend_limit", "인증번호는 세 번까지 다시 받을 수 있어요.", 429)
        code = self.codec.otp()
        challenge = OtpChallenge(
            id=str(uuid.uuid4()),
            link_id=link.id,
            code_digest=self.codec.digest(code),
            created_at=now,
            expires_at=now + OTP_LIFETIME,
            resend_count=resend_count,
        )
        self.store.save_challenge(challenge)
        await self.message_gateway.send(SentMessage(MessageKind.OTP, self.codec.decrypt(link.phone_ciphertext), code))
        return challenge

    def verify_otp(self, challenge_id: str, code: str) -> tuple[PatientSession, str]:
        challenge = self.store.challenges.get(challenge_id)
        if challenge is None:
            raise PatientFlowError("otp_invalid", "인증번호 요청을 찾을 수 없습니다.", 404)
        link = self.store.links[challenge.link_id]
        self._assert_link_open(link)
        now = self.now()
        if challenge.locked_at:
            raise PatientFlowError("otp_locked", "인증번호를 5회 잘못 입력해 링크가 잠겼어요.", 429)
        if now >= challenge.expires_at:
            raise PatientFlowError("otp_expired", "인증번호 유효시간 3분이 지났어요.", 410)
        if not re.fullmatch(r"\d{6}", code) or not self.codec.matches(code, challenge.code_digest):
            challenge.failures += 1
            if challenge.failures >= 5:
                challenge.locked_at = now
                raise PatientFlowError("otp_locked", "인증번호를 5회 잘못 입력해 링크가 잠겼어요.", 429)
            raise PatientFlowError("otp_mismatch", "인증번호가 맞지 않아요.", 401)
        challenge.verified_at = now
        raw_session = self.codec.random_token()
        session = PatientSession(
            id=str(uuid.uuid4()),
            link_id=link.id,
            token_digest=self.codec.digest(raw_session),
            created_at=now,
            expires_at=now + SESSION_LIFETIME,
        )
        self.store.save_session(session)
        return session, raw_session

    def authenticate(self, raw_session: str | None) -> tuple[PatientSession, PatientLink]:
        if not raw_session:
            raise PatientFlowError("reauthentication_required", "본인 확인이 필요해요.", 401)
        session = self.store.find_session(self.codec.digest(raw_session))
        if session is None or session.revoked_at:
            raise PatientFlowError("reauthentication_required", "본인 확인이 필요해요.", 401)
        if self.now() >= session.expires_at:
            session.revoked_at = self.now()
            raise PatientFlowError("session_expired", "30분이 지나 다시 확인해 주세요.", 401)
        link = self.store.links[session.link_id]
        self._assert_link_open(link)
        return session, link

    async def reissue_link(self, raw_token: str, phone_number: str, birth_date: str) -> PatientLink:
        old_link = self.store.find_link_by_digest(self.codec.digest(raw_token))
        if old_link is None:
            raise PatientFlowError("identity_mismatch", "번호나 생년월일이 맞지 않아요.", 401)
        now = self.now()
        if old_link.fallback_locked_until and now < old_link.fallback_locked_until:
            retry = int((old_link.fallback_locked_until - now).total_seconds()) + 1
            raise PatientFlowError("fallback_locked", "10분 동안 잠깁니다.", 429, retry)
        try:
            normalized_phone = self.normalize_phone(phone_number)
        except PatientFlowError:
            normalized_phone = ""
        identity_matches = normalized_phone == self.codec.decrypt(old_link.phone_ciphertext) and self.codec.matches(
            birth_date, old_link.birth_date_digest
        )
        if not identity_matches:
            old_link.fallback_failures += 1
            if old_link.fallback_failures >= 5:
                old_link.fallback_locked_until = now + FALLBACK_LOCK_TIME
                old_link.fallback_failures = 0
                raise PatientFlowError("fallback_locked", "10분 동안 잠깁니다.", 429, 600)
            raise PatientFlowError("identity_mismatch", "번호나 생년월일이 맞지 않아요.", 401)
        reissue_key = (old_link.care_episode_id, now.date())
        today_count = self.store.reissues_by_episode_and_date.get(reissue_key, 0)
        if today_count >= 3:
            raise PatientFlowError("daily_reissue_limit", "안내문 문자는 하루 3번까지 받을 수 있어요.", 429)
        old_link.resend_dates.append(now.date())
        self.store.reissues_by_episode_and_date[reissue_key] = today_count + 1
        old_link.state = LinkState.REVOKED
        old_link.revoked_at = now
        self._revoke_sessions(old_link.id)
        return await self._issue_from_bundle(
            old_link.bundle,
            normalized_phone,
            None,
            now,
            old_link.purpose,
            birth_date_digest=old_link.birth_date_digest,
        )

    def guidance(self, raw_session: str | None) -> ApprovedGuidanceBundle:
        _, link = self.authenticate(raw_session)
        return link.bundle

    def follow_up_status(self, raw_session: str | None) -> dict[str, object]:
        _, link = self.authenticate(raw_session)
        due_date = link.encounter_date + timedelta(days=7)
        return {
            "due": self.now().date() >= due_date,
            "due_date": due_date,
            "submitted": link.id in self.store.follow_ups,
        }

    def medication_status(self, raw_session: str | None) -> dict[str, object]:
        _, link = self.authenticate(raw_session)
        elapsed_days = max((self.now().date() - link.encounter_date).days, 0)
        medications = []
        for medication in link.bundle.medications:
            remaining_days = max(medication.duration_days - elapsed_days, 0)
            medications.append(
                {
                    "name": medication.name,
                    "strength": medication.strength,
                    "total_days": medication.duration_days,
                    "elapsed_days": elapsed_days,
                    "remaining_days": remaining_days,
                    "progress_percent": min(round(elapsed_days / medication.duration_days * 100), 100),
                    "depletion_date": link.encounter_date + timedelta(days=medication.duration_days),
                    "purpose": medication.purpose,
                }
            )
        return {
            "prescription_date": link.encounter_date,
            "clinic_name": link.bundle.clinic_name,
            "medications": medications,
        }

    def record_adherence_selection(
        self,
        raw_session: str | None,
        adherence: AdherenceStatus,
    ) -> FollowUpAlert | None:
        _, link = self.authenticate(raw_session)
        if adherence not in {AdherenceStatus.STOPPED_SIDE_EFFECTS, AdherenceStatus.STOPPED_BETTER}:
            return None
        key = (link.id, adherence.value)
        existing = self.store.follow_up_alerts.get(key)
        if existing:
            return existing
        alert = FollowUpAlert(
            id=str(uuid.uuid4()),
            link_id=link.id,
            adherence=adherence,
            created_at=self.now(),
        )
        self.store.follow_up_alerts[key] = alert
        return alert

    def submit_follow_up(
        self,
        raw_session: str | None,
        adherence: AdherenceStatus,
        has_pain: bool,
        pain_score: int | None,
        pain_types: tuple[PainType, ...],
        memo: str | None,
    ) -> FollowUpResponse:
        _, link = self.authenticate(raw_session)
        due_date = link.encounter_date + timedelta(days=7)
        if self.now().date() < due_date:
            raise PatientFlowError("follow_up_not_due", "아직 복약 확인 기간이 아닙니다.", 409)
        if link.id in self.store.follow_ups:
            raise PatientFlowError("follow_up_already_submitted", "이미 기록이 저장됐어요.", 409)
        if has_pain and (pain_score is None or not 0 <= pain_score <= 10):
            raise PatientFlowError("pain_score_required", "통증 정도를 0에서 10 사이로 입력해 주세요.", 422)
        if not has_pain and (pain_score is not None or pain_types):
            raise PatientFlowError("pain_details_not_allowed", "통증이 없으면 정도와 유형을 입력하지 않습니다.", 422)
        response = FollowUpResponse(
            id=str(uuid.uuid4()),
            link_id=link.id,
            adherence=adherence,
            has_pain=has_pain,
            pain_score=pain_score,
            pain_types=pain_types,
            memo=memo.strip()[:500] if memo and memo.strip() else None,
            created_at=self.now(),
        )
        self.store.follow_ups[link.id] = response
        return response

    def get_follow_up_for_staff(self, link_id: str) -> FollowUpResponse:
        if link_id not in self.store.links:
            raise PatientFlowError("link_not_found", "링크를 찾을 수 없습니다.", 404)
        response = self.store.follow_ups.get(link_id)
        if response is None:
            raise PatientFlowError("follow_up_not_found", "저장된 복약 확인이 없습니다.", 404)
        return response

    def get_follow_up_alerts_for_staff(self, link_id: str) -> list[FollowUpAlert]:
        if link_id not in self.store.links:
            raise PatientFlowError("link_not_found", "링크를 찾을 수 없습니다.", 404)
        return [item for item in self.store.follow_up_alerts.values() if item.link_id == link_id]

    def _latest_challenge(self, link_id: str) -> OtpChallenge | None:
        matches = [item for item in self.store.challenges.values() if item.link_id == link_id]
        return max(matches, key=lambda item: item.created_at) if matches else None

    def _revoke_sessions(self, link_id: str) -> None:
        now = self.now()
        for session in self.store.sessions_by_digest.values():
            if session.link_id == link_id and session.revoked_at is None:
                session.revoked_at = now
