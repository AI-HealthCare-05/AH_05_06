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
        day_start: datetime,
        day_end: datetime,
        *,
        exclude_visit_id: int | None = None,
    ) -> bool:
        """`day_start`·`day_end` 는 **의원 시간대(KST) 로 준다** — KEY-181.

        `visited_at` 열이 KST 벽시계를 담고 있어서, 여기 UTC 로 바꿔 넘기면
        아홉 시간 밀린 창으로 재게 된다. 예전 이름이 `start_utc` 였고 실제로
        UTC 를 넘기고 있었다.
        """
        query = Visit.filter(
            patient_id=patient_id,
            hospital_id=hospital_id,
            visited_at__gte=day_start,
            visited_at__lt=day_end,
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
        day_start: datetime,
        day_end: datetime,
    ) -> list[Visit]:
        """선택 날짜와 아직 해결되지 않은 보완 후보만 DB에서 읽는다.

        `day_start`·`day_end` 는 **의원 시간대(KST) 로 준다** — KEY-181.
        `exists_on_day` 와 같은 이유다.
        """
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
            .filter(Q(visited_at__gte=day_start, visited_at__lt=day_end) | attention)
            .prefetch_related("patient")
            .order_by("-visited_at", "-visit_id")
            .distinct()
        )

    async def save(self, visit: Visit, fields: list[str]) -> None:
        await visit.save(update_fields=fields)
