"""이 실행이 **실제로 무엇을 쓰는지** 한 줄로 남긴다 (KEY-282).

혼자서는 아무것도 증명하지 않는다. `test_key282_run_isolation.py` 가 자리를
달리해 이 파일을 두 번 띄우고, 남은 두 줄이 **서로 다른지**를 본다.

왜 이렇게 하나 — 한 프로세스 안에서 `config.REDIS_DB == run_slot()` 을 재면
자리 0 에서 `0 == 0` 이라 늘 참이다. Redis 를 자리와 따로 두는 회귀(예전 동작)가
그 단언을 그대로 통과한다. 실제로 겹치는지는 **프로세스가 둘일 때만** 드러난다.
"""

import json
import os
import tempfile
from pathlib import Path

from app.core import config
from app.tests.conftest import TEST_SLOT_ENV, get_test_db_config, run_slot

PROBE_DIR = Path(tempfile.gettempdir()) / "ah05-slot-probe"


def probe_path(slot: int) -> Path:
    return PROBE_DIR / f"slot-{slot}.json"


def test_this_run_records_what_it_actually_uses() -> None:
    slot = run_slot()
    database = get_test_db_config()["connections"]["models"]["credentials"]["database"]

    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    probe_path(slot).write_text(
        json.dumps(
            {
                "slot": slot,
                "database": database,
                "redis_db": config.REDIS_DB,
                "pid": os.getpid(),
                "env_slot": os.environ.get(TEST_SLOT_ENV),
            }
        ),
        encoding="utf-8",
    )

    #: 여기서 재는 것은 「적어 냈다」뿐이다. 값이 서로 다른지는 부모가 본다.
    assert database, "쓰는 DB 이름이 비어 있다"
