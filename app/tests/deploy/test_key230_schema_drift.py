"""양방향 표·컬럼 drift와 실패 종료 계약. 실제 DB는 QA 기록에서 별도 검증한다."""

from unittest.mock import AsyncMock

import pytest

from app.tests.deploy.conftest import compose
from scripts import check_schema_drift as checker


@pytest.mark.parametrize(
    ("expected", "live", "gaps"),
    [
        ({"staff": {"id"}}, {"staff": {"id"}}, ([], [], [], [])),
        ({"staff": {"id"}}, {}, (["staff"], [], [], [])),
        ({}, {"legacy": {"id"}}, ([], [], ["legacy"], [])),
        ({"staff": {"id", "name"}}, {"staff": {"id"}}, ([], [("staff", ["name"])], [], [])),
        ({"staff": {"id"}}, {"staff": {"id", "legacy"}}, ([], [], [], [("staff", ["legacy"])])),
    ],
)
async def test_comparison_and_exit(expected, live, gaps, monkeypatch, capsys):
    assert checker.compare_schemas(expected, live) == gaps
    monkeypatch.setattr(checker, "_gaps", AsyncMock(return_value=gaps))
    assert await checker.main() == int(any(gaps))
    output = capsys.readouterr()
    assert bool(output.err) == any(gaps)


async def test_connection_closed_on_query_failure(monkeypatch):
    monkeypatch.setattr(checker.Tortoise, "init", AsyncMock(side_effect=RuntimeError("unavailable")))
    close = AsyncMock()
    monkeypatch.setattr(checker.Tortoise, "close_connections", close)
    with pytest.raises(RuntimeError, match="unavailable"):
        await checker._gaps()
    close.assert_awaited_once()


def test_real_bootstrap_ci_job():
    workflow = compose(".github/workflows/checks.yml")
    job = workflow["jobs"]["bootstrap"]
    assert not job.get("continue-on-error", False)
    steps = job["steps"]
    assert all(not step.get("continue-on-error", False) for step in steps)
    build = next(step["run"] for step in steps if step["name"] == "Build local API image")
    assert "docker build -f app/Dockerfile" in build
    run = next(step["run"] for step in steps if step["name"] == "Bootstrap fresh database and repeat")
    assert "set -euo pipefail" in run
    assert run.count("./scripts/bootstrap-local.sh") == 2
    assert "sha256sum .env .bootstrap.local.env" in run
