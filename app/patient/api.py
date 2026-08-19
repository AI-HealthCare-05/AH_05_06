import json
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import StreamingResponse

from app.core import config
from app.core.config import Env
from app.dependencies.security import get_request_user
from app.models.users import User
from app.patient.chatbot import ApprovedKnowledgeChatbot
from app.patient.container import chatbot, service
from app.patient.schemas import (
    ChatRequest,
    FollowUpResponseSchema,
    FollowUpSubmitRequest,
    GuidanceResponse,
    IssueLinkRequest,
    LinkInspectionResponse,
    LinkManagementResponse,
    LinkTokenRequest,
    OtpRequestedResponse,
    ReissueLinkRequest,
    VerifyOtpRequest,
)
from app.patient.service import PatientFlowService

SESSION_COOKIE = "patient_session"

patient_management_router = APIRouter(prefix="/patient-links", tags=["patient-links"])
patient_router = APIRouter(prefix="/patient", tags=["patient"])


def get_patient_service() -> PatientFlowService:
    return service


def get_chatbot() -> ApprovedKnowledgeChatbot:
    return chatbot


@patient_management_router.post("", response_model=LinkManagementResponse, status_code=status.HTTP_201_CREATED)
async def issue_link(
    request: IssueLinkRequest,
    _: Annotated[User, Depends(get_request_user)],
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
) -> LinkManagementResponse:
    link = await flow.issue_link(
        request.care_episode_id,
        request.phone_number,
        request.birth_date,
        request.send_at,
        request.purpose,
    )
    return LinkManagementResponse(id=link.id, state=link.state, send_at=link.send_at, expires_at=link.expires_at)


@patient_management_router.post("/dispatch-due", status_code=status.HTTP_200_OK)
async def dispatch_due(
    _: Annotated[User, Depends(get_request_user)],
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
) -> dict[str, int]:
    return {"sent": await flow.dispatch_due_links()}


@patient_management_router.post("/{link_id}/revoke", response_model=LinkManagementResponse)
async def revoke_link(
    link_id: str,
    _: Annotated[User, Depends(get_request_user)],
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
) -> LinkManagementResponse:
    link = flow.revoke_link(link_id)
    return LinkManagementResponse(id=link.id, state=link.state, send_at=link.send_at, expires_at=link.expires_at)


@patient_management_router.get("/{link_id}/follow-up", response_model=FollowUpResponseSchema)
async def get_follow_up_for_staff(
    link_id: str,
    _: Annotated[User, Depends(get_request_user)],
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
) -> FollowUpResponseSchema:
    saved = flow.get_follow_up_for_staff(link_id)
    return FollowUpResponseSchema.model_validate(saved, from_attributes=True)


@patient_router.post("/auth/link", response_model=LinkInspectionResponse)
async def inspect_link(
    request: LinkTokenRequest,
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
) -> LinkInspectionResponse:
    link = flow.inspect_link(request.token)
    return LinkInspectionResponse(
        masked_phone=f"010-****-{link.phone_last4}",
        encounter_date=link.encounter_date,
        expires_at=link.expires_at,
        purpose=link.purpose,
    )


@patient_router.post("/auth/otp", response_model=OtpRequestedResponse)
async def request_otp(
    request: LinkTokenRequest,
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
) -> OtpRequestedResponse:
    link = flow.inspect_link(request.token)
    challenge = await flow.request_otp(request.token)
    return OtpRequestedResponse(
        challenge_id=challenge.id,
        expires_at=challenge.expires_at,
        masked_phone=f"010-****-{link.phone_last4}",
    )


@patient_router.post("/auth/verify", status_code=status.HTTP_200_OK)
async def verify_otp(
    request: VerifyOtpRequest,
    response: Response,
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
) -> dict[str, object]:
    session, raw_session = flow.verify_otp(request.challenge_id, request.code)
    response.set_cookie(
        SESSION_COOKIE,
        raw_session,
        httponly=True,
        secure=config.ENV == Env.PROD,
        samesite="strict",
        path="/api/v1/patient",
    )
    return {"authenticated": True, "expires_at": session.expires_at}


@patient_router.post("/auth/reissue", response_model=LinkManagementResponse, status_code=status.HTTP_201_CREATED)
async def reissue_link(
    request: ReissueLinkRequest,
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
) -> LinkManagementResponse:
    link = await flow.reissue_link(request.token, request.phone_number, request.birth_date)
    return LinkManagementResponse(id=link.id, state=link.state, send_at=link.send_at, expires_at=link.expires_at)


@patient_router.get("/guidance", response_model=GuidanceResponse)
async def get_guidance(
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
    patient_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> GuidanceResponse:
    bundle = flow.guidance(patient_session)
    return GuidanceResponse.model_validate(bundle, from_attributes=True)


@patient_router.post("/chat/stream")
async def stream_chat(
    request: ChatRequest,
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
    rag: Annotated[ApprovedKnowledgeChatbot, Depends(get_chatbot)],
    patient_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> StreamingResponse:
    bundle = flow.guidance(patient_session)
    grounded = rag.answer(request.question, bundle)

    async def events():
        yield f"event: limitation\ndata: {json.dumps({'text': grounded.limitation}, ensure_ascii=False)}\n\n"
        async for chunk in rag.stream(request.question, bundle):
            yield f"event: delta\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        for evidence in grounded.evidence:
            yield f"event: evidence\ndata: {json.dumps(evidence.__dict__, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@patient_router.get("/follow-up")
async def get_follow_up(
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
    patient_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict[str, object]:
    return flow.follow_up_status(patient_session)


@patient_router.post("/follow-up", response_model=FollowUpResponseSchema, status_code=status.HTTP_201_CREATED)
async def submit_follow_up(
    request: FollowUpSubmitRequest,
    flow: Annotated[PatientFlowService, Depends(get_patient_service)],
    patient_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> FollowUpResponseSchema:
    saved = flow.submit_follow_up(
        patient_session,
        request.adherence,
        request.has_pain,
        request.pain_score,
        request.pain_types,
        request.memo,
    )
    return FollowUpResponseSchema.model_validate(saved, from_attributes=True)
