"""마이그레이션 파일이 aerich 가 읽을 수 있는 형식인가 — KEY-196.

`aerich upgrade` 는 **마지막 파일 하나**만 보고 형식을 판정한다.
그 파일에 `MODELS_STATE` 가 없으면 이렇게 멈춘다.

    RuntimeError: Old format of migration file detected,
                  run `aerich fix-migrations` to upgrade format

KEY-165(`20_…`)가 손으로 쓰인 파일이라 그 값이 비어 있었고, 그래서
**배포 경로에 마이그레이션 단계를 넣을 수가 없었다.** 21 개 중 하나가
전체를 막았다.

그 파일 자신의 주석이 「병합한 뒤 `aerich migrate` 를 실행해 확보해야
한다」고 적어 두었는데 후속이 안 됐다. 사람이 기억할 일이 아니라
검사가 볼 일이다.
"""

from pathlib import Path
from typing import Any

import pytest
from aerich.utils import decompress_dict

MIGRATIONS = Path(__file__).resolve().parents[3] / "app" / "core" / "db" / "migrations" / "models"


def version_files() -> list[Path]:
    """번호가 붙은 마이그레이션 파일. aerich 가 세는 것과 같은 규칙."""
    return sorted(
        (p for p in MIGRATIONS.glob("*.py") if p.name.split("_")[0].isdigit()),
        key=lambda p: int(p.name.split("_")[0]),
    )


def models_state(path: Path) -> str | None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "MODELS_STATE", None)


def test_there_are_migration_files() -> None:
    """**아래 검사가 조용히 통과하지 않게 한다.**"""
    files = version_files()

    assert len(files) > 5, f"마이그레이션을 거의 못 찾았다 — 검사가 헛돈다: {[f.name for f in files]}"


def test_the_last_file_carries_a_models_state() -> None:
    """**여기가 막히면 배포가 스키마를 못 만든다.**

    aerich 는 마지막 파일만 본다. 새 마이그레이션을 손으로 쓰고
    `MODELS_STATE` 를 안 넣으면 그 순간부터 `upgrade` 가 멈춘다.
    """
    last = version_files()[-1]

    state = models_state(last)
    assert state, (
        f"{last.name} 에 MODELS_STATE 가 없다 — `aerich upgrade` 가 "
        "「Old format」으로 멈춘다. `aerich fix-migrations` 를 돌리거나, "
        "손으로 쓴 파일이면 `aerich.utils.get_formatted_compressed_data` 로 채워라"
    )


@pytest.mark.parametrize("path", version_files(), ids=lambda p: p.name.split("_")[0])
def test_every_file_carries_one(path: Path) -> None:
    """마지막만 보면 되지만, 중간이 비면 그 파일이 마지막이 될 때 막힌다."""
    assert models_state(path), f"{path.name} 에 MODELS_STATE 가 없다"


def test_the_last_state_can_be_read_back() -> None:
    """압축이 깨져 있으면 있으나 마나다."""
    last = version_files()[-1]

    decoded = decompress_dict(models_state(last) or "")

    assert isinstance(decoded, dict) and decoded, f"{last.name} 의 MODELS_STATE 를 못 푼다"
    assert all(k.startswith("models.") for k in decoded), f"모델 스냅샷이 아니다: {sorted(decoded)[:3]}"


def test_the_last_state_matches_the_models_we_have() -> None:
    """**스냅샷이 실제 모델과 갈리면 다음 마이그레이션이 엉뚱하게 나온다.**

    aerich 는 이 값을 「직전 상태」로 삼아 다음 diff 를 만든다. 여기가
    낡으면 이미 있는 표를 또 만들려 들거나 있는 칸을 빠뜨린다.
    """
    from tortoise import Tortoise

    from app.core.db.databases import TORTOISE_APP_MODELS

    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    live = set(Tortoise.describe_models(serializable=True))
    snapshot = set(decompress_dict(models_state(version_files()[-1]) or ""))

    missing = sorted(live - snapshot)
    assert not missing, f"모델은 있는데 스냅샷에 없다 — 마지막 마이그레이션 뒤에 모델이 늘었다: {missing}"


#: 스키마와 무관해 **비교에서 걷어내는** 키 — KEY-333 · KEY-347.
#:
#: `managed` 는 스냅샷을 저장한 뒤에 생긴 칸이고, `docstring` 은 aerich 가
#: diff 에 안 쓰는 문서다. 둘 다 있어도 `aerich migrate` 는 DDL 을 안 뱉는다.
_IGNORED_KEYS = frozenset({"managed", "docstring"})


def _same_shape(value: Any) -> Any:
    """스냅샷과 `describe_models()` 를 **뜻으로** 견주기 위한 정규화 — KEY-333.

    둘은 같은 내용을 담고도 그냥 비교하면 **44개 모델이 전부 다르다고 나온다.**
    까닭은 둘뿐이고, 어느 쪽도 스키마와 상관이 없다.

      * `indexes`·`unique_together` 가 한쪽은 **tuple**, 한쪽은 list 다.
        `json` 으로 찍으면 글자가 같은데 `==` 는 거짓이다.
      * 스냅샷에는 `managed` 키가 없다 — 저장한 뒤에 생긴 칸이다.

    이것을 안 걷으면 검사가 늘 빨개져서 아무도 안 본다. 걷고 나면 **진짜
    어긋남만** 남는다(실측: develop 에서 44개 전부 일치).

    🚩 **`docstring` 도 걷는다** — KEY-347. `describe_models()` 는 클래스
    docstring 을 통째로 담는데, **aerich 는 그것을 안 본다.** 실측으로 확인했다 —
    `GuideSafetyCheck` 의 docstring 에 문단을 더한 `#317` 뒤에 이 검사는 울었지만
    `aerich migrate --offline` 은 `No changes detected` 였다.

    걷지 않으면 **모델에 주석 한 줄 다는 일이 마이그레이션 작업이 된다.** 그러면
    아무도 주석을 안 달게 되고, 이 저장소가 맥락을 남기는 방식이 무너진다.

    **`description` 은 안 걷는다.** 그쪽은 표·칸 주석이라 DDL 에 실린다. Tortoise 는
    docstring 의 **첫 줄**을 모델 `description` 으로 쓰므로, 첫 줄을 고치면
    `description` 이 갈려 여전히 걸린다 — 잡아야 할 것은 그쪽이다.
    """
    if isinstance(value, dict):
        return {key: _same_shape(item) for key, item in sorted(value.items()) if key not in _IGNORED_KEYS}
    if isinstance(value, (list, tuple)):
        return [_same_shape(item) for item in value]
    return value


def _drifted_fields(snapshot: Any, live: Any) -> list[str]:
    """어긋난 **칸 이름과 갈린 키**만 뽑는다 — KEY-333.

    `describe` 를 통째로 찍으면 한 모델이 백 줄이라 아무도 안 읽는다. 그러면
    검사가 「다르다」까지만 말하고 **어디가 다른지는 사람이 다시 파야** 한다.
    """
    before = {field["name"]: field for field in (snapshot or {}).get("data_fields", [])}
    after = {field["name"]: field for field in (live or {}).get("data_fields", [])}

    lines: list[str] = []
    for name in sorted(set(before) | set(after)):
        old, new = _same_shape(before.get(name)), _same_shape(after.get(name))
        if old == new:
            continue
        if old is None or new is None:
            lines.append(f"    {name}: {'모델에만' if old is None else '스냅샷에만'} 있다")
            continue
        keys = sorted(key for key in set(old) | set(new) if old.get(key) != new.get(key))
        lines.append(f"    {name}: " + ", ".join(f"{key} {old.get(key)!r} → {new.get(key)!r}" for key in keys))

    return lines or ["    (칸이 아니라 모델 단위 키가 갈렸다 — indexes·unique_together·pk_field 를 봐라)"]


def test_the_last_state_matches_the_models_field_by_field() -> None:
    """**이름만 같아서는 모자란다** — 칸이 갈린 것도 잡는다 (KEY-333).

    위 검사 둘은 **모델 이름 집합**만 본다. 그래서 「표는 그대로인데 칸 하나가
    넓어졌다」 같은 어긋남은 통과한다. 그런데 `aerich migrate` 가 다음 diff 를
    만들 때 쓰는 것은 이 스냅샷의 **내용**이다 — 여기가 낡으면 이미 있는 칸을
    다시 `ADD` 하려 들고, 배포가 `Duplicate column` 으로 멈춘다(`#279` 전례).

    **KEY-230 과 겹치지 않는다.** 저쪽은 「DB ↔ 모델」을 본다. 여기는 「저장소의
    마지막 스냅샷 ↔ 모델」이라 DB 없이 돈다 — 손으로 다듬은 마이그레이션이
    스냅샷을 흘렸는지가 이 자리에서 걸린다.
    """
    from tortoise import Tortoise

    from app.core.db.databases import TORTOISE_APP_MODELS

    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    live = Tortoise.describe_models(serializable=True)
    snapshot = decompress_dict(models_state(version_files()[-1]) or "")

    drifted = sorted(name for name in live if _same_shape(snapshot.get(name)) != _same_shape(live.get(name)))
    detail = "\n".join(
        line for name in drifted for line in (f"  {name}", *_drifted_fields(snapshot.get(name), live.get(name)))
    )
    assert not drifted, (
        f"{version_files()[-1].name} 의 MODELS_STATE 가 지금 모델과 다르다:\n{detail}\n"
        "손으로 다듬은 마이그레이션이 스냅샷을 흘렸을 때 이렇게 된다.\n"
        "**`python_type` 만 갈렸으면 파이썬 판이 다른 것이다** — 3.13 은 `Union[dict, list]`, "
        "3.14 는 `dict | list` 로 적는다. aerich 는 이 한 칸 때문에 JSON 칸마다 "
        "아무것도 안 바꾸는 `MODIFY COLUMN` 을 뱉는다(KEY-333 실측).\n"
        "CI 와 같은 자리에서 다시 만들어라: `uv run --python 3.13 aerich migrate --name <설명> --offline`"
    )


def test_the_snapshot_carries_nothing_we_deleted() -> None:
    """**반대 방향 — 모델을 지웠는데 표를 안 지운 경우** (KEY-206).

    위 검사는 `live - snapshot` 만 본다. 모델이 늘었는데 마이그레이션을 안
    만든 경우다. 그 반대는 안 본다.

    모델 파일에서 클래스를 지우면 `describe_models` 에서는 사라지지만
    스냅샷에는 남는다. 그리고 **DB 에도 표가 그대로 남는다** — `DROP TABLE`
    마이그레이션을 따로 만들어야 하는데, 아무도 안 울어서 그냥 지나간다.
    남은 표는 다음 사람이 「이건 뭐지」 하고 볼 때까지 산다.

    이희진 님이 `#156` 리뷰에서 짚은 자리다: `extra = sorted(snapshot - live)`.
    """
    from tortoise import Tortoise

    from app.core.db.databases import TORTOISE_APP_MODELS

    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    live = set(Tortoise.describe_models(serializable=True))
    snapshot = set(decompress_dict(models_state(version_files()[-1]) or ""))

    extra = sorted(snapshot - live)
    assert not extra, f"스냅샷에는 있는데 코드에 없는 모델 — 지웠으면 `DROP TABLE` 마이그레이션도 만들어라: {extra}"


def test_a_docstring_paragraph_does_not_count_as_drift() -> None:
    """모델에 **주석 한 줄 다는 일**이 마이그레이션 작업이 되면 안 된다 — KEY-347.

    `describe_models()` 는 클래스 docstring 을 통째로 담는다. 그래서 `#317` 이
    `GuideSafetyCheck` docstring 에 문단을 더하자 **develop 이 빨개졌다** —
    스키마는 한 글자도 안 바뀌었는데.

    aerich 는 그 칸을 안 본다(실측: 그 상태에서 `migrate --offline` 이
    `No changes detected`). 막으려던 것은 「낡은 스냅샷이 다음 diff 를 망친다」인데
    이건 그것이 아니다.
    """
    snapshot = {"docstring": "한 줄.\n\n옛 문단.", "description": "한 줄."}
    live = {"docstring": "한 줄.\n\n옛 문단.\n\n새로 더한 문단.", "description": "한 줄."}

    assert _same_shape(snapshot) == _same_shape(live), "docstring 뒷문단이 어긋남으로 잡힌다"


def test_the_first_docstring_line_still_counts() -> None:
    """🚩 **첫 줄은 걷어내지 않는다.**

    Tortoise 는 docstring 첫 줄을 모델 `description` 으로 쓰고, 그것은 표 주석이라
    DDL 에 실린다. `docstring` 을 걷는다고 이쪽까지 놓치면, 걷어낸 것이 너무 많다.
    """
    snapshot = {"docstring": "옛 한 줄.", "description": "옛 한 줄."}
    live = {"docstring": "새 한 줄.", "description": "새 한 줄."}

    assert _same_shape(snapshot) != _same_shape(live), "첫 줄이 갈렸는데 같다고 본다"
