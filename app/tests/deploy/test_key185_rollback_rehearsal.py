"""KEY-185 롤백 리허설 문서가 안전 경계와 증적 자리를 유지하는지 검사한다."""

from app.tests.deploy.conftest import read

EVIDENCE = "docs/qa/KEY-185-pilot-rollback-rehearsal.md"


def test_rehearsal_records_completed_rollback_and_restore() -> None:
    prose = read(EVIDENCE)

    assert "PASS — 롤백·검증·현재 버전 재복구 완료" in prose
    assert "롤백 후와 재복구 후 smoke가 모두 통과" in prose
    assert "현재 Pilot은 시작 시 정상 버전으로 복구" in prose


def test_all_three_image_versions_are_recorded_for_rollback_and_restore() -> None:
    prose = read(EVIDENCE)

    for variable in ("APP_VERSION", "AI_WORKER_VERSION", "WEB_VERSION"):
        assert variable in prose
    for stage in ("시작 시 정상 태그", "롤백 대상 태그", "재복구 태그"):
        assert stage in prose
    for version in ("`v1.0.1`", "`v1.0.2`", "`v1.0.3`", "`v1.0.4`"):
        assert version in prose


def test_rehearsal_has_smoke_gates_before_after_and_after_restore() -> None:
    prose = read(EVIDENCE)

    assert "기준 smoke" in prose
    assert "롤백 후 smoke" in prose
    assert "최종 smoke" in prose
    assert "uv run python scripts/smoke.py" in prose
    assert "health·auth·core smoke" in prose
    assert "HTTP 502" in prose
    assert "application startup 완료" in prose


def test_destructive_database_recovery_is_outside_this_rehearsal() -> None:
    prose = read(EVIDENCE)

    assert "docker compose down -v" in prose
    assert "범위 밖" in prose
    assert "DB migration downgrade" in prose
    assert "별도 승인" in prose


def test_secret_values_are_not_documented() -> None:
    prose = read(EVIDENCE)

    assert "SMOKE_PASSWORD=<저장소 밖에서 전달받은 합성 비밀번호>" in prose
    assert "비밀번호·PAT·SSH 키·환자 링크 토큰" in prose
    assert "응답 본문, 토큰,\n비밀번호는 증적에 복사하지 않았다" in prose
