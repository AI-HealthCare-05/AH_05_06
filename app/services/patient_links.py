"""환자 링크 발급·조회·재발급·승인 안내 조회 — KEY-90, KEY-219, KEY-241.

KEY-219의 링크 상태·재발급 계약과 KEY-241의 P2~P5 공개 응답을 함께 제공한다.
공개 안내에는 저장 모델에서 직접 확인할 수 있는 값만 보탠다.
"""

import asyncio
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from tortoise.exceptions import IntegrityError
from tortoise.timezone import now

from app.core.auth_errors import AuthError as ApiError
from app.core.masking import mask_phone
from app.core.time import DISPLAY_TIMEZONE, as_utc
from app.models.ocr import OcrField
from app.models.prescriptions import Prescription, PrescriptionItem
from app.models.staffs import Hospital
from app.models.visits import GuideDocument, GuideSectionKey, GuideStatus, PatientGuideLink

LINK_TTL = timedelta(hours=72)
ISSUER_ROLES = frozenset({"staff", "doctor"})
_DRUG_WITH_INGREDIENT = re.compile(r"^(?P<brand>[^()]+?)\((?P<ingredient>[^)]+)\)(?P<suffix>.*)$")


@dataclass(frozen=True, slots=True)
class MedicationProgress:
    prescribed: int
    day_on: int
    remaining: int
    pct: int
    depletion_date: date


@dataclass(frozen=True, slots=True)
class PatientMedicationData:
    drug_name: str
    short_name: str
    ingredient_label: str | None
    directions: str | None
    stat_sub: str | None
    prescribed: int
    progress: MedicationProgress | None


@dataclass(frozen=True, slots=True)
class PatientGuideData:
    visit_date: date
    clinic_name: str | None
    disease_name: str | None
    medication: PatientMedicationData | None
    sections: dict[GuideSectionKey, str]


def _clinic_date(value: datetime) -> date:
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(DISPLAY_TIMEZONE).date()


def calculate_medication_progress(
    *,
    started_at: datetime,
    prescribed_days: int,
    as_of: date | None = None,
) -> MedicationProgress:
    """확정 OCR 작업 시작일부터의 복약 진행률을 0~100으로 제한한다.

    Jira 계약이 정한 시작일은 `Visit.visited_at`이 아니라 최신 확정 OCR 작업의
    `OcrJob.started_at`이다. 그 날을 1일째로 세고, 미래 시작일은 0일째로,
    처방 기간을 지난 경우에는 실제 경과일은 유지하되 진행률과 남은 일수만
    각각 100과 0에서 멈춘다.
    """

    if prescribed_days <= 0:
        raise ValueError("prescribed_days must be positive")

    start_date = _clinic_date(started_at)
    current_date = as_of or now().astimezone(DISPLAY_TIMEZONE).date()
    day_on = max((current_date - start_date).days + 1, 0)
    remaining = max(prescribed_days - day_on, 0)

    # 양수의 일반적인 사사오입. Python round()의 bankers rounding을 쓰면 정확히
    # x.5인 날이 화면 계약과 다르게 짝수 쪽으로 내려갈 수 있다.
    numerator = day_on * 100
    rounded = (2 * numerator + prescribed_days) // (2 * prescribed_days)
    pct = min(max(rounded, 0), 100)
    return MedicationProgress(
        prescribed=prescribed_days,
        day_on=day_on,
        remaining=remaining,
        pct=pct,
        depletion_date=start_date + timedelta(days=prescribed_days),
    )


def _medication_data(
    item: PrescriptionItem,
    *,
    started_at: datetime | None,
    as_of: date,
) -> PatientMedicationData:
    raw_name = item.name.strip()
    matched = _DRUG_WITH_INGREDIENT.match(raw_name)
    if matched:
        brand = matched.group("brand").strip()
        suffix = matched.group("suffix").strip()
        drug_name = " ".join(part for part in (brand, suffix) if part)
        short_name = brand
        ingredient_label = f"성분 · {matched.group('ingredient').strip()}"
    else:
        drug_name = raw_name
        short_name = raw_name
        ingredient_label = None

    prescribed = max(item.duration_days or 0, 0)
    duration = f"{prescribed}일분" if prescribed > 0 else None
    directions = " · ".join(part for part in (item.frequency.strip(), duration) if part) or None
    stat_sub = " · ".join(part for part in (ingredient_label, directions) if part) or None
    progress = (
        calculate_medication_progress(
            started_at=started_at,
            prescribed_days=prescribed,
            as_of=as_of,
        )
        if started_at is not None and prescribed > 0
        else None
    )
    return PatientMedicationData(
        drug_name=drug_name,
        short_name=short_name,
        ingredient_label=ingredient_label,
        directions=directions,
        stat_sub=stat_sub,
        prescribed=prescribed,
        progress=progress,
    )


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
            .prefetch_related("guide_document__sections", "guide_document__visit")
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

    async def get_patient_guide_data(
        self,
        raw_token: str,
    ) -> tuple[PatientGuideLink, GuideDocument, PatientGuideData]:
        """승인 안내와 현재 저장 모델에서 직접 만들 수 있는 화면 데이터만 돌려준다.

        `get_approved_guide()`의 링크·만료·승인 게이트를 먼저 통과한 뒤 조회한다.
        구조화 소스가 없는 목표·챌린지·챗봇 칩은 여기서 지어내지 않는다.
        """

        link, guide = await self.get_approved_guide(raw_token)
        visit = guide.visit
        visit_date = _clinic_date(visit.visited_at)

        # 아래 네 조회는 서로의 결과에 의존하지 않는다. 원격 DB 환경에서
        # 순차 RTT가 환자 화면 지연으로 그대로 더해지지 않도록 함께 실행한다.
        hospital_query = Hospital.filter(hospital_id=visit.hospital_id).first()
        latest_confirmed_field_query = (
            OcrField.filter(
                ocr_result__ocr_job__visit_id=guide.visit_id,
                ocr_result__ocr_job__hospital_id=visit.hospital_id,
                is_confirmed=True,
                confirmed_at__isnull=False,
            )
            .prefetch_related("ocr_result__ocr_job")
            .order_by("-confirmed_at", "-ocr_field_id")
            .first()
        )
        diagnosis_query = (
            OcrField.filter(
                ocr_result__ocr_job__visit_id=guide.visit_id,
                ocr_result__ocr_job__hospital_id=visit.hospital_id,
                field_type="DIAGNOSIS",
                is_confirmed=True,
            )
            .order_by("-confirmed_at", "-ocr_field_id")
            .first()
        )
        prescription_query = Prescription.filter(visit_id=guide.visit_id).prefetch_related("items").first()
        hospital, latest_confirmed_field, diagnosis, prescription = await asyncio.gather(
            hospital_query,
            latest_confirmed_field_query,
            diagnosis_query,
            prescription_query,
        )

        progress_started_at = (
            latest_confirmed_field.ocr_result.ocr_job.started_at if latest_confirmed_field is not None else None
        )
        items = (
            sorted(prescription.items, key=lambda item: item.prescription_item_id) if prescription is not None else []
        )
        primary_item = next(
            (item for item in items if item.duration_days is not None and item.duration_days > 0),
            items[0] if items else None,
        )
        medication = (
            _medication_data(
                primary_item,
                started_at=progress_started_at,
                as_of=now().astimezone(DISPLAY_TIMEZONE).date(),
            )
            if primary_item is not None
            else None
        )

        diagnosis_name = diagnosis.value.strip() if diagnosis is not None and diagnosis.value else None
        disease_name: str | None
        if diagnosis_name and medication:
            disease_name = f"{diagnosis_name} · {medication.short_name} 복용 중"
        elif diagnosis_name:
            disease_name = diagnosis_name
        else:
            # 처방 세트 이름은 확정 진단이 아니다. 와이어프레임 자리를 채우려고
            # 질환명처럼 내보내지 않고, 확정 DIAGNOSIS가 없으면 생략한다.
            disease_name = None

        return (
            link,
            guide,
            PatientGuideData(
                visit_date=visit_date,
                clinic_name=hospital.name if hospital is not None else None,
                disease_name=disease_name,
                medication=medication,
                sections={section.section_key: section.body for section in guide.sections},
            ),
        )
