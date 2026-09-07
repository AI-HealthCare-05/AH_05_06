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
import subprocess
import sys
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


def _free_slots() -> tuple[int, int]:
    """부모가 안 쓰는 자리 둘.

    부모가 `-n auto` 로 돌면 워커들이 `base … base+N-1` 을 이미 잡고 있다. 그 위를
    골라야 자식이 부모를 물지 않는다 — 안 그러면 이 검사가 **자기 자신을 막는다.**
    """
    base = int(os.environ.get(TEST_SLOT_ENV, "0") or "0")
    workers = int(os.environ.get("PYTEST_XDIST_WORKER_COUNT", "1") or "1")
    first = base + workers
    if first + 1 >= REDIS_LOGICAL_DB_COUNT:
        pytest.skip(f"자리가 모자라 자식을 띄울 수 없다 — 부모가 {first}번까지 쓰고 있다")
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


def _run_both(slot_a: int, slot_b: int, target: str = CHILD_TARGET) -> list[tuple[int, str]]:
    """둘을 **겹쳐** 띄운다 — 하나씩 돌리면 이 결함은 안 난다."""
    children = [_spawn(slot_a, target), _spawn(slot_b, target)]
    out = []
    for child in children:
        try:
            text = child.communicate(timeout=CHILD_TIMEOUT)[0]
        except subprocess.TimeoutExpired:
            child.kill()
            text = child.communicate()[0]
            pytest.fail(f"자식이 {CHILD_TIMEOUT}초 안에 안 끝났다 — 서로 막고 있는 것 같다\n{text[-2000:]}")
        out.append((child.returncode, text))
    return out


class TestTwoRunsDoNotEatEachOther:
    def test_the_same_slot_stops_instead_of_overlapping(self) -> None:
        """같은 자리를 두 실행이 잡으면 **한쪽이 그 자리에서 멈춘다.**

        조용히 진행하면 늦게 시작한 쪽이 먼저 돌던 쪽의 스키마를 지운다. 겹치는
        것보다 우는 편이 낫다는 것은 이 파일 위쪽(워커 16개 초과)이 이미 정한 태도다.
        """
        slot = _free_slots()[0]
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
        slot_a, slot_b = _free_slots()
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
        slot_a, slot_b = _free_slots()
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
