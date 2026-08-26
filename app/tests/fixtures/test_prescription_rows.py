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
        items = items_from_row("비잔정(디에노게스트) 2mg", "1일 1회", "84")
        assert len(items) == 1
        assert items[0].name == "비잔정(디에노게스트) 2mg"
        assert items[0].frequency == "1일 1회"
        assert items[0].duration_days == 84

    def test_a_two_drug_row_makes_two_items_in_order(self) -> None:
        items = items_from_row("비잔정(디에노게스트) 2mg + 진통제", "1일 1회 + 필요시", "84")
        assert [i.name for i in items] == ["비잔정(디에노게스트) 2mg", "진통제"]
        assert [i.frequency for i in items] == ["1일 1회", AS_NEEDED]

    def test_an_empty_row_makes_nothing(self) -> None:
        assert items_from_row("", "", "") == []

    def test_mismatched_counts_are_refused_not_guessed(self) -> None:
        """짝이 안 맞으면 추측해서 붙이지 않는다 — 어느 약의 용법인지 모른다."""
        with pytest.raises(PrescriptionRowError):
            items_from_row("비잔정(디에노게스트) 2mg + 진통제", "1일 1회", "84")


class TestAsNeededDrugsGetNoDuration:
    """**이 파일의 존재 이유다.**

    `처방일수` 는 행에 하나뿐인데 약은 둘일 수 있다. 그 하나를 두 줄에 다 붙이면
    안내문이 「진통제를 84일간 드세요」라고 말한다.
    """

    def test_the_as_needed_line_is_left_empty(self) -> None:
        items = items_from_row("비잔정(디에노게스트) 2mg + 진통제", "1일 1회 + 필요시", "84")
        by_name = {i.name: i for i in items}
        assert by_name["비잔정(디에노게스트) 2mg"].duration_days == 84
        assert by_name["진통제"].duration_days is None, "필요시 약에 기간이 붙었다"

    def test_two_scheduled_drugs_both_keep_the_duration(self) -> None:
        """`필요시` 가 아니면 둘 다 기간을 받는다 — 규칙이 과하게 걸리지 않는 것."""
        items = items_from_row("야즈정(드로스피레논/에티닐에스트라디올) + 메트포르민 500mg", "1일 1회 + 1일 2회", "84")
        assert [i.duration_days for i in items] == [84, 84]

    def test_a_non_numeric_duration_becomes_empty(self) -> None:
        items = items_from_row("비잔정(디에노게스트) 2mg", "1일 1회", "")
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


# ── 약품명 표기 — KEY-183 ─────────────────────────────────────────────────────

#: 브랜드명 → 함께 적을 성분명. **여기가 정본이다.**
#:
#: 성분명은 지어내지 않는다(`docs/synthetic-data-spec.md` §1 「임의로 만들지
#: 않는다」). 이 표의 값은 이희진 님이 정한 표기를 그대로 옮긴 것이고,
#: `docs/decisions/KEY-163-ocr-real-contract.md` §3 에 이미 같은 모양으로 적혀
#: 있다. 성분을 새로 더할 때는 식약처 의약품정보에서 확인하고 근거를 남긴다.
INGREDIENTS = {
    "비잔정": "디에노게스트",
    "야즈정": "드로스피레논/에티닐에스트라디올",
}

#: 제품명이 곧 성분명이라 괄호를 붙이지 않는 것.
SAME_AS_INGREDIENT = ("메트포르민",)

FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "js"
DECISION = Path(__file__).resolve().parents[3] / "docs" / "decisions" / "KEY-163-ocr-real-contract.md"


def expected_name(brand: str) -> str:
    return f"{brand}({INGREDIENTS[brand]})"


class TestDrugNamesCarryTheirIngredient:
    """`브랜드명(성분명) 용량` 으로 **세 표면이 같은 말을 하는가** — KEY-183.

    이 검사가 생긴 이유가 곧 이 티켓이다. 같은 약이 세 곳에서 다르게 적혀
    있었다.

        정본 CSV        비잔정 2mg
        KEY-163 §3      비잔정(디에노게스트) 2mg
        프런트          비잔정 2mg · 성분 디에노게스트

    처방 세트 매칭이 id 가 아니라 **이름 문자열** 기준으로 바뀌면서
    (`60d2669`), 이 차이는 보기 나쁜 것을 넘어 매칭 성패에 닿게 됐다.

    한 곳만 고치면 다시 갈린다. 그래서 **세 표면을 한 검사에서 맞춘다** —
    파이썬 검사가 프런트 파일을 읽는 것이 어색하지만, 이 불변식은 어느 한
    표면에도 속하지 않는다.
    """

    def test_the_canonical_csv_spells_out_every_ingredient(self) -> None:
        offenders = []
        for row in ROWS:
            for piece in (row.get("약") or "").split(" + "):
                piece = piece.strip()
                for brand, _ in INGREDIENTS.items():
                    if piece.startswith(brand) and expected_name(brand) not in piece:
                        offenders.append(f"{row.get('시나리오ID')}: {piece}")
        assert not offenders, f"성분명이 병기되지 않은 약: {offenders[:5]}"

    def test_a_drug_whose_name_is_its_ingredient_gets_no_parentheses(self) -> None:
        """메트포르민에 `메트포르민(메트포르민)` 을 붙이면 읽는 사람만 헷갈린다."""
        for row in ROWS:
            for piece in (row.get("약") or "").split(" + "):
                for brand in SAME_AS_INGREDIENT:
                    if piece.strip().startswith(brand):
                        assert "(" not in piece, f"제품명=성분명인데 괄호가 붙었다: {piece}"

    def test_the_decision_document_agrees_with_the_table(self) -> None:
        """`KEY-163` §3 이 정본이라 여기와 어긋나면 둘 중 하나가 틀린 것이다."""
        text = DECISION.read_text(encoding="utf-8")
        assert expected_name("비잔정") in text, "결정 문서가 다른 표기를 쓴다"

    #: 약을 **처방 항목으로 지목하는** 자리. 여기만 이 규칙의 대상이다.
    #:
    #: 세트 요약(`자궁내막증 · 비잔 (계속)`)과 산문(`비잔 복용 중에는…`),
    #: 절 제목(`비잔정 2mg 드시는 동안`)은 짧은 이름을 쓴다. 거기까지 괄호를
    #: 넣을지는 **표기 규칙 결정**이라 이 검사가 앞서 정하지 않는다 — `#142`
    #: 에서 이희진 님께 여쭤 두었다.
    NAMING_SITES = ('name: "', "처방받은 약 — ")

    @pytest.mark.parametrize("name", ["guide-api.js", "doctor-api.js"])
    def test_the_screen_shows_the_same_spelling(self, name: str) -> None:
        """**환자·원장님이 읽는 약품명 줄**이 규칙과 같아야 한다.

        `drugs` 는 목 전용이지만(실서버 계약은 `sections` 뿐) 데모에서 그대로
        화면에 나간다. 여기가 어긋나면 시연에서 세 표기가 다시 보인다.
        """
        text = (FRONTEND / name).read_text(encoding="utf-8")
        checked = 0
        for line in text.splitlines():
            if not any(site in line for site in self.NAMING_SITES):
                continue
            for brand in INGREDIENTS:
                if brand not in line:
                    continue
                checked += 1
                assert expected_name(brand) in line, f"{name} 에 옛 표기가 남았다: {line.strip()}"
        assert checked, f"{name} 에서 약품명 줄을 하나도 못 찾았다 — 검사가 헛돈다"
