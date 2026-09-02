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


class SetDrug(StrictModel):
    """처방 세트에 든 약 하나 — 와이어프레임 D2-3 「처방 약」."""

    name: str
    frequency: str | None = None
    note: str | None = None


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

    #: 이 처방에 든 약 — 화면 차례대로 (와이어프레임 D2-3 「처방 약」).
    #:
    #: **확인 항목과 같은 이유로 함께 준다.** 판독 화면이 처방을 고르는 순간
    #: 아래에 약 목록을 세워야 하는데, 그때 한 번 더 다녀오면 목록이 비었다
    #: 찼다 한다 (2heej 님 `#176` 리뷰).
    drugs: list[SetDrug] = []

    #: 「총투」 칸의 의미와 한 통의 일수. **약마다 며칠인지가 이 둘로 정해진다** —
    #: 판독이 읽은 총투 하나를 여기 규칙으로 환산한다. 세트는 「이 처방은 통으로
    #: 센다」까지만 알고, 몇 통인지는 그 진료의 판독값이 안다.
    days_mode: SetDaysMode = SetDaysMode.DAYS
    days_per_pack: int | None = None


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


