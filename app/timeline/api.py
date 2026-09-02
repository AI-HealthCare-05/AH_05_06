"""진료 처리 이력 — KEY-234, 와이어프레임 D1-6.

읽기 전용이다. 이 화면은 **기록을 만들지 않는다** — 기록은 각자의 일을
하는 자리(안내문 수정 · 승인 · 환자 열람)가 남긴다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.core.api_errors import ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.timeline.schemas import TimelineResponse
from app.timeline.service import TimelineService

timeline_router = APIRouter(tags=["timeline"], route_class=ContractRoute)


@timeline_router.get("/visits/{visit_id}/timeline", response_model=TimelineResponse)
async def read_timeline(
    visit_id: Annotated[int, Path(gt=0)],
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
) -> TimelineResponse:
    """이 진료에 무슨 일이 있었는지 시간 순으로 준다.

    **스탭도 본다.** 무엇이 밀려 있는지 알아야 하는 것은 스탭도 같다
    (D1-6 캡션 — 「스탭도 이 화면을 볼 수 있다」).
    """
    return await TimelineService().read(actor, visit_id)
