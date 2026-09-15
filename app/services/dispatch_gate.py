"""발송 직전 게이트 — KEY-250, KEY-289.

안내 미승인 / 원본 의료문서 미삭제 / 예약 주소 없음 / 생성 후 안전검증 미통과
또는 승인 목록 밖 수신 번호에 걸리면 막는다(`HELD`). 막힌 이유는 `GuideMessageHold` 값으로만 돌려준다 —
예외 메시지나 원문을 실어 나르지 않는다.
"""

from dataclasses import dataclass

from app.core import config
from app.core.approved_phones import approved_test_phones
from app.core.config import SmsProvider
from app.core.storage import LocalFileStorage, StorageProbe
from app.core.utils.common import normalize_phone_number
from app.models.catalog import MessageTemplateKind
from app.models.documents import MedicalDocument
from app.models.staffs import Hospital
from app.models.visits import (
    GuideDocument,
    GuideMessage,
    GuideMessageHold,
    GuideSafetyCheck,
    SafetyCheckStage,
    SafetyCheckVerdict,
    Visit,
)
from app.services.message_templates import effective_body


@dataclass(frozen=True)
class DispatchGateDecision:
    guide: GuideDocument | None
    hold_reason: GuideMessageHold | None
    #: 🚩 **게이트가 실제로 읽은 문구와 의원** — KEY-331 (이희진 님 #295 리뷰).
    #:
    #: 발송이 이것을 다시 읽으면 **판정과 실제로 나간 글이 갈린다.** 게이트가
    #: 「`{예약링크}` 를 채울 주소가 있다」로 통과시킨 뒤 관리자가 A1-4 에서 그
    #: 주소를 지우면, 발송은 빈 문자열로 채워 「재진 예약을 잡아주세요: 」를
    #: 보낸다 — `BOOKING_URL_MISSING` 이 막으려던 바로 그 문자다. 반대로
    #: D2-5 에서 문구에 `{예약링크}` 를 새로 넣어도 게이트는 그것을 못 본 채
    #: 지나간다.
    #:
    #: 그래서 **본 것을 실어 보낸다.** `guide` 를 이미 그렇게 넘기고 있다.
    body: str | None = None
    hospital: Hospital | None = None


async def evaluate_dispatch_gate(
    message: GuideMessage,
    *,
    storage: StorageProbe | None = None,
) -> DispatchGateDecision:
    """게이트 판정과 그때 읽은 안내문을 함께 돌려준다."""
    guide = await GuideDocument.filter(guide_document_id=message.guide_document_id).first()
    if guide is None or guide.approved_at is None:
        return DispatchGateDecision(guide=guide, hold_reason=GuideMessageHold.NOT_APPROVED)

    backend = storage or LocalFileStorage(config.UPLOAD_DIR)
    if not await _source_documents_are_deleted(guide.visit_id, backend):
        return DispatchGateDecision(guide=guide, hold_reason=GuideMessageHold.SOURCE_NOT_DELETED)

    #: **여기서 한 번만 읽는다.** 아래 판정도, 발송의 렌더도 이 값을 쓴다.
    body = await effective_body(guide.hospital_id, MessageTemplateKind(message.kind.value))
    hospital = await Hospital.filter(hospital_id=guide.hospital_id).first()

    if not _booking_url_is_ready(body, hospital):
        return DispatchGateDecision(
            guide=guide,
            hold_reason=GuideMessageHold.BOOKING_URL_MISSING,
            body=body,
            hospital=hospital,
        )

    # 생성 후 안전검증 — KEY-289.
    # 현재 운영 경로에서는 이 게이트 조건에 도달하지 않는다.
    # POST_GENERATE BLOCK은 안내문 생성 자체를 막으므로(record_failure 참조),
    # guide_document가 존재한다는 것 자체가 POST_GENERATE를 통과했다는 증거다.
    # 사후 비동기 안전검증 흐름이 추가될 때를 대비한 방어 코드로 유지한다.
    if not await _post_generate_safety_check_passed(guide.guide_document_id):
        return DispatchGateDecision(
            guide=guide,
            hold_reason=GuideMessageHold.SAFETY_CHECK_FAILED,
            body=body,
            hospital=hospital,
        )

    # 승인 번호로만 발송 — KEY-338. mock 경로는 기존 동작을 유지한다.
    if config.SMS_PROVIDER is SmsProvider.SOLAPI:
        visit = await Visit.filter(visit_id=guide.visit_id).select_related("patient").first()
        recipient = normalize_phone_number(visit.patient.phone) if visit else ""
        if recipient not in approved_test_phones():
            return DispatchGateDecision(
                guide=guide,
                hold_reason=GuideMessageHold.RECIPIENT_NOT_APPROVED,
                body=body,
                hospital=hospital,
            )

    return DispatchGateDecision(guide=guide, hold_reason=None, body=body, hospital=hospital)


async def gate_hold_reason(
    message: GuideMessage,
    *,
    storage: StorageProbe | None = None,
) -> GuideMessageHold | None:
    """막을 이유가 있으면 그 사유를, 없으면 `None`을 돌려준다."""
    return (await evaluate_dispatch_gate(message, storage=storage)).hold_reason


def _booking_url_is_ready(body: str, hospital: Hospital | None) -> bool:
    """이 문자가 `{예약링크}` 를 쓴다면, 채울 주소가 있는가 — KEY-331.

    **회차가 아니라 문구를 본다.** 기본 문구에서는 소진(`RUN_OUT`)·재진만
    `{예약링크}` 를 쓰지만, 의원은 D2-5 에서 아무 회차 문구에나 그 변수를 넣을
    수 있다(`KNOWN_VARIABLES` 가 전 회차 공통이다). 회차 이름으로 재면 그렇게
    고친 의원의 문자만 빈칸으로 나가고, 그것은 **고친 사람만 겪는 버그**라
    제일 늦게 발견된다.

    **읽지 않고 받는다.** 부르는 쪽이 읽은 문구와 의원을 그대로 넘긴다 — 여기서
    또 읽으면 판정과 발송이 서로 다른 값을 볼 수 있다.
    """
    if "{예약링크}" not in body:
        return True
    return bool(hospital and hospital.booking_url)


async def _post_generate_safety_check_passed(guide_document_id: int) -> bool:
    """POST_GENERATE 안전검증 결과가 BLOCK이면 False를 반환한다 — KEY-289.

    결과 레코드 자체가 없으면 통과로 처리한다. 고정 템플릿 경로는
    POST_GENERATE 결과를 기록하지 않으며, KEY-83 계약상 차단 대상이 아니다.

    현재 운영 경로에서는 이 함수가 False를 반환할 수 없다.
    BLOCK이 나면 안내문이 생성되지 않으므로(record_failure → guide_document=None),
    guide_document_id에 연결된 POST_GENERATE BLOCK 레코드가 존재하지 않는다.
    사후 비동기 안전검증 흐름이 추가되면 비로소 의미를 갖는다.

    형제 함수 _source_documents_are_deleted와 방향이 반대다 — 원본 삭제는
    기록이 없으면(조회 실패 포함) 막고, 이 함수는 기록이 없으면 통과한다.
    원본 삭제는 실시간 파일 존재 여부를 확인할 수 있어 불확실성이 다르고,
    고정 템플릿 경로는 POST_GENERATE 검증 자체를 실행하지 않아 기록 없음이
    곧 「검증 대상 아님」을 뜻한다. 의도된 비대칭이다.
    """
    return not await GuideSafetyCheck.filter(
        guide_document_id=guide_document_id,
        stage=SafetyCheckStage.POST_GENERATE,
        verdict=SafetyCheckVerdict.BLOCK,
    ).exists()


async def _source_documents_are_deleted(visit_id: int, storage: StorageProbe) -> bool:
    """원본 행이 남아 있으면 삭제를 확인할 수 없으므로 발송을 막는다.

    파일 존재는 미삭제이고, 파일 부재는 삭제 이력 없이 삭제를 증명하지
    못한다. 행이 없는 진료만 원본 비연결로 통과한다. 이는 KEY-349가
    명시적인 원본 삭제 완료 기록을 도입하기 전까지 적용하는 fail-closed
    판정이다. 발송 허용을 위해 MedicalDocument 행 자체를 삭제하면 안 된다.
    KEY-349가 삭제 완료 기록을 확정하면 이 함수가 그 기록을 기준으로
    판정하도록 교체한다.
    """
    docs = await MedicalDocument.filter(visit_id=visit_id).all()
    if not docs:
        return True
    return False
