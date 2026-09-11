"""발송 직전 게이트 — KEY-250.

안내 미승인 / 생성 전·후 안전검증 미통과 / 원본 의료문서 미삭제 / 예약 주소
없음 중 하나라도 걸리면 막는다(`HELD`). 막힌 이유는 `GuideMessageHold` 값으로만 돌려준다 —
예외 메시지나 원문을 실어 나르지 않는다.
"""

from dataclasses import dataclass

from app.core import config
from app.core.storage import LocalFileStorage, StorageProbe
from app.models.catalog import MessageTemplateKind
from app.models.documents import MedicalDocument
from app.models.staffs import Hospital
from app.models.visits import GuideDocument, GuideMessage, GuideMessageHold
from app.services.message_templates import effective_body


@dataclass(frozen=True)
class DispatchGateDecision:
    guide: GuideDocument | None
    hold_reason: GuideMessageHold | None


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

    if not await _booking_url_is_ready(guide.hospital_id, message):
        return DispatchGateDecision(guide=guide, hold_reason=GuideMessageHold.BOOKING_URL_MISSING)

    # 생성 전·후 안전검증 — KEY-250 범위. "생성 전" 쪽은 GuideService.generate()가
    # 확정 OCR 필드 없이는 생성 자체를 막아서(KEY-150), 여기 도달한 GuideDocument는
    # 이미 그 검증을 통과한 상태다. "생성 후" 쪽을 나타내는 필드·이벤트는 코드에서
    # 확인하지 못했다 — 잘못 짐작해서 안전 게이트를 엉성하게 만드는 것보다는
    # 이희진 님 확인 전까지 비워 두는 쪽을 택했다. PR 코멘트에도 남긴다.
    return DispatchGateDecision(guide=guide, hold_reason=None)


async def gate_hold_reason(
    message: GuideMessage,
    *,
    storage: StorageProbe | None = None,
) -> GuideMessageHold | None:
    """막을 이유가 있으면 그 사유를, 없으면 `None`을 돌려준다."""
    return (await evaluate_dispatch_gate(message, storage=storage)).hold_reason


async def _booking_url_is_ready(hospital_id: int, message: GuideMessage) -> bool:
    """이 문자가 `{예약링크}` 를 쓴다면, 채울 주소가 있는가 — KEY-331.

    **회차가 아니라 문구를 본다.** 기본 문구에서는 소진(`RUN_OUT`)·재진만
    `{예약링크}` 를 쓰지만, 의원은 D2-5 에서 아무 회차 문구에나 그 변수를 넣을
    수 있다(`KNOWN_VARIABLES` 가 전 회차 공통이다). 회차 이름으로 재면 그렇게
    고친 의원의 문자만 빈칸으로 나가고, 그것은 **고친 사람만 겪는 버그**라
    제일 늦게 발견된다.

    발송이 읽을 문구와 같은 것을 읽는다(`effective_body`) — 여기서 표를 따로
    읽으면 게이트가 잰 글과 실제로 나간 글이 갈린다.
    """
    body = await effective_body(hospital_id, MessageTemplateKind(message.kind.value))
    if "{예약링크}" not in body:
        return True
    hospital = await Hospital.filter(hospital_id=hospital_id).first()
    return bool(hospital and hospital.booking_url)


async def _source_documents_are_deleted(visit_id: int, storage: StorageProbe) -> bool:
    """이 진료에 딸린 원본 의료문서 파일이 전부 지워졌는가.

    저장소 조회가 실패하면 삭제됐다고 추측하지 않고 발송을 막는다. 상대
    경로·권한 오류·지원하지 않는 저장소를 파일 부재로 오인하면 안 된다.
    """
    docs = await MedicalDocument.filter(visit_id=visit_id).all()
    if not docs:
        # 애초에 원본을 올린 적이 없다 — 지울 것도 없으니 막지 않는다.
        return True
    try:
        for doc in docs:
            if await storage.exists(doc.file_path):
                return False
        return True
    except (OSError, RuntimeError, ValueError):
        return False
