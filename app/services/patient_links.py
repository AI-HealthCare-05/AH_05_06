"""개발용 환자 링크 발급·조회 — KEY-90 최소 범위.

실제 SMS·예약 발송·OTP·폐기·재발급은 이 서비스에 넣지 않는다. 이번 범위는
승인 안내 한 건을 합성 시나리오에서 여는 Walking Skeleton뿐이다.
"""

import hashlib
import secrets
from datetime import timedelta

from tortoise.exceptions import IntegrityError
from tortoise.timezone import now

from app.core.auth_errors import AuthError as ApiError
from app.models.visits import GuideDocument, GuideStatus, PatientGuideLink

LINK_TTL = timedelta(hours=72)
ISSUER_ROLES = frozenset({"staff", "doctor"})


def _digest(raw_token: str) -> str:
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
                token_digest=_digest(raw_token),
                expires_at=now() + LINK_TTL,
                issued_by=actor.user_id,
            )
        except IntegrityError as exc:
            # 동시에 두 요청이 들어와도 한 링크만 남긴다.
            raise ApiError("LINK_ALREADY_ISSUED", 409, "이미 개발용 링크가 발급된 안내문입니다.") from exc
        return link, raw_token

    async def get_approved_guide(self, raw_token: str) -> tuple[PatientGuideLink, GuideDocument]:
        link = (
            await PatientGuideLink.filter(token_digest=_digest(raw_token))
            .prefetch_related("guide_document__sections")
            .first()
        )
        if link is None:
            raise _link_not_found()
        if link.expires_at <= now():
            raise ApiError("LINK_EXPIRED", 410, "환자 링크가 만료되었습니다.")

        guide = link.guide_document
        if guide.status is not GuideStatus.SCHEDULED_TO_SEND or guide.approved_at is None:
            # 링크가 있더라도 승인 상태가 아니면 안내 존재 여부를 환자에게 내보내지 않는다.
            raise _link_not_found()
        return link, guide
