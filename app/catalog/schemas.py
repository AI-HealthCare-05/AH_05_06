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

from pydantic import Field

from app.dtos.base import StrictModel
from app.models.catalog import SetDaysMode, SetDisease, SetPhase
from app.models.visits import VisitCheckKey


class SetDrug(StrictModel):
    """처방 세트에 든 약 하나 — 와이어프레임 D2-3 「처방 약」.

    **길이를 여기서 막는다.** 표의 한계와 같은 값이다(`models/catalog.py`).
    안 막으면 MySQL 이 `DataError` 를 던지고 그것을 잡는 자리가 없어 **500**
    이 난다 — 화면은 「잠시 후 다시 시도해 주세요」라고 하는데 몇 번을 눌러도
    같은 500 이고, 어느 칸이 문제인지 말해 주지 않는다. EMR 에서 성분명을
    통째로 붙여 넣으면 100자는 쉽게 넘는다.
    """

    name: str = Field(max_length=100)
    frequency: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=200)


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

    #: **감춘 처방인가.** 「없다」가 아니라 「새로 못 고른다」는 뜻이다 —
    #: 이미 이 처방으로 나간 진료기록에서는 문구가 그대로 붙는다.
    #: 그래서 목록은 **감춘 것도 다 준다.** 거르는 것은 새로 고르는 칸뿐이다.
    hidden: bool = False

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
    #: 한 통이 며칠치인가. 표가 `SmallIntField` 라 범위를 넘으면 500 이 난다.
    days_per_pack: int | None = None


class PrescriptionSetSaveRequest(StrictModel):
    """설정 화면이 보내는 한 판.

    **통째로 받는다.** 약을 하나 지우고 확인 항목을 하나 켜는 것이 한 번의
    「저장」인데, 조각으로 받으면 중간에 끊겼을 때 반쪽이 남는다.
    """

    # **이름은 받지 않는다.** `StrictModel` 이 `extra="forbid"` 라, 담아 보내면
    # 400 `INVALID_REQUEST` 로 튕긴다 — 받아 놓고 무시하면 「바꿔 달라 보냈는데
    # 200 이 오고 안 바뀐」 조용한 성공이 된다.
    #
    # 왜 못 바꾸나: `Prescription.prescription_set` 은 스냅샷 **문자열**이고
    # (KEY-137) `guides.py`·`drug_caution.py` 가 그 문자열로 세트를 찾아
    # 안내문 문구를 붙인다. 이름을 바꾸면 **기존 진료기록의 문구가 통째로
    # 떨어져 나가고** 화면엔 아무 말도 안 뜬다. 바꾸는 대신 숨기고 새로 만든다.
    disease: SetDisease
    phase: SetPhase
    days_mode: SetDaysMode
    #: 한 통이 며칠치인가. 표가 `SmallIntField` 라 범위를 넘으면 500 이 난다.
    days_per_pack: int | None = Field(default=None, ge=1, le=32767)
    emr_code: str | None = None
    revisit_note: str | None = None
    check_d15_on: bool = True
    check_d30_on: bool = False
    run_out_on: bool = True
    run_out_before_days: int = Field(default=3, ge=1, le=365)
    drugs: list[SetDrug] = []
    check_items: list[VisitCheckKey] = []


class PrescriptionSetDetail(StrictModel):
    """설정 화면(D2-3)이 읽고 쓰는 한 세트."""

    prescription_set_id: int
    name: str

    #: 감춘 처방인가. 화면이 「숨기기」와 「되살리기」를 가른다.
    hidden: bool = False
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


class PrescriptionSetCreateRequest(StrictModel):
    """새 처방 만들기 — **이름과 진단만 받는다.**

    나머지는 만든 뒤 설정 화면에서 고친다. 한 번에 다 받으면 「만들기」가
    저장과 같아지고, 잘못 지은 이름을 되돌릴 길이 없는데(이름은 못 바꾼다)
    긴 판을 다 채운 뒤에야 그것을 알게 된다.
    """

    name: str = Field(max_length=100)
    disease: SetDisease
