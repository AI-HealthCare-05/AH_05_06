"""합성 CSV 한 행 → 판독 필드 규칙 — KEY-271 P1.

DB 를 안 띄운다. 규칙을 시드 밖에 둔 까닭이 이것이다.
"""

import csv
from collections import Counter
from pathlib import Path

import pytest

from app.models.ocr import DAYS_PER_PACK, DurationUnit, course_days
from app.tests.fixtures.ocr_rows import (
    LAB_FIELD_FOR,
    UNMAPPED_LAB_LABELS,
    OcrRowError,
    ReadStage,
    duration_row,
    read_from_row,
    stage_for,
)

CSV_PATH = Path(__file__).resolve().parents[3] / "docs" / "data" / "synthetic-patients.csv"


def _rows() -> list[dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _row(scenario: str) -> dict[str, str]:
    for row in _rows():
        if row["시나리오ID"] == scenario:
            return row
    raise AssertionError(f"CSV 에 {scenario} 가 없다 — 검사가 헛돈다")


class TestStage:
    def test_a_visit_with_no_document_gets_no_reading(self) -> None:
        """「진료기록 없음」은 판독 작업 자체를 안 만든다."""
        assert stage_for("진료기록 없음") is ReadStage.NONE
        assert read_from_row(_row("SYN-PCOS-06")).fields == ()

    def test_only_staff_review_is_left_unconfirmed(self) -> None:
        """**미확정은 「스탭 확인 중」 하나다.**

        「승인 대기」·「보완」은 안내문이 이미 있다는 뜻이고 안내문은 확정 없이
        못 만든다. 표본을 늘리려고 그것들을 미확정으로 심으면 상태의 뜻이
        비틀리고, 이 데이터를 믿고 짠 다음 사람이 틀린다.
        """
        assert stage_for("스탭 확인 중") is ReadStage.UNCONFIRMED
        for state in ("승인 대기", "보완", "발송 완료", "발송 예정", "생성 중", "계획된 중단"):
            assert stage_for(state) is ReadStage.CONFIRMED, f"{state} 가 미확정으로 샜다"

    def test_an_unknown_state_stops_instead_of_guessing(self) -> None:
        """**모르는 상태를 조용히 확정으로 떨어뜨리지 않는다.**

        떨어뜨리면 상태가 하나 늘 때마다 미확정 표본이 소리 없이 사라지고,
        확인 화면이 빈 채로 초록이 된다.
        """
        with pytest.raises(OcrRowError, match="모르는 진료상태"):
            stage_for("발송 보류")

    def test_every_state_in_the_csv_is_known(self) -> None:
        """CSV 가 쓰는 상태를 규칙이 전부 안다 — 하나라도 모르면 시드가 멈춘다."""
        for state in {row["진료상태"] for row in _rows()}:
            stage_for(state)


class TestDuration:
    def test_a_pack_count_keeps_the_number_and_says_it_is_packs(self) -> None:
        """**판독은 원문 숫자를 읽는다.** `1/1/3` 의 `3` 이 그것이다.

        3통인지 3일인지는 숫자에 안 적혀 있다 — 그래서 `unit` 에 남긴다.
        """
        made = duration_row("1/1/3", "통수", "84")
        assert made is not None
        assert made.value == "3", "환산한 값을 넣으면 판독이 읽은 것이 아니게 된다"
        assert made.unit == DurationUnit.PACK

    def test_a_day_count_is_left_alone(self) -> None:
        made = duration_row("1/1/84", "일수", "84")
        assert made is not None
        assert (made.value, made.unit) == ("84", DurationUnit.DAYS)

    def test_a_conversion_that_disagrees_with_the_csv_stops(self) -> None:
        """`처방일수` 칸이 **답안지**다. 어긋나면 여기서 멈춘다.

        조용히 심으면 소진 문자가 엉뚱한 날 예약된다.
        """
        with pytest.raises(OcrRowError, match="어긋난다"):
            duration_row("1/1/3", "통수", "3")

    def test_every_row_in_the_csv_converts_to_its_own_answer(self) -> None:
        """**합성 100행 전수.** `총투 × 단위 = 처방일수` 가 데이터 전체에서 선다."""
        checked = 0
        for row in _rows():
            made = duration_row(row["총투원문"], row["총투단위"], row["처방일수"])
            if made is None:
                continue
            checked += 1
        assert checked == 99, f"환산을 잰 행이 {checked}개다 — 진료가 있는 99행이어야 한다"

    def test_the_pack_rows_are_the_ones_that_would_have_broken(self) -> None:
        """통수 행이 실제로 있다 — 없으면 위 검사들이 빈 데이터를 재는 것이다."""
        units = Counter(row["총투단위"] for row in _rows())
        assert units["통수"] == 33, f"통수 행이 {units['통수']}개다"


class TestCourseDays:
    def test_packs_multiply(self) -> None:
        assert course_days("3", DurationUnit.PACK) == 3 * DAYS_PER_PACK

    def test_days_do_not(self) -> None:
        assert course_days("84", DurationUnit.DAYS) == 84

    def test_no_unit_means_no_multiplying(self) -> None:
        """**모르면 곱하지 않는다.** 여태 그렇게 살았고, 지어낸 값으로 예약하는 것보다 낫다."""
        assert course_days("3", None) == 3

    def test_a_unit_suffix_in_the_text_is_stripped(self) -> None:
        """「84일」처럼 단위가 붙어 와도 숫자만 뗀다 — 옛 `_course_days` 가 하던 것이다."""
        assert course_days("84일", DurationUnit.DAYS) == 84

    def test_nothing_readable_gives_nothing(self) -> None:
        for value in (None, "", "미상", "0"):
            assert course_days(value, DurationUnit.DAYS) is None, f"{value!r} 에서 숫자를 지어냈다"


class TestFields:
    def test_the_required_trio_is_there(self) -> None:
        """`DIAGNOSIS`·`MEDICATION_NAME`·`DURATION_DAYS` — 이 셋이 없으면 사슬이 선다."""
        made = read_from_row(_row("SYN-PCOS-02"))
        types = {field.field_type for field in made.fields}
        assert {"DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"} <= types, f"빠졌다 — {sorted(types)}"
        assert "PRESCRIPTION_SET" in types, "없으면 finalize 가 422 MISSING_PRESCRIPTION_SET"
        assert "FREQUENCY" in types, "없으면 finalize 가 422 MISSING_FREQUENCY"

    def test_a_second_drug_gets_the_second_slot(self) -> None:
        """약이 둘이면 `_2` 로 간다 — 서버가 번호로 차례를 정한다."""
        two = next(row for row in _rows() if " + " in row["약"])
        made = read_from_row(two)
        types = {field.field_type for field in made.fields}
        assert {"MEDICATION_NAME", "MEDICATION_NAME_2", "FREQUENCY", "FREQUENCY_2"} <= types

    def test_a_late_result_is_marked_pending_not_missing(self) -> None:
        """**「값이 없다」와 「아직 안 나왔다」는 다르다.**

        앞은 채워야 하고 뒤는 비어 있는 것이 맞다 — 화면이 그 줄만 점선 + ? 로
        그린다. 구별이 없으면 그 항목이 「확인할 항목」에 영영 남는다.
        """
        made = read_from_row(_row("SYN-EMS-02"))
        amh = next(field for field in made.fields if field.field_type == "AMH")
        assert amh.is_pending_report is True
        assert amh.value == "추후보고예정"

    def test_a_blank_lab_makes_no_row_at_all(self) -> None:
        """빈 칸은 「그 방문에 그 검사를 안 했다」는 뜻이다 — 못 읽은 것이 아니다."""
        row = _row("SYN-EMS-02")
        assert row["총테스토스테론"].strip() == "", "CSV 가 바뀌었다 — 검사를 고쳐야 한다"
        types = {field.field_type for field in read_from_row(row).fields}
        assert "TESTOSTERONE" not in types

    def test_a_column_with_no_field_type_is_dropped_out_loud(self) -> None:
        """**담을 이름이 없으면 버린다.** 지어 넣으면 그 이름이 진짜인 줄 아는 사람이 생긴다.

        무엇을 버렸는지는 값으로 남긴다 — 조용히 버리면 다음 사람이 「왜 이
        검사만 화면에 없지」로 시간을 쓴다.
        """
        made = read_from_row(_row("SYN-PCOS-02"))
        assert set(made.dropped) == {"월경주기", "기타검사"}
        for label in UNMAPPED_LAB_LABELS:
            assert label not in LAB_FIELD_FOR, f"{label} 이 양쪽에 다 있다 — 규칙이 어긋난다"

    def test_the_whole_csv_passes_the_rule(self) -> None:
        """**100행 전수.** 한 행이라도 규칙에 안 맞으면 시드가 그 자리에서 멈춘다."""
        stages = Counter(read_from_row(row).stage for row in _rows())
        assert stages[ReadStage.UNCONFIRMED] == 2, f"미확정이 {stages[ReadStage.UNCONFIRMED]}건 — S1-6·S1-7 표본이다"
        assert stages[ReadStage.CONFIRMED] == 96
        assert stages[ReadStage.NONE] == 2
