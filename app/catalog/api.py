"""약속처방 목록 — KEY-234.

읽기 전용이다. 목록을 고치는 것은 설정 화면(D2)의 몫이고, 그건 이 일감
범위 밖이다 — 여기서는 판독 확인 화면이 고를 수 있게 **주기만** 한다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.api_errors import ContractRoute
from app.catalog.schemas import PrescriptionSetResponse
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.models.catalog import PrescriptionSet

catalog_router = APIRouter(tags=["catalog"], route_class=ContractRoute)


@catalog_router.get("/prescription-sets", response_model=list[PrescriptionSetResponse])
async def list_prescription_sets(
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
) -> list[PrescriptionSetResponse]:
    """약속처방 목록을 이름순으로 준다.

    **병원별로 가르지 않는다.** `prescription_set` 표에 `hospital_id` 가 없다 —
    지금은 8종이 전 병원 공통이다. 병원마다 다르게 두려면 표에 칸을 더하고
    여기서 걸러야 한다. 그때까지 이 주석이 그 사실을 붙잡아 둔다.

    로그인은 필요하다. 처방 세트 이름 자체가 이 의원이 무엇을 다루는지를
    말해 주고, 그건 밖에 흘릴 것이 아니다.
    """
    rows = await PrescriptionSet.all().order_by("prescription_set_id")
    return [
        PrescriptionSetResponse(prescription_set_id=row.prescription_set_id, name=row.name)
        for row in rows
    ]
