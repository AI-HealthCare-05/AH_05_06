"""**워커 이미지가 임베딩 모델을 안고 나간다** — KEY-339.

9/18 Pilot 에서 RAG 를 켜자 안내 생성이 워커 안에서 멈췄다. 워커가 그때서야
모델(458MB)을 내려받기 시작했고, 컨테이너를 다시 만들 때마다 그 기다림이
돌아왔다. 그래서 `ai_worker/Dockerfile` 이 빌드 때 미리 받아 둔다.

여기서 재는 것은 **두 자리가 갈라지지 않는가** 하나다.

    코드가 부르는 판      app/services/knowledge_search.py (KEY-82 가 고정)
    이미지가 받아 둔 판    ai_worker/Dockerfile

둘이 어긋나도 **생성은 성공한다** — 런타임이 없는 판을 조용히 다시 내려받을
뿐이다. 그래서 사람이 알아채는 경로가 없다. 느려진 이유를 찾다가 여기까지
오는 데 9/18 에 반나절이 걸렸다. 검사가 대신 본다.
"""

import re

from app.services.knowledge_search import EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION
from app.tests.deploy.conftest import read

DOCKERFILE = "ai_worker/Dockerfile"

#: `SentenceTransformer('<모델>', revision='<판>')` 에서 두 값.
#:
#: 낱말만 찾지 않는다 — `"paraphrase-multilingual" in text` 는 주석에 적힌
#: 이름에도 걸린다. 그러면 **주석만 남고 받아 두는 줄이 사라져도** 통과한다.
PRELOAD = re.compile(
    r"SentenceTransformer\(\s*['\"](?P<model>[^'\"]+)['\"]\s*,\s*revision=['\"](?P<revision>[^'\"]+)['\"]"
)

#: `ENV HF_HOME=<자리>` — 빌드와 런타임이 같은 자리를 보게 하는 줄.
HF_HOME = re.compile(r"^ENV\s+HF_HOME=(?P<path>\S+)\s*$", re.MULTILINE)

#: 40 자리 16 진수. 가지 이름(`main`)이나 태그는 **움직인다.**
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _preload() -> re.Match[str]:
    match = PRELOAD.search(read(DOCKERFILE))
    assert match is not None, f"{DOCKERFILE} 에 모델을 미리 받는 줄이 없다 — 첫 생성이 내려받기를 기다린다"
    return match


class TestTheImageCarriesTheModelTheCodeAsksFor:
    def test_the_model_matches_the_code(self) -> None:
        """이름이 다르면 런타임이 **다른 모델**을 새로 내려받는다."""
        assert _preload().group("model") == EMBEDDING_MODEL, (
            f"{DOCKERFILE} 이 받아 두는 모델이 knowledge_search.py 의 EMBEDDING_MODEL 과 다르다"
        )

    def test_the_revision_matches_the_code(self) -> None:
        """판이 다르면 받아 둔 것을 **못 쓰고** 그 자리에서 다시 받는다."""
        assert _preload().group("revision") == EMBEDDING_MODEL_REVISION, (
            f"{DOCKERFILE} 이 받아 두는 revision 이 knowledge_search.py 의 EMBEDDING_MODEL_REVISION 과 다르다"
        )

    def test_the_revision_is_a_commit_not_a_moving_ref(self) -> None:
        """`main` 을 박아 두면 빌드마다 다른 판이 들어온다 — KEY-82 가 판을 고정한 까닭이다."""
        assert COMMIT.match(EMBEDDING_MODEL_REVISION), "고정 판이 40 자리 커밋이 아니다"


class TestBuildAndRuntimeLookAtTheSamePlace:
    def test_the_cache_home_is_declared(self) -> None:
        """`HF_HOME` 이 없으면 빌드가 받아 둔 것이 **쓰기 층**에 남는다 —
        컨테이너를 다시 만드는 순간 사라지고, 배포마다 첫 생성이 다시 기다린다.
        """
        match = HF_HOME.search(read(DOCKERFILE))
        assert match is not None, f"{DOCKERFILE} 에 ENV HF_HOME 이 없다"
        assert match.group("path").startswith("/"), "HF_HOME 이 절대 경로가 아니다 — WORKDIR 에 따라 갈린다"

    def test_the_preload_comes_after_the_dependencies(self) -> None:
        """`uv sync` 보다 앞서면 `sentence_transformers` 가 아직 없어 빌드가 죽는다."""
        text = read(DOCKERFILE)
        assert text.index("uv sync") < _preload().start(), "모델을 받는 줄이 uv sync 보다 앞에 있다"

    def test_the_cache_home_is_set_before_the_preload(self) -> None:
        """`ENV` 가 뒤에 오면 **빌드는 다른 자리**에 받아 둔다 — 런타임은 빈 자리를 본다."""
        match = HF_HOME.search(read(DOCKERFILE))
        assert match is not None
        assert match.start() < _preload().start(), "ENV HF_HOME 이 모델을 받는 줄보다 뒤에 있다"
