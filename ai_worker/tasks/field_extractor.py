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
        # ── KEY-234: 판독이 읽어야 하는 스물한 항목 ──────────────────────
        #
        # 증상 — 사람이 물어 적는 값이라 표현이 제각각이다. 「있다/없다」로
        # 굳혀 담는다: 화면이 고르는 칸으로 받는 것과 같은 어휘여야 한다.
        "PAIN_SCORE": r"생리통\s*[:：]?\s*(\d{1,2})\s*점?",
        "HEAVY_BLEEDING": r"생리\s*과다\s*[:：]?\s*(있(?:다|음)|없(?:다|음)|유|무)",
        "IRREGULAR_CYCLE": r"(?:불규칙\s*월경|월경\s*불규칙)\s*[:：]?\s*(있(?:다|음)|없(?:다|음)|유|무)",
        # 초음파 — 본 것
        "ADENOMYOSIS_SIZE": r"(?:선근증|자궁\s*크기)\s*[:：]?\s*([\d.]+\s*cm)",
        "MYOMA_SIZE": r"근종\s*크기\s*[:：]?\s*([\d.]+\s*cm)",
        "MYOMA_COUNT": r"근종\s*개수\s*[:：]?\s*(\d{1,2})\s*개?",
        "ADNEXAL_CYST_LEFT": (
            r"(?:난소\s*)?부속기\s*혹\s*\(?\s*(?:왼쪽|좌|Lt)\s*\)?\s*[:：]?\s*"
            r"(있(?:다|음)\s*[\d.]+\s*cm|있(?:다|음)|없(?:다|음)|[\d.]+\s*cm)"
        ),
        "ADNEXAL_CYST_RIGHT": (
            r"(?:난소\s*)?부속기\s*혹\s*\(?\s*(?:오른쪽|우|Rt)\s*\)?\s*[:：]?\s*"
            r"(있(?:다|음)\s*[\d.]+\s*cm|있(?:다|음)|없(?:다|음)|[\d.]+\s*cm)"
        ),
        # 혈액 — 뽑아 잰 것. AST 와 ALT 를 **따로** 읽는다: 예전 `AST_ALT` 는
        # 한 칸에 둘을 담아서 한쪽만 고칠 수가 없었다.
        "AST": r"\bAST\b(?!\s*/)\s*[:：]\s*([\d.]+\s*(?:U/L)?)",
        "ALT": r"\bALT\b\s*[:：]\s*([\d.]+\s*(?:U/L)?)",
        "LH_FSH_RATIO": r"LH\s*/\s*FSH(?:\s*비율)?\s*[:：]\s*([\d.]+(?:\s*[:/]\s*[\d.]+)?)",
        "DHEA_S": r"DHEA[-\s]?S\b\s*[:：]\s*([\d.]+\s*(?:[µu]g/dL)?)",
        "TESTOSTERONE": r"(?:Testosterone|테스토스테론)\s*[:：]\s*([\d.]+\s*(?:ng/dL)?)",
        "PROLACTIN": r"(?:Prolactin|프로락틴)\s*[:：]\s*([\d.]+\s*(?:ng/mL)?)",
        "TSH": r"\bTSH\b\s*[:：]\s*([\d.]+\s*(?:[µu]IU/mL)?)",
        "T3": r"\bT3\b\s*[:：]\s*([\d.]+\s*(?:pg/mL)?)",
        "T4": r"\bT4\b\s*[:：]\s*([\d.]+\s*(?:ng/dL)?)",
        "PROGESTERONE": r"(?:Progesterone|프로게스테론)\s*[:：]\s*([\d.]+\s*(?:ng/mL)?)",
    }.items()
}

# EMR: colon-adjacent fallback (CLOVA 블록 파서가 실패한 경우에만 사용)
_EMR_PATTERNS: dict[str, re.Pattern[str]] = {
    k: re.compile(v, re.IGNORECASE)
    for k, v in {
        "DIAGNOSIS": r"(?:진단|상병|Dx|diagnosis)\s*[:：]\s*([^\n\r,;]{1,80})",
        "MEDICATION_NAME": (
            r"(?:처방|투약|약제|Rx)\s*[:：]?\s*"
            r"([가-힣A-Za-z]{2,}(?:\s?\d+(?:\.\d+)?\s*(?:mg|mcg|g|mL|정|캡슐))?)"
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
        "MEDICATION_NAME": (r"([가-힣A-Za-z]{2,}(?:\s?\d+(?:\.\d+)?\s*(?:mg|mcg|g|mL|정|캡슐)))"),
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
# LAB_RESULT 표 파서 상수
# ---------------------------------------------------------------------------

_TEST_NAME_COLUMN_KEYWORDS: frozenset[str] = frozenset({"검사항목", "검사명", "항목명"})
_RESULT_COLUMN_KEYWORDS: frozenset[str] = frozenset({"검사결과", "결과", "측정값"})

# 검사항목 열 텍스트 → field_type 매핑 (순서 중요: 더 구체적인 패턴을 앞에)
_LAB_TEST_NAME_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"CA[-\s]?19[-\s]?9", re.I), "CA19_9"),
    (re.compile(r"CA[-\s]?125", re.I), "CA_125"),
    (re.compile(r"\bROMA\b", re.I), "ROMA_SCORE"),
    (re.compile(r"\bAMH\b", re.I), "AMH"),
    (re.compile(r"\bHemoglobin\b|혈색소|헤모글로빈|\bHb\b", re.I), "HEMOGLOBIN"),
    (re.compile(r"\bCRP\b", re.I), "CRP"),
    (re.compile(r"\bE2\b", re.I), "E2"),
    (re.compile(r"\bAST\b(?!\s*/)", re.I), "AST"),
    (re.compile(r"\bALT\b", re.I), "ALT"),
    (re.compile(r"LH\s*/\s*FSH", re.I), "LH_FSH_RATIO"),
    (re.compile(r"\bLH\b", re.I), "LH"),
    (re.compile(r"\bFSH\b", re.I), "FSH"),
    (re.compile(r"\bDHEA[-\s]?S\b", re.I), "DHEA_S"),
    (re.compile(r"Testosterone|테스토스테론", re.I), "TESTOSTERONE"),
    (re.compile(r"Prolactin|프로락틴", re.I), "PROLACTIN"),
    (re.compile(r"\bTSH\b", re.I), "TSH"),
    (re.compile(r"\bT3\b", re.I), "T3"),
    (re.compile(r"\bT4\b", re.I), "T4"),
    (re.compile(r"Progesterone|프로게스테론", re.I), "PROGESTERONE"),
    (re.compile(r"자궁내막종", re.I), "ENDOMETRIOMA_SIZE"),
    (re.compile(r"내막\s*두께|자궁내막\s*두께", re.I), "ENDOMETRIAL_THICKNESS"),
]

_COL_MARGIN = 5.0  # px — 열 경계 허용 오차


# ---------------------------------------------------------------------------
# 공개 인터페이스
# ---------------------------------------------------------------------------


def extract_fields(
    clova_result: ClovaOcrResult,
    document_type: OcrDocumentType,
) -> list[ExtractedField]:
    """CLOVA 결과에서 문서 유형에 맞는 핵심 필드를 추출한다.

    EMR: 블록 파서 우선, 누락 필드는 정규식으로 보완.
    LAB_RESULT: 표 파서 우선, 누락 필드는 정규식으로 보완.
    그 외: 정규식만 사용.
    동일 field_type은 첫 번째 매칭만 사용한다.
    """
    if document_type == OcrDocumentType.EMR:
        return _extract_emr(clova_result)
    if document_type == OcrDocumentType.LAB_RESULT:
        return _extract_lab(clova_result)

    patterns = _PATTERNS_BY_TYPE.get(document_type)
    if not patterns:
        return []
    return _extract_by_regex(clova_result, patterns)


# ---------------------------------------------------------------------------
# 내부 — LAB_RESULT 추출
# ---------------------------------------------------------------------------


def _match_lab_test_name(test_name: str) -> str | None:
    """검사항목 텍스트를 field_type으로 변환한다. 매칭 실패 시 None."""
    for pattern, field_type in _LAB_TEST_NAME_KEYWORDS:
        if pattern.search(test_name):
            return field_type
    return None


def _find_lab_columns(rows: list) -> tuple[int, tuple[float, float], tuple[float, float]] | None:
    """헤더 행에서 '검사항목'과 '검사결과' 열의 (header_row_idx, tn_col, res_col)을 반환한다.

    두 열을 모두 찾지 못하면 None을 반환한다.
    """
    tn_col: tuple[float, float] | None = None
    res_col: tuple[float, float] | None = None
    header_row_idx: int | None = None
    for i, row in enumerate(rows):
        for block in row:
            text = block.text.strip()
            if text in _TEST_NAME_COLUMN_KEYWORDS and tn_col is None:
                tn_col = (block.left, block.right)
                header_row_idx = i
            elif text in _RESULT_COLUMN_KEYWORDS and res_col is None:
                res_col = (block.left, block.right)
                if header_row_idx is None:
                    header_row_idx = i
        if tn_col and res_col:
            break
    if header_row_idx is None or tn_col is None or res_col is None:
        return None
    return header_row_idx, tn_col, res_col


def _extract_lab_table(rows: list) -> list[ExtractedField]:
    """바운딩 박스 행 그룹에서 검사항목→결과 쌍을 추출한다.

    헤더 행에서 '검사항목'과 '검사결과' 열 위치를 확인한 뒤,
    각 데이터 행에서 해당 열에 속하는 블록을 골라 (검사명, 결과값) 쌍을 만든다.
    헤더가 없거나 열 위치를 특정할 수 없으면 빈 리스트를 반환한다.
    """
    col_info = _find_lab_columns(rows)
    if col_info is None:
        return []

    header_row_idx, tn_col, res_col = col_info
    tn_l, tn_r = tn_col[0] - _COL_MARGIN, tn_col[1] + _COL_MARGIN
    res_l, res_r = res_col[0] - _COL_MARGIN, res_col[1] + _COL_MARGIN

    results: list[ExtractedField] = []
    seen: set[str] = set()
    for row in rows[header_row_idx + 1 :]:
        tn_blocks = [b for b in row if b.right > tn_l and b.left < tn_r]
        res_blocks = [b for b in row if b.right > res_l and b.left < res_r]
        if not tn_blocks or not res_blocks:
            continue
        test_name = " ".join(b.text.strip() for b in tn_blocks).strip()
        result_value = " ".join(b.text.strip() for b in res_blocks).strip()
        if not test_name or not result_value:
            continue
        field_type = _match_lab_test_name(test_name)
        if field_type is None or field_type in seen:
            continue
        seen.add(field_type)
        avg_conf = sum(b.confidence for b in res_blocks) / len(res_blocks)
        results.append(
            ExtractedField(
                field_type=field_type,
                extracted_value=result_value,
                confidence=Decimal(str(round(avg_conf, 4))),
            )
        )
    return results


def _extract_lab(clova_result: ClovaOcrResult) -> list[ExtractedField]:
    """LAB_RESULT: 표 파서 우선, 누락 필드는 정규식으로 보완."""
    results = _extract_lab_table(clova_result.rows) if clova_result.rows else []
    found_types = {f.field_type for f in results}
    for field in _extract_by_regex(clova_result, _LAB_PATTERNS):
        if field.field_type not in found_types:
            results.append(field)
            found_types.add(field.field_type)
    return results


# ---------------------------------------------------------------------------
# 내부 — EMR 추출
# ---------------------------------------------------------------------------


def _extract_emr(clova_result: ClovaOcrResult) -> list[ExtractedField]:
    """EMR: CLOVA 블록 파서 우선, 누락 필드를 정규식과 검사결과지 표 파서로 보완.

    모든 문서가 EMR 기본값으로 업로드되므로, 검사결과지도 이 경로를 탄다.
    표 헤더가 있으면 표 파서를, 없으면 정규식 fallback을 시도한다.
    """
    results = _extract_from_clova_blocks(clova_result)
    found_types = {f.field_type for f in results}

    for field in _extract_by_regex(clova_result, _EMR_PATTERNS):
        if field.field_type not in found_types:
            results.append(field)
            found_types.add(field.field_type)

    # 검사결과지 표 파서 — 표 헤더(검사항목·검사결과)가 있을 때만 실행된다
    for field in _extract_lab_table(clova_result.rows):
        if field.field_type not in found_types:
            results.append(field)
            found_types.add(field.field_type)

    # 검사결과지 정규식 fallback — 콜론 형식 값을 추가로 읽는다
    for field in _extract_by_regex(clova_result, _LAB_PATTERNS):
        if field.field_type not in found_types:
            results.append(field)
            found_types.add(field.field_type)

    return results


def _extract_from_clova_blocks(clova_result: ClovaOcrResult) -> list[ExtractedField]:
    """CLOVA 블록 리스트에서 헤더→값 레이아웃으로 EMR 필드를 추출한다.

    SYN-EMS-01 실측 기준 (PR #147 / KEY-190):
      진단 표: 상병명/진단명 헤더 → 다음 비헤더 블록이 진단명
      처방 표: 처방 열 헤더들이 연속 구간을 이루어야 한다. 마지막 헤더 다음부터
               등장 순서대로 값 블록이 위치한다. 헤더 구간 안에 비헤더 블록이
               끼이면 positional 매핑이 틀리므로 파서 전체를 건너뛴다(safe-fail).
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

    # 2. 처방 표
    results.extend(_extract_prescription_fields(texts, clova_result.fields))
    return results


def _extract_prescription_fields(
    texts: list[str],
    fields: list,
) -> list[ExtractedField]:
    """처방 표에서 헤더→값 positional 매핑으로 필드를 추출한다.

    헤더가 연속 구간을 이루어야만 파싱을 진행한다. 헤더 구간 안에 비헤더 블록이
    끼이면 safe-fail로 빈 리스트를 반환한다.
    """
    n = len(texts)
    header_positions: dict[str, int] = {}
    for i, t in enumerate(texts):
        if t in _PRESCRIPTION_COLUMN_HEADERS and t not in header_positions:
            header_positions[t] = i

    if len(header_positions) < 2:
        return []

    ordered_headers = sorted(header_positions.items(), key=lambda x: x[1])
    first_header_pos = ordered_headers[0][1]
    last_header_pos = ordered_headers[-1][1]

    header_span = texts[first_header_pos : last_header_pos + 1]
    if not all(t in _PRESCRIPTION_COLUMN_HEADERS for t in header_span):
        return []

    results: list[ExtractedField] = []
    for rank, (header_text, _) in enumerate(ordered_headers):
        value_idx = last_header_pos + 1 + rank
        if value_idx >= n:
            break
        value = texts[value_idx]
        field_type = _PRESCRIPTION_COLUMN_HEADERS[header_text]
        if not value or value in _KNOWN_NON_VALUE_TOKENS:
            continue
        if field_type == "DURATION_DAYS" and not re.search(r"\d", value):
            continue
        if field_type == "MEDICATION_NAME" and not re.search(r"[가-힣A-Za-z]", value):
            continue
        results.append(
            ExtractedField(
                field_type=field_type,
                extracted_value=value,
                confidence=Decimal(str(round(fields[value_idx].confidence, 4))),
            )
        )
    return results


# ---------------------------------------------------------------------------
# 내부 — 정규식 추출 (colon-adjacent fallback)
# ---------------------------------------------------------------------------


def _extract_by_regex(
    clova_result: ClovaOcrResult,
    patterns: dict[str, re.Pattern[str]],
) -> list[ExtractedField]:
    """정규식으로 raw_text에서 필드를 추출한다."""
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


def _confidence_for(value: str, clova_result: ClovaOcrResult) -> Decimal:
    """추출한 값과 가장 잘 일치하는 CLOVA 블록의 신뢰도를 반환한다.

    완전 일치를 먼저 탐색하고, 3자 이상인 경우만 포함 관계로 fallback한다.
    짧은 숫자("1", "84" 등)의 오매칭으로 is_low_confidence가 잘못 판정되는 것을 방지한다.
    일치하는 블록이 없으면 _DEFAULT_CONFIDENCE를 반환한다 (정규식 단독 매칭).
    """
    value_lower = value.lower()
    for field in clova_result.fields:
        if field.text.lower() == value_lower:
            return Decimal(str(round(field.confidence, 4)))
    if len(value_lower) >= 3:
        for field in clova_result.fields:
            text_lower = field.text.lower()
            if value_lower in text_lower or text_lower in value_lower:
                return Decimal(str(round(field.confidence, 4)))
    return _DEFAULT_CONFIDENCE
