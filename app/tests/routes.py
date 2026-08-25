"""등록된 라우트를 **한 가지 기준으로** 훑는다 — KEY-169.

두 검사가 같은 일을 따로 하고 있었다.

    app/tests/routing/test_route_ownership.py::_api_routes()
    app/tests/auth_apis/test_auth_contract.py::implemented_endpoints()

둘 다 「`/api/v1` 로 시작하는가」와 「HEAD·OPTIONS 는 뺀다」를 각자 적었다.
한쪽만 고치면 두 검사가 **다른 세상을 보게 된다** — 그때 한쪽은 통과하고
한쪽은 실패하는데, 무엇이 옳은지는 아무 데도 안 적혀 있다.

기준을 여기 한 곳에만 둔다.
"""

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.main import app

#: 이 저장소의 API 는 전부 이 아래에 산다. 접두사가 바뀌면 **여기만** 고친다.
API_PREFIX = "/api/v1"

#: 계약이 아닌 메서드. FastAPI 가 자동으로 붙이는 것이라 문서에도 없고
#: 인증도 안 걸린다. 이것만 있는 라우트는 「구현된 엔드포인트」가 아니다.
NON_CONTRACT_METHODS = frozenset({"HEAD", "OPTIONS"})


def contract_methods(route: object) -> set[str]:
    """그 라우트가 실제로 약속하는 메서드.

    `getattr` 로 받는 것은 `app.routes` 에 `APIRoute` 가 아닌 것도 섞이기
    때문이다(`Mount`, 정적 파일 등). 그것들은 빈 집합이 되어 걸러진다.
    """
    return set(getattr(route, "methods", None) or ()) - NON_CONTRACT_METHODS


def api_routes(source: FastAPI = app, prefix: str = API_PREFIX) -> Iterator[APIRoute]:
    """`prefix` 아래 등록된 API 라우트.

    `source` 를 받는 것은 **가짜 앱으로 판정 규칙 자체를 검사**할 수 있게
    하려는 것이다. 규칙을 실제 라우터로만 재면, 지금 그런 라우터가 없는
    경우(예: 태그가 둘인 라우트)를 영영 못 잰다.
    """
    for route in source.routes:
        path = getattr(route, "path", "")
        if not path.startswith(prefix):
            continue
        if not contract_methods(route):
            continue
        yield route  # type: ignore[misc]


def method_path_pairs(source: FastAPI = app, prefix: str = API_PREFIX) -> set[tuple[str, str]]:
    """`{("GET", "/api/v1/auth/me"), …}` — 계약 문서와 맞대 보기 좋은 모양."""
    return {(method, route.path) for route in api_routes(source, prefix) for method in contract_methods(route)}
