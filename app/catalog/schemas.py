"""약속처방 카탈로그 — KEY-234.

의사가 설정(D2-3)에서 정해 두는 처방 세트다. 판독 확인 화면(S1-6)의 「처방」
칸이 이 목록에서 고른다 — 판독이 읽은 약 이름을 그대로 쓰지 않는다.

이름을 고르면 그 세트에 묶인 주의 문구(`DrugCautionContent`)가 안내문에
붙는다. 그래서 **자유 입력이 아니라 목록**이어야 한다: 「비잔」과 「비잔정」이
다른 값으로 들어오면 붙일 문구를 못 찾는다.

**목록과 상세를 가른다.** 목록은 고르는 칸이 쓰고(이름과 확인 항목이면 된다),
상세는 설정 화면이 쓴다. 목록에 상세를 다 실으면 고르는 칸 하나 그리려고
여덟 세트의 약·문구를 전부 받아 온다.
"""

from app.dtos.base import StrictModel
from app.models.catalog import SetDaysMode, SetDisease, SetPhase
from app.models.visits import VisitCheckKey


class PrescriptionSetResponse(StrictModel):
    prescription_set_id: int
    name: str

    #: 설정 화면의 왼쪽 레일이 이것으로 묶는다(D2-3 「자궁내막증 4 · 다낭성 4」).
    #: 상세를 받아야 알 수 있게 두면, 묶어서 세우려고 여덟 번 다녀와야 한다.
    disease: SetDisease = SetDisease.ENDOMETRIOSIS

    #: 이 처방에서 여쭙는 확인 항목 — 화면 차례대로 (와이어프레임 S1-6 「처방별」).
    #:
    #: 목록과 **함께** 준다. 따로 물으면 화면이 처방을 고를 때마다 한 번 더
    #: 다녀와야 하고, 그 사이 확인 항목 칸이 비었다 찼다 한다.
    check_items: list[VisitCheckKey] = []


class SetDrug(StrictModel):
    """처방 세트에 든 약 하나 — 와이어프레임 D2-3 「처방 약」."""

    name: str
    frequency: str | None = None
    note: str | None = None


class PrescriptionSetDetail(StrictModel):
    """설정 화면(D2-3)이 읽고 쓰는 한 세트."""

    prescription_set_id: int
    name: str
    disease: SetDisease
    phase: SetPhase

    #: EMR 「총투」 칸의 의미. **소진 예정일이 이 값으로 셈해진다.**
    days_mode: SetDaysMode
    #: 한 통이 며칠치인가. `days_mode` 가 `PACK` 일 때만 쓴다.
    days_per_pack: int | None = None

    emr_code: str | None = None
    revisit_note: str | None = None

    #: 자동 발송 기본값. 일주일 뒤는 칸이 없다 — 어느 처방에서도 못 끈다.
    check_d15_on: bool = True
    check_d30_on: bool = False
    run_out_on: bool = True
    run_out_before_days: int = 3

    drugs: list[SetDrug] = []
    check_items: list[VisitCheckKey] = []


class PrescriptionSetSaveRequest(StrictModel):
    """설정 화면이 보내는 한 판.

    **통째로 받는다.** 약을 하나 지우고 확인 항목을 하나 켜는 것이 한 번의
    「저장」인데, 조각으로 받으면 중간에 끊겼을 때 반쪽이 남는다.
    """

    name: str
    disease: SetDisease
    phase: SetPhase
    days_mode: SetDaysMode
    days_per_pack: int | None = None
    emr_code: str | None = None
    revisit_note: str | None = None
    check_d15_on: bool = True
    check_d30_on: bool = False
    run_out_on: bool = True
    run_out_before_days: int = 3
    drugs: list[SetDrug] = []
    check_items: list[VisitCheckKey] = []
