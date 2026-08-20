"""합성 데이터 정상·오류 fixture 자동 검증 — KEY-32."""

from copy import deepcopy
from pathlib import Path

import pytest

from app.tests.fixtures.validation import (
    PATIENT_CSV_PATH,
    SyntheticDataValidationError,
    read_patient_rows,
    validate_canonical_patient_data,
    validate_patient_rows,
)


def changed_row(**changes: str) -> list[dict[str, str]]:
    rows = deepcopy(read_patient_rows())
    rows[0].update(changes)
    return rows


def error_text(rows: list[dict[str, str]]) -> str:
    with pytest.raises(SyntheticDataValidationError) as caught:
        validate_patient_rows(rows)
    return str(caught.value)


class TestCanonicalDataPasses:
    def test_the_repository_fixture_is_valid(self) -> None:
        validate_canonical_patient_data()


class TestBrokenCsvShapeFailsClearly:
    def test_a_missing_header_names_the_header(self, tmp_path: Path) -> None:
        source = PATIENT_CSV_PATH.read_text(encoding="utf-8-sig")
        broken = source.replace("시나리오ID,", "", 1)
        path = tmp_path / "missing-header.csv"
        path.write_text(broken, encoding="utf-8")

        with pytest.raises(SyntheticDataValidationError, match=r"\[CSV_HEADER\].*CSV 헤더"):
            read_patient_rows(path)

    def test_an_extra_unquoted_comma_names_the_line(self, tmp_path: Path) -> None:
        source = PATIENT_CSV_PATH.read_text(encoding="utf-8-sig")
        broken = source.replace("정상 진행 · 기준 케이스", "정상, 진행 · 기준 케이스", 1)
        path = tmp_path / "extra-column.csv"
        path.write_text(broken, encoding="utf-8")

        with pytest.raises(SyntheticDataValidationError, match=r"\[CSV_SHAPE\] 2행 SYN-EMS-01"):
            read_patient_rows(path)


@pytest.mark.parametrize(
    ("changes", "code", "field"),
    [
        ({"이름": ""}, "REQUIRED", "이름"),
        ({"시나리오ID": "patient-1"}, "SCENARIO_FORMAT", "시나리오ID"),
        ({"차트번호": "12A"}, "CHART_FORMAT", "차트번호"),
        ({"휴대폰": "010-123-4567"}, "PHONE_FORMAT", "휴대폰"),
        ({"문자수신동의": "true"}, "CODE_RANGE", "문자수신동의"),
        ({"생년월일": "1989/03/12"}, "DATE_FORMAT", "생년월일"),
        ({"진료일": "1988-01-01"}, "DATE_ORDER", "생년월일"),
        ({"진료일": "2026-08-16"}, "VISIT_WEEKDAY", "진료일"),
        ({"처방일수": "eighty-four"}, "NUMBER_FORMAT", "처방일수"),
        ({"처방일수": "0"}, "DAYS_RANGE", "처방일수"),
        ({"처방일수": "3"}, "DOSAGE_DAYS", "처방일수"),
        ({"소진예정일": "2026-10-22"}, "EXHAUSTION_DATE", "소진예정일"),
        ({"담당의": "없는의사"}, "DOCTOR_REFERENCE", "담당의"),
        ({"케이스의도": "token=do-not-store-this"}, "FORBIDDEN_PATTERN", "케이스의도"),
    ],
    ids=[
        "required",
        "scenario-code",
        "chart-code",
        "phone-pattern",
        "yes-no-code",
        "date-format",
        "date-order",
        "sunday",
        "number-format",
        "days-range",
        "dosage-days",
        "exhaustion-date",
        "doctor-reference",
        "secret-pattern",
    ],
)
def test_an_intentional_error_reports_its_code_and_field(changes: dict[str, str], code: str, field: str) -> None:
    message = error_text(changed_row(**changes))
    assert f"[{code}]" in message
    assert f"2행 {changes.get('시나리오ID', 'SYN-EMS-01')}" in message
    assert field in message


class TestRelationshipsFailClearly:
    def test_a_duplicate_scenario_points_to_the_original_line(self) -> None:
        rows = read_patient_rows()
        rows[1]["시나리오ID"] = rows[0]["시나리오ID"]

        message = error_text(rows)
        assert "[UNIQUE_SCENARIO]" in message
        assert "2행과 중복" in message

    def test_same_chart_cannot_identify_two_people(self) -> None:
        rows = read_patient_rows()
        duplicate = deepcopy(rows[0])
        duplicate["시나리오ID"] = "SYN-BULK-999"
        duplicate["휴대폰"] = "010-9999-9999"
        rows.append(duplicate)

        message = error_text(rows)
        assert "[PATIENT_IDENTITY]" in message
        assert "같은 차트번호의 환자 식별정보가 다르다" in message

    def test_patient_only_row_cannot_carry_visit_data(self) -> None:
        rows = read_patient_rows()
        patient_only = next(row for row in rows if row["시나리오ID"] == "SYN-DUP-11")
        patient_only["담당의"] = "박연"

        message = error_text(rows)
        assert "[PATIENT_ONLY]" in message
        assert "담당의" in message

    def test_opted_out_patient_cannot_have_message_rounds(self) -> None:
        message = error_text(changed_row(문자수신동의="N"))
        assert "[SMS_OPT_OUT]" in message

    def test_read_state_needs_a_sent_message(self) -> None:
        message = error_text(changed_row(확인문자회차="", 열람여부="열람"))
        assert "[READ_WITHOUT_MESSAGE]" in message

    def test_planned_stop_is_not_patient_exit(self) -> None:
        rows = read_patient_rows()
        planned_stop = next(row for row in rows if row["시나리오ID"] == "SYN-EMS-03")
        planned_stop["이탈표시"] = "소진 후 7일 경과"

        message = error_text(rows)
        assert "[PLANNED_STOP_EXIT]" in message

    def test_future_message_round_is_rejected(self) -> None:
        message = error_text(changed_row(확인문자회차="D+7 · D+15 · D+30"))
        assert "[MESSAGE_BEFORE_DUE]" in message
        assert "30" in message
