"""발송 이력 CSV — 와이어프레임 S2-4 하단 「CSV 내려받기」.

**여기에도 사람 말이 필요하다.** 화면은 `frontend/js/message-words.js` 로
코드를 옮기는데, 파일은 엑셀에서 사람이 바로 읽어야 하므로 서버가 옮겨야
한다. 낱말이 두 곳에 사는 셈이라, 두 곳이 같은지 재는 검사를 뒀다
(`test_message_export.py`) — 한쪽만 고치면 그 검사가 운다.
"""

from datetime import date, datetime

from app.core.time import DISPLAY_TIMEZONE
from app.dtos.messages import SentMessageItem
from app.models.visits import GuideMessageFailure, GuideMessageKind, GuideMessageStatus

HEADER = [
    "발송일시",
    "환자",
    "차트번호",
    "식별정보",
    "세트명",
    "종류",
    "발송상태",
    "실패사유",
    "열람여부",
    "열람일시",
]

KIND_SAYING = {
    GuideMessageKind.GUIDE: "진료 안내문",
    GuideMessageKind.CHECK_D7: "일주일 뒤 확인",
    GuideMessageKind.CHECK_D15: "보름 뒤",
    GuideMessageKind.CHECK_D30: "한 달 뒤",
    GuideMessageKind.RUN_OUT: "소진 임박",
}

STATUS_SAYING = {
    GuideMessageStatus.SENT: "발송 완료",
    GuideMessageStatus.FAILED: "발송 실패",
}

FAILURE_SAYING = {
    GuideMessageFailure.INVALID_PHONE: "잘못된 번호",
    GuideMessageFailure.OPT_OUT: "수신 거부",
    GuideMessageFailure.CARRIER: "통신사 오류",
    GuideMessageFailure.SENDER_UNREGISTERED: "발신번호 미등록",
}

GENDER_SAYING = {"FEMALE": "여", "MALE": "남"}

#: 표 프로그램이 **셈식으로 읽는** 첫 글자들. 이름이 `=cmd|...` 로 시작하면
#: 엑셀이 그것을 실행하려 든다 — 우리가 만든 파일이 남의 컴퓨터에서 도는 셈이라
#: 반드시 막는다. 값을 지우지 않고 앞에 홑따옴표를 붙여 글자로 만든다.
FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def defuse(value: str | None) -> str:
    """셈식으로 읽힐 값을 글자로 묶는다.

    **지우거나 바꾸지 않는다.** 환자 이름이 `-` 로 시작할 수도 있고, 그 이름은
    그대로 남아야 한다. 앞에 홑따옴표 하나만 붙인다 — 엑셀이 그것을 「이건
    글자다」로 읽고 화면에는 안 보인다.
    """
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in FORMULA_LEAD else text


def clock(at: datetime | None) -> str:
    if at is None:
        return ""
    return at.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M")


def identity(item: SentMessageItem) -> str:
    """화면의 식별정보 칸과 같은 모양 — 「여 · 34세 · 1992-05-20」."""
    parts = []
    if GENDER_SAYING.get(str(item.gender)):
        parts.append(GENDER_SAYING[str(item.gender)])
    parts.append(f"{item.age}세")
    parts.append(item.birth_date.isoformat())
    return " · ".join(parts)


def viewed_saying(item: SentMessageItem) -> str:
    """못 나간 문자에 열람을 묻지 않는다 — 원문도 실패 줄에는 「—」를 적는다."""
    if item.status is GuideMessageStatus.FAILED:
        return "—"
    return "열람" if item.viewed else "미열람"


def csv_rows(items: list[SentMessageItem]) -> list[list[str]]:
    rows = [list(HEADER)]
    for item in items:
        rows.append(
            [
                clock(item.happened_at),
                defuse(item.name),
                defuse(item.hospital_patient_no),
                identity(item),
                defuse(item.prescription_set or ""),
                KIND_SAYING.get(item.kind, str(item.kind)),
                STATUS_SAYING.get(item.status, str(item.status)),
                FAILURE_SAYING.get(item.failure_code, "") if item.failure_code else "",
                viewed_saying(item),
                clock(item.viewed_at),
            ]
        )
    return rows


def csv_filename(since: date, until: date) -> str:
    """받은 사람이 나중에 무엇인지 알 수 있게 기간을 이름에 넣는다.

    한글을 파일 이름에 쓰지 않는다 — `Content-Disposition` 은 라틴 글자만
    안전하게 실을 수 있고, 브라우저마다 다르게 깨진다.
    """
    return f"send-history-{since.isoformat()}-to-{until.isoformat()}.csv"
