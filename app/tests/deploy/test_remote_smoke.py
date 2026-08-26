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

from app.tests.deploy.test_pilot_deploy_contract import ROOT
from scripts.smoke import (
    Check,
    Reason,
    exit_code,
    failure_of,
    judge_core,
    judge_health,
    judge_login,
    judge_status,
    normalize_base,
    report,
    run_smoke,
    run_smoke_with_retry,
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


class TestRetryOnlyForNotReachingIt:
    """배포 직후 콜드스타트만 다시 건다 — `#141` 리뷰의 설계 질문에 대한 답.

    **판정된 실패는 다시 걸지 않는다.** `degraded`·`401`·`5xx` 는 다시 물어도
    같은 답이 오고, 여러 번 묻는 동안 진짜 고장이 「간헐적」으로 보인다.
    """

    class FlakyThenUp(StubClient):
        """처음 몇 번은 못 닿고, 그 뒤에는 멀쩡한 서버."""

        def __init__(self, fail_times: int) -> None:
            super().__init__(StubResponse(200, HEALTHY), LOGIN_OK, CORE_OK)
            self.left = fail_times
            self.tries = 0

        def _give(self, key: str, url: str, kwargs: dict) -> StubResponse:
            if key == "health":
                self.tries += 1
                if self.left > 0:
                    self.left -= 1
                    raise httpx.ConnectError("아직 뜨는 중")
            return super()._give(key, url, kwargs)

    async def test_a_cold_start_is_given_another_chance(self) -> None:
        client = self.FlakyThenUp(fail_times=2)

        checks = await run_smoke_with_retry("https://synthetic.example", "s", "s", client, attempts=3, wait_seconds=0)  # type: ignore[arg-type]

        assert exit_code(checks) == 0, "콜드스타트 한두 번에 되돌리게 된다"
        assert client.tries == 3

    async def test_a_judged_failure_is_not_asked_again(self) -> None:
        """`degraded` 를 여러 번 물으면 진짜 고장이 간헐적으로 보인다."""
        client = StubClient(StubResponse(503, DEGRADED))

        checks = await run_smoke_with_retry("https://synthetic.example", "s", "s", client, attempts=3, wait_seconds=0)  # type: ignore[arg-type]

        assert exit_code(checks) == 1
        assert len(client.seen) == 1, f"판정된 실패를 다시 물었다 ({len(client.seen)}회)"

    def test_the_entry_point_actually_uses_it(self) -> None:
        """**부품만 있고 연결이 없으면 아무 일도 안 일어난다.**

        실제로 이 PR 을 만들다 `main()` 이 재시도 없는 쪽을 부르는 채로 한 번
        지나갔다. 검사 넷이 다 초록이었는데 배포에서는 재시도가 안 돈다.
        """
        source = (ROOT / "scripts" / "smoke.py").read_text(encoding="utf-8")
        entry = source[source.index("async def main(") :]

        assert "run_smoke_with_retry(" in entry, "진입점이 재시도판을 안 쓴다"
        assert "await run_smoke(" not in entry, "진입점이 재시도 없는 쪽을 부른다"

    async def test_it_gives_up_after_the_last_attempt(self) -> None:
        client = self.FlakyThenUp(fail_times=99)

        checks = await run_smoke_with_retry("https://synthetic.example", "s", "s", client, attempts=2, wait_seconds=0)  # type: ignore[arg-type]

        assert exit_code(checks) == 1
        assert client.tries == 2, "정해진 횟수를 넘겨 계속 건다"


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


class TestRejectedAndNotPermittedAreDifferentThings:
    """401 과 403 은 **고치는 사람이 다르다** — `#141` 리뷰.

        401  토큰이 없거나 만료됐다 — 인증 문제
        403  `hospital_id` 미배정이거나 `PATIENT_READ` 가 없다 — 계정 설정 문제

    한 사유로 묶으면 배포가 멈춘 새벽에 비밀번호부터 뒤진다.
    """

    @pytest.mark.parametrize("name", ["auth", "core"])
    def test_a_401_is_an_auth_problem(self, name: str) -> None:
        assert judge_status(name, 401).reason is Reason.AUTH_REJECTED  # type: ignore[union-attr]

    @pytest.mark.parametrize("name", ["auth", "core"])
    def test_a_403_is_an_account_setup_problem(self, name: str) -> None:
        check = judge_status(name, 403)
        assert check is not None and check.reason is Reason.NOT_PERMITTED
        assert "hospital_id" in str(check.reason), "무엇을 봐야 하는지 안 알려 준다"

    def test_the_two_do_not_share_a_reason(self) -> None:
        """같은 사유로 묶이면 이 검사가 운다."""
        assert judge_status("core", 401).reason is not judge_status("core", 403).reason  # type: ignore[union-attr]


class TestOnlyKnownServiceNamesLeave:
    """`health` 가 새 항목을 돌려줘도 **그 글자는 안 나간다** — `#141` 리뷰."""

    def test_a_known_service_is_named(self) -> None:
        assert judge_health(503, DEGRADED).note == "db"

    def test_an_unknown_service_name_is_not_echoed(self) -> None:
        body = {
            "status": "degraded",
            "services": {
                "api": {"status": "ok"},
                "SYNTHETIC-NEW-KEY": {"status": "error", "detail": LEAK_MARKERS[0]},
            },
        }
        check = judge_health(503, body)

        assert not check.ok
        assert "SYNTHETIC-NEW-KEY" not in check.line(), "모르는 항목 이름이 그대로 나갔다"
        assert LEAK_MARKERS[0] not in check.line()


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

    def test_an_unknown_exception_becomes_a_failure_not_a_traceback(self) -> None:
        """모르는 예외도 **실패로 남기되 어휘로만 낸다** — `#141` 리뷰 반영.

        예전에는 그대로 다시 던졌다. 「삼키지 않는다」는 맞았지만, 판정 함수에
        버그가 있으면 정제된 보고문 대신 raw traceback 이 배포 로그에 찍힌다.
        """
        check = failure_of("health", RuntimeError("SYNTHETIC-INNER-DETAIL"))

        assert not check.ok, "모르는 예외가 통과로 보인다"
        assert check.reason is Reason.JUDGE_FAILED
        assert "SYNTHETIC-INNER-DETAIL" not in check.line(), "예외 속 글자가 보고문으로 샜다"
        assert "RuntimeError" in check.note, "무엇이 터졌는지는 남아야 한다"
