"""KEY-228 로컬 부트스트랩의 실행 계약.

실제 Docker를 띄우는 clean-clone 검증은 KEY-230의 몫이다. 여기서는 가짜 Docker
경계로 순서·멱등성·실패 중단·비밀값 비노출을 실제 셸 실행으로 고정한다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.tests.deploy.conftest import ROOT, compose, service

SCRIPT = ROOT / "scripts/bootstrap-local.sh"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _sandbox(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    (root / "envs").mkdir()
    shutil.copy2(SCRIPT, root / "scripts/bootstrap-local.sh")
    shutil.copy2(ROOT / "envs/example.local.env", root / "envs/example.local.env")
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    _write_executable(
        bin_dir / "docker",
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$DOCKER_LOG"
if [[ "${1:-}" == info ]]; then
  [[ "${DOCKER_DOWN:-0}" == 1 ]] && exit 1
  exit 0
fi
if [[ "${1:-}" == inspect ]]; then
  printf '%s\\n' "${DOCKER_HEALTH:-healthy}"
  exit 0
fi
if [[ "${1:-}" == compose ]]; then
  case "$*" in
    *"config --quiet"*) [[ "${COMPOSE_CONFIG_FAIL:-0}" == 1 ]] && exit 42; exit 0 ;;
    *"ps --status running -q"*) [[ "${OWNED_SERVICES:-1}" == 1 ]] && printf 'owned\\n'; exit 0 ;;
    *"ps -q"*) printf 'container-id\\n'; exit 0 ;;
    *"aerich upgrade"*)
      if [[ "${MIGRATION_FAIL:-0}" == 1 ]]; then
        [[ "${MIGRATION_ACCESS_DENIED:-0}" == 1 ]] && printf '%s\\n' 'Access denied for user test' >&2
        exit 41
      fi
      ;;
  esac
  exit 0
fi
exit 0
""",
    )
    _write_executable(bin_dir / "curl", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        bin_dir / "openssl",
        "#!/usr/bin/env bash\nprintf '%064d\\n' 0 | tr '0' 'a'\n",
    )
    _write_executable(
        bin_dir / "python3",
        '#!/usr/bin/env bash\n[[ "${PORT_BUSY:-0}" == 1 ]] && exit 1\nexit 0\n',
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "DOCKER_LOG": str(log),
            "BOOTSTRAP_TIMEOUT_SECONDS": "1",
        }
    )
    return root, log, env


def _run(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(root / "scripts/bootstrap-local.sh"), *args],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_script_is_executable_and_compose_supports_the_whole_flow() -> None:
    assert os.access(SCRIPT, os.X_OK), "bootstrap-local.sh를 바로 실행할 수 없다"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".bootstrap.local.env"],
        cwd=ROOT,
        check=False,
    )
    assert ignored.returncode == 0, "합성 계정 비밀번호 파일이 Git에 들어갈 수 있다"

    fastapi_mounts = {str(item) for item in service("docker-compose.yml", "fastapi").get("volumes") or []}
    assert "./scripts:/app/scripts:ro" in fastapi_mounts
    assert "./docs/data:/app/docs/data:ro" in fastapi_mounts

    init = service("docker-compose.yml", "minio-init")
    assert init.get("profiles") == ["ocr"]
    assert init.get("restart") == "no"
    assert "@sha256:" in str(init.get("image"))
    assert "minio_init.sh" in " ".join(map(str, init.get("entrypoint") or []))


def test_default_run_is_idempotent_preserves_env_and_hides_secrets(tmp_path: Path) -> None:
    root, log, env = _sandbox(tmp_path)

    first = _run(root, env)
    assert first.returncode == 0, first.stderr
    env_bytes = (root / ".env").read_bytes()
    bootstrap_bytes = (root / ".bootstrap.local.env").read_bytes()
    secret = "a" * 64

    second = _run(root, env)
    assert second.returncode == 0, second.stderr
    assert (root / ".env").read_bytes() == env_bytes
    assert (root / ".bootstrap.local.env").read_bytes() == bootstrap_bytes

    calls = log.read_text(encoding="utf-8")
    output = first.stdout + first.stderr + second.stdout + second.stderr + calls
    assert secret not in output
    assert "--profile ocr" not in calls
    assert "up -d redis mysql fastapi" in calls
    assert "up -d --build" not in calls
    assert calls.index("aerich upgrade") < calls.index("scripts/seed.py")
    assert calls.index("scripts/seed.py") < calls.index("check_schema_drift.py")
    assert calls.index("check_schema_drift.py") < calls.index("scripts/smoke.py")


def test_ocr_option_starts_only_the_existing_ocr_profile(tmp_path: Path) -> None:
    root, log, env = _sandbox(tmp_path)

    done = _run(root, env, "--with-ocr-worker")
    assert done.returncode == 0, done.stderr
    calls = log.read_text(encoding="utf-8")
    assert "--profile ocr up -d redis mysql fastapi ai-worker minio" in calls
    assert "--profile ai" not in calls and "--profile tools" not in calls
    assert "run --rm -T --no-deps minio-init" in calls


def test_migration_failure_stops_before_seed_drift_and_smoke(tmp_path: Path) -> None:
    root, log, env = _sandbox(tmp_path)
    env["MIGRATION_FAIL"] = "1"

    done = _run(root, env)
    assert done.returncode == 41
    assert "migration" in done.stderr
    calls = log.read_text(encoding="utf-8")
    assert "scripts/seed.py" not in calls
    assert "check_schema_drift.py" not in calls
    assert "scripts/smoke.py" not in calls


def test_stale_mysql_volume_failure_explains_manual_destructive_recovery(tmp_path: Path) -> None:
    root, _, env = _sandbox(tmp_path)
    env.update({"MIGRATION_FAIL": "1", "MIGRATION_ACCESS_DENIED": "1"})

    done = _run(root, env)

    assert done.returncode == 41
    assert "기존 mysql_data 볼륨" in done.stderr
    assert "직접 `docker compose down -v`" in done.stderr
    assert "로컬 볼륨을 삭제" in done.stderr and "백업" in done.stderr


def test_rebuild_is_explicit_and_can_be_combined_with_ocr(tmp_path: Path) -> None:
    root, log, env = _sandbox(tmp_path)

    done = _run(root, env, "--with-ocr-worker", "--rebuild")

    assert done.returncode == 0, done.stderr
    calls = log.read_text(encoding="utf-8")
    assert "--profile ocr up -d --build redis mysql fastapi ai-worker minio" in calls


def test_compose_validation_failure_names_the_right_stage(tmp_path: Path) -> None:
    root, _, env = _sandbox(tmp_path)
    env["COMPOSE_CONFIG_FAIL"] = "1"

    done = _run(root, env)

    assert done.returncode == 42
    assert "compose 설정 검증 단계" in done.stderr


def test_port_probe_covers_ipv4_ipv6_and_reusable_closed_ports() -> None:
    body = SCRIPT.read_text(encoding="utf-8")

    assert 'socket.AF_INET, "0.0.0.0"' in body
    assert 'socket.AF_INET6, "::"' in body
    assert "socket.SO_REUSEADDR" in body


def test_minio_init_really_runs_under_posix_sh(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "mc.log"
    _write_executable(
        bin_dir / "mc",
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$MC_LOG"\n',
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "MC_LOG": str(log),
            "MC_HOST_bootstrap": "http://local-only-placeholder@minio:9000",
            "MINIO_BUCKET": "ocr-fixtures",
        }
    )

    done = subprocess.run(
        ["/bin/sh", str(ROOT / "scripts/minio_init.sh"), "bootstrap"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    calls = log.read_text(encoding="utf-8")
    assert "mb --ignore-existing bootstrap/ocr-fixtures" in calls
    assert "anonymous set none bootstrap/ocr-fixtures" in calls


def test_preflight_explains_docker_and_port_failures(tmp_path: Path) -> None:
    root, _, env = _sandbox(tmp_path)
    env["DOCKER_DOWN"] = "1"
    docker_down = _run(root, env)
    assert docker_down.returncode != 0
    assert "Docker Desktop" in docker_down.stderr

    env.pop("DOCKER_DOWN")
    env["OWNED_SERVICES"] = "0"
    env["PORT_BUSY"] = "1"
    busy = _run(root, env)
    assert busy.returncode != 0
    assert "포트 3306" in busy.stderr and "종료하거나" in busy.stderr


def test_health_timeout_names_the_stage_and_solution(tmp_path: Path) -> None:
    root, _, env = _sandbox(tmp_path)
    env["DOCKER_HEALTH"] = "starting"
    env["BOOTSTRAP_TIMEOUT_SECONDS"] = "1"

    done = _run(root, env)
    assert done.returncode != 0
    assert "의존 서비스 health" in done.stderr
    assert "docker compose logs mysql" in done.stderr


def test_default_services_remain_exactly_the_lightweight_three() -> None:
    services = compose("docker-compose.yml")["services"]
    default = {name for name, body in services.items() if not body.get("profiles")}
    assert default == {"redis", "mysql", "fastapi"}
