"""업무 카테고리 파생 규칙 — KEY-120 (계약 `docs/api/hospital.md` §3 S1-1).

**규칙이 두 곳에 있다.** 얼려 둔 계약 문서와 `app/services/work_category.py` 다.
둘이 어긋나면 화면은 코드를 따르고 사람은 문서를 읽는다 — 그 사이가 벌어지는 것을
여기서 막는다. 그래서 이 파일은 **문서를 파싱해서 코드와 맞댄다.**

파생은 DB 를 타지 않는 순수 함수라, 조합을 표처럼 채워서 잰다. 열둘 중 여덟만
지금 파생 가능하고 넷은 그 기능 자체가 없다 — 그것도 **양쪽으로** 잡는다.

여기 값은 전부 합성이다.
"""

import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.api_errors import ApiError
from app.models.ocr import OcrJobStatus
from app.models.visits import GuideStatus
from app.services.work_category import (
    CATEGORY_OF,
    CATEGORY_PRIORITY,
    NOT_YET_DERIVABLE,
    Candidate,
    DetailStatus,
    VisitSignals,
    WorkCategory,
    _latest,
    count_by_category,
    derive,
    sms_reachable,
)

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "api" / "hospital.md"

REACHABLE = "01039457702"
OPTED_OUT_AT = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


def signals(**overrides: object) -> VisitSignals:
    """닿을 수 있는 환자 · 아무 이벤트도 없는 진료를 기본으로 둔다."""
    base: dict[str, object] = {
        "has_document": False,
        "ocr_status": None,
        "guide_status": None,
        "phone": REACHABLE,
        "sms_opted_out_at": None,
    }
    base.update(overrides)
    return VisitSignals(**base)  # type: ignore[arg-type]


# ────────────────────────────────────────────────────────────
#  계약 문서와 코드가 같은 것을 말하는가
# ────────────────────────────────────────────────────────────


def _s1_1_section() -> str:
    """`S1-1 날짜별 업무 목록` 절만 잘라낸다.

    문서 전체를 훑으면 오류 코드 표(`| 401 | UNAUTHORIZED | … |` 모양)까지 함께
    걸린다. **범위를 좁히지 않으면 검사가 엉뚱한 것을 잰다.**
    """
    text = CONTRACT.read_text(encoding="utf-8")
    start = text.index("#### S1-1 날짜별 업무 목록")
    end = text.index("####", start + 1)
    return text[start:end]


def _contract_table() -> dict[str, set[str]]:
    """S1-1 의 「화면 탭 / work_category / detail_status」 표를 읽는다."""
    rows = re.findall(r"^\|\s*[^|]+\|\s*`([A-Z_]+)`\s*\|([^|]+)\|\s*$", _s1_1_section(), re.M)
    return {category: set(re.findall(r"`([A-Z_]+)`", details)) for category, details in rows}


def test_the_parser_actually_found_the_table() -> None:
    """**이 검사가 먼저다.**

    표 모양이 바뀌면 아래 검사들은 빈 표를 훑고 조용히 통과한다 — 「같다」가 아니라
    「볼 게 없다」인데 초록불이 된다.
    """
    table = _contract_table()
    assert len(table) == len(WorkCategory), f"계약에서 카테고리 표를 못 읽었다: {table}"
    assert sum(len(v) for v in table.values()) == len(DetailStatus), f"계약 표의 detail_status 수가 안 맞는다: {table}"


def test_code_and_contract_agree_on_every_detail_status() -> None:
    """어느 상태가 어느 탭에 속하는지 — 문서와 코드가 같아야 한다."""
    contract = _contract_table()
    from_code: dict[str, set[str]] = {category.value: set() for category in WorkCategory}
    for detail, category in CATEGORY_OF.items():
        from_code[category.value].add(detail.value)

    assert from_code == contract, "계약 표와 CATEGORY_OF 가 다르다"


def test_code_and_contract_agree_on_priority() -> None:
    """우선순위 문장도 코드와 같아야 한다."""
    match = re.search(r"여러 이벤트가 동시에 존재하면\s*`([^`]+)`", _s1_1_section())
    assert match, "계약에서 우선순위 문장을 못 찾았다"

    written = tuple(part.strip() for part in match.group(1).split("→"))
    assert written == tuple(c.value for c in CATEGORY_PRIORITY), (
        f"계약이 적은 순서와 CATEGORY_PRIORITY 가 다르다: {written}"
    )


def test_every_detail_status_belongs_to_a_category() -> None:
    """빠진 값이 있으면 `derive()` 가 그 자리에서 죽는다."""
    missing = sorted(s.value for s in DetailStatus if s not in CATEGORY_OF)
    assert not missing, f"어느 탭에도 안 속한 상태: {missing}"


# ────────────────────────────────────────────────────────────
#  조합 표 — 지금 파생할 수 있는 여덟
# ────────────────────────────────────────────────────────────

CASES: list[tuple[str, VisitSignals, WorkCategory, DetailStatus]] = [
    (
        "아무것도 안 올라온 진료",
        signals(),
        WorkCategory.IN_PROGRESS,
        DetailStatus.NO_DOCUMENT,
    ),
    (
        "문서만 올라오고 판독 작업은 아직",
        signals(has_document=True),
        WorkCategory.IN_PROGRESS,
        DetailStatus.OCR_REVIEW,
    ),
    (
        "판독 중",
        signals(has_document=True, ocr_status=OcrJobStatus.PROCESSING),
        WorkCategory.IN_PROGRESS,
        DetailStatus.OCR_REVIEW,
    ),
    (
        "판독 끝났고 스탭이 볼 차례",
        signals(has_document=True, ocr_status=OcrJobStatus.COMPLETED),
        WorkCategory.IN_PROGRESS,
        DetailStatus.OCR_REVIEW,
    ),
    (
        "판독 실패 — 재업로드로 푸는 자리라 작성 중에 둔다",
        signals(has_document=True, ocr_status=OcrJobStatus.FAILED),
        WorkCategory.IN_PROGRESS,
        DetailStatus.OCR_REVIEW,
    ),
    (
        "안내문을 스탭이 쓰는 중",
        signals(has_document=True, guide_status=GuideStatus.STAFF_REVIEW),
        WorkCategory.IN_PROGRESS,
        DetailStatus.STAFF_REVIEW,
    ),
    (
        "승인 요청",
        signals(has_document=True, guide_status=GuideStatus.APPROVAL_PENDING),
        WorkCategory.APPROVAL_REQUESTED,
        DetailStatus.APPROVAL_PENDING,
    ),
    (
        "승인돼 발송 예약",
        signals(has_document=True, guide_status=GuideStatus.SCHEDULED_TO_SEND),
        WorkCategory.SEND_PENDING,
        DetailStatus.SCHEDULED_TO_SEND,
    ),
    (
        "반려 — 스탭이 고쳐야 한다",
        signals(has_document=True, guide_status=GuideStatus.APPROVAL_RETURNED),
        WorkCategory.NEEDS_ATTENTION,
        DetailStatus.APPROVAL_RETURNED,
    ),
    (
        "문자 수신 거부",
        signals(sms_opted_out_at=OPTED_OUT_AT),
        WorkCategory.NEEDS_ATTENTION,
        DetailStatus.SMS_OPT_OUT,
    ),
    (
        "유선번호라 문자가 못 간다",
        signals(phone="0212345678"),
        WorkCategory.NEEDS_ATTENTION,
        DetailStatus.INVALID_PHONE,
    ),
    (
        "번호가 아예 없다",
        signals(phone=None),
        WorkCategory.NEEDS_ATTENTION,
        DetailStatus.INVALID_PHONE,
    ),
]


@pytest.mark.parametrize(("label", "given", "category", "detail"), CASES, ids=[c[0] for c in CASES])
def test_derives_the_documented_status(
    label: str, given: VisitSignals, category: WorkCategory, detail: DetailStatus
) -> None:
    assert derive(given) == (category, detail), label


# ────────────────────────────────────────────────────────────
#  우선순위 — 동시에 참일 때 무엇을 보여 주는가
# ────────────────────────────────────────────────────────────


def test_unreachable_patient_wins_over_approval_request() -> None:
    """승인해 봐야 나갈 곳이 없다. 스탭이 먼저 볼 것은 전화번호다."""
    both = signals(has_document=True, guide_status=GuideStatus.APPROVAL_PENDING, phone="0212345678")
    assert derive(both) == (WorkCategory.NEEDS_ATTENTION, DetailStatus.INVALID_PHONE)


def test_opt_out_wins_even_after_approval() -> None:
    """이미 승인해 발송을 기다려도, 받지 않겠다고 한 환자는 보완이다."""
    both = signals(
        has_document=True,
        guide_status=GuideStatus.SCHEDULED_TO_SEND,
        sms_opted_out_at=OPTED_OUT_AT,
    )
    assert derive(both) == (WorkCategory.NEEDS_ATTENTION, DetailStatus.SMS_OPT_OUT)


def test_opt_out_is_reported_before_a_bad_number() -> None:
    """둘 다 참이면 **사람이 정한 것**을 먼저 말한다.

    번호가 틀린 것은 고치면 되지만, 받지 않겠다고 한 것은 고칠 일이 아니다.
    """
    both = signals(phone="0212345678", sms_opted_out_at=OPTED_OUT_AT)
    assert derive(both) == (WorkCategory.NEEDS_ATTENTION, DetailStatus.SMS_OPT_OUT)


def test_guide_state_hides_the_ocr_step() -> None:
    """안내문이 있으면 판독은 지난 단계라 말하지 않는다."""
    later = signals(
        has_document=True,
        ocr_status=OcrJobStatus.COMPLETED,
        guide_status=GuideStatus.APPROVAL_PENDING,
    )
    assert derive(later) == (WorkCategory.APPROVAL_REQUESTED, DetailStatus.APPROVAL_PENDING)


# ────────────────────────────────────────────────────────────
#  아직 파생할 수 없는 넷 — 양쪽으로 잡는다
# ────────────────────────────────────────────────────────────


def test_statuses_we_cannot_derive_yet_never_come_out() -> None:
    """기능이 없는데 있는 척 파생하면 화면이 거짓을 말한다."""
    produced = {derive(given)[1] for _, given, _, _ in CASES}
    leaked = sorted(s.value for s in produced & NOT_YET_DERIVABLE)
    assert not leaked, f"아직 만들 수 없는 상태가 파생됐다: {leaked}"


def test_the_unreachable_list_is_exactly_what_the_table_does_not_cover() -> None:
    """**반대 방향.** 파생할 수 있게 됐는데 목록에 남아 있으면 여기서 알려 준다.

    이것이 없으면 KEY-150 이 안내 생성을 붙인 뒤에도 `GUIDE_GENERATING` 이
    「아직 없다」로 남고, 다음 사람은 목록만 보고 그렇게 믿는다.
    """
    covered = {detail for _, _, _, detail in CASES}
    uncovered = set(DetailStatus) - covered
    assert uncovered == NOT_YET_DERIVABLE, (
        "표가 덮는 범위와 NOT_YET_DERIVABLE 이 어긋난다 — "
        f"표에 없는 것 {sorted(s.value for s in uncovered)} · "
        f"목록 {sorted(s.value for s in NOT_YET_DERIVABLE)}"
    )


# ────────────────────────────────────────────────────────────
#  문자를 보낼 수 있는 번호인가
# ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        ("01039457702", True),
        ("010-3945-7702", True),
        ("+821039457702", True),
        ("0113945770", True),
        ("0212345678", False),  # 유선 — 저장은 되지만 문자는 못 간다
        ("0313945770", False),
        ("", False),
        (None, False),
    ],
)
def test_sms_reachable(phone: str | None, expected: bool) -> None:
    assert sms_reachable(phone) is expected


# ────────────────────────────────────────────────────────────
#  건수
# ────────────────────────────────────────────────────────────


def test_counts_always_carry_all_five_tabs() -> None:
    """0 인 탭을 빼면 화면이 그 탭을 안 그리거나 `undefined` 를 센다."""
    counts = count_by_category({})
    assert set(counts) == {c.value for c in WorkCategory}
    assert set(counts.values()) == {0}


def test_counts_match_the_derived_categories() -> None:
    derived = {
        1: (WorkCategory.IN_PROGRESS, DetailStatus.NO_DOCUMENT),
        2: (WorkCategory.IN_PROGRESS, DetailStatus.OCR_REVIEW),
        3: (WorkCategory.NEEDS_ATTENTION, DetailStatus.SMS_OPT_OUT),
    }
    counts = count_by_category(derived)
    assert counts["IN_PROGRESS"] == 2
    assert counts["NEEDS_ATTENTION"] == 1
    assert counts["COMPLETED"] == 0


def test_unknown_derivation_rule_uses_the_contract_error() -> None:
    with (
        patch.dict(CATEGORY_OF, {}, clear=True),
        pytest.raises(ApiError) as captured,
    ):
        derive(signals())

    assert captured.value.status_code == 500
    assert captured.value.code == "WORK_CATEGORY_DATA_INVALID"
    assert "NO_DOCUMENT" not in captured.value.message


# ────────────────────────────────────────────────────────────
#  같은 탭 안에서는 **가장 최근**을 말한다 — KEY-166
#
#  계약: 「동일 카테고리에서는 가장 최근에 발생한 미해결 상태를 선택」.
#
#  예전에는 `_candidates()` 가 담은 차례대로 첫 번째를 골랐다. 안내문 가지가
#  늘 먼저 담기므로, 2주 전 반려와 어제 수신거부가 함께 걸린 진료에서
#  **2주 전 반려**가 떴다. 둘 다 「보완」 탭이지만 스탭이 먼저 볼 것은 어제
#  것이다 (이희진 님 `#93` 리뷰).

TWO_WEEKS_AGO = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
YESTERDAY = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def test_recent_opt_out_wins_over_an_old_return() -> None:
    """2주 전 반려 · 어제 수신거부 → **어제 것**을 말한다."""
    both = signals(
        has_document=True,
        guide_status=GuideStatus.APPROVAL_RETURNED,
        guide_changed_at=TWO_WEEKS_AGO,
        sms_opted_out_at=YESTERDAY,
    )
    assert derive(both) == (WorkCategory.NEEDS_ATTENTION, DetailStatus.SMS_OPT_OUT)


def test_recent_return_wins_over_an_old_opt_out() -> None:
    """차례를 뒤집어도 규칙이 같다 — **시각**이 고르지 담긴 순서가 아니다.

    이 검사가 짝으로 있어야 한다. 하나만 두면 「늘 수신거부가 이긴다」로
    고쳐도 통과한다.
    """
    both = signals(
        has_document=True,
        guide_status=GuideStatus.APPROVAL_RETURNED,
        guide_changed_at=YESTERDAY,
        sms_opted_out_at=TWO_WEEKS_AGO,
    )
    assert derive(both) == (WorkCategory.NEEDS_ATTENTION, DetailStatus.APPROVAL_RETURNED)


def test_a_recent_bad_number_wins_over_an_old_return() -> None:
    """`INVALID_PHONE` 도 같은 규칙을 탄다 — 번호를 마지막으로 고친 때가 그 시각이다."""
    both = signals(
        has_document=True,
        guide_status=GuideStatus.APPROVAL_RETURNED,
        guide_changed_at=TWO_WEEKS_AGO,
        phone="0212345678",
        patient_changed_at=YESTERDAY,
    )
    assert derive(both) == (WorkCategory.NEEDS_ATTENTION, DetailStatus.INVALID_PHONE)


def test_an_old_bad_number_loses_to_a_recent_return() -> None:
    both = signals(
        has_document=True,
        guide_status=GuideStatus.APPROVAL_RETURNED,
        guide_changed_at=YESTERDAY,
        phone="0212345678",
        patient_changed_at=TWO_WEEKS_AGO,
    )
    assert derive(both) == (WorkCategory.NEEDS_ATTENTION, DetailStatus.APPROVAL_RETURNED)


def test_category_priority_still_beats_recency() -> None:
    """**탭 사이 우선순위는 시각이 못 뒤집는다.**

    승인 요청이 방금 걸렸어도, 보낼 곳이 없는 진료는 「보완」이다. 시각으로
    탭까지 고르기 시작하면 계약의 `CATEGORY_PRIORITY` 가 무의미해진다.
    """
    both = signals(
        has_document=True,
        guide_status=GuideStatus.APPROVAL_PENDING,
        guide_changed_at=YESTERDAY,
        sms_opted_out_at=TWO_WEEKS_AGO,
    )
    assert derive(both) == (WorkCategory.NEEDS_ATTENTION, DetailStatus.SMS_OPT_OUT)


def test_a_known_time_beats_an_unknown_one() -> None:
    """시각을 모르는 후보를 「최신」으로 읽지 않는다.

    지금은 시각 없는 후보가 자기 탭에 혼자 있어 겨루지 않지만, 겹치는 날
    조용히 뒤집히면 안 된다. `_latest()` 를 직접 재는 유일한 자리다.
    """
    known = Candidate(DetailStatus.SMS_OPT_OUT, TWO_WEEKS_AGO)
    unknown = Candidate(DetailStatus.APPROVAL_RETURNED, None)

    assert _latest([unknown, known]) is known
    assert _latest([known, unknown]) is known


def test_a_tie_keeps_the_documented_order() -> None:
    """같은 시각이면 흔들리지 않는다 — 같은 데이터에 화면이 달라지면 안 된다."""
    first = Candidate(DetailStatus.APPROVAL_RETURNED, YESTERDAY)
    second = Candidate(DetailStatus.SMS_OPT_OUT, YESTERDAY)

    assert _latest([first, second]) is first
    assert _latest([second, first]) is second
