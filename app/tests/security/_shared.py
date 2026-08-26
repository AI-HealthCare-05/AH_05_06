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
