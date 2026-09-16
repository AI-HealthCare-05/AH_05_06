"""실제 bootstrap 셸의 실패 전파 QA. Docker 실행 자체의 증거는 별도 실측 기록."""

from pathlib import Path

import pytest

from app.tests.deploy.test_key228_bootstrap_local import _run, _sandbox


@pytest.mark.parametrize(
    ("failed_call", "next_call"),
    [
        ("up -d redis mysql fastapi", "aerich upgrade"),
        ("aerich upgrade", "scripts/seed.py"),
        ("scripts/seed.py", "check_schema_drift.py"),
        ("check_schema_drift.py", "scripts/smoke.py"),
        ("scripts/smoke.py", None),
    ],
)
def test_each_failed_stage_exits_nonzero_without_success(
    tmp_path: Path, failed_call: str, next_call: str | None
) -> None:
    root, log, env = _sandbox(tmp_path)
    docker = tmp_path / "bin" / "docker"
    body = docker.read_text()
    body = body.replace(
        'if [[ "${1:-}" == info ]]; then',
        f'if [[ "$*" == *"{failed_call}"* ]]; then exit 43; fi\nif [[ "${{1:-}}" == info ]]; then',
    )
    docker.write_text(body)
    done = _run(root, env)
    assert done.returncode == 43, done.stderr
    assert "완료 — health·auth·core" not in done.stdout
    assert failed_call in log.read_text()
    if next_call is not None:
        assert next_call not in log.read_text()
