"""저장소 이력에 노출된 비밀값이 **다시 쓰이지 않는지** 본다 — KEY-110.

초기 세팅 커밋 `b8ee2a9` 에 `envs/example.*.env` 가 실제 값이 담긴 채로
커밋됐다. `25fe152` 가 자리표시자로 바꿨지만 **이력에는 그대로 남아 있고
이 저장소는 공개(public)** 다. 이력을 되쓰지 않기로 했으므로(티켓 참조),
남은 방어선은 하나다 — **그 값들을 아무 데서도 쓰지 않는 것.**

값 자체는 여기 적지 않는다. 적으면 이 파일이 새 유출점이 된다.
**sha256 만 들고** 비교한다.

새로 노출된 값이 생기면 해시를 여기에 더한다.
"""

import hashlib
import re
from functools import lru_cache

from app.tests.security._shared import REPO_ROOT as ROOT
from app.tests.security._shared import read_tracked_text, tracked_files

#: `b8ee2a9` 의 `SECRET_KEY` · `DB_PASSWORD` · `DB_ROOT_PASSWORD` (local · prod)
EXPOSED_DIGESTS = frozenset(
    {
        "065811792719a9575964a1edb1786209b2d80053196a1d607c0c4953e8083572",
        "28b57dbb6074542ec7f4b9c06cee6d97e95d2dfec8986380e7dad020efae5fbd",
        "ae2d8345a478f20f13c168b54721c6b6ca555b0fcb4d00bf539650609982eefd",
        "b63e25edc1b1583c52d00a699c173339c8ec9f2ef931f7c5a3b84b87c72c2f30",
        "fb72a905a57f81e8358e432b7c699ff6987200697366167e4ba962953b072868",
    }
)

#: 이 파일 자신은 해시를 들고 있으므로 검사 대상에서 뺀다.
SKIP = frozenset({"app/tests/security/test_exposed_secrets_not_reused.py"})

#: 값이 나타날 만한 자리 — `KEY=값` · 따옴표 문자열 · YAML `키: 값`.
#: 줄 끝 인라인 주석(`# ...`)이 붙어도 값은 여전히 잡아야 하고, 따옴표 문자열은
#: 이스케이프된 인용부호(`\'`, `\"`) 때문에 엉뚱한 자리에서 끝나면 안 된다.
_CANDIDATES = (
    re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*[:=]\s*[\"']?([^\"'\n#]+?)[\"']?\s*(?:#.*)?$", re.M),
    re.compile(r"[\"']((?:\\.|[^\"'\\\n]){4,128})[\"']"),
)


@lru_cache(maxsize=1)
def _digest_index() -> dict[str, list[tuple[str, str]]]:
    """추적 파일 전체를 한 번만 훑어, 나온 값마다 sha256 을 인덱싱한다.

    `_scan()` 이 매번 다른 digest 집합으로 불려도(가드 · 자가진단) 파일을
    다시 읽고 다시 정규식을 돌리지 않도록 훑기 자체를 한 번만 한다.
    """
    index: dict[str, list[tuple[str, str]]] = {}
    for rel in tracked_files(skip=SKIP):
        # 읽는 방법은 `_shared.read_tracked_text` 하나뿐이다 — 왜 그렇게
        # 읽는지는 거기 적혀 있다 (KEY-139 · 이희진 님 `#143`).
        body = read_tracked_text(ROOT / rel)
        if body is None:
            continue  # 심볼릭 링크·디렉터리
        for pattern in _CANDIDATES:
            for value in pattern.findall(body):
                digest = hashlib.sha256(value.strip().encode()).hexdigest()
                index.setdefault(digest, []).append((rel, digest[:12]))
    return index


def _scan(digests: frozenset[str]) -> list[tuple[str, str]]:
    """주어진 해시 중 추적 파일에서 걸리는 것을 찾는다."""
    index = _digest_index()
    found = [hit for digest in digests for hit in index.get(digest, [])]
    return sorted(set(found))


def test_exposed_secrets_are_not_used_anywhere() -> None:
    offenders = _scan(EXPOSED_DIGESTS)
    assert not offenders, (
        "이력에 노출된 비밀값이 추적 파일에서 다시 쓰이고 있다 (KEY-110). "
        "값을 바꾸고 다시 돌려라 — " + ", ".join(f"{path}(sha256:{d}…)" for path, d in offenders)
    )


def test_the_scanner_actually_finds_things() -> None:
    """가드가 통과하는 이유가 「아무것도 안 봐서」면 안 된다.

    비밀이 아닌 값 하나를 일부러 찾게 해서 훑기가 도는지 확인한다.
    `JWT_ALGORITHM` 은 `app/core/config.py` 에 있고 비밀이 아니다.
    """
    assert tracked_files(skip=SKIP), "추적 파일을 하나도 못 읽었다 — 검사가 헛돌고 있다"
    assert len(EXPOSED_DIGESTS) == 5, "b8ee2a9 에서 새어 나간 값은 다섯이다"

    harmless = hashlib.sha256(b"HS256").hexdigest()
    assert _scan(frozenset({harmless})), "훑기가 실제 파일 내용을 못 보고 있다"
