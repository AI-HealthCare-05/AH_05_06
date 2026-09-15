"""같은 열쇠가 두 번 와도 모델은 한 번만 부른다 — KEY-328.

이 종점은 환자 경로에서 **외부 모델을 부르는 유일한 자리**다. 두 번 불리면
돈이 두 번 나가고 이용 기록이 두 줄이 되어 S2-2·D1-6 의 셈이 부푼다.

여기서 재는 것은 인수조건 다섯이다.

    ① 같은 열쇠 두 번 → 모델 한 번, 답이 같다
    ② 이용 기록도 한 줄
    ③ 같은 열쇠에 다른 물음이면 막힌다
    ④ 다른 안내문의 같은 열쇠는 안 부딪힌다
    ⑤ 물음·답 원문이 표에 새로 남지 않는다

그리고 이희진 님이 더해 달라고 한 자리 — **첫 답이 캐시에 들어가기 전에** 같은
열쇠가 또 오는 경우(응답 유실·중단 직후 재시도)다.
"""

import asyncio
from dataclasses import dataclass, field

import httpx
from httpx import ASGITransport, AsyncClient

from app.apis.v1.chatbot_routers import get_chatbot_service
from app.main import app
from app.models.visits import (
    ChatbotSubmission,
    GuideDocument,
    PatientUsageEvent,
    PatientUsageEventType,
)
from app.services.chatbot import ChatbotService, ChatModelError, ModelAnswer
from app.services.chatbot_submissions import ChatbotSubmissionGuard
from app.services.patient_sessions import PatientSessionStore
from app.tests.chatbot.test_chatbot import OTHER_TOKEN, TOKEN, ChatbotTestCase

KEY = "3f1a7c64-5b2e-4a19-9c33-8d0b6f2a1e57"
OTHER_KEY = "9b2c4d81-7e6f-4a35-8c19-2d5a0f7b3e64"
QUESTION = "약은 언제 먹나요?"


@dataclass
class CountingModel:
    """부른 횟수를 센다. **잠금이 잡힌 채로 불리는지도 본다.**

    잠금을 모델 호출 **뒤에** 잡으면 순차 검사는 다 통과하면서도 동시 요청은
    둘 다 모델을 부른다. 그래서 부르는 순간 잠금 키가 살아 있는지 여기서 잰다.
    """

    redis: object | None = None
    lock_key: str | None = None
    answer: str = "매일 저녁 같은 시간에 복용하세요."
    fail: bool = False
    calls: list[str] = field(default_factory=list)
    locked_while_calling: list[bool] = field(default_factory=list)
    model_name: str = "synthetic-key328-model"

    async def generate(self, *, instructions: str, prompt: str) -> ModelAnswer:
        self.calls.append(prompt)
        if self.redis is not None and self.lock_key is not None:
            self.locked_while_calling.append(bool(await self.redis.exists(self.lock_key)))  # type: ignore[attr-defined]
        if self.fail:
            raise ChatModelError("synthetic failure")
        return ModelAnswer(self.answer, input_tokens=10, output_tokens=5)


class SubmissionKeyTestCase(ChatbotTestCase):
    async def ask(
        self,
        service: ChatbotService,
        *,
        question: str = QUESTION,
        key: str | None = KEY,
        token: str = TOKEN,
    ) -> httpx.Response:
        body: dict[str, object] = {"question": question}
        if key is not None:
            body["submission_id"] = key

        app.dependency_overrides[get_chatbot_service] = lambda: service
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                raw_session = await PatientSessionStore(self.redis).start(token)  # type: ignore[arg-type]
                client.cookies.set("patient_session", raw_session)
                return await client.post("/api/v1/chatbot/responses", json=body)
        finally:
            app.dependency_overrides.pop(get_chatbot_service, None)

    @staticmethod
    async def chatbot_events(guide: GuideDocument) -> int:
        return await PatientUsageEvent.filter(
            guide_document_id=guide.guide_document_id,
            event_type=PatientUsageEventType.CHATBOT_ANSWERED,
        ).count()


class TestTheSameKeyAnswersOnce(SubmissionKeyTestCase):
    async def test_the_model_is_called_once_and_the_answer_is_the_same(self) -> None:
        """인수조건 ①② — 모델 한 번, 이용 기록 한 줄."""
        guide = await self.approved("KEY-328 같은 열쇠 두 번")
        model = CountingModel()

        first = await self.ask(ChatbotService(model=model))
        second = await self.ask(ChatbotService(model=model))

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert len(model.calls) == 1, f"모델이 {len(model.calls)} 번 불렸다"
        assert first.json() == second.json(), "두 번째가 그때 그 답이 아니다"
        assert await self.chatbot_events(guide) == 1, "이용 기록이 두 줄이다"
        assert await ChatbotSubmission.filter(guide_document_id=guide.guide_document_id).count() == 1

    async def test_the_reply_carries_the_same_response_ref(self) -> None:
        """답을 되돌려 줄 때 `response_ref` 도 그때 그 값이어야 한다.

        이 값의 digest 로 환자 피드백이 이용 기록을 찾는다(KEY-239). 새로
        만들어 주면 두 번째 답에 단 피드백이 **아무 기록에도 안 붙는다.**
        """
        await self.approved("KEY-328 응답 참조")
        model = CountingModel()

        first = await self.ask(ChatbotService(model=model))
        second = await self.ask(ChatbotService(model=model))

        assert first.json()["response_ref"] is not None
        assert first.json()["response_ref"] == second.json()["response_ref"]

    async def test_a_different_question_on_the_same_key_is_blocked(self) -> None:
        """인수조건 ③ — 열쇠 하나는 물음 하나의 것이다."""
        guide = await self.approved("KEY-328 같은 열쇠 다른 물음")
        model = CountingModel()

        await self.ask(ChatbotService(model=model))
        clashed = await self.ask(ChatbotService(model=model), question="운동해도 되나요?")

        assert clashed.status_code == 409
        assert clashed.json()["code"] == "CHATBOT_SUBMISSION_CONFLICT"
        assert len(model.calls) == 1, "막아 놓고 모델은 불렀다"
        assert await self.chatbot_events(guide) == 1

    async def test_another_guide_with_the_same_key_does_not_collide(self) -> None:
        """인수조건 ④ — 열쇠는 그 안내문 안에서만 유일하다."""
        mine = await self.approved("KEY-328 내 안내문")
        other = await self.approved("KEY-328 남의 안내문", token=OTHER_TOKEN)
        model = CountingModel()

        first = await self.ask(ChatbotService(model=model))
        second = await self.ask(ChatbotService(model=model), token=OTHER_TOKEN)

        assert first.status_code == 200
        assert second.status_code == 200, second.text
        assert len(model.calls) == 2, "다른 안내문인데 앞의 답을 돌려줬다"
        assert await self.chatbot_events(mine) == 1
        assert await self.chatbot_events(other) == 1

    async def test_a_request_without_a_key_is_not_guarded(self) -> None:
        """열쇠 없는 요청은 **예전 그대로** 돈다.

        옛 화면·스크립트가 아직 안 보낸다. 여기서 막으면 그 화면이 죽는다 —
        필수로 돌리는 것은 보내는 쪽이 다 갈린 뒤의 일이다(이희진 님 확인).
        """
        guide = await self.approved("KEY-328 열쇠 없는 요청")
        model = CountingModel()

        await self.ask(ChatbotService(model=model), key=None)
        await self.ask(ChatbotService(model=model), key=None)

        assert len(model.calls) == 2
        assert await self.chatbot_events(guide) == 2
        assert await ChatbotSubmission.all().count() == 0, "열쇠가 없는데 줄이 생겼다"


class TestTheSecondRequestArrivesTooEarly(SubmissionKeyTestCase):
    """첫 답이 캐시에 들어가기 **전에** 같은 열쇠가 또 오는 경우.

    ⚠️ **진짜 동시 요청은 이 하네스에서 못 만든다** — `tortoise.contrib.test.
    TestCase` 가 검사를 트랜잭션으로 감싸고 커넥션 하나를 공유해서, 두 요청을
    `asyncio.gather` 로 보내면 MySQL 소켓이 먼저 깨진다(`#50` 때와 같은 자리).

    그래서 둘로 나눠 잰다.
      ① 잠금이 **모델을 부르는 동안** 잡혀 있는가 (그래야 둘째가 막힌다)
      ② 잠긴 상태에서 같은 열쇠가 오면 `409` 인가
    """

    async def test_the_lock_is_held_while_the_model_runs(self) -> None:
        guide = await self.approved("KEY-328 잠금 유지")
        guard = ChatbotSubmissionGuard(self.redis, submission_id=KEY, question=QUESTION)  # type: ignore[arg-type]
        await guard.open(guide)
        lock_key = guard._lock_key  # noqa: SLF001 - 키 모양까지 재려는 검사다
        await guard.release()

        model = CountingModel(redis=self.redis, lock_key=lock_key)
        answered = await self.ask(ChatbotService(model=model))

        assert answered.status_code == 200, answered.text
        assert model.locked_while_calling == [True], "모델을 부르는 동안 잠금이 없다 — 동시 요청이 둘 다 지나간다"

    async def test_a_second_request_under_the_lock_is_told_it_is_in_progress(self) -> None:
        guide = await self.approved("KEY-328 처리 중")
        holder = ChatbotSubmissionGuard(self.redis, submission_id=KEY, question=QUESTION)  # type: ignore[arg-type]
        assert await holder.open(guide) is None, "처음 여는 열쇠인데 답이 돌아왔다"

        model = CountingModel()
        blocked = await self.ask(ChatbotService(model=model))

        assert blocked.status_code == 409
        assert blocked.json()["code"] == "CHATBOT_ANSWER_IN_PROGRESS"
        assert model.calls == [], "처리 중인데 모델을 또 불렀다"
        assert await self.chatbot_events(guide) == 0

    async def test_two_guards_racing_for_the_same_key_leave_one_holder(self) -> None:
        """잠금 자체는 Redis 만 쓰므로 여기서는 **진짜로 동시에** 부를 수 있다."""
        guide = await self.approved("KEY-328 잠금 경합")
        guards = [
            ChatbotSubmissionGuard(self.redis, submission_id=KEY, question=QUESTION)  # type: ignore[arg-type]
            for _ in range(5)
        ]

        results = await asyncio.gather(*(g.open(guide) for g in guards), return_exceptions=True)

        passed = [r for r in results if not isinstance(r, Exception)]
        blocked = [r for r in results if isinstance(r, Exception)]
        assert len(passed) == 1, f"{len(passed)} 개가 동시에 통과했다 — 모델이 그만큼 불린다"
        assert len(blocked) == 4
        assert all(getattr(error, "code", None) == "CHATBOT_ANSWER_IN_PROGRESS" for error in blocked)


class TestWhenThereIsNoAnswerToReplay(SubmissionKeyTestCase):
    async def test_the_key_is_spent_once_the_cached_answer_is_gone(self) -> None:
        """5분이 지나면 **되돌려 줄 답이 없다.** 새로 답하지 않고 막는다.

        새로 답하면 이용 기록이 두 줄이 되어 인수조건 ②를 어긴다. 화면은
        재시도할 때만 같은 열쇠를 다시 쓰므로, 5분 뒤에 같은 열쇠가 오는 것은
        정상 흐름이 아니다(이희진 님 결정).
        """
        guide = await self.approved("KEY-328 캐시 만료")
        model = CountingModel()
        await self.ask(ChatbotService(model=model))

        for key in [k for k in self.redis.values if k.startswith("chatbot:answer:")]:
            await self.redis.delete(key)

        expired = await self.ask(ChatbotService(model=model))

        assert expired.status_code == 409
        assert expired.json()["code"] == "CHATBOT_ANSWER_EXPIRED"
        assert len(model.calls) == 1, "답을 못 돌려주면서 모델은 다시 불렀다"
        assert await self.chatbot_events(guide) == 1, "이용 기록이 두 줄이 됐다"

    async def test_a_model_failure_leaves_the_key_usable_again(self) -> None:
        """모델이 실패하면 **줄을 안 남긴다** — 「다시 시도」가 같은 열쇠로 가야 한다."""
        guide = await self.approved("KEY-328 모델 실패")
        failing = CountingModel(fail=True)

        failed = await self.ask(ChatbotService(model=failing))

        assert failed.status_code == 200, "환자에게는 고정 안내를 준다"
        assert failed.json()["fallback"] is True
        assert await ChatbotSubmission.all().count() == 0, "실패한 요청이 열쇠를 태웠다"

        working = CountingModel()
        retried = await self.ask(ChatbotService(model=working))

        assert retried.status_code == 200, retried.text
        assert retried.json()["fallback"] is False
        assert len(working.calls) == 1, "다시 시도가 막혔다"
        assert await self.chatbot_events(guide) == 2


class TestNothingNewIsKept(SubmissionKeyTestCase):
    async def test_the_row_holds_only_digests(self) -> None:
        """인수조건 ⑤ — 물음도 답도 표에 안 들어간다."""
        await self.approved("KEY-328 원문 없음")
        await self.ask(ChatbotService(model=CountingModel()))

        row = await ChatbotSubmission.all().first()
        assert row is not None
        stored = {name: getattr(row, name) for name in row._meta.fields_map if hasattr(row, name)}
        flattened = " ".join(str(value) for value in stored.values())

        assert QUESTION not in flattened, "물음 원문이 표에 남았다"
        assert "매일 저녁" not in flattened, "답 원문이 표에 남았다"
        assert KEY not in flattened, "열쇠 원문이 그대로 남았다 — digest 여야 한다"
        assert len(row.idempotency_digest) == 64
        assert len(row.question_digest) == 64

    async def test_the_cache_key_carries_no_raw_values(self) -> None:
        """캐시 **키**에도 원문이 없다. 값은 환자에게 이미 보낸 답 그대로다."""
        await self.approved("KEY-328 캐시 키")
        await self.ask(ChatbotService(model=CountingModel()))

        cached = [key for key in self.redis.values if key.startswith("chatbot:")]
        assert cached, "답을 캐시에 안 넣었다"
        for key in cached:
            assert KEY not in key
            assert QUESTION not in key
