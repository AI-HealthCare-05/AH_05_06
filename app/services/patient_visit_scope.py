from datetime import datetime

from app.core.api_errors import ApiError
from app.core.pagination import decode_cursor
from app.dependencies.patient_access import ClinicalActor


def hospital_id_of(actor: ClinicalActor) -> int:
    if actor.hospital_id is None:
        raise ApiError(403, "FORBIDDEN", "병원 소속 직원만 접근할 수 있습니다.")
    return actor.hospital_id


def visit_cursor(cursor: str | None) -> tuple[datetime | None, int | None]:
    try:
        payload = decode_cursor(cursor)
        if payload is None:
            return None, None
        visited_at = payload.get("visited_at")
        visit_id = payload.get("visit_id")
        if not isinstance(visited_at, str) or not isinstance(visit_id, int):
            raise ValueError
        parsed = datetime.fromisoformat(visited_at)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed, visit_id
    except ValueError as error:
        raise ApiError(400, "INVALID_REQUEST", "페이지 커서가 올바르지 않습니다.") from error
