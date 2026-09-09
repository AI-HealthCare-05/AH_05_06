"""**파이썬 검사도 실리는 화면 파일만 읽는다** — KEY-313.

프런트 쪽에는 같은 규칙이 있다(`frontend/tests/orphan-scripts.test.js`). 그런데
그것은 JS 검사만 훑어서, **파이썬 검사가 고아를 읽는 것을 못 봤다.**

실제로 그 구멍으로 한 번 새어 나갔다 — 고아 셋을 지운 뒤 프런트 회귀는 전부
초록이었는데 CI 가 빨갛게 났다. `app/tests/fixtures/test_prescription_rows.py`
가 `frontend/js/guide-api.js` 를 읽고 있었다. **한쪽만 재는 규칙은 그쪽만
지킨다.**
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend"

#: 파이썬 검사가 화면 파일을 가리키는 모양 — `"frontend" / "js" / "이름.js"` 와
#: `FRONTEND / name` 둘 다 결국 파일 이름으로 끝난다. 이름만 뽑아 본다.
SCRIPT_NAME = re.compile(r'"([\w.-]+\.js)"')


def loaded_scripts() -> set[str]:
    """어느 화면이든 `<script src>` 로 싣는 것 — 버전 꼬리는 뗀다."""
    pages = list(FRONTEND.glob("*.html")) + list((FRONTEND / "patient_wireframe" / "html").glob("*.html"))
    loaded: set[str] = set()
    for page in pages:
        for found in re.finditer(r'<script src="([^"]+)"', page.read_text(encoding="utf-8")):
            loaded.add(found.group(1).split("?")[0].lstrip("/"))
    return loaded


def test_no_python_test_reads_a_script_no_page_loads() -> None:
    """**이름이 아니라 자리로 본다.**

    `guide-api.js` 는 두 자리에 있(었)다 — `frontend/js/`(고아)와
    `frontend/patient_wireframe/js/`(실린다). 이름만 세면 실리는 쪽 때문에
    고아가 늘 통과한다. 처음에 그렇게 썼다가 돌연변이가 안 물어서 알았다.
    """
    loaded = loaded_scripts()
    orphans = {
        str(path.relative_to(FRONTEND))
        for path in FRONTEND.rglob("*.js")
        if "tests" not in path.parts
        and "node_modules" not in path.parts
        and str(path.relative_to(FRONTEND)) not in loaded
    }

    wrong: list[str] = []
    for path in (ROOT / "app" / "tests").rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            #: 같은 줄에서 실리는 자리를 못 박았으면 그것을 믿는다.
            if "patient_wireframe" in line:
                continue
            for found in SCRIPT_NAME.finditer(line):
                if f"js/{found.group(1)}" in orphans:
                    wrong.append(f"{path.relative_to(ROOT)}:{number} → js/{found.group(1)}")

    assert not wrong, (
        "파이썬 검사가 아무 화면도 안 싣는 파일을 읽는다 — " + " · ".join(sorted(set(wrong))) + ". "
        "지키려는 계약을 실제로 실리는 파일로 옮긴다"
    )
