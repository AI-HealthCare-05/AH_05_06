"""발송 직전 게이트 — KEY-250, KEY-289.

안내 미승인 / 원본 의료문서 미삭제 / 예약 주소 없음 / 생성 후 안전검증 미통과
또는 승인 목록 밖 수신 번호에 걸리면 막는다(`HELD`). 막힌 이유는 `GuideMessageHold` 값으로만 돌려준다 —
예외 메시지나 원문을 실어 나르지 않는다.
"""

from dataclasses import dataclass

from app.core import config
from app.core.approved_phones import approved_test_phones
from app.core.config import SmsProvider
from app.core.sms_opt_out import is_opted_out
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
    #: 아직 삭제 기록이 없는 원본 문서 id — KEY-349.
    #:
    #: 게이트 자신은 이 목록이 비어 있지 않아도 막지 않는다(그게 곧
    #: "삭제할 차례"라는 뜻이다) — 실제 삭제·확인·기록은
    #: `message_dispatch.dispatch_message()`가 이 목록을 받아서 실행한다.
    #: 게이트가 직접 지우지 않는 이유는 하나다 — 여기서 막힐 다른
    #: 이유(미승인 등)가 남아 있으면 원본을 먼저 지우면 안 된다. 이
    #: 목록이 채워지는 시점엔 이미 그 다른 게이트를 전부 통과했다는
    #: 뜻이라 안전하다.
    pending_source_document_ids: tuple[int, ...] = ()
    source_failure_type: str | None = None


async def evaluate_dispatch_gate(
    message: GuideMessage,
    *,
    storage: StorageProbe | None = None,
    recover_sources: bool = False,
) -> DispatchGateDecision:
    """게이트 판정과 그때 읽은 안내문을 함께 돌려준다."""
    guide = await GuideDocument.filter(guide_document_id=message.guide_document_id).first()
    if guide is None or guide.approved_at is None:
        return DispatchGateDecision(guide=guide, hold_reason=GuideMessageHold.NOT_APPROVED)

    backend = storage or LocalFileStorage(config.UPLOAD_DIR)
    try:
        mismatch, pending_ids = await _source_deletion_state(guide.visit_id, backend)
    except (OSError, ValueError):
        return DispatchGateDecision(
            guide=guide,
            hold_reason=GuideMessageHold.SOURCE_NOT_DELETED,
            source_failure_type="STORAGE_UNAVAILABLE",
        )
    if recover_sources:
        # Re-verify every source, including a deletion record whose file reappeared.
        pending_ids = tuple(doc.document_id for doc in await MedicalDocument.filter(visit_id=guide.visit_id).all())
        mismatch = False
    if mismatch:
        return DispatchGateDecision(
            guide=guide,
            hold_reason=GuideMessageHold.SOURCE_NOT_DELETED,
            source_failure_type="DELETION_RECORD_MISMATCH",
        )

    #: **여기서 한 번만 읽는다.** 아래 판정도, 발송의 렌더도 이 값을 쓴다.
    body = await effective_body(
        guide.hospital_id,
        MessageTemplateKind(message.kind.value),
        guide_document_id=guide.guide_document_id,
    )
    hospital = await Hospital.filter(hospital_id=guide.hospital_id).first()

    if not _booking_url_is_ready(body, hospital):
        return DispatchGateDecision(
            guide=guide,
            hold_reason=GuideMessageHold.BOOKING_URL_MISSING,
            body=body,
            hospital=hospital,
            pending_source_document_ids=pending_ids,
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
            pending_source_document_ids=pending_ids,
        )

    # 문자 수신 거부 — KEY-355. provider와 무관하게 늘 본다(mock도 포함) —
    # 이건 시연 안전장치가 아니라 실제 환자 사실이다. 업무 목록에서 이미
    # 이 진료를 뺐으니(front_desk.py), 화면에 안 보이는 진료의 예약
    # 문자가 뒤에서 몰래 나가면 안 된다.
    visit = await Visit.filter(visit_id=guide.visit_id).select_related("patient").first()
    if visit is not None and is_opted_out(visit):
        return DispatchGateDecision(
            guide=guide,
            hold_reason=GuideMessageHold.SMS_OPT_OUT,
            body=body,
            hospital=hospital,
            pending_source_document_ids=pending_ids,
        )

    # 승인 번호로만 발송 — KEY-338. mock 경로는 기존 동작을 유지한다.
    if config.SMS_PROVIDER is SmsProvider.SOLAPI:
        recipient = normalize_phone_number(visit.patient.phone) if visit else ""
        if recipient not in approved_test_phones():
            return DispatchGateDecision(
                guide=guide,
                hold_reason=GuideMessageHold.RECIPIENT_NOT_APPROVED,
                body=body,
                hospital=hospital,
                pending_source_document_ids=pending_ids,
            )

    return DispatchGateDecision(
        guide=guide, hold_reason=None, body=body, hospital=hospital, pending_source_document_ids=pending_ids
    )


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

    형제 함수 _source_deletion_state와 방향이 반대다 — 원본 삭제는
    기록이 없으면 오히려 통과시키고(그 자리에서 지울 차례로 보고한다,
    KEY-349) 기록과 실제가 어긋날 때만 막는다. 이 함수는 반대로 기록이
    없으면 통과, 기록이 BLOCK이면 막는다. 원본 삭제는 실시간 파일 존재
    여부를 확인할 수 있어 불확실성이 다르고, 고정 템플릿 경로는
    POST_GENERATE 검증 자체를 실행하지 않아 기록 없음이 곧 「검증 대상
    아님」을 뜻한다. 의도된 비대칭이다.
    """
    return not await GuideSafetyCheck.filter(
        guide_document_id=guide_document_id,
        stage=SafetyCheckStage.POST_GENERATE,
        verdict=SafetyCheckVerdict.BLOCK,
    ).exists()


async def _source_deletion_state(visit_id: int, storage: StorageProbe) -> tuple[bool, tuple[int, ...]]:
    """원본 삭제 판정을 기록 기준으로 낸다 — KEY-349.

    (막혔는가, 아직 지워야 할 문서 id들)을 돌려준다.

    행               삭제 기록   파일       판정
    없음             —          —          통과, 지울 것 없음
    있음             없음       있음/없음  통과, 이 문서를 지울 차례로 보고한다
    있음             있음       없음       통과, 지울 것 없음
    있음             있음       있음       막는다 — 기록과 실제가 어긋난다

    저장소 조회 자체가 실패하면(권한 오류 등) 그대로 올려 보낸다 —
    `evaluate_dispatch_gate`를 부르는 `dispatch_message`가 그 예외를
    이미 재시도 경로로 잡는다(fail-closed, 여기서 새로 감싸지 않는다).
    """
    docs = await MedicalDocument.filter(visit_id=visit_id).all()
    pending: list[int] = []
    for doc in docs:
        if doc.source_deleted_at is None:
            pending.append(doc.document_id)
            continue
        if await storage.exists(doc.file_path):
            return True, ()
    return False, tuple(pending)
