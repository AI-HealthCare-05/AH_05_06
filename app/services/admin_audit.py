"""감사 로그를 **읽을 때 합친다** — A1-6 · A1-7 (KEY-322).

이벤트는 이미 네 표에 append-only 로 쌓이고 있는데 읽을 길이 없었다. 통합
`AuditLog` 표로 물리 통합하는 것은 별도 논의라, 여기서는 조회 시 합친다.

## 모든 길이 `GuideDocument` 를 지난다

울타리를 어디에 치나가 이 파일의 뼈대다. 네 표가 병원을 각자 들고 있지 않지만
**전부 `GuideDocument` 에 닿고**, 거기에 `hospital_id` 와 `visit_id` 가 둘 다
있다.

    guide_event          → guide_document
    patient_usage_event  → guide_document
    guide_message_event  → guide_message      → guide_document
    patient_otp_event    → patient_guide_link → guide_document

앞 셋은 FK 라 조인으로 한 번에 거른다. **`patient_otp_event` 만 다르다** —
`patient_guide_link_id` 가 FK 가 아니라 그냥 `BigIntField` 라 조인할 자리가
없다. 그 표만 링크 id 를 먼저 모아 `__in` 으로 건다. 파일럿 규모(의원 하나)
에서는 문제가 없지만, 의원이 늘면 여기가 먼저 아프다 — 그때는 FK 를 세우는
것이 답이지 여기서 우회할 일이 아니다.

## 쪽 나눔

표 넷을 SQL 로 합칠 수 없으므로 **각 표에서 한 쪽씩 떠 와 파이썬에서 섞는다.**
각자 `limit + 1` 을 최신순으로 뜨면, 섞어서 앞의 `limit` 개를 고른 결과는
전체를 정렬한 것과 같다 — 어느 표에서 안 떠 온 줄은 그 표의 `limit + 1` 번째
보다 오래된 것이라 앞자리에 못 온다.

순서는 `(occurred_at, source, pk)` 내림차순 하나다. **문자열 `event_id` 로
줄 세우지 않는다** — `"guide:9" > "guide:10"` 이라 열 번째 줄부터 순서가
뒤집힌다. 처음에 그렇게 썼고 쪽 나눔 검사가 잡았다(일곱 줄을 세 개씩 넘겼더니
여섯만 보였다).

커서는 그 셋을 그대로 담고, 표마다 SQL 로 정확히 자른다 — 파이썬에서 다시
거르면 `LIMIT` 이 먼저 걸려 경계 줄이 한 개씩 사라진다(그것이 여섯만 보인
까닭이다). **같은 커서로 다시 물으면 같은 답이 온다.**
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tortoise.expressions import Q

from app.core.api_errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor
from app.dependencies.admin_access import AdminActor
from app.dtos.admin_audit import AuditLogEntry, AuditLogPage, AuditLogQuery, AuditSource
from app.models.staffs import Staff, StaffAccountEvent, StaffAccountEventType
from app.models.visits import (
    GuideEvent,
    GuideEventType,
    GuideMessageEvent,
    GuideMessageEventType,
    PatientGuideLink,
    PatientOtpEvent,
    PatientOtpEventType,
    PatientUsageEvent,
    PatientUsageEventType,
)

LOGGER = logging.getLogger(__name__)

#: 사람이 읽을 한 줄. **서버가 짓는 고정 문구다** — 사람이 적은 값(`reason`)이나
#: 환자 정보가 흘러들 자리가 없다. 모르는 유형은 원래 값을 그대로 적는다:
#: 표에 유형이 늘었을 때 빈칸을 그리는 것보다 낫다.
_SUMMARY: dict[tuple[AuditSource, str], str] = {
    (AuditSource.GUIDE, GuideEventType.GENERATED): "안내문을 생성했습니다",
    (AuditSource.GUIDE, GuideEventType.EDITED): "안내문을 수정했습니다",
    (AuditSource.GUIDE, GuideEventType.SUBMITTED): "안내문을 의사에게 넘겼습니다",
    (AuditSource.GUIDE, GuideEventType.APPROVED): "안내문을 승인했습니다",
    (AuditSource.GUIDE, GuideEventType.UNAPPROVED): "안내문 승인을 취소했습니다",
    (AuditSource.GUIDE, GuideEventType.RETURNED): "안내문을 스탭에게 되돌렸습니다",
    (AuditSource.GUIDE, GuideEventType.REGENERATED): "안내문을 다시 생성했습니다",
    (AuditSource.GUIDE, GuideEventType.SECTION_REORDERED): "안내문 항목 차례를 바꿨습니다",
    (AuditSource.GUIDE, GuideEventType.LINK_REISSUED): "환자 링크를 다시 발급했습니다",
    (AuditSource.GUIDE, GuideEventType.LINK_REVOKED): "환자 링크를 폐기했습니다",
    (AuditSource.OTP, PatientOtpEventType.ISSUED): "환자에게 인증번호를 보냈습니다",
    (AuditSource.OTP, PatientOtpEventType.DELIVERY_FAILED): "인증번호를 보내지 못했습니다",
    (AuditSource.OTP, PatientOtpEventType.VERIFIED): "환자가 본인 확인을 마쳤습니다",
    (AuditSource.OTP, PatientOtpEventType.VERIFICATION_FAILED): "환자가 인증번호를 틀렸습니다",
    (AuditSource.OTP, PatientOtpEventType.LOCKED): "인증 시도가 많아 잠겼습니다",
    (AuditSource.MESSAGE, GuideMessageEventType.ATTEMPTED): "문자 발송을 시도했습니다",
    (AuditSource.MESSAGE, GuideMessageEventType.SENT): "문자를 보냈습니다",
    (AuditSource.MESSAGE, GuideMessageEventType.FAILED): "문자를 보내지 못했습니다",
    (AuditSource.MESSAGE, GuideMessageEventType.HELD): "문자를 보류했습니다",
    (AuditSource.PATIENT_USAGE, PatientUsageEventType.GUIDE_VIEWED): "환자가 안내를 열어 봤습니다",
    (AuditSource.PATIENT_USAGE, PatientUsageEventType.CHATBOT_ANSWERED): "챗봇이 환자 물음에 답했습니다",
    (AuditSource.STAFF_ACCOUNT, StaffAccountEventType.STAFF_CREATED): "직원 계정을 만들었습니다",
}


@dataclass(frozen=True, slots=True)
class _Row:
    """표 넷이 공통으로 옮겨지는 자리. DTO 로 나가기 전의 중간 모양이다."""

    pk: int
    occurred_at: datetime
    source: AuditSource
    event_type: str
    actor_staff_id: int | None
    visit_id: int | None

    @property
    def event_id(self) -> str:
        """화면과 커서가 가리키는 이름. 표가 달라도 안 겹친다."""
        return f"{self.source.value}:{self.pk}"

    @property
    def order_key(self) -> tuple[datetime, str, int]:
        """**문자열이 아니라 튜플이다.** `pk` 를 숫자로 견줘야 열 번째부터
        뒤집히지 않는다."""
        return (self.occurred_at, self.source.value, self.pk)


@dataclass(frozen=True, slots=True)
class _Scope:
    """한 번의 조회가 지키는 울타리와 거르개."""

    hospital_id: int
    query: AuditLogQuery
    #: 커서가 가리키는 자리 `(시각, 표, 번호)`. 이보다 **오래된** 것만 본다.
    after: tuple[datetime, str, int] | None
    #: 각 표에서 떠 올 개수. 섞은 뒤 `limit` 개를 고르므로 하나 더 뜬다.
    take: int


def _summary(source: AuditSource, event_type: str) -> str:
    return _SUMMARY.get((source, event_type), event_type)


def _before_cursor(rows: Any, scope: _Scope, source: AuditSource, pk_field: str) -> Any:
    """커서보다 **오래된** 것만 남긴다 — 파이썬이 아니라 SQL 에서.

    파이썬에서 거르면 `LIMIT` 이 먼저 걸려 경계 줄이 쪽마다 하나씩 사라진다.
    실제로 그랬다: 일곱 줄을 세 개씩 넘겼더니 여섯만 보였다.

    같은 시각일 때는 `(표 이름, 번호)` 로 가른다. 표가 커서의 표와 같으면 번호를
    견주고, 이름이 앞서면 그 시각 줄이 전부 커서보다 뒤(=오래된 쪽)이므로 남기고,
    뒤서면 전부 앞이므로 버린다.
    """
    if scope.after is None:
        return rows
    at, cursor_source, cursor_pk = scope.after
    if source.value == cursor_source:
        same_time: dict[str, Any] = {"created_at": at, f"{pk_field}__lt": cursor_pk}
        return rows.filter(Q(created_at__lt=at) | Q(**same_time))
    if source.value < cursor_source:
        return rows.filter(created_at__lte=at)
    return rows.filter(created_at__lt=at)


class AdminAuditService:
    """**읽기 전용이다.** 이 클래스에는 쓰는 경로가 없다 — `create` · `save` ·
    `update` · `delete` 를 부르지 않는다. 감사 기록을 읽는 길이 쓰는 길을
    겸하면 그것은 감사 기록이 아니다.
    """

    async def page(self, actor: AdminActor, query: AuditLogQuery) -> AuditLogPage:
        scope = _Scope(
            hospital_id=actor.hospital_id,
            query=query,
            after=_after(query.cursor),
            take=query.limit + 1,
        )

        sources: dict[AuditSource, Callable[[_Scope], Awaitable[list[_Row]]]] = {
            AuditSource.GUIDE: self._guide_rows,
            AuditSource.OTP: self._otp_rows,
            AuditSource.MESSAGE: self._message_rows,
            AuditSource.PATIENT_USAGE: self._usage_rows,
            AuditSource.STAFF_ACCOUNT: self._staff_account_rows,
        }
        wanted = [query.source] if query.source else list(sources)

        #: **한 번에 묻는다.** 표 다섯이 서로를 안 기다리므로 순차로 `await` 하면
        #: 한 쪽의 지연이 「가장 느린 것」이 아니라 **다섯의 합**이 된다. 표가
        #: 늘수록 벌어지는 자리다 (이희진 님 `#287` 리뷰 ③).
        #:
        #: 섞는 것은 어차피 파이썬에서 다시 정렬하므로 순서가 안 중요하다 —
        #: 병렬로 바꿔도 답이 같다.
        found = await asyncio.gather(*(sources[source](scope) for source in wanted))
        merged: list[_Row] = [row for rows in found for row in rows]

        merged.sort(key=lambda row: row.order_key, reverse=True)
        page = merged[: query.limit]
        has_more = len(merged) > len(page)

        return AuditLogPage(
            entries=await self._named(scope, page),
            next_cursor=_cursor_for(page[-1]) if page and has_more else None,
            has_more=has_more,
        )

    async def _named(self, scope: _Scope, rows: Sequence[_Row]) -> list[AuditLogEntry]:
        """직원 이름을 **한 번에** 가져온다 — 줄마다 물으면 쪽마다 50번이다.

        **이름도 울타리 안에서만 찾는다.** `GuideEvent.actor_id` 는 FK 가 아니라
        그냥 `BigIntField` 라, 어떤 사정으로 남의 의원 직원 번호가 들어 있으면
        그 사람 **이름이 이 목록에 뜬다.** 실제로 그럴 일은 없어야 하지만
        (그 진료에 손댈 권한이 있어야 사건이 남는다), 없어야 하는 것과 못
        하는 것은 다르다 — 못 하게 둔다 (이희진 님 `#287` 리뷰 ⑤).

        못 찾으면 이름이 비고 번호는 남는다. **줄이 사라지지는 않는다** —
        「누가 했는지 모르는 일이 있었다」가 「아무 일도 없었다」보다 낫다.
        """
        wanted = {row.actor_staff_id for row in rows if row.actor_staff_id is not None}
        names: dict[int, str] = {}
        if wanted:
            found = await Staff.filter(hospital_id=scope.hospital_id, staff_id__in=sorted(wanted))
            names = {staff.staff_id: staff.name for staff in found}
        return [
            AuditLogEntry(
                event_id=row.event_id,
                occurred_at=row.occurred_at,
                source=row.source,
                event_type=row.event_type,
                actor_staff_id=row.actor_staff_id,
                actor_name=names.get(row.actor_staff_id) if row.actor_staff_id is not None else None,
                visit_id=row.visit_id,
                summary=_summary(row.source, row.event_type),
            )
            for row in rows
        ]

    # ── 표 넷 ────────────────────────────────────────────────────────────
    #
    # 넷이 같은 모양이다: 울타리로 좁히고, 거르개를 걸고, 최신순으로 `take` 만큼
    # 떠서 `_Row` 로 옮긴다. 다른 것은 **병원까지 가는 길**뿐이다.

    async def _guide_rows(self, scope: _Scope) -> list[_Row]:
        rows = GuideEvent.filter(guide_document__hospital_id=scope.hospital_id)
        if scope.query.visit_id is not None:
            rows = rows.filter(guide_document__visit_id=scope.query.visit_id)
        if scope.query.actor_staff_id is not None:
            rows = rows.filter(actor_id=scope.query.actor_staff_id)
        rows = _before_cursor(_in_window(rows, scope), scope, AuditSource.GUIDE, "guide_event_id")
        found = (
            await rows.order_by("-created_at", "-guide_event_id")
            .limit(scope.take)
            .values("guide_event_id", "event_type", "created_at", "actor_id", "guide_document__visit_id")
        )
        return [
            _Row(
                pk=row["guide_event_id"],
                occurred_at=row["created_at"],
                source=AuditSource.GUIDE,
                event_type=str(row["event_type"]),
                actor_staff_id=row["actor_id"],
                visit_id=row["guide_document__visit_id"],
            )
            for row in found
        ]

    async def _usage_rows(self, scope: _Scope) -> list[_Row]:
        """**환자가 한 일이라 행위자가 없다.** 행위자 거르개가 걸리면 빈 목록이다.

        「이 직원이 한 일」을 물었는데 환자의 열람이 섞여 나오면 그 목록은
        답이 아니다.
        """
        if scope.query.actor_staff_id is not None:
            return []
        rows = PatientUsageEvent.filter(guide_document__hospital_id=scope.hospital_id)
        if scope.query.visit_id is not None:
            rows = rows.filter(guide_document__visit_id=scope.query.visit_id)
        rows = _before_cursor(_in_window(rows, scope), scope, AuditSource.PATIENT_USAGE, "patient_usage_event_id")
        found = (
            await rows.order_by("-created_at", "-patient_usage_event_id")
            .limit(scope.take)
            .values("patient_usage_event_id", "event_type", "created_at", "guide_document__visit_id")
        )
        return [
            _Row(
                pk=row["patient_usage_event_id"],
                occurred_at=row["created_at"],
                source=AuditSource.PATIENT_USAGE,
                event_type=str(row["event_type"]),
                actor_staff_id=None,
                visit_id=row["guide_document__visit_id"],
            )
            for row in found
        ]

    async def _message_rows(self, scope: _Scope) -> list[_Row]:
        """발송기가 한 일이라 사람 행위자가 없다 — 예약은 사람이 했지만 그것은
        안내문 사건(`SUBMITTED`·`APPROVED`)으로 이미 남는다."""
        if scope.query.actor_staff_id is not None:
            return []
        rows = GuideMessageEvent.filter(guide_message__guide_document__hospital_id=scope.hospital_id)
        if scope.query.visit_id is not None:
            rows = rows.filter(guide_message__guide_document__visit_id=scope.query.visit_id)
        rows = _before_cursor(_in_window(rows, scope), scope, AuditSource.MESSAGE, "guide_message_event_id")
        found = (
            await rows.order_by("-created_at", "-guide_message_event_id")
            .limit(scope.take)
            .values("guide_message_event_id", "event_type", "created_at", "guide_message__guide_document__visit_id")
        )
        return [
            _Row(
                pk=row["guide_message_event_id"],
                occurred_at=row["created_at"],
                source=AuditSource.MESSAGE,
                event_type=str(row["event_type"]),
                actor_staff_id=None,
                visit_id=row["guide_message__guide_document__visit_id"],
            )
            for row in found
        ]

    async def _otp_rows(self, scope: _Scope) -> list[_Row]:
        """**여기만 조인이 없다.** `patient_guide_link_id` 가 FK 가 아니라
        `BigIntField` 라, 이 의원의 링크 id 를 먼저 모아 `__in` 으로 건다.

        **링크 토큰은 어디에도 안 실린다.** 여기서 읽는 것은 링크의 **번호**와
        그 링크가 붙은 진료뿐이다 — `token_digest` 도 안 읽는다.
        """
        if scope.query.actor_staff_id is not None:
            return []

        links = PatientGuideLink.filter(guide_document__hospital_id=scope.hospital_id)
        if scope.query.visit_id is not None:
            links = links.filter(guide_document__visit_id=scope.query.visit_id)
        visit_of: dict[int, int | None] = {
            row["patient_guide_link_id"]: row["guide_document__visit_id"]
            for row in await links.values("patient_guide_link_id", "guide_document__visit_id")
        }
        if not visit_of:
            return []

        rows = _before_cursor(
            _in_window(PatientOtpEvent.filter(patient_guide_link_id__in=sorted(visit_of)), scope),
            scope,
            AuditSource.OTP,
            "patient_otp_event_id",
        )
        found = (
            await rows.order_by("-created_at", "-patient_otp_event_id")
            .limit(scope.take)
            .values("patient_otp_event_id", "event_type", "created_at", "patient_guide_link_id")
        )
        return [
            _Row(
                pk=row["patient_otp_event_id"],
                occurred_at=row["created_at"],
                source=AuditSource.OTP,
                event_type=str(row["event_type"]),
                actor_staff_id=None,
                visit_id=visit_of.get(row["patient_guide_link_id"]),
            )
            for row in found
        ]

    async def _staff_account_rows(self, scope: _Scope) -> list[_Row]:
        """**이 표만 진료를 안 지난다.** 계정은 진료 건에 매달리지 않으므로
        `hospital_id` 를 제가 들고 있고 `visit_id` 는 언제나 비어 있다.

        그래서 `visit_id` 로 거르면 이 표는 통째로 빠진다 — A1-7 은 「이 진료
        건에 무슨 일이 있었나」인데 계정 생성은 그 진료의 일이 아니다.

        **비밀번호는 이 표에 칸이 없다**(KEY-321). 여기서 새어 나갈 값이 없다.
        """
        if scope.query.visit_id is not None:
            return []
        rows = StaffAccountEvent.filter(hospital_id=scope.hospital_id)
        if scope.query.actor_staff_id is not None:
            rows = rows.filter(actor_staff_id=scope.query.actor_staff_id)
        rows = _before_cursor(_in_window(rows, scope), scope, AuditSource.STAFF_ACCOUNT, "staff_account_event_id")
        found = (
            await rows.order_by("-created_at", "-staff_account_event_id")
            .limit(scope.take)
            .values("staff_account_event_id", "event_type", "created_at", "actor_staff_id")
        )
        return [
            _Row(
                pk=row["staff_account_event_id"],
                occurred_at=row["created_at"],
                source=AuditSource.STAFF_ACCOUNT,
                event_type=str(row["event_type"]),
                actor_staff_id=row["actor_staff_id"],
                visit_id=None,
            )
            for row in found
        ]


def _in_window(rows: Any, scope: _Scope) -> Any:
    """기간 거르개만 건다. 커서는 `_before_cursor` 가 표마다 따로 자른다."""
    if scope.query.occurred_from is not None:
        rows = rows.filter(created_at__gte=scope.query.occurred_from)
    if scope.query.occurred_to is not None:
        rows = rows.filter(created_at__lte=scope.query.occurred_to)
    return rows


def _cursor_for(row: _Row) -> str:
    """**순서 열쇠를 그대로 담는다** — 시각 · 표 · 번호. 문자열 `event_id` 를
    담았다가 `"guide:9" > "guide:10"` 으로 순서가 뒤집혔다."""
    return encode_cursor({"at": row.occurred_at.isoformat(), "src": row.source.value, "pk": row.pk})


def _after(cursor: str | None) -> tuple[datetime, str, int] | None:
    """**서명된 커서만 받는다.** 손으로 지어낸 커서로 남의 자리를 가리키지
    못한다 — 울타리는 커서가 아니라 `hospital_id` 가 치지만, 읽을 수 없는 값을
    조용히 무시하면 사용자는 첫 쪽을 다시 받고 그것을 다음 쪽이라 믿는다.
    """
    if cursor is None:
        return None
    try:
        payload = decode_cursor(cursor)
        if payload is None:
            return None
        return (datetime.fromisoformat(str(payload["at"])), str(payload["src"]), int(payload["pk"]))
    except (ValueError, KeyError, TypeError) as error:
        raise ApiError(400, "INVALID_CURSOR", "잘못된 쪽 열쇠입니다. 처음부터 다시 불러 주세요.") from error
