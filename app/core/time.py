from datetime import date, datetime, time, timedelta

from app.core.config import Config

# 화면·업무 날짜는 병원 표시 시간대를 한 곳에서 사용한다.
DISPLAY_TIMEZONE = Config().TIMEZONE


def clinic_day_window(day: date) -> tuple[datetime, datetime]:
    """그 날 하루의 경계 — **의원 시간대 자정에서 자정까지** (KEY-181).

    돌려주는 값은 **시간대가 붙은 채로 그대로 질의에 넘긴다.** UTC 로 바꾸면
    안 된다.

    `visited_at` 열에는 KST 벽시계가 담겨 있고, asyncmy 의 `escape_datetime`
    은 tzinfo 를 무시하고 `.hour`·`.minute` 값만 SQL 에 싣는다. 그래서
    `.astimezone(UTC)` 를 거친 값을 넘기면 **벽시계가 아홉 시간 밀린 채로**
    비교된다. 하루의 경계가 15:00 이 되고, 두 자리에서 다르게 터졌다.

        접수대 목록      15:00 이후 진료가 어느 날짜에도 안 뜬다
        하루 한 건 규칙   저녁 진료 뒤 다음 날 아침 재진이 409 로 막힌다

    **경계를 만드는 곳을 한 곳으로 모은 것이 이 함수의 요점이다.** 예전에는
    같은 두 줄이 `front_desk.py` 와 `visits.py` 에 복제돼 있었고, 「KST 로
    줘야 한다」는 규칙을 주석으로만 지키고 있었다 — 다음 사람이 한쪽에
    `.astimezone(UTC)` 를 도로 넣으면 아무것도 안 운다 (이희진 님 `#136`
    리뷰).

    저장을 UTC 로 정규화하는 근본 정리는 별건이다. 그때는 **이 함수 하나만**
    고치면 된다.
    """
    start = datetime.combine(day, time.min, tzinfo=DISPLAY_TIMEZONE)
    return start, start + timedelta(days=1)


def clinic_today() -> date:
    """의원 시간대의 오늘.

    `clinic_day_window` 와 **같은 시간대에서 재야 한다.** 서버가 UTC 로
    돌면 한국 시각 자정에서 아홉 시까지가 어제로 잡히고, 그 동안 「오늘
    나갈 문자」가 하루 앞 것으로 뜬다.

    경계를 만드는 곳을 한 곳에 모으는 것이 이 파일의 요점이라 여기 둔다 —
    부르는 자리(S2-3 · S2-4)마다 `datetime.now(...)` 를 적으면 한쪽만
    고쳐지는 날이 온다.
    """
    return datetime.now(DISPLAY_TIMEZONE).date()
