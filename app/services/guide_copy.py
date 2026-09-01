"""안내문 고치기 — 와이어프레임 D2-1 · D2-2.

**원본 위에 표현을 덧씌운다.** 원문 주석: 「의사마다 말하는 방식이 다르고
같은 의사도 일정하지 않다. 문구를 하나로 강제하면 원장님이 안 쓰신다. 대신
원본을 위에 두어 무엇이 사실이고 무엇이 표현인지 보이게 한다.」

**원본은 손대지 않는다.** `DrugCautionContent` 는 근거(출처 · 등급 · 검증일)와
승인이 붙은 자료다 — 그것을 고치면 「무엇이 사실인가」를 잃는다. 되돌리기가
줄을 지우는 일인 것도 그래서다.

**🚨 응급 문구는 열리지 않는다.** 원문: 「🚨 문구는 이 화면이 열리지 않는다」.
표현을 다듬는 자리이지 안전 문장을 고치는 자리가 아니다.
"""

from dataclasses import dataclass

from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor
from app.models.catalog import (
    ApprovalStatus,
    CautionSectionKey,
    DoctorGuideCopy,
    DoctorGuideReview,
    DrugCautionContent,
    PrescriptionSet,
)
from app.services.patient_visit_scope import hospital_id_of

#: 의사가 고칠 수 있는 구역. **응급은 없다** — 원문이 못박는다.
EDITABLE_SECTIONS = (CautionSectionKey.CAUTION,)


@dataclass(frozen=True, slots=True)
class CopySection:
    section_key: CautionSectionKey
    #: 승인된 원본. 없을 수 있다 — 그 세트에 아직 승인 문구가 없다는 뜻이다.
    origin: str | None
    #: 원장님 문구. 없으면 원본이 그대로 나간다.
    body: str | None
    editable: bool


@dataclass(frozen=True, slots=True)
class CopySet:
    prescription_set_id: int
    name: str
    disease: str
    sections: list[CopySection]
    reviewed: bool


class GuideCopyService:
    async def list(self, actor: ClinicalActor, *, doctor_id: int) -> list[CopySet]:
        hospital_id = hospital_id_of(actor)
        sets = await PrescriptionSet.all().order_by("disease", "prescription_set_id")
        origins = await self._origins()
        edits = await self._edits(hospital_id, doctor_id)
        reviewed = await self._reviewed(hospital_id, doctor_id)

        found = []
        for row in sets:
            found.append(
                CopySet(
                    prescription_set_id=row.prescription_set_id,
                    name=row.name,
                    disease=str(row.disease),
                    sections=[
                        CopySection(
                            section_key=key,
                            origin=origins.get((row.prescription_set_id, key)),
                            body=edits.get((row.prescription_set_id, key)),
                            editable=key in EDITABLE_SECTIONS,
                        )
                        for key in CautionSectionKey
                    ],
                    reviewed=row.prescription_set_id in reviewed,
                )
            )
        return found

    async def save(
        self,
        actor: ClinicalActor,
        *,
        doctor_id: int,
        prescription_set_id: int,
        section_key: CautionSectionKey,
        body: str,
    ) -> None:
        """원문: 「표현만 수정해 주세요 — 새로운 의학 정보를 추가할 수 없습니다」.

        그 말은 **사람에게 하는 부탁**이고 여기서 판정할 수 없다 — 무엇이 새
        의학 정보인지 기계가 가릴 수 없기 때문이다. 그래서 막는 것은 셋뿐이다:
        의사인가 · 고칠 수 있는 구역인가 · 비어 있지 않은가.
        """
        self._require_doctor(actor, doctor_id)
        if section_key not in EDITABLE_SECTIONS:
            raise ApiError(422, "SECTION_LOCKED", "이 문구는 안전을 위해 수정할 수 없습니다.")
        body = (body or "").strip()
        if not body:
            raise ApiError(400, "EMPTY_BODY", "문구를 비워 둘 수 없습니다.")

        hospital_id = hospital_id_of(actor)
        await self._exists(prescription_set_id)
        async with in_transaction() as connection:
            await DoctorGuideCopy.update_or_create(
                hospital_id=hospital_id,
                doctor_id=doctor_id,
                prescription_set_id=prescription_set_id,
                section_key=section_key,
                defaults={"body": body, "updated_by": actor.staff_id},
                using_db=connection,
            )
            # **고치면 확인이 풀린다.** 「확인 완료」가 붙은 채로 바뀐 글이
            # 나가면 그 표시가 거짓말이 된다.
            await (
                DoctorGuideReview.filter(
                    hospital_id=hospital_id, doctor_id=doctor_id, prescription_set_id=prescription_set_id
                )
                .using_db(connection)
                .delete()
            )

    async def revert(
        self,
        actor: ClinicalActor,
        *,
        doctor_id: int,
        prescription_set_id: int,
        section_key: CautionSectionKey,
    ) -> None:
        """**줄을 지운다.** 원본을 베껴 넣지 않는 이유는, 그러면 원본이 개정돼도
        되돌린 의사만 옛 글을 계속 쓰기 때문이다."""
        self._require_doctor(actor, doctor_id)
        hospital_id = hospital_id_of(actor)
        await DoctorGuideCopy.filter(
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            prescription_set_id=prescription_set_id,
            section_key=section_key,
        ).delete()
        await DoctorGuideReview.filter(
            hospital_id=hospital_id, doctor_id=doctor_id, prescription_set_id=prescription_set_id
        ).delete()

    async def review(self, actor: ClinicalActor, *, doctor_id: int, prescription_set_id: int) -> None:
        """원문 「확인 완료」 — 한 장을 다 봤다는 표시다."""
        self._require_doctor(actor, doctor_id)
        await self._exists(prescription_set_id)
        await DoctorGuideReview.get_or_create(
            hospital_id=hospital_id_of(actor),
            doctor_id=doctor_id,
            prescription_set_id=prescription_set_id,
        )

    @staticmethod
    async def _exists(prescription_set_id: int) -> None:
        if not await PrescriptionSet.filter(prescription_set_id=prescription_set_id).exists():
            raise ApiError(404, "PRESCRIPTION_SET_NOT_FOUND", "처방을 찾을 수 없습니다.")

    @staticmethod
    def _require_doctor(actor: ClinicalActor, doctor_id: int) -> None:
        """원문 부제: 「의사 계정만 · 스탭은 볼 수만 있다」.

        **남의 이름으로 고치는 것도 막는다.** 문구가 그 의사 담당 환자에게
        나가므로, 다른 의사 문구를 고치는 것은 그 사람 이름으로 말하는 일이다.
        """
        if "doctor" not in actor.roles:
            raise ApiError(403, "DOCTOR_ONLY", "안내문 문구는 의사 계정만 수정할 수 있습니다.")
        if actor.staff_id != doctor_id:
            raise ApiError(403, "OTHER_DOCTOR", "다른 의사의 문구는 수정할 수 없습니다.")

    @staticmethod
    async def _origins() -> dict[tuple[int, CautionSectionKey], str]:
        """**승인된 것만 원본이다.** 초안이나 폐기된 문구를 「원본」이라 보이면
        의사가 그것을 사실로 읽는다."""
        rows = await DrugCautionContent.filter(approval_status=ApprovalStatus.APPROVED).values_list(
            "prescription_set_id", "section_key", "body"
        )
        return {(set_id, CautionSectionKey(key)): body for set_id, key, body in rows}

    @staticmethod
    async def _edits(hospital_id: int, doctor_id: int) -> dict[tuple[int, CautionSectionKey], str]:
        rows = await DoctorGuideCopy.filter(hospital_id=hospital_id, doctor_id=doctor_id).values_list(
            "prescription_set_id", "section_key", "body"
        )
        return {(set_id, CautionSectionKey(key)): body for set_id, key, body in rows}

    @staticmethod
    async def _reviewed(hospital_id: int, doctor_id: int) -> set[int]:
        return set(
            await DoctorGuideReview.filter(hospital_id=hospital_id, doctor_id=doctor_id).values_list(
                "prescription_set_id", flat=True
            )
        )
