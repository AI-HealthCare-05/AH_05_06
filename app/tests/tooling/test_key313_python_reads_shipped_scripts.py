"""**파이썬 검사도 실리는 화면 파일만 읽는다** — KEY-313.

프런트 쪽에는 같은 규칙이 있다(`frontend/tests/orphan-scripts.test.js`). 그런데
그것은 JS 검사만 훑어서, **파이썬 검사가 고아를 읽는 것을 못 봤다.**

실제로 그 구멍으로 한 번 새어 나갔다 — 고아 셋을 지운 뒤 프런트 회귀는 전부
초록이었는데 CI 가 빨갛게 났다. `app/tests/fixtures/test_prescription_rows.py`
가 `frontend/js/guide-api.js` 를 읽고 있었다. **한쪽만 재는 규칙은 그쪽만
지킨다.**
"""

import io
import re
import tokenize
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend"

#: 한 줄에 적힌 따옴표 토막 전부. 파이썬 검사가 화면 파일을 가리키는 모양은
#: 둘이다 — `FRONTEND / "js" / "이름.js"` 처럼 칸을 나눠 적거나,
#: `"frontend/js/이름.js"` 처럼 한 따옴표에 통째로 적는다.
QUOTED = re.compile(r'"([\w./-]+)"')


def referenced_paths(line: str) -> set[str]:
    """한 줄이 가리키는 화면 파일 경로 후보 — **`frontend/` 아래 자리로 맞춘다.**

    칸을 나눠 적은 것은 이어 붙여야 자리가 드러난다 — `"patient_wireframe" /
    "component" / "tab-bar.js"` 는 이름만 보면 `tab-bar.js` 지만 자리로 보면
    `patient_wireframe/component/tab-bar.js` 다.

    **끝만 맞춰 보면 안 된다.** `frontend/patient_wireframe/js/guide-api.js` 는
    `js/guide-api.js` 로 끝나서, 실리는 쪽을 가리켰는데 고아로 잡힌다. 그래서
    `frontend/` 뒤를 잘라 **자리를 통째로** 견준다.
    """
    parts = QUOTED.findall(line)
    if not any(part.endswith(".js") for part in parts):
        return set()

    def under_frontend(text: str) -> str:
        return text.split("frontend/", 1)[1] if "frontend/" in text else text

    found = {under_frontend(part) for part in parts if part.endswith(".js")}
    found.add(under_frontend("/".join(parts)))
    return found


def code_lines(text: str) -> dict[int, str]:
    """주석과 독스트링을 뺀 줄 — **설명글에 적은 경로가 제 검사에 걸린다.**

    프런트 쪽 규칙(`orphan-scripts.test.js`)이 같은 자리에서 한 번 넘어졌고,
    이 파일도 고쳐 놓고 보니 **제 독스트링에 예로 적은 경로**를 스스로 잡았다.
    재려는 것은 검사가 실제로 읽는 파일이지 설명에 적힌 이름이 아니다.
    """
    starts_statement = {tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING}
    skip = {tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}

    kept: dict[int, list[str]] = {}
    previous = tokenize.ENCODING
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            continue
        #: 홀로 선 문자열은 독스트링이다 — 값으로 쓰이는 문자열과 이렇게 갈린다.
        if token.type == tokenize.STRING and previous in starts_statement:
            previous = tokenize.STRING
            continue
        if token.type not in skip:
            kept.setdefault(token.start[0], []).append(token.string)
        if token.type != tokenize.NL:
            previous = token.type
    return {number: " ".join(parts) for number, parts in kept.items()}


def loaded_scripts() -> set[str]:
    """어느 화면이든 `<script src>` 로 싣는 것 — 버전 꼬리는 뗀다."""
    pages = list(FRONTEND.glob("*.html")) + list((FRONTEND / "patient_wireframe" / "html").glob("*.html"))
    loaded: set[str] = set()
    for page in pages:
        for found in re.finditer(r'<script src="([^"]+)"', page.read_text(encoding="utf-8")):
            loaded.add(found.group(1).split("?")[0].lstrip("/"))
    return loaded


def test_no_python_test_reads_a_script_no_page_loads() -> None:
    """**이름이 아니라 자리로 본다 — 자리를 못 대면 이름으로만 잰다.**

    `guide-api.js` 는 두 자리에 있(었)다 — `frontend/js/`(고아)와
    `frontend/patient_wireframe/js/`(실린다). 이름만 세면 실리는 쪽 때문에
    고아가 늘 통과한다. 처음에 그렇게 썼다가 돌연변이가 안 물어서 알았다.

    🚩 그 다음에 **반대쪽으로 샜다** (2heej 리뷰). 고쳐 놓은 것이 `js/` 로
    시작하는 자리만 재고, 같은 줄에 `patient_wireframe` 글자가 있으면 통째로
    믿고 건너뛰었다. 그런데 이 티켓이 지운 고아 셋 중 하나가 바로
    `patient_wireframe/component/tab-bar.js` 였다 — **막으려던 그 자리를 스스로
    비껴갔다.** 이제 건너뛰지 않고, 줄에 적힌 칸을 이어 붙여 자리로 잰다.

    자리를 안 적고 이름만 넘기는 줄도 있다(`parametrize("name", [...])` 뒤에
    `FRONTEND / name`). 그런 이름은 **고아에만 있고 실리는 쪽에는 없을 때만**
    잰다 — 두 자리에 같은 이름이 있으면 어느 쪽인지 줄만 봐서는 모른다.
    """
    loaded = loaded_scripts()
    orphans = {
        str(path.relative_to(FRONTEND))
        for path in FRONTEND.rglob("*.js")
        if "tests" not in path.parts
        and "node_modules" not in path.parts
        and str(path.relative_to(FRONTEND)) not in loaded
    }
    shipped_names = {PurePosixPath(rel).name for rel in loaded}

    wrong: list[str] = []
    for path in (ROOT / "app" / "tests").rglob("*.py"):
        for number, line in code_lines(path.read_text(encoding="utf-8")).items():
            for candidate in referenced_paths(line):
                for orphan in orphans:
                    #: 자리 없이 이름만 적었다면, 그 이름이 고아에만 있을 때만 잰다.
                    named_only = (
                        "/" not in candidate
                        and candidate == PurePosixPath(orphan).name
                        and candidate not in shipped_names
                    )
                    if candidate == orphan or named_only:
                        wrong.append(f"{path.relative_to(ROOT)}:{number} → {orphan}")

    assert not wrong, (
        "파이썬 검사가 아무 화면도 안 싣는 파일을 읽는다 — " + " · ".join(sorted(set(wrong))) + ". "
        "지키려는 계약을 실제로 실리는 파일로 옮긴다"
    )
