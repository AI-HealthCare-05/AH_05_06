"""마이그레이션을 만드는 파이썬 판을 못 박는다 — KEY-333.

3.14 는 JSONField 의 `python_type` 을 `dict | list` 로, 3.13 은
`Union[dict, list]` 로 적는다. 판이 갈린 채로 `aerich migrate` 를 돌리면
**아무도 모델을 안 고쳤는데** JSON 칸마다 아무것도 안 바꾸는 `MODIFY COLUMN`
이 붙는다 — MySQL 8 에서 JSON 칸 `MODIFY` 는 표를 다시 쓰고, `upgrade` 와
`downgrade` 가 같은 문장이라 되돌리지도 못한다.

`test_the_last_state_matches_the_models_field_by_field` 가 그것을 **사후에**
잡는다. 여기서는 **애초에 다른 판으로 못 돌게** 막는다.

🚩 **두 자리 다 건다** (이희진 님 `#298`·`#305` 리뷰). 하나만 걸면 다른 경로가
뚫려 있다.

    .python-version 만    `uv` 를 안 거치는 `python3 -m aerich` 는 안 막힌다
    requires-python 만    이미 3.14 를 가진 사람의 직접 실행은 안 막힌다
"""

import tomllib
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[3]

#: 스냅샷을 만드는 판. CI(`.github/workflows/checks.yml`)도 이 판으로 돈다.
PINNED = "3.13"

#: 들어오면 안 되는 판 — `python_type` 표기가 갈리는 첫 자리다.
BROKEN = "3.14"


def _requires_python() -> SpecifierSet:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    raw = data["project"]["requires-python"]
    return SpecifierSet(raw)


def test_the_upper_bound_actually_rejects_the_breaking_version() -> None:
    """**글자를 보지 않고 판정해 본다.**

    `"<3.14" in text` 로 재면 `>=3.13,<3.14.0a1` 처럼 뜻은 같고 글자가 다른
    표기에서 헛되이 운다. 반대로 상한을 지웠는데 주석에 그 글자가 남아 있으면
    통과해 버린다. 그래서 **실제로 판을 넣어 본다.**
    """
    spec = _requires_python()

    assert Version(PINNED) in spec, f"고정하려는 {PINNED} 이 `requires-python` 을 못 지난다: {spec}"
    assert Version(f"{PINNED}.5") in spec, f"{PINNED} 의 패치 판이 막힌다: {spec}"
    assert Version(BROKEN) not in spec, (
        f"`requires-python` 이 {BROKEN} 을 받아들인다 ({spec}) — "
        "그 판에서 만든 스냅샷은 JSON 칸마다 헛된 MODIFY COLUMN 을 부른다 (KEY-333)"
    )


def test_the_local_pin_exists_and_agrees_with_the_contract() -> None:
    """`.python-version` 은 `uv run` 이 알아서 그 판을 받아 쓰게 한다.

    둘이 어긋나면 **로컬과 계약이 다른 말을 한다** — 그 상태로는 어느 쪽을
    믿어야 할지 다음 사람이 알 수 없다.

    실제로는 **`uv` 가 먼저 막는다**(실측). `.python-version` 을 3.14 로 두고
    `uv run` 을 하면 명령 자체가 거부된다.

        error: The Python request from `.python-version` resolved to Python
        3.14.7, which is incompatible with the project's Python requirement:
        `==3.13.*` (from `project.requires-python`)

    그러니 이 검사는 **`uv` 를 안 거치는 경로**를 위한 그물이다 — 그것이 두
    자리 다 거는 까닭이기도 하다.
    """
    pin = ROOT / ".python-version"

    assert pin.exists(), "`.python-version` 이 없다 — `uv run` 이 아무 판이나 쓴다"
    value = pin.read_text(encoding="utf-8").strip()
    assert value, "`.python-version` 이 비어 있다"
    assert Version(value) in _requires_python(), (
        f"`.python-version` 의 {value} 가 `requires-python` 을 못 지난다 — 둘이 어긋났다"
    )


def test_the_ci_runs_the_pinned_version_too() -> None:
    """CI 가 다른 판으로 돌면, 여기서 초록인 것이 거기서 빨개진다.

    실제로 그렇게 물렸다 — 내 자리는 3.14, CI 는 3.13 이었고 `#298` 이 그 차이로
    빨개졌다.
    """
    workflow = (ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8")
    declared = {
        line.split(":", 1)[1].strip().strip("'\"") for line in workflow.splitlines() if "python-version:" in line
    }

    assert declared, "CI 에 `python-version` 선언이 없다 — 검사가 헛돈다"
    for version in declared:
        assert Version(version) in _requires_python(), (
            f"CI 가 {version} 으로 도는데 `requires-python` 이 그것을 안 받는다"
        )
