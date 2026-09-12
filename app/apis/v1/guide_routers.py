"""안내문 검토·승인·반려 — KEY-111 (와이어프레임 D1-1~D1-5).

권한은 **서비스가 판단한다**(`app/services/guides.py`) — 라우터는 누가 왔는지만
넘긴다. 「승인은 의사만」은 규칙이고, 규칙은 서비스에 있다(`docs/models-layout.md`).
"""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.time import DISPLAY_TIMEZONE
from app.dependencies.staff_auth import StaffActor, get_staff_actor
from app.dtos.guides import (
    GuidePreview,
    GuideResponse,
    MessagePlanRequest,
    MessagePlanResponse,
    PatientHead,
    ReturnRequest,
    SectionEditRequest,
    SectionOrderRequest,
    SectionResponse,
)
from app.models.visits import GuideDocument, GuideSection, GuideSectionKey
from app.services import guide_section_order
from app.services.guides import GuideService
from app.services.patient_guide_view import guide_detail_of
from app.services.patient_links import PatientLinkService

guide_router = APIRouter(prefix="/visits", tags=["guides"])


def _service() -> GuideService:
    return GuideService()


def _age_on(birth_date: date, today: date) -> int:
    """만 나이. 생일이 아직 안 지났으면 한 살 뺀다.

    계약 §4 — 「`age` 는 저장값이 아니라 **요청한 현지 날짜**와 `birth_date` 로
    계산한다」. 저장해 두면 시간이 지나면서 조용히 틀린 값이 된다.
    """
    before_birthday = (today.month, today.day) < (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (1 if before_birthday else 0)


async def _preview_of(guide: GuideDocument) -> GuidePreview:
    """미리보기가 그리는 카드 — **환자 종점이 짓는 그 파생 그대로** (KEY-294).

    승인 여부를 안 본다. 스탭·의사는 **승인 전에** 이 화면에서 검토하고,
    검토가 이 화면의 일이다. 환자 쪽 게이트(링크·만료·승인)는 환자 종점이
    제 자리에서 그대로 친다.

    **`guide` 만 비고 봉투는 남는다.** 처방도 목표도 없으면 `guide` 가 `null`
    인데, 그때도 진료일은 있다 — 환자 화면의 「나의 목표」 카드는 값이 없어도
    서고 머리에 진료일을 단다(`if (d.visit)`). 봉투째 비우면 미리보기만 그
    날짜를 잃는다.
    """
    data = await PatientLinkService().build_patient_guide_data(guide)
    return GuidePreview(visit=data.visit_date.strftime("%Y.%m.%d"), guide=guide_detail_of(data))


async def _to_response(guide: GuideDocument, *, with_preview: bool = False) -> GuideResponse:
    """**미리보기는 부르는 쪽이 필요할 때만 짓는다.**

    `_preview_of` 는 다섯 질의를 돈다. 상태를 바꾸는 종점
    (`generate`·`submit`·`approve`·`unapprove`·`return`)의 응답은 화면이
    **쓰지 않는다** — 전부 곧바로 `GET /guide` 를 다시 불러 그리므로, 붙여
    두면 상태 전환 한 번에 그 다섯 질의가 두 벌 돈다 (이희진 님 `#272`).
    """
    visit = guide.visit
    patient = visit.patient
    today = datetime.now(DISPLAY_TIMEZONE).date()
    return GuideResponse(
        visit_id=guide.visit_id,
        patient=PatientHead(
            patient_id=patient.patient_id,
            name=patient.name,
            birth_date=patient.birth_date,
            age=_age_on(patient.birth_date, today),
            gender=patient.gender,
            hospital_patient_no=patient.hospital_patient_no,
        ),
        summary=visit.visit_summary,
        status=guide.status,
        version=guide.version,
        approved_at=guide.approved_at,
        scheduled_at=guide.scheduled_at,
        returned_reason=guide.returned_reason,
        sections=[_section(s) for s in sorted(guide.sections, key=_section_order)],
        preview=await _preview_of(guide) if with_preview else None,
    )


def _section_order(section: GuideSection) -> tuple[int, int]:
    """**차례를 삽입 순서에 맡기지 않는다.**

    예전에는 `guide_section_id` 로 정렬했다. 지금 생성 경로가 계약 순서대로
    넣으니 결과는 같지만, 그건 **우연히 같은 것**이다. 행 하나를 나중에
    끼워 넣으면(예: 기존 안내문에 `emergency` 를 채워 넣는 backfill) 그 행이
    맨 뒤로 가고, 응급 문장이 문자 설정 뒤에 붙는다 (KEY-161).

    그 뒤로 차례는 **사람이 정할 수 있는 것**이 됐다(KEY-317). 계약 표는
    이제 기본값일 뿐이라 표에서 읽으면 사람이 바꾼 차례가 안 보인다 —
    저장된 `display_order` 에서 읽는다. 같은 값이 둘이면(있을 수 없지만)
    행 번호로 갈라 **답이 매번 같게** 한다.
    """
    return (section.display_order, section.guide_section_id)


def _section(section: GuideSection) -> SectionResponse:
    return SectionResponse(
        key=section.section_key,
        movable=GuideSectionKey(section.section_key) not in guide_section_order.SAFETY_SECTIONS,
        body=section.body,
        edited=section.edited_body is not None,
        locked=section.locked,
        warn=section.warn,
    )


@guide_router.post("/{visit_id}/guide/generate", response_model=GuideResponse, status_code=status.HTTP_201_CREATED)
async def generate_guide(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
    discard_edits: bool = False,
) -> GuideResponse:
    """**고친 문구가 있으면 묻고 멈춘다** — `discard_edits=true` 로 다시 부른다.

    다시 만들면 절이 통째로 새로 써진다. 스탭이 이미 바로잡은 문장이 붙어
    있으면 그것이 말없이 사라지므로, 기본값은 **멈추는 쪽**이다(409
    `GUIDE_HAS_EDITS`). 화면이 「고친 것을 버리고 다시 만들까요」를 묻고, 사람이
    그렇다고 하면 이 값을 켜서 다시 부른다 (이희진 님 `#221` ①).
    """
    guide = await service.generate(actor, visit_id, discard_edits=discard_edits)
    await guide.fetch_related("sections", "visit__patient")
    return await _to_response(guide)


@guide_router.get("/{visit_id}/guide", response_model=GuideResponse)
async def read_guide(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    return await _to_response(await service.get(actor, visit_id), with_preview=True)


@guide_router.patch("/{visit_id}/guide/sections/{key}", response_model=SectionResponse)
async def edit_section(
    visit_id: int,
    key: str,
    body: SectionEditRequest,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> SectionResponse:
    return _section(await service.edit_section(actor, visit_id, key, body.body))


@guide_router.put("/{visit_id}/guide/sections/order", response_model=GuideResponse, status_code=status.HTTP_200_OK)
async def reorder_sections(
    visit_id: int,
    body: SectionOrderRequest,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    """절의 **차례**를 바꾼다 — KEY-317.

    `PATCH` 가 아니라 `PUT` 이다. 한 절을 고치는 것이 아니라 **차례 전체를**
    통째로 놓는 것이라, 같은 목록을 두 번 보내면 두 번째는 아무 일도 안 한다.

    답으로 안내문 전체를 준다. 차례가 바뀌면 화면이 다시 그려야 하는데,
    바뀐 차례만 주면 화면이 제 손으로 다시 늘어놓아야 한다 — 그러면 서버가
    아는 차례와 화면이 그린 차례가 갈릴 자리가 생긴다.
    """
    return await _to_response(await service.reorder_sections(actor, visit_id, [key.value for key in body.order]))


@guide_router.post("/{visit_id}/guide/submit", response_model=GuideResponse, status_code=status.HTTP_200_OK)
async def submit_guide(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    """스탭이 확인을 마치고 의사에게 넘긴다 — 와이어프레임 S1-11.

    이 자리가 없어서 안내문이 만들어지자마자 원장님 목록에 떴다.
    승인은 여전히 의사만 한다 (`/guide/approve`).
    """
    guide = await service.submit(actor, visit_id)
    await guide.fetch_related("sections", "visit__patient")
    return await _to_response(guide)


@guide_router.post("/{visit_id}/guide/approve", response_model=GuideResponse, status_code=status.HTTP_200_OK)
async def approve_guide(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    guide = await service.approve(actor, visit_id)
    await guide.fetch_related("sections", "visit__patient")
    return await _to_response(guide)


@guide_router.get("/{visit_id}/guide/messages", response_model=MessagePlanResponse, status_code=status.HTTP_200_OK)
async def read_message_plan(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> MessagePlanResponse:
    """이 진료의 문자 회차 설정 — 와이어프레임 S1-14.

    한 번도 안 만진 진료도 기본값으로 답한다. 「설정이 없다」와 「기본값이다」를
    화면이 가를 이유가 없다.
    """
    return MessagePlanResponse(**await service.message_plan(actor, visit_id))


@guide_router.put("/{visit_id}/guide/messages", response_model=MessagePlanResponse, status_code=status.HTTP_200_OK)
async def save_message_plan(
    visit_id: int,
    payload: MessagePlanRequest,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> MessagePlanResponse:
    """문자 설정을 저장한다 — 「이 환자만 적용」.

    **한 판을 통째로 받는다.** 회차 하나씩 PATCH 로 받으면, 중간에 끊겼을 때
    「보름 뒤는 껐는데 한 달 뒤는 안 켜진」 반쪽 상태가 남는다.
    """
    return MessagePlanResponse(**await service.save_message_plan(actor, visit_id, payload))


@guide_router.post("/{visit_id}/guide/unapprove", response_model=GuideResponse, status_code=status.HTTP_200_OK)
async def unapprove_guide(
    visit_id: int,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    """승인을 거둔다 — 승인했는데 잘못된 것을 발견했을 때.

    이미 나간 문자가 있으면 거두지 않는다. 예약된 문자는 꺼진다.
    """
    guide = await service.unapprove(actor, visit_id)
    await guide.fetch_related("sections", "visit__patient")
    return await _to_response(guide)


@guide_router.post("/{visit_id}/guide/return", response_model=GuideResponse, status_code=status.HTTP_200_OK)
async def return_guide(
    visit_id: int,
    body: ReturnRequest,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
    service: Annotated[GuideService, Depends(_service)],
) -> GuideResponse:
    guide = await service.return_to_staff(actor, visit_id, body.reason)
    await guide.fetch_related("sections", "visit__patient")
    return await _to_response(guide)
