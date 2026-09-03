"""병원 링크 발급 응답이 승인 안내·챗봇까지 같은 토큰으로 이어지는가 — KEY-205."""

import hashlib
from dataclasses import dataclass, field
from unittest.mock import patch

from app.apis.v1.chatbot_routers import get_chatbot_service
from app.main import app
from app.models.visits import GuideDocument, GuideStatus, PatientGuideLink
from app.services.chatbot import ChatbotService, ModelAnswer
from app.services.patient_sessions import PatientSessionStore
from app.tests.patient_links.test_patient_links import (
    PatientLinkTestCase,
    make_guide,
    make_hospital,
    make_staff,
)

LINK_TOKEN = "synthetic-key205-link-token-never-used-outside-tests"


@dataclass
class ApprovedGuideModel:
    model_name: str = "synthetic-key205-model"
    prompts: list[str] = field(default_factory=list)

    async def generate(self, *, instructions: str, prompt: str) -> ModelAnswer:
        self.prompts.append(f"{instructions}\n{prompt}")
        # 최신 안전 계약은 승인 컨텍스트의 완전한 문장을 그대로 인용한 답만
        # 환자에게 내보낸다. fixture도 실제 승인 본문을 벗어나 새 표현을 만들지 않는다.
        return ModelAnswer("합성 승인 복약 안내", input_tokens=1, output_tokens=1)


class TestKey205PatientLinkLaunch(PatientLinkTestCase):
    async def test_issue_path_opens_the_same_approved_guide_and_chatbot_context(self) -> None:
        hospital = await make_hospital("KEY-205 SYN-EMS-01 합성의원")
        guide: GuideDocument = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key205-staff", ["staff"])
        model = ApprovedGuideModel()
        app.dependency_overrides[get_chatbot_service] = lambda: ChatbotService(model=model)

        with patch("app.services.patient_links.secrets.token_urlsafe", return_value=LINK_TOKEN):
            async with self.client() as client:
                issued = await client.post(
                    f"/api/v1/visits/{guide.visit_id}/guide/link",
                    headers=await self.headers(staff),
                )
                assert issued.status_code == 201, issued.text
                path = issued.json()["path"]
                opened = await client.get(path)
                raw_session = await PatientSessionStore(self.redis).start(LINK_TOKEN)  # type: ignore[arg-type]
                client.cookies.set("patient_session", raw_session)
                chatbot = await client.post(
                    "/api/v1/chatbot/responses",
                    json={"question": "약은 언제 먹나요?"},
                )

        assert path == f"/api/v1/guides/{LINK_TOKEN}"
        assert opened.status_code == 200, opened.text
        assert opened.json()["sections"] == [{"key": "medication", "body": "합성 승인 복약 안내"}]
        assert chatbot.status_code == 200, chatbot.text
        assert chatbot.json()["fallback"] is False
        assert chatbot.json()["source"] == "담당 의료진이 승인한 진료 안내"
        assert len(model.prompts) == 1
        assert "합성 승인 복약 안내" in model.prompts[0]
        assert "합성 생성 원문" not in model.prompts[0]

        saved = await PatientGuideLink.get(guide_document=guide)
        assert saved.token_digest == hashlib.sha256(LINK_TOKEN.encode()).hexdigest()
        assert LINK_TOKEN not in repr(saved.__dict__)
