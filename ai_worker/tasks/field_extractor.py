"""문서 유형별 CLOVA OCR 텍스트 → OcrField 변환 — KEY-56 step 6.

근거: 와이어프레임 S1-6~9 판독 확인 화면 (2026-08-25).
패턴 정확도는 8/27 멘토링 후 실제 CLOVA 출력을 확인하고 보정한다.

인식에 실패한 항목은 결과 목록에서 제외된다 — 스탭이 S1-7 화면에서
직접 입력하거나 「항목 추가」로 보완한다.

TODO(8/27 이후):
  - 실제 CLOVA inferText 출력 형식에 맞춰 정규식 패턴 보정
  - 동일 field_type이 복수 문서에서 나올 때 OcrFieldCandidate 생성
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from ai_worker.adapters.clova import ClovaOcrResult
from app.models.ocr import OcrDocumentType

# 정규식으로만 매칭됐을 때 부여하는 기본 신뢰도.
# ClovaTextField에서 일치하는 블록을 찾으면 해당 inferConfidence로 덮어쓴다.
_DEFAULT_CONFIDENCE = Decimal("0.80")


@dataclass
class ExtractedField:
    field_type: str
    extracted_value: str
    confidence: Decimal


# ---------------------------------------------------------------------------
# 패턴 테이블 — 와이어프레임 S1-6~9 기준 (2026-08-25)
# ---------------------------------------------------------------------------

# 검사 결과지 (LAB_RESULT) — 공통 형식: "KEYWORD : VALUE UNIT"
_LAB_PATTERNS: dict[str, re.Pattern[str]] = {
    k: re.compile(v, re.IGNORECASE)
    for k, v in {
        # 검사일
        "LAB_DATE": (
            r"검사일\s*[:：]?\s*"
            r"(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2})"
        ),
        # 혈색소: "Hb : 10.4 g/dL" 또는 "혈색소 10.4 g/dL"
        "HEMOGLOBIN": r"(?:Hb|혈색소|헤모글로빈)\s*[:：]?\s*([\d.]+\s*g/dL)",
        # CA-125
        "CA_125": r"CA[-\s]?125\s*[:：]\s*([\d.]+\s*U/mL)",
        # AMH — "추후 보고 예정" 같은 텍스트도 캡처
        "AMH": (
            r"AMH\s*[:：]\s*"
            r"([\d.]+\s*(?:ng/mL|pmol/L)|추후\s*보고\s*예정|별도\s*보고)"
        ),
        # CA19-9
        "CA19_9": r"CA[-\s]?19[-\s]?9\s*[:：]\s*([\d.]+\s*U/mL)",
        # E2 (에스트라디올)
        "E2": r"\bE2\b\s*[:：]\s*([\d.]+\s*pg/mL)",
        # CRP
        "CRP": r"\bCRP\b\s*[:：]\s*([\d.]+\s*mg/L)",
        # 자궁내막종 크기
        "ENDOMETRIOMA_SIZE": r"자궁내막종\s*[:：]?\s*([\d.]+\s*cm)",
        # 내막 두께
        "ENDOMETRIAL_THICKNESS": (r"(?:내막\s*두께|자궁내막\s*두께|내막두께)\s*[:：]?\s*([\d.]+\s*cm)"),
        # 간수치 AST/ALT
        "AST_ALT": r"AST\s*/\s*ALT\s*[:：]\s*([\d]+\s*/\s*[\d]+\s*U/L)",
    }.items()
}

# EMR 기록 — 진단·처방 소견 텍스트
# 와이어프레임 주석: "소견에서 판독" — 자유 형식이라 패턴 정확도가 낮을 수 있다
_EMR_PATTERNS: dict[str, re.Pattern[str]] = {
    k: re.compile(v, re.IGNORECASE)
    for k, v in {
        # 진단: "진단: 자궁내막증", "Dx: endometriosis"
        "DIAGNOSIS": r"(?:진단|상병|Dx|diagnosis)\s*[:：]\s*([^\n\r,;]{1,80})",
        # 처방약명: "처방: 비잔 2mg"
        "PRESCRIPTION_NAME": (
            r"(?:처방|투약|약제|Rx)\s*[:：]?\s*"
            r"([가-힣A-Za-z][가-힣A-Za-z\s]*(?:\d+\s*mg)?)"
        ),
        # 처방일수: "84일 처방"
        "PRESCRIPTION_DURATION": r"(\d{1,3})\s*일\s*(?:처방|분|치)",
        # 처방일
        "PRESCRIPTION_DATE": (
            r"(?:처방일|처방날짜)\s*[:：]?\s*"
            r"(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2})"
        ),
    }.items()
}

# 처방전 (PRESCRIPTION) — 비교적 구조화된 양식
_PRESCRIPTION_PATTERNS: dict[str, re.Pattern[str]] = {
    k: re.compile(v, re.IGNORECASE)
    for k, v in {
        # 약품명+용량: "비잔 2mg"
        "PRESCRIPTION_NAME": (r"([가-힣A-Za-z][가-힣A-Za-z\s]+\d+\s*(?:mg|mcg|g|mL))"),
        # 투약일수
        "PRESCRIPTION_DURATION": r"(\d{1,3})\s*일",
        # 처방·발행일
        "PRESCRIPTION_DATE": (
            r"(?:처방일|발행일|조제일)\s*[:：]?\s*"
            r"(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2})"
        ),
    }.items()
}

_PATTERNS_BY_TYPE: dict[OcrDocumentType, dict[str, re.Pattern[str]]] = {
    OcrDocumentType.LAB_RESULT: _LAB_PATTERNS,
    OcrDocumentType.EMR: _EMR_PATTERNS,
    OcrDocumentType.PRESCRIPTION: _PRESCRIPTION_PATTERNS,
}


# ---------------------------------------------------------------------------
# 공개 인터페이스
# ---------------------------------------------------------------------------


def extract_fields(
    clova_result: ClovaOcrResult,
    document_type: OcrDocumentType,
) -> list[ExtractedField]:
    """CLOVA 결과에서 문서 유형에 맞는 핵심 필드를 추출한다.

    매칭되지 않은 항목은 결과에서 제외된다.
    동일 field_type은 첫 번째 매칭만 사용한다 (중복 처리는 8/27 이후 OcrFieldCandidate로 확장).
    """
    patterns = _PATTERNS_BY_TYPE.get(document_type)
    if not patterns:
        return []

    raw_text = clova_result.raw_text or ""
    extracted: list[ExtractedField] = []

    for field_type, pattern in patterns.items():
        match = pattern.search(raw_text)
        if not match:
            continue
        value = match.group(1).strip()
        if not value:
            continue
        extracted.append(
            ExtractedField(
                field_type=field_type,
                extracted_value=value,
                confidence=_confidence_for(value, clova_result),
            )
        )

    return extracted


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _confidence_for(value: str, clova_result: ClovaOcrResult) -> Decimal:
    """추출한 값과 가장 잘 일치하는 CLOVA 텍스트 블록의 신뢰도를 반환한다.

    일치하는 블록이 없으면 기본값(_DEFAULT_CONFIDENCE)을 반환한다.
    """
    value_lower = value.lower()
    for field in clova_result.fields:
        text_lower = field.text.lower()
        if value_lower in text_lower or text_lower in value_lower:
            return Decimal(str(round(field.confidence, 4)))
    return _DEFAULT_CONFIDENCE
