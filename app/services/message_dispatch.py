"""예약 문자 발송 파이프라인 — KEY-249.

`GuideMessage(SCHEDULED)` 를 집어서 실제로 보내고 `SENT`/`FAILED` 로 전이시킨다.
`HELD` 는 게이트가 미리 막아 둔 상태만 있다 — 이 파이프라인은 HELD로 만들지
않는다(그 판단은 별도 게이트 작업의 몫이다).
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from tortoise.timezone import now

from app.core.logger import default_logger
from app.models.catalog import MessageTemplate
from app.models.ocr import OcrField
from app.models.patients import Patient
from app.models.staffs import Hospital
from app.models.visits import (
    GuideDocument,
    GuideMessage,
    GuideMessageKind,
    GuideMessageStatus,
    Visit,
)
from app.services.message_templates import DEFAULT_BODY, MessageTemplateKind
from app.services.sms_sender import SmsDeliveryStatus, SmsSender, SmsSendError, SmsSendResult

#: 최대 재시도 횟수. 이걸 넘기면 일시 실패도 영구 실패(FAILED)로 종료한다.
MAX_ATTEMPTS = 5
#: 지수 백오프 시작값(초) — 1차 1분, 2차 2분, 3차 4분 ... 최대 1시간.
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 3600

#: 확인 문자 회차 → 「며칠째」 숫자. app/services/guides.py의 CHECK_DAYS와 같다.
_CHECK_DAY_NUMBER: dict[GuideMessageKind, int] = {
    GuideMessageKind.CHECK_D7: 7,
    GuideMessageKind.CHECK_D15: 15,
    GuideMessageKind.CHECK_D30: 30,
}


def backoff_seconds(attempt: int) -> int:
    """`attempt`번째 실패 뒤 다음 시도까지 기다릴 시간(초)."""
    return min(BACKOFF_BASE_SECONDS * (2 ** max(attempt - 1, 0)), BACKOFF_MAX_SECONDS)


@dataclass(frozen=True)
class DispatchResult:
    guide_message_id: int
    status: GuideMessageStatus


class LinkNotAvailableError(RuntimeError):
    """`{링크}`/`{예약링크}`를 채울 원문 토큰을 얻을 방법이 없을 때.

    `PatientLinkService.issue()`는 스탭 인증(actor)을 전제하고, 이미 링크가
    발급된 안내문은 재발급을 막는다 — `PatientGuideLink` 모델 docstring이
    스스로 「폐기·재발급 정책이 확정되기 전」이라고 적어 둔 대로, 이 정책은
    아직 팀 차원에서 결정되지 않았다.

    발송 직전 원문을 새로 발급/교체하는 방법도 있지만, 그건 링크 보안
    모델(원문을 저장하지 않는다는 원칙)에 손대는 결정이라 이 파이프라인이
    대신 정하지 않는다 — PR 코멘트로 의견만 남기고, 정책이 정해지면 여기를
    채운다. 그때까지는 조용히 깨진 링크를 보내는 대신 명시적으로 실패시킨다.
    """


async def _template_body(hospital_id: int, kind: MessageTemplateKind) -> str:
    row = await MessageTemplate.filter(hospital_id=hospital_id, kind=kind).first()
    return row.body if row is not None and row.body else DEFAULT_BODY[kind]


async def _course_days(visit_id: int) -> int | None:
    """처방일수 — 판독이 확정한 값에서 읽는다 (app/services/guides.py의 같은 이름과 동일 로직).

    **확정된 것만 본다.** 스탭이 아직 확인하지 않은 값을 문구에 쓰면 안 된다.
    """
    row = await OcrField.filter(
        ocr_result__ocr_job__visit_id=visit_id,
        field_type="DURATION_DAYS",
        is_confirmed=True,
    ).first()
    if row is None or not row.value:
        return None
    try:
        days = int(str(row.value).strip())
    except ValueError:
        digits = "".join(ch for ch in str(row.value) if ch.isdigit())
        if not digits:
            return None
        days = int(digits)
    return days if days > 0 else None


async def render_message_body(message: GuideMessage) -> str:
    """이 문자 한 통의 실제 발송 문구를 만든다 — 보낼 때 그 시점 템플릿으로.

    `{링크}`/`{예약링크}`는 채우지 않는다 — 이유는 `LinkNotAvailableError`
    docstring을 본다. 남은 변수만 채운 뒤, 그 둘이 아직도 문구에 남아
    있으면 `LinkNotAvailableError`를 던진다.
    """
    guide = await GuideDocument.filter(guide_document_id=message.guide_document_id).first()
    if guide is None:
        raise ValueError(f"guide_document not found for message {message.guide_message_id}")
    visit = await Visit.filter(visit_id=guide.visit_id).first()
    patient = await Patient.filter(patient_id=visit.patient_id).first() if visit else None
    hospital = await Hospital.filter(hospital_id=guide.hospital_id).first()

    body = await _template_body(guide.hospital_id, MessageTemplateKind(message.kind.value))
    values = {
        "의원명": hospital.name if hospital else "",
        "환자명": patient.name if patient else "",
    }
    if message.kind in _CHECK_DAY_NUMBER:
        values["일차"] = str(_CHECK_DAY_NUMBER[message.kind])
    if message.kind is GuideMessageKind.RUN_OUT:
        days = await _course_days(guide.visit_id)
        values["일수"] = str(days) if days is not None else ""
        remaining = (message.scheduled_at.date() - now().date()).days if visit else None
        values["D"] = str(max(remaining, 0)) if remaining is not None else ""

    for name, value in values.items():
        body = body.replace("{" + name + "}", value)

    if "{링크}" in body or "{예약링크}" in body:
        raise LinkNotAvailableError(f"guide_message_id={message.guide_message_id} kind={message.kind.value}")
    return body


async def _claim(message_id: int, *, at: datetime) -> str | None:
    """SCHEDULED·시각 도래·미점유 행을 원자적으로 붙잡는다 — 멱등키.

    같은 메시지를 두 워커가 동시에 집어도 `claim_token__isnull=True` 조건에
    걸려 한쪽만 영향을 받는다(affected row 1). 진 쪽은 0을 보고 넘어간다 —
    별도 잠금 없이 UPDATE 문 자체의 원자성만으로 막는다.
    """
    token = secrets.token_hex(8)
    affected = await GuideMessage.filter(
        guide_message_id=message_id,
        status=GuideMessageStatus.SCHEDULED,
        claim_token__isnull=True,
        scheduled_at__lte=at,
    ).update(claim_token=token)
    return token if affected == 1 else None


async def dispatch_message(message_id: int, sender: SmsSender) -> DispatchResult | None:
    """문자 한 통을 집어서 보내고 상태를 전이시킨다.

    이미 다른 워커가 집었거나 아직 보낼 시각이 아니면 `None`을 돌려준다 —
    실패가 아니라 「이번엔 내 차례가 아니다」라는 뜻이다.
    """
    moment = now()
    token = await _claim(message_id, at=moment)
    if token is None:
        return None

    message = await GuideMessage.get(guide_message_id=message_id)
    try:
        guide = await GuideDocument.filter(guide_document_id=message.guide_document_id).first()
        visit = await Visit.filter(visit_id=guide.visit_id).first() if guide else None
        patient = await Patient.filter(patient_id=visit.patient_id).first() if visit else None
        if patient is None:
            raise ValueError(f"patient not found for message {message_id}")

        body = await render_message_body(message)
        result = await sender.send(patient.phone, body)
    except LinkNotAvailableError:
        # 재시도해도 정책이 정해지기 전엔 같은 결과다 — 5번 돌 필요 없이 바로 종료한다.
        return await _finish_failed(message, token, provider_detail="link_not_available_pending_policy")
    except SmsSendError as exc:
        return await _finish_retryable(message, token, moment, provider_detail=exc.reason)
    except Exception:
        default_logger.exception("문자 발송 처리 중 예상치 못한 예외 — guide_message_id=%s", message_id)
        return await _finish_retryable(message, token, moment, provider_detail="worker_exception")

    if result.status is SmsDeliveryStatus.SENT:
        return await _finish_sent(message, token, moment, body, result)
    # 공급자가 명시적으로 거절했다 — 재시도해도 같은 결과다. 바로 종료한다.
    return await _finish_failed(message, token, provider_detail=result.provider_code)


async def _finish_sent(
    message: GuideMessage,
    token: str,
    moment: datetime,
    body: str,
    result: SmsSendResult,
) -> DispatchResult:
    affected = await GuideMessage.filter(guide_message_id=message.guide_message_id, claim_token=token).update(
        status=GuideMessageStatus.SENT,
        sent_at=moment,
        sent_body=body,
        provider_message_id=result.provider_message_id,
        provider_detail=None,
        failure_code=None,
        attempt_count=message.attempt_count + 1,
        claim_token=None,
    )
    if affected != 1:
        raise RuntimeError(f"발송 결과 저장 실패: guide_message_id={message.guide_message_id}")
    return DispatchResult(guide_message_id=message.guide_message_id, status=GuideMessageStatus.SENT)


async def _finish_failed(
    message: GuideMessage,
    token: str,
    *,
    provider_detail: str | None,
) -> DispatchResult:
    affected = await GuideMessage.filter(
        guide_message_id=message.guide_message_id,
        claim_token=token,
    ).update(
        status=GuideMessageStatus.FAILED,
        provider_detail=provider_detail,
        attempt_count=message.attempt_count + 1,
        claim_token=None,
    )

    if affected != 1:
        raise RuntimeError(f"발송 결과 저장 실패: guide_message_id={message.guide_message_id}")

    return DispatchResult(
        guide_message_id=message.guide_message_id,
        status=GuideMessageStatus.FAILED,
    )


async def _finish_retryable(
    message: GuideMessage,
    token: str,
    moment: datetime,
    *,
    provider_detail: str,
) -> DispatchResult:
    """일시 실패 — 재시도 여지가 남았으면 다시 예약한다."""
    attempt = message.attempt_count + 1

    if attempt >= MAX_ATTEMPTS:
        return await _finish_failed(
            message,
            token,
            provider_detail=provider_detail,
        )

    next_at = moment + timedelta(seconds=backoff_seconds(attempt))
    affected = await GuideMessage.filter(
        guide_message_id=message.guide_message_id,
        claim_token=token,
    ).update(
        status=GuideMessageStatus.SCHEDULED,
        scheduled_at=next_at,
        provider_detail=provider_detail,
        attempt_count=attempt,
        claim_token=None,
    )

    if affected != 1:
        raise RuntimeError(f"발송 결과 저장 실패: guide_message_id={message.guide_message_id}")

    return DispatchResult(
        guide_message_id=message.guide_message_id,
        status=GuideMessageStatus.SCHEDULED,
    )


async def dispatch_due_messages(sender: SmsSender, *, limit: int = 100) -> list[DispatchResult]:
    """지금 시각 기준으로 나갈 때가 된 문자를 전부 찾아서 하나씩 처리한다."""
    moment = now()
    due_ids: list[int] = await (
        GuideMessage.filter(
            status=GuideMessageStatus.SCHEDULED,
            claim_token__isnull=True,
            scheduled_at__lte=moment,
        )
        .order_by("scheduled_at", "guide_message_id")
        .limit(limit)
        .values_list("guide_message_id", flat=True)
    )  # type: ignore[assignment]
    results = []
    for message_id in due_ids:
        outcome = await dispatch_message(message_id, sender)
        if outcome is not None:
            results.append(outcome)
    return results
