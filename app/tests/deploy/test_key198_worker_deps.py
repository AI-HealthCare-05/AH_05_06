"""**워커 이미지가 필요한 것만 담는가** — KEY-198.

KEY-197 이 워커의 임포트 크래시를 고치면서 `--group app` 을 통째로 붙였다.
덕분에 워커가 돌긴 하는데, 안 쓰는 것이 함께 들어온다. 그중 하나가 무겁다.

    aerich   `aerich upgrade` · `aerich downgrade` 가 이미지에 함께 들어온다.
             워커는 이미 DB 크리덴셜을 쥐고 있으므로, 스키마를 갈아엎는 명령까지
             같은 이미지에 두면 한 번 뚫렸을 때 번지는 범위가 커진다.

여기서 재는 것은 **선언**이다 — 어느 그룹을 깔라고 적혀 있는가, 그 그룹에
무엇이 들어 있는가. 실제로 구운 이미지에 그것이 없는지는 PR 본문에 실측으로
남긴다 (여기서 굽기에는 `ai` 그룹의 torch 때문에 너무 오래 걸린다).
"""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = ROOT / "ai_worker" / "Dockerfile"
PYPROJECT = ROOT / "pyproject.toml"

#: 워커 이미지에 있으면 안 되는 것.
UNWANTED = ("aerich", "passlib", "bcrypt")


def _groups() -> dict[str, list[str]]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["dependency-groups"]


def _installed_groups() -> list[str]:
    """Dockerfile 의 `uv sync` 가 **실제로 깔라고 적은** 그룹.

    주석은 안 본다. KEY-197 이 바로 그 함정이었다 — 주석은 「app 그룹만」인데
    명령은 `--group ai` 였고, 어긋난 채로 병합돼서 워커가 임포트에서 죽었다.
    """
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped.startswith("RUN") and "uv sync" in stripped:
            return re.findall(r"--group\s+([A-Za-z0-9_-]+)", stripped)
    raise AssertionError("Dockerfile 에 `uv sync` 실행 줄이 없다")


class TestTheWorkerImageInstallsOnlyWhatItNeeds:
    def test_the_dockerfile_uses_the_worker_group(self) -> None:
        groups = _installed_groups()

        assert "worker" in groups, f"워커 전용 그룹을 안 깐다 — {groups}"
        assert "app" not in groups, f"`app` 그룹을 통째로 깐다 — 워커가 안 쓰는 것이 함께 들어온다. {groups}"

    @pytest.mark.parametrize("package", UNWANTED)
    def test_the_worker_group_leaves_out_what_the_worker_never_uses(self, package: str) -> None:
        worker = _groups().get("worker")
        assert worker is not None, "pyproject.toml 에 `worker` 그룹이 없다"

        names = {re.split(r"[<>=!\[]", entry, maxsplit=1)[0].strip() for entry in worker}
        assert package not in names, f"`worker` 그룹이 {package} 를 담고 있다 — 워커 임포트 체인에 없는 것이다" + (
            " (그리고 스키마를 갈아엎는 CLI 가 워커 이미지에 들어간다)" if package == "aerich" else ""
        )

    def test_it_still_keeps_what_the_worker_does_need(self) -> None:
        """**반대쪽도 잰다.** 이것이 없으면 위 검사는 「그룹을 비워라」로도 통과한다."""
        worker = _groups()["worker"]
        names = {re.split(r"[<>=!\[]", entry, maxsplit=1)[0].strip() for entry in worker}

        for needed in ("tortoise-orm", "asyncmy", "pyjwt", "httpx", "orjson"):
            assert needed in names, f"`worker` 그룹에 {needed} 가 없다 — 워커가 실제로 쓴다"


class TestTheWorkerDoesNotLoadAerichModels:
    """**`aerich` 를 빼려면 모델 목록에서도 빼야 한다.**

    `TORTOISE_APP_MODELS` 에 `aerich.models` 가 있으면 `Tortoise.init` 이
    런타임에 그 패키지를 임포트한다. 실제로 재 봤다 — 없으면 이렇게 죽는다.

        ConfigurationError: Module "aerich.models" not found

    그래서 워커용 사본을 따로 둔다. **`TORTOISE_ORM` 자체는 못 건드린다** —
    `pyproject.toml` 의 `[tool.aerich] tortoise_orm` 이 그것을 그대로 읽는다.
    """

    def test_the_worker_config_drops_aerich_models(self) -> None:
        from app.core.db.databases import WORKER_TORTOISE_ORM

        apps = WORKER_TORTOISE_ORM["apps"]
        assert isinstance(apps, dict)
        models = apps["models"]["models"]
        assert "aerich.models" not in models, (
            "워커 설정이 aerich.models 를 싣는다 — 그러면 이미지에서 aerich 를 뺄 수 없다"
        )

    def test_the_app_config_keeps_aerich_models(self) -> None:
        """앱 쪽은 그대로여야 한다 — 마이그레이션이 자기 이력 표를 잃는다."""
        from app.core.db.databases import TORTOISE_ORM

        apps = TORTOISE_ORM["apps"]
        assert isinstance(apps, dict)
        assert "aerich.models" in apps["models"]["models"], (
            "`TORTOISE_ORM` 에서 aerich.models 가 사라졌다 — `[tool.aerich]` 가 이것을 읽는다"
        )

    def test_aerich_still_points_at_the_untouched_config(self) -> None:
        aerich = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["aerich"]
        assert aerich["tortoise_orm"] == "app.core.db.databases.TORTOISE_ORM", (
            f"aerich 가 보는 설정이 바뀌었다 — {aerich['tortoise_orm']}"
        )

    def test_the_worker_actually_uses_the_worker_config(self) -> None:
        """선언만 있고 안 쓰면 아무 소용이 없다."""
        source = (ROOT / "ai_worker" / "main.py").read_text(encoding="utf-8")
        live = "\n".join(line.split("#", 1)[0] for line in source.splitlines())

        assert "WORKER_TORTOISE_ORM" in live, "워커가 워커용 설정을 안 쓴다"
        assert "Tortoise.init(config=WORKER_TORTOISE_ORM)" in live, "워커가 여전히 다른 설정으로 init 한다"


class TestTheReadmeMatchesTheCode:
    """**문서대로 따라 했더니 죽는 일**이 없게 한다.

    `README` 가 `uv sync --group ai   # AI 워커용` 이라고 적어 두었는데, 그 그룹에는
    `tortoise-orm` 이 없다. 그대로 따라 하면 도커 경로에서 KEY-197 이 고친 것과
    **똑같은** `ModuleNotFoundError: No module named 'tortoise'` 로 죽는다.
    """

    README = ROOT / "README.md"

    def test_the_readme_tells_you_the_group_that_works(self) -> None:
        prose = self.README.read_text(encoding="utf-8")
        worker_lines = [ln for ln in prose.splitlines() if "AI 워커용" in ln]

        assert worker_lines, "README 에 워커 설치 안내가 없다"
        for line in worker_lines:
            assert "--group worker" in line, f"워커 설치 안내가 `worker` 그룹을 안 알려 준다 — 「{line.strip()}」"

    def test_the_readme_points_at_the_drift_check(self) -> None:
        prose = self.README.read_text(encoding="utf-8")
        assert "scripts/check_schema_drift.py" in prose, (
            "README 가 스키마 정합 확인을 안 알려 준다 — 밀린 채로 검증을 돌리게 된다"
        )
        assert (ROOT / "scripts" / "check_schema_drift.py").exists(), "README 가 없는 스크립트를 가리킨다"


class TestTheDeadSwitchIsGone:
    """아무 코드도 안 읽는 항목이 예시 env 에 남아 있었다 (KEY-36 잔재).

    **이 파일에는 그 이름을 글자 그대로 적지 않는다.** 처음에 적었더니 검사가
    자기 자신을 잡아 빨간불이 났다 — 저장소를 훑는 검사가 스스로를 훑는 자리다.
    자기 파일만 예외로 빼는 방법도 있지만, 그러면 「검사 파일에 적으면 안 걸린다」
    는 구멍이 생긴다. 이름을 쪼개 두면 그 구멍이 없다.
    """

    #: 글자 그대로 적지 않으려고 쪼갠 것이다 (위 docstring 참고).
    DEAD_NAME = "KEY36" + "_TEST_" + "PASSWORD"

    def test_nothing_mentions_it_any_more(self) -> None:
        hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git/" in str(path) or ".venv" in str(path):
                continue
            if path.suffix not in {".py", ".md", ".env", ".yml", ".yaml", ".toml", ".sh"}:
                continue
            try:
                if self.DEAD_NAME in path.read_text(encoding="utf-8"):
                    hits.append(str(path.relative_to(ROOT)))
            except (UnicodeDecodeError, OSError):
                continue

        assert not hits, f"죽은 {self.DEAD_NAME} 가 아직 남아 있다 — {hits}"
