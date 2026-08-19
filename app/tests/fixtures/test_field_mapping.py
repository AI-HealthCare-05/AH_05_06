"""매핑표가 CSV·타입·API 계약과 맞는가 — KEY-30.

완료 조건 둘을 각각 검사로 옮긴 것이다.

  ① 데이터 생성자가 추가 해석 없이 fixture 를 만들 수 있음
     → 칸이 하나도 빠지지 않았는가 · 적어 둔 타입대로 읽히는가. **지금 돈다.**

  ② 필드명이 API 계약과 일치
     → FastAPI 가 코드에서 뽑는 OpenAPI 와 대조한다.
        환자·진료 API 가 아직 없어 지금은 skip 되고, 생기는 순간 켜진다.
        **손으로 관리하는 명세서를 따로 두지 않는다.**

     여기서 보는 것은 **이름뿐이다.** 타입(`string` / `integer` / `date-time` …)까지
     맞추는 자동 검증은 `KEY-32` 몫이다 — 이 파일이 그것까지 한다고 읽히면 안 된다.
"""

import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.tests.fixtures.mapping import API_SCHEMA_FOR, MAPPING, NOT_STORED, PENDING, Field, Kind, Where

CSV_PATH = Path(__file__).resolve().parents[3] / "docs" / "data" / "synthetic-patients.csv"

with CSV_PATH.open(encoding="utf-8-sig") as _f:
    ROWS: list[dict[str, str]] = list(csv.DictReader(_f))

COLUMNS: list[str] = list(ROWS[0].keys())


def values(column: str) -> list[str]:
    return [r[column].strip() for r in ROWS if r[column].strip()]


class TestNothingIsMissing:
    """빠진 칸이 있으면 시드가 그 값을 어디에 넣을지 스스로 정하게 된다."""

    def test_every_csv_column_is_mapped(self) -> None:
        missing = [c for c in COLUMNS if c not in MAPPING]
        assert not missing, f"매핑표에 없는 CSV 칸: {missing}"

    def test_mapping_has_no_ghost_column(self) -> None:
        ghosts = [c for c in MAPPING if c not in COLUMNS]
        assert not ghosts, f"CSV 에 없는데 매핑표에만 있는 칸: {ghosts}"

    def test_stored_fields_have_a_name(self) -> None:
        """어딘가에 저장한다면 필드명이 있어야 한다. 없으면 넣을 곳이 없다."""
        nameless = [c for c, f in MAPPING.items() if f.where not in NOT_STORED and not f.name]
        assert not nameless, f"저장한다면서 필드명이 없다: {nameless}"

    def test_unstored_fields_have_a_reason(self) -> None:
        """왜 저장하지 않는지 적혀 있어야 나중에 컬럼을 억지로 만들지 않는다."""
        silent = [c for c, f in MAPPING.items() if f.where in NOT_STORED and not f.note]
        assert not silent, f"저장하지 않는 이유가 안 적힌 칸: {silent}"


@pytest.mark.parametrize("column", COLUMNS)
class TestValuesMatchTheirKind:
    """적어 둔 타입대로 실제 값이 읽히는가.

    표에 `date` 라고 써 놓고 값이 `2026/08/19` 면 생성자가 또 해석해야 한다.
    """

    def test_required_columns_are_never_blank(self, column: str) -> None:
        field: Field = MAPPING[column]
        if not field.required:
            return
        blanks = [r["시나리오ID"] for r in ROWS if not r[column].strip()]
        assert not blanks, f"{column} 은 필수인데 비어 있다: {blanks[:5]}"

    def test_values_parse_as_declared(self, column: str) -> None:
        field: Field = MAPPING[column]
        bad: list[str] = []
        for value in values(column):
            if field.kind is Kind.DATE:
                try:
                    dt.date.fromisoformat(value)
                except ValueError:
                    bad.append(value)
            elif field.kind is Kind.INT and not re.fullmatch(r"-?\d+", value):
                bad.append(value)
            elif field.kind is Kind.DECIMAL and not re.fullmatch(r"-?\d+(\.\d+)?", value):
                bad.append(value)
            elif field.kind is Kind.LAB and value != PENDING and not re.fullmatch(r"-?\d+(\.\d+)?", value):
                bad.append(value)
            elif field.kind is Kind.BOOL and value not in ("Y", "N"):
                bad.append(value)
        assert not bad, f"{column} 은 {field.kind.value} 라고 적었는데 이렇게 들어 있다: {sorted(set(bad))[:5]}"

    def test_enum_values_stay_inside_the_list(self, column: str) -> None:
        field: Field = MAPPING[column]
        if field.kind is not Kind.ENUM or not field.choices:
            return
        outside = sorted({v for v in values(column) if v not in field.choices})
        assert not outside, f"{column} 에 정의 밖의 값이 있다: {outside}"


class TestLabResultsHaveTwoKindsOfEmpty:
    """검사는 「안 했다」와 「아직 안 나왔다」가 다르다. 시드가 이 둘을 갈라 넣어야 한다.

    빈 칸은 그 방문에 검사를 안 한 것이고(`S1-9` — 검사 칸을 통째로 접는다),
    `추후보고예정`은 검사는 했는데 결과가 늦는 것이다(`S1-7` — 그 줄만 점선 + `?`).
    같게 다루면 화면 둘 중 하나를 못 만든다.
    """

    LAB_COLUMNS = [c for c, f in MAPPING.items() if f.kind is Kind.LAB]

    def test_the_pending_marker_is_actually_used(self) -> None:
        rows = [r["시나리오ID"] for r in ROWS if any(r[c].strip() == PENDING for c in self.LAB_COLUMNS)]
        assert rows, f"{PENDING!r} 를 쓰는 행이 없다 — S1-7(판독 누락)을 볼 데이터가 없다"

    def test_visits_without_labs_exist_too(self) -> None:
        """계속 처방 방문의 대부분이 검사를 안 한 방문이다."""
        visits = [r for r in ROWS if r["진료일"].strip()]
        none = [r for r in visits if not any(r[c].strip() for c in self.LAB_COLUMNS)]
        assert none, "검사를 하나도 안 한 방문이 없다 — S1-9 를 볼 데이터가 없다"

    def test_pending_is_not_confused_with_missing(self) -> None:
        """`추후보고예정`인 행은 다른 검사 값이 있어야 한다.

        전부 비어 있으면 「검사를 안 했다」이지 「결과가 늦는다」가 아니다.
        """
        for row in ROWS:
            pending = [c for c in self.LAB_COLUMNS if row[c].strip() == PENDING]
            if not pending:
                continue
            others = [c for c in self.LAB_COLUMNS if c not in pending and row[c].strip()]
            assert others, f"{row['시나리오ID']} 는 {pending} 만 있고 나머지가 비었다 — 검사를 한 방문이 아니다"


class TestEnumListsAreUsed:
    """적어만 두고 아무도 안 쓰는 값이 있으면, 그 상태는 화면에서 볼 수 없다."""

    @pytest.mark.parametrize(
        "column", [c for c, f in MAPPING.items() if f.kind is Kind.ENUM and f.choices], ids=lambda c: c
    )
    def test_no_choice_is_dead(self, column: str) -> None:
        used = set(values(column))
        unused = [c for c in MAPPING[column].choices if c not in used]
        # 「진료기록 없음」처럼 한 행만 쓰는 값도 있으므로 절반 넘게 죽어 있을 때만 잡는다
        assert len(unused) <= len(MAPPING[column].choices) / 2, f"{column} 의 값 절반 이상이 안 쓰인다: {unused}"


class TestFieldNamesAgainstOpenApi:
    """② 필드 **이름**이 API 계약에 있는가 — FastAPI 가 코드에서 뽑는 것과 대조한다.

    손으로 관리하는 명세서를 두지 않는다. 코드가 곧 계약이고, 이 검사가 그 계약과
    합성 데이터를 이어 준다. 환자·진료 API 가 생기면 저절로 켜진다.

    **타입은 보지 않는다.** OpenAPI 스키마의 `type` · `format` 까지 맞추는 자동 검증은
    `KEY-32` 에서 한다. 여기서 이름만 보는 이유는, 이름이 어긋나면 타입을 볼
    필요도 없이 시드가 깨지기 때문이다 — 먼저 걸러 내는 자리다.
    """

    @staticmethod
    def load() -> dict[str, Any]:
        from fastapi.openapi.utils import get_openapi

        from app.main import app

        spec = get_openapi(title=app.title, version=app.version, routes=app.routes)
        return json.loads(json.dumps(spec))

    def test_openapi_is_generated_from_code(self) -> None:
        """자동 생성이 실제로 되는지부터 확인한다. 이게 되면 명세서를 손으로 안 써도 된다."""
        spec = self.load()
        assert spec["paths"], "OpenAPI 에 경로가 하나도 없다"
        assert spec.get("components", {}).get("schemas"), "OpenAPI 에 스키마가 없다"

    @pytest.mark.parametrize("where", sorted(API_SCHEMA_FOR), ids=lambda w: w.value)
    def test_mapped_field_names_exist_in_the_api_schema(self, where: Where) -> None:
        """이름이 있는지만 본다. 타입 일치는 KEY-32."""
        schemas = self.load().get("components", {}).get("schemas", {})
        found = next((schemas[n] for n in API_SCHEMA_FOR[where] if n in schemas), None)
        if found is None:
            pytest.skip(f"{where.value} API 가 아직 없다 — 생기면 이 검사가 켜진다 (KEY-12·KEY-16)")

        api_fields = set(found.get("properties", {}))
        ours = {f.name for f in MAPPING.values() if f.where is where and f.name}
        missing = sorted(ours - api_fields)
        assert not missing, f"매핑표가 쓰는 필드가 {where.value} API 에 없다: {missing}"
