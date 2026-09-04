"""환자 링크 발급·조회·재발급·승인 안내 조회 — KEY-90, KEY-219, KEY-241.

KEY-219의 링크 상태·재발급 계약과 KEY-241의 P2~P5 공개 응답을 함께 제공한다.
공개 안내에는 저장 모델에서 직접 확인할 수 있는 값만 보탠다.
"""

import asyncio
import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.timezone import now

from app.core.auth_errors import AuthError as ApiError
from app.core.masking import mask_phone
from app.core.time import DISPLAY_TIMEZONE, as_utc
from app.models.catalog import BaselineDirection, LabBaseline, PrescriptionSet, SetDisease
from app.models.ocr import OcrField
from app.models.prescriptions import Prescription, PrescriptionItem, ordered_prescription_items
from app.models.staffs import Hospital
from app.models.visits import GuideDocument, GuideSectionKey, GuideStatus, PatientGuideLink

LINK_TTL = timedelta(hours=72)
ISSUER_ROLES = frozenset({"staff", "doctor"})
_DRUG_WITH_INGREDIENT = re.compile(r"^(?P<brand>[^()]+?)\((?P<ingredient>[^)]+)\)(?P<suffix>.*)$")
_LAB_KEY = re.compile(r"[^0-9a-z가-힣]+")
_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
LOGGER = logging.getLogger("app.patient_links")


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
class PatientGuideGoalData:
    name: str
    current: str | None
    target: str | None
    has_chart: bool
    range_label: str | None


@dataclass(frozen=True, slots=True)
class PatientGuideData:
    visit_date: date
    clinic_name: str | None
    disease_name: str | None
    #: 환자 전체 이름. 응답에 넣을지(= OTP 인증 여부)는 라우터가 정한다 — KEY-268.
    patient_name: str | None
    medication: PatientMedicationData | None
    goals: list[PatientGuideGoalData]
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


def _normalize_lab_key(value: str) -> str:
    return _LAB_KEY.sub("", value.casefold())


def _confirmed_diseases(value: str | None) -> set[SetDisease]:
    normalized = _normalize_lab_key(value or "")
    diseases: set[SetDisease] = set()
    if "pcos" in normalized or "다낭성" in normalized:
        diseases.add(SetDisease.PCOS)
    if "endometriosis" in normalized or "자궁내막증" in normalized:
        diseases.add(SetDisease.ENDOMETRIOSIS)
    return diseases


def _decimal_from_lab(value: str | None, *, unit: str = "") -> Decimal | None:
    if not value:
        return None
    normalized = value.replace(",", "")
    matches = list(_NUMBER.finditer(normalized))
    if not matches:
        return None

    # "2차 10.4 g/dL"처럼 검사 회차가 앞에 붙을 수 있다. 단위가 있으면 그
    # 단위 바로 앞의 숫자를 우선하고, 없으면 마지막 숫자를 측정값으로 본다.
    matched = matches[-1]
    if unit := unit.strip():
        unit_pattern = re.compile(rf"({_NUMBER.pattern})\s*{re.escape(unit)}", re.IGNORECASE)
        unit_matches = list(unit_pattern.finditer(normalized))
        if unit_matches:
            matched = unit_matches[-1]
    try:
        return Decimal(matched.group(1) if matched.lastindex else matched.group())
    except InvalidOperation:
        return None


def _display_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _baseline_label(baseline: LabBaseline) -> str | None:
    low = baseline.low
    high = baseline.high
    unit = f" {baseline.unit.strip()}" if baseline.unit.strip() else ""
    if baseline.by_age:
        return "연령별 기준"
    if low is not None and high is not None:
        return f"기준 {_display_decimal(low)}~{_display_decimal(high)}{unit}"
    if low is not None:
        return f"기준 {_display_decimal(low)}{unit} 이상"
    if high is not None:
        return f"기준 {_display_decimal(high)}{unit} 미만"
    return None


def _target_for_baseline(baseline: LabBaseline, current: Decimal | None) -> Decimal | None:
    if current is None or baseline.by_age or baseline.direction is BaselineDirection.REFERENCE:
        return None
    low = baseline.low
    high = baseline.high
    if low is not None and high is not None:
        if current < low:
            return low
        if current > high:
            return high
        # 단일 목표점 계약으로 정상 범위를 억지로 한 숫자로 축약하지 않는다.
        return None
    return low if low is not None else high


def _goal_data(baseline: LabBaseline, field: OcrField) -> PatientGuideGoalData:
    current = _decimal_from_lab(field.value, unit=baseline.unit)
    target = _target_for_baseline(baseline, current)
    return PatientGuideGoalData(
        name=baseline.name,
        current=_display_decimal(current) if current is not None else None,
        target=_display_decimal(target) if target is not None else None,
        has_chart=current is not None and target is not None,
        range_label=_baseline_label(baseline),
    )


def _match_goals(
    baselines: list[LabBaseline],
    confirmed_fields: list[OcrField],
) -> list[PatientGuideGoalData]:
    goals: list[PatientGuideGoalData] = []
    for baseline in baselines:
        alias_keys = {
            normalized
            for alias in (baseline.name, *baseline.keywords.split(","))
            if (normalized := _normalize_lab_key(alias))
        }
        matched_field = None
        # confirmed_fields는 최신순이다. 별칭 선언 순서가 아니라 모든 별칭을
        # 통틀어 가장 최근에 확정된 필드를 선택한다.
        for field in confirmed_fields:
            if _normalize_lab_key(field.field_type) in alias_keys:
                matched_field = field
                break
        if matched_field is not None:
            goals.append(_goal_data(baseline, matched_field))
        else:
            LOGGER.warning(
                "patient guide baseline did not match a confirmed OCR field",
                extra={
                    "hospital_id": baseline.hospital_id,
                    "lab_baseline_id": baseline.lab_baseline_id,
                    "baseline_name": baseline.name,
                },
            )
    return goals


def _confirmed_fields_query(*, visit_id: int, hospital_id: int):
    return OcrField.filter(
        ocr_result__ocr_job__visit_id=visit_id,
        ocr_result__ocr_job__hospital_id=hospital_id,
        is_confirmed=True,
        confirmed_at__isnull=False,
    ).order_by("-confirmed_at", "-ocr_field_id")


def _select_baselines(
    baselines: list[LabBaseline],
    *,
    diseases: set[SetDisease],
    doctor_id: int | None,
) -> list[LabBaseline]:
    selected: list[LabBaseline] = []
    for disease in (SetDisease.PCOS, SetDisease.ENDOMETRIOSIS):
        if disease not in diseases:
            continue
        disease_rows = [baseline for baseline in baselines if baseline.disease is disease]
        doctor_rows = [baseline for baseline in disease_rows if baseline.doctor_id == doctor_id]
        selected.extend(doctor_rows or [baseline for baseline in disease_rows if baseline.doctor_id is None])
    return selected


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
        return await self.get_approved_guide_by_digest(digest_link_token(raw_token))

    async def get_approved_guide_by_digest(self, token_digest: str) -> tuple[PatientGuideLink, GuideDocument]:
        """Load the approved guide selected by an authenticated patient session."""

        link = (
            await PatientGuideLink.filter(token_digest=token_digest)
            .prefetch_related("guide_document__sections", "guide_document__visit__patient")
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

        # 아래 다섯 조회는 서로의 결과에 의존하지 않는다. 원격 DB 환경에서
        # 순차 RTT가 환자 화면 지연으로 그대로 더해지지 않도록 함께 실행한다.
        hospital_query = Hospital.filter(hospital_id=visit.hospital_id).first()
        confirmed_fields_query = _confirmed_fields_query(
            visit_id=guide.visit_id,
            hospital_id=visit.hospital_id,
        ).prefetch_related("ocr_result__ocr_job")
        prescription_query = Prescription.filter(visit_id=guide.visit_id).prefetch_related("items").first()
        prescription_sets_query = PrescriptionSet.all()
        baselines_query = LabBaseline.filter(
            Q(doctor_id=visit.doctor_id) | Q(doctor_id=None),
            hospital_id=visit.hospital_id,
            disease__in=(SetDisease.PCOS, SetDisease.ENDOMETRIOSIS),
        ).order_by("position", "lab_baseline_id")
        hospital, confirmed_fields, prescription, prescription_sets, baselines = await asyncio.gather(
            hospital_query,
            confirmed_fields_query,
            prescription_query,
            prescription_sets_query,
            baselines_query,
        )
        latest_confirmed_field = confirmed_fields[0] if confirmed_fields else None
        diagnosis = next(
            (field for field in confirmed_fields if field.field_type == "DIAGNOSIS"),
            None,
        )

        progress_started_at = (
            latest_confirmed_field.ocr_result.ocr_job.started_at if latest_confirmed_field is not None else None
        )
        items = ordered_prescription_items(prescription)
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
        diseases = _confirmed_diseases(diagnosis_name)
        if diagnosis_name and prescription is not None:
            prescription_set = next(
                (row for row in prescription_sets if row.name == prescription.prescription_set),
                None,
            )
            if prescription_set is not None:
                diseases.add(prescription_set.disease)
        goals: list[PatientGuideGoalData] = []
        if diseases:
            selected_baselines = _select_baselines(
                list(baselines),
                diseases=diseases,
                doctor_id=visit.doctor_id,
            )
            goals = _match_goals(selected_baselines, list(confirmed_fields))

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
                patient_name=(visit.patient.name or None),
                medication=medication,
                goals=goals,
                sections={section.section_key: section.body for section in guide.sections},
            ),
        )
