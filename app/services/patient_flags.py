"""이탈 배지 — 와이어프레임 S2-1 「★ 이탈을 잡는 자리」.

원문이 세 가지를 든다.

    ⚠ 3회 연속 미열람   확인 문자를 세 번 보냈는데 안내를 한 번도 안 열었다
    ⚠ 복약 중단 응답     확인 문자에 그만 먹는다고 답했다
    ⚠ 소진 후 7일 경과   약이 떨어진 지 이레가 지났는데 다시 안 왔다

셋 다 지금 있는 자료로 낸다. 「복약 중단 응답」은 한 번 「담을 표가 없다」고
잘못 적었다가 고친 자리다 — `check_in` 이 KEY-151 부터 있고, 다섯 답 중 둘이
중단이다. 없다고 단정하기 전에 찾아봐야 한다.

**다만 「3회 연속 미열람」은 아직 뜰 수 없다.** 나간 확인 문자를 세는데 문자를
실제로 보내는 발송기가 없어 `SENT` 가 되는 줄이 없다. 규칙은 맞고 자료가 아직
없는 것이라, 발송기가 붙으면 저절로 뜬다.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.models.prescriptions import Prescription
from app.models.visits import (
    CheckIn,
    CheckInMedication,
    GuideMessage,
    GuideMessageKind,
    GuideMessageStatus,
    PatientUsageEvent,
    PatientUsageEventType,
    Visit,
)

#: 원문의 「3회 연속」. 회차 이름(일주일 뒤 · 보름 뒤 · 한 달 뒤)이 셋이라
#: 이 수가 곧 「확인 문자를 다 놓쳤다」는 뜻이 된다.
UNREAD_STREAK = 3

#: 원문의 「소진 후 7일 경과」.
RUN_OUT_GRACE = 7

#: 확인 문자 — 열람을 물을 수 있는 회차. 진료 안내문(GUIDE)은 빼는데,
#: 그것을 안 열었다는 것은 「연속으로 놓쳤다」가 아니라 「처음부터 안 봤다」다.
#: 「그만 먹는다」에 드는 답 — 부작용으로 끊었거나 좋아져서 끊었거나.
#: 나머지 셋(먹는 중 · 불편함 · 거름)은 중단이 아니다.
STOPPED_ANSWERS = (
    CheckInMedication.STOPPED_SIDE_EFFECT,
    CheckInMedication.STOPPED_IMPROVED,
)

CHECK_KINDS = (
    GuideMessageKind.CHECK_D7,
    GuideMessageKind.CHECK_D15,
    GuideMessageKind.CHECK_D30,
)


class PatientFlag:
    """줄에 붙는 배지 이름. 화면이 사람 말로 옮긴다."""

    UNREAD_STREAK = "UNREAD_STREAK"
    STOPPED_DOSING = "STOPPED_DOSING"
    RUN_OUT_OVERDUE = "RUN_OUT_OVERDUE"


@dataclass(frozen=True, slots=True)
class FlagInput:
    """한 환자의 **가장 최근 진료 한 코스**에 대한 근거.

    코스 단위인 것이 요점이다. 원문의 배지가 「확인 문자 3회 연속 미열람
    (일주일 뒤 · 보름 뒤 · 한 달 뒤)」인데, 이 셋은 한 진료가 만든 회차다 —
    지난 코스에서 한 번 열었다고 이번 코스를 챙길 필요가 없어지지는 않는다.

    질의에서 떼어 놓는다 — 규칙이 순수해야 검사가 닿는다.
    """

    #: 이 코스에서 나간 확인 문자 수
    checks_sent: int
    #: 이 코스의 안내문을 연 적이 있는가
    viewed: bool
    #: 약이 떨어지는 날. 처방일수를 모르면 없다 — **셈하지 않는다.**
    runs_out_on: date | None


def flags_of(given: FlagInput, today: date) -> list[str]:
    """**모르면 붙이지 않는다.**

    배지는 스탭에게 「이 환자를 챙기라」는 말이다. 근거가 없는데 붙이면 챙길
    일이 없는 환자를 부르게 되고, 몇 번 헛걸음하면 배지 전체를 안 믿게 된다.
    """
    found = []
    if given.checks_sent >= UNREAD_STREAK and not given.viewed:
        found.append(PatientFlag.UNREAD_STREAK)
    if given.runs_out_on is not None and today > given.runs_out_on + timedelta(days=RUN_OUT_GRACE):
        found.append(PatientFlag.RUN_OUT_OVERDUE)
    return found


async def stopped_dosing(latest_visits: dict[int, Visit]) -> set[int]:
    """**그만 먹는다고 답한 환자** — 와이어프레임 S2-1 「⚠ 복약 중단 응답」.

    근거는 `check_in` 이다 (KEY-151). 환자가 확인 링크에서 복약 상태를 고르는데,
    다섯 중 둘이 중단이다 — 부작용으로 끊었거나 좋아져서 끊었거나.

    **좋아져서 끊은 것도 배지를 붙인다.** 스스로 판단해 끊은 것이라 다음
    진료에서 확인할 일이고, 원문의 배지도 이유를 가르지 않는다. 이유는
    환자 이력 모달(S2-2)에서 본다.

    한 안내문에 응답 한 건만 허용되므로(`OneToOne`), 최근 진료의 안내문에
    달린 것만 본다 — 지난 코스에서 끊었다가 다시 처방받은 환자를 계속
    붙들고 있으면 배지를 안 믿게 된다.
    """
    visit_ids = [visit.visit_id for visit in latest_visits.values()]
    if not visit_ids:
        return set()
    stopped_visits = set(
        await CheckIn.filter(
            guide_document__visit_id__in=visit_ids,
            medication__in=STOPPED_ANSWERS,
        ).values_list("guide_document__visit_id", flat=True)
    )
    return {patient_id for patient_id, visit in latest_visits.items() if visit.visit_id in stopped_visits}


async def load_flag_inputs(
    latest_visits: dict[int, Visit],
    hospital_id: int,
) -> dict[int, FlagInput]:
    """환자 여럿의 배지 근거를 **질의 셋으로** 읽는다.

    환자마다 한 번씩 물으면 `limit=100` 에서 질의가 삼백 번 난다
    (`work_category.load_signals` 와 같은 까닭이다).

    받는 것은 **환자별 가장 최근 진료**다. 부르는 쪽이 이미 그것을 손에
    쥐고 있어서(`PatientRepository.latest_visits`) 다시 읽지 않는다.
    """
    visit_ids = [visit.visit_id for visit in latest_visits.values()]
    if not visit_ids:
        return {}

    # `flat=True` 면 값이 그대로 오는데 스텁은 늘 튜플 목록이라 한다.
    checks: list[int] = await GuideMessage.filter(
        guide_document__visit_id__in=visit_ids,
        kind__in=CHECK_KINDS,
        status=GuideMessageStatus.SENT,
    ).values_list("guide_document__visit_id", flat=True)  # type: ignore[assignment]

    viewed = set(
        await PatientUsageEvent.filter(
            guide_document__visit_id__in=visit_ids,
            event_type=PatientUsageEventType.GUIDE_VIEWED,
        ).values_list("guide_document__visit_id", flat=True)
    )

    #: 한 처방에 약이 여럿이고 처방일수가 빈 줄도 있다 — **가장 긴 것**으로
    #: 잡는다. 「비잔 84일 + 진통제(빈칸)」에서 84 를 잃으면 안 된다.
    longest: dict[int, int] = {}
    # 스텁이 `values_list` 를 늘 `tuple[Any, ...]` 라 해서 두 칸으로 안 풀린다.
    # 실제로는 (진료번호, 처방일수) 가 온다.
    rows = await Prescription.filter(visit_id__in=visit_ids).values_list("visit_id", "items__duration_days")
    for row in rows:
        visit_id, duration = int(row[0]), row[1]
        if duration and duration > longest.get(visit_id, 0):
            longest[visit_id] = duration

    sent: dict[int, int] = {}
    for checked in checks:
        sent[checked] = sent.get(checked, 0) + 1

    found = {}
    for patient_id, visit in latest_visits.items():
        duration = longest.get(visit.visit_id)
        found[patient_id] = FlagInput(
            checks_sent=sent.get(visit.visit_id, 0),
            viewed=visit.visit_id in viewed,
            runs_out_on=visit.visited_at.date() + timedelta(days=duration) if duration else None,
        )
    return found
