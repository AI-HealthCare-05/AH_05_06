"""CLOVA 결과를 KEY-276 지식 적재 OCR 계약으로 변환한다."""

from ai_worker.adapters.clova import call_clova_ocr
from app.services.knowledge_extraction import OcrTextBlock


class ClovaKnowledgeOcrExtractor:
    async def extract(self, payload: bytes, mime_type: str) -> tuple[OcrTextBlock, ...]:
        result = await call_clova_ocr(payload, mime_type)
        if not result.raw_text.strip():
            return ()
        boxes = tuple(
            {
                "x": field.left,
                "y": field.top,
                "width": max(0.0, field.right - field.left),
                "height": max(0.0, field.bottom - field.top),
            }
            for field in result.fields
        )
        confidence = sum(field.confidence for field in result.fields) / len(result.fields) if result.fields else None
        return (
            OcrTextBlock(
                text=result.raw_text,
                page_number=1,
                bounding_boxes=boxes,
                confidence=confidence,
            ),
        )
