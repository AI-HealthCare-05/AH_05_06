from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import pytest

from app.models.catalog import SourceGrade
from app.services.drug_caution import DrugCautionService
from app.tests.fixtures.catalog import DRUG_CAUTION_CONTENTS


@pytest.mark.parametrize("row", [r for r in DRUG_CAUTION_CONTENTS if r.source_grade is SourceGrade.C])
def test_fixture_body_edit_does_not_inherit_approval(row):
    changed = replace(row, body=row.body + " [미검토 변경]")
    assert changed.physician_review == row.physician_review
    assert DrugCautionService.has_evidence(row)
    assert not DrugCautionService.has_evidence(changed)


def content():
    return SimpleNamespace(
        source_grade=SourceGrade.C,
        source_name="전문의 복약지도",
        source_org="합성 병원",
        source_url="https://example.invalid/review",
        content_version="v1",
        body="합성 승인 문장",
        physician_review={
            "reviewer": "합성 전문의",
            "hospital": "합성 병원",
            "reviewed_at": "2026-09-04",
            "body_sha256": sha256("합성 승인 문장".encode()).hexdigest(),
        },
    )


def test_complete_record_allows_template():
    assert DrugCautionService.has_evidence(content())


@pytest.mark.parametrize("key", ["source_name", "source_org", "source_url", "content_version"])
@pytest.mark.parametrize("value", [None, "", "  ", 123])
def test_missing_or_invalid_evidence_falls_back(key, value):
    row = content()
    setattr(row, key, value)
    assert not DrugCautionService.has_evidence(row)


@pytest.mark.parametrize("key", ["reviewer", "hospital", "reviewed_at", "body_sha256"])
def test_missing_review_field_blocks(key):
    row = content()
    del row.physician_review[key]
    assert not DrugCautionService.has_evidence(row)


@pytest.mark.parametrize("record", [None, {}, "전문의 승인", {"reviewer": 123}])
def test_source_title_alone_never_proves_approval(record):
    row = content()
    row.physician_review = record
    assert not DrugCautionService.has_evidence(row)


def test_changed_body_invalidates_review():
    row = content()
    row.body += " 승인되지 않은 내용"
    assert not DrugCautionService.has_evidence(row)


@pytest.mark.parametrize(
    "key,value", [("hospital", "다른 병원"), ("reviewed_at", "invalid"), ("reviewed_at", "2099-01-01")]
)
def test_invalid_review_blocks(key, value):
    row = content()
    row.physician_review[key] = value
    assert not DrugCautionService.has_evidence(row)
