"""예약 문자 발송 파이프라인 — KEY-249, KEY-250, KEY-297.

`GuideMessage(SCHEDULED)` 를 집어서 발송 직전 게이트(`dispatch_gate.py`)를
먼저 거친다. 막히면 `HELD`, 통과하면 실제로 보내고 `SENT`/`FAILED` 로
전이시킨다. 시도·성공·실패·보류 네 갈래를 전부 append-only 감사 이벤트로
남긴다(`GuideMessageEvent`) — KEY-250.

`{링크}`/`{예약링크}`가 든 문구는 보내는 그 순간 원문을 새로 발급한다
(`PatientLinkService.issue_for_dispatch`) — 예약 승인 시점에 미리 만들어
두지 않는다. 원문은 워커 메모리에서 문구를 만드는 동안에만 살아 있다.
"""

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from tortoise.timezone import now

from app.core import config
from app.core.logger import default_logger
from app.core.time import DISPLAY_TIMEZONE
from app.models.catalog import MessageTemplate
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, course_days
from app.models.patients import Patient
from app.models.staffs import Hospital
from app.models.visits import (
    GuideDocument,
    GuideMessage,
    GuideMessageEvent,
    GuideMessageEventType,
    GuideMessageFailure,
    GuideMessageHold,
    GuideMessageKind,
    GuideMessageStatus,
    Visit,
)
from app.services.dispatch_gate import evaluate_dispatch_gate
from app.services.message_templates import DEFAULT_BODY, MessageTemplateKind
from app.services.patient_links import PatientLinkService
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


#: 환자 링크가 여는 화면 경로 — `frontend/js/link-token.js`의 조각(`#t=`) 규칙과
#: 맞춘다. 조각은 서버 요청·access log에 남지 않는다.
_LINK_PATH = "/patient_wireframe/html/otp.html#t={token}"
#: secrets.token_urlsafe(32)는 항상 정확히 43자다(32바이트를 패딩 없는
#: base64url로 인코딩한 길이) — `+`나 `{43,}` 같은 열린 길이 대신 정확한
#: 길이를 쓴다. `#t=` 바로 뒤가 시작점이라 앞쪽 경계는 이미 확실하고,
#: 뒤쪽은 정확히 43자에서 멈추므로 병원이 "{링크}1회용"처럼 구분자 없이
#: 붙여 써도 그 뒤 글자를 삼키지 않는다.
#:
#: app/core/masking.py의 URLSAFE_TOKEN({43,} + \b 경계)을 그대로 쓰지
#: 않는다 — 재현해 보니 그쪽은 이 경우에 오히려 더 나쁘게 실패한다.
#: 토큰 바로 뒤에 한글이 오면(예: "1회용") Python 정규식에서 한글이
#: \w로 잡혀서 경계(\b) 자체를 못 찾고 **아예 매칭이 안 된다** — 일부만
#: 삼키는 게 아니라 토큰이 통째로 안 가려진다(2heej 리뷰 이후 직접
#: 재현). 여기서는 위치를 이미 알아서(`#t=` 뒤) 경계 추측이 필요 없다.
_LINK_TOKEN_IN_BODY = re.compile(r"(?<=#t=)[A-Za-z0-9_-]{43}")


def _absolute_link_url(raw_token: str) -> str:
    base = config.PATIENT_WEB_BASE_URL.rstrip("/")
    return base + _LINK_PATH.format(token=raw_token)


def _body_for_storage(body: str) -> str:
    """Keep the sent text for support without retaining a patient link token."""

    return _LINK_TOKEN_IN_BODY.sub("[REDACTED]", body)


def _format_expiry(expires_at: datetime) -> str:
    """환자에게 보이는 만료 시각 — "9월 8일 15시" 모양."""
    local = expires_at.astimezone(DISPLAY_TIMEZONE)
    return f"{local.month}월 {local.day}일 {local.hour}시"


async def _template_body(hospital_id: int, kind: MessageTemplateKind) -> str:
    row = await MessageTemplate.filter(hospital_id=hospital_id, kind=kind).first()
    return row.body if row is not None and row.body else DEFAULT_BODY[kind]


async def _course_days(visit_id: int) -> int | None:
    """처방일수 — **최신 비제외 COMPLETED job** 의 확정 값에서 읽는다.

    제외·이전 job 이 섞이면 소진 문자 날짜와 {일수} 변수가 어긋난다.
    예: job1(84일)→job2(28일) 재판독 후 job1 을 제외해도
    필터 없이 first() 하면 84일 기준으로 문자 본문이 채워진다.
    `guides.py` 의 같은 이름과 동일 로직 — 두 함수가 다르면 발송 날짜와
    문자 본문이 달라진다.
    """
    latest_job = (
        await OcrJob.filter(
            visit_id=visit_id,
            excluded_from_guide=False,
            status=OcrJobStatus.COMPLETED,
        )
        .order_by("-created_at")
        .first()
    )
    if latest_job is None:
        return None
    row = await OcrField.filter(
        ocr_result__ocr_job=latest_job,
        field_type="DURATION_DAYS",
        is_confirmed=True,
    ).first()
    if row is None:
        return None
    # 판독이 읽은 숫자가 총투(통)일 수 있다 — `unit` 이 그것을 말한다.
    return course_days(row.value, row.unit)


async def render_message_body(
    message: GuideMessage,
    *,
    guide: GuideDocument | None = None,
    visit: Visit | None = None,
) -> str:
    """이 문자 한 통의 실제 발송 문구를 만든다 — 보낼 때 그 시점 템플릿으로.

    `{링크}`/`{예약링크}`가 문구에 있으면 그때 원문을 새로 발급한다(KEY-297).
    원문은 이 함수 안에서 완성된 문자열에 섞일 뿐 별도로 저장하지 않는다.
    """
    guide = guide or await GuideDocument.filter(guide_document_id=message.guide_document_id).first()
    if guide is None:
        raise ValueError(f"guide_document not found for message {message.guide_message_id}")
    visit = visit or await Visit.filter(visit_id=guide.visit_id).first()
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

    if "{링크}" in body or "{예약링크}" in body:
        raw_token, expires_at = await PatientLinkService().issue_for_dispatch(
            guide.guide_document_id,
            message.guide_message_id,
            message.kind,
        )
        link = _absolute_link_url(raw_token)
        values["링크"] = link
        values["예약링크"] = link
        values["만료일"] = _format_expiry(expires_at)

    for name, value in values.items():
        body = body.replace("{" + name + "}", value)
    return body


async def _log_event(message_id: int, event_type: GuideMessageEventType, *, reason: str | None = None) -> None:
    """감사 이벤트 한 줄을 남긴다 — append-only(KEY-250). update·delete는 안 쓴다.

    `reason`은 못박힌 값(`GuideMessageHold`·`GuideMessageFailure`)이나 짧은
    내부 코드 문자열만 받는다 — 예외 메시지·본문을 그대로 옮기지 않는다.
    """
    await GuideMessageEvent.create(guide_message_id=message_id, event_type=event_type, reason=reason)


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
        await _log_event(message_id, GuideMessageEventType.ATTEMPTED)
        gate = await evaluate_dispatch_gate(message)
    except Exception:
        default_logger.exception("문자 발송 게이트 처리 중 예상치 못한 예외 — guide_message_id=%s", message_id)
        return await _finish_retryable(message, token, moment, provider_detail="worker_exception")

    if gate.hold_reason is not None:
        return await _finish_held(message, token, gate.hold_reason)

    try:
        guide = gate.guide
        visit = await Visit.filter(visit_id=guide.visit_id).first() if guide else None
        patient = await Patient.filter(patient_id=visit.patient_id).first() if visit else None
        if patient is None:
            raise ValueError(f"patient not found for message {message_id}")

        body = await render_message_body(message, guide=guide, visit=visit)
        result = await sender.send(patient.phone, body)
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
        sent_body=_body_for_storage(body),
        provider_message_id=result.provider_message_id,
        provider_detail=None,
        failure_code=None,
        attempt_count=message.attempt_count + 1,
        claim_token=None,
    )
    if affected != 1:
        raise RuntimeError(f"발송 결과 저장 실패: guide_message_id={message.guide_message_id}")
    # sent_body(원문 링크 포함)를 절대 여기 남기지 않는다 — reason 없이 SENT만 남긴다.
    await _log_event(message.guide_message_id, GuideMessageEventType.SENT)
    return DispatchResult(guide_message_id=message.guide_message_id, status=GuideMessageStatus.SENT)


async def _finish_held(message: GuideMessage, token: str, hold_reason: GuideMessageHold) -> DispatchResult:
    affected = await GuideMessage.filter(
        guide_message_id=message.guide_message_id,
        claim_token=token,
    ).update(
        status=GuideMessageStatus.HELD,
        hold_reason=hold_reason,
        claim_token=None,
    )
    if affected != 1:
        raise RuntimeError(f"발송 결과 저장 실패: guide_message_id={message.guide_message_id}")
    await _log_event(message.guide_message_id, GuideMessageEventType.HELD, reason=hold_reason.value)
    return DispatchResult(guide_message_id=message.guide_message_id, status=GuideMessageStatus.HELD)


def _failure_code_for(provider_detail: str | None) -> GuideMessageFailure:
    """`provider_detail`(내부 전용 원시 사유)을 화면·CSV export에 보이는
    4값(GuideMessageFailure) 중 하나로 옮긴다.

    실제 알리고 result_code별 의미를 담은 공식 표가 없어서, 지금은 전부
    `CARRIER`(「통신사 오류」)로 본다 — 그중 어느 것도 「이 번호가
    잘못됐다」·「수신 거부됐다」·「발신번호가 미등록이다」라고 확신할
    근거가 없기 때문이다. 틀린 확신을 화면에 내보내는 것보다는 모호하게
    맞는 말을 하는 쪽을 골랐다(2heej 리뷰).

    `link_not_available_pending_policy`(PR 코멘트 참고)도 여기로
    떨어지는데, 이건 사실 통신사 문제가 전혀 아니다 — 정책이 아직
    확정되지 않아 우리 쪽에서 링크를 못 만든 것이다. 넷 중 아무것도 안
    맞아서 어쩔 수 없이 여기 둔다 — 실제 원인은 `provider_detail`(내부
    전용, 화면에 안 보임)로 구분한다.
    """
    return GuideMessageFailure.CARRIER


async def _finish_failed(
    message: GuideMessage,
    token: str,
    *,
    provider_detail: str | None,
) -> DispatchResult:
    failure_code = _failure_code_for(provider_detail)
    affected = await GuideMessage.filter(
        guide_message_id=message.guide_message_id,
        claim_token=token,
    ).update(
        status=GuideMessageStatus.FAILED,
        failure_code=failure_code,
        provider_detail=provider_detail,
        attempt_count=message.attempt_count + 1,
        claim_token=None,
    )

    if affected != 1:
        raise RuntimeError(f"발송 결과 저장 실패: guide_message_id={message.guide_message_id}")

    await _log_event(message.guide_message_id, GuideMessageEventType.FAILED, reason=failure_code.value)
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
        try:
            outcome = await dispatch_message(message_id, sender)
        except Exception:
            # 한 통 처리 중 예상치 못한 예외(예: claim_token 불일치 RuntimeError)가
            # 나머지 배치까지 이번 주기에서 밀어내면 안 된다 — 메시지끼리는
            # 서로 독립적이다(2heej 리뷰).
            default_logger.exception("문자 한 통 처리 중 예상치 못한 예외 — guide_message_id=%s", message_id)
            continue
        if outcome is not None:
            results.append(outcome)
    return results
