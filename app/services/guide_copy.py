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

# **`list` 를 메서드 이름으로 쓰면 클래스 본문 안에서 내장 `list` 가 가려진다.**
# 그 뒤에 나오는 `list[Staff]` 같은 애너테이션이 그 메서드를 첨자로 읽어
# `TypeError: 'function' object is not subscriptable` 로 **import 가 터진다.**
#
# 호스트(3.14)는 애너테이션을 늦게 읽어 안 터지고 컨테이너(3.13)는 터졌다 —
# 검사가 호스트에서 돌아 통과했는데 서버는 아예 안 떴다. 이 한 줄이 판을
# 가리지 않고 애너테이션을 글자로 두어, 두 곳이 같게 돈다.
from __future__ import annotations

from dataclasses import dataclass

from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor
from app.models.catalog import (
    CautionSectionKey,
    DoctorGuideCopy,
    DoctorGuideReview,
    PrescriptionSet,
    SetDisease,
)
from app.services import guide_defaults
from app.services.drug_caution import DrugCautionService
from app.services.patient_visit_scope import hospital_id_of

#: 의사가 고칠 수 있는 구역. **응급은 없다** — 원문이 못박는다.
EDITABLE_SECTIONS = guide_defaults.EDITABLE_SECTIONS
"""고칠 수 있는 갈래 셋. **응급만 빠진다.**

원문 D2-2 가 「이 약을 왜 드시나요 [수정] · 먹는 방법 [수정] · 주의할 점
[수정] · 🚨 바로 병원에 오셔야 하는 경우 **수정 불가**」로 넷을 적어 두었다.
한동안 주의사항 하나만 열려 있었다 — 나머지 둘은 `guides.py` 에 문장이 박혀
있어 고칠 자리가 아예 없었다.
"""


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
    #: **코드가 아니라 뜻을 나른다.** DTO(`CopySetItem`)가 열거형을 요구하고,
    #: 화면은 이 값으로 묶음을 나눈다 — 문자열로 흘리면 오타가 조용히 지난다.
    disease: SetDisease
    sections: list[CopySection]
    reviewed: bool


class GuideCopyService:
    async def list(self, actor: ClinicalActor, *, doctor_id: int | None) -> list[CopySet]:
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
                    disease=row.disease,
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
        doctor_id: int | None,
        prescription_set_id: int,
        section_key: CautionSectionKey,
        body: str,
    ) -> None:
        """원문: 「표현만 수정해 주세요 — 새로운 의학 정보를 추가할 수 없습니다」.

        그 말은 **사람에게 하는 부탁**이고 여기서 판정할 수 없다 — 무엇이 새
        의학 정보인지 기계가 가릴 수 없기 때문이다. 그래서 막는 것은 셋뿐이다:
        의사인가 · 고칠 수 있는 구역인가 · 비어 있지 않은가.
        """
        self._require_owner(actor, doctor_id)
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
        doctor_id: int | None,
        prescription_set_id: int,
        section_key: CautionSectionKey,
    ) -> None:
        """**줄을 지운다.** 원본을 베껴 넣지 않는 이유는, 그러면 원본이 개정돼도
        되돌린 의사만 옛 글을 계속 쓰기 때문이다."""
        self._require_owner(actor, doctor_id)
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

    async def review(self, actor: ClinicalActor, *, doctor_id: int | None, prescription_set_id: int) -> None:
        """원문 「확인 완료」 — 한 장을 다 봤다는 표시다."""
        self._require_owner(actor, doctor_id)
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
    def _require_owner(actor: ClinicalActor, doctor_id: int | None) -> None:
        """**막는 것은 「남의 이름으로 고치는 것」 하나다.**

        원문 D2-2 는 「의사 계정만 · 스탭은 볼 수만 있다」였는데, 2026-09-02
        회의에서 **설정 화면의 수정 권한을 스탭에게도 연다**고 정했다. 그래서
        역할은 더 이상 문을 막지 않는다.

        남는 규칙 하나는 그대로다 — 개인 문구는 **그 사람 이름으로** 환자에게
        가므로, 남의 것을 고치는 것은 그 사람 이름으로 말하는 일이다.

        **의원 공통(`None`)은 같은 의원 사람이면 고친다.** 그것은 누구의
        이름도 아니고 의원의 기준선이다 — `lab_baselines.py` 가 같은 규칙을
        쓴다. 막아 두면 **아무도 못 고치는 판**이 되어, 설정에서 처음 여는
        문구를 어느 계정으로도 손댈 수 없게 된다.
        """
        if doctor_id is None:
            return
        if actor.staff_id != doctor_id:
            raise ApiError(403, "OTHER_DOCTOR", "다른 사람의 문구는 수정할 수 없습니다.")

    @staticmethod
    async def _origins() -> dict[tuple[int, CautionSectionKey], str]:
        """**생성이 쓸 글만 원본이다.** 초안이나 폐기된 문구를 「원본」이라
        보이면 의사가 그것을 사실로 읽는다.

        세트별 문구가 없는 자리는 **기본 문구**를 보인다
        (`guide_defaults.BY_SECTION`). 안내문 생성이 그때 쓰는 글이 그것이라,
        여기서 빈칸을 보이면 「원본이 없다」로 읽히는데 실제로는 나갈 글이 있다.

        **잣대는 생성과 같은 것을 쓴다** — `DrugCautionService.generation_ready()`
        와 `has_evidence()`. 예전에는 여기서 `approval_status=APPROVED` 하나만
        봤는데, 생성은 거기에 등급 A 와 근거 넷을 더 요구한다(KEY-180 §2·§4).
        등급이 A 가 아닌 자문 문구가 들어오면 **화면은 그것을 「원본」이라 보여
        주고 환자에게는 기본 한 줄이 나갔다** — 이 파일이 없애려던 바로 그
        갈림이 한 칸 옆에 남아 있었다 (이희진 님 `#214` ③).
        """
        rows = await DrugCautionService.generation_ready().filter(approved_key__isnull=False)
        approved = {
            (row.prescription_set_id, row.section_key): row.body for row in rows if DrugCautionService.has_evidence(row)
        }

        found: dict[tuple[int, CautionSectionKey], str] = {}
        for row in await PrescriptionSet.all().only("prescription_set_id"):
            set_id = row.prescription_set_id
            for key, fallback in guide_defaults.BY_SECTION.items():
                found[(set_id, key)] = approved.get((set_id, key), fallback)

        return found

    @staticmethod
    async def _edits(hospital_id: int, doctor_id: int | None) -> dict[tuple[int, CautionSectionKey], str]:
        rows = await DoctorGuideCopy.filter(hospital_id=hospital_id, doctor_id=doctor_id).values_list(
            "prescription_set_id", "section_key", "body"
        )
        return {(set_id, CautionSectionKey(key)): body for set_id, key, body in rows}

    @staticmethod
    async def _reviewed(hospital_id: int, doctor_id: int | None) -> set[int]:
        # `flat=True` 면 값이 그대로 오는데 Tortoise 스텁은 늘 튜플 목록이라 한다.
        rows: list[int] = await DoctorGuideReview.filter(hospital_id=hospital_id, doctor_id=doctor_id).values_list(
            "prescription_set_id", flat=True
        )  # type: ignore[assignment]
        return set(rows)
