"""약속처방 목록 — KEY-234.

읽기 전용이다. 목록을 고치는 것은 설정 화면(D2)의 몫이고, 그건 이 일감
범위 밖이다 — 여기서는 판독 확인 화면이 고를 수 있게 **주기만** 한다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from tortoise.transactions import in_transaction

from app.catalog.schemas import (
    PrescriptionSetDetail,
    PrescriptionSetResponse,
    PrescriptionSetSaveRequest,
    SetDrug,
)
from app.core.api_errors import ApiError, ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.dependencies.staff_auth import StaffActor, get_staff_actor
from app.models.catalog import (
    PrescriptionCheckItem,
    PrescriptionSet,
    PrescriptionSetDrug,
    SetDaysMode,
)
from app.models.staffs import StaffRole
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


@catalog_router.put("/prescription-sets/{prescription_set_id}", response_model=PrescriptionSetDetail)
async def save_prescription_set(
    prescription_set_id: int,
    payload: PrescriptionSetSaveRequest,
    actor: Annotated[StaffActor, Depends(get_staff_actor)],
) -> PrescriptionSetDetail:
    """설정을 저장한다 — **의사만**.

    와이어프레임 D2-2 가 「의사 계정만 · 스탭은 볼 수만 있다」로 못박는다.
    이 값이 안내문과 문자 발송일을 정하므로 의료 판단에 걸린다.

    **한 판을 통째로 받는다.** 약을 지우고 확인 항목을 켜는 것이 한 번의
    「저장」인데, 조각으로 받으면 중간에 끊겼을 때 반쪽이 남는다.
    """
    if StaffRole.DOCTOR.value not in {str(r) for r in (actor.roles or [])}:
        raise ApiError(403, "FORBIDDEN", "처방 설정은 의사 계정만 고칠 수 있습니다.")

    row = await PrescriptionSet.filter(prescription_set_id=prescription_set_id).first()
    if row is None:
        raise ApiError(404, "PRESCRIPTION_SET_NOT_FOUND", "처방 세트를 찾을 수 없습니다.")

    # 통·상자 수로 세는데 한 통이 며칠인지 모르면 소진 예정일을 셈할 수 없다.
    if payload.days_mode is SetDaysMode.PACK and not payload.days_per_pack:
        raise ApiError(422, "DAYS_PER_PACK_REQUIRED", "한 통이 며칠치인지 적어 주세요.")

    async with in_transaction() as connection:
        row.name = payload.name.strip()
        row.disease = payload.disease
        row.phase = payload.phase
        row.days_mode = payload.days_mode
        row.days_per_pack = payload.days_per_pack if payload.days_mode is SetDaysMode.PACK else None
        row.emr_code = (payload.emr_code or "").strip() or None
        row.revisit_note = (payload.revisit_note or "").strip() or None
        row.check_d15_on = payload.check_d15_on
        row.check_d30_on = payload.check_d30_on
        row.run_out_on = payload.run_out_on
        row.run_out_before_days = payload.run_out_before_days
        await row.save(using_db=connection)

        # 약과 확인 항목은 **지우고 다시 넣는다.** 줄마다 번호를 주고받으면
        # 화면이 그 번호를 들고 다녀야 하고, 지운 줄을 놓치면 유령이 남는다.
        await PrescriptionSetDrug.filter(prescription_set_id=prescription_set_id).using_db(connection).delete()
        for i, drug in enumerate(payload.drugs):
            if not drug.name.strip():
                continue
            await PrescriptionSetDrug.create(
                prescription_set_id=prescription_set_id,
                name=drug.name.strip(),
                frequency=(drug.frequency or "").strip() or None,
                note=(drug.note or "").strip() or None,
                position=i,
                using_db=connection,
            )

        await PrescriptionCheckItem.filter(prescription_set_id=prescription_set_id).using_db(connection).delete()
        for i, key in enumerate(payload.check_items):
            await PrescriptionCheckItem.create(
                prescription_set_id=prescription_set_id,
                item_key=key,
                position=i,
                using_db=connection,
            )

    return await _load(prescription_set_id)
