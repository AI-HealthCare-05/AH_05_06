"""라우트 소유권과 오류 봉투가 어긋나지 않는가 — KEY-164.

`#95`(KEY-133) 리뷰에서 「`/visits/{id}/ocr-job` 의 공개 경로는 visit 인데
구현은 `app/ocr/api.py` 에 있다」가 확인됐다. 조사해 보니 그건 **오류가 아니라
이 저장소의 규칙**이었다 — 아래 `test_a_sub_resource_owns_its_own_routes` 가
그 규칙을 적어 둔 자리다.

대신 **아무도 강제하지 않는 규약**이 하나 나왔다. 오류 봉투가 라우터마다
opt-in 이라(`route_class=ContractRoute`), 봉투 없는 라우터에 `ApiError` 를
던지는 의존성을 붙이면 **그 오류가 raw 500 으로 샌다.** 지금은 짝이 맞지만
맞춰 주는 것이 아무것도 없다.
"""

import inspect

from app.core.api_errors import ApiError, ContractRoute
from app.main import app

#: 오류 봉투 없이도 되는 라우터. `AuthError` 만 던지고, 그것은 전역 처리기가 받는다.
#: 여기 이름을 더하는 것은 **결정**이다 — 그 라우터에서 `ApiError` 를 쓰면 샌다.
ENVELOPE_EXEMPT_TAGS = frozenset(
    {"health", "auth", "guides", "patient-links", "patient-guides", "patient-checkins", "ocr"}
)


def _api_routes():
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/v1") and getattr(route, "methods", None):
            yield route


def test_the_registry_is_not_empty() -> None:
    """**이 파일의 다른 검사가 조용히 통과하지 않게 한다.**

    앱을 못 불러오거나 접두사가 바뀌면 아래가 전부 빈 목록을 돌게 된다.
    """
    routes = list(_api_routes())
    assert len(routes) >= 25, f"등록 라우트가 {len(routes)}개다 — 라우터를 못 읽고 있다"


def test_no_two_routes_claim_the_same_method_and_path() -> None:
    """같은 (메서드, 경로)를 둘이 등록하면 **먼저 등록된 쪽만 산다.**

    나중 것은 조용히 죽는다 — 호출은 200 인데 다른 코드가 도는 자리다.
    """
    seen: dict[tuple[str, str], str] = {}
    duplicates = []
    for route in _api_routes():
        module = inspect.getmodule(route.endpoint)
        where = module.__name__ if module else "?"
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            key = (method, route.path)
            if key in seen:
                duplicates.append(f"{method} {route.path} — {seen[key]} · {where}")
            seen[key] = where
    assert not duplicates, "같은 경로를 둘이 등록했다:\n  " + "\n  ".join(duplicates)


def test_a_sub_resource_owns_its_own_routes() -> None:
    """**경로가 아니라 하위 자원이 소유를 정한다** — 이 저장소의 규칙.

    `/visits/**` 는 지금 여섯 모듈에 흩어져 있는데, 흩어진 것이 아니라
    **자원별로 갈린 것**이다.

        /visits/{id}                   진료 그 자체    apis.v1.visit_routers
        /visits/{id}/guide/**          안내문          apis.v1.guide_routers
        /visits/{id}/guide/link        환자 링크       apis.v1.patient_link_routers
        /visits/{id}/ocr-job(s)        판독            ocr.api
        /front-desk/visits/{id}/documents  문서        documents.api

    그래서 판정 기준은 **URL 앞부분이 아니라 「무엇에 대한 것인가」** 이고,
    파일은 그 자원의 서비스가 사는 곳에 둔다. `app/ocr/api.py` 의 현재 배치는
    이 규칙에 맞다 — 옮길 이유가 없다.

    이 검사는 그 규칙을 **표로 못 박는다.** 새 `/visits` 하위 경로가 아무
    모듈에나 생기면 여기서 걸린다.
    """
    owner_of = {
        "/api/v1/visits/{visit_id}": "app.apis.v1.visit_routers",
        "/api/v1/patients/{patient_id}/visits": "app.apis.v1.visit_routers",
        "/api/v1/visits/{visit_id}/guide": "app.apis.v1.guide_routers",
        "/api/v1/visits/{visit_id}/guide/approve": "app.apis.v1.guide_routers",
        "/api/v1/visits/{visit_id}/guide/generate": "app.apis.v1.guide_routers",
        "/api/v1/visits/{visit_id}/guide/return": "app.apis.v1.guide_routers",
        "/api/v1/visits/{visit_id}/guide/sections/{key}": "app.apis.v1.guide_routers",
        "/api/v1/visits/{visit_id}/guide/link": "app.apis.v1.patient_link_routers",
        "/api/v1/visits/{visit_id}/checkin": "app.apis.v1.patient_link_routers",
        "/api/v1/visits/{visit_id}/ocr-job": "app.ocr.api",
        "/api/v1/visits/{visit_id}/ocr-jobs": "app.ocr.api",
        "/api/v1/front-desk/visits": "app.apis.v1.front_desk_routers",
        "/api/v1/front-desk/visits/{visit_id}/documents": "app.documents.api",
    }

    actual: dict[str, str] = {}
    for route in _api_routes():
        if "/visits" not in route.path:
            continue
        module = inspect.getmodule(route.endpoint)
        actual[route.path] = module.__name__ if module else "?"

    assert actual == owner_of, (
        "`/visits` 하위 경로의 소유가 바뀌었다. 자원이 늘었으면 위 표에 함께 적는다.\n"
        f"  지금: {sorted(actual.items())}\n"
        f"  적힌 것: {sorted(owner_of.items())}"
    )


def test_every_router_that_can_raise_api_error_wears_the_envelope() -> None:
    """`ApiError` 를 던지는 의존성이 걸린 라우트는 **봉투를 입어야 한다.**

    오류 봉투는 라우터마다 opt-in 이다(`route_class=ContractRoute`). 봉투가
    없으면 `ApiError` 는 아무도 안 받아 **raw 500** 으로 나간다 — 화면은
    「불러오지 못했습니다」만 말하고, 어떤 코드였는지는 로그를 파야 안다.

    지금은 짝이 맞다. 맞춰 주는 것이 아무것도 없어서 이 검사를 둔다.
    """
    naked = []
    for route in _api_routes():
        if isinstance(route, ContractRoute):
            continue
        tags = set(getattr(route, "tags", []) or [])
        if tags & ENVELOPE_EXEMPT_TAGS:
            continue
        naked.append(f"{sorted(route.methods - {'HEAD', 'OPTIONS'})} {route.path} [{sorted(tags)}]")

    #: 지금 벗고 있는 것 — **KEY-167 이 지우는 중이다**(`#109`).
    #:
    #: 「없어야 한다」가 아니라 「이만큼만 있다」로 적는다. 늘면 새 구멍이고,
    #: 줄면 KEY-167 이 병합된 것이라 이 목록을 비울 때다 — **양쪽으로 잡는다.**
    known_naked = [
        "['GET'] /api/v1/users/me [['users']]",
        "['PATCH'] /api/v1/users/me [['users']]",
    ]
    assert sorted(naked) == sorted(known_naked), (
        "봉투(`ContractRoute`) 없이 등록된 라우트 목록이 바뀌었다.\n"
        f"  지금: {sorted(naked)}\n"
        f"  적힌 것: {sorted(known_naked)}\n"
        "  늘었으면 `ApiError` 가 raw 500 으로 새는 자리다. 줄었으면 목록을 줄인다."
    )


def test_the_two_error_types_still_disagree_on_argument_order() -> None:
    """**같은 이름, 반대 순서.** 알고 있으라고 남기는 검사다.

        app.core.api_errors.ApiError(status_code, code, message)
        app.core.auth_errors.AuthError(code, status_code, message)

    그런데 `guides.py` · `patient_links.py` · `checkins.py` 는
    `from app.core.auth_errors import AuthError as ApiError` 로 **이름을 바꿔
    쓴다.** 그래서 같은 저장소에서 `ApiError(...)` 가 두 뜻을 갖는다.

    서비스 사이로 코드를 옮기면 상태와 코드가 조용히 뒤바뀐다. 고치는 것은
    이 일감 범위 밖이라(공통 오류 계약 변경) **사실만 못 박는다** — 둘이
    같아지는 날 이 검사가 죽고, 그때 별칭을 걷으면 된다.
    """
    from app.core.auth_errors import AuthError

    api_args = list(inspect.signature(ApiError.__init__).parameters)[1:4]
    auth_args = list(inspect.signature(AuthError.__init__).parameters)[1:4]

    assert api_args == ["status_code", "code", "message"], f"api_errors 쪽이 바뀌었다: {api_args}"
    assert auth_args == ["code", "status_code", "message"], f"auth_errors 쪽이 바뀌었다: {auth_args}"
    assert api_args != auth_args, "둘이 같아졌다 — `AuthError as ApiError` 별칭을 걷을 때다"
