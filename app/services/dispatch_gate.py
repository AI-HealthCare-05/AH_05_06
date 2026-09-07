"""발송 직전 게이트 — KEY-250.

안내 미승인 / 생성 전·후 안전검증 미통과 / 원본 의료문서 미삭제 중 하나라도
걸리면 막는다(`HELD`). 막힌 이유는 `GuideMessageHold` 값으로만 돌려준다 —
예외 메시지나 원문을 실어 나르지 않는다.
"""

from pathlib import Path

from app.models.documents import MedicalDocument
from app.models.visits import GuideDocument, GuideMessage, GuideMessageHold


async def gate_hold_reason(message: GuideMessage) -> GuideMessageHold | None:
    """막을 이유가 있으면 그 사유를, 없으면 `None`을 돌려준다."""
    guide = await GuideDocument.filter(guide_document_id=message.guide_document_id).first()
    if guide is None or guide.approved_at is None:
        return GuideMessageHold.NOT_APPROVED

    if not await _source_documents_are_deleted(guide.visit_id):
        return GuideMessageHold.SOURCE_NOT_DELETED

    # 생성 전·후 안전검증 — KEY-250 범위. "생성 전" 쪽은 GuideService.generate()가
    # 확정 OCR 필드 없이는 생성 자체를 막아서(KEY-150), 여기 도달한 GuideDocument는
    # 이미 그 검증을 통과한 상태다. "생성 후" 쪽을 나타내는 필드·이벤트는 코드에서
    # 확인하지 못했다 — 잘못 짐작해서 안전 게이트를 엉성하게 만드는 것보다는
    # 이희진 님 확인 전까지 비워 두는 쪽을 택했다. PR 코멘트에도 남긴다.
    return None


async def _source_documents_are_deleted(visit_id: int) -> bool:
    """이 진료에 딸린 원본 의료문서 파일이 전부 지워졌는가.

    `app/ocr/api.py`의 `get_document_image()`가 삭제 여부를 재는 것과 같은
    방식이다 — 행은 남아도 실제 파일이 없으면 지워진 것으로 본다.
    """
    docs = await MedicalDocument.filter(visit_id=visit_id).all()
    if not docs:
        # 애초에 원본을 올린 적이 없다 — 지울 것도 없으니 막지 않는다.
        return True
    return all(not Path(doc.file_path).exists() for doc in docs)
