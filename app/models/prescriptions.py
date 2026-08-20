"""처방 — 복약안내가 「무엇을 언제까지」 라고 말할 근거 — KEY-137.

합성 데이터 100행 중 **99행에 처방이 있는데 넣을 표가 없었다.** 그래서
`소진예정일`(= `visited_at` + `duration_days`)이 파생으로 선언만 되어 있고
근거가 존재하지 않는 상태였다. 복약안내 본문·D+7 화면(`P7-*`)·이탈 플래그
「소진 후 7일 경과」가 전부 그 파생에 매달려 있다.

표를 둘로 가르는 이유는 **한 처방에 약이 여럿이기 때문**이다. 합성 데이터가
그렇게 생겼다.

    약    "비잔정 2mg + 진통제"
    용법  "1일 1회   + 필요시"

`+` 로 묶인 개수가 약과 용법에서 항상 같다(100행 전수 확인, 어긋난 행 0).
한 줄에 눌러 담으면 「두 번째 약의 용법」을 꺼낼 수 없다.
"""

from tortoise import fields, models
from tortoise.fields import OnDelete

from app.models.visits import Visit


class Prescription(models.Model):
    """한 진료의 처방 묶음.

    **`hospital_id` 사본을 두지 않는다.** 병원은 `visit` 을 타고 판단한다.

    이 저장소가 스스로 정한 규칙이다 — 같은 값을 두 곳에 두면 어긋날 자리도
    함께 생기고, 어긋난 순간 남의 의원 것이 열린다(`#25` 리뷰). `guide_document`
    가 `hospital_id` 를 들고 있지만 그것은 목록을 거르는 인덱스용 사본이고,
    `GuideService.get()` 은 격리 판정에 그 사본을 쓰지 않는다.

    처방은 목록으로 훑을 일이 없다 — 늘 「이 진료의 처방」으로 읽는다. 사본을
    둘 이유가 없으니 두지 않는다.
    """

    prescription_id = fields.BigIntField(primary_key=True)
    visit_id: int
    visit: fields.ForeignKeyRelation[Visit] = fields.ForeignKeyField(
        "models.Visit",
        related_name="prescriptions",
        on_delete=OnDelete.CASCADE,
        source_field="visit_id",
    )
    #: 진료 당시 처방 세트 이름의 **스냅샷**이다 — "자궁내막증 · 비잔 (계속)".
    #:
    #: 정본(`mapping.py`)이 이 칸을 `prescription_set_version_id` 로 불렀고
    #: 문서는 `bigint` 이라고 적었는데, **실제 값은 id 가 아니라 사람이 읽는
    #: 이름**이다(8종 · 최대 17자). 세트 템플릿 표는 어디에도 없다.
    #: `..._id` 라는 이름이 붙은 칸에 한글 문구가 들어 있으면 다음 사람이
    #: 조인할 표를 찾게 되므로, 담고 있는 것대로 부른다.
    #:
    #: 템플릿 표가 생기면 그때 FK 를 더한다. 이 칸은 `visit.department` 처럼
    #: 그때의 이름을 남기는 스냅샷으로 남는다 — 세트가 개정돼도 그 진료가
    #: 무엇을 근거로 했는지는 바뀌면 안 된다.
    prescription_set = fields.CharField(max_length=100)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    items: fields.ReverseRelation["PrescriptionItem"]

    class Meta:
        table = "prescription"


class PrescriptionItem(models.Model):
    """처방 안의 약 한 줄."""

    prescription_item_id = fields.BigIntField(primary_key=True)
    prescription_id: int
    prescription: fields.ForeignKeyRelation[Prescription] = fields.ForeignKeyField(
        "models.Prescription",
        related_name="items",
        on_delete=OnDelete.CASCADE,
        source_field="prescription_id",
    )
    name = fields.CharField(max_length=100)
    frequency = fields.CharField(max_length=50)
    #: **`null` 이 허용된다. 그게 이 칸의 요점이다.**
    #:
    #: 합성 데이터의 `처방일수` 는 행에 하나뿐이다 — `+` 가 들어간 행이 하나도
    #: 없다(전수 확인). 그런데 그 행에 약은 둘일 수 있다.
    #:
    #:     약    "비잔정 2mg + 진통제"
    #:     용법  "1일 1회   + 필요시"
    #:     일수  "84"
    #:
    #: 그 84 를 두 줄에 다 붙이면 **「진통제를 84일간 드세요」** 가 된다.
    #: 복약지도 프로그램에서 그건 틀린 문장이고, 소진예정일까지 진통제 기준으로
    #: 하나 더 생긴다.
    #:
    #: 그래서 **`필요시` 인 약에는 기간을 넣지 않는다.** 없는 값을 지어내는 대신
    #: 비워 둔다 — 없는 것과 모르는 것을 같게 두는 편이 정직하다.
    duration_days: int | None = fields.IntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "prescription_item"


#: 기간이 붙지 않는 용법. 「필요할 때만」 먹는 약은 정해진 복용 기간이 없다.
AS_NEEDED = "필요시"
