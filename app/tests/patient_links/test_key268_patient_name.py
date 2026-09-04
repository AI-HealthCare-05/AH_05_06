"""OTP 인증한 뷰어에게 환자 전체 이름을 보여준다 — KEY-268.

KEY-268을 만들 당시엔 안내 조회가 링크 토큰만으로 열렸어서(KEY-178 이전),
`patient_name`을 "인증한 뷰어에게만" 보태는 선택적 필드로 뒀다. 이후
KEY-178이 조회 자체에 세션을 강제하면서, 이 라우트에 도달한 시점엔 이미
항상 인증된 뷰어다 — "선택적 표시"가 "항상 표시"로 접힌다.

세션이 없거나 다른 링크의 세션인 경우는 이제 401(PATIENT_SESSION_EXPIRED)로
막힌다 — test_patient_session.py 가 그 경계를 본다. 이 파일은 인증을 통과한
뒤 patient_name 이 실제로 마스킹 없이 실리는지, 그리고 no-store 헤더가
붙는지만 확인한다.
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


class TestKey268PatientName(PatientLinkTestCase):
    async def _issue_approved_link(self) -> None:
        hospital = await make_hospital("KEY-268 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key268-staff", ["staff"])
        assert (await self.issue(guide, staff)).status_code == 201

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
