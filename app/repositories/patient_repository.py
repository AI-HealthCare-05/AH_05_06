from tortoise.expressions import Q

from app.models.patients import Patient
from app.models.visits import Visit


class PatientRepository:
    async def create(self, data: dict[str, object]) -> Patient:
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
            query = query.filter(
                Q(name__startswith=keyword) | Q(hospital_patient_no__contains=keyword) | Q(phone__contains=keyword)
            )
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

    async def save(self, patient: Patient, fields: list[str]) -> None:
        await patient.save(update_fields=fields)
