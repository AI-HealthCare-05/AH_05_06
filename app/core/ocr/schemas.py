from enum import StrEnum

from pydantic import BaseModel


class DocumentType(StrEnum):
    EMR = "EMR"  # 의무기록·과거기록
    CLINICAL_NOTE = "CLINICAL_NOTE"  # 소견·메모·초음파
    LAB_RESULT = "LAB_RESULT"  # 검사 결과지
    PRESCRIPTION = "PRESCRIPTION"  # 처방전
    DRUG_LABEL = "DRUG_LABEL"  # 약봉투
    UNCLASSIFIED = "UNCLASSIFIED"  # 미분류 — OCR 후 재판정


class ClassifiedBy(StrEnum):
    AUTO = "AUTO"  # 서버 자동 분류
    MANUAL = "MANUAL"  # 사용자 직접 지정


class ClassificationResult(BaseModel):
    document_type: DocumentType
    classified_by: ClassifiedBy
    confidence: float | None = None


class ClovaOCRField(BaseModel):
    infer_text: str
    infer_confidence: float
    line_break: bool = False


class ClovaOCRImageResult(BaseModel):
    uid: str
    name: str
    infer_result: str  # "SUCCESS" | "FAILURE"
    message: str = ""
    fields: list[ClovaOCRField] = []

    @property
    def raw_text(self) -> str:
        parts: list[str] = []
        for f in self.fields:
            parts.append(f.infer_text)
            parts.append("\n" if f.line_break else " ")
        return "".join(parts).strip()
