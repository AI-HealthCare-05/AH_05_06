"""이 디렉터리의 보안 가드 테스트들이 공유하는 저장소 스캔 유틸리티."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def tracked_files(skip: frozenset[str] = frozenset()) -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p and p not in skip]
