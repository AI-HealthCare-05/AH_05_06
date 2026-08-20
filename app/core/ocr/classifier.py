import re

from app.core.ocr.schemas import ClassificationResult, ClassifiedBy, DocumentType

SUPPORTED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/bmp",
        "image/webp",
        "application/pdf",
    }
)

# 순서 중요 — 구체적인 패턴을 먼저 검사한다.
# 약봉투는 처방전보다 먼저 검사해야 "복약_처방" 같은 이름이 DRUG_LABEL로 떨어진다.
_FILENAME_RULES: list[tuple[re.Pattern[str], DocumentType]] = [
    (re.compile(r"(drug|약봉투|약봉지|복약|bag)", re.I), DocumentType.DRUG_LABEL),
    (re.compile(r"(prescription|처방전|rx)", re.I), DocumentType.PRESCRIPTION),
    (re.compile(r"(lab|검사|결과지|result|혈액|blood|amh|lh\b|fsh|afp|cbc)", re.I), DocumentType.LAB_RESULT),
    (re.compile(r"(note|소견|메모|초음파|ultrasound|endo)", re.I), DocumentType.CLINICAL_NOTE),
    (re.compile(r"(emr|의무기록|진단|medical|chart|과거기록)", re.I), DocumentType.EMR),
]


def is_supported_mime(mime_type: str) -> bool:
    return mime_type in SUPPORTED_MIME_TYPES


def classify_by_filename(filename: str, mime_type: str) -> ClassificationResult:
    """파일 이름과 MIME 타입으로 문서 유형을 추정한다.

    규칙이 일치하지 않으면 UNCLASSIFIED를 반환한다.
    OCR 텍스트로 재분류하는 단계는 KEY-57 Worker에서 수행한다.
    """
    for pattern, doc_type in _FILENAME_RULES:
        if pattern.search(filename):
            return ClassificationResult(
                document_type=doc_type,
                classified_by=ClassifiedBy.AUTO,
            )
    return ClassificationResult(
        document_type=DocumentType.UNCLASSIFIED,
        classified_by=ClassifiedBy.AUTO,
    )
