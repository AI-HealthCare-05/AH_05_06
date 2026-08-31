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

import ast
import inspect
import pathlib
from enum import Enum

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from app.core.api_errors import ApiError, ContractRoute
from app.main import app
from app.tests.routes import NON_CONTRACT_METHODS, api_routes, contract_methods

#: 오류 봉투 없이도 되는 라우터. `AuthError` 만 던지고, 그것은 전역 처리기가 받는다.
#: 여기 이름을 더하는 것은 **결정**이다 — 그 라우터에서 `ApiError` 를 쓰면 샌다.
ENVELOPE_EXEMPT_TAGS = frozenset(
    {
        "health",
        "auth",
        "guides",
        "patient-links",
        "patient-guides",
        "patient-checkins",
        "ocr",
        # `#113`(KEY-91) 이 붙일 자리. `app/services/patient_otp.py` 는
        # `AuthError` 만 던지므로 봉투가 없어도 전역 처리기가 받는다 — 실측했다.
        # 병합을 기다리지 않고 먼저 적어 두면, 그 PR 이 들어올 때 이 검사가
        # **새 라우터를 벗은 것으로 잘못 세지 않는다** (이희진 님 `#110` 리뷰).
        "patient-auth",
    }
)


def route_tags(route: object) -> set[str]:
    return set(getattr(route, "tags", []) or [])


def wears_envelope(route: object) -> bool:
    return isinstance(route, ContractRoute)


def naked_routes(source: FastAPI = app) -> list[str]:
    """봉투도 없고 예외도 아닌 라우트 — `ApiError` 가 raw 500 으로 샐 자리.

    본 검사와 아래 가짜 앱 검사가 **이 함수 하나**를 쓴다. 정책 함수만 맞고
    본 검사가 그것을 안 쓰면 아무 소용이 없기 때문이다.
    """
    return sorted(
        f"{sorted(contract_methods(route))} {route.path} [{sorted(route_tags(route))}]"
        for route in api_routes(source)
        if not wears_envelope(route) and not envelope_exempt(route)
    )


def envelope_exempt(route: object) -> bool:
    """**전부 예외일 때만 예외다** — 하나라도 걸치면 봉투를 입어야 한다.

    태그 교집합(`tags & ENVELOPE_EXEMPT_TAGS`)으로 재면 예외 태그 **하나만**
    붙어도 통째로 빠진다. `tags=["patient-auth", "visits"]` 같은 라우터가
    생기면 봉투 없이도 조용히 검사를 지나가고, 그 자리에서 `ApiError` 는
    raw 500 으로 샌다 (이희진 님 `#110` 리뷰, KEY-169).

    지금 태그가 둘인 라우터는 하나도 없다. **그래서 지금 정한다** — 생긴
    뒤에는 이미 새고 있는 상태에서 정하게 된다.

    태그가 아예 없는 라우트도 예외가 아니다. 「어느 라우터인지 모르겠으니
    봐 준다」는 가장 위험한 쪽으로 틀리는 판정이다.
    """
    tags = route_tags(route)
    return bool(tags) and tags <= ENVELOPE_EXEMPT_TAGS


def test_the_registry_is_not_empty() -> None:
    """**이 파일의 다른 검사가 조용히 통과하지 않게 한다.**

    앱을 못 불러오거나 접두사가 바뀌면 아래가 전부 빈 목록을 돌게 된다.
    """
    routes = list(api_routes())
    assert len(routes) >= 25, f"등록 라우트가 {len(routes)}개다 — 라우터를 못 읽고 있다"


def test_no_two_routes_claim_the_same_method_and_path() -> None:
    """같은 (메서드, 경로)를 둘이 등록하면 **먼저 등록된 쪽만 산다.**

    나중 것은 조용히 죽는다 — 호출은 200 인데 다른 코드가 도는 자리다.
    """
    seen: dict[tuple[str, str], str] = {}
    duplicates = []
    for route in api_routes():
        module = inspect.getmodule(route.endpoint)
        where = module.__name__ if module else "?"
        for method in sorted(contract_methods(route)):
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
        # 스탭이 확인을 마치고 의사에게 넘긴다 — 와이어프레임 S1-11 (KEY-234)
        "/api/v1/visits/{visit_id}/guide/submit": "app.apis.v1.guide_routers",
        # 승인을 거둔다 — 승인했는데 잘못된 것을 발견했을 때 (KEY-234)
        "/api/v1/visits/{visit_id}/guide/unapprove": "app.apis.v1.guide_routers",
        "/api/v1/visits/{visit_id}/guide/sections/{key}": "app.apis.v1.guide_routers",
        "/api/v1/visits/{visit_id}/guide/link": "app.apis.v1.patient_link_routers",
        "/api/v1/visits/{visit_id}/checkin": "app.apis.v1.patient_link_routers",
        # 이 진료에 무슨 일이 있었는지 — 와이어프레임 D1-6 (KEY-234)
        "/api/v1/visits/{visit_id}/timeline": "app.timeline.api",
        "/api/v1/visits/{visit_id}/ocr-job": "app.ocr.api",
        "/api/v1/visits/{visit_id}/ocr-jobs": "app.ocr.api",
        "/api/v1/front-desk/visits": "app.apis.v1.front_desk_routers",
        "/api/v1/front-desk/visits/{visit_id}/documents": "app.documents.api",
    }

    actual: dict[str, str] = {}
    for route in api_routes():
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
    naked = naked_routes()

    #: 지금은 **하나도 없다.** KEY-167 이 마지막 둘(`/users/me`)을 지웠다(`#109`).
    #:
    #: 그래도 「없어야 한다」가 아니라 「이만큼만 있다」로 적는다. 비어 있는
    #: 목록은 늘어나는 것만 잡지만, 목록으로 두면 나중에 봉투 없는 라우트를
    #: 일부러 허용할 때 **여기에 적고 사유를 남기는** 자리가 된다.
    known_naked: list[str] = []
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


def _probe_app(tags: list[str | Enum], *, envelope: bool, methods: list[str] | None = None) -> FastAPI:
    """그 태그 조합을 가진 라우트 하나짜리 **가짜 앱**.

    실제 라우터로만 규칙을 재면 「지금 없는 조합」은 영영 못 잰다. 태그가 둘인
    라우터는 지금 하나도 없고, 그래서 사각지대가 조용했다.
    """
    router = APIRouter(route_class=ContractRoute) if envelope else APIRouter()

    @router.api_route("/probe", methods=methods or ["GET"], tags=tags)
    async def _endpoint() -> dict[str, str]:  # pragma: no cover - 부르지 않는다
        return {}

    probe = FastAPI()
    probe.include_router(router, prefix="/api/v1")
    return probe


def _probe(tags: list[str | Enum], *, envelope: bool, methods: list[str] | None = None) -> APIRoute:
    return next(iter(api_routes(_probe_app(tags, envelope=envelope, methods=methods))))


class TestTheEnvelopeExemptionIsAllOrNothing:
    """예외 태그 **하나만** 걸쳐도 빠져나가지 않는가 — KEY-169.

    `#110` 리뷰에서 이희진 님이 짚은 자리다. 교집합으로 재면
    `tags=["patient-auth", "visits"]` 인 라우터가 봉투 없이도 통과한다.
    """

    def test_a_wholly_exempt_route_is_exempt(self) -> None:
        assert envelope_exempt(_probe(["health"], envelope=False))

    def test_a_route_with_one_exempt_tag_among_others_is_not_exempt(self) -> None:
        """**이것이 사각지대였다.**

        `patient-auth` 는 예외지만 `visits` 는 아니다. 섞이면 봉투가 필요하다.
        """
        mixed = _probe(["patient-auth", "visits"], envelope=False)

        assert not envelope_exempt(mixed), "예외 태그 하나로 통째로 빠져나갔다"
        assert not wears_envelope(mixed)

    def test_an_untagged_route_is_not_exempt(self) -> None:
        """모르면 봐 주는 것이 아니라 **봉투를 요구한다.**"""
        assert not envelope_exempt(_probe([], envelope=False))

    def test_the_check_itself_reports_a_mixed_tag_route(self) -> None:
        """정책이 **검사 결과로 이어지는지**까지 본다.

        `envelope_exempt()` 가 맞아도 본 검사가 그것을 안 쓰면 소용이 없다.
        그래서 본 검사가 부르는 `naked_routes()` 를 그대로 부른다.
        """
        mixed = _probe_app(["patient-auth", "visits"], envelope=False)

        assert naked_routes(mixed) == ["['GET'] /api/v1/probe [['patient-auth', 'visits']]"]

    def test_a_mixed_tag_route_with_the_envelope_is_fine(self) -> None:
        """섞였어도 **봉투를 입었으면 문제가 아니다.**

        정책이 태그를 트집 잡는 것이 아니라 「샐 자리인가」를 재는 것임을
        못 박는다. 이것까지 걸리면 규칙이 너무 넓은 것이다.
        """
        mixed = _probe_app(["patient-auth", "visits"], envelope=True)

        assert naked_routes(mixed) == []


class TestHeadAndOptionsAreNotContract:
    """HEAD·OPTIONS 제외가 **헛돌지 않는가** — KEY-169.

    돌연변이로 재 보니 `contract_methods()` 에서 제외를 걷어내도 아무 검사도
    죽지 않았다. 지금 앱의 라우트에는 HEAD·OPTIONS 가 **아예 안 붙기**
    때문이다 — FastAPI 의 `APIRoute` 는 Starlette 의 `Route` 와 달리 GET 에
    HEAD 를 자동으로 얹지 않는다. 실측했다: 등장하는 메서드는 GET·PATCH·POST뿐.

    그러니 이 제외는 지금 **방어일 뿐 아무것도 막고 있지 않다.** 그렇다고
    지우면, 나중에 `methods=[...]` 로 직접 얹는 라우트가 생겼을 때 계약 문서에
    없는 `HEAD /auth/me` 같은 것이 「구현된 엔드포인트」로 세어진다.

    남겨 두되 **재는 검사를 붙인다.** 안 재는 방어는 방어가 아니다.
    """

    def test_head_and_options_are_dropped(self) -> None:
        # 여기 리터럴은 **재는 기준이 아니라 만들어 넣는 입력값**이다.
        # `NON_CONTRACT_METHODS` 로 바꾸면 같은 상수로 만들고 같은 상수로 재게 되어
        # 무엇을 바꾸든 통과한다 — 검사가 자기 자신을 재는 자리가 된다.
        route = _probe(["health"], envelope=False, methods=["GET", "HEAD", "OPTIONS"])

        assert contract_methods(route) == {"GET"}

    def test_a_route_with_only_head_and_options_is_not_an_api_route(self) -> None:
        """계약이 없는 라우트는 **세지 않는다.**"""
        probe = _probe_app(["health"], envelope=False, methods=["HEAD", "OPTIONS"])

        assert list(api_routes(probe)) == []

    def test_the_live_app_has_no_head_or_options_today(self) -> None:
        """**지금은 하나도 없다** — 위 둘이 가상의 상황을 재고 있음을 못 박는다.

        생기는 날 이 검사가 죽고, 그때 제외가 진짜로 일하기 시작한 것이다.

        **이름값대로만 잰다.** 예전에는 메서드 구성 전체를 완전 일치로 박아
        뒀는데, 그러면 HEAD·OPTIONS 와 아무 상관 없는 새 동사에도 터진다.
        실제로 `#119`(KEY-92)가 저장소 최초의 `DELETE` 를 들고 오자 이 클래스
        안의 검사가 빨간불이 났다 — 로그아웃 엔드포인트를 더한 사람이
        「HEAD·OPTIONS 계약」 검사가 깨진 빌드를 받았다. 실패 메시지가 실제
        이유와 맞지 않으면 고치는 사람이 엉뚱한 데를 판다.

        그리고 그 리터럴 자체가 KEY-169 가 없애려던 것이다 — 「이 앱에 어떤
        메서드가 있는가」를 이 파일이 다시 적고 있었다. 기준은 `routes.py` 의
        `NON_CONTRACT_METHODS` 하나다.
        """
        live = {method for route in api_routes() for method in route.methods}

        leaked = live & NON_CONTRACT_METHODS
        assert not leaked, f"HEAD·OPTIONS 가 생겼다: {sorted(leaked)}"


#: 「같은 뜻」인지 재는 잣대. **정본에서 가져온다** — 여기 다시 적으면 이 검사
#: 자신이 기준을 두 곳에 적는 꼴이 된다. 실제로 처음엔 그렇게 썼다가 자기
#: 가드에 걸렸다. 잣대가 정본을 따라가므로 `TRACE` 가 늘어도 함께 움직인다.
_CRITERION_NAMES = NON_CONTRACT_METHODS


def _string_elements(node: ast.AST) -> frozenset[str]:
    """`{...}` · `[...]` · `(...)` 안의 문자열 상수들."""
    if not isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return frozenset()
    return frozenset(e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))


def _spells_out_the_criterion(node: ast.AST) -> bool:
    """이 마디가 **기준을 집합으로 적고 있는가.**

    리스트·튜플은 세지 않는다. 가짜 라우트를 만들 때 쓰는
    `methods=["GET", "HEAD", "OPTIONS"]` 는 재는 기준이 아니라 **입력값**이라
    일부러 남겨 둔 것이다.
    """
    if isinstance(node, ast.Set):
        return _string_elements(node) == _CRITERION_NAMES
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"set", "frozenset"}:
        return any(_string_elements(arg) == _CRITERION_NAMES for arg in node.args)
    return False


def _subtracts_them_apart(node: ast.AST) -> bool:
    """`x - {"HEAD"} - {"OPTIONS"}` 처럼 **나눠 빼는** 모양."""
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Sub):
        return False
    taken: set[str] = set()
    cur: ast.AST = node
    while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Sub):
        taken |= _string_elements(cur.right)
        cur = cur.left
    return _CRITERION_NAMES <= taken


def _files_that_spell_out_the_criterion(root: pathlib.Path) -> list[str]:
    """HEAD·OPTIONS 를 **집합으로 적은** 파일들.

    글자가 아니라 **뜻**으로 잰다. 정규식으로 찾으면 같은 뜻인데 모양이 다른
    것을 놓친다 — 실제로 KEY-169 직전 판에 홑따옴표로 적힌 리터럴이 하나 더
    있었고, 그 검사는 그것을 못 봤다.

    못 잡던 모양들:

        {'HEAD', 'OPTIONS'}          홑따옴표
        {"OPTIONS", "HEAD"}          순서 뒤집기
        set(["HEAD", "OPTIONS"])     생성자
        x - {"HEAD"} - {"OPTIONS"}   나눠 빼기

    AST 로 보면 넷 다 같은 뜻이라 한 판정에 걸린다. 반대로 **주석·독스트링·
    문자열 안의 글자는 안 걸린다** — 파싱하면 코드가 아니기 때문이다. 그래서
    이 설명에 {"HEAD", "OPTIONS"} 를 그대로 써도 된다. 정규식 판에서는 자기
    독스트링에 걸려 설명을 에둘러 써야 했다.
    """
    found = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if _spells_out_the_criterion(node) or _subtracts_them_apart(node):
                found.add(str(path.relative_to(root)))
                break
    return sorted(found)


def test_the_method_criterion_lives_in_exactly_one_place() -> None:
    """**기준을 한 곳에 둔다**는 이 일감의 요점을 스스로 지킨다 — KEY-169.

    처음 올린 판에서 이 파일 안에 리터럴이 하나 남아 있었다(이희진 님 `#117`
    리뷰). 값이 같아 통과하고 있어서 아무도 못 잡았다. 지금은 같지만 `TRACE`
    같은 것이 늘면 **그 검사만 조용히 옛 기준으로 남는다** — KEY-169 가 막으려던
    바로 그 재발이다.

    그래서 「고쳤다」로 끝내지 않고 **다시 생기면 죽게** 걸어 둔다. 판정은
    `_files_that_spell_out_the_criterion()` 이 AST 로 한다 — 글자로 재면
    `{'HEAD', 'OPTIONS'}` 같은 같은 뜻 다른 모양을 놓친다.
    """
    owners = _files_that_spell_out_the_criterion(pathlib.Path(__file__).resolve().parents[1])

    assert owners == ["routes.py"], (
        f"HEAD·OPTIONS 제외 기준이 두 곳이 됐다 — `contract_methods()` 를 써라.\n  지금 기준을 적고 있는 파일: {owners}"
    )
