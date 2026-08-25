"""OCR API 가 **로그인해서 받은 토큰**으로 실제로 열리는지 본다 — KEY-116.

이 파일이 있는 이유가 요점이다. 기존 OCR 검사는 둘 다 인증을 건너뛴다.

  * API 검사      `app.dependency_overrides[get_ocr_actor] = lambda: STAFF`
  * 보안 단위 검사  `get_ocr_actor(...)` 를 직접 부른다

그래서 **의존성 배선이 틀려도 초록불**이었다. 실제로 틀려 있었다 —
`get_request_user` 에 걸려 있었고, 그것은 토큰의 `user_id` 를 보는데
제품 안에 그 클레임을 담은 토큰을 만드는 경로가 없다. OCR 다섯이 전부
401 이었고 아무도 몰랐다.

여기서는 `POST /auth/login` 으로 **라우트를 통해** 토큰을 받아서 쓴다.
배선이 끊기면 이 파일이 먼저 빨간불이 된다.
"""

from datetime import UTC, date, datetime
from typing import Any

from httpx import ASGITransport, AsyncClient, Response

from app.core.utils.security import hash_password
from app.main import app
from app.models.ocr import OcrJob, OcrJobStatus
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit
from app.tests.auth_base import AuthTestCase

PASSWORD = "Password123!"
LOGIN_URL = "/api/v1/auth/login"


class OcrAuthWiringTestCase(AuthTestCase):

    async def make_staff(
        self,
        *,
        login_id: str,
        roles: list[str],
        hospital_name: str,
        must_change_password: bool = False,
    ) -> Staff:
        hospital = await Hospital.create(name=hospital_name)
        return await Staff.create(
            hospital=hospital,
            login_id=login_id,
            password_hash=hash_password(PASSWORD),
            name="합성 직원",
            roles=roles,
            # 모델 기본값은 True 다 — 어드민이 만든 계정은 첫 로그인에 바꾼다.
            # 여기서 보려는 것은 그 관문이 아니라 OCR 배선이라 꺼 둔다.
            must_change_password=must_change_password,
        )

    async def login(self, login_id: str) -> str:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(LOGIN_URL, json={"login_id": login_id, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return str(response.json()["access_token"])

    async def request(
        self,
        method: str,
        path: str,
        token: str | None = None,
        *,
        json: dict[str, Any] | None = None,
    ) -> Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, f"/api/v1{path}", headers=headers, json=json)

    async def get(self, path: str, token: str | None = None) -> Response:
        return await self.request("GET", path, token)


class TestStaffTokenOpensOcr(OcrAuthWiringTestCase):
    async def test_logged_in_staff_is_not_rejected_as_unauthenticated(self) -> None:
        """없는 job 이라 404 여야 한다 — **401 이면 배선이 끊긴 것이다.**"""
        await self.make_staff(login_id="ocrstaff01", roles=["staff"], hospital_name="기준의원")
        token = await self.login("ocrstaff01")

        response = await self.get("/ocr/jobs/does-not-exist", token)

        assert response.status_code != 401, "직원 토큰인데 인증에서 막혔다 — 의존성 배선을 보라"
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    async def test_doctor_token_also_opens_ocr(self) -> None:
        await self.make_staff(login_id="ocrdoctor01", roles=["doctor"], hospital_name="기준의원")
        token = await self.login("ocrdoctor01")

        response = await self.get("/ocr/jobs/does-not-exist", token)

        assert response.status_code == 404


class TestOcrIsClosedWithoutTheRightToken(OcrAuthWiringTestCase):
    async def test_no_token_is_rejected(self) -> None:
        response = await self.get("/ocr/jobs/does-not-exist")

        assert response.status_code in (401, 403)

    async def test_first_login_must_change_password_before_ocr(self) -> None:
        """비밀번호 관문은 OCR 에도 걸린다 — 발급받은 비밀번호로 진료 자료를 열지 못한다."""
        await self.make_staff(
            login_id="ocrnewbie01",
            roles=["staff"],
            hospital_name="기준의원",
            must_change_password=True,
        )
        token = await self.login("ocrnewbie01")

        response = await self.get("/ocr/jobs/does-not-exist", token)

        assert response.status_code == 403
        assert response.json()["code"] == "password_change_required"

    async def test_admin_alone_cannot_open_ocr(self) -> None:
        """`admin` 은 역할이 아니라 권한이다 — 로그인은 되지만 OCR 은 못 연다."""
        await self.make_staff(login_id="ocradmin01", roles=["admin"], hospital_name="기준의원")
        token = await self.login("ocradmin01")

        response = await self.get("/ocr/jobs/does-not-exist", token)

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"


class TestHospitalFenceComesFromTheToken(OcrAuthWiringTestCase):
    async def test_other_hospital_job_is_not_found(self) -> None:
        """다른 병원 자원은 403 이 아니라 **404** 다 — 있다는 사실도 알리지 않는다.

        이 검사가 `hospital_id` 가 정말 로그인한 직원에게서 오는지를 못 박는다.
        배선이 틀리면 병원 울타리가 통째로 사라진다.
        """
        alpha = await self.make_staff(login_id="alphastaff01", roles=["staff"], hospital_name="알파의원")
        beta = await self.make_staff(login_id="betastaff01", roles=["staff"], hospital_name="베타의원")
        assert alpha.hospital_id != beta.hospital_id

        patient = await Patient.create(
            hospital_id=alpha.hospital_id,
            hospital_patient_no="SYN-KEY116-001",
            name="합성 환자",
            birth_date=date(2000, 1, 1),
            phone="01000000000",
        )
        visit = await Visit.create(
            hospital_id=alpha.hospital_id,
            patient=patient,
            visited_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
        )
        await OcrJob.create(
            ocr_job_id="syn-key116-alpha",
            hospital_id=alpha.hospital_id,
            visit_id=visit.visit_id,
            requested_by=alpha.staff_id,
            status=OcrJobStatus.PROCESSING,
        )

        mine = await self.get("/ocr/jobs/syn-key116-alpha", await self.login("alphastaff01"))
        theirs = await self.get("/ocr/jobs/syn-key116-alpha", await self.login("betastaff01"))

        assert mine.status_code == 200
        assert theirs.status_code == 404
        assert "syn-key116-alpha" not in theirs.text
