"""챗봇 물음의 멱등 열쇠 — KEY-328.

`POST /chatbot/responses` 는 환자 경로에서 **외부 모델을 부르는 유일한 자리**다.
같은 요청이 두 번 오면 돈이 두 번 나가고 이용 기록이 두 줄이 된다. 재시도가 바로
그 상황을 만든다 — 서버는 답을 만들었는데 응답이 유실되면 환자 화면에는 오류가
뜨고, 화면 잠금은 그때 이미 풀려 있다.

**무엇을 어디 두는가** (이희진 님 결정, 2026-09-14).

    표(`chatbot_submission`)   열쇠 digest · 물음 digest · 시각.  영구.
    Redis                      열쇠 digest → 답.                 5분.
    Redis                      처리 중 잠금.                     짧게.

답 본문은 표에 안 들어간다. 환자 질문·답변을 영구 보관하지 않는 쪽으로 간다 —
원본 삭제·토큰 비노출과 같은 방향이다. 그래서 5분이 지나면 **되돌려 줄 답이
없다.** 그때는 새로 답하지 않고 막는다. 새로 답하면 이용 기록이 두 줄이 되어
인수조건 2 를 어긴다. 화면은 재시도할 때만 같은 열쇠를 다시 쓰므로, 5분 뒤에
같은 열쇠가 오는 것은 정상 흐름이 아니다.

**잠금이 따로 있는 까닭.** 첫 답이 캐시에 들어가기 **전에** 같은 열쇠의 두 번째
요청이 오면(응답 유실 직후 재시도 · 중단 직후 재시도) 표에도 캐시에도 아직
아무것도 없다. 잠금이 없으면 둘 다 모델을 부른다.
"""

import hashlib
import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

from redis.asyncio import Redis
from tortoise.exceptions import IntegrityError

from app.core.api_errors import ApiError
from app.models.visits import ChatbotSubmission, GuideDocument, GuideSectionKey

if TYPE_CHECKING:  # pragma: no cover - 순환 import 를 피한다
    from tortoise import BaseDBAsyncClient

    from app.services.chatbot import ChatbotResult

#: 답을 캐시에 두는 시간. 두 번 누름과 재시도는 거의 다 몇 초 안에 일어난다.
ANSWER_TTL_SECONDS = 300

#: 처리 중 잠금. 모델 호출 시간(`OPENAI_TIMEOUT_SECONDS` 기본 30초)보다 넉넉해야
#: 첫 요청이 답하는 동안 잠금이 풀리지 않는다. 반대로 너무 길면 서버가 죽은 뒤
#: 같은 열쇠가 그만큼 막힌다 — 그 경우 환자는 새 물음을 보내면 된다.
LOCK_TTL_SECONDS = 60


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _conflict() -> ApiError:
    return ApiError(
        409,
        "CHATBOT_SUBMISSION_CONFLICT",
        "같은 요청 열쇠로 다른 물음이 왔습니다.",
    )


def _expired() -> ApiError:
    return ApiError(
        409,
        "CHATBOT_ANSWER_EXPIRED",
        "이미 답한 물음인데 답을 다시 불러올 수 있는 시간이 지났습니다.",
    )


def _in_progress() -> ApiError:
    return ApiError(
        409,
        "CHATBOT_ANSWER_IN_PROGRESS",
        "같은 물음에 답하는 중입니다.",
    )


class ChatbotSubmissionGuard:
    """요청 하나를 지키는 문지기. **한 요청에 하나씩 만든다.**

    `ChatbotService` 가 안내문을 찾은 **뒤에** `open()` 을 부르고, 답을 남길 때
    `commit()` 을 같은 트랜잭션 안에서 부른다. 모델이 실패하면 `release()` 만
    불러 잠금을 풀고 줄은 남기지 않는다 — 그래야 「다시 시도」가 같은 열쇠로
    정상 진행된다.
    """

    def __init__(self, redis: Redis, *, submission_id: UUID, question: str) -> None:
        self._redis = redis
        self._key = _digest(str(submission_id))
        self._question_digest = _digest(question)
        self._guide_document_id: int | None = None
        self._locked = False

    async def open(self, guide: GuideDocument) -> "ChatbotResult | None":
        """이미 답한 열쇠면 그 답을, 처음 보는 열쇠면 `None` 을 준다.

        되돌려 줄 수 없는 경우는 **막는다**(409). 셋을 코드로 가른다 — 다른
        물음인가, 시간이 지났나, 지금 답하는 중인가. 화면이 각각 다르게
        말해야 해서다.
        """
        self._guide_document_id = guide.guide_document_id

        existing = await ChatbotSubmission.filter(
            guide_document_id=guide.guide_document_id,
            idempotency_digest=self._key,
        ).first()
        if existing is not None:
            if existing.question_digest != self._question_digest:
                raise _conflict()
            cached = await self._redis.get(self._answer_key)
            if cached is None:
                raise _expired()
            return _from_cache(cached)

        if not await self._redis.set(self._lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS):
            raise _in_progress()
        self._locked = True
        return None

    async def commit(self, *, connection: "BaseDBAsyncClient | None" = None) -> None:
        """줄을 남긴다 — **이용 기록과 같은 트랜잭션에서** 부른다.

        여기서 `IntegrityError` 가 나면 잠금을 뚫고 둘이 들어왔다는 뜻이다
        (잠금이 만료될 만큼 오래 걸린 경우). 그때는 트랜잭션째 물러서게
        둔다 — 이용 기록도 함께 물러서므로 두 줄로 세지 않는다.
        """
        assert self._guide_document_id is not None, "open() 을 먼저 부른다"
        try:
            await ChatbotSubmission.create(
                guide_document_id=self._guide_document_id,
                idempotency_digest=self._key,
                question_digest=self._question_digest,
                using_db=connection,
            )
        except IntegrityError:
            raise _in_progress() from None

    async def publish(self, result: "ChatbotResult") -> None:
        """답을 캐시에 넣고 잠금을 푼다. **줄이 남은 뒤에만** 부른다."""
        await self._redis.setex(self._answer_key, ANSWER_TTL_SECONDS, _to_cache(result))
        await self.release()

    async def release(self) -> None:
        if self._locked:
            await self._redis.delete(self._lock_key)
            self._locked = False

    @property
    def _answer_key(self) -> str:
        return f"chatbot:answer:{self._guide_document_id}:{self._key}"

    @property
    def _lock_key(self) -> str:
        return f"chatbot:lock:{self._guide_document_id}:{self._key}"


def _to_cache(result: "ChatbotResult") -> str:
    """**물음은 안 담는다.** 담는 것은 환자에게 이미 보낸 답 그대로다."""
    return json.dumps(
        {
            "answer": result.answer,
            "evidence": result.evidence,
            "source": result.source,
            "limitation": result.limitation,
            "urgent": result.urgent,
            "fallback": result.fallback,
            "grounded_section": result.grounded_section.value if result.grounded_section else None,
            "response_ref": result.response_ref,
        },
        ensure_ascii=False,
    )


def _from_cache(raw: str) -> "ChatbotResult":
    from app.services.chatbot import ChatbotResult

    data: dict[str, Any] = json.loads(raw)
    section = data.get("grounded_section")
    return ChatbotResult(
        answer=data["answer"],
        evidence=data["evidence"],
        source=data["source"],
        limitation=data["limitation"],
        urgent=data["urgent"],
        fallback=data["fallback"],
        grounded_section=GuideSectionKey(section) if section else None,
        response_ref=data.get("response_ref"),
    )
