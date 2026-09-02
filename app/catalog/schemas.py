"""약속처방 목록 응답 — KEY-234.

의사가 설정(D2)에서 정해 두는 처방 세트다. 판독 확인 화면(S1-6)의 「처방」
칸이 이 목록에서 고른다 — 판독이 읽은 약 이름을 그대로 쓰지 않는다.

이름을 고르면 그 세트에 묶인 주의 문구(`DrugCautionContent`)가 안내문에
붙는다. 그래서 **자유 입력이 아니라 목록**이어야 한다: 「비잔」과 「비잔정」이
다른 값으로 들어오면 붙일 문구를 못 찾는다.
"""

from app.dtos.base import StrictModel
from app.models.visits import VisitCheckKey


class PrescriptionSetResponse(StrictModel):
    prescription_set_id: int
    name: str

    #: 이 처방에서 여쭙는 확인 항목 — 화면 차례대로 (와이어프레임 S1-6 「처방별」).
    #:
    #: 목록과 **함께** 준다. 따로 물으면 화면이 처방을 고를 때마다 한 번 더
    #: 다녀와야 하고, 그 사이 확인 항목 칸이 비었다 찼다 한다.
    check_items: list[VisitCheckKey] = []
