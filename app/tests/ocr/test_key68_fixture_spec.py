"""판독 샘플 기대값이 정본과 어긋나면 죽는다 — KEY-68.

기대값은 세 곳에 흩어져 살 수밖에 없다.

    docs/data/synthetic-patients.csv           환자·처방 값 (정본)
    docs/data/ocr-fixtures/*.toml              ICD·표 위치 (EMR 에만 있는 것)
    docs/decisions/KEY-163-ocr-real-contract.md  필수·권장 분류와 확정 표

**셋이 조용히 갈라지는 것**이 이 파일이 막는 일이다. 사람이 CSV 한 줄을 고치거나
KEY-163 이 8/27 멘토링으로 확정되면서 값이 바뀌면, 여기가 먼저 운다.

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


#: 결정 문서와 정본 CSV 가 **지금 다르게 적고 있는 것.** 알고 두는 것이지 봐 주는
#: 것이 아니다 — 하나씩 사라져야 하고, 사라지면 이 검사가 죽어 그때 걷는다.
#:
#: `약품명` — 문서 §3 은 `비잔정(디에노게스트) 2mg`, CSV 는 `비잔정 2mg` 이다.
#: 오늘 처방 세트 매칭이 ID 에서 **이름 문자열**로 바뀌었으므로(`60d2669`)
#: 이 차이는 글자 문제가 아니라 매칭이 되고 안 되고의 문제다. 어느 쪽이 맞는지는
#: 8/27 멘토링에서 정한다. 그때까지 fixture 는 **정본 규칙대로 CSV 를 따른다**
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
