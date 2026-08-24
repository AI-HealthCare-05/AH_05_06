"""마이그레이션 파일의 **정수 접두사가 겹치지 않는지** 본다 — KEY-162.

왜 이 검사가 없으면 안 되는가.

`aerich` 는 파일 이름 앞의 정수로 정렬하고, 같은 번호끼리는 **안정 정렬**이라
순서가 파일이 나열되는 차례에 달린다. 겹쳐도 **오류를 내지 않는다** — 둘 다
조용히 실행된다. 깨지면 차라리 나은데 그러지 않는 것이 이 문제의 고약한 점이다.

`git` 도 못 잡는다. 두 브랜치가 각자 다음 번호를 붙이면 파일 이름이 달라서
충돌이 안 나고, 그대로 둘 다 들어온다. 이번 스프린트에 `#50` · `#67` · `#70` ·
`#82` 네 번 났고, 그중 하나(`#50` 과 `#82`)는 **실제로 `develop` 에 들어갔다.**

CI 도 못 잡았다. 검사는 `tortoise.contrib.test.initializer` 가 모델에서 스키마를
바로 만들어 쓰므로 **마이그레이션을 한 번도 돌리지 않는다.** 그래서 파일을
읽는 이 검사가 필요하다.
"""

import re
from collections import defaultdict

from app.tests.migrations.conftest import MIGRATIONS, migration_files

#: 앞자리 정수와 그 뒤 이름. `aerich` 가 정렬에 쓰는 것은 앞의 정수뿐이다.
_NUMBERED = re.compile(r"^(\d+)_(.+)\.py$")

#: 이 아래로 떨어지면 파일을 못 찾고 있는 것이다 — 아래 검사 참고.
MINIMUM_EXPECTED = 10


def test_the_guard_actually_sees_the_migrations() -> None:
    """**이 검사가 먼저다.**

    경로가 틀리거나 이름 규칙이 바뀌면 아래 검사는 빈 목록을 훑고 조용히
    통과한다 — 「번호가 안 겹친다」가 아니라 「볼 게 없다」인데 초록불이 된다.
    그 상태를 여기서 막는다.
    """
    files = migration_files()
    assert MIGRATIONS.is_dir(), f"마이그레이션 폴더를 못 찾았다: {MIGRATIONS}"
    assert len(files) >= MINIMUM_EXPECTED, (
        f"마이그레이션 파일을 {len(files)} 개밖에 못 찾았다 (최소 {MINIMUM_EXPECTED}). "
        "경로나 이름 규칙이 바뀌었는지 확인해라 — 이 검사가 헛돌고 있다"
    )
    assert any(p.name.startswith("0_") for p in files), "첫 마이그레이션(`0_`)이 안 보인다"


def test_no_two_migrations_share_a_version_number() -> None:
    """번호가 겹치면 **둘 다 조용히 실행된다.** 그 자리를 막는다."""
    by_number: dict[int, list[str]] = defaultdict(list)
    unnamed: list[str] = []

    for path in migration_files():
        match = _NUMBERED.match(path.name)
        if not match:
            unnamed.append(path.name)
            continue
        by_number[int(match.group(1))].append(path.name)

    assert not unnamed, f"`<번호>_<이름>.py` 모양이 아닌 파일: {sorted(unnamed)}"

    clashes = {number: sorted(names) for number, names in by_number.items() if len(names) > 1}
    assert not clashes, "번호가 겹친다 — " + " · ".join(
        f"{number}번: {', '.join(names)}" for number, names in sorted(clashes.items())
    )
