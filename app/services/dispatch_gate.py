"""발송 직전 게이트 — KEY-250.

안내 미승인 / 생성 전·후 안전검증 미통과 / 원본 의료문서 미삭제 중 하나라도
걸리면 막는다(`HELD`). 막힌 이유는 `GuideMessageHold` 값으로만 돌려준다 —
예외 메시지나 원문을 실어 나르지 않는다.
"""

from dataclasses import dataclass

from app.core import config
from app.core.storage import LocalFileStorage, StorageProbe
from app.models.documents import MedicalDocument
from app.models.visits import GuideDocument, GuideMessage, GuideMessageHold


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
