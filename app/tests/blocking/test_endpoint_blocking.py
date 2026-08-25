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

from collections.abc import Callable

from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.main import app
from app.models.visits import GuideDocument, GuideStatus, PatientGuideLink
from app.tests.blocking.accounts import (
    build_two_hospitals,
    client,
    make_guide,
    make_ocr,
    make_patient_and_visit,
    make_staff_in,
    new_patient_body,
    new_visit_body,
)
from app.tests.fakes import FakeRedis

#: 진료 자료를 다루는 보호 엔드포인트. `{p}` `{v}` 는 그 의원의 환자·진료다.
#:
#: **여기 없는 경로는 아무도 안 잰다.** 이 목록의 값은 「덮은 것」이 아니라
#: 「덮었다고 믿는 것」이라, 빠지면 조용하다. 실제로 셋이 빠져 있었다.
#:
#:   `GET /visits/{v}/guide`     KEY-153 QA 에서 발견. 역할 검사를 통째로
#:                               무력화해도 40 개가 전부 통과했다
#:   `POST /patients`            `#115`(KEY-52) 리뷰에서 발견 — 읽기·수정은
#:   `POST /patients/{p}/visits` 있는데 **생성이 하나도 없었다**
#:
#: 셋 다 구멍이 아니라 **매트릭스가 그 자리를 모르던 것**이었다. 새 보호
#: 경로를 만들면 여기 한 줄을 함께 더한다.
#: 생성 경로에 보낼 본문은 부를 때마다 달라야 한다. 그 모양은 합성 환자·진료를
#: 아는 `accounts.py` 가 갖는다 — 이 파일은 「무엇을 어디에 보내는가」만 적는다.
Payload = dict | Callable[[], dict] | None

CLINICAL_ROUTES: list[tuple[str, str, Payload]] = [
    ("GET", "/api/v1/patients", None),
    ("GET", "/api/v1/patients/{p}", None),
    ("PATCH", "/api/v1/patients/{p}", {"name": "고친이름"}),
    ("GET", "/api/v1/patients/{p}/visits", None),
    ("GET", "/api/v1/visits/{v}", None),
    ("PATCH", "/api/v1/visits/{v}", {"visit_summary": "메모"}),
    ("GET", "/api/v1/visits/{v}/guide", None),
    ("POST", "/api/v1/patients", new_patient_body),
    ("POST", "/api/v1/patients/{p}/visits", new_visit_body),
]

#: 자기 자신에 대한 것 — 최초 로그인 상태에서도 열려 있어야 한다.
SELF_SCOPED_ROUTES: list[tuple[str, str, Payload]] = [
    ("GET", "/api/v1/auth/me", None),
]

#: OCR 다섯. `KEY-116` 때문에 오늘은 실제 토큰으로 부를 수 없다.
OCR_ROUTES: list[tuple[str, str, Payload]] = [
    ("GET", "/api/v1/ocr/jobs/synthetic-job", None),
    ("GET", "/api/v1/ocr/jobs/synthetic-job/result", None),
    ("GET", "/api/v1/ocr/jobs/synthetic-job/fields", None),
    # `base_version` 을 반드시 싣는다. 빠지면 **422 로 먼저 튕겨 인가에 닿지도
    # 못한다** — 권한이 깨져도 이 줄로는 못 잡는다 (이희진 님 `#87` 리뷰).
    ("PATCH", "/api/v1/ocr/fields/1", {"corrected_value": "1", "base_version": 1}),
    # `POST /documents/{id}/ocr` 는 여기 없다. 업로드가 판독을 함께 시작하므로
    # 그 수동 경로는 레거시이고 `#112`(KEY-159)가 지운다. 지워질 경로로 인가를
    # 재면 그 PR 이 이 검사를 만나 죽는다 (이희진 님 `#87` 리뷰).
]


class BlockingTestCase(TestCase):
    """의원 둘 · 역할 셋 · 각 의원의 환자와 진료를 깔고 시작한다."""

    def setUp(self) -> None:
        super().setUp()
        app.dependency_overrides[get_redis] = lambda: FakeRedis()

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def call(self, method: str, template: str, fence, headers: dict | None, body: "Payload"):
        path = template.format(p=fence.patient_id, v=fence.visit_id)
        kwargs: dict = {}
        if headers:
            kwargs["headers"] = headers
        payload = body() if callable(body) else body
        if payload is not None:
            kwargs["json"] = payload
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
        # **주인 것이 실제로 있어야 격리를 잰다.** 안내문을 안 심으면
        # `GET /visits/{v}/guide` 의 404 가 「남의 것이라 막혔다」인지 「애초에
        # 없다」인지 갈리지 않는다. 병원 필터가 통째로 빠져도 그대로 통과한다 —
        # 실측했더니 40 개가 전부 초록이었다 (이희진 님 `#122` 리뷰).
        #
        # `accounts.py` 의 `OcrFixture` 가 적어 둔 원칙이 이것이다:
        # 「같은 식별자로 주인은 열고 남은 못 여는 것을 보여야 격리다.」
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.APPROVAL_PENDING)
        for method, template, body in CLINICAL_ROUTES:
            if template == "/api/v1/patients":
                # **경로에 남의 것을 가리킬 자리가 없는 둘**이다. 템플릿 문자열이
                # 같아 GET·POST 가 함께 걸린다.
                #   GET  목록은 자기 의원만 담는다 — 아래에서 따로 잰다
                #   POST 병원이 본문이 아니라 actor 에서만 정해진다
                #        (`PatientCreateRequest` 에 `hospital_id` 가 없다)
                # 그래서 「남의 의원 자원」 케이스가 성립하지 않는다.
                # 같은 템플릿을 쓰는 라우트가 또 생기면 **여기 이유를 함께 적는다**
                # (이희진 님 `#122` 리뷰).
                continue
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

    async def test_the_list_carries_mine_and_only_mine(self) -> None:
        """**부재만 재면 빈 목록도 통과한다.**

        예전에는 「남의 의원 환자가 없다」만 봤다. 목록이 통째로 비어도, 필터가
        모든 것을 걸러내도 초록이었다 — 격리가 아니라 고장도 통과한다
        (이희진 님 `#87` 리뷰).

        자기 것이 **있고** 남의 것이 **없는** 것을 함께 잰다.
        """
        world = await build_two_hospitals()
        async with client() as http:
            response = await http.get("/api/v1/patients?limit=100", headers=world["staff2"].auth)

        assert response.status_code == 200
        charts = [item["hospital_patient_no"] for item in response.json()["items"]]
        assert "BLK-H2-001" in charts, f"자기 의원 환자가 목록에 없다 — 목록이 고장났다: {charts}"
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
        # `GET /visits/{v}/guide` 는 **안내문이 있어야** 200 이다. 공용 픽스처는
        # 안내문을 안 심으므로 여기서만 한 건 깐다 — 차단 쪽 검사는 안내문
        # 존재와 무관하게 돌지만(역할 검사가 먼저다) 정상 경로는 아니다.
        # `TestOnlyDoctorsDecideOnGuides` 가 이미 쓰는 방식이다 (이희진 님 KEY-153 답).
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.APPROVAL_PENDING)
        for who in ("staff1", "doctor1"):
            for method, template, body in CLINICAL_ROUTES:
                response = await self.call(method, template, world["h1"], world[who].auth, body)
                # **막혔는가**만 잰다. 성공 코드가 `200` 인지 `201` 인지는 계약
                # 검사의 몫이다.
                #
                # 예전에는 `201 if method == "POST"` 로 갈랐는데, 그건 「POST 면
                # 생성」이라는 가정이다. 200 을 주는 액션성 POST(`…/actions/lock`
                # 같은)가 목록에 들어오면 엉뚱한 기댓값을 재고, 실패 메시지가
                # 「정상 경로가 막혔다」라 **권한 회귀처럼 오해된다**
                # (이희진 님 `#122` 리뷰).
                assert 200 <= response.status_code < 300, (
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

    async def test_a_valid_staff_token_gets_past_authentication_and_authorisation(self) -> None:
        """인증**과 인가**를 함께 지난다.

        예전에는 `!= 401` 만 봤다. 그러면 **정상 직원의 OCR 권한이 깨져 403 이
        나와도 통과한다** — 인증만 지키고 인가는 놓치는 검사였다
        (유가은 님 `#87` 리뷰).

        지금은 401·403 을 **둘 다** 실패로 본다. 없는 식별자를 두드리므로
        정상 응답은 「못 찾음」 계열이고, 그 값만 허용한다.
        """
        world = await build_two_hospitals()
        for method, template, body in OCR_ROUTES:
            response = await self.call(method, template, world["h1"], world["staff1"].auth, body)
            assert response.status_code not in (401, 403), (
                f"{method} {template} 이 정상 직원에게 {response.status_code} 다 — "
                "인증이 막혔거나(401) 권한이 깨졌다(403)"
            )
            assert response.status_code in (404, 422), (
                f"{method} {template} 이 뜻밖의 {response.status_code} 를 냈다 — 없는 식별자이므로 404·422 여야 한다"
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


# ────────────────────────────────────────────────────────────
#  의사 외에는 승인하지 못한다 — KEY-153 범위
#
#  「의사 외 안내 승인을 차단」. 이것이 뚫리면 **의사가 보지 않은 글이 환자에게
#  간다** — 이 제품이 존재하는 이유가 무너지는 자리다(D1-5).
#
#  역할 검사가 안내문 조회보다 **앞**이라(`GuideService._require_doctor`),
#  안내문이 없어도 403 이 나와야 한다. 그것까지 함께 잰다.

GUIDE_DOCTOR_ONLY_ROUTES = [
    ("POST", "/api/v1/visits/{v}/guide/approve", {}),
    ("POST", "/api/v1/visits/{v}/guide/return", {"reason": "합성 반려 사유"}),
    ("PATCH", "/api/v1/visits/{v}/guide/sections/medication", {"body": "합성 수정 본문"}),
]


class TestOnlyDoctorsDecideOnGuides(BlockingTestCase):
    async def test_no_token_is_401(self) -> None:
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.APPROVAL_PENDING)
        for method, template, body in GUIDE_DOCTOR_ONLY_ROUTES:
            response = await self.call(method, template, world["h1"], None, body)
            assert response.status_code == 401, f"{method} {template} 이 토큰 없이 {response.status_code} 를 냈다"

    async def test_staff_cannot_approve_or_return(self) -> None:
        """접수 직원은 승인·반려·수정을 못 한다. **`staff` 는 의사가 아니다.**"""
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.APPROVAL_PENDING)
        for method, template, body in GUIDE_DOCTOR_ONLY_ROUTES:
            response = await self.call(method, template, world["h1"], world["staff1"].auth, body)
            assert response.status_code == 403, f"{method} {template} 이 접수 직원에게 {response.status_code} 로 열렸다"

    async def test_admin_only_cannot_approve(self) -> None:
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.APPROVAL_PENDING)
        for method, template, body in GUIDE_DOCTOR_ONLY_ROUTES:
            response = await self.call(method, template, world["h1"], world["admin1"].auth, body)
            assert response.status_code == 403, f"{method} {template} 이 관리자에게 {response.status_code} 로 열렸다"

    async def test_role_is_checked_before_the_guide_is_looked_up(self) -> None:
        """**안내문이 없어도 403 이다.**

        먼저 찾고 나중에 역할을 보면, 없는 진료에 404 를 주면서 「그 의원에
        그런 진료가 없다」를 권한 없는 사람에게 알려 준다.
        """
        world = await build_two_hospitals()  # 안내문을 심지 않는다
        for method, template, body in GUIDE_DOCTOR_ONLY_ROUTES:
            response = await self.call(method, template, world["h1"], world["staff1"].auth, body)
            assert response.status_code == 403, f"{method} {template} 이 역할보다 안내문을 먼저 봤다"

    async def test_another_hospitals_guide_is_not_found(self) -> None:
        """남의 의원 안내문은 **의사라도** 없는 것이다."""
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.APPROVAL_PENDING)
        doctor2 = await make_staff_in(world["h2"].hospital_id, "blk_doctor2", ["doctor"])
        for method, template, body in GUIDE_DOCTOR_ONLY_ROUTES:
            response = await self.call(method, template, world["h1"], doctor2.auth, body)
            assert response.status_code == 404, (
                f"{method} {template} 이 남의 의원 의사에게 {response.status_code} 를 냈다 — 존재가 샌다"
            )

    async def test_first_login_is_held_at_the_door(self) -> None:
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.APPROVAL_PENDING)
        newbie_doctor = await make_staff_in(
            world["h1"].hospital_id, "blk_newdoc1", ["doctor"], must_change_password=True
        )
        for method, template, body in GUIDE_DOCTOR_ONLY_ROUTES:
            response = await self.call(method, template, world["h1"], newbie_doctor.auth, body)
            assert response.status_code == 403, f"{method} {template} 이 최초 로그인 상태로 열렸다"

    async def test_the_doctor_of_that_hospital_can_approve(self) -> None:
        """**막는 것만 재면 전부 막아 둔 코드도 통과한다.** 열려야 하는 길을 함께 잰다."""
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.APPROVAL_PENDING)

        response = await self.call("POST", "/api/v1/visits/{v}/guide/approve", world["h1"], world["doctor1"].auth, {})
        assert response.status_code == 200, (
            f"그 의원 의사가 승인하지 못한다: {response.status_code} {response.text[:120]}"
        )


# ────────────────────────────────────────────────────────────
#  승인 전에는 환자에게 가지 않는다 — KEY-153 범위
#
#  「승인 전 환자 안내 조회를 차단」. 개발용 환자 링크(KEY-90 / `#99`)가
#  들어오면서 **직원 인증 없이 열리는 경로**가 처음 생겼다. 여기가 뚫리면
#  의사가 승인하지 않은 글이 환자 화면에 뜬다.

PATIENT_LINK_ISSUE = "/api/v1/visits/{v}/guide/link"


class TestUnapprovedGuidesNeverReachThePatient(BlockingTestCase):
    async def test_no_token_cannot_issue_a_link(self) -> None:
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.SCHEDULED_TO_SEND)
        response = await self.call("POST", PATIENT_LINK_ISSUE, world["h1"], None, {})
        assert response.status_code == 401

    async def test_admin_only_cannot_issue_a_link(self) -> None:
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.SCHEDULED_TO_SEND)
        response = await self.call("POST", PATIENT_LINK_ISSUE, world["h1"], world["admin1"].auth, {})
        assert response.status_code == 403

    async def test_another_hospital_cannot_issue_a_link(self) -> None:
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.SCHEDULED_TO_SEND)
        response = await self.call("POST", PATIENT_LINK_ISSUE, world["h1"], world["staff2"].auth, {})
        assert response.status_code == 404, "남의 의원 안내문에 링크가 발급됐거나 존재가 샜다"

    async def test_an_unapproved_guide_gets_no_link_at_all(self) -> None:
        """승인 전에는 **링크 자체가 생기지 않는다.**"""
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.APPROVAL_PENDING)

        response = await self.call("POST", PATIENT_LINK_ISSUE, world["h1"], world["staff1"].auth, {})
        assert response.status_code == 409
        assert response.json()["code"] == "GUIDE_NOT_APPROVED"
        assert await PatientGuideLink.all().count() == 0, "막았다면서 링크 행이 남았다"

    async def test_a_link_stops_working_when_the_guide_leaves_approval(self) -> None:
        """발급 뒤에 되돌려도 **그 순간부터 안 열린다.**

        승인이 취소된 글을 환자가 계속 볼 수 있으면, 되돌리는 동작 자체가
        환자에게는 아무 의미가 없다.
        """
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.SCHEDULED_TO_SEND)

        issued = await self.call("POST", PATIENT_LINK_ISSUE, world["h1"], world["staff1"].auth, {})
        assert issued.status_code == 201, issued.text[:200]
        path = issued.json()["path"]

        async with client() as http:
            opened = await http.get(path)
        assert opened.status_code == 200, "승인된 안내문이 환자 링크로 안 열린다"

        guide = await GuideDocument.get(visit_id=world["h1"].visit_id)
        guide.status = GuideStatus.APPROVAL_RETURNED
        await guide.save(update_fields=["status"])

        async with client() as http:
            after = await http.get(path)
        assert after.status_code == 404, f"되돌린 안내문이 환자 링크로 계속 열린다: {after.status_code}"
        assert "합성 복약 안내" not in after.text, "막았다면서 본문이 새어 나갔다"

    async def test_a_made_up_token_reveals_nothing(self) -> None:
        world = await build_two_hospitals()
        await make_guide(world["h1"].hospital_id, world["h1"].visit_id, GuideStatus.SCHEDULED_TO_SEND)

        async with client() as http:
            response = await http.get("/api/v1/guides/" + "z" * 43)
        assert response.status_code == 404
        assert "합성 복약 안내" not in response.text


class TestOcrIsIsolatedByHospital(BlockingTestCase):
    """OCR 도 병원으로 갈린다 — 유가은 님 · 이희진 님 `#87` 리뷰.

    두 분이 같은 곳을 짚으셨다. 위 `OCR_ROUTES` 는 `synthetic-job` · `fields/1`
    처럼 **없는 식별자**를 두드린다. 그래서 타 병원 직원이 `404` 를 받아도
    「격리됐다」가 아니라 「원래 없다」일 수 있다 — 격리가 실제로 깨져도 이
    묶음으로는 못 잡는다.

    그래서 **H1 에 진짜 판독 자료를 만들고, 같은 식별자로** 잰다.
    주인은 열고 남은 못 여는 것이 격리다.
    """

    async def world_with_ocr(self):
        world = await build_two_hospitals()
        fixture = await make_ocr(
            hospital_id=world["h1"].hospital_id,
            visit_id=world["h1"].visit_id,
            job_id="blk-h1-job",
            requested_by=1,
        )
        return world, fixture

    async def test_the_owning_hospital_can_read_its_own_job(self) -> None:
        """**주인은 열려야 한다.** 아래 404 가 격리 때문임을 이 검사가 보증한다."""
        world, fx = await self.world_with_ocr()
        async with client() as http:
            for path in (
                f"/api/v1/ocr/jobs/{fx.job_id}",
                f"/api/v1/ocr/jobs/{fx.job_id}/result",
                f"/api/v1/ocr/jobs/{fx.job_id}/fields",
            ):
                response = await http.get(path, headers=world["staff1"].auth)
                assert response.status_code == 200, (
                    f"{path} 이 주인에게 {response.status_code} 다 — 아래 격리 검사가 헛돈다"
                )

    async def test_another_hospital_cannot_read_the_same_job(self) -> None:
        """**같은 식별자**로 남의 의원 직원은 404 다."""
        world, fx = await self.world_with_ocr()
        async with client() as http:
            for path in (
                f"/api/v1/ocr/jobs/{fx.job_id}",
                f"/api/v1/ocr/jobs/{fx.job_id}/result",
                f"/api/v1/ocr/jobs/{fx.job_id}/fields",
            ):
                response = await http.get(path, headers=world["staff2"].auth)
                assert response.status_code == 404, (
                    f"{path} 이 남의 의원 직원에게 {response.status_code} 다 — 격리가 뚫렸거나 존재가 샌다"
                )

    async def test_another_hospital_cannot_touch_the_same_field(self) -> None:
        """읽기만이 아니라 **쓰기도** 갈린다."""
        world, fx = await self.world_with_ocr()
        async with client() as http:
            response = await http.patch(
                f"/api/v1/ocr/fields/{fx.field_id}",
                json={"corrected_value": "남의 의원이 고쳐 본다", "base_version": 1},
                headers=world["staff2"].auth,
            )
        assert response.status_code == 404, f"남의 의원이 필드를 고쳤거나 존재가 샜다: {response.status_code}"

    async def test_the_answer_is_the_same_as_for_a_job_that_never_existed(self) -> None:
        """있는 것을 감출 때와 없는 것을 말할 때가 **같아야** 한다.

        코드나 문구가 다르면 그 차이만으로 「그 의원에 그 작업이 있다」를
        알 수 있다.
        """
        world, fx = await self.world_with_ocr()
        async with client() as http:
            hidden = await http.get(f"/api/v1/ocr/jobs/{fx.job_id}", headers=world["staff2"].auth)
            absent = await http.get("/api/v1/ocr/jobs/blk-no-such-job", headers=world["staff2"].auth)

        assert hidden.status_code == absent.status_code == 404
        assert hidden.json() == absent.json(), (
            f"감출 때와 없을 때의 응답이 다르다 — 존재가 샌다\n  감춤: {hidden.text[:120]}\n  없음: {absent.text[:120]}"
        )


class TestDocumentsDoNotLeakAcrossVisits(BlockingTestCase):
    """문서가 **진료와 병원 양쪽으로** 갈리는가 — 이희진 님 `#87` 리뷰.

    한때 `POST /documents/{id}/ocr` 로 쟀는데, 업로드가 판독을 함께 시작하므로
    그 수동 경로는 레거시이고 `#112`(KEY-159)가 지운다. 지워질 경로로 격리를
    재면 그 PR 이 이 검사를 만나 죽는다.

    그래서 **업로드로 문서를 만들고 `GET /visits/{id}/ocr-jobs` 응답에서**
    잰다. 그 응답이 `document_id` 를 실어 주므로(`OcrJobByDocumentResponse`)
    무엇이 보이는지를 그대로 확인할 수 있다.

    이 목록 경로는 남의 것을 `404` 가 아니라 **`200 []`** 로 감춘다. 없는
    진료도 `200 []` 라 **감출 때와 없을 때가 구별되지 않는다** — 존재가 새지
    않는다는 뜻이라 그대로 둔다(아래에서 함께 잰다).
    """

    UPLOAD = "/api/v1/front-desk/visits/{v}/documents"
    JOBS = "/api/v1/visits/{v}/ocr-jobs"

    async def upload_to(self, visit_id: int, headers: dict) -> int:
        files = {"files": ("synthetic.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 64, "image/jpeg")}
        async with client() as http:
            response = await http.post(self.UPLOAD.format(v=visit_id), headers=headers, files=files)
        assert response.status_code == 201, f"업로드가 안 된다: {response.status_code} {response.text[:120]}"
        return response.json()["document_ids"][0]

    async def documents_seen(self, visit_id: int, headers: dict) -> tuple[int, list[int]]:
        async with client() as http:
            response = await http.get(self.JOBS.format(v=visit_id), headers=headers)
        if response.status_code != 200:
            return response.status_code, []
        return 200, [row["document_id"] for row in response.json()]

    async def test_the_owner_sees_the_document_they_uploaded(self) -> None:
        """**주인은 보여야 한다.** 아래 「안 보인다」들이 격리 때문임을 이것이 보증한다."""
        world = await build_two_hospitals()
        document_id = await self.upload_to(world["h1"].visit_id, world["staff1"].auth)

        status_code, seen = await self.documents_seen(world["h1"].visit_id, world["staff1"].auth)

        assert status_code == 200
        assert document_id in seen, f"올린 문서가 자기 목록에 없다: {seen}"

    async def test_another_hospital_does_not_see_it(self) -> None:
        """남의 의원 직원에게는 **한 건도** 안 보인다."""
        world = await build_two_hospitals()
        document_id = await self.upload_to(world["h1"].visit_id, world["staff1"].auth)

        _, seen = await self.documents_seen(world["h1"].visit_id, world["staff2"].auth)

        assert document_id not in seen, "남의 의원 직원에게 문서가 샜다"
        assert seen == [], f"남의 의원 진료에서 무언가 보인다: {seen}"

    async def test_a_document_does_not_cross_to_another_visit_of_the_same_hospital(self) -> None:
        """**같은 의원이라도 진료가 다르면 안 섞인다** (이희진 님 `#87` 리뷰).

        병원만 맞으면 통과하는 구현이면 여기서 걸린다. 한 환자의 지난 진료
        문서가 오늘 진료에 붙으면 스탭은 **다른 날 기록을 오늘 것으로 읽는다.**
        """
        world = await build_two_hospitals()
        _, other_visit = await make_patient_and_visit(world["h1"].hospital_id, "BLK-H1-002")

        mine = await self.upload_to(world["h1"].visit_id, world["staff1"].auth)
        theirs = await self.upload_to(other_visit, world["staff1"].auth)

        _, seen_here = await self.documents_seen(world["h1"].visit_id, world["staff1"].auth)
        _, seen_there = await self.documents_seen(other_visit, world["staff1"].auth)

        assert seen_here == [mine], f"이 진료에 다른 진료 문서가 섞였다: {seen_here}"
        assert seen_there == [theirs], f"저 진료에 다른 진료 문서가 섞였다: {seen_there}"

    async def test_hiding_and_not_existing_look_the_same(self) -> None:
        """감출 때와 없을 때가 **같아야** 한다.

        다르면 그 차이만으로 「그 의원에 그런 진료가 있다」를 알 수 있다.
        이 경로는 둘 다 `200 []` 다 — 404 를 쓰는 다른 OCR 경로와 다르지만,
        구별되지 않는다는 목적은 같다.
        """
        world = await build_two_hospitals()
        await self.upload_to(world["h1"].visit_id, world["staff1"].auth)

        hidden = await self.documents_seen(world["h1"].visit_id, world["staff2"].auth)
        absent = await self.documents_seen(999_999, world["staff2"].auth)

        assert hidden == absent, f"감출 때와 없을 때가 다르다 — 존재가 샌다\n  감춤: {hidden}\n  없음: {absent}"

    async def test_no_token_cannot_read_the_list(self) -> None:
        world = await build_two_hospitals()
        async with client() as http:
            response = await http.get(self.JOBS.format(v=world["h1"].visit_id))
        assert response.status_code == 401
