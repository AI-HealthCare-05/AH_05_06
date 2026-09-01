"""CSV 한 행을 처방 항목으로 가르는 규칙 — KEY-137.

이 검사가 없으면 규칙이 시드 안에서만 돌고 아무도 확인하지 않는다. 실제로
처음에는 `scripts/seed.py` 안에 있었고, **`필요시` 에도 기간을 붙이는 돌연변이를
심었는데 검사가 하나도 안 죽었다.** 그래서 규칙을 여기로 꺼냈다.
"""

import ast
import csv
import re
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

#: `브랜드(성분) 용량` 에서 브랜드와 성분을 떼어 내는 자.
NAMED = re.compile(r"^(?P<brand>[가-힣A-Za-z]+)\((?P<ingredient>[^)]+)\)")


def ingredients_from_csv() -> dict[str, str]:
    """**정본 CSV 에서 읽는다** — 코드에 표를 박지 않는다.

    처음에는 이 파일에 `{"비잔정": "디에노게스트", …}` 를 적고 「여기가
    정본이다」라고 주석을 달았다. 그런데 `docs/synthetic-data-spec.md` §1 이
    이렇게 못 박고 있다.

        정본은 `docs/data/` 아래 CSV 둘뿐이다 — **코드에 값을 박지 않는다**

    정면으로 어긴 것이었다 (이희진 님 `#142` 리뷰). 표를 걷고 CSV 에서 뽑으니
    **야즈정도 저절로 따라온다** — 손으로 적었을 때는 빠뜨리기 쉬운 자리다.
    """
    found: dict[str, str] = {}
    for row in ROWS:
        for piece in (row.get("약") or "").split(" + "):
            match = NAMED.match(piece.strip())
            if match:
                found[match.group("brand")] = match.group("ingredient")
    return found


INGREDIENTS = ingredients_from_csv()

#: 제품명이 곧 성분명이라 괄호를 붙이지 않는 것.
SAME_AS_INGREDIENT = ("메트포르민",)

FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "js"
DOCS = Path(__file__).resolve().parents[3] / "docs"

#: **CSV 의 「약」 값을 그대로 옮겨 적는 문서들.** 여기는 형식을 따라와야 한다.
#:
#: 처음엔 결정 문서 하나만 봤다. 그래서 `docs/qa/KEY-148-walking-skeleton.md`
#: 가 옛 표기로 남은 것을 이 검사가 아니라 **사람이 찾았다** (이희진 님 `#142`).
TRANSCRIBING_DOCS = (
    "decisions/KEY-163-ocr-real-contract.md",
    "qa/KEY-148-walking-skeleton.md",
    "ai-worker.md",
)

#: 약 이름이 나오지만 **형식을 따라오면 안 되는** 문서. 까닭을 함께 적는다.
EXEMPT_DOCS = {
    # 와이어프레임은 고정된 스냅샷이고, 여기 나오는 것은 절 제목
    # (`야즈정 드시는 동안`)이라 브랜드만 쓰는 것이 맞다 — `#142` ④ 결정.
    "wireframes/PATCH-2.3-to-2.3.1.md",
    # API 계약 문서라 약 이름(drugName, n)과 성분(drugSub, s)이 별도 JSON
    # 필드로 분리되어 있다. 서술문 형식을 강제하면 API 계약 자체가 바뀐다.
    "api/patient.md",
}


def code_strings(source: str) -> list[str]:
    """**코드가 쓰는 문자열만** 돌려준다 — 설명(도크스트링)은 뺀다.

    왜 옛 표기를 걷었는지 적으려면 그 표기를 쓰게 되는데, 그것까지 잡으면
    설명을 못 남긴다. 앞글자로 거르려다 도크스트링 **안쪽 줄**에 걸렸다
    (`scripts/deployment.sh` 의 `chmod` 검사에서도 같은 자리였다).

    줄이 아니라 **구문**으로 가른다.
    """
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


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

    def test_a_branded_tablet_always_carries_its_ingredient(self) -> None:
        """**정본 CSV 가 조용히 후퇴하지 못하게** 한다 — `#142` 리뷰 뒤에 생긴 구멍.

        표를 CSV 에서 뽑게 고쳤더니(그게 맞다) 새 구멍이 생겼다 — CSV 에서 병기를
        걷으면 표에서도 사라져서 **아무도 안 운다.** 실제로 야즈정을 되돌려 보니
        검사가 조용했다.

        그래서 값을 박는 대신 **모양으로 잰다.**

            비잔정(디에노게스트) 2mg   「…정」으로 끝나는 제품명 → 병기해야 한다
            야즈정(드로스피레논/…)      같다
            메트포르민 500mg           성분명 자체라 「정」이 안 붙는다 → 면제
            진통제                     제품명이 아니다 → 면제

        새 약이 들어와도 규칙이 따라간다.
        """
        offenders = []
        for row in ROWS:
            for piece in (row.get("약") or "").split(" + "):
                piece = piece.strip()
                head = piece.split("(")[0].split(" ")[0]
                if head.endswith("정") and "(" not in piece:
                    offenders.append(f"{row.get('시나리오ID')}: {piece}")

        assert not offenders, f"제품명인데 성분이 안 적혔다: {sorted(set(offenders))[:5]}"

    def test_at_least_the_two_known_tablets_are_there(self) -> None:
        """훑기가 헛돌지 않는지 — 조각이 하나도 안 걸리면 위 검사는 늘 통과한다."""
        assert len(INGREDIENTS) >= 2, f"정본에서 뽑은 것이 너무 적다: {INGREDIENTS}"

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

    @pytest.mark.parametrize("rel", TRANSCRIBING_DOCS)
    def test_the_documents_do_not_contradict_the_csv(self, rel: str) -> None:
        """CSV 를 옮겨 적은 문서가 **적어 둔 약에 대해서만** 어긋나지 않는지 본다.

        예전 판은 비잔정만 확인하면서 주석에는 「§3 에 이미 같은 모양으로 적혀
        있다」고 적었다. 그런데 **§3 에는 야즈정이 아예 없다** — 있지도 않은
        일치를 주장하고 있었다 (이희진 님 `#142` 리뷰).

        문서에 없는 약을 있어야 한다고 우기지 않는다. 적힌 것만 대조하고, 무엇도
        대조하지 못하면 그때 운다 — 그래야 검사가 헛돌지 않는다.
        """
        text = (DOCS / rel).read_text(encoding="utf-8")

        checked = 0
        for brand in INGREDIENTS:
            if brand not in text:
                continue  # 이 문서가 다루지 않는 약이다
            checked += 1
            assert expected_name(brand) in text, f"{rel} 이 {brand} 를 옛 표기로 쓴다"

        assert checked, f"{rel} 에서 아는 약을 하나도 못 찾았다 — 검사가 헛돈다"

    def test_no_document_slips_through_unclassified(self) -> None:
        """**목록이 조용히 낡지 않게 한다.**

        약 이름이 나오는 문서가 새로 생기면, 형식을 따라야 하는 쪽인지
        (`TRANSCRIBING_DOCS`) 아닌지(`EXEMPT_DOCS`) 사람이 정해야 한다.
        정하지 않은 문서가 있으면 여기서 운다 — 처음에 결정 문서 하나만
        보다가 `docs/qa/` 를 통째로 놓친 자리다.
        """
        classified = set(TRANSCRIBING_DOCS) | EXEMPT_DOCS
        mentioning = {
            path.relative_to(DOCS).as_posix()
            for path in DOCS.rglob("*.md")
            if any(brand in path.read_text(encoding="utf-8") for brand in INGREDIENTS)
        }

        assert mentioning, "약 이름이 나오는 문서를 하나도 못 찾았다 — 검사가 헛돈다"

        unclassified = sorted(mentioning - classified)
        assert not unclassified, (
            f"약 이름이 나오는데 어느 쪽인지 안 정해진 문서: {unclassified} — "
            "CSV 를 옮겨 적었으면 TRANSCRIBING_DOCS, 아니면 까닭과 함께 EXEMPT_DOCS 로"
        )

    #: 약을 **처방 항목으로 지목하는** 자리. 여기만 이 규칙의 대상이다.
    #:
    #: 세트 요약(`자궁내막증 · 비잔 (계속)`)과 산문(`비잔 복용 중에는…`),
    #: 절 제목(`비잔정 드시는 동안`)은 짧은 이름을 쓴다. **그대로 두는 것이
    #: 맞다** — 「산문 제목은 브랜드만 쓴다」로 이희진 님이 `#142` 에서 승인했다.
    #: 성분명은 처방 항목에서 한 번 보이면 되고, 읽는 문장까지 괄호를 넣으면
    #: 환자가 읽기 어려워진다.
    NAMING_SITES = ('name: "', "처방받은 약 — ")

    @pytest.mark.parametrize(
        "path",
        ["app/tests/models/test_prescription_models.py", "app/tests/fixtures/test_prescription_rows.py"],
    )
    def test_the_hardcoded_names_in_tests_follow_the_rule_too(self, path: str) -> None:
        """검사 안의 약품명도 **추적되지 않는 사본**이 되면 안 된다.

        이 PR 이 열한 곳을 손으로 고쳤는데, 그 자리들이 새 검사에 안 걸려 있었다
        — 네 번째 사본이 된 셈이다 (이희진 님 `#142` 리뷰).
        """
        text = (Path(__file__).resolve().parents[3] / path).read_text(encoding="utf-8")

        for brand in INGREDIENTS:
            for value in code_strings(text):
                if not value.startswith(brand):
                    continue
                assert expected_name(brand) in value, f"{path} 에 옛 표기가 남았다: {value}"

    @pytest.mark.parametrize("name", ["guide-api.js", "doctor-api.js", "checkin-api.js"])
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
