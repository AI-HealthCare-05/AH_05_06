"""판독 샘플 기대값이 정본과 어긋나면 죽는다 — KEY-68.

기대값은 세 곳에 흩어져 살 수밖에 없다.

    docs/data/synthetic-patients.csv           환자·처방 값 (정본)
    docs/data/ocr-fixtures/*.toml              ICD·표 위치 (EMR 에만 있는 것)
    docs/decisions/KEY-163-ocr-real-contract.md  필수·권장 분류와 확정 표

**셋이 조용히 갈라지는 것**이 이 파일이 막는 일이다. 사람이 CSV 한 줄을 고치거나
KEY-163 이 8/28 멘토링으로 확정되면서 값이 바뀌면, 여기가 먼저 운다.

산출물(SVG·JSON)은 커밋하지 않으므로 검사하지 않는다. 검사하는 것은 **만드는
법**이다 — 그것만 저장소에 있다.
"""

import csv
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC_DIR = ROOT / "docs" / "data" / "ocr-fixtures"
PATIENTS_CSV = ROOT / "docs" / "data" / "synthetic-patients.csv"
DECISION = ROOT / "docs" / "decisions" / "KEY-163-ocr-real-contract.md"

#: KEY-163 §2 가 필수로 분류한 셋. 하나라도 빠지면 fallback 이다.
REQUIRED_FIELDS = {"DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"}

SPECS = sorted(SPEC_DIR.glob("*.toml"))


def load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def csv_rows() -> list[dict[str, str]]:
    with PATIENTS_CSV.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_there_is_at_least_one_spec() -> None:
    """기대값이 하나도 없으면 아래가 전부 빈 목록을 돈다."""
    assert SPECS, f"{SPEC_DIR} 에 기대값 파일이 없다"


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_the_spec_points_at_columns_that_exist(path: Path) -> None:
    """**값을 적지 않고 열을 가리킨다**는 규칙이 실제로 지켜지는가.

    `csv_column` 이 CSV 헤더에 없으면 생성기가 조용히 빈 값을 넣는다.
    """
    spec = load(path)
    header = set(csv_rows()[0])

    missing = sorted(
        rule["csv_column"] for rule in spec["fields"].values() if rule["csv_column"] not in header
    ) + sorted(col for col in spec["patient"]["columns"].values() if col not in header)

    assert not missing, f"{path.name} 이 없는 열을 가리킨다: {missing}\n  CSV 헤더: {sorted(header)}"


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_the_scenario_row_exists(path: Path) -> None:
    spec = load(path)
    wanted = spec["patient"]["csv_scenario"]
    ids = {row["시나리오ID"] for row in csv_rows()}
    assert wanted in ids, f"{PATIENTS_CSV.name} 에 {wanted} 행이 없다"


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_required_fields_match_the_decision(path: Path) -> None:
    """필수 분류가 KEY-163 §2 와 같은가.

    멘토링에서 필수 목록이 바뀌면 이 검사가 죽고, 그때 기대값도 함께 고치게 된다.
    """
    spec = load(path)
    declared = {name for name, rule in spec["fields"].items() if rule.get("required")}
    assert declared == REQUIRED_FIELDS, f"{path.name} 의 필수 분류가 KEY-163 §2 와 다르다: {sorted(declared)}"
    assert set(spec["success_requires"]) == REQUIRED_FIELDS, (
        f"{path.name} 의 success_requires 가 필수 분류와 다르다: {spec['success_requires']}"
    )


@pytest.mark.parametrize("path", SPECS, ids=lambda p: p.stem)
def test_the_patient_comes_only_from_the_synthetic_csv(path: Path) -> None:
    """**실제 환자정보 미포함**을 사람 눈이 아니라 검사로 못 박는다.

    신원 값이 전부 정본 CSV 의 그 행에서 나왔는지 되짚는다. 생성기가 값을
    지어내거나 다른 행에서 끌어오면 여기서 걸린다.
    """
    spec = load(path)
    scenario = spec["patient"]["csv_scenario"]
    row = next(r for r in csv_rows() if r["시나리오ID"] == scenario)

    for key, column in spec["patient"]["columns"].items():
        assert row[column].strip(), f"{scenario} 행의 `{column}` 이 비었다 ({key})"


def test_the_generator_runs_and_writes_nothing_into_the_repo(tmp_path: Path) -> None:
    """생성기가 실제로 돌고, **저장소 안에는 아무것도 안 남긴다.**

    산출물이 커밋되지 않는다는 것이 KEY-68 의 범위 밖 첫 줄이다. 기본 출력 자리는
    `.gitignore` 가 막지만, 그것만으로는 「막고 있다」를 재는 것이 아니다.
    여기서는 저장소 밖으로 내보내 보고, 저장소가 깨끗한지 직접 센다.
    """
    before = {p for p in ROOT.rglob("*.svg")} | {p for p in ROOT.rglob("*.expected.json")}

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_ocr_fixture.py"), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, f"생성기가 실패했다:\n{result.stdout}\n{result.stderr}"

    made = sorted(p.name for p in tmp_path.iterdir())
    assert any(n.endswith(".svg") for n in made), f"SVG 가 안 나왔다: {made}"
    assert any(n.endswith(".expected.json") for n in made), f"기대값 JSON 이 안 나왔다: {made}"

    after = {p for p in ROOT.rglob("*.svg")} | {p for p in ROOT.rglob("*.expected.json")}
    assert after == before, f"저장소 안에 산출물이 생겼다: {sorted(p.name for p in after - before)}"


def test_the_default_output_place_is_ignored_by_git() -> None:
    """**`--out` 을 안 줬을 때** 나가는 자리가 실제로 막혀 있는가.

    위 검사는 `--out` 으로 자리를 지정해 돌린다. 그래서 `DEFAULT_OUT` 이 어디를
    가리키든 안 죽는다 — 돌연변이로 확인했다(`DEFAULT_OUT` 을 `docs/` 로 바꿔도
    전부 초록이었다). 기본값이 곧 사람이 실제로 쓰는 값인데 아무도 안 재고 있었다.

    여기서는 git 에게 직접 묻는다 — 어느 줄이 막는지는 상관없다. 지금은
    `.gitignore` 3행의 `build/` 가 막고 있어서 규칙을 새로 더하지 않았다.
    그 줄이 사라지거나 기본 출력 자리가 추적되는 곳으로 옮겨지면 여기서 운다.
    """
    from scripts.make_ocr_fixture import DEFAULT_OUT

    assert ROOT in DEFAULT_OUT.parents, f"기본 출력 자리가 저장소 밖이다: {DEFAULT_OUT}"

    probe = DEFAULT_OUT / "probe.svg"
    ignored = subprocess.run(["git", "check-ignore", "-q", str(probe)], cwd=ROOT, capture_output=True)
    assert ignored.returncode == 0, (
        f"기본 출력 자리가 `.gitignore` 에 안 걸린다: {probe.relative_to(ROOT)}\n"
        "  산출물이 커밋될 수 있다 — KEY-68 범위 밖 첫 줄이 그것이다."
    )


def test_the_recommended_fields_are_split_out_of_the_combined_column(tmp_path: Path) -> None:
    """`총투원문` 한 열에 든 셋을 제대로 갈라 내는가.

    CSV 는 `1/1/84` 처럼 1회량·일일횟수·처방일수를 한 칸에 담는다. 쪼개기가
    망가지면 `DOSAGE` 가 `1/1/84` 통째가 되는데, 권장 필드라 다른 검사들이 값을
    안 봐서 조용히 지나간다 — 돌연변이로 확인했다.

    권장이라고 안 재면 안 재는 것이다.
    """
    import json

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_ocr_fixture.py"), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    made = json.loads((tmp_path / "SYN-EMS-01.emr.v1.expected.json").read_text(encoding="utf-8"))
    row = next(r for r in csv_rows() if r["시나리오ID"] == "SYN-EMS-01")
    dose, freq, _ = row["총투원문"].split("/")

    assert made["fields"]["DOSAGE"]["value"] == dose, (
        f"1회량이 안 갈렸다: {made['fields']['DOSAGE']['value']!r} (CSV 총투원문 {row['총투원문']!r})"
    )
    assert made["fields"]["FREQUENCY"]["value"] == freq, (
        f"일일횟수가 안 갈렸다: {made['fields']['FREQUENCY']['value']!r}"
    )
    assert made["fields"]["DURATION_DAYS"]["value"] == row["처방일수"]


def test_the_expected_json_carries_what_consumers_loop_over(tmp_path: Path) -> None:
    """`docs/ocr-fixtures.md` §7 이 KEY-56·KEY-69 에게 시킨 것이 실제로 들어 있는가.

    소비자는 `success_requires` 를 돌며 필드를 맞댄다. 그것이 빈 목록이면 **아무것도
    안 재면서 초록**이 된다. 생성기에서 그 자리를 `[]` 로 바꿔도 검사가 하나도 안
    죽는 것을 돌연변이로 확인했다 — 문서가 시킨 것을 문서만 알고 있었다.
    """
    import json

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_ocr_fixture.py"), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    made = json.loads((tmp_path / "SYN-EMS-01.emr.v1.expected.json").read_text(encoding="utf-8"))

    assert set(made["success_requires"]) == REQUIRED_FIELDS, (
        f"기대값 JSON 의 success_requires 가 필수 셋과 다르다: {made['success_requires']}\n"
        "  소비자는 이 목록을 돌며 판독 결과를 맞댄다 — 비면 아무것도 안 잰다."
    )
    for name in made["success_requires"]:
        assert made["fields"][name]["value"], f"{name} 값이 비었다"
        assert made["fields"][name]["required"] is True, f"{name} 이 필수로 안 실렸다"


#: 결정 문서와 정본 CSV 가 **지금 다르게 적고 있는 것.** 알고 두는 것이지 봐 주는
#: 것이 아니다 — 하나씩 사라져야 하고, 사라지면 이 검사가 죽어 그때 걷는다.
#:
#: `약품명` — 문서 §3 은 `비잔정(디에노게스트) 2mg`, CSV 는 `비잔정 2mg` 이다.
#: 처방 세트 매칭이 ID 에서 **이름 문자열**로 바뀌었으므로(`60d2669`) 이 차이는
#: 글자 문제가 아니라 매칭이 되고 안 되고의 문제다.
#:
#: **방향은 정해졌다** — `브랜드명(성분명) 용량` 으로 성분명을 병기한다
#: (이희진 님 `#129` 답). 다만 정본 CSV·검사 열한 곳·프런트 표기를 함께 옮기는
#: 일이라 **별도 티켓**으로 분리됐고, 그것이 들어오면 이 목록에서 빼면 된다.
#: 그때까지 fixture 는 **정본 규칙대로 CSV 를 따른다**
#: (`docs/synthetic-data-spec.md` 1절 「한 곳에서만 고친다」).
KNOWN_DIVERGENCE = {"MEDICATION_NAME"}


def test_the_generated_values_match_the_decision_table(tmp_path: Path) -> None:
    """KEY-163 §3 의 합성값 표와 실제로 같은 값이 나오는가.

    문서가 바뀌거나 CSV 가 바뀌면 여기가 갈린다 — 어느 쪽이 맞는지는 사람이
    정하고, **갈렸다는 것만** 여기서 안다.
    """
    import json

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_ocr_fixture.py"), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    made = json.loads((tmp_path / "SYN-EMS-01.emr.v1.expected.json").read_text(encoding="utf-8"))
    decision = DECISION.read_text(encoding="utf-8")

    checks = {
        "DIAGNOSIS": made["fields"]["DIAGNOSIS"]["icd_code"],
        "MEDICATION_NAME": made["fields"]["MEDICATION_NAME"]["value"],
        "DURATION_DAYS": made["fields"]["DURATION_DAYS"]["value"],
    }
    diverged = {name for name, value in checks.items() if value not in decision}

    assert diverged == KNOWN_DIVERGENCE, (
        "결정 문서와 정본 CSV 가 갈리는 자리가 달라졌다.\n"
        f"  지금 갈린 것: {sorted(diverged)}\n"
        f"  알고 있던 것: {sorted(KNOWN_DIVERGENCE)}\n"
        "  줄었다면 `KNOWN_DIVERGENCE` 에서 빼라. 늘었다면 무엇이 갈렸는지 먼저 본다.\n"
        f"  생성값: { {k: v for k, v in checks.items()} }"
    )


#: 아래 둘은 **지금 안 터지지만 다음 확장에서 바로 부딪히는** 자리다
#: (이희진 님 `#129` 리뷰). 재현해서 고쳤고, 여기서 못 박는다.


def test_a_short_csv_row_reaches_the_guided_error_not_an_attribute_error() -> None:
    """`csv.DictReader` 는 짧은 행의 값을 **키는 둔 채 `None`** 으로 채운다.

    그래서 `patient.get(col, "")` 의 기본값이 안 먹고, 뒤이은 `.strip()` 이
    `AttributeError` 로 터지면서 「비었다」 안내를 **지나쳐 버렸다.**

        SYN-A      처방일수='84'   .get(col,"") → '84'
        SYN-SHORT  처방일수=None   .get(col,"") → None
    """
    import csv as _csv
    import io

    from scripts.make_ocr_fixture import column

    rows = list(_csv.DictReader(io.StringIO("시나리오ID,처방일수\nSYN-SHORT\n")))
    assert rows[0]["처방일수"] is None, "DictReader 가 더 이상 None 을 안 넣는다 — 이 검사의 전제가 사라졌다"

    assert column(rows[0], "처방일수") == "", "짧은 행이 문자열로 안 나온다 — AttributeError 로 새는 자리다"
    assert column(rows[0], "없는열") == ""
    assert column({"진단": "자궁내막증"}, "진단") == "자궁내막증"


def test_a_missing_recommended_field_draws_a_blank_not_a_key_error() -> None:
    """권장 필드(`DOSAGE`·`FREQUENCY`)를 안 정의한 기대값이 와도 죽지 않는다.

    KEY-163 §2 가 권장으로 분류한 것들이라 **없어도 되는 값**이다. 필수 필드는
    `resolve()` 가 앞에서 막으므로 여기까지 안 온다.
    """
    from scripts.make_ocr_fixture import value_of

    assert value_of({}, "DOSAGE") == ""
    assert value_of({"DOSAGE": {"value": "1"}}, "DOSAGE") == "1"


def test_an_unknown_document_type_is_refused_with_a_reason() -> None:
    """**EMR 표 구조만 그릴 줄 안다.**

    처방전·검사결과지는 표가 달라서, 그대로 그리면 EMR 모양의 가짜가 나온다.
    안내 없는 `KeyError` 로 죽는 대신 이유를 대고 멈춘다 — 이 스크립트의 다른
    실패가 전부 그러하듯이.
    """
    import pytest as _pytest

    from scripts.make_ocr_fixture import render_svg

    spec = {"document_type": "PRESCRIPTION", "scenario": "SYN-EMS-01", "version": "v1"}

    with _pytest.raises(SystemExit) as caught:
        render_svg(spec, {}, {})

    assert "렌더러가 없다" in str(caught.value), str(caught.value)
    assert "PRESCRIPTION" in str(caught.value)
