"""환자 이용 이벤트가 **결과만** 남기는가 — KEY-170.

이 검사가 지키려는 것은 둘이다.

  ① 승인된 안내에만 남는다 — 아직 안 나간 글을 「환자가 읽었다」로 세지 않는다
  ② **원문이 담길 자리가 없다** — 질문·답변·프롬프트·토큰

②는 값을 확인하는 것으로 부족하다. 「지금은 안 담긴다」가 아니라 **담을 칸이
없다**를 재야 한다. 칸이 생기는 날 이 검사가 죽어야, 그때 계약으로 올라온다.

여기 값은 전부 합성이다.
"""

import hashlib

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core.auth_errors import AuthError as ApiError
from app.models.visits import (
    GuideDocument,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    PatientAnswerOutcome,
    PatientGuideLink,
    PatientQuestionKind,
    PatientUsageEvent,
    PatientUsageEventType,
)
from app.services.patient_usage import PatientUsageService
from app.tests.patient_links.test_patient_links import TOKEN, make_guide, make_hospital

QUESTION = "비잔 먹고 머리가 아픈데 계속 먹어도 되나요"
ANSWER = "합성 답변 원문 — 저장되면 안 됩니다"


class PatientUsageTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.usage = PatientUsageService()


class TestOnlyApprovedGuidesGetEvents(PatientUsageTestCase):
    async def test_an_approved_guide_records_a_view(self) -> None:
        clinic = await make_hospital("이용 합성의원")
        guide = await make_guide(clinic, GuideStatus.SCHEDULED_TO_SEND)

        event = await self.usage.record_guide_view(guide.guide_document_id)

        assert event.event_type is PatientUsageEventType.GUIDE_VIEWED
        assert event.guide_document_id == guide.guide_document_id
        assert await PatientUsageEvent.all().count() == 1

    async def test_the_event_reaches_the_visit_through_the_guide(self) -> None:
        """인수조건 — 이벤트가 그 `visit_id` 와 연결된다.

        `visit_id` 를 사본으로 두지 않고 안내문을 타고 간다. 사본을 두면
        두 값이 어긋날 자리가 생긴다.
        """
        clinic = await make_hospital("연결 합성의원")
        guide = await make_guide(clinic, GuideStatus.SCHEDULED_TO_SEND)

        event = await self.usage.record_guide_view(guide.guide_document_id)

        stored = await PatientUsageEvent.get(patient_usage_event_id=event.patient_usage_event_id)
        reached = await stored.guide_document
        assert reached.visit_id == guide.visit_id

    async def test_an_unapproved_guide_records_nothing(self) -> None:
        """**환자가 볼 수 없는 글에는 이용 기록이 생길 수 없다.**

        여기서 안 막으면 「아직 안 나간 글을 환자가 읽었다」가 통계에 섞인다.
        """
        clinic = await make_hospital("미승인 합성의원")
        guide = await make_guide(clinic, GuideStatus.APPROVAL_PENDING)

        for call in (
            lambda: self.usage.record_guide_view(guide.guide_document_id),
            lambda: self.usage.record_chatbot_answer(
                guide.guide_document_id,
                question_kind=PatientQuestionKind.MEDICATION,
                outcome=PatientAnswerOutcome.ANSWERED,
            ),
        ):
            try:
                await call()
            except ApiError as error:
                assert error.status_code == 404
                assert error.code == "GUIDE_NOT_FOUND"
            else:
                raise AssertionError("미승인 안내문에 이용 이벤트가 남았다")

        assert await PatientUsageEvent.all().count() == 0

    async def test_a_missing_guide_answers_like_an_unapproved_one(self) -> None:
        """없는 것과 아직 승인 안 된 것이 **같은 답**이다.

        다르면 그 차이만으로 「그 진료가 있다」를 알 수 있다.
        """
        clinic = await make_hospital("대조 합성의원")
        pending = await make_guide(clinic, GuideStatus.APPROVAL_PENDING)

        errors = []
        for guide_id in (pending.guide_document_id, 999_999):
            try:
                await self.usage.record_guide_view(guide_id)
            except ApiError as error:
                errors.append((error.status_code, error.code, str(error)))

        assert len(errors) == 2
        assert errors[0] == errors[1], f"감출 때와 없을 때가 다르다: {errors}"


class TestNothingVerbatimIsStored(PatientUsageTestCase):
    async def test_the_table_has_no_column_for_words(self) -> None:
        """**담을 칸이 없다.**

        값이 안 담기는 것을 재는 것으로는 부족하다 — 칸이 있으면 언젠가 담긴다.
        칸이 생기는 날 이 검사가 죽고, 그때 계약으로 올라온다.
        """
        columns = set(PatientUsageEvent._meta.fields_map)

        assert columns == {
            "patient_usage_event_id",
            "guide_document",
            "guide_document_id",
            "event_type",
            "question_kind",
            "answer_outcome",
            "grounded_section",
            "created_at",
        }, f"칸이 바뀌었다: {sorted(columns)}"

        # `question_kind` · `answer_outcome` 은 **갈래와 결과**이지 원문이 아니다.
        # 위 목록에 이미 있으므로, 여기서는 **원문이 들어갈 법한 이름**만 본다.
        # 「무엇을 물었나」가 아니라 「어떤 갈래였나」까지가 이 표의 한계다.
        shaped = {"question_kind", "answer_outcome", "grounded_section"}
        for forbidden in ("question", "answer", "prompt", "token", "text", "body", "content", "message"):
            leaked = [c for c in columns - shaped if forbidden in c.lower()]
            assert not leaked, f"원문이 담길 만한 칸이 생겼다: {leaked}"

    async def test_the_interface_takes_no_words(self) -> None:
        """**인터페이스가 원문을 받지 않는다.**

        받을 수 있게 두면 KEY-95·KEY-96 이 넣고, 그때는 이미 쌓인 뒤다.
        """
        import inspect

        params = set(inspect.signature(PatientUsageService.record_chatbot_answer).parameters)
        assert params == {"self", "guide_document_id", "question_kind", "outcome", "grounded_section"}, (
            f"인자가 바뀌었다: {sorted(params)}"
        )

    async def test_a_recorded_answer_keeps_only_the_shape(self) -> None:
        clinic = await make_hospital("챗봇 합성의원")
        guide = await make_guide(clinic, GuideStatus.SCHEDULED_TO_SEND)

        event = await self.usage.record_chatbot_answer(
            guide.guide_document_id,
            question_kind=PatientQuestionKind.MEDICATION,
            outcome=PatientAnswerOutcome.BLOCKED,
            grounded_section=GuideSectionKey.CAUTION,
        )

        assert event.question_kind is PatientQuestionKind.MEDICATION
        assert event.answer_outcome is PatientAnswerOutcome.BLOCKED
        assert event.grounded_section is GuideSectionKey.CAUTION

        stored = repr((await PatientUsageEvent.get(patient_usage_event_id=event.patient_usage_event_id)).__dict__)
        for word in (QUESTION, ANSWER, TOKEN):
            assert word not in stored

    async def test_blocked_and_fallback_are_told_apart(self) -> None:
        """막은 것과 못 한 것은 **다른 문제**다.

        한 값으로 뭉치면 「규칙을 손봐야 하는가 · 지식을 손봐야 하는가」를
        나중에 가릴 수 없다.
        """
        clinic = await make_hospital("결과 합성의원")
        guide = await make_guide(clinic, GuideStatus.SCHEDULED_TO_SEND)

        for outcome in PatientAnswerOutcome:
            await self.usage.record_chatbot_answer(
                guide.guide_document_id,
                question_kind=PatientQuestionKind.OTHER,
                outcome=outcome,
            )

        stored = {event.answer_outcome for event in await PatientUsageEvent.all()}
        assert stored == set(PatientAnswerOutcome)


OTHER_TOKEN = "zW4nR7tB1kM9pC3xL6vD8sG2hJ5qA0yF7uE4bN1oT2r"


async def open_guide(clinic_name: str, token: str) -> GuideDocument:
    """승인 안내 하나와 그것을 여는 링크 하나."""
    clinic = await make_hospital(clinic_name)
    guide = await make_guide(clinic, GuideStatus.SCHEDULED_TO_SEND)
    await GuideSection.create(
        guide_document=guide,
        section_key=GuideSectionKey.CAUTION,
        generated_body="합성 승인 주의 안내",
    )
    await PatientGuideLink.create(
        guide_document=guide,
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now().replace(year=now().year + 1),
        issued_by=1,
    )
    return guide


class TestTheReadPathRecordsTheView(PatientUsageTestCase):
    """인터페이스만 두면 아무도 안 부른다 — 실제 경로에 걸려 있는가."""

    def setUp(self) -> None:
        super().setUp()
        from app.core.redis_client import get_redis
        from app.dependencies.patient_auth import require_patient_session
        from app.main import app
        from app.tests.fakes import FakeRedis

        self.app = app
        app.dependency_overrides[get_redis] = lambda: FakeRedis()
        app.dependency_overrides[require_patient_session] = lambda: None
        self.addCleanup(app.dependency_overrides.clear)

    async def read(self, token: str):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test") as client:
            return await client.get(f"/api/v1/guides/{token}")

    async def test_reading_the_patient_link_leaves_a_view_event(self) -> None:
        guide = await open_guide("열람 합성의원", TOKEN)

        read = await self.read(TOKEN)

        assert read.status_code == 200
        events = await PatientUsageEvent.all()
        assert len(events) == 1, "환자가 안내를 열었는데 이용 이벤트가 안 남았다"
        assert events[0].event_type is PatientUsageEventType.GUIDE_VIEWED
        assert events[0].guide_document_id == guide.guide_document_id
        assert TOKEN not in read.text

    async def test_one_hospitals_token_never_marks_another_hospitals_guide(self) -> None:
        """인수조건 — **타 병원 데이터로 이벤트를 만들 수 없다.**

        이벤트가 붙는 자리를 토큰이 정한다. 병원 번호를 따로 받지 않으므로
        「A 병원 토큰으로 B 병원 안내를 읽었다」가 될 자리가 없다. 이 검사는
        그 자리가 생기면 죽는다.
        """
        ours = await open_guide("우리 합성의원", TOKEN)
        theirs = await open_guide("다른 합성의원", OTHER_TOKEN)

        assert (await self.read(TOKEN)).status_code == 200

        events = await PatientUsageEvent.all()
        assert [event.guide_document_id for event in events] == [ours.guide_document_id]
        assert await PatientUsageEvent.filter(guide_document_id=theirs.guide_document_id).count() == 0, (
            "다른 병원 안내에 이용 기록이 남았다"
        )

    async def test_no_endpoint_serves_usage_events_back(self) -> None:
        """인수조건 — **병원 사용자가 원문 전체를 조회할 API를 더하지 않는다.**

        표에 원문 칸이 없으니 원문은 못 나간다. 그래도 이용 이벤트를 그대로
        돌려주는 창구가 생기면 그때 다시 볼 일이므로, 창구 자체가 없는 것을
        여기서 못 박는다.
        """
        paths = [path for path in (getattr(route, "path", "") for route in self.app.routes) if path.startswith("/api/")]

        # KEY-96의 환자용 `/chatbot/responses`는 필요하다. 여기서 금지하는 것은
        # 저장된 이용 이벤트를 병원에 다시 돌려주는 조회 창구다.
        opened = [p for p in paths if "usage" in p or "events" in p]
        assert not opened, f"이용 이벤트를 돌려주는 창구가 생겼다: {opened}"
