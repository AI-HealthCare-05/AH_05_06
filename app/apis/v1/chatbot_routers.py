"""환자 챗봇 단일 응답 API — KEY-96."""

from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core.api_errors import ContractRoute
from app.core.config import Config
from app.core.redis_client import get_redis
from app.dependencies.patient_auth import require_patient_session_link
from app.dtos.chatbot import ChatbotResponse, ChatbotResponseRequest
from app.services.chatbot import ChatbotService, OpenAIResponsesModel
from app.services.chatbot_submissions import ChatbotSubmissionGuard

chatbot_router = APIRouter(prefix="/chatbot", tags=["patient-chatbot"], route_class=ContractRoute)


def get_chatbot_service() -> ChatbotService:
    config = Config()
    model = None
    if config.OPENAI_API_KEY is not None:
        model = OpenAIResponsesModel(
            api_key=config.OPENAI_API_KEY.get_secret_value(),
            model_name=config.OPENAI_MODEL,
            base_url=config.OPENAI_BASE_URL,
            timeout_seconds=config.OPENAI_TIMEOUT_SECONDS,
        )
    return ChatbotService(
        model=model,
        input_usd_per_1m_tokens=config.LLM_INPUT_USD_PER_1M_TOKENS,
        output_usd_per_1m_tokens=config.LLM_OUTPUT_USD_PER_1M_TOKENS,
    )


@chatbot_router.post("/responses", response_model=ChatbotResponse)
async def create_chatbot_response(
    payload: ChatbotResponseRequest,
    link_digest: Annotated[str, Depends(require_patient_session_link)],
    service: Annotated[ChatbotService, Depends(get_chatbot_service)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ChatbotResponse:
    # 열쇠는 **있을 때만** 문지기를 세운다 — 옛 화면·스크립트는 안 보낸다
    # (KEY-328). 열쇠 없는 요청은 예전 그대로 돌고 멱등 보장이 없다.
    guard = (
        ChatbotSubmissionGuard(redis, submission_id=payload.submission_id, question=payload.question)
        if payload.submission_id is not None
        else None
    )
    result = await service.answer_for_link_digest(
        link_digest=link_digest,
        question=payload.question,
        guard=guard,
    )
    return ChatbotResponse(
        answer=result.answer,
        evidence=result.evidence,
        source=result.source,
        limitation=result.limitation,
        urgent=result.urgent,
        fallback=result.fallback,
        grounded_section=result.grounded_section,
        response_ref=result.response_ref,
    )
