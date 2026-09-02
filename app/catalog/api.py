"""약속처방 목록 — KEY-234.

읽기 전용이다. 목록을 고치는 것은 설정 화면(D2)의 몫이고, 그건 이 일감
범위 밖이다 — 여기서는 판독 확인 화면이 고를 수 있게 **주기만** 한다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.catalog.schemas import (
    PrescriptionSetDetail,
    PrescriptionSetResponse,
    SetDrug,
)
from app.core.api_errors import ApiError, ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.models.catalog import (
    PrescriptionCheckItem,
    PrescriptionSet,
    PrescriptionSetDrug,
)
from app.models.visits import VisitCheckKey

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

    # 확인 항목을 **한 번에** 읽는다. 세트마다 물으면 여덟 번 다녀온다.
    items = await PrescriptionCheckItem.all().order_by("position", "prescription_check_item_id")
    by_set: dict[int, list[VisitCheckKey]] = {}
    for item in items:
        by_set.setdefault(item.prescription_set_id, []).append(item.item_key)

    # 약도 **한 번에** 읽는다 — 확인 항목과 같은 이유다.
    drugs = await PrescriptionSetDrug.all().order_by("position", "prescription_set_drug_id")
    drugs_by_set: dict[int, list[SetDrug]] = {}
    for drug in drugs:
        drugs_by_set.setdefault(drug.prescription_set_id, []).append(
            SetDrug(name=drug.name, frequency=drug.frequency, note=drug.note)
        )

    return [
        PrescriptionSetResponse(
            prescription_set_id=row.prescription_set_id,
            name=row.name,
            disease=row.disease,
            check_items=by_set.get(row.prescription_set_id, []),
            drugs=drugs_by_set.get(row.prescription_set_id, []),
            days_mode=row.days_mode,
            days_per_pack=row.days_per_pack,
        )
        for row in rows
    ]


def _detail(row: PrescriptionSet, drugs: list[PrescriptionSetDrug], items: list) -> PrescriptionSetDetail:
    return PrescriptionSetDetail(
        prescription_set_id=row.prescription_set_id,
        name=row.name,
        disease=row.disease,
        phase=row.phase,
        days_mode=row.days_mode,
        days_per_pack=row.days_per_pack,
        emr_code=row.emr_code,
        revisit_note=row.revisit_note,
        check_d15_on=row.check_d15_on,
        check_d30_on=row.check_d30_on,
        run_out_on=row.run_out_on,
        run_out_before_days=row.run_out_before_days,
        drugs=[SetDrug(name=d.name, frequency=d.frequency, note=d.note) for d in drugs],
        check_items=[i.item_key for i in items],
    )


async def _load(prescription_set_id: int) -> PrescriptionSetDetail:
    row = await PrescriptionSet.filter(prescription_set_id=prescription_set_id).first()
    if row is None:
        raise ApiError(404, "PRESCRIPTION_SET_NOT_FOUND", "처방 세트를 찾을 수 없습니다.")

    drugs = await PrescriptionSetDrug.filter(prescription_set_id=prescription_set_id).order_by(
        "position", "prescription_set_drug_id"
    )
    items = await PrescriptionCheckItem.filter(prescription_set_id=prescription_set_id).order_by(
        "position", "prescription_check_item_id"
    )
    return _detail(row, list(drugs), list(items))


@catalog_router.get("/prescription-sets/{prescription_set_id}", response_model=PrescriptionSetDetail)
async def read_prescription_set(
    prescription_set_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
) -> PrescriptionSetDetail:
    """설정 화면(D2-3)이 읽는 한 세트.

    **보는 것은 스탭도 된다.** 어느 처방에 무엇이 딸려 있는지는 스탭이 판독
    화면에서 고를 때 알아야 하는 것이고, 고치는 것만 의사다.
    """
    return await _load(prescription_set_id)


# ── 처방 설정 저장은 아직 열지 않는다 ──────────────────────────────────
#
# `PUT /prescription-sets/{id}` 가 여기 있었다. 걷었다.
#
# `prescription_set` 표에는 `hospital_id` 가 없다 — 여덟 처방 유형을 **전
# 의원이 함께 쓴다**(`app/models/catalog.py`). 역할(의사)만 확인하고 쓰기를
# 열어 두었더니, 어느 의원 의사든 다른 모든 의원의 질환 분류 · 총투 해석
# (`days_mode`) · 소진 예정일 셈법을 바꿀 수 있었다. 그 값들이 안내문 문구와
# 문자 발송일을 정한다. 2heej 님이 `#183` 리뷰에서 찾아 주셨다.
#
# **표를 의원별로 가르는 것이 옳은 해결이다.** 다만 씨앗 데이터 · 이름
# `unique` · 기존 참조를 다 손봐야 해서 이 PR 밖으로 뺀다. 그때까지는 읽기
# 전용이다 — 화면(D2-3)도 `canEditSet` 으로 막아 두었다.
#
# 읽기(`GET`)는 그대로다. 어느 처방에 무엇이 딸려 있는지는 판독 화면에서
# 고를 때 스탭도 알아야 한다.

