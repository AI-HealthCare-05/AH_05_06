"""원격 smoke 가 **틀렸을 때 틀렸다고 하는가** — KEY-184.

배포 게이트라 두 가지가 동시에 참이어야 한다.

    정상인데 막으면   아무도 안 쓰게 된다
    고장인데 통과하면 게이트가 없는 것과 같다

그리고 이 실행기는 **배포 로그에 글자를 남긴다.** `health` 는 로컬에서 예외
문자열을 `detail` 에 실어 주므로(`health_routers.py:27`), 응답을 그대로 옮기면
접속 문자열이 CI 로그에 남는다. 그래서 「무엇이 안 새는가」를 따로 잰다.

외부 환경도 운영 자격증명도 쓰지 않는다 — 오가는 것을 전부 껍데기로 세운다.
"""

import httpx
import pytest

from scripts.smoke import (
    Check,
    Reason,
    exit_code,
    failure_of,
    judge_core,
    judge_health,
    judge_login,
    normalize_base,
    report,
    run_smoke,
)

#: 응답 안에 있으면 안 되는 것들이 밖으로 나오는지 보려고 심는 표식.
LEAK_MARKERS = ("SYNTHETIC-DSN-marker", "SYNTHETIC-TOKEN-marker", "SYNTHETIC-PASSWORD-marker")

HEALTHY = {"status": "ok", "services": {"api": {"status": "ok"}, "db": {"status": "ok"}, "redis": {"status": "ok"}}}
DEGRADED = {
    "status": "degraded",
    "services": {
        "api": {"status": "ok"},
        "db": {"status": "error", "reason": "connection_failed", "detail": LEAK_MARKERS[0]},
        "redis": {"status": "ok"},
    },
}


class StubResponse:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        if self._body is None:
            raise ValueError("본문이 JSON 이 아니다")
        return self._body


class StubClient:
    """정해 둔 답만 돌려주는 껍데기. 예외를 심으면 그대로 던진다."""

    def __init__(self, health: object, login: object = None, core: object = None) -> None:
        self._plan = {"health": health, "login": login, "core": core}
        self.seen: list[str] = []

    async def get(self, url: str, **kwargs: object) -> StubResponse:
        key = "health" if "health" in url else "core"
        return self._give(key, url, kwargs)

    async def post(self, url: str, **kwargs: object) -> StubResponse:
        return self._give("login", url, kwargs)

    def _give(self, key: str, url: str, kwargs: dict) -> StubResponse:
        self.seen.append(url)
        planned = self._plan[key]
        if isinstance(planned, Exception):
            raise planned
        assert isinstance(planned, StubResponse), f"{key} 를 부를 계획이 없었다"
        return planned


LOGIN_OK = StubResponse(200, {"access_token": LEAK_MARKERS[1], "must_change_password": False})
CORE_OK = StubResponse(200, {"visits": []})


class TestItPassesOnlyWhenEverythingIsUp:
    async def test_all_three_green_exits_zero(self) -> None:
        client = StubClient(StubResponse(200, HEALTHY), LOGIN_OK, CORE_OK)
        checks = await run_smoke("https://synthetic.example", "synthetic", "synthetic", client)  # type: ignore[arg-type]

        assert [c.name for c in checks] == ["health", "auth", "core"]
        assert all(c.ok for c in checks)
        assert exit_code(checks) == 0

    async def test_it_stops_at_the_first_failure(self) -> None:
        """health 가 죽었는데 로그인을 시도하면 그 실패가 진짜 원인을 덮는다."""
        client = StubClient(StubResponse(503, DEGRADED))
        checks = await run_smoke("https://synthetic.example", "synthetic", "synthetic", client)  # type: ignore[arg-type]

        assert [c.name for c in checks] == ["health"]
        assert exit_code(checks) == 1

    @pytest.mark.parametrize(
        ("plan", "expected"),
        [
            (StubResponse(503, DEGRADED), Reason.DEGRADED),
            (StubResponse(500, None), Reason.SERVER_ERROR),
            (StubResponse(200, {"nope": 1}), Reason.MALFORMED),
            (httpx.ConnectError("연결 실패"), Reason.UNREACHABLE),
            (httpx.ReadTimeout("느림"), Reason.TIMEOUT),
        ],
    )
    async def test_each_way_of_being_broken_has_its_own_name(self, plan: object, expected: Reason) -> None:
        """「잘못된 주소·타임아웃·5xx 가 서로 구분」이 인수조건이다."""
        client = StubClient(plan)
        checks = await run_smoke("https://synthetic.example", "synthetic", "synthetic", client)  # type: ignore[arg-type]

        assert checks[0].reason is expected
        assert exit_code(checks) == 1

    async def test_a_rejected_login_fails_the_gate(self) -> None:
        client = StubClient(StubResponse(200, HEALTHY), StubResponse(401, {"code": "INVALID_CREDENTIALS"}))
        checks = await run_smoke("https://synthetic.example", "synthetic", "synthetic", client)  # type: ignore[arg-type]

        assert checks[-1].reason is Reason.AUTH_REJECTED
        assert exit_code(checks) == 1

    async def test_a_core_api_failure_fails_the_gate(self) -> None:
        client = StubClient(StubResponse(200, HEALTHY), LOGIN_OK, StubResponse(500, None))
        checks = await run_smoke("https://synthetic.example", "synthetic", "synthetic", client)  # type: ignore[arg-type]

        assert [c.name for c in checks] == ["health", "auth", "core"]
        assert checks[-1].reason is Reason.SERVER_ERROR
        assert exit_code(checks) == 1


class TestNothingFromTheResponseLeavesTheProcess:
    """**이 검사가 이 파일의 요점이다.**

    진단이 응답에서 글자를 가져오기 시작하면, 어느 날 `detail` 에 실린 접속
    문자열이나 토큰이 배포 로그에 남는다. 그래서 「무엇을 찍는가」가 아니라
    **「무엇이 못 나가는가」**를 잰다.
    """

    @pytest.mark.parametrize(
        "plan",
        [
            (StubResponse(503, DEGRADED), None, None),
            (StubResponse(200, HEALTHY), LOGIN_OK, CORE_OK),
            (StubResponse(200, HEALTHY), StubResponse(401, {"detail": LEAK_MARKERS[0]}), None),
        ],
    )
    async def test_no_marker_reaches_the_report(self, plan: tuple) -> None:
        client = StubClient(*plan)
        checks = await run_smoke("https://synthetic.example", "synthetic", LEAK_MARKERS[2], client)  # type: ignore[arg-type]
        printed = report(checks)

        for marker in LEAK_MARKERS:
            assert marker not in printed, f"응답·비밀값이 보고문으로 샜다: {marker}"

    def test_every_diagnosis_word_comes_from_the_fixed_vocabulary(self) -> None:
        """진단 문장은 `Reason` 에 적힌 것뿐이다 — 응답에서 만들어 오지 않는다."""
        allowed = {str(reason) for reason in Reason}
        for reason in Reason:
            assert str(Check("x", reason).reason) in allowed

    def test_the_note_never_carries_free_text(self) -> None:
        """`note` 는 서비스 이름·상태 코드만 담는다."""
        degraded = judge_health(503, DEGRADED)
        assert degraded.note == "db"
        assert LEAK_MARKERS[0] not in degraded.note


class TestTheTargetUrlIsCheckedBeforeAnythingIsSent:
    @pytest.mark.parametrize("raw", ["api.example.com", "ftp://api.example.com", "", "  "])
    def test_a_target_that_is_not_http_is_refused(self, raw: str) -> None:
        assert normalize_base(raw) is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("https://a.example/", "https://a.example"), ("http://a.example", "http://a.example")],
    )
    def test_a_trailing_slash_is_dropped(self, raw: str, expected: str) -> None:
        assert normalize_base(raw) == expected


class TestTheJudgementsThemselves:
    def test_health_needs_every_service_ok(self) -> None:
        assert judge_health(200, HEALTHY).ok
        assert not judge_health(200, {"status": "ok", "services": {"db": {"status": "error"}}}).ok

    def test_login_without_a_token_is_not_a_pass(self) -> None:
        assert judge_login(200, {"must_change_password": False}).reason is Reason.NO_TOKEN

    def test_core_two_hundred_is_the_only_pass(self) -> None:
        assert judge_core(200).ok
        assert not judge_core(204).ok

    def test_an_unknown_exception_is_not_swallowed(self) -> None:
        """모르는 예외를 삼키면 「통과」로 보일 수 있다 — 그대로 터뜨린다."""
        with pytest.raises(RuntimeError):
            failure_of("health", RuntimeError("모르는 것"))
