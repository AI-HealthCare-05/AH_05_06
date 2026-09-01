"""환자 링크 발급·조회·재발급 — KEY-90, KEY-219."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from tortoise.exceptions import IntegrityError
from tortoise.timezone import now

from app.core.auth_errors import AuthError as ApiError
from app.core.time import as_utc
from app.core.masking import mask_phone
from app.models.staffs import Hospital
from app.models.visits import GuideDocument, GuideStatus, PatientGuideLink

LINK_TTL = timedelta(hours=72)
ISSUER_ROLES = frozenset({"staff", "doctor"})


@dataclass(frozen=True)
class PatientLinkContext:
    hospital_name: str
    masked_phone: str
    visited_at: date
    expires_at: datetime


def digest_link_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _link_not_found() -> ApiError:
    return ApiError("LINK_NOT_FOUND", 404, "환자 링크를 찾을 수 없습니다.")


class PatientLinkService:
    async def issue(self, actor, visit_id: int) -> tuple[PatientGuideLink, str]:
        if not ISSUER_ROLES.intersection(actor.roles):
            raise ApiError("FORBIDDEN", 403, "환자 링크를 발급할 권한이 없습니다.")

        guide = await GuideDocument.filter(
            visit_id=visit_id,
            visit__hospital_id=actor.hospital_id,
        ).first()
        if guide is None:
            # 없는 진료와 타 병원 진료를 같은 응답으로 감춘다.
            raise ApiError("GUIDE_NOT_FOUND", 404, "안내문을 찾을 수 없습니다.")
        if guide.status is not GuideStatus.SCHEDULED_TO_SEND or guide.approved_at is None:
            raise ApiError("GUIDE_NOT_APPROVED", 409, "승인 완료된 안내문만 링크를 발급할 수 있습니다.")
        if await PatientGuideLink.filter(guide_document_id=guide.guide_document_id).exists():
            raise ApiError("LINK_ALREADY_ISSUED", 409, "이미 개발용 링크가 발급된 안내문입니다.")

        raw_token = secrets.token_urlsafe(32)
        try:
            link = await PatientGuideLink.create(
                guide_document=guide,
                token_digest=digest_link_token(raw_token),
                expires_at=now() + LINK_TTL,
                issued_by=actor.user_id,
            )
        except IntegrityError as exc:
            # 동시에 두 요청이 들어와도 한 링크만 남긴다.
            raise ApiError("LINK_ALREADY_ISSUED", 409, "이미 개발용 링크가 발급된 안내문입니다.") from exc
        return link, raw_token

    async def get_context(self, raw_link_token: str) -> "PatientLinkContext":
        link = (
            await PatientGuideLink.filter(token_digest=digest_link_token(raw_link_token))
            .prefetch_related("guide_document__visit__patient")
            .first()
        )
        if link is None:
            raise ApiError("LINK_NOT_FOUND", 404, "환자 링크를 찾을 수 없습니다.")

        timestamp = now()
        if as_utc(link.expires_at) <= as_utc(timestamp):
            raise ApiError("LINK_EXPIRED", 410, "환자 링크가 만료되었습니다.")

        guide = link.guide_document
        if guide.status is not GuideStatus.SCHEDULED_TO_SEND or guide.approved_at is None:
            raise ApiError("LINK_REVOKED", 410, "환자 링크가 폐기되었습니다.")

        visit = guide.visit
        patient = visit.patient
        hospital = await Hospital.filter(hospital_id=visit.hospital_id).first()

        return PatientLinkContext(
            hospital_name=hospital.name if hospital else "",
            masked_phone=mask_phone(patient.phone),
            visited_at=visit.visited_at.date(),
            expires_at=as_utc(link.expires_at),
        )

    async def re_issue(self, raw_link_token: str) -> None:
        """만료·폐기 링크에 새 토큰을 발급한다. mock SMS 발송만 수행한다 — KEY-219."""
        link = await PatientGuideLink.filter(token_digest=digest_link_token(raw_link_token)).first()
        if link is None:
            raise ApiError("LINK_NOT_FOUND", 404, "환자 링크를 찾을 수 없습니다.")

        timestamp = now()
        guide = await GuideDocument.filter(guide_document_id=link.guide_document_id).first()
        is_expired = as_utc(link.expires_at) <= as_utc(timestamp)
        is_revoked = guide is None or guide.status is not GuideStatus.SCHEDULED_TO_SEND or guide.approved_at is None

        if not is_expired and not is_revoked:
            raise ApiError("LINK_STILL_ACTIVE", 409, "현재 유효한 링크가 있습니다.")

        new_raw_token = secrets.token_urlsafe(32)
        link.token_digest = digest_link_token(new_raw_token)
        link.expires_at = timestamp + LINK_TTL
        await link.save(update_fields=["token_digest", "expires_at"])

    async def get_approved_guide(self, raw_token: str) -> tuple[PatientGuideLink, GuideDocument]:
        link = (
            await PatientGuideLink.filter(token_digest=digest_link_token(raw_token))
            .prefetch_related("guide_document__sections")
            .first()
        )
        if link is None:
            raise _link_not_found()
        if as_utc(link.expires_at) <= as_utc(now()):
            raise ApiError("LINK_EXPIRED", 410, "환자 링크가 만료되었습니다.")

        guide = link.guide_document
        if guide.status is not GuideStatus.SCHEDULED_TO_SEND or guide.approved_at is None:
            # 링크가 있더라도 승인 상태가 아니면 안내 존재 여부를 환자에게 내보내지 않는다.
            raise _link_not_found()
        return link, guide
