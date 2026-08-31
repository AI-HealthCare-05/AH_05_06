"""진료 처리 이력을 모은다 — KEY-234, 와이어프레임 D1-6.

한 표에 다 있지 않다. 안내문에 사람이 한 일은 `guide_event`, 환자가 한 일은
`patient_usage_event`, 확인 문자 응답은 `check_in` 에 있다. 세 곳을 합쳐
시간 순으로 세운다.

**세 표를 그대로 합치는 것이 맞다.** 하나로 모으는 표를 새로 만들면 기록이
두 곳에 남고, 어느 쪽이 정본인지 흐려진다 — 각자의 일을 하는 자리가 남긴
것을 읽기만 한다.
"""

from app.core.api_errors import ApiError
from app.models.staffs import Staff
from app.models.visits import CheckIn, GuideDocument, GuideEvent, PatientUsageEvent, Visit
from app.timeline.schemas import TimelineEntry, TimelineResponse


class TimelineService:
    async def read(self, actor, visit_id: int) -> TimelineResponse:
        # 남의 의원 것은 **없는 것이다.** 존재 여부가 새면 그 자체가 정보다.
        visit = await Visit.filter(visit_id=visit_id, hospital_id=actor.hospital_id).first()
        if visit is None:
            # **인자 차례를 조심한다.** 이 저장소에는 같은 이름의 오류가 둘이고
            # 차례가 반대다 (`app/tests/routing/test_route_ownership.py` 가 그
            # 사실을 못 박아 두었다):
            #   app.core.api_errors.ApiError(status_code, code, message)
            #   app.core.auth_errors.AuthError(code, status_code, message)
            # 여기는 앞의 것이다 — 이 라우터가 `api_errors` 의 봉투를 입는다.
            raise ApiError(404, "VISIT_NOT_FOUND", "진료 건을 찾을 수 없습니다.")

        entries: list[TimelineEntry] = []

        # 진료 등록 — 이 진료의 시작이다. 다른 표가 아니라 `visit` 이 갖고 있다.
        entries.append(TimelineEntry(at=visit.visited_at, kind="VISIT_CREATED"))

        guide = await GuideDocument.filter(visit_id=visit_id).first()
        if guide is None:
            return TimelineResponse(visit_id=visit_id, entries=self._sorted(entries))

        # 사람이 안내문에 한 일 — 수정 · 넘김 · 승인 · 반려
        events = await GuideEvent.filter(guide_document_id=guide.guide_document_id).all()

        # 이름은 한 번에 모아 온다. 줄마다 물어보면 스무 줄에 스무 번 간다.
        actor_ids = {e.actor_id for e in events if e.actor_id}
        names: dict[int, str] = {}
        if actor_ids:
            for staff in await Staff.filter(staff_id__in=list(actor_ids)).all():
                names[staff.staff_id] = staff.name

        for event in events:
            entries.append(
                TimelineEntry(
                    at=event.created_at,
                    kind=str(event.event_type),
                    # **모르는 사람은 이름을 지어내지 않는다.** 지워진 계정일 수
                    # 있고, 그때는 화면이 「알 수 없음」이라 적는다.
                    actor=names.get(event.actor_id),
                    section=str(event.section_key) if event.section_key else None,
                    detail=event.reason,
                )
            )

        # 환자가 한 일 — 열람 · 챗봇 질문. **행위자는 비운다**(환자다).
        for used in await PatientUsageEvent.filter(guide_document_id=guide.guide_document_id).all():
            entries.append(
                TimelineEntry(
                    at=used.created_at,
                    kind=str(used.event_type),
                    section=str(used.grounded_section) if used.grounded_section else None,
                )
            )

        # 확인 문자 응답 — 한 진료에 한 건이다(Walking Skeleton).
        answer = await CheckIn.filter(guide_document_id=guide.guide_document_id).first()
        if answer is not None:
            entries.append(
                TimelineEntry(
                    at=answer.created_at,
                    kind="CHECK_IN",
                    detail=str(answer.medication),
                )
            )

        return TimelineResponse(visit_id=visit_id, entries=self._sorted(entries))

    @staticmethod
    def _sorted(entries: list[TimelineEntry]) -> list[TimelineEntry]:
        """**오래된 것이 위다.** 진료가 어떻게 흘러갔는지 읽는 자리라,
        최신순으로 뒤집으면 거꾸로 읽게 된다.

        같은 시각이면 넣은 차례를 지킨다 — 등록이 수정보다 뒤로 가면 안 된다.
        """
        return sorted(entries, key=lambda e: e.at)
