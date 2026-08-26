"""이 디렉터리의 보안 가드 테스트들이 공유하는 저장소 스캔 유틸리티."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def tracked_files(skip: frozenset[str] = frozenset(), root: Path = REPO_ROOT) -> list[str]:
    """추적 중인 파일 경로를 돌려준다.

    **`-z` 가 핵심이다.** 그냥 `git ls-files` 를 부르면 non-ASCII 이름을
    따옴표로 감싸 8진수로 이스케이프해 준다.

        지금 방식   "\\355\\225\\234\\352\\270\\200\\355\\214\\214\\354\\235\\274.env"
        -z          한글파일.env

    앞의 것은 `root / rel` 로 열리지 않는다. 그러면 **그 파일은 스캔에서 조용히
    빠진다** — 비밀값 재유출을 찾는 가드에서 이건 못 찾는 것과 같다 (KEY-139).

    `root` 를 받는 이유는 이 규칙 자체를 재려면 **다른 저장소가 필요해서**다.
    이 저장소에 한글 이름 파일을 넣어 두고 재는 것은 검사를 위해 정본을
    더럽히는 일이라, 검사가 임시 저장소를 만들어 넘긴다.
    """
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p and p not in skip]


def read_tracked_text(path: Path) -> str | None:
    """추적 파일 하나를 **인코딩 때문에 빠뜨리지 않고** 읽는다.

    `read_text(encoding="utf-8")` 은 CP949·EUC-KR 로 저장된 **멀쩡한 텍스트
    파일**에서 `UnicodeDecodeError` 를 낸다. 그걸 `except … : continue` 로
    받으면 그 파일은 훑기에서 통째로 빠지고, 안에 비밀값이 있어도 가드는
    초록이다 (KEY-139).

    가드가 찾는 것(개인키 머리글·비밀값)은 전부 ASCII 라, 못 읽는 바이트를
    바꿔치기해도 걸릴 것은 그대로 걸린다. 바이너리는 걸릴 모양이 없어 그냥
    지나간다.

    **여기 하나만 둔다.** 같은 버그가 이 디렉터리 안에서 두 번 따로 생겼다
    (재유출 가드 · 개인키 가드 — 이희진 님 `#143`). 세 번째를 막으려면
    읽는 자리가 하나여야 한다.

    열 수 없는 것(심볼릭 링크 · 디렉터리)은 `None` 이다.
    """
    try:
        raw = path.read_bytes()
    except (OSError, IsADirectoryError):
        return None
    return raw.decode("utf-8", errors="replace")
