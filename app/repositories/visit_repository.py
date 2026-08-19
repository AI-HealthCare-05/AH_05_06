from datetime import datetime

from tortoise.expressions import Q

from app.models.visits import Visit


class VisitRepository:
    async def create(self, data: dict[str, object]) -> Visit:
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

    async def save(self, visit: Visit, fields: list[str]) -> None:
        await visit.save(update_fields=fields)
