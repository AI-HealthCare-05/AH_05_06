from collections.abc import Sequence
from datetime import datetime
from typing import Any

from tortoise import BaseDBAsyncClient
from tortoise.expressions import Q
from tortoise.functions import Max

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
        sms_opt_out_only: bool = False,
        patient_ids: list[int] | None = None,
    ) -> list[Patient]:
        query = self._scoped_query(hospital_id, keyword)
        if sms_opt_out_only:
            query = query.filter(sms_opted_out_at__isnull=False)
        if patient_ids is not None:
            if not patient_ids:
                return []
            query = query.filter(patient_id__in=patient_ids)
        if after_id is not None:
            query = query.filter(patient_id__gt=after_id)
        return await query.order_by("patient_id").limit(limit)

    async def category_counts(
        self,
        hospital_id: int,
        *,
        keyword: str | None,
        inactive_patient_ids: list[int],
    ) -> tuple[int, int, int]:
        query = self._scoped_query(hospital_id, keyword)
        all_count = await query.count()
        sms_opt_out_count = await query.filter(sms_opted_out_at__isnull=False).count()
        inactive_count = await query.filter(patient_id__in=inactive_patient_ids).count() if inactive_patient_ids else 0
        return all_count, sms_opt_out_count, inactive_count

    @staticmethod
    async def latest_visit_times(hospital_id: int) -> dict[int, datetime]:
        """환자별 최신 진료 시각만 한 번의 집계 질의로 읽는다."""
        rows = await (
            Visit.filter(hospital_id=hospital_id)
            .annotate(latest_visited_at=Max("visited_at"))
            .group_by("patient_id")
            .values("patient_id", "latest_visited_at")
        )
        return {int(row["patient_id"]): row["latest_visited_at"] for row in rows}

    @staticmethod
    def _scoped_query(hospital_id: int, keyword: str | None):  # type: ignore[no-untyped-def]
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
        return query

    async def latest_visits(self, patient_ids: list[int], hospital_id: int) -> dict[int, Visit]:
        """환자 수와 무관하게 한 번의 질의로 최신 진료를 모은다."""
        if not patient_ids:
            return {}
        rows = await Visit.filter(patient_id__in=patient_ids, hospital_id=hospital_id).order_by(
            "patient_id", "-visited_at", "-visit_id"
        )
        latest: dict[int, Visit] = {}
        for visit in rows:
            latest.setdefault(visit.patient_id, visit)
        return latest

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
