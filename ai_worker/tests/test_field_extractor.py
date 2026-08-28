"""field_extractor 단위 테스트 — KEY-187.

테스트 범위:
  - SYN-EMS-01 실측 CLOVA 블록 레이아웃에서 필수 3개 필드 추출
  - 필드명이 KEY-163 §2 계약(MEDICATION_NAME·DURATION_DAYS)과 일치
  - DOSAGE·FREQUENCY 권장 필드 추출
  - CLOVA 블록 매칭 시 실제 inferConfidence 사용
  - 정규식 단독 매칭 시 _DEFAULT_CONFIDENCE(0.70) 사용 → is_low_confidence 임계값(0.75) 미만
  - 구버전 필드명(PRESCRIPTION_NAME·PRESCRIPTION_DURATION) 미생성
"""

from decimal import Decimal

from ai_worker.adapters.clova import ClovaOcrResult, ClovaTextField
from ai_worker.tasks.field_extractor import _DEFAULT_CONFIDENCE, extract_fields
from app.models.ocr import OcrDocumentType

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
# 신뢰도 — 정규식 단독 매칭 시 _DEFAULT_CONFIDENCE(0.70) 적용
# ---------------------------------------------------------------------------


def test_regex_only_match_uses_default_confidence() -> None:
    """CLOVA 블록과 매칭되지 않은 정규식 추출값은 _DEFAULT_CONFIDENCE를 가진다."""
    result = ClovaOcrResult(
        raw_text="CA-125 : 48 U/mL\nAMH : 2.8 ng/mL",
        fields=[],  # 매칭되는 CLOVA 블록 없음 → 정규식 단독 매칭
    )
    fields = extract_fields(result, OcrDocumentType.LAB_RESULT)
    assert len(fields) > 0, "LAB_RESULT 패턴이 추출되어야 한다"

    for f in fields:
        assert f.confidence == _DEFAULT_CONFIDENCE, (
            f"{f.field_type}의 confidence {f.confidence}가 _DEFAULT_CONFIDENCE({_DEFAULT_CONFIDENCE})여야 한다"
        )


def test_regex_default_confidence_is_below_low_confidence_threshold() -> None:
    """_DEFAULT_CONFIDENCE가 is_low_confidence 임계값(0.75) 미만이다."""
    assert _DEFAULT_CONFIDENCE < Decimal("0.75"), (
        f"_DEFAULT_CONFIDENCE({_DEFAULT_CONFIDENCE})가 임계값 0.75 이상이면 "
        "정규식 단독 매칭값이 is_low_confidence로 표시되지 않는다"
    )


# ---------------------------------------------------------------------------
# 처방전(PRESCRIPTION) 문서 유형 — 필드명 정합
# ---------------------------------------------------------------------------


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


def test_emr_regex_medication_name_captures_dosage_units() -> None:
    """EMR 정규식 fallback: mg·정·캡슐 등 다양한 용량 단위를 포함해 추출한다."""
    cases = [
        ("처방: 비잔정 2mg", "비잔정 2mg"),
        ("투약: 프로베라정 1정", "프로베라정 1정"),
        ("약제: 루프론 3.75mg", "루프론 3.75mg"),
    ]
    for raw_text, expected_value in cases:
        result = ClovaOcrResult(raw_text=raw_text, fields=[])
        fields = extract_fields(result, OcrDocumentType.EMR)
        field_map = {f.field_type: f.extracted_value for f in fields}
        assert "MEDICATION_NAME" in field_map, f"MEDICATION_NAME 누락: {raw_text!r}"
        assert field_map["MEDICATION_NAME"] == expected_value, (
            f"기대값={expected_value!r}, 실제값={field_map['MEDICATION_NAME']!r}"
        )


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
