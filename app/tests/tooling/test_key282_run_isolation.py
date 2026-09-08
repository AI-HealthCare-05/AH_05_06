"""검사 판 자체를 잰다 — pytest 두 실행이 서로를 망치지 않는가 (KEY-282).

**이름이 다른지가 아니라 실제로 두 번 띄워서 본다.** `get_test_db_config()` 가
`test` 와 `test_1` 을 돌려주는지 확인하는 검사는 이 결함을 못 잡았을 것이다 —
결함은 이름을 짓는 함수가 아니라 「따로 띄운 두 실행이 둘 다 같은 이름을 받는다」는
데 있었고, 그건 프로세스가 둘일 때만 드러난다.

겪은 것(2026-09-07 로컬): 멀쩡한 검사 하나가 빨갛게 나왔고, 두 실행이 22분 동안
서로를 막았다. **틀린 답이 나오는 것이 느린 것보다 나쁘다** — 없는 결함을 쫓게 된다.
"""

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.tests.conftest import REDIS_LOGICAL_DB_COUNT, TEST_SLOT_ENV
from app.tests.tooling.test_key282_slot_probe import probe_path

ROOT = Path(__file__).resolve().parents[3]

#: 자식이 돌릴 것 — DB 를 실제로 세우되(세션 픽스처가 도는 것이 요점이다) 짧은 것.
CHILD_TARGET = "app/tests/fixtures/test_prescription_rows.py"
#: 자리마다 「실제로 무엇을 썼는지」를 파일로 남기는 쪽.
PROBE_TARGET = "app/tests/tooling/test_key282_slot_probe.py"
CHILD_TIMEOUT = 180

LOCK_MARK = "이미 다른 pytest 실행이 쓰고 있다"
GRANT_MARK = "만들 권한이 없다"


def _free_slots(lane: int = 0) -> tuple[int, int]:
    """부모도 **형제도** 안 쓰는 자리 둘.

    부모가 `-n auto` 로 돌면 워커들이 `base … base+N-1` 을 이미 잡고 있다. 그 위를
    골라야 자식이 부모를 물지 않는다 — 안 그러면 이 검사가 **자기 자신을 막는다.**

    형제를 피하는 것이 `lane` 이다 (KEY-309). 전에는 호출자 모두에게 같은 쌍을
    돌려줬다. `-n auto` 면 이 파일의 검사들이 서로 다른 워커로 흩어져 나란히 도는데,
    그중 하나(`test_the_same_slot_stops_instead_of_overlapping`)는 그 자리를
    **일부러 물고 있다.** 그 사이 다른 검사가 같은 자리를 잡으려다 잠금에 걸려,
    상관없는 PR 의 CI 가 빨개졌다 — 2,248 통과에 이것 하나만 실패하는 모양이라
    사람이 원인을 자기 변경에서 찾게 된다. 부모만 피하고 형제는 안 피했던 것이다.

    한 검사가 최대 두 자리를 쓰므로 `lane` 은 둘씩 벌려 준다.
    """
    base = int(os.environ.get(TEST_SLOT_ENV, "0") or "0")
    workers = int(os.environ.get("PYTEST_XDIST_WORKER_COUNT", "1") or "1")
    first = base + workers + lane
    if first + 1 >= REDIS_LOGICAL_DB_COUNT:
        pytest.skip(
            f"자리가 모자라 자식을 띄울 수 없다 — 부모가 {base + workers - 1}번까지 쓰고, "
            f"이 검사는 {first}·{first + 1}번이 필요하다"
        )
    return first, first + 1


def _skip_if_ungranted(results: list[tuple[int, str]]) -> None:
    """이 판의 MySQL 볼륨이 `initdb.d` 보다 오래된 경우 — 권한을 넣으면 된다.

    자식이 그 방법까지 적어 주므로 그대로 옮겨 보여 준다. 조용히 통과시키지 않는다.
    """
    reason = next((text for _, text in results if GRANT_MARK in text), None)
    if reason is not None:
        pytest.skip(f"자리별 DB 를 만들 권한이 없다:\n{reason[-900:]}")


def _spawn(slot: int, target: str) -> subprocess.Popen[str]:
    env = {**os.environ, TEST_SLOT_ENV: str(slot)}
    #: 자식이 또 이 검사를 집으면 무한히 번진다 — 대상을 한 파일로 못 박는다.
    env.pop("PYTEST_XDIST_WORKER", None)
    env.pop("PYTEST_XDIST_WORKER_COUNT", None)
    return subprocess.Popen(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _drain_with(child: "subprocess.Popen[str]", timeout: int) -> tuple[bool, int, str]:
    """한 자식을 끝까지 읽는다. 시간이 지나면 **죽이고** 그 사실을 함께 돌려준다.

    여기서 `pytest.fail()` 을 부르지 않는다 — 스레드 안에서 던지면 다른 자식이
    거둬지지 않은 채 남는다. 판정은 둘을 다 거둔 뒤 부르는 쪽이 한다.
    """
    try:
        text = child.communicate(timeout=timeout)[0]
    except subprocess.TimeoutExpired:
        child.kill()
        return True, -9, child.communicate()[0]
    return False, child.returncode, text


def _drain(child: "subprocess.Popen[str]") -> tuple[bool, int, str]:
    return _drain_with(child, CHILD_TIMEOUT)


def _run_both(slot_a: int, slot_b: int, target: str = CHILD_TARGET) -> list[tuple[int, str]]:
    """둘을 **겹쳐** 띄운다 — 하나씩 돌리면 이 결함은 안 난다.

    **둘을 나란히 읽는다** — 이희진 님 `#240` ②③.

    예전 판은 순서대로 `communicate()` 했다. 두 가지가 걸렸다.

    ⓐ 첫 자식이 시간을 넘기면 그 자식만 죽이고 `pytest.fail()` 로 곧장 빠져나가,
      **둘째는 죽지도 기다려지지도 않은 채 남았다.** 세션 픽스처에 도달을 못 하니
      제 자리의 잠금을 계속 들고 있다 — 이 검사가 잡으려는 그 상황을 스스로 만든다.
    ⓑ 둘 다 `stdout=PIPE` 인데 순서대로 비우면, 아직 안 읽는 쪽이 파이프를 채웠을 때
      서로를 막는다. 「GRANT 없으면 36 errors」처럼 말이 많아지는 갈래가 실제로 있다.

    스레드 둘로 나란히 읽고, 무슨 일이 있어도 살아남은 자식은 `finally` 에서 죽인다.
    """
    children = [_spawn(slot_a, target), _spawn(slot_b, target)]
    try:
        with ThreadPoolExecutor(max_workers=len(children)) as pool:
            drained = list(pool.map(_drain, children))
    finally:
        for child in children:
            if child.poll() is None:  # 여기 오면 위에서 못 거둔 것이다
                child.kill()
                child.wait()

    late = [text for timed_out, _, text in drained if timed_out]
    if late:
        pytest.fail(f"자식이 {CHILD_TIMEOUT}초 안에 안 끝났다 — 서로 막고 있는 것 같다\n{late[0][-2000:]}")
    return [(code, text) for _, code, text in drained]


class TestTheHarnessCleansUpAfterItself:
    """이 검사 도구가 **스스로 이 결함을 만들지 않는지** 잰다 — 이희진 님 `#240` ①②⑤."""

    def test_a_stuck_child_is_never_left_behind(self, monkeypatch: "pytest.MonkeyPatch") -> None:
        """시간을 넘겨도 **둘 다** 거둔다.

        예전 판은 첫 자식이 시간을 넘기면 그 자식만 죽이고 곧장 빠져나가, 둘째가
        살아남아 제 자리의 잠금을 계속 들었다 — 이 파일이 잡으려는 그 상황을
        스스로 만들었다.

        **`_run_both` 을 실제로 지난다.** 처음에는 `_drain_with` 만 따로 불러 봤는데,
        그러면 `_run_both` 의 거두는 코드를 걷어내도 검사가 안 울었다.
        """
        module = sys.modules[__name__]
        spawned: list[subprocess.Popen[str]] = []

        def never_finishes(_slot: int, _target: str) -> "subprocess.Popen[str]":
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(120)"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            spawned.append(child)
            return child

        monkeypatch.setattr(module, "_spawn", never_finishes)
        monkeypatch.setattr(module, "CHILD_TIMEOUT", 1)

        try:
            with pytest.raises(BaseException):  # noqa: B017 — pytest.fail 의 예외를 붙잡는다
                _run_both(0, 1)

            assert len(spawned) == 2, f"자식을 {len(spawned)}개만 띄웠다"
            for child in spawned:
                assert child.poll() is not None, f"자식 {child.pid} 이 살아남았다 — 자리를 계속 들고 있다"
        finally:
            for child in spawned:
                if child.poll() is None:
                    child.kill()
                    child.wait()

    def test_the_loser_can_say_who_is_holding_the_slot(self) -> None:
        """**진 쪽이 보유자를 지우지 않는다** — `"w"` 로 열면 여는 것만으로 지운다.

        정작 충돌한 그 순간에 「누가 들고 있는지」를 알 수 없으면, 사람은 터미널을
        하나씩 뒤져야 한다.
        """
        slot = _free_slots(lane=0)[0]
        first, second = _run_both(slot, slot)
        _skip_if_ungranted([first, second])

        stopped = next((text for code, text in (first, second) if code != 0 and LOCK_MARK in text), None)
        assert stopped is not None, "겹쳤는데 아무도 안 멈췄다"
        assert re.search(r"pid \d+", stopped), f"보유자를 못 말한다 — {stopped[-400:]}"

    def test_the_slot_is_released_even_when_teardown_blows_up(self) -> None:
        """**놓는 일은 `finally` 에서 한다.**

        pytest 는 teardown 예외에도 곧장 안 죽고 다른 finalizer·리포트까지 마친다.
        그 사이 같은 자리를 쓰는 두 번째 실행이 막힌다 — 이 파일이 막으려던 그 상황이다.

        실제로 `finalizer()` 를 터뜨려 확인했고(그때도 다음 실행이 안 막혔다), 여기서는
        그 구조가 남아 있는지를 잰다 — 터뜨리는 상황은 검사 안에서 만들 수 없다.
        """
        source = (Path(__file__).resolve().parents[1] / "conftest.py").read_text(encoding="utf-8")

        #: **코드 모양으로 못 박는다.** 「`finally:` 가 `_release_slot()` 보다 앞에
        #: 있는가」로 재면 그 위 주석에 적힌 같은 이름을 먼저 잡아 헛돈다 —
        #: 실제로 처음에 그렇게 썼다가 걸렸다.
        assert "    finally:\n        _release_slot()" in source, (
            "teardown 이 터지면 자리를 붙든 채 남는다 — 놓는 일이 `finally` 안에 없다"
        )


class TestTwoRunsDoNotEatEachOther:
    def test_the_same_slot_stops_instead_of_overlapping(self) -> None:
        """같은 자리를 두 실행이 잡으면 **한쪽이 그 자리에서 멈춘다.**

        조용히 진행하면 늦게 시작한 쪽이 먼저 돌던 쪽의 스키마를 지운다. 겹치는
        것보다 우는 편이 낫다는 것은 이 파일 위쪽(워커 16개 초과)이 이미 정한 태도다.
        """
        slot = _free_slots(lane=2)[0]
        results = _run_both(slot, slot)

        stopped = [text for code, text in results if code != 0 and LOCK_MARK in text]
        assert len(stopped) == 1, (
            "같은 자리를 잡은 두 실행 중 정확히 하나가 멈춰야 한다 — "
            f"멈춘 것 {len(stopped)}개. 둘 다 진행했다면 한쪽이 남의 스키마를 지운다.\n"
            + "\n──\n".join(text[-1500:] for _, text in results)
        )
        #: 멈추는 것만으로는 부족하다 — **무엇을 하면 되는지**까지 말해야 한다.
        assert TEST_SLOT_ENV in stopped[0], "멈추면서 자리를 달리 주는 방법을 안 알려 준다"

    def test_different_slots_both_finish(self) -> None:
        """자리를 달리 주면 둘 다 끝까지 간다 — 서로의 결과를 바꾸지 않는다."""
        slot_a, slot_b = _free_slots(lane=4)
        results = _run_both(slot_a, slot_b)
        _skip_if_ungranted(results)

        for slot, (code, text) in zip((slot_a, slot_b), results, strict=True):
            assert code == 0, f"자리 {slot} 실행이 실패했다 — 서로를 밟고 있다\n{text[-2000:]}"
            assert LOCK_MARK not in text, f"자리 {slot} 이 남의 자리를 잡으려 했다"

    def test_the_two_runs_use_different_databases_and_redis(self) -> None:
        """**둘이 실제로 무엇을 썼는지** 받아 보고 비교한다.

        한 프로세스 안에서 `config.REDIS_DB == run_slot()` 을 재면 자리 0 에서
        `0 == 0` 이라 늘 참이고, Redis 를 자리와 따로 두는 회귀가 그대로 통과한다.
        겹치는지는 프로세스가 둘일 때만 드러난다.
        """
        slot_a, slot_b = _free_slots(lane=6)
        for slot in (slot_a, slot_b):
            probe_path(slot).unlink(missing_ok=True)

        results = _run_both(slot_a, slot_b, target=PROBE_TARGET)
        _skip_if_ungranted(results)
        for slot, (code, text) in zip((slot_a, slot_b), results, strict=True):
            assert code == 0, f"자리 {slot} 자취를 못 남겼다\n{text[-2000:]}"

        seen = []
        for slot in (slot_a, slot_b):
            path = probe_path(slot)
            assert path.exists(), f"자리 {slot} 이 자취를 안 남겼다"
            seen.append(json.loads(path.read_text(encoding="utf-8")))

        first, second = seen
        assert first["database"] != second["database"], (
            f"두 실행이 같은 DB `{first['database']}` 를 썼다 — 한쪽이 남의 스키마를 지운다"
        )
        assert first["redis_db"] != second["redis_db"], (
            f"두 실행이 같은 Redis 논리 DB({first['redis_db']})를 썼다 — 이름만 갈리고 세션·로그인시도 카운터는 겹친다"
        )
