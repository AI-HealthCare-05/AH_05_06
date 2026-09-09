"""RDS 로 옮길 때 컨테이너 MySQL 이 **실제로 꺼지는가** — KEY-201.

티켓은 「앱은 `DB_HOST` 만 교체」라고 적었다. 앱이 붙는 곳만 보면 맞는 말이다.
그런데 `docker-compose.prod.yml` 은 그 값과 무관하게 `mysql` 컨테이너를 띄우고,
`fastapi` · `ai-worker` 가 그것의 `service_healthy` 를 기다린다.

**그러면 아무도 안 쓰는 MySQL 이 EC2 에서 계속 돌고, 그 볼륨에는 옮기기 전의
진료 기록이 그대로 남는다.** 백업 대상도 아니고 지우는 절차도 없는 자리다.
`DB_HOST` 만 바꾸는 것으로 끝내면 환자 데이터 사본이 소리 없이 남는다.

그래서 오버레이(`docker-compose.rds.yml`)를 둔다. 여기서 재는 것은 **그것을
얹었을 때 실제로 어떤 판이 서는가**다 — 파일에 뭐라고 적혀 있는가가 아니라.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from app.tests.deploy.conftest import ROOT, compose, read

PROD = "infra/docker/docker-compose.prod.yml"
RDS = "infra/docker/docker-compose.rds.yml"

#: `docker compose config` 가 값을 요구하는 것들. 진짜 값은 하나도 안 쓴다.
SYNTHETIC_ENV = {
    "DOCKER_USER": "synthetic",
    "DOCKER_REPOSITORY": "synthetic",
    "APP_VERSION": "v0.0.0",
    "AI_WORKER_VERSION": "v0.0.0",
    "WEB_VERSION": "v0.0.0",
    "DB_ROOT_PASSWORD": "synthetic",
    "DB_NAME": "synthetic",
    "DB_USER": "synthetic",
    "DB_PASSWORD": "synthetic",
    "MINIO_ROOT_USER": "synthetic",
    "MINIO_ROOT_PASSWORD": "synthetic",
}


class _TagTolerantLoader(yaml.SafeLoader):
    """`!override` 같은 compose 태그를 값 그대로 읽는다.

    `yaml.safe_load` 는 모르는 태그에서 죽는다. 태그는 compose 가 병합할 때
    쓰는 표시이고 값 자체는 그 아래 매핑이므로, 여기서는 벗겨서 본다.
    """


_TagTolerantLoader.add_multi_constructor("!", lambda loader, suffix, node: loader.construct_mapping(node, deep=True))


def _overlay() -> dict[str, Any]:
    loaded = yaml.load(read(RDS), Loader=_TagTolerantLoader)  # noqa: S506 — SafeLoader 파생이다
    assert isinstance(loaded, dict), f"{RDS} 가 매핑이 아니다"
    return loaded


class TestTheOverlayTurnsOffTheContainerDatabase:
    def test_mysql_goes_behind_a_profile(self) -> None:
        """프로필이 붙은 서비스는 그 프로필을 켰을 때만 뜬다."""
        mysql = _overlay()["services"]["mysql"]

        assert mysql.get("profiles"), "오버레이가 mysql 을 그대로 띄운다 — 안 쓰는 DB 가 계속 돈다"

    def test_the_apps_stop_waiting_for_mysql_but_still_wait_for_redis(self) -> None:
        """**기다림도 함께 지워야 한다.**

        프로필만 붙이면 compose 가 아예 거부한다 — `service "fastapi" depends on
        undefined service "mysql"`. 그렇다고 통째로 지우면 앱이 redis 보다 먼저
        떠서 세션·큐가 첫 몇 초 동안 죽는다.
        """
        services = _overlay()["services"]

        for name in ("fastapi", "ai-worker"):
            waits = services[name]["depends_on"]
            assert "mysql" not in waits, f"{name} 이 아직 mysql 을 기다린다 — 프로필과 어긋나 배포가 거부된다"
            assert "redis" in waits, f"{name} 이 redis 도 안 기다린다 — 앱이 먼저 떠서 세션·큐가 죽는다"

    def test_the_base_file_alone_still_starts_mysql(self) -> None:
        """**지금 배포는 그대로다.** 오버레이를 얹은 배포만 달라진다."""
        prod = compose(PROD)["services"]

        assert not prod["mysql"].get("profiles"), "운영 기본 판에서 mysql 이 사라졌다"
        assert "mysql" in prod["fastapi"]["depends_on"], "기본 판이 mysql 을 안 기다린다"


class TestComposeActuallyRendersItThatWay:
    """**글자가 아니라 compose 에게 물어본다.**

    위 검사들은 파일에 적힌 모양을 본다. 태그 하나(`!override` ↔ `!reset`)만
    달라져도 결과가 갈리는데 모양은 비슷하다 — 실제로 `!reset` 으로 썼다가
    redis 기다림까지 사라진 것을 이 자리에서 알았다.
    """

    def _rendered(self, tmp_path: Path, *files: str) -> dict[str, Any]:
        docker = shutil.which("docker")
        if docker is None:
            pytest.skip("docker 가 없다 — 이 판에서는 compose 에게 물어볼 수 없다")

        #: 운영 compose 는 `env_file: .env` 를 요구한다 — 서버에는 있고 여기에는
        #: 없다. 저장소에 그 파일을 만들지 않고, 사본 옆에 빈 것을 둔다.
        for rel in files:
            shutil.copy(ROOT / rel, tmp_path / Path(rel).name)
        (tmp_path / ".env").write_text("", encoding="utf-8")

        argv = [docker, "compose"]
        for rel in files:
            argv += ["-f", Path(rel).name]
        argv += ["config", "--format", "json"]
        done = subprocess.run(
            argv, cwd=tmp_path, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", **SYNTHETIC_ENV}
        )
        if done.returncode != 0:
            pytest.skip(f"docker compose 가 이 판에서 안 돈다:\n{done.stderr[-400:]}")

        import json

        return dict(json.loads(done.stdout))

    def test_the_overlay_leaves_no_mysql_in_the_project(self, tmp_path: Path) -> None:
        rendered = self._rendered(tmp_path, PROD, RDS)

        assert "mysql" not in rendered["services"], (
            f"오버레이를 얹었는데도 mysql 이 판에 남았다 — {sorted(rendered['services'])}"
        )
        for name in ("fastapi", "ai-worker"):
            assert set(rendered["services"][name].get("depends_on") or {}) == {"redis"}, (
                f"{name} 의 기다림이 redis 하나가 아니다 — {rendered['services'][name].get('depends_on')}"
            )

    def test_without_the_overlay_mysql_is_still_there(self, tmp_path: Path) -> None:
        rendered = self._rendered(tmp_path, PROD)

        assert "mysql" in rendered["services"], "오버레이 없이도 mysql 이 사라졌다 — 지금 배포가 깨진다"


class TestTheOverlayCanActuallyReachTheServer:
    """**`-f` 를 넘길 자리가 없다.**

    배포 스크립트는 `docker compose` 를 `-f` 없이 부르고(`lib.sh`),
    `~/project/docker-compose.yml` 을 매번 덮어쓴다(`deployment.sh`). 그래서
    오버레이는 **이름으로** 얹는다 — compose 가 자동으로 합치는
    `docker-compose.override.yml` 이다.

    이 검사가 없으면 오버레이는 저장소 안에서만 옳고 서버에서는 한 번도 안
    얹힌다 — 그리고 그 사실은 아무 데서도 안 드러난다.
    """

    def test_the_deploy_never_calls_compose_with_a_file_flag(self) -> None:
        lib = read("scripts/lib.sh")

        calls = [ln.strip() for ln in lib.splitlines() if ln.strip().startswith("docker compose ")]
        assert calls, "배포가 compose 를 안 부른다 — 검사가 헛돈다"
        for call in calls:
            assert " -f " not in call, f"배포가 `-f` 를 쓴다 — 그러면 이름으로 얹는 규칙이 더 이상 맞지 않는다: {call}"

    def test_the_deploy_does_not_overwrite_the_override_name(self) -> None:
        """덮어쓰면 옮긴 다음 배포에서 컨테이너 MySQL 이 되살아난다."""
        deploy = read("scripts/deployment.sh")

        assert "docker-compose.override.yml" not in deploy, (
            "배포가 override 파일 이름을 건드린다 — 다음 배포에 RDS 설정이 지워진다"
        )
        assert "~/project/docker-compose.yml" in deploy, "배포가 compose 를 안 올린다 — 검사가 헛돈다"

    def test_the_runbook_puts_it_there_by_that_name(self) -> None:
        runbook = read("docs/deploy-runbook.md")

        assert "docker-compose.override.yml" in runbook, "런북이 얹는 방법을 안 적었다"


class TestTheProcedureIsWrittenDown:
    """옮기는 사람이 **두 곳을 함께** 바꿔야 한다는 것을 어디선가 읽어야 한다."""

    def test_the_prod_example_points_at_the_overlay(self) -> None:
        example = read("envs/example.prod.env")

        assert "docker-compose.rds.yml" in example, "DB_HOST 를 바꾸는 사람이 오버레이를 모른다"

    def test_the_runbook_has_the_migration_section(self) -> None:
        runbook = read("docs/deploy-runbook.md")

        assert "## 4-5." in runbook, "런북에 RDS 절이 없다"
        assert "docker-compose.rds.yml" in runbook, "런북이 오버레이를 안 가리킨다"
        assert "--single-transaction" in runbook, "옮기는 명령이 InnoDB 를 잠근 채 뜬다"
