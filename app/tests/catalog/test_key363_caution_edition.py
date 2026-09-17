"""승인 문구를 고칠 때 기록이 같이 따라오는가 — KEY-363.

2026-09-17 산부인과 전문의 비공식 자문에서 비잔 주의사항 한 문장을 고쳤다.
「약을 조절하거나 바꿀 수 있어요」가 **무엇을** 조절하고 **무엇을** 바꾸는지
모호하다는 지적이었다.

**글자만 바꾸면 그 문구가 조용히 승인 밖으로 나간다.** 런타임이 본문 해시를
실제로 견준다 (`app/services/drug_caution.py` `_is_physician_reviewed`).
해시가 어긋나면 C등급 문구가 승인된 것으로 안 쳐지고, `GUIDE_RAG_ENABLED=true`
경로에서는 `approved_fallback()` 이 None 을 돌려 **안내문 생성이 통째로**
`unverified_context` 로 실패한다.

🚩 **이 검사가 잡으려는 두 번째 것은 반대쪽이다.**

전에는 판번호가 전역 하나였다(`content_version != _APPROVED_VERSION`). 한 칸만
고쳐도 열두 칸의 판번호를 같이 올려야 했고, 그러면 **그날 보지도 않은 열한
칸까지 `reviewed_at` 이 새 날짜로 바뀌었다.** 승인 기록이 사실과 달라지는 것은
문구가 틀리는 것과 같은 무게다 — 「누가 언제 무엇을 봤나」가 그 기록의 전부다.
"""

from datetime import date
from hashlib import sha256

from app.models.catalog import CautionSectionKey, SourceGrade
from app.tests.fixtures.catalog import DRUG_CAUTION_CONTENTS

#: 이번 자문에서 실제로 본 칸. 이것만 새 판이다.
REVIEWED_ON_0917 = {
    ("자궁내막증 · 비잔 (처음)", "caution"),
    ("자궁내막증 · 비잔 (계속)", "caution"),
}

NEW_EDITION = "2026-09-17"
OLD_EDITION = "2026-09-04"


def _c_rows():
    """전문의 자문이 근거인 칸들. 식약처 A등급(응급)은 검토 기록이 없다."""
    return [row for row in DRUG_CAUTION_CONTENTS if row.source_grade is SourceGrade.C]


def test_every_reviewed_body_matches_its_recorded_hash() -> None:
    """**본문에서 직접 세어 견준다.** 표에 적힌 값을 그대로 믿지 않는다."""
    offenders = []
    for row in _c_rows():
        review = row.physician_review
        assert review is not None, f"{row.prescription_set_name}/{row.section_key.value} 의 검토 기록이 사라졌다"
        if review["body_sha256"] != sha256(row.body.encode()).hexdigest():
            offenders.append(f"{row.prescription_set_name}/{row.section_key.value}")

    assert not offenders, (
        "승인 해시가 본문과 어긋난다 — 그 문구는 승인된 것으로 안 쳐지고 RAG 켠 경로가 막힌다:\n"
        + "\n".join(f"  {item}" for item in offenders)
    )


def test_the_changed_sentence_says_what_is_adjusted_and_what_is_changed() -> None:
    """자문이 요구한 것은 **용량과 종류를 나눠 적는 것**이었다."""
    rows = [
        row for row in DRUG_CAUTION_CONTENTS if (row.prescription_set_name, row.section_key.value) in REVIEWED_ON_0917
    ]
    assert len(rows) == 2, f"비잔 주의사항 두 칸을 못 찾았다: {len(rows)}"

    for row in rows:
        assert "약의 용량을 조절하거나 종류를 바꿀 수 있어요" in row.body, (
            f"{row.prescription_set_name}: 용량·종류를 나눠 적지 않았다"
        )
        assert "약을 조절하거나 바꿀 수 있어요" not in row.body, f"{row.prescription_set_name}: 옛 문장이 그대로 남았다"


def test_the_new_edition_is_carried_only_by_the_rows_that_were_reviewed() -> None:
    """🚩 **이 검사가 이 티켓의 핵심이다.**

    판번호를 전역으로 올리면 여기서 운다 — 보지도 않은 칸이 새 판을 달게 된다.
    """
    wrongly_bumped = [
        f"{row.prescription_set_name}/{row.section_key.value}"
        for row in _c_rows()
        if row.content_version == NEW_EDITION
        and (row.prescription_set_name, row.section_key.value) not in REVIEWED_ON_0917
    ]
    assert not wrongly_bumped, (
        f"2026-09-17 자문에서 보지 않은 칸이 새 판({NEW_EDITION})을 달았다 — 승인 기록이 사실과 달라진다:\n"
        + "\n".join(f"  {item}" for item in wrongly_bumped)
    )

    not_bumped = [
        f"{row.prescription_set_name}/{row.section_key.value}"
        for row in _c_rows()
        if (row.prescription_set_name, row.section_key.value) in REVIEWED_ON_0917 and row.content_version != NEW_EDITION
    ]
    assert not not_bumped, (
        "고친 문구가 옛 판번호 그대로다 — 씨앗이 (세트, 절, 판)으로 건너뛰므로 **서버에 안 들어간다**:\n"
        + "\n".join(f"  {item}" for item in not_bumped)
    )


def test_the_untouched_rows_keep_their_original_review_date() -> None:
    """나머지 열 칸은 2026-09-04 검토 그대로여야 한다."""
    for row in _c_rows():
        if (row.prescription_set_name, row.section_key.value) in REVIEWED_ON_0917:
            continue
        review = row.physician_review
        assert review is not None
        assert review["reviewed_at"] == OLD_EDITION, (
            f"{row.prescription_set_name}/{row.section_key.value} 의 검토일이 {review['reviewed_at']} 로 바뀌었다 — "
            "그날 보지 않은 문구다"
        )


def test_the_review_date_follows_the_edition() -> None:
    """검토일이 판번호를 따라간다 — 한쪽만 바꾸면 여기서 걸린다."""
    for row in _c_rows():
        review = row.physician_review
        assert review is not None
        assert review["reviewed_at"] == row.content_version, (
            f"{row.prescription_set_name}/{row.section_key.value}: "
            f"판 {row.content_version} 인데 검토일이 {review['reviewed_at']} 다"
        )
        assert date.fromisoformat(review["reviewed_at"]) == row.verified_at, (
            f"{row.prescription_set_name}/{row.section_key.value}: verified_at 과 reviewed_at 이 갈렸다"
        )


def test_an_edition_with_no_recorded_review_is_not_treated_as_approved() -> None:
    """🚩 **반대 방향.** 표에 없는 판은 승인 기록이 **없어야** 한다.

    이걸 안 재면 게이트를 `return {...}` 하나로 열어 놔도 위 검사들이 전부
    통과한다. 그러면 아무 판번호나 승인된 것처럼 보인다.
    """
    row = next(row for row in _c_rows() if row.section_key is CautionSectionKey.CAUTION)
    unknown = type(row)(
        prescription_set_name=row.prescription_set_name,
        section_key=row.section_key,
        body=row.body,
        source_grade=SourceGrade.C,
        source_name=row.source_name,
        source_org=row.source_org,
        source_url=row.source_url,
        verified_at=date(2030, 1, 1),
        content_version="2030-01-01",
    )
    assert unknown.physician_review is None, (
        "해시 표에 없는 판이 검토 기록을 들고 나왔다 — 아무 판이나 승인된 것처럼 보인다"
    )
