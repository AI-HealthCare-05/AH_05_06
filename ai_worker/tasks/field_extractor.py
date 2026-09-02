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
# EMR 상병명 표 파서 상수 — 구조: 코드|명칭|과목|수술|주상병|...
# ---------------------------------------------------------------------------

# 상병명 표 헤더 식별: "코드"와 "명칭" 두 열이 함께 있는 행
_DIAG_TABLE_HEADER_SET: frozenset[str] = frozenset({"코드", "명칭"})
_DIAG_NAME_COL_LABEL: str = "명칭"

# 진단 키워드 패턴
_ENDO_RE = re.compile(r"자궁\s*내막\s*증", re.IGNORECASE)
# 다낭성(정확한 표기)과 다난성(오타 형태) 모두 인식
_PCOS_RE = re.compile(r"다[낭난]성\s*난소|PCOS", re.IGNORECASE)

# 상병명 표 열 허용 오차 (px) — 헤더 텍스트보다 넓은 데이터 셀 양쪽에 추가
_DIAG_COL_MARGIN = 5.0

# ---------------------------------------------------------------------------
# EMR 처방 표 파서 상수 — 구조: 처방코드|명칭|용량|일투|총투|...|코드분류
# ---------------------------------------------------------------------------

# 처방 표에서 찾아야 할 열 헤더
_RX_NAME_LABELS: frozenset[str] = frozenset({"명칭", "품명"})
_RX_TOTAL_LABELS: frozenset[str] = frozenset({"총투"})
# CLOVA OCR이 원외 체크박스 마크를 읽지 못하는 경우가 있으므로,
# '코드분류' 열에서 약품 행을 식별한다 (내복약·외용약·주사 등).
_RX_CLASS_LABELS: frozenset[str] = frozenset({"코드분류"})
_RX_MED_CLASSES: frozenset[str] = frozenset({"내복약", "외용약", "주사약", "주사"})

# 비잔정 패턴 — 이 약의 총투 값에 28을 곱해서 처방일수를 계산한다
_BIZANJUNG_RE = re.compile(r"비잔\s*정", re.IGNORECASE)


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
        # 콜론을 필수로 요구해 「처방점검」·「처방전View」 같은 복합 토큰을 오추출하지 않는다
        "MEDICATION_NAME": (
            r"(?:처방|투약|약제|Rx)\s*[:：]\s*"
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


def _find_diag_name_col(rows: list) -> tuple[int, tuple[float, float]] | None:
    """상병명 표 헤더 행에서 '명칭' 열 범위 (행 인덱스, (left, right))를 반환한다.

    '명칭' 텍스트 블록의 너비는 실제 데이터 셀보다 훨씬 좁다.
    열 우측 경계는 헤더 행에서 '명칭' 바로 오른쪽에 있는 다음 헤더 블록의
    left 값으로 결정한다 — 이렇게 해야 '난소의 자궁내막증' 같은 긴 데이터
    텍스트가 열 범위 안에 들어온다.
    """
    for i, row in enumerate(rows):
        texts_in_row = {b.text.strip() for b in row}
        if not _DIAG_TABLE_HEADER_SET.issubset(texts_in_row):
            continue
        sorted_row = sorted(row, key=lambda b: b.left)
        name_block = next((b for b in sorted_row if b.text.strip() == _DIAG_NAME_COL_LABEL), None)
        if name_block is None:
            continue
        # 다음 헤더 블록의 left를 열 우측 경계로 사용한다
        next_block = next((b for b in sorted_row if b.left > name_block.right), None)
        col_right = next_block.left if next_block else name_block.right + 200.0
        return i, (name_block.left, col_right)
    return None


def _scan_diag_rows(rows: list, header_row_idx: int, name_l: float, name_r: float) -> tuple[bool, bool, float, int]:
    """상병명 데이터 행을 훑어 (has_endo, has_pcos, total_conf, block_count)를 반환한다."""
    has_endo = has_pcos = False
    total_conf = 0.0
    block_count = 0
    for row in rows[header_row_idx + 1 :]:
        name_blocks = [b for b in row if b.right > name_l and b.left < name_r]
        if not name_blocks:
            continue
        name_text = " ".join(b.text.strip() for b in name_blocks).strip()
        if not name_text:
            continue
        if _ENDO_RE.search(name_text):
            has_endo = True
        if _PCOS_RE.search(name_text):
            has_pcos = True
        for b in name_blocks:
            total_conf += b.confidence
            block_count += 1
    return has_endo, has_pcos, total_conf, block_count


def _extract_emr_diagnosis_table(rows: list) -> list[ExtractedField]:
    """EMR 상병명 표에서 진단 키워드를 찾아 DIAGNOSIS 필드를 반환한다.

    헤더 행에 '코드'와 '명칭'이 함께 있어야 상병명 표로 인식한다.
    자궁내막증 → "자궁내막증" / 다낭성·PCOS → "다낭성난소증후군(PCOS)" / 둘 다 → "둘 다"
    """
    if not rows:
        return []
    info = _find_diag_name_col(rows)
    if info is None:
        return []
    header_row_idx, name_col = info
    name_l = name_col[0] - _DIAG_COL_MARGIN
    name_r = name_col[1] + _DIAG_COL_MARGIN

    has_endo, has_pcos, total_conf, block_count = _scan_diag_rows(rows, header_row_idx, name_l, name_r)
    if not has_endo and not has_pcos:
        return []

    if has_endo and has_pcos:
        value = "둘 다"
    elif has_endo:
        value = "자궁내막증"
    else:
        value = "다낭성난소증후군(PCOS)"

    conf = Decimal(str(round(total_conf / block_count, 4))) if block_count else _DEFAULT_CONFIDENCE
    return [ExtractedField(field_type="DIAGNOSIS", extracted_value=value, confidence=conf)]


def _find_rx_columns(
    rows: list,
) -> tuple[int, tuple[float, float], tuple[float, float] | None, tuple[float, float]] | None:
    """처방 표 헤더 행에서 명칭·총투·코드분류 열 위치를 반환한다.

    CLOVA OCR이 원외 체크박스 마크를 읽지 못하는 경우가 많으므로,
    '코드분류' 열로 약품 행을 식별하는 방식을 사용한다.
    헤더 행에 '명칭'과 '코드분류'가 함께 있을 때 처방 표로 인식한다.
    """
    for i, row in enumerate(rows):
        found: dict[str, tuple[float, float]] = {}
        for b in row:
            t = b.text.strip()
            if t in _RX_NAME_LABELS and "명칭" not in found:
                found["명칭"] = (b.left, b.right)
            elif t in _RX_TOTAL_LABELS and "총투" not in found:
                found["총투"] = (b.left, b.right)
            elif t in _RX_CLASS_LABELS and "코드분류" not in found:
                found["코드분류"] = (b.left, b.right)
        if "명칭" in found and "코드분류" in found:
            return i, found["명칭"], found.get("총투"), found["코드분류"]
    return None


def _rx_duration(med_name: str, total_l: float, total_r: float, row: list) -> ExtractedField | None:
    """처방 행에서 총투 값을 읽어 처방일수 필드를 만든다."""
    total_blocks = [b for b in row if b.right > total_l and b.left < total_r]
    if not total_blocks:
        return None
    total_text = " ".join(b.text.strip() for b in total_blocks).strip()
    m = re.search(r"(\d+)", total_text)
    if not m:
        return None
    total_int = int(m.group(1))
    days = total_int * 28 if _BIZANJUNG_RE.search(med_name) else total_int
    return ExtractedField(field_type="DURATION_DAYS", extracted_value=str(days), confidence=_DEFAULT_CONFIDENCE)


def _extract_emr_rx_table(rows: list) -> list[ExtractedField]:
    """EMR 처방 표에서 약품 행의 약품명과 처방일수를 추출한다.

    '코드분류' 열 값이 약품 분류(내복약·외용약·주사 등)인 행만 처리한다.
    CLOVA OCR이 원외 체크박스를 읽지 못하는 문제를 우회하는 방식이다.
    비잔정: DURATION_DAYS = 총투 × 28 / 그 외: DURATION_DAYS = 총투.
    여러 약품 행 → MEDICATION_NAME, MEDICATION_NAME_2, MEDICATION_NAME_3 …
    """
    if not rows:
        return []
    info = _find_rx_columns(rows)
    if info is None:
        return []
    header_row_idx, name_col, total_col, class_col = info

    name_l, name_r = name_col[0] - _COL_MARGIN, name_col[1] + _COL_MARGIN
    total_l = (total_col[0] - _COL_MARGIN) if total_col else None
    total_r = (total_col[1] + _COL_MARGIN) if total_col else None
    class_l, class_r = class_col[0] - _COL_MARGIN, class_col[1] + _COL_MARGIN

    results: list[ExtractedField] = []
    med_index = 0

    for row in rows[header_row_idx + 1 :]:
        class_blocks = [b for b in row if b.right > class_l and b.left < class_r]
        if not class_blocks:
            continue
        class_text = " ".join(b.text.strip() for b in class_blocks).strip()
        if class_text not in _RX_MED_CLASSES:
            continue

        name_blocks = [b for b in row if b.right > name_l and b.left < name_r]
        if not name_blocks:
            continue
        med_name = " ".join(b.text.strip() for b in name_blocks).strip()
        if not med_name:
            continue

        suffix = "" if med_index == 0 else f"_{med_index + 1}"
        name_conf = Decimal(str(round(sum(b.confidence for b in name_blocks) / len(name_blocks), 4)))
        results.append(
            ExtractedField(field_type=f"MEDICATION_NAME{suffix}", extracted_value=med_name, confidence=name_conf)
        )

        if total_l is not None and total_r is not None:
            dur = _rx_duration(med_name, total_l, total_r, row)
            if dur is not None:
                results.append(
                    ExtractedField(
                        field_type=f"DURATION_DAYS{suffix}",
                        extracted_value=dur.extracted_value,
                        confidence=dur.confidence,
                    )
                )

        med_index += 1

    return results


def _extract_emr(clova_result: ClovaOcrResult) -> list[ExtractedField]:
    """EMR: 상병명·처방 표 파서 우선, 누락 필드를 블록 파서·정규식·검사 표 파서로 보완.

    모든 문서가 EMR 기본값으로 업로드되므로, 검사결과지도 이 경로를 탄다.
    표 헤더가 있으면 표 파서를, 없으면 정규식 fallback을 시도한다.
    """
    results: list[ExtractedField] = []
    found_types: set[str] = set()

    def _add(fields: list[ExtractedField]) -> None:
        for f in fields:
            if f.field_type not in found_types:
                results.append(f)
                found_types.add(f.field_type)

    # ① EMR 상병명 표 → DIAGNOSIS (구조 기반)
    _add(_extract_emr_diagnosis_table(clova_result.rows))

    # ② EMR 처방 표 → MEDICATION_NAME[_N] + DURATION_DAYS[_N] (원외 체크 행)
    #    인덱스형 필드(MEDICATION_NAME_2 등)는 found_types 충돌 없이 누적된다.
    for f in _extract_emr_rx_table(clova_result.rows):
        results.append(f)
        found_types.add(f.field_type)

    # ③ CLOVA 블록 파서 (헤더→값 레이아웃) — ①②에서 못 찾은 필드 보완
    _add(_extract_from_clova_blocks(clova_result))

    # ④ 정규식 fallback
    _add(_extract_by_regex(clova_result, _EMR_PATTERNS))

    # ⑤ 검사결과지 표 파서 — 표 헤더(검사항목·검사결과)가 있을 때만 실행된다
    _add(_extract_lab_table(clova_result.rows))

    # ⑥ 검사결과지 정규식 fallback
    _add(_extract_by_regex(clova_result, _LAB_PATTERNS))

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
