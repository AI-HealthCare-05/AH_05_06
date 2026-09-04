"""OTP 인증한 뷰어에게만 환자 전체 이름을 보여준다 — KEY-268.

안내 조회 자체는 링크 토큰만으로 열리지만(KEY-178), `patient_name` 은 이 링크로
OTP 인증을 마친 세션이 있을 때만 응답에 실린다. 마스킹하지 않고 전체 이름을 준다.
"""

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.visits import GuideStatus
from app.services.patient_sessions import PatientSessionStore
from app.tests.patient_links.test_patient_links import (
    TOKEN,
    PatientLinkTestCase,
    make_guide,
    make_hospital,
    make_staff,
)


def _client_with_session(raw_session: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"patient_session": raw_session},
    )


OTHER_LINK_TOKEN = "z9Y8x7W6v5U4t3S2r1Q0p9O8n7M6l5K4j3I2h1G0fE1"


class TestKey268PatientName(PatientLinkTestCase):
    async def _issue_approved_link(self) -> None:
        hospital = await make_hospital("KEY-268 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key268-staff", ["staff"])
        assert (await self.issue(guide, staff)).status_code == 201

    async def test_name_is_absent_without_an_otp_session(self) -> None:
        await self._issue_approved_link()

        async with self.client() as client:
            response = await client.get(f"/api/v1/guides/{TOKEN}")

        assert response.status_code == 200
        body = response.json()
        assert "patient_name" not in body
        assert "합성환자" not in response.text
        # 이 응답도 캐시되면 세션이 생긴 뒤 patient_name 이 실린 응답과
        # 뒤섞일 여지가 있다 — 인증·미인증 모두 no-store 로 답한다.
        assert response.headers["cache-control"] == "no-store"

    async def test_full_name_is_shown_to_a_verified_viewer(self) -> None:
        await self._issue_approved_link()
        raw_session = await PatientSessionStore(self.redis).start(TOKEN)  # type: ignore[arg-type]

        async with _client_with_session(raw_session) as client:
            response = await client.get(f"/api/v1/guides/{TOKEN}")

        assert response.status_code == 200
        # 마스킹하지 않은 전체 이름.
        assert response.json()["patient_name"] == "합성환자"
        # 로그아웃·세션 만료 뒤에도 캐시된 이 응답이 재사용되면 안 된다
        # (기술 리드 리뷰, PR #211).
        assert response.headers["cache-control"] == "no-store"

    async def test_session_for_another_link_does_not_reveal_the_name(self) -> None:
        await self._issue_approved_link()
        raw_session = await PatientSessionStore(self.redis).start(  # type: ignore[arg-type]
            OTHER_LINK_TOKEN
        )

        async with _client_with_session(raw_session) as client:
            response = await client.get(f"/api/v1/guides/{TOKEN}")

        assert response.status_code == 200
        assert "patient_name" not in response.json()
