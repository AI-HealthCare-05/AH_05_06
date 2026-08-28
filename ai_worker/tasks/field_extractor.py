"""문서 유형별 CLOVA OCR 텍스트 → OcrField 변환 — KEY-56 · KEY-187.

근거: 와이어프레임 S1-6~9 판독 확인 화면, KEY-163 §2 필드 계약.

EMR 문서는 CLOVA 블록 파서(헤더→값 레이아웃)를 우선 사용하고,
블록 파서가 찾지 못한 필드는 정규식(colon-adjacent fallback)으로 보완한다.

인식에 실패한 항목은 결과 목록에서 제외된다 — 스탭이 S1-7 화면에서
직접 입력하거나 「항목 추가」로 보완한다.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from ai_worker.adapters.clova import ClovaOcrResult
from app.models.ocr import OcrDocumentType

# 정규식 단독 매칭값의 신뢰도 (KEY-187: is_low_confidence 임계값 0.75보다 낮게 설정).
# CLOVA 블록에서 직접 읽은 값은 해당 블록의 inferConfidence를 사용한다.
_DEFAULT_CONFIDENCE = Decimal("0.70")


@dataclass
class ExtractedField:
    field_type: str
    extracted_value: str
    confidence: Decimal


# ---------------------------------------------------------------------------
# EMR 블록 파서 상수 — KEY-163 §2, SYN-EMS-01 실측 (PR #147 / KEY-190)
# ---------------------------------------------------------------------------

# 처방 표 열 헤더 텍스트 → field_type 매핑 (KEY-163 §2 계약)
_PRESCRIPTION_COLUMN_HEADERS: dict[str, str] = {
    "약품명": "MEDICATION_NAME",
    "1회량": "DOSAGE",
    "일일횟수": "FREQUENCY",
    "처방일수": "DURATION_DAYS",
}

# 진단 표에서 상병명 값 바로 앞에 오는 헤더 키워드
_DIAGNOSIS_HEADER_KEYWORDS: frozenset[str] = frozenset({"상병명", "진단명"})

# 블록 파서가 값으로 오인하지 않아야 할 알려진 레이블/헤더
_KNOWN_NON_VALUE_TOKENS: frozenset[str] = (
    _DIAGNOSIS_HEADER_KEYWORDS
    | frozenset(_PRESCRIPTION_COLUMN_HEADERS.keys())
    | frozenset({"[진단]", "ICD코드", "주/부상병", "주상병", "부상병", "진료과", "투약구분"})
)


# ---------------------------------------------------------------------------
# 패턴 테이블 — colon-adjacent fallback (와이어프레임 S1-6~9 기준)
# ---------------------------------------------------------------------------

_LAB_PATTERNS: dict[str, re.Pattern[str]] = {
    k: re.compile(v, re.IGNORECASE)
    for k, v in {
        "LAB_DATE": (
            r"검사일\s*[:：]?\s*"
            r"(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2})"
        ),
        "HEMOGLOBIN": r"(?:Hb|혈색소|헤모글로빈)\s*[:：]?\s*([\d.]+\s*g/dL)",
        "CA_125": r"CA[-\s]?125\s*[:：]\s*([\d.]+\s*U/mL)",
        "AMH": (
            r"AMH\s*[:：]\s*"
            r"([\d.]+\s*(?:ng/mL|pmol/L)|추후\s*보고\s*예정|별도\s*보고)"
        ),
        "CA19_9": r"CA[-\s]?19[-\s]?9\s*[:：]\s*([\d.]+\s*U/mL)",
        "E2": r"\bE2\b\s*[:：]\s*([\d.]+\s*pg/mL)",
        "CRP": r"\bCRP\b\s*[:：]\s*([\d.]+\s*mg/L)",
        "ENDOMETRIOMA_SIZE": r"자궁내막종\s*[:：]?\s*([\d.]+\s*cm)",
        "ENDOMETRIAL_THICKNESS": (r"(?:내막\s*두께|자궁내막\s*두께|내막두께)\s*[:：]?\s*([\d.]+\s*cm)"),
        "AST_ALT": r"AST\s*/\s*ALT\s*[:：]\s*([\d]+\s*/\s*[\d]+\s*U/L)",
    }.items()
}

# EMR: colon-adjacent fallback (CLOVA 블록 파서가 실패한 경우에만 사용)
_EMR_PATTERNS: dict[str, re.Pattern[str]] = {
    k: re.compile(v, re.IGNORECASE)
    for k, v in {
        "DIAGNOSIS": r"(?:진단|상병|Dx|diagnosis)\s*[:：]\s*([^\n\r,;]{1,80})",
        "MEDICATION_NAME": (
            r"(?:처방|투약|약제|Rx)\s*[:：]?\s*"
            r"([가-힣A-Za-z]{2,}[가-힣A-Za-z ]*(?:\d+(?:\.\d+)?\s*(?:mg|mcg|g|mL|정|캡슐))?)"
        ),
        "DURATION_DAYS": r"(\d{1,3})\s*일\s*(?:처방|분|치)",
        "DOSAGE": r"1회량\s*[:：]?\s*(\d+(?:\.\d+)?(?:\s*정|\s*캡슐|\s*mL)?)",
        "FREQUENCY": r"(?:일일|하루)\s*(\d+)\s*회",
        "PRESCRIPTION_DATE": (
            r"(?:처방일|처방날짜)\s*[:：]?\s*"
            r"(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2})"
        ),
    }.items()
}

_PRESCRIPTION_PATTERNS: dict[str, re.Pattern[str]] = {
    k: re.compile(v, re.IGNORECASE)
    for k, v in {
        "MEDICATION_NAME": (r"([가-힣A-Za-z]{2,}[가-힣A-Za-z\s]+\d+\s*(?:mg|mcg|g|mL))"),
        "DURATION_DAYS": r"(\d{1,3})\s*일",
        "DOSAGE": r"1회량\s*[:：]?\s*(\d+(?:\.\d+)?(?:\s*정|\s*캡슐|\s*mL)?)",
        "FREQUENCY": r"(?:일일|하루)\s*(\d+)\s*회",
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

    EMR: 블록 파서 우선, 누락 필드는 정규식으로 보완.
    그 외: 정규식만 사용.
    동일 field_type은 첫 번째 매칭만 사용한다.
    """
    if document_type == OcrDocumentType.EMR:
        return _extract_emr(clova_result)

    patterns = _PATTERNS_BY_TYPE.get(document_type)
    if not patterns:
        return []
    return _extract_by_regex(clova_result, patterns)


# ---------------------------------------------------------------------------
# 내부 — EMR 추출
# ---------------------------------------------------------------------------


def _extract_emr(clova_result: ClovaOcrResult) -> list[ExtractedField]:
    """EMR: CLOVA 블록 파서 우선, 누락 필드를 정규식으로 보완."""
    results = _extract_from_clova_blocks(clova_result)
    found_types = {f.field_type for f in results}

    for field in _extract_by_regex(clova_result, _EMR_PATTERNS):
        if field.field_type not in found_types:
            results.append(field)
            found_types.add(field.field_type)

    return results


def _extract_from_clova_blocks(clova_result: ClovaOcrResult) -> list[ExtractedField]:
    """CLOVA 블록 리스트에서 헤더→값 레이아웃으로 EMR 필드를 추출한다.

    SYN-EMS-01 실측 기준 (PR #147 / KEY-190):
      진단 표: 상병명 헤더 → 다음 비헤더 블록이 진단명
      처방 표: [약품명·1회량·일일횟수·처방일수] 연속 → 그 다음 N개 블록이 값
    """
    texts = [f.text.strip() for f in clova_result.fields]
    n = len(texts)
    results: list[ExtractedField] = []

    # 1. 진단명: 상병명/진단명 헤더 → 다음 비헤더 블록
    for i, t in enumerate(texts):
        if t in _DIAGNOSIS_HEADER_KEYWORDS and i + 1 < n:
            candidate = texts[i + 1]
            if candidate not in _KNOWN_NON_VALUE_TOKENS:
                results.append(
                    ExtractedField(
                        field_type="DIAGNOSIS",
                        extracted_value=candidate,
                        confidence=Decimal(str(round(clova_result.fields[i + 1].confidence, 4))),
                    )
                )
            break

    # 2. 처방 표: 연속된 열 헤더 블록 → 오프셋으로 값 블록 추출
    all_pres_headers = set(_PRESCRIPTION_COLUMN_HEADERS.keys())
    for start in range(n):
        run: list[str] = []
        j = start
        while j < n and texts[j] in all_pres_headers:
            run.append(texts[j])
            j += 1
        if len(run) < 2:
            continue
        # run의 마지막 헤더 바로 다음부터 값 블록이 헤더 순서대로 위치한다
        last_header_idx = start + len(run) - 1
        for rank, header_text in enumerate(run):
            value_idx = last_header_idx + 1 + rank
            if value_idx >= n:
                break
            results.append(
                ExtractedField(
                    field_type=_PRESCRIPTION_COLUMN_HEADERS[header_text],
                    extracted_value=texts[value_idx],
                    confidence=Decimal(str(round(clova_result.fields[value_idx].confidence, 4))),
                )
            )
        break  # 첫 번째 처방 표만 처리

    return results


# ---------------------------------------------------------------------------
# 내부 — 정규식 추출 (colon-adjacent fallback)
# ---------------------------------------------------------------------------


def _extract_by_regex(
    clova_result: ClovaOcrResult,
    patterns: dict[str, re.Pattern[str]],
) -> list[ExtractedField]:
    """정규식으로 raw_text에서 필드를 추출한다. 동일 field_type은 첫 번째만 사용."""
    raw_text = clova_result.raw_text or ""
    extracted: list[ExtractedField] = []
    seen: set[str] = set()

    for field_type, pattern in patterns.items():
        if field_type in seen:
            continue
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
        seen.add(field_type)

    return extracted


def _confidence_for(value: str, clova_result: ClovaOcrResult) -> Decimal:
    """추출한 값과 가장 잘 일치하는 CLOVA 블록의 신뢰도를 반환한다.

    일치하는 블록이 없으면 _DEFAULT_CONFIDENCE를 반환한다 (정규식 단독 매칭).
    """
    value_lower = value.lower()
    for field in clova_result.fields:
        text_lower = field.text.lower()
        if value_lower in text_lower or text_lower in value_lower:
            return Decimal(str(round(field.confidence, 4)))
    return _DEFAULT_CONFIDENCE
