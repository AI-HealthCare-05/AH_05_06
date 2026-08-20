"""합성 환자·진료 데이터 자동 검증 — KEY-32.

정본 CSV를 DB에 넣기 전에 필수값, 코드, 관계, 날짜와 금지 패턴을 한 번에
검사한다. 오류를 하나씩 고치며 다시 실행하지 않아도 되도록 발견한 문제를 모두
모아 행·시나리오·필드와 함께 보여 준다.
"""

import csv
import datetime as dt
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core.masking import JWT, SECRET_KEYS
from app.core.utils.common import normalize_phone_number
from app.tests.fixtures.mapping import MAPPING, PENDING, Kind, Where
from app.tests.fixtures.staff import DEFAULT_HOSPITAL, Staff, all_staff

PATIENT_CSV_PATH = Path(__file__).resolve().parents[3] / "docs" / "data" / "synthetic-patients.csv"

# 합성 데이터가 표현하는 고정 시점. 실행하는 날에 따라 같은 fixture의 판정이
# 달라지지 않게 벽시계 대신 데이터 세트 기준일을 쓴다.
DATASET_AS_OF = dt.date(2026, 8, 20)

SCENARIO_ID_PATTERN = re.compile(r"SYN-(?:EMS|PCOS|BOTH|DUP)-\d{2}|SYN-BULK-\d{3}")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
DOSAGE_PATTERN = re.compile(r"\d+/\d+/(\d+)")
MESSAGE_ROUND_PATTERN = re.compile(r"D\+(\d+)")

SECRET_KEY_PATTERN = "|".join(re.escape(key) for key in (*SECRET_KEYS, "jwt"))
FORBIDDEN_COLUMN_PATTERN = re.compile(SECRET_KEY_PATTERN, re.IGNORECASE)
FORBIDDEN_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("JWT", JWT),
    ("API key", re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")),
    (
        "credential assignment",
        re.compile(rf"(?:{SECRET_KEY_PATTERN})\s*[:=]\s*\S+", re.IGNORECASE),
    ),
)

VISIT_FIELDS = tuple(
    column
    for column, field in MAPPING.items()
    if field.where not in {Where.PATIENT, Where.DOC_ONLY} and column != "진료일"
)

MESSAGE_ALLOWED_STATUSES = frozenset({"발송 완료", "보완", "계획된 중단"})
MESSAGE_ROUNDS = frozenset({7, 15, 30})
IDENTITY_FIELDS = ("이름", "생년월일", "휴대폰")

PatientRow = dict[str, str]


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    line: int
    scenario_id: str
    field: str
    message: str

    def render(self) -> str:
        return f"[{self.code}] {self.line}행 {self.scenario_id} {self.field}: {self.message}"


class SyntheticDataValidationError(ValueError):
    """합성 데이터가 안전하게 적재될 수 없을 때 발생한다."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("합성 데이터 검증 실패\n" + "\n".join(issue.render() for issue in self.issues))


def read_patient_rows(path: Path = PATIENT_CSV_PATH) -> list[PatientRow]:
    """CSV를 읽고 열 수가 깨졌으면 값 검증 전에 명확하게 실패한다."""
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        expected = list(MAPPING)
        if reader.fieldnames != expected:
            issue = ValidationIssue(
                code="CSV_HEADER",
                line=1,
                scenario_id="<header>",
                field="CSV 헤더",
                message=f"기대 열 {expected}, 실제 열 {reader.fieldnames}",
            )
            raise SyntheticDataValidationError([issue])

        rows: list[PatientRow] = []
        shape_issues: list[ValidationIssue] = []
        for line, raw in enumerate(reader, start=2):
            scenario_id = raw.get("시나리오ID")
            scenario_text = scenario_id.strip() if isinstance(scenario_id, str) else "<unknown>"
            if raw.get(None) is not None:
                shape_issues.append(ValidationIssue("CSV_SHAPE", line, scenario_text, "CSV 행", "헤더보다 값이 많다"))
                continue

            missing = [column for column in expected if not isinstance(raw.get(column), str)]
            if missing:
                shape_issues.append(ValidationIssue("CSV_SHAPE", line, scenario_text, "CSV 행", f"빠진 열 {missing}"))
                continue

            rows.append({column: str(raw[column]).strip() for column in expected})

    if shape_issues:
        raise SyntheticDataValidationError(shape_issues)
    return rows


def _add_issue(
    issues: list[ValidationIssue],
    code: str,
    index: int,
    row: PatientRow,
    field: str,
    message: str,
) -> None:
    issues.append(
        ValidationIssue(
            code=code,
            line=index + 2,
            scenario_id=row.get("시나리오ID") or "<blank>",
            field=field,
            message=message,
        )
    )


def _parse_iso_date(value: str) -> dt.date | None:
    """오직 YYYY-MM-DD 달력 날짜만 파싱한다."""
    if not value:
        return None
    if DATE_PATTERN.fullmatch(value) is None:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _parse_date(issues: list[ValidationIssue], index: int, row: PatientRow, field: str) -> dt.date | None:
    value = row.get(field, "")
    parsed = _parse_iso_date(value)
    if value and parsed is None:
        _add_issue(issues, "DATE_FORMAT", index, row, field, f"YYYY-MM-DD 형식이 아니다: {value!r}")
    return parsed


def _parse_int(issues: list[ValidationIssue], index: int, row: PatientRow, field: str) -> int | None:
    value = row.get(field, "")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        _add_issue(issues, "NUMBER_FORMAT", index, row, field, f"정수가 아니다: {value!r}")
        return None


def _date_or_none(row: PatientRow, field: str) -> dt.date | None:
    """이미 오류가 보고된 날짜를 관계 검사에서 조용히 건너뛴다."""
    return _parse_iso_date(row.get(field, ""))


def _validate_declared_value(issues: list[ValidationIssue], index: int, row: PatientRow, column: str) -> None:
    field = MAPPING[column]
    value = row[column]
    if field.required and not value:
        _add_issue(issues, "REQUIRED", index, row, column, "필수값이 비어 있다")
    if not value:
        return
    if field.kind is Kind.BOOL and value not in {"Y", "N"}:
        _add_issue(issues, "CODE_RANGE", index, row, column, f"Y 또는 N이어야 한다: {value!r}")
    elif field.kind is Kind.ENUM and field.choices and value not in field.choices:
        _add_issue(
            issues,
            "CODE_RANGE",
            index,
            row,
            column,
            f"허용값 {list(field.choices)} 밖의 값이다: {value!r}",
        )
    elif field.kind is Kind.DECIMAL:
        _validate_decimal(issues, index, row, column, value)
    elif field.kind is Kind.LAB and value != PENDING:
        _validate_lab_value(issues, index, row, column, value)


def _validate_decimal(issues: list[ValidationIssue], index: int, row: PatientRow, column: str, value: str) -> None:
    if NUMBER_PATTERN.fullmatch(value) is None:
        _add_issue(issues, "NUMBER_FORMAT", index, row, column, f"숫자가 아니다: {value!r}")


def _validate_lab_value(issues: list[ValidationIssue], index: int, row: PatientRow, column: str, value: str) -> None:
    if NUMBER_PATTERN.fullmatch(value) is None:
        _add_issue(
            issues,
            "LAB_FORMAT",
            index,
            row,
            column,
            f"검사 수치 또는 {PENDING!r}가 아니다: {value!r}",
        )


def _validate_required_and_codes(issues: list[ValidationIssue], index: int, row: PatientRow) -> None:
    unknown = sorted(set(row) - set(MAPPING))
    missing = sorted(set(MAPPING) - set(row))
    if unknown or missing:
        _add_issue(
            issues,
            "ROW_COLUMNS",
            index,
            row,
            "CSV 행",
            f"알 수 없는 열 {unknown}, 빠진 열 {missing}",
        )
        return

    for column in MAPPING:
        _validate_declared_value(issues, index, row, column)


def _validate_patterns(issues: list[ValidationIssue], index: int, row: PatientRow) -> None:
    scenario_id = row.get("시나리오ID", "")
    if scenario_id and SCENARIO_ID_PATTERN.fullmatch(scenario_id) is None:
        _add_issue(issues, "SCENARIO_FORMAT", index, row, "시나리오ID", f"정해진 형식이 아니다: {scenario_id!r}")

    chart_no = row.get("차트번호", "")
    if chart_no and len(chart_no) > 50:
        _add_issue(issues, "CHART_FORMAT", index, row, "차트번호", f"1~50자 범위여야 한다: {chart_no!r}")

    phone = row.get("휴대폰", "")
    if phone:
        normalized_phone = normalize_phone_number(phone)
        if not 10 <= len(normalized_phone) <= 11:
            _add_issue(issues, "PHONE_FORMAT", index, row, "휴대폰", "정규화 후 숫자 10~11자리여야 한다")

    for column, value in row.items():
        for label, pattern in FORBIDDEN_VALUE_PATTERNS:
            if pattern.search(value):
                _add_issue(issues, "FORBIDDEN_PATTERN", index, row, column, f"{label} 형태의 값을 포함한다")


def _validate_visit_date(
    issues: list[ValidationIssue], index: int, row: PatientRow, birth_date: dt.date | None, visit_date: dt.date
) -> None:
    if birth_date is not None and birth_date >= visit_date:
        _add_issue(issues, "DATE_ORDER", index, row, "생년월일", "생년월일은 진료일보다 앞서야 한다")
    if visit_date > DATASET_AS_OF:
        _add_issue(issues, "DATE_RANGE", index, row, "진료일", f"데이터 기준일 {DATASET_AS_OF} 뒤의 진료다")
    if visit_date.weekday() == 6:
        _add_issue(issues, "VISIT_WEEKDAY", index, row, "진료일", "일요일 진료는 허용하지 않는다")


def _validate_dosage(issues: list[ValidationIssue], index: int, row: PatientRow, days: int | None) -> None:
    if days is not None and not 1 <= days <= 365:
        _add_issue(issues, "DAYS_RANGE", index, row, "처방일수", f"1~365일 범위 밖이다: {days}")

    dosage = row.get("총투원문", "")
    unit = row.get("총투단위", "")
    if dosage or unit or days is not None:
        match = DOSAGE_PATTERN.fullmatch(dosage)
        if match is None:
            _add_issue(issues, "DOSAGE_FORMAT", index, row, "총투원문", f"a/b/c 형식이 아니다: {dosage!r}")
        elif unit in {"", "일수", "통수"} and days is not None:
            expected_days = int(match.group(1)) * (28 if unit == "통수" else 1)
            if days != expected_days:
                _add_issue(
                    issues,
                    "DOSAGE_DAYS",
                    index,
                    row,
                    "처방일수",
                    f"총투원문·단위 계산값 {expected_days}일과 다르다: {days}일",
                )


def _validate_exhaustion_date(
    issues: list[ValidationIssue],
    index: int,
    row: PatientRow,
    visit_date: dt.date,
    exhaustion_date: dt.date | None,
    days: int | None,
) -> None:
    if days is not None and exhaustion_date is not None:
        expected_exhaustion = visit_date + dt.timedelta(days=days)
        if exhaustion_date != expected_exhaustion:
            _add_issue(
                issues,
                "EXHAUSTION_DATE",
                index,
                row,
                "소진예정일",
                f"진료일+처방일수는 {expected_exhaustion}이어야 한다: {exhaustion_date}",
            )


def _validate_dates_and_dosage(issues: list[ValidationIssue], index: int, row: PatientRow) -> None:
    birth_date = _parse_date(issues, index, row, "생년월일")
    visit_date = _parse_date(issues, index, row, "진료일")
    exhaustion_date = _parse_date(issues, index, row, "소진예정일")
    days = _parse_int(issues, index, row, "처방일수")

    if not row.get("진료일"):
        filled = [field for field in VISIT_FIELDS if row.get(field)]
        if filled:
            _add_issue(
                issues,
                "PATIENT_ONLY",
                index,
                row,
                "진료일",
                f"진료일 없는 환자-only 행에 진료값이 있다: {filled}",
            )
        return

    if visit_date is None:
        return

    _validate_visit_date(issues, index, row, birth_date, visit_date)
    _validate_dosage(issues, index, row, days)
    _validate_exhaustion_date(issues, index, row, visit_date, exhaustion_date, days)


def _parse_message_rounds(issues: list[ValidationIssue], index: int, row: PatientRow, rounds_text: str) -> list[int]:
    rounds: list[int] = []
    for part in rounds_text.split(" · "):
        match = MESSAGE_ROUND_PATTERN.fullmatch(part)
        if match is None:
            _add_issue(issues, "MESSAGE_FORMAT", index, row, "확인문자회차", f"D+숫자 형식이 아니다: {part!r}")
            continue
        rounds.append(int(match.group(1)))
    return rounds


def _validate_message_rounds(
    issues: list[ValidationIssue], index: int, row: PatientRow, rounds: list[int], visit_date: dt.date | None
) -> None:
    invalid = sorted(set(rounds) - MESSAGE_ROUNDS)
    if invalid:
        _add_issue(issues, "CODE_RANGE", index, row, "확인문자회차", f"허용되지 않은 회차다: {invalid}")
    if rounds != sorted(set(rounds)):
        _add_issue(issues, "MESSAGE_ORDER", index, row, "확인문자회차", "회차가 중복되었거나 오름차순이 아니다")
    if row["진료상태"] not in MESSAGE_ALLOWED_STATUSES:
        _add_issue(
            issues,
            "MESSAGE_STATUS",
            index,
            row,
            "진료상태",
            f"{row['진료상태']!r} 상태에는 발송 회차를 둘 수 없다",
        )
    if row["문자수신동의"] == "N":
        _add_issue(issues, "SMS_OPT_OUT", index, row, "확인문자회차", "문자 수신 거부 환자에게 발송 회차가 있다")
    if visit_date is not None:
        future_rounds = [round_no for round_no in rounds if visit_date + dt.timedelta(days=round_no) > DATASET_AS_OF]
        if future_rounds:
            _add_issue(
                issues,
                "MESSAGE_BEFORE_DUE",
                index,
                row,
                "확인문자회차",
                f"데이터 기준일에 아직 오지 않은 회차다: {future_rounds}",
            )


def _validate_exit_relations(
    issues: list[ValidationIssue], index: int, row: PatientRow, exhaustion_date: dt.date | None
) -> None:
    exit_flag = row["이탈표시"]
    if row["진료상태"] == "계획된 중단" and exit_flag:
        _add_issue(issues, "PLANNED_STOP_EXIT", index, row, "이탈표시", "계획된 중단은 이탈로 표시하지 않는다")
    if exit_flag == "소진 후 7일 경과" and exhaustion_date is not None:
        due = exhaustion_date + dt.timedelta(days=7)
        if DATASET_AS_OF < due:
            _add_issue(issues, "EXIT_BEFORE_DUE", index, row, "이탈표시", f"{due} 전에는 소진 후 7일 경과가 아니다")


def _validate_message_relations(issues: list[ValidationIssue], index: int, row: PatientRow) -> None:
    rounds_text = row["확인문자회차"]
    visit_date = _date_or_none(row, "진료일")
    exhaustion_date = _date_or_none(row, "소진예정일")

    if rounds_text:
        rounds = _parse_message_rounds(issues, index, row, rounds_text)
        _validate_message_rounds(issues, index, row, rounds, visit_date)

    if row["열람여부"] and not rounds_text:
        _add_issue(issues, "READ_WITHOUT_MESSAGE", index, row, "열람여부", "발송 회차 없이 열람 상태만 있다")
    _validate_exit_relations(issues, index, row, exhaustion_date)


def validate_patient_rows(rows: Sequence[PatientRow], staff: Sequence[Staff] | None = None) -> None:
    """정상 데이터면 반환하고, 하나라도 틀리면 모든 오류를 모아 예외로 알린다."""
    issues: list[ValidationIssue] = []
    staff_rows = tuple(all_staff() if staff is None else staff)
    doctors = {person.name for person in staff_rows if person.hospital == DEFAULT_HOSPITAL and "doctor" in person.roles}
    seen_scenarios: dict[str, int] = {}
    identities_by_chart: dict[str, tuple[str, ...]] = {}

    forbidden_columns = sorted(column for column in MAPPING if FORBIDDEN_COLUMN_PATTERN.search(column))
    if forbidden_columns:
        issues.append(
            ValidationIssue(
                "FORBIDDEN_COLUMN",
                1,
                "<header>",
                "CSV 헤더",
                f"비밀값을 저장할 수 있는 열이 있다: {forbidden_columns}",
            )
        )

    for index, row in enumerate(rows):
        _validate_required_and_codes(issues, index, row)
        if set(row) != set(MAPPING):
            continue
        _validate_patterns(issues, index, row)
        _validate_dates_and_dosage(issues, index, row)
        _validate_message_relations(issues, index, row)

        scenario_id = row["시나리오ID"]
        if scenario_id in seen_scenarios:
            _add_issue(
                issues,
                "UNIQUE_SCENARIO",
                index,
                row,
                "시나리오ID",
                f"{seen_scenarios[scenario_id]}행과 중복이다",
            )
        else:
            seen_scenarios[scenario_id] = index + 2

        chart_no = row["차트번호"]
        identity = tuple(row[field] for field in IDENTITY_FIELDS)
        previous = identities_by_chart.get(chart_no)
        if previous is not None and previous != identity:
            _add_issue(
                issues,
                "PATIENT_IDENTITY",
                index,
                row,
                "차트번호",
                f"같은 차트번호의 환자 식별정보가 다르다: {previous} != {identity}",
            )
        else:
            identities_by_chart[chart_no] = identity

        doctor = row["담당의"]
        if row["진료일"] and doctor not in doctors:
            _add_issue(
                issues,
                "DOCTOR_REFERENCE",
                index,
                row,
                "담당의",
                f"{DEFAULT_HOSPITAL} doctor fixture에 없는 이름이다: {doctor!r}",
            )

    if issues:
        raise SyntheticDataValidationError(issues)


def validate_canonical_patient_data() -> None:
    """CI와 seed가 같은 정본 검사를 호출할 수 있는 진입점."""
    validate_patient_rows(read_patient_rows())
