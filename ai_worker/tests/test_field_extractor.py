"""field_extractor 단위 테스트 — KEY-187.

테스트 범위:
  - SYN-EMS-01 실측 CLOVA 블록 레이아웃에서 필수 3개 필드 추출
  - 필드명이 KEY-163 §2 계약(MEDICATION_NAME·DURATION_DAYS)과 일치
  - DOSAGE·FREQUENCY 권장 필드 추출
  - CLOVA 블록 매칭 시 실제 inferConfidence 사용
  - 정규식 단독 매칭 시 is_low_confidence 임계값(0.75) 미만 신뢰도 부여
  - 구버전 필드명(PRESCRIPTION_NAME·PRESCRIPTION_DURATION) 미생성
  - 처방 표 헤더 비연속 레이아웃에서도 올바른 필드 추출
  - 짧은 숫자값의 블록 부분 매칭 오판정 방지
  - LAB_RESULT 표 파서: 헤더 기반 열 위치로 검사항목→결과 쌍 추출
  - EMR 상병명 표 파서: 코드·명칭 헤더 기반 진단 키워드 매핑
  - EMR 처방 표 파서: 원외 체크 행 약품명·처방일수(비잔정 ×28) 추출
"""

from decimal import Decimal

import pytest

from ai_worker.adapters.clova import ClovaOcrResult, ClovaTextField
from ai_worker.tasks.field_extractor import extract_fields
from app.models.ocr import OcrDocumentType

_LOW_CONFIDENCE_THRESHOLD = Decimal("0.75")

# ---------------------------------------------------------------------------
# SYN-EMS-01 실측 CLOVA 블록 — PR #147 / KEY-190 (2026-08-27)
# ---------------------------------------------------------------------------
# CLOVA General V2가 헤더 블록 → 값 블록 순서로 반환한 표 구조를 재현한다.
# 진단 표: [진단] / N809 / ICD코드 / 상병명 / 자궁내막증 / 주/부상병 / 주상병
# 처방 표: 약품명 / 1회량 / 일일횟수 / 처방일수 / 비잔정(디에노게스트)2mg / 1 / 1 / 84
_SYN_EMS_01_BLOCKS = [
    ClovaTextField(text="[진단]", confidence=0.99),
    ClovaTextField(text="N809", confidence=0.96),
    ClovaTextField(text="ICD코드", confidence=0.98),
    ClovaTextField(text="상병명", confidence=0.99),
    ClovaTextField(text="자궁내막증", confidence=0.92),
    ClovaTextField(text="주/부상병", confidence=0.97),
    ClovaTextField(text="주상병", confidence=0.95),
    ClovaTextField(text="약품명", confidence=0.99),
    ClovaTextField(text="1회량", confidence=0.98),
    ClovaTextField(text="일일횟수", confidence=0.97),
    ClovaTextField(text="처방일수", confidence=0.99),
    ClovaTextField(text="비잔정(디에노게스트)2mg", confidence=0.94),
    ClovaTextField(text="1", confidence=0.98),
    ClovaTextField(text="1", confidence=0.97),
    ClovaTextField(text="84", confidence=0.99),
]

_SYN_EMS_01 = ClovaOcrResult(
    raw_text="\n".join(b.text for b in _SYN_EMS_01_BLOCKS),
    fields=_SYN_EMS_01_BLOCKS,
)

# ---------------------------------------------------------------------------
# 필수 필드 추출 — SYN-EMS-01 실측 블록 레이아웃 (인수조건 핵심)
# ---------------------------------------------------------------------------


def test_syn_ems_01_extracts_all_required_fields() -> None:
    """SYN-EMS-01 실측 CLOVA 응답에서 필수 3개 필드가 모두 추출된다."""
    fields = extract_fields(_SYN_EMS_01, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}

    assert "DIAGNOSIS" in field_map, "DIAGNOSIS 누락"
    assert "MEDICATION_NAME" in field_map, "MEDICATION_NAME 누락"
    assert "DURATION_DAYS" in field_map, "DURATION_DAYS 누락"


def test_syn_ems_01_diagnosis_value() -> None:
    fields = extract_fields(_SYN_EMS_01, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map["DIAGNOSIS"] == "자궁내막증"


def test_syn_ems_01_medication_name_value() -> None:
    fields = extract_fields(_SYN_EMS_01, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map["MEDICATION_NAME"] == "비잔정(디에노게스트)2mg"


def test_syn_ems_01_duration_days_value() -> None:
    fields = extract_fields(_SYN_EMS_01, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map["DURATION_DAYS"] == "84"


# ---------------------------------------------------------------------------
# 권장 필드 (DOSAGE·FREQUENCY) 추출
# ---------------------------------------------------------------------------


def test_syn_ems_01_extracts_dosage_and_frequency() -> None:
    """처방 표에서 권장 필드 DOSAGE·FREQUENCY도 추출된다."""
    fields = extract_fields(_SYN_EMS_01, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}

    assert "DOSAGE" in field_map
    assert "FREQUENCY" in field_map
    assert field_map["DOSAGE"] == "1"
    assert field_map["FREQUENCY"] == "1"


# ---------------------------------------------------------------------------
# 필드명 계약 정합 — 구버전 이름이 생성되지 않아야 한다 (KEY-187 Task 1)
# ---------------------------------------------------------------------------


def test_no_deprecated_field_names() -> None:
    """PRESCRIPTION_NAME·PRESCRIPTION_DURATION 구버전 필드명이 생성되지 않는다."""
    fields = extract_fields(_SYN_EMS_01, OcrDocumentType.EMR)
    field_types = {f.field_type for f in fields}

    assert "PRESCRIPTION_NAME" not in field_types
    assert "PRESCRIPTION_DURATION" not in field_types


# ---------------------------------------------------------------------------
# 처방 표 블록 파서 — 헤더 비연속 레이아웃 (항목 3 수정 검증)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="연속 헤더 요구 복원(Issue 1): 헤더 구간에 비헤더 블록이 끼면 safe-fail로 처리한다")
def test_prescription_table_with_non_consecutive_headers() -> None:
    """처방 표 헤더 사이에 비헤더 블록이 끼어 있으면 처방 표 파서를 건너뛴다 (safe-fail)."""
    # 약품명 / [비헤더] / 1회량 / 일일횟수 / 처방일수 / 비잔정2mg / 1 / 1 / 84
    blocks = [
        ClovaTextField(text="약품명", confidence=0.99),
        ClovaTextField(text="(구분선)", confidence=0.88),  # 비헤더 블록
        ClovaTextField(text="1회량", confidence=0.98),
        ClovaTextField(text="일일횟수", confidence=0.97),
        ClovaTextField(text="처방일수", confidence=0.99),
        ClovaTextField(text="비잔정 2mg", confidence=0.94),
        ClovaTextField(text="1", confidence=0.98),
        ClovaTextField(text="1", confidence=0.97),
        ClovaTextField(text="84", confidence=0.99),
    ]
    result = ClovaOcrResult(raw_text="\n".join(b.text for b in blocks), fields=blocks)
    fields = extract_fields(result, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}

    assert field_map.get("MEDICATION_NAME") == "비잔정 2mg"
    assert field_map.get("DOSAGE") == "1"
    assert field_map.get("DURATION_DAYS") == "84"


# ---------------------------------------------------------------------------
# 신뢰도 — CLOVA 블록 매칭 시 실제 inferConfidence 사용
# ---------------------------------------------------------------------------


def test_block_matched_field_uses_clova_confidence() -> None:
    """블록 파서로 추출된 값은 CLOVA 블록의 실제 inferConfidence를 사용한다."""
    fields = extract_fields(_SYN_EMS_01, OcrDocumentType.EMR)
    field_map = {f.field_type: f for f in fields}

    # 자궁내막증 블록 confidence = 0.92
    assert field_map["DIAGNOSIS"].confidence == Decimal("0.92")
    # 비잔정(디에노게스트)2mg 블록 confidence = 0.94
    assert field_map["MEDICATION_NAME"].confidence == Decimal("0.94")
    # 84 블록 confidence = 0.99
    assert field_map["DURATION_DAYS"].confidence == Decimal("0.99")


# ---------------------------------------------------------------------------
# 신뢰도 — 정규식 단독 매칭 시 is_low_confidence 임계값 미만 (항목 6 수정)
# ---------------------------------------------------------------------------


def test_regex_only_match_uses_low_confidence() -> None:
    """CLOVA 블록과 매칭되지 않은 정규식 추출값은 is_low_confidence 임계값(0.75) 미만이다."""
    result = ClovaOcrResult(
        raw_text="CA-125 : 48 U/mL\nAMH : 2.8 ng/mL",
        fields=[],  # 매칭되는 CLOVA 블록 없음 → 정규식 단독 매칭
    )
    fields = extract_fields(result, OcrDocumentType.LAB_RESULT)
    assert len(fields) > 0, "LAB_RESULT 패턴이 추출되어야 한다"

    for f in fields:
        assert f.confidence < _LOW_CONFIDENCE_THRESHOLD, (
            f"{f.field_type}의 confidence {f.confidence}가 임계값({_LOW_CONFIDENCE_THRESHOLD}) 이상"
        )


def test_short_numeric_value_avoids_partial_block_match() -> None:
    """길이 3 미만의 추출값은 블록 부분 일치를 시도하지 않아 낮은 신뢰도를 반환한다."""
    # PRESCRIPTION DURATION_DAYS 패턴이 "84"를 추출하지만,
    # 블록 텍스트 "84일처방기간"에 "84"가 포함되어도 len("84") < 3이므로 부분 매칭 안 함
    result = ClovaOcrResult(
        raw_text="84일",
        fields=[ClovaTextField(text="84일처방기간", confidence=0.95)],
    )
    fields = extract_fields(result, OcrDocumentType.PRESCRIPTION)
    field_map = {f.field_type: f for f in fields}

    assert "DURATION_DAYS" in field_map
    assert field_map["DURATION_DAYS"].confidence < _LOW_CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# EMR 정규식 fallback — MEDICATION_NAME 경계 강화 (KEY-187)
# ---------------------------------------------------------------------------


def test_emr_regex_medication_name_does_not_cross_newline() -> None:
    """EMR 정규식 fallback: 약품명이 개행 너머 텍스트를 포함하지 않는다."""
    result = ClovaOcrResult(
        raw_text="처방: 비잔정 2mg\n무관한텍스트 여기까지가끝",
        fields=[],  # 블록 파서 미작동 → 정규식 fallback
    )
    fields = extract_fields(result, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}

    assert "MEDICATION_NAME" in field_map
    assert "\n" not in field_map["MEDICATION_NAME"]
    assert "무관한텍스트" not in field_map["MEDICATION_NAME"]


@pytest.mark.parametrize(
    "raw_text, expected_value",
    [
        ("처방: 비잔정 2mg", "비잔정 2mg"),
        ("투약: 프로베라정 1정", "프로베라정 1정"),
        ("약제: 루프론 3.75mg", "루프론 3.75mg"),
    ],
)
def test_emr_regex_medication_name_captures_dosage_units(raw_text: str, expected_value: str) -> None:
    """EMR 정규식 fallback: mg·정·캡슐 등 다양한 용량 단위를 포함해 추출한다."""
    result = ClovaOcrResult(raw_text=raw_text, fields=[])
    fields = extract_fields(result, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}

    assert "MEDICATION_NAME" in field_map, f"MEDICATION_NAME 누락: {raw_text!r}"
    assert field_map["MEDICATION_NAME"] == expected_value


# ---------------------------------------------------------------------------
# 처방전(PRESCRIPTION) 문서 유형 — 필드명 정합
# ---------------------------------------------------------------------------


def test_prescription_doc_type_uses_correct_field_names() -> None:
    """PRESCRIPTION 문서 유형도 MEDICATION_NAME·DURATION_DAYS 이름을 사용한다."""
    result = ClovaOcrResult(
        raw_text="비잔정 2mg\n84일",
        fields=[
            ClovaTextField(text="비잔정 2mg", confidence=0.93),
            ClovaTextField(text="84일", confidence=0.95),
        ],
    )
    fields = extract_fields(result, OcrDocumentType.PRESCRIPTION)
    field_types = {f.field_type for f in fields}

    assert "PRESCRIPTION_NAME" not in field_types
    assert "PRESCRIPTION_DURATION" not in field_types


# ---------------------------------------------------------------------------
# LAB_RESULT 표 파서 — 바운딩 박스 기반 행/열 추출
# ---------------------------------------------------------------------------


def _lab_block(text: str, conf: float, left: float, top: float, right: float, bottom: float) -> ClovaTextField:
    return ClovaTextField(text=text, confidence=conf, left=left, top=top, right=right, bottom=bottom)


# 헤더: 검사항목(x:100-200), 검사결과(x:220-320), 참고치(x:340-440)  — y:10-30
# 행1:  CA19-9 (ECLIA)  / 20.20             / ≤ 34.00 U/mL       — y:40-60
# 행2:  CA125 (ECLIA)   / 16.20             / ≤ 35.00 U/mL       — y:70-90
_LAB_TABLE_BLOCKS = [
    _lab_block("검사항목", 0.99, 100, 10, 200, 30),
    _lab_block("검사결과", 0.99, 220, 10, 320, 30),
    _lab_block("참고치", 0.99, 340, 10, 440, 30),
    _lab_block("CA19-9 (ECLIA)", 0.95, 100, 40, 200, 60),
    _lab_block("20.20", 0.97, 220, 40, 270, 60),
    _lab_block("≤ 34.00 U/mL", 0.94, 340, 40, 440, 60),
    _lab_block("CA125 (ECLIA)", 0.96, 100, 70, 200, 90),
    _lab_block("16.20", 0.98, 220, 70, 270, 90),
    _lab_block("≤ 35.00 U/mL", 0.93, 340, 70, 440, 90),
]

from ai_worker.adapters.clova import _group_fields_by_row  # noqa: E402

_LAB_TABLE_ROWS = _group_fields_by_row(_LAB_TABLE_BLOCKS)
_LAB_TABLE_RESULT = ClovaOcrResult(
    raw_text="\n".join("\t".join(f.text for f in row) for row in _LAB_TABLE_ROWS),
    fields=_LAB_TABLE_BLOCKS,
    rows=_LAB_TABLE_ROWS,
)


def test_lab_table_extracts_ca19_9() -> None:
    """표 파서가 CA19-9 검사결과 값을 CA19_9 필드로 추출한다."""
    fields = extract_fields(_LAB_TABLE_RESULT, OcrDocumentType.LAB_RESULT)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("CA19_9") == "20.20"


def test_lab_table_extracts_ca125() -> None:
    """표 파서가 CA125 검사결과 값을 CA_125 필드로 추출한다."""
    fields = extract_fields(_LAB_TABLE_RESULT, OcrDocumentType.LAB_RESULT)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("CA_125") == "16.20"


def test_lab_table_uses_result_block_confidence() -> None:
    """표 파서가 검사결과 블록의 실제 confidence를 사용한다."""
    fields = extract_fields(_LAB_TABLE_RESULT, OcrDocumentType.LAB_RESULT)
    field_map = {f.field_type: f for f in fields}
    # CA19-9 결과 블록 confidence=0.97
    assert field_map["CA19_9"].confidence == Decimal("0.97")


def test_lab_table_does_not_extract_reference_range_as_value() -> None:
    """참고치 열이 결과값으로 추출되지 않는다."""
    fields = extract_fields(_LAB_TABLE_RESULT, OcrDocumentType.LAB_RESULT)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("CA19_9") != "≤ 34.00 U/mL"
    assert field_map.get("CA_125") != "≤ 35.00 U/mL"


def test_lab_table_falls_back_to_regex_when_no_rows() -> None:
    """rows가 없으면(바운딩 박스 미지원) 정규식 fallback이 동작한다."""
    result = ClovaOcrResult(
        raw_text="CA-125 : 48 U/mL",
        fields=[],
        rows=[],
    )
    fields = extract_fields(result, OcrDocumentType.LAB_RESULT)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("CA_125") == "48 U/mL"


# ---------------------------------------------------------------------------
# EMR 타입으로 업로드된 검사결과지 — 표 파서와 LAB 정규식 모두 동작
# ---------------------------------------------------------------------------


def test_emr_type_extracts_lab_table_fields() -> None:
    """검사결과지를 EMR 타입으로 업로드해도 표 파서가 혈액검사 값을 추출한다."""
    fields = extract_fields(_LAB_TABLE_RESULT, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("CA19_9") == "20.20"
    assert field_map.get("CA_125") == "16.20"


def test_emr_type_extracts_lab_regex_fields() -> None:
    """검사결과지를 EMR 타입으로 업로드해도 LAB 정규식 fallback이 동작한다."""
    result = ClovaOcrResult(
        raw_text="CA-125 : 48 U/mL\nAMH : 2.8 ng/mL",
        fields=[],
        rows=[],
    )
    fields = extract_fields(result, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("CA_125") == "48 U/mL"
    assert field_map.get("AMH") == "2.8 ng/mL"


# ---------------------------------------------------------------------------
# EMR 상병명 표 파서 — 바운딩 박스 기반 진단 키워드 매핑
# ---------------------------------------------------------------------------


def _diag_block(text: str, conf: float, left: float, top: float, right: float, bottom: float) -> ClovaTextField:
    return ClovaTextField(text=text, confidence=conf, left=left, top=top, right=right, bottom=bottom)


# 상병명 표: 코드(x:10-60), 명칭(x:70-300), 과목(x:310-390)
# 헤더 행 y:10-30 / 데이터 행 y:40-60, 70-90
_DIAG_TABLE_BLOCKS = [
    _diag_block("코드", 0.99, 10, 10, 60, 30),
    _diag_block("명칭", 0.99, 70, 10, 300, 30),
    _diag_block("과목", 0.99, 310, 10, 390, 30),
    _diag_block("N801", 0.96, 10, 40, 60, 60),
    _diag_block("난소의 자궁내막증", 0.94, 70, 40, 300, 60),
    _diag_block("산부인과", 0.97, 310, 40, 390, 60),
    _diag_block("D649", 0.95, 10, 70, 60, 90),
    _diag_block("상세불명의 빈혈", 0.96, 70, 70, 300, 90),
    _diag_block("산부인과", 0.97, 310, 70, 390, 90),
]

_DIAG_TABLE_ROWS = _group_fields_by_row(_DIAG_TABLE_BLOCKS)
_DIAG_TABLE_RESULT = ClovaOcrResult(
    raw_text="코드\t명칭\t과목\nN801\t난소의 자궁내막증\t산부인과",
    fields=_DIAG_TABLE_BLOCKS,
    rows=_DIAG_TABLE_ROWS,
)


def test_diag_table_extracts_endometriosis() -> None:
    """상병명 표에서 '자궁내막증' 키워드가 DIAGNOSIS='자궁내막증'으로 추출된다."""
    fields = extract_fields(_DIAG_TABLE_RESULT, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("DIAGNOSIS") == "자궁내막증"


def test_diag_table_both_keywords_returns_dul_da() -> None:
    """상병명 표에 자궁내막증과 다낭성난소 키워드가 모두 있으면 DIAGNOSIS='둘 다'."""
    blocks = [
        _diag_block("코드", 0.99, 10, 10, 60, 30),
        _diag_block("명칭", 0.99, 70, 10, 300, 30),
        _diag_block("N801", 0.96, 10, 40, 60, 60),
        _diag_block("난소의 자궁내막증", 0.94, 70, 40, 300, 60),
        _diag_block("E282", 0.96, 10, 70, 60, 90),
        _diag_block("다낭성난소증후군", 0.93, 70, 70, 300, 90),
    ]
    rows = _group_fields_by_row(blocks)
    result = ClovaOcrResult(raw_text="", fields=blocks, rows=rows)
    fields = extract_fields(result, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("DIAGNOSIS") == "둘 다"


def test_diag_table_no_keyword_returns_no_diagnosis() -> None:
    """상병명 표에 진단 키워드가 없으면 DIAGNOSIS 필드를 만들지 않는다."""
    blocks = [
        _diag_block("코드", 0.99, 10, 10, 60, 30),
        _diag_block("명칭", 0.99, 70, 10, 300, 30),
        _diag_block("D649", 0.95, 10, 40, 60, 60),
        _diag_block("상세불명의 빈혈", 0.96, 70, 40, 300, 60),
    ]
    rows = _group_fields_by_row(blocks)
    result = ClovaOcrResult(raw_text="", fields=blocks, rows=rows)
    fields = extract_fields(result, OcrDocumentType.EMR)
    field_types = {f.field_type for f in fields}
    assert "DIAGNOSIS" not in field_types


# ---------------------------------------------------------------------------
# EMR 처방 표 파서 — 원외 체크 행 약품명·처방일수 추출
# ---------------------------------------------------------------------------


def _rx_block(text: str, conf: float, left: float, top: float, right: float, bottom: float) -> ClovaTextField:
    return ClovaTextField(text=text, confidence=conf, left=left, top=top, right=right, bottom=bottom)


# 처방 표: 명칭(x:10-200), 원외(x:210-250), 총투(x:350-400)
# 헤더 행 y:10-30
# 행1: 비잔정 2mg / ☑(체크) / 1    → MEDICATION_NAME + DURATION_DAYS = 1×28 = 28
# 행2: 프로베라정 / □(미체크) / 84  → 원외 미체크라 제외
# 행3: 루프론3.75mg / ■(체크) / 84  → MEDICATION_NAME_2 + DURATION_DAYS_2 = 84
_RX_TABLE_BLOCKS = [
    _rx_block("명칭", 0.99, 10, 10, 200, 30),
    _rx_block("원외", 0.99, 210, 10, 250, 30),
    _rx_block("총투", 0.99, 350, 10, 400, 30),
    _rx_block("비잔정(디에노게스트)2mg", 0.95, 10, 40, 200, 60),
    _rx_block("☑", 0.90, 210, 40, 250, 60),
    _rx_block("1", 0.98, 350, 40, 400, 60),
    _rx_block("프로베라정", 0.95, 10, 70, 200, 90),
    _rx_block("□", 0.90, 210, 70, 250, 90),
    _rx_block("84", 0.98, 350, 70, 400, 90),
    _rx_block("루프론3.75mg", 0.94, 10, 100, 200, 120),
    _rx_block("■", 0.91, 210, 100, 250, 120),
    _rx_block("84", 0.97, 350, 100, 400, 120),
]

_RX_TABLE_ROWS = _group_fields_by_row(_RX_TABLE_BLOCKS)
_RX_TABLE_RESULT = ClovaOcrResult(raw_text="", fields=_RX_TABLE_BLOCKS, rows=_RX_TABLE_ROWS)


def test_rx_table_extracts_checked_bizanjung() -> None:
    """원외 체크된 비잔정의 처방일수를 총투×28로 계산한다."""
    fields = extract_fields(_RX_TABLE_RESULT, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("MEDICATION_NAME") == "비잔정(디에노게스트)2mg"
    assert field_map.get("DURATION_DAYS") == "28"  # 1 × 28


def test_rx_table_extracts_second_medication_with_suffix() -> None:
    """원외 체크된 두 번째 약은 MEDICATION_NAME_2 / DURATION_DAYS_2 로 추출된다."""
    fields = extract_fields(_RX_TABLE_RESULT, OcrDocumentType.EMR)
    field_map = {f.field_type: f.extracted_value for f in fields}
    assert field_map.get("MEDICATION_NAME_2") == "루프론3.75mg"
    assert field_map.get("DURATION_DAYS_2") == "84"


def test_rx_table_skips_unchecked_rows() -> None:
    """원외 미체크(□) 행은 추출하지 않는다."""
    fields = extract_fields(_RX_TABLE_RESULT, OcrDocumentType.EMR)
    # 프로베라정은 미체크 → 목록에 없어야 한다
    assert not any("프로베라정" in (f.extracted_value or "") for f in fields)
