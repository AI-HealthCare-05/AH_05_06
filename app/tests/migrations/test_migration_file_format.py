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
