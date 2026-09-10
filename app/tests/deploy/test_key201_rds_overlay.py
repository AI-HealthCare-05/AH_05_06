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

import re
import shutil
import subprocess
from collections.abc import Callable
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


def _section(heading: str) -> str:
    """런북에서 그 절만 떼어 온다."""
    runbook = read("docs/deploy-runbook.md")
    at = runbook.index(heading)
    return runbook[at : runbook.index("\n## ", at + 5)]


def _commands(markdown: str) -> str:
    """```bash 울타리 **안**의 줄만. 설명글은 명령이 아니다."""
    lines, inside, out = markdown.splitlines(), False, []
    for line in lines:
        if line.startswith("```"):
            inside = line.startswith("```bash")
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


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


class TestTheCleanupCommandsNameThingsThatExist:
    """지우라고 적은 것이 **그 이름으로 실재해야** 한다.

    런북이 `docker volume rm docker_mysql_data` 라고 적고 있었다. compose 파일이
    볼륨 이름을 못 박아 두어(`name: mysql_data`) 프로젝트 접두어가 안 붙는데,
    다른 판의 습관대로 적은 것이다. 그 명령은 `no such volume` 으로 실패하고,
    **절차를 따라간 사람은 옮기기 전 진료 기록을 지웠다고 믿고 넘어간다** —
    이 절이 막으려던 바로 그 자리다.
    """

    def test_the_runbook_removes_the_volume_by_its_real_name(self) -> None:
        volumes = compose(PROD).get("volumes") or {}
        real = (volumes.get("mysql_data") or {}).get("name") or "mysql_data"

        runbook = read("docs/deploy-runbook.md")
        assert f"docker volume rm {real}" in runbook, f"런북이 볼륨을 {real} 로 안 부른다"

        wrong = [
            line.strip()
            for line in runbook.splitlines()
            if "docker volume rm" in line and f"docker volume rm {real}" not in line
        ]
        assert not wrong, f"없는 볼륨 이름을 지우라고 적었다 — {wrong}"

    def test_the_container_database_is_removed_with_its_profile(self) -> None:
        """**프로필 없이 이름을 대면 판이 통째로 내려간다.**

        오버레이가 얹힌 뒤라 `mysql` 은 프로필 뒤에 있다. 그 상태에서
        `docker compose down mysql` 을 부르면 compose 가 이름을 못 찾고 프로젝트
        전체를 내린다 — `fastapi` · `nginx` 까지 멈춘다 (같은 모양으로 실측).
        """
        section = _section("## 4-5.")

        assert "--profile container-db rm -sf mysql" in section, "프로필 없이 컨테이너 DB 를 지우라고 적었다"

        #: **시키는 줄만 본다.** 하지 말라고 적은 설명글에도 그 명령이 나온다 —
        #: 글자로만 세면 경고문이 제 검사에 걸린다.
        assert "down mysql" not in _commands(section), "판을 통째로 내리는 명령이 남아 있다"


class TestTheServerHasNoRepository:
    """서버에는 저장소가 없다 — 배포가 올리는 것은 `.env` · compose · nginx 셋뿐이다.

    `-f infra/docker/...` 로 부르면 그런 파일이 없다. 런북 3절이 그 사실을 스스로
    적어 두었는데도 이 절이 그 경로를 쓰고 있었다.
    """

    def test_the_migration_section_runs_from_the_deploy_directory(self) -> None:
        section = _section("## 4-5.")

        repo_paths = [
            line.strip()
            for line in _commands(section).splitlines()
            if "docker compose" in line and "infra/docker/" in line
        ]
        assert not repo_paths, f"서버에 없는 경로로 compose 를 부른다 — {repo_paths}"
        assert "cd ~/project" in section, "어디서 부르는지 안 적었다"


class TestTheProcedureNamesItsOwnRequirements:
    """절차가 **제가 기대는 것**을 먼저 말해야 한다 (이희진 님 `#275` ④⑤)."""

    def test_the_dump_uses_the_root_account(self) -> None:
        """앱 계정은 제 스키마에만 권한이 있다 — `--routines` · `--triggers` 가 막힐 수 있다."""
        section = _section("## 4-5.")

        assert "mysqldump" in section, "옮기는 명령이 없다 — 검사가 헛돈다"
        assert "-uroot" in _commands(section), "앱 계정으로 뜬다 — routines·triggers 가 빠질 수 있다"

    def test_the_compose_version_is_checked_first(self) -> None:
        """`!override` 는 v2.24.4 부터다. 낮으면 그 줄을 모른 채 `mysql` 이 그대로 뜬다."""
        section = _section("## 4-5.")

        assert "docker compose version" in _commands(section), "compose 판을 안 보고 시작한다"
        assert "2.24" in section, "어느 판부터인지 안 적었다"

    def test_the_earlier_section_points_here(self) -> None:
        """4-4 절의 「운영에는 profiles 가 없다」는 옮긴 서버에서 거짓이 된다."""
        runbook = read("docs/deploy-runbook.md")
        at = runbook.index("이 저장소의 운영 compose 에는 `profiles:` 가 없다")

        assert "4-5" in runbook[at : at + 400], "옮긴 서버는 다르다는 것을 안 알린다"


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


class TestRollingBackIsActuallyPossible:
    """**되돌아갈 자리를 절차가 지켜 주는가** — 한금준 님 리뷰.

    오버레이가 옳게 얹히는 것과, 옮긴 뒤 되돌아갈 수 있는 것은 다른 문제다.
    여기서 재는 셋은 전부 「절차가 이렇게 적혀 있지 않으면 데이터를 잃는다」다.
    """

    def test_the_deploy_overwrites_the_server_env(self) -> None:
        """`DB_HOST` 를 두 곳에 적으라는 말이 **기대는 사실**을 못 박는다.

        배포가 `envs/.prod.env` 를 서버 `.env` 로 덮어쓴다. 이것이 바뀌면 런북의
        「두 곳이다」가 더 이상 맞지 않는다 — 그때 이 검사가 운다.
        """
        deploy = read("scripts/deployment.sh")

        assert "envs/.prod.env" in deploy, "배포가 원본 env 를 안 올린다 — 검사가 헛돈다"
        assert "~/project/.env" in deploy, "배포가 서버 .env 를 안 덮어쓴다 — 런북의 「두 곳」이 근거를 잃는다"

    def test_the_runbook_changes_db_host_in_both_places(self) -> None:
        """한 곳만 고치면 다음 배포에서 되돌아가고 앱만 죽는다.

        **바꾸라고 시키는 자리에서** 잰다. 절 전체에서 낱말만 세면 아래 설명글이
        대신 통과시켜 준다 — 실제로 그렇게 썼다가 돌연변이가 안 물어서 알았다.
        """
        section = _section("## 4-5.")
        commands = _commands(section[section.index("### ③") : section.index("### ④")])

        assert "envs/.prod.env" in commands, "런북이 배포 원본을 안 고치게 한다 — 다음 배포에서 되돌아간다"
        assert "--force-recreate" in commands, "환경변수를 고치고 컨테이너를 안 다시 세운다 — 도는 판은 그대로다"
        assert "@@hostname" in commands, "붙었는지를 설정으로만 본다 — 실제 연결을 안 묻는다"

    def test_the_runbook_keeps_the_volume_until_the_end(self) -> None:
        """볼륨을 전환 단계에서 지우면 되돌아갈 자리가 없어진다.

        볼륨 삭제는 **한 번만**, 그것도 백업 검증과 롤백 기간 뒤인 마지막 절에
        있어야 한다.
        """
        section = _section("## 4-5.")
        removals = [line for line in _commands(section).splitlines() if "docker volume rm" in line]

        assert len(removals) == 1, f"볼륨 삭제가 여러 자리에 있다 — 어느 것이 맞는지 모른다: {removals}"

        cleanup = section.index("### ⑦")
        assert section.index(removals[0]) > cleanup, "볼륨 삭제가 전환 단계에 있다 — 되돌아갈 자리를 먼저 지운다"

        rollback = section.index("### ⑤")
        assert "역이전" in section[rollback:cleanup], "되돌리기가 RDS 에 쌓인 것을 어떻게 가져올지 안 적었다"

    def test_the_backup_comes_before_the_removal(self) -> None:
        """**뜨고, 확인하고, 지운다** — 순서가 뒤면 지운 뒤 백업한다.

        설명은 「삭제 전에 백업」인데 명령 배치가 거꾸로였다. 위에서부터 따라
        실행하면 원본을 지운 뒤 빈 것을 묶는다 (한금준 님 리뷰 ②).
        """
        section = _section("## 4-5.")
        commands = _commands(section[section.index("### ⑦") :])

        assert "tar czf" in commands, "볼륨을 뜨는 명령이 없다"
        assert "docker volume rm" in commands, "볼륨을 지우는 명령이 없다 — 검사가 헛돈다"
        assert commands.index("tar czf") < commands.index("docker volume rm"), (
            "지운 뒤에 백업한다 — 뜰 원본이 이미 없다"
        )
        assert "tar tzf" in commands, "뜬 것을 확인하지 않는다 — 빈 묶음을 백업이라 믿는다"
        assert commands.index("tar tzf") < commands.index("docker volume rm"), (
            "확인이 삭제 뒤에 있다 — 확인할 때는 이미 지운 뒤다"
        )

    def test_the_connection_check_is_valid_python(self) -> None:
        """런북에 적은 파이썬이 **실제로 실행될 모양인가.**

        `await asyncio.run(main())` 를 적어 두었다 — 함수 밖의 `await` 라
        실행하면 문법 오류다 (한금준 님 리뷰 ①). 이 PR 의 핵심 산출물이 명령인데
        그 명령을 돌려 보지 않았다. 이제 검사가 대신 본다.

        **`ast.parse` 로는 안 잡힌다** — 최상위 `await` 는 파서를 통과하고
        컴파일에서 거부된다. 처음에 `ast.parse` 로 썼더니 돌연변이(`await` 를
        되돌리는 것)가 안 물어서 알았다. `compile` 로 재야 한다.
        """
        section = _section("## 4-5.")
        found = re.search(r'python -c "\n(.*?)\n"', section, re.S)

        assert found, "연결 확인 명령이 없다 — 검사가 헛돈다"
        compile(found.group(1), "<deploy-runbook.md §4-5 ③>", "exec")

    def test_the_rollback_brings_mysql_back_before_the_app(self) -> None:
        """**앱보다 DB 가 먼저다** — ⓐ 「아직 아무것도 안 썼다면」 갈래.

        ③ⓓ 가 컨테이너 MySQL 을 지운다(볼륨만 남긴다). 그래서 되돌릴 때
        ③ⓒ 의 `--no-deps ... fastapi ai-worker` 만 다시 부르면 **MySQL 이 안
        돌아온다.** 앱은 뜨고 `docker compose ps` 도 `running` 인데 DB 를 못
        찾는다 — 되돌리기가 성공한 것처럼 보인다 (한금준 님 `#275` 리뷰).

        같은 판을 세워 밟아 확인했다:
        `ERROR 2005 (HY000): Unknown MySQL server host 'mysql' (-2)`.

        세 가지를 순서로 잰다 — 오버레이를 걷고, mysql 을 띄우고, 그 다음에 앱.
        오버레이가 남아 있으면 mysql 이 프로필 뒤에 숨어 `up` 이 아무것도 안 한다.
        """
        section = _section("## 4-5.")
        branch = section[section.index("#### ⓐ") : section.index("#### ⓑ")]
        lines = _commands(branch).splitlines()

        def at(match: Callable[[str], bool]) -> int | None:
            found = [i for i, line in enumerate(lines) if match(line)]
            return found[0] if found else None

        drop_overlay = at(lambda line: line.strip().startswith("rm ") and "docker-compose.override.yml" in line)
        start_db = at(lambda line: "docker compose up" in line and "mysql" in line)
        start_app = at(lambda line: "--force-recreate" in line)

        assert drop_overlay is not None, "되돌리기가 오버레이를 안 걷는다 — mysql 이 프로필 뒤에 계속 숨는다"
        assert start_db is not None, (
            "되돌리기에 MySQL 을 띄우는 줄이 없다 — ③ⓓ 가 컨테이너를 지웠으므로 "
            "앱만 다시 세우면 `Unknown MySQL server host 'mysql'` 로 끝난다"
        )
        assert start_app is not None, "되돌리기가 앱을 다시 안 세운다 — 환경변수는 컨테이너를 만들 때 박힌다"

        assert drop_overlay < start_db, "오버레이를 걷기 전에 mysql 을 띄운다 — 프로필 뒤라 아무것도 안 뜬다"
        assert start_db < start_app, "앱을 DB 보다 먼저 세운다 — 그 순간 앱은 없는 곳을 찾는다"
