"""[KEY-56] 문서 자동분류 단위 테스트."""

import pytest

from app.core.ocr.classifier import classify_by_filename, is_supported_mime
from app.core.ocr.schemas import ClassifiedBy, DocumentType


@pytest.mark.parametrize(
    "filename,expected_type",
    [
        # LAB_RESULT
        ("lab_result_2024.jpg", DocumentType.LAB_RESULT),
        ("검사결과지_20240815.png", DocumentType.LAB_RESULT),
        ("AMH_blood_test.pdf", DocumentType.LAB_RESULT),
        ("CBC_result.jpg", DocumentType.LAB_RESULT),
        # PRESCRIPTION
        ("prescription_20240101.pdf", DocumentType.PRESCRIPTION),
        ("처방전_박OO.jpg", DocumentType.PRESCRIPTION),
        ("Rx_note.png", DocumentType.PRESCRIPTION),
        # DRUG_LABEL
        ("약봉투_001.jpg", DocumentType.DRUG_LABEL),
        ("drug_bag_scan.png", DocumentType.DRUG_LABEL),
        ("복약지도문.pdf", DocumentType.DRUG_LABEL),
        # CLINICAL_NOTE
        ("초음파소견서.jpg", DocumentType.CLINICAL_NOTE),
        ("endometriosis_note.png", DocumentType.CLINICAL_NOTE),
        ("소견_memo.pdf", DocumentType.CLINICAL_NOTE),
        # EMR
        ("emr_chart.jpg", DocumentType.EMR),
        ("의무기록_20240801.pdf", DocumentType.EMR),
        ("medical_record.png", DocumentType.EMR),
        # UNCLASSIFIED
        ("image_001.jpg", DocumentType.UNCLASSIFIED),
        ("scan20240101.pdf", DocumentType.UNCLASSIFIED),
        ("unknown.png", DocumentType.UNCLASSIFIED),
    ],
)
def test_classify_by_filename(filename: str, expected_type: DocumentType) -> None:
    result = classify_by_filename(filename, "image/jpeg")
    assert result.document_type == expected_type
    assert result.classified_by == ClassifiedBy.AUTO


def test_classify_returns_auto() -> None:
    result = classify_by_filename("emr.jpg", "image/jpeg")
    assert result.classified_by == ClassifiedBy.AUTO
    assert result.confidence is None


@pytest.mark.parametrize(
    "mime,expected",
    [
        ("image/jpeg", True),
        ("image/png", True),
        ("image/tiff", True),
        ("image/bmp", True),
        ("image/webp", True),
        ("application/pdf", True),
        ("text/plain", False),
        ("application/msword", False),
        ("video/mp4", False),
        ("", False),
    ],
)
def test_is_supported_mime(mime: str, expected: bool) -> None:
    assert is_supported_mime(mime) is expected
