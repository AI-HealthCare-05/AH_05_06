from collections.abc import Sequence
from typing import Any

from tortoise import BaseDBAsyncClient
from tortoise.expressions import Q

from app.core.utils.common import normalize_phone_number
from app.models.patients import Patient
from app.models.visits import Visit


class PatientRepository:
    async def create(self, data: dict[str, Any]) -> Patient:
        return await Patient.create(**data)

    async def get_scoped(self, patient_id: int, hospital_id: int) -> Patient | None:
        return await Patient.get_or_none(patient_id=patient_id, hospital_id=hospital_id)

    async def get_by_number(self, hospital_id: int, hospital_patient_no: str) -> Patient | None:
        return await Patient.get_or_none(
            hospital_id=hospital_id,
            hospital_patient_no=hospital_patient_no,
        )

    async def list_scoped(
        self,
        hospital_id: int,
        *,
        keyword: str | None,
        after_id: int | None,
        limit: int,
    ) -> list[Patient]:
        query = Patient.filter(hospital_id=hospital_id)
        if keyword:
            # 저장은 숫자만 남긴다(normalize_phone_number). 검색어도 같은 모양으로
            # 맞춰야 차트에 적힌 대로 "010-3945-7702" 를 쳤을 때 찾힌다 — 계약 §6 의
            # 「정규화된 휴대폰에서 검색한다」가 이 자리다.
            # 못 찾으면 오류가 아니라 「결과 없음」이라, 직원은 미등록 환자로 알고
            # 새로 등록한다. 그러면 차트번호 중복까지 이어진다.
            conditions = Q(name__startswith=keyword) | Q(hospital_patient_no__contains=keyword)
            digits = normalize_phone_number(keyword)
            if digits:
                conditions |= Q(phone__contains=digits)
            query = query.filter(conditions)
        if after_id is not None:
            query = query.filter(patient_id__gt=after_id)
        return await query.order_by("patient_id").limit(limit)

    async def latest_visit(self, patient_id: int, hospital_id: int) -> Visit | None:
        return (
            await Visit.filter(patient_id=patient_id, hospital_id=hospital_id)
            .order_by("-visited_at", "-visit_id")
            .first()
        )

    async def has_visits(self, patient_id: int, hospital_id: int) -> bool:
        return await Visit.filter(patient_id=patient_id, hospital_id=hospital_id).exists()

    async def save(
        self,
        patient: Patient,
        fields: Sequence[str],
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        # `using_db` 를 받는 이유는 환자번호 정정 때문이다 — 번호를 바꾸는 것과
        # 감사 기록을 남기는 것이 **한 트랜잭션**이어야 한다(KEY-121). 갈라 두면
        # 번호만 바뀌고 「왜 바꿨나」가 비는 행이 생기고, 그러면 의무기록 정정을
        # 되짚을 수 없다.
        await patient.save(update_fields=fields, using_db=using_db)
