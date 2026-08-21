"""보호 엔드포인트가 실제로 막히는가 — KEY-153.

이 저장소에는 이미 권한 검사가 여럿 있다. 다만 전부 **한 층 위에서** 잰다.

    app/tests/rbac/            `has_permission()` 순수 함수
    patient_visit_apis/        `get_clinical_actor` 를 갈아 끼운 뒤의 서비스
    ocr/test_ocr_api.py        `FakeOcrService` · 의존성 함수 직접 호출

`app/tests/rbac/test_rbac_guard.py` 가 스스로 남긴 말이 이 파일의 이유다.

    「엔드포인트에서 실제로 403이 나오는지는 엔드포인트가 생긴 뒤에 붙인다.」

엔드포인트는 생겼다. 그래서 여기서는 **아무것도 갈아 끼우지 않고** 라우트로
받은 토큰을 헤더에 실어 실제 응답 코드를 본다. `KEY-116` 이 그 차이를 보여
줬다 — 손으로 만든 토큰 위에서 초록불이 켜져 있는 동안 실제 앱의 OCR
엔드포인트 다섯은 전부 `401` 이었다.

재는 것은 넷이다.

    ① 토큰이 없으면 401
    ② 역할이 없으면 403 (관리자만 가진 계정은 진료 자료를 못 본다)
    ③ 남의 의원 자료는 404 — **없는 자료와 구별되지 않아야 한다**
    ④ 최초 로그인 상태로는 보호 API 를 못 쓴다

그리고 ⑤ **정상 경로가 그대로 열리는지**도 함께 잰다. 차단만 재면 전부 막는
구현이 만점을 받는다.
"""

from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.main import app
from app.tests.blocking.accounts import build_two_hospitals, client
from app.tests.fakes import FakeRedis

#: 진료 자료를 다루는 보호 엔드포인트. `{p}` `{v}` 는 그 의원의 환자·진료다.
CLINICAL_ROUTES: list[tuple[str, str, dict | None]] = [
    ("GET", "/api/v1/patients", None),
    ("GET", "/api/v1/patients/{p}", None),
    ("PATCH", "/api/v1/patients/{p}", {"name": "고친이름"}),
    ("GET", "/api/v1/patients/{p}/visits", None),
    ("GET", "/api/v1/visits/{v}", None),
    ("PATCH", "/api/v1/visits/{v}", {"visit_summary": "메모"}),
]

#: 자기 자신에 대한 것 — 최초 로그인 상태에서도 열려 있어야 한다.
SELF_SCOPED_ROUTES: list[tuple[str, str, dict | None]] = [
    ("GET", "/api/v1/auth/me", None),
]

#: OCR 다섯. `KEY-116` 때문에 오늘은 실제 토큰으로 부를 수 없다.
OCR_ROUTES: list[tuple[str, str, dict | None]] = [
    ("POST", "/api/v1/documents/1/ocr", {"visit_id": 1, "document_type": "EMR"}),
    ("GET", "/api/v1/ocr/jobs/synthetic-job", None),
    ("GET", "/api/v1/ocr/jobs/synthetic-job/result", None),
    ("GET", "/api/v1/ocr/jobs/synthetic-job/fields", None),
    ("PATCH", "/api/v1/ocr/fields/1", {"corrected_value": "1"}),
]


class BlockingTestCase(TestCase):
    """의원 둘 · 역할 셋 · 각 의원의 환자와 진료를 깔고 시작한다."""

    def setUp(self) -> None:
        super().setUp()
        app.dependency_overrides[get_redis] = lambda: FakeRedis()

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def call(self, method: str, template: str, fence, headers: dict | None, body: dict | None):
        path = template.format(p=fence.patient_id, v=fence.visit_id)
        kwargs: dict = {}
        if headers:
            kwargs["headers"] = headers
        if body is not None:
            kwargs["json"] = body
        async with client() as http:
            return await http.request(method, path, **kwargs)


class TestNoTokenIs401(BlockingTestCase):
    """토큰 없이 문을 밀면 열리지 않는다."""

    async def test_clinical_routes_reject_anonymous(self) -> None:
        world = await build_two_hospitals()
        for method, template, body in CLINICAL_ROUTES + SELF_SCOPED_ROUTES:
            response = await self.call(method, template, world["h1"], None, body)
            assert response.status_code == 401, f"{method} {template} 이 토큰 없이 {response.status_code} 를 냈다"


class TestAdminOnlyIsForbidden(BlockingTestCase):
    """`admin` 은 **권한**이지 역할이 아니다 (KEY-9).

    의원 운영은 할 수 있어도 진료 자료는 못 본다. 이 구분이 무너지면 원무
    담당자가 환자 기록을 열 수 있게 된다.
    """

    async def test_admin_only_cannot_touch_clinical_data(self) -> None:
        world = await build_two_hospitals()
        for method, template, body in CLINICAL_ROUTES:
            response = await self.call(method, template, world["h1"], world["admin1"].auth, body)
            assert response.status_code == 403, f"{method} {template} 이 관리자에게 {response.status_code} 로 열렸다"
            assert response.json()["code"] == "FORBIDDEN"

    async def test_admin_can_still_read_their_own_account(self) -> None:
        """관리자를 통째로 잠그는 것이 아니다 — 자기 자신은 볼 수 있어야 한다."""
        world = await build_two_hospitals()
        response = await self.call("GET", "/api/v1/auth/me", world["h1"], world["admin1"].auth, None)
        assert response.status_code == 200


class TestOtherHospitalIsHiddenAsNotFound(BlockingTestCase):
    """남의 의원 자료는 `403` 이 아니라 `404` 다.

    `docs/api/hospital.md` 5절 — 존재 여부 자체를 감춘다. `403` 을 주면
    「그 차트번호는 있긴 하다」가 새어 나간다.
    """

    async def test_other_hospital_clinical_data_is_not_found(self) -> None:
        world = await build_two_hospitals()
        for method, template, body in CLINICAL_ROUTES:
            if template == "/api/v1/patients":
                continue  # 목록은 자기 의원만 담으므로 아래에서 따로 잰다
            response = await self.call(method, template, world["h1"], world["staff2"].auth, body)
            assert response.status_code == 404, (
                f"{method} {template} 이 남의 의원 사람에게 {response.status_code} 를 냈다"
            )

    async def test_the_answer_is_the_same_as_for_data_that_never_existed(self) -> None:
        """**존재가 새지 않는지**가 요점이다 — 있는 것과 없는 것이 같아야 한다."""
        world = await build_two_hospitals()
        async with client() as http:
            theirs = await http.get(f"/api/v1/patients/{world['h1'].patient_id}", headers=world["staff2"].auth)
            nobody = await http.get("/api/v1/patients/999999", headers=world["staff2"].auth)

        assert theirs.status_code == nobody.status_code == 404
        assert theirs.json() == nobody.json(), "남의 의원 환자와 없는 환자의 응답이 다르다 — 그 차이가 존재를 알려 준다"

    async def test_the_list_never_carries_another_hospital(self) -> None:
        world = await build_two_hospitals()
        async with client() as http:
            response = await http.get("/api/v1/patients?limit=100", headers=world["staff2"].auth)
        assert response.status_code == 200
        charts = [item["hospital_patient_no"] for item in response.json()["items"]]
        assert "BLK-H1-001" not in charts, "목록에 남의 의원 환자가 실렸다"


class TestFirstLoginIsHeldAtTheDoor(BlockingTestCase):
    """비밀번호를 바꾸기 전에는 보호 API 를 못 쓴다.

    `docs/api/hospital.md` — 「최초 로그인 사용자는 `L-3` 완료 전 다른 보호
    화면에 접근할 수 없음」. 예외는 자기 자신에 대한 것뿐이다.
    """

    async def test_clinical_routes_are_closed_until_the_password_changes(self) -> None:
        world = await build_two_hospitals()
        for method, template, body in CLINICAL_ROUTES:
            response = await self.call(method, template, world["h1"], world["newbie1"].auth, body)
            assert response.status_code == 403, f"{method} {template} 이 최초 로그인 상태로 열렸다"
            assert response.json()["code"] == "password_change_required"

    async def test_self_scoped_routes_stay_open(self) -> None:
        """전부 막으면 비밀번호를 바꾸러 갈 수도 없다."""
        world = await build_two_hospitals()
        response = await self.call("GET", "/api/v1/auth/me", world["h1"], world["newbie1"].auth, None)
        assert response.status_code == 200


class TestTheAllowedPathStillOpens(BlockingTestCase):
    """차단만 재면 **전부 막는 구현이 만점**을 받는다.

    KEY-153 의 완료 조건 첫 줄이 「정상 경로를 깨지 않으면서」인 이유다.
    """

    async def test_staff_and_doctor_can_read_their_own_hospital(self) -> None:
        world = await build_two_hospitals()
        for who in ("staff1", "doctor1"):
            for method, template, body in CLINICAL_ROUTES:
                response = await self.call(method, template, world["h1"], world[who].auth, body)
                assert response.status_code == 200, (
                    f"{who} 가 {method} {template} 에서 {response.status_code} 를 받았다 — 정상 경로가 막혔다"
                )


class TestOcrIsReachableAndStillGuarded(BlockingTestCase):
    """OCR 다섯이 이제 실제로 열린다 — `KEY-116`(`#61`)이 병합됐다.

    이 자리는 얼마 전까지 `xfail(strict)` 이었다. `get_ocr_actor` 가 아무도 행을
    만들지 않는 `users` 표에 걸려 있어 **실제 직원 토큰으로 다섯이 전부 401** 이
    었기 때문이다. 검사는 초록인데 아무도 못 쓰는 상태였다.

    `#61` 이 들어오면서 통과로 바뀌었고 `strict` 가 그것을 알려 줬다. 이제
    「열린다」와 「그래도 막을 것은 막는다」를 함께 잰다.
    """

    async def test_a_valid_staff_token_gets_past_authentication(self) -> None:
        """401 이 아니어야 한다. 무엇을 받든 **인증은 지나야** 한다."""
        world = await build_two_hospitals()
        for method, template, body in OCR_ROUTES:
            response = await self.call(method, template, world["h1"], world["staff1"].auth, body)
            assert response.status_code != 401, (
                f"{method} {template} 이 실제 직원 토큰을 401 로 되돌린다 — 아무도 이 경로를 쓸 수 없다"
            )

    async def test_admin_only_cannot_touch_ocr(self) -> None:
        """`admin` 은 권한이지 역할이 아니다 — 권한표의 `OCR_UPLOAD` 가 막는다."""
        world = await build_two_hospitals()
        for method, template, body in OCR_ROUTES:
            response = await self.call(method, template, world["h1"], world["admin1"].auth, body)
            assert response.status_code == 403, f"{method} {template} 이 관리자에게 {response.status_code} 로 열렸다"

    async def test_first_login_is_held_at_the_door_here_too(self) -> None:
        """비밀번호를 바꾸기 전에는 OCR 도 못 쓴다."""
        world = await build_two_hospitals()
        for method, template, body in OCR_ROUTES:
            response = await self.call(method, template, world["h1"], world["newbie1"].auth, body)
            assert response.status_code == 403, f"{method} {template} 이 최초 로그인 상태로 열렸다"


class TestUploadIsGuarded(BlockingTestCase):
    """문서 업로드 — `KEY-54`(`#82`)가 develop 에 들어왔다.

    8/27 골격의 3단계다. 여기가 뚫리면 남의 의원 진료에 문서가 붙는다.
    """

    UPLOAD = "/api/v1/front-desk/visits/{v}/documents"

    async def upload(self, fence, headers):
        files = {"files": ("synthetic.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 64, "image/jpeg")}
        async with client() as http:
            return await http.post(
                self.UPLOAD.format(v=fence.visit_id),
                headers=headers or {},
                files=files,
            )

    async def test_no_token_is_401(self) -> None:
        world = await build_two_hospitals()
        assert (await self.upload(world["h1"], None)).status_code == 401

    async def test_admin_only_is_forbidden(self) -> None:
        world = await build_two_hospitals()
        assert (await self.upload(world["h1"], world["admin1"].auth)).status_code == 403

    async def test_first_login_is_held_at_the_door(self) -> None:
        world = await build_two_hospitals()
        response = await self.upload(world["h1"], world["newbie1"].auth)
        assert response.status_code == 403
        assert response.json()["code"] == "password_change_required"

    async def test_other_hospital_visit_is_not_found(self) -> None:
        """**남의 의원 진료에 문서를 붙일 수 없다.**

        `#82` 리뷰에서 이 차단을 지우는 돌연변이를 심어도 그쪽 검사 8개가 전부
        통과하는 것을 확인했다 — 구현은 맞는데 지켜 줄 것이 없었다. 여기서 잰다.
        """
        world = await build_two_hospitals()
        response = await self.upload(world["h1"], world["staff2"].auth)
        assert response.status_code == 404, "남의 의원 진료에 문서가 붙었다"

    async def test_staff_and_doctor_can_upload_to_their_own_hospital(self) -> None:
        """차단만 재면 전부 막는 구현이 만점을 받는다."""
        world = await build_two_hospitals()
        for who in ("staff1", "doctor1"):
            response = await self.upload(world["h1"], world[who].auth)
            assert response.status_code == 201, f"{who} 가 자기 의원 진료에 못 올린다 — {response.status_code}"


class TestOcrStillRejectsAnonymous(BlockingTestCase):
    async def test_it_at_least_rejects_anonymous_callers(self) -> None:
        """막혀 있는 동안에도 이것만은 참이어야 한다."""
        world = await build_two_hospitals()
        for method, template, body in OCR_ROUTES:
            response = await self.call(method, template, world["h1"], None, body)
            assert response.status_code == 401
