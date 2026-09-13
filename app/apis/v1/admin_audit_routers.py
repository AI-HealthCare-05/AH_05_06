"""어드민 — 감사 로그 조회 (A1-6 · A1-7). KEY-322.

**A1-7 은 별도 경로가 아니다.** 「한 진료 건의 시간 흐름」은 이 경로에
`visit_id` 를 거는 것이다 — 표 넷을 합치는 규칙이 하나면 두 화면이 같은 답을
본다. 두 경로로 나누면 한쪽에만 표가 늘어나는 날이 온다.

`AUDIT_READ` 가 아니라 `STAFF_MANAGE` 로 막지 않는다 — 둘 다 `admin` 만 여는
권한이지만 뜻이 다르고, 권한표가 이미 `AUDIT_READ` 를 갖고 있다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.api_errors import ContractRoute
from app.dependencies.admin_access import AdminActor, require_audit_read
from app.dtos.admin_audit import AuditLogPage, AuditLogQuery
from app.services.admin_audit import AdminAuditService

admin_audit_router = APIRouter(prefix="/admin/audit-logs", tags=["admin"], route_class=ContractRoute)


@admin_audit_router.get("", response_model=AuditLogPage)
async def list_audit_logs(
    actor: Annotated[AdminActor, Depends(require_audit_read)],
    query: Annotated[AuditLogQuery, Query()],
) -> AuditLogPage:
    """A1-6 — 의원 전체. `visit_id` 를 주면 A1-7(한 진료 건의 시간 흐름)이다."""
    return await AdminAuditService().page(actor, query)
