"""CSV 한 행을 처방 항목으로 가르는 규칙 — KEY-137.

이 검사가 없으면 규칙이 시드 안에서만 돌고 아무도 확인하지 않는다. 실제로
처음에는 `scripts/seed.py` 안에 있었고, **`필요시` 에도 기간을 붙이는 돌연변이를
심었는데 검사가 하나도 안 죽었다.** 그래서 규칙을 여기로 꺼냈다.
"""

import csv
from pathlib import Path

import pytest

from app.models.prescriptions import AS_NEEDED
from app.tests.fixtures.prescriptions import PrescriptionRowError, items_from_row

CSV_PATH = Path(__file__).resolve().parents[3] / "docs" / "data" / "synthetic-patients.csv"

with CSV_PATH.open(encoding="utf-8-sig") as _f:
    ROWS: list[dict[str, str]] = list(csv.DictReader(_f))


class TestSplittingOneRowIntoItems:
    def test_a_single_drug_row_makes_one_item(self) -> None:
        items = items_from_row("비잔정 2mg", "1일 1회", "84")
        assert len(items) == 1
        assert items[0].name == "비잔정 2mg"
        assert items[0].frequency == "1일 1회"
        assert items[0].duration_days == 84

    def test_a_two_drug_row_makes_two_items_in_order(self) -> None:
        items = items_from_row("비잔정 2mg + 진통제", "1일 1회 + 필요시", "84")
        assert [i.name for i in items] == ["비잔정 2mg", "진통제"]
        assert [i.frequency for i in items] == ["1일 1회", AS_NEEDED]

    def test_an_empty_row_makes_nothing(self) -> None:
        assert items_from_row("", "", "") == []

    def test_mismatched_counts_are_refused_not_guessed(self) -> None:
        """짝이 안 맞으면 추측해서 붙이지 않는다 — 어느 약의 용법인지 모른다."""
        with pytest.raises(PrescriptionRowError):
            items_from_row("비잔정 2mg + 진통제", "1일 1회", "84")


class TestAsNeededDrugsGetNoDuration:
    """**이 파일의 존재 이유다.**

    `처방일수` 는 행에 하나뿐인데 약은 둘일 수 있다. 그 하나를 두 줄에 다 붙이면
    안내문이 「진통제를 84일간 드세요」라고 말한다.
    """

    def test_the_as_needed_line_is_left_empty(self) -> None:
        items = items_from_row("비잔정 2mg + 진통제", "1일 1회 + 필요시", "84")
        by_name = {i.name: i for i in items}
        assert by_name["비잔정 2mg"].duration_days == 84
        assert by_name["진통제"].duration_days is None, "필요시 약에 기간이 붙었다"

    def test_two_scheduled_drugs_both_keep_the_duration(self) -> None:
        """`필요시` 가 아니면 둘 다 기간을 받는다 — 규칙이 과하게 걸리지 않는 것."""
        items = items_from_row("야즈정 + 메트포르민 500mg", "1일 1회 + 1일 2회", "84")
        assert [i.duration_days for i in items] == [84, 84]

    def test_a_non_numeric_duration_becomes_empty(self) -> None:
        items = items_from_row("비잔정 2mg", "1일 1회", "")
        assert items[0].duration_days is None


class TestAgainstTheRealSyntheticData:
    """합성 CSV 전수로 돌려 본다 — 규칙이 실제 데이터에서 성립하는가."""

    def test_every_row_splits_without_error(self) -> None:
        for row in ROWS:
            if not row["약"].strip():
                continue
            items_from_row(row["약"], row["용법"], row["처방일수"])

    def test_the_row_and_item_counts_are_what_we_measured(self) -> None:
        """처방 99건 · 항목 112건. 숫자가 바뀌면 CSV 가 바뀐 것이다."""
        rows = [r for r in ROWS if r["약"].strip() and r["처방세트"].strip()]
        items = [i for r in rows for i in items_from_row(r["약"], r["용법"], r["처방일수"])]
        assert len(rows) == 99
        assert len(items) == 112

    def test_exactly_the_as_needed_items_have_no_duration(self) -> None:
        """비어 있는 기간과 `필요시` 가 정확히 같은 집합이어야 한다."""
        items = [i for r in ROWS if r["약"].strip() for i in items_from_row(r["약"], r["용법"], r["처방일수"])]
        empty = {id(i) for i in items if i.duration_days is None}
        as_needed = {id(i) for i in items if i.frequency == AS_NEEDED}
        assert empty == as_needed, "기간이 빈 줄과 `필요시` 줄이 어긋난다"
        assert len(as_needed) == 9, "필요시 줄이 9개가 아니다 — CSV 가 바뀌었는가"
