"""마이그레이션 검사들이 함께 쓰는 것 — KEY-162 (`#91` 리뷰, 이희진).

`MIGRATIONS` 와 `_files()` 를 두 검사 파일이 각자 들고 있었다. **경로나 이름
규칙이 바뀔 때 한쪽만 고치고 넘어가기 쉽다** — 그러면 안 고친 쪽이 빈 목록을
훑고 조용히 통과한다. 이 폴더의 검사들이 막으려는 것이 정확히 그 상태라,
같은 실수를 검사 자신이 하지 않도록 한 곳으로 모은다.
"""

from pathlib import Path

#: `aerich` 가 읽는 마이그레이션 폴더.
MIGRATIONS = Path(__file__).resolve().parents[2] / "core" / "db" / "migrations" / "models"


def migration_files() -> list[Path]:
    """번호가 붙은 마이그레이션 파일. `__init__.py` 같은 것은 뺀다."""
    return sorted(p for p in MIGRATIONS.glob("*.py") if p.name[0].isdigit())
