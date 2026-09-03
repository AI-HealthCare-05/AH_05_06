"""약속처방 목록 — KEY-234.

읽기 전용이다. 목록을 고치는 것은 설정 화면(D2)의 몫이고, 그건 이 일감
범위 밖이다 — 여기서는 판독 확인 화면이 고를 수 있게 **주기만** 한다.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.catalog.schemas import (
    PrescriptionSetCreateRequest,
    PrescriptionSetDetail,
    PrescriptionSetResponse,
    PrescriptionSetSaveRequest,
    SetDrug,
)
from app.core.api_errors import ApiError, ContractRoute
from app.dependencies.patient_access import ClinicalActor, require_patient_read
from app.models.catalog import (
    PrescriptionCheckItem,
    PrescriptionSet,
    PrescriptionSetDrug,
    SetDaysMode,
    SetStatus,
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
            hidden=row.status is SetStatus.HIDDEN,
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
        hidden=row.status is SetStatus.HIDDEN,
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
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
) -> PrescriptionSetDetail:
    """설정을 저장한다 — 진단 · 약 · 확인 항목 · 자동 발송까지 한 판.

    **이름은 못 바꾼다.** 지난 진료기록이 그 이름으로 이 세트를 가리키고 있다
    (`app/models/prescriptions.py:70` 스냅샷 문자열 · `app/services/guides.py`
    와 `app/services/drug_caution.py` 가 `filter(name=…)` 으로 찾는다).
    바꾸면 그 진료들의 안내문 문구가 조용히 떨어져 나간다. 잘못 지은 이름은
    **숨기고 새로 만든다** — 의료 데이터라 지우지도 않는다.

    **의원 하나를 보는 프로그램이다**(2026-09-02 회의). 처방 여덟은 그 의원의
    것이고 한 의원 안의 의사들이 모두 공통으로 쓴다. 그래서 「누구 것인가」를
    묻지 않는다. 역할도 안 본다 — 같은 회의에서 설정 수정을 스탭에게도 열었다.

    한동안 이 경로가 걷혀 있었다. 여러 의원이 한 표를 나눠 쓰는 모양이라 남의
    의원 것까지 바뀌었기 때문이다(`#183` 리뷰, 2heej). 의원이 하나라는 것이
    정해지면서 그 걱정이 범위 밖으로 갔다 — **고친 것이 아니라 범위가 줄어든
    것이다.** 의원이 둘이 되는 날 `prescription_set` 에 의원 칸부터 만든다.

    **한 판을 통째로 받는다.** 약을 지우고 확인 항목을 켜는 것이 한 번의
    「저장」인데, 조각으로 받으면 중간에 끊겼을 때 반쪽이 남는다.
    """
    row = await PrescriptionSet.filter(prescription_set_id=prescription_set_id).first()
    if row is None:
        raise ApiError(404, "PRESCRIPTION_SET_NOT_FOUND", "처방 세트를 찾을 수 없습니다.")

    # 통·상자 수로 세는데 한 통이 며칠인지 모르면 소진 예정일을 셈할 수 없다.
    if payload.days_mode is SetDaysMode.PACK and not payload.days_per_pack:
        raise ApiError(422, "DAYS_PER_PACK_REQUIRED", "한 통이 며칠치인지 적어 주세요.")

    async with in_transaction() as connection:
        # 이름은 안 바꾼다 — 스키마가 애초에 안 받는다. 까닭은 거기 적었다.
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


def _clean_name(raw: str) -> str:
    """이름을 **한 가지 꼴로 다듬는다.**

    `utf8mb4_0900_ai_ci` 는 NO PAD 라 앞뒤 공백이 다르면 `unique` 가 **안
    막는다.** 「비잔 (계속)」과 「비잔 (계속) 」이 나란히 앉고, 화면에서는
    눈으로 구별되지 않는다. 엑셀이나 메신저에서 붙여 넣으면 흔히 붙는다.

    가운데 겹공백도 접는다 — 같은 이유로 다른 이름이 되는데 눈으로는 같다.
    이름은 한 번 정하면 못 바꾸므로 **들어올 때 다듬는 수밖에 없다.**
    """
    return " ".join(raw.split())


@catalog_router.post("/prescription-sets", response_model=PrescriptionSetDetail, status_code=201)
async def create_prescription_set(
    payload: PrescriptionSetCreateRequest,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
) -> PrescriptionSetDetail:
    """새 처방을 만든다.

    **이름은 만들 때 한 번만 정한다.** 지난 진료기록이 이 이름으로 이 세트를
    가리키게 되므로 나중에는 못 바꾼다. 잘못 지었으면 숨기고 새로 만든다.

    같은 이름은 막는다. `filter(name=…).first()` 에는 `ORDER BY` 가 없어서
    같은 이름이 둘이면 **어느 세트로 풀릴지 모르고**, 그 갈림이 곧 안내문
    문구가 갈리는 것이다. **감춘 세트의 이름도 못 쓴다** — 그 이름을 든
    진료기록이 이미 있다.
    """
    name = _clean_name(payload.name)
    if not name:
        raise ApiError(422, "NAME_REQUIRED", "처방 이름을 적어 주세요.")

    if await PrescriptionSet.filter(name=name).exists():
        raise ApiError(409, "PRESCRIPTION_SET_EXISTS", "같은 이름의 처방이 이미 있습니다.")

    try:
        row = await PrescriptionSet.create(name=name, disease=payload.disease)
    except IntegrityError as clash:
        # 위 확인과 여기 사이가 갈릴 수 있다. `unique` 가 마지막 자물쇠다.
        raise ApiError(409, "PRESCRIPTION_SET_EXISTS", "같은 이름의 처방이 이미 있습니다.") from clash

    return await _load(row.prescription_set_id)


@catalog_router.post("/prescription-sets/{prescription_set_id}/hide", response_model=PrescriptionSetDetail)
async def hide_prescription_set(
    prescription_set_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
) -> PrescriptionSetDetail:
    """처방을 감춘다 — **지우지 않는다.**

    의료 데이터라 삭제가 금지된다. 여기서는 이유가 하나 더 있다: 지난
    진료기록이 이 세트를 **이름 문자열로** 가리키므로, 행이 사라지면 그
    진료들의 안내문 문구가 조용히 떨어진다.

    감춘 뒤에도 **그 진료들에는 문구가 그대로 붙는다.** 감춤은 「새로 못
    고른다」는 뜻이지 「없다」가 아니다.
    """
    row = await PrescriptionSet.filter(prescription_set_id=prescription_set_id).first()
    if row is None:
        raise ApiError(404, "PRESCRIPTION_SET_NOT_FOUND", "처방 세트를 찾을 수 없습니다.")

    if row.status is not SetStatus.HIDDEN:
        row.status = SetStatus.HIDDEN
        row.hidden_at = datetime.now(UTC)
        await row.save()

    return await _load(prescription_set_id)


@catalog_router.post("/prescription-sets/{prescription_set_id}/unhide", response_model=PrescriptionSetDetail)
async def unhide_prescription_set(
    prescription_set_id: int,
    actor: Annotated[ClinicalActor, Depends(require_patient_read)],
) -> PrescriptionSetDetail:
    """감춘 처방을 되살린다. 다시 고를 수 있게 된다."""
    row = await PrescriptionSet.filter(prescription_set_id=prescription_set_id).first()
    if row is None:
        raise ApiError(404, "PRESCRIPTION_SET_NOT_FOUND", "처방 세트를 찾을 수 없습니다.")

    if row.status is not SetStatus.ACTIVE:
        row.status = SetStatus.ACTIVE
        row.hidden_at = None
        await row.save()

    return await _load(prescription_set_id)
