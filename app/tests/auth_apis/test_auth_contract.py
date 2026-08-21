"""계약 문서와 구현이 갈리지 않는지 본다 — KEY-73 ⑤.

②③④ 는 「이 규칙이 지켜지는가」를 본다. 여기는 다른 것을 본다 —
**문서가 바뀌었는데 코드가 안 바뀐 것**, 그리고 그 반대.

계약은 사람이 읽는 문서(`docs/api/hospital.md`)이고 구현은 코드다. 둘이 갈리면
한동안 아무도 모른다. 로그인 화면(`#14`)도, 목업(`frontend/js/api.js`)도 이
문서를 근거로 만들었기 때문에, 문서가 근거로서 살아 있는지 검사가 지켜야 한다.

`KEY-30` 의 매핑표 검사(`app/tests/fixtures/`)와 같은 자리다.
"""

import re
from pathlib import Path
from typing import Any

from tortoise.contrib.test import TestCase

from app.core import auth_errors
from app.core.auth_errors import (
    ACCOUNT_LOCKED,
    INVALID_CREDENTIALS,
    INVALID_REQUEST,
    PASSWORD_CHANGE_REQUIRED,
    TOKEN_EXPIRED,
)
from app.main import app
from app.services.login_attempts import LOCK_SECONDS, MAX_FAILURES
from app.services.session_store import IDLE_SECONDS

CONTRACT = Path(__file__).parents[3] / "docs" / "api" / "hospital.md"


def contract_text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def auth_contract_text() -> str:
    """통합 문서에서 직원 인증 계약 절만 읽는다."""
    text = contract_text()
    return text.split("## 2. 직원 인증", 1)[1].split("## 3. 환자·진료", 1)[0]


def documented_endpoints() -> set[tuple[str, str]]:
    """4절의 엔드포인트 표를 그대로 읽는다.

    `| **`PATCH`** | `/api/v1/auth/password` |` 처럼 굵게 쓴 줄이 섞여 있어
    별표는 걷어내고 본다.
    """
    rows = re.findall(
        r"^\|\s*\**`(GET|POST|PATCH|PUT|DELETE)`\**\s*\|\s*`(/api/v1/auth/[a-z/]+)`\s*\|",
        contract_text(),
        re.MULTILINE,
    )
    return {(method, path) for method, path in rows}


def implemented_endpoints() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/auth"):
            continue
        methods: set[str] = getattr(route, "methods", set())
        for method in methods - {"HEAD", "OPTIONS"}:
            found.add((method, path))
    return found


# 계약 밖이지만 아직 살아 있는 것들. **지금은 비어 있다.**
#
# `GET /auth/token/refresh` 는 세션을 안 보고 액세스 토큰을 찍어 줘서 지웠고,
# `POST /auth/signup` 은 로그인할 수 없는 계정을 만들어서 지웠다.
# 비워 둔 채로 두면 「계약에 없는 인증 경로」가 조용히 늘어나는 것을 막는다.
KNOWN_LEGACY: set[tuple[str, str]] = set()


class TestEndpointsMatchTheDocument(TestCase):
    async def test_document_lists_five(self) -> None:
        """문서에서 하나가 빠지면 여기서 먼저 걸린다."""
        assert len(documented_endpoints()) == 5

    async def test_every_documented_endpoint_exists(self) -> None:
        missing = documented_endpoints() - implemented_endpoints()

        assert not missing, f"계약에 있는데 구현에 없다: {sorted(missing)}"

    async def test_no_undocumented_auth_endpoint(self) -> None:
        """계약에 없는 인증 경로가 조용히 늘어나지 않게 한다."""
        extra = implemented_endpoints() - documented_endpoints() - KNOWN_LEGACY

        assert not extra, f"계약에 없는데 구현에 있다: {sorted(extra)}"

    async def test_legacy_is_still_only_what_we_knew_about(self) -> None:
        """A1-2 가 signup 을 정리하면 이 검사가 먼저 알려 준다."""
        leftover = implemented_endpoints() & KNOWN_LEGACY

        assert leftover == KNOWN_LEGACY, f"legacy 목록이 실제와 다르다: {sorted(leftover)}"


class TestErrorCodesMatchTheDocument(TestCase):
    def documented_codes(self) -> set[str]:
        """5절 규칙 표의 `401 invalid_credentials` 같은 칸에서 코드만 뽑는다."""
        return set(re.findall(r"`(?:4\d\d) ([A-Za-z_]+)`", auth_contract_text()))

    async def test_every_documented_code_is_defined(self) -> None:
        defined = {
            value
            for name, value in vars(auth_errors).items()
            if name.isupper() and isinstance(value, str) and not name.startswith("_")
        }
        missing = self.documented_codes() - defined

        assert not missing, f"문서에 있는데 코드에 없다: {sorted(missing)}"

    async def test_the_four_that_carry_meaning_are_there(self) -> None:
        """이 넷은 화면 문구가 서로 다르다 — 하나로 뭉치면 화면이 정하지 못한다."""
        assert self.documented_codes() >= {
            INVALID_CREDENTIALS,
            TOKEN_EXPIRED,
            ACCOUNT_LOCKED,
            PASSWORD_CHANGE_REQUIRED,
        }

    async def test_wrong_credentials_and_expired_session_differ(self) -> None:
        """둘 다 401 이지만 사용자가 해야 할 일이 다르다 —
        다시 입력할 것인가, 다시 로그인할 것인가."""
        assert INVALID_CREDENTIALS != TOKEN_EXPIRED


class TestNumbersMatchTheDocument(TestCase):
    async def test_lockout_threshold(self) -> None:
        """「5회 초과」가 문서에 적힌 값이다."""
        written = re.search(r"(\d+)회 초과", contract_text())

        assert written is not None
        assert int(written.group(1)) == MAX_FAILURES

    async def test_lock_window(self) -> None:
        """`Retry-After: 600` 이 표준 헤더로 그대로 나간다."""
        written = re.search(r"Retry-After: (\d+)", contract_text())

        assert written is not None
        assert int(written.group(1)) == LOCK_SECONDS

    async def test_idle_window(self) -> None:
        """「유휴 30분」 — 직원과 환자가 같은 기준을 쓴다."""
        written = re.search(r"유휴 (\d+)분", contract_text())

        assert written is not None
        assert int(written.group(1)) * 60 == IDLE_SECONDS


class TestOpenApiShowsTheContract(TestCase):
    """완료 조건 — 「OpenAPI 에서 위 5개 엔드포인트의 DTO·오류 응답 예시 확인 가능」."""

    def schema(self) -> dict[str, Any]:
        return app.openapi()

    async def test_five_endpoints_are_published(self) -> None:
        paths = self.schema()["paths"]

        for method, path in documented_endpoints():
            assert path in paths, path
            assert method.lower() in paths[path], f"{method} {path}"

    async def test_login_shows_the_request_shape(self) -> None:
        """`email` 이 아니라 `login_id` 로 받는다는 것이 문서에서 읽혀야 한다."""
        components = self.schema()["components"]["schemas"]
        fields = components["StaffLoginRequest"]["properties"]

        assert set(fields) == {"login_id", "password", "remember"}
        assert "email" not in fields

    async def test_me_shows_what_the_screen_branches_on(self) -> None:
        fields = self.schema()["components"]["schemas"]["StaffMeResponse"]["properties"]

        assert {"roles", "must_change_password", "clinic_name"} <= set(fields)

    async def test_password_change_makes_current_optional(self) -> None:
        """최초 로그인은 `new_password` 만 보낸다 — 필수로 걸면 그 경로가 막힌다."""
        schema = self.schema()["components"]["schemas"]["PasswordChangeRequest"]

        assert schema.get("required") == ["new_password"]

    def _example_code(self, path: str, method: str, status_code: str) -> str:
        responses = self.schema()["paths"][path][method]["responses"]
        return responses[status_code]["content"]["application/json"]["example"]["code"]

    async def test_login_shows_error_examples(self) -> None:
        """DTO 만으로는 「몇 번 틀리면 잠기는지」가 안 보인다 — 오류도 계약이다."""
        assert self._example_code("/api/v1/auth/login", "post", "401") == INVALID_CREDENTIALS
        assert self._example_code("/api/v1/auth/login", "post", "429") == ACCOUNT_LOCKED

    async def test_protected_endpoints_show_token_expired(self) -> None:
        for method, path in [
            ("post", "/api/v1/auth/refresh"),
            ("post", "/api/v1/auth/logout"),
            ("get", "/api/v1/auth/me"),
            ("patch", "/api/v1/auth/password"),
        ]:
            assert self._example_code(path, method, "401") == TOKEN_EXPIRED, f"{method} {path}"

    async def test_password_change_shows_validation_error_example(self) -> None:
        assert self._example_code("/api/v1/auth/password", "patch", "422") == INVALID_REQUEST
