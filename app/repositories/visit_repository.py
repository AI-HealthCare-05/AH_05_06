from datetime import datetime
from typing import Any

from tortoise.expressions import Q

from app.models.visits import GuideDocument, GuideStatus, Visit


class VisitRepository:
    async def create(self, data: dict[str, Any]) -> Visit:
        return await Visit.create(**data)

    async def get_scoped(self, visit_id: int, hospital_id: int) -> Visit | None:
        visit = await Visit.get_or_none(visit_id=visit_id, hospital_id=hospital_id)
        if visit is not None:
            await visit.fetch_related("patient")
            if visit.patient.hospital_id != hospital_id:
                return None
        return visit

    async def exists_on_day(
        self,
        patient_id: int,
        hospital_id: int,
        start_utc: datetime,
        end_utc: datetime,
        *,
        exclude_visit_id: int | None = None,
    ) -> bool:
        query = Visit.filter(
            patient_id=patient_id,
            hospital_id=hospital_id,
            visited_at__gte=start_utc,
            visited_at__lt=end_utc,
        )
        if exclude_visit_id is not None:
            query = query.exclude(visit_id=exclude_visit_id)
        return await query.exists()

    async def list_scoped(
        self,
        patient_id: int,
        hospital_id: int,
        *,
        before_visited_at: datetime | None,
        before_visit_id: int | None,
        limit: int,
    ) -> list[Visit]:
        query = Visit.filter(patient_id=patient_id, hospital_id=hospital_id)
        if before_visited_at is not None and before_visit_id is not None:
            query = query.filter(
                Q(visited_at__lt=before_visited_at) | Q(visited_at=before_visited_at, visit_id__lt=before_visit_id)
            )
        return await query.order_by("-visited_at", "-visit_id").limit(limit)

    async def front_desk_candidates(
        self,
        hospital_id: int,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[Visit]:
        """선택 날짜와 아직 해결되지 않은 보완 후보만 DB에서 읽는다."""
        returned_visit_ids = await GuideDocument.filter(
            hospital_id=hospital_id,
            status=GuideStatus.APPROVAL_RETURNED,
        ).values_list("visit_id", flat=True)
        reachable_mobile = (
            Q(patient__phone__startswith="010")
            | Q(patient__phone__startswith="011")
            | Q(patient__phone__startswith="016")
            | Q(patient__phone__startswith="017")
            | Q(patient__phone__startswith="018")
            | Q(patient__phone__startswith="019")
        )
        attention = Q(patient__sms_opted_out_at__isnull=False) | ~reachable_mobile
        if returned_visit_ids:
            attention |= Q(visit_id__in=returned_visit_ids)
        return await (
            Visit.filter(hospital_id=hospital_id)
            .filter(Q(visited_at__gte=start_utc, visited_at__lt=end_utc) | attention)
            .prefetch_related("patient")
            .order_by("-visited_at", "-visit_id")
            .distinct()
        )

    async def save(self, visit: Visit, fields: list[str]) -> None:
        await visit.save(update_fields=fields)
