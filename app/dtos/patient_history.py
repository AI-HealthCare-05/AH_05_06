"""환자 이력 — 와이어프레임 S2-2 「환자 이력 모달 ★ 신설」.

원문 주석이 층을 못박는다: 「이력을 어드민으로만 묶으면 스탭이 관리를 못
한다. 그래서 두 층으로 나눈다 — 관리에 필요한 만큼(**발송 · 열람 · 응답**)은
이 모달로 스탭 · 의사 모두에게, 감사 수준(누가 열어봤나 · 토큰 · 버전 이력)은
A1-7로 관리자에게만.」

**그래서 여기에 직원 열람 기록과 토큰 이력을 담지 않는다.** 담을 칸을 만들지
않는 것이 담지 않겠다는 약속을 지키는 가장 확실한 방법이다 —
`PatientUsageEvent` 가 원문을 담지 않는 것과 같은 판단이다.
"""

from datetime import date, datetime

from pydantic import BaseModel

from app.dtos.visits import DoctorResponse
from app.models.visits import GuideMessageKind


class HistoryCheck(BaseModel):
    """확인 문자 한 통 — 원문 「일주일 뒤 05-27 미열람」·「… 응답 「잘 먹고 있어요」」."""

    kind: GuideMessageKind
    at: datetime
    sent: bool
    #: 이 문자 뒤에 안내를 열었는가. **문자 단위로 붙일 수 있는 이유**는
    #: 열람에 시각이 남기 때문이다 — 이 문자가 나간 뒤 다음 문자 전까지 열었으면
    #: 이 문자를 보고 연 것으로 읽는다.
    viewed_at: datetime | None
    #: 복약 응답. **`CHECK_D7` 에만 붙는다** — `check_in` 이 「승인 안내 한 건에
    #: 연결된 D+7 응답」이고 안내문당 한 건뿐이다(KEY-151).
    answer: str | None


class HistoryVisit(BaseModel):
    """진료 한 건 — 원문의 블록 하나."""

    visit_id: int
    visited_at: datetime
    prescription_set: str | None
    course_days: int | None

    #: 진료 안내문이 나간 시각. 안 나갔으면 없다.
    guide_sent_at: datetime | None
    #: 환자가 처음 연 시각. **몇 장까지 읽었는지는 담지 않는다** — 열람
    #: 이벤트에 어느 장인지가 남지 않아 셈할 수 없다(원문의 「5장 중 3장」).
    guide_viewed_at: datetime | None

    checks: list[HistoryCheck]

    #: 약이 떨어지는 날. 처방일수를 모르면 없다 — **셈하지 않는다.**
    runs_out_on: date | None
    #: 이 진료 뒤에 다시 왔는가. 원문의 「재진 예약 없음」이 이 값이다.
    revisited: bool


class PatientHistoryResponse(BaseModel):
    patient_id: int
    name: str
    hospital_patient_no: str
    phone: str
    diagnosis_name: str | None
    doctor: DoctorResponse | None

    visits: list[HistoryVisit]
    #: 이 환자의 진료가 모두 몇 건인가. 원문 「지난 안내문 4건 중 3건」의 앞 수다.
    total: int
