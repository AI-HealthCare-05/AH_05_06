from enum import StrEnum

from tortoise import fields, models
from tortoise.fields import OnDelete

from app.models.patients import Patient


class VisitStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"


class Visit(models.Model):
    """One clinic-scoped encounter belonging to exactly one patient."""

    visit_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    patient_id: int
    patient: fields.ForeignKeyRelation[Patient] = fields.ForeignKeyField(
        "models.Patient",
        related_name="visits",
        on_delete=OnDelete.RESTRICT,
        source_field="patient_id",
    )
    doctor_id: int | None = fields.BigIntField(null=True)
    department = fields.CharField(max_length=100, null=True)
    visited_at = fields.DatetimeField()
    visit_summary = fields.TextField(null=True)
    doctor_note = fields.TextField(null=True)
    status = fields.CharEnumField(enum_type=VisitStatus, default=VisitStatus.COMPLETED)
    planned_stop = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "visit"
        indexes = (
            ("hospital_id", "visited_at"),
            ("patient", "visited_at"),
        )


class GuideStatus(StrEnum):
    """안내문이 지금 어디에 있는가.

    **새 이름을 만들지 않는다.** `docs/contracts/patient-visit-api-v1.md` §6 이
    화면 탭과 `detail_status` 를 이미 얼려 두었고, 이 값들이 그대로 그 탭으로
    파생된다. 같은 것을 두 어휘로 부르기 시작하면 어느 쪽이 정본인지 흐려진다.

        STAFF_REVIEW        스탭 확인 중        → 작성 중
        APPROVAL_PENDING    승인 요청           → 승인 요청
        SCHEDULED_TO_SEND   발송 예약됨         → 발송 대기
        APPROVAL_RETURNED   승인 반려           → 보완

    승인의 결과가 `APPROVED` 가 아니라 `SCHEDULED_TO_SEND` 인 것이 중요하다 —
    **승인이 곧 발송 예약이다**(와이어프레임 D1-5 「스탭이 발송 버튼을 누르지
    않는다」). 승인과 발송 사이에 사람이 한 번 더 손대는 자리를 만들지 않는다.
    """

    STAFF_REVIEW = "STAFF_REVIEW"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    SCHEDULED_TO_SEND = "SCHEDULED_TO_SEND"
    APPROVAL_RETURNED = "APPROVAL_RETURNED"


class GuideSectionKey(StrEnum):
    """환자 화면의 차례와 같다 — P2 · P3 · P4, 그리고 문자 설정."""

    MEDICATION = "medication"
    CAUTION = "caution"
    LIFE = "life"
    MESSAGES = "messages"


class GuideEventType(StrEnum):
    EDITED = "EDITED"
    APPROVED = "APPROVED"
    RETURNED = "RETURNED"


class GuideDocument(models.Model):
    """진료 한 건이 만들어 내는 안내문. `visit` 과 1:1 이다.

    한 진료에 안내문이 둘일 수 없다 — 환자가 받는 것이 하나이기 때문이다.
    다시 만들면 같은 행의 내용이 바뀌고 `version` 이 오른다.
    """

    guide_document_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    visit: fields.OneToOneRelation[Visit] = fields.OneToOneField(
        "models.Visit",
        related_name="guide",
        on_delete=OnDelete.CASCADE,
        source_field="visit_id",
    )
    #: Tortoise 가 만들어 주는 것들. 선언해 두지 않으면 타입 검사가 못 본다.
    visit_id: int
    sections: fields.ReverseRelation["GuideSection"]
    events: fields.ReverseRelation["GuideEvent"]

    status = fields.CharEnumField(enum_type=GuideStatus, default=GuideStatus.STAFF_REVIEW)
    version = fields.IntField(default=1)

    #: 승인한 사람과 시각. 「누가 이 글을 환자에게 내보냈는가」의 답이다.
    approved_by = fields.BigIntField(null=True)
    approved_at = fields.DatetimeField(null=True)
    #: 발송 예정 시각. 승인이 이 값을 채운다 — 승인과 예약이 한 동작이다.
    scheduled_at = fields.DatetimeField(null=True)

    #: 마지막 반려 사유. 스탭 알림에 그대로 뜨는 문장이라 여기 남긴다.
    #: 이력 전체는 GuideEvent 가 갖는다.
    returned_reason = fields.CharField(max_length=200, null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "guide_document"
        indexes = (("hospital_id", "status"),)


class GuideSection(models.Model):
    """안내문 네 갈래. 한 갈래가 한 행이다.

    **생성 원문과 사람이 고친 것을 함께 남긴다.** 하나만 두면 「AI 가 이렇게
    썼는데 원장님이 이렇게 고쳤다」를 다음 초안 개선에 쓸 수 없다
    (와이어프레임 D1-2 — 「AI 가 만든 원문과 원장님이 고친 결과를 함께 남겨
    다음 초안을 개선하는 데 쓴다」).

    `locked` 는 🚨 응급 문장이다. 식약처 의약품정보를 근거로 미리 써 둔
    문장이라 약이 바뀌면 문장도 함께 바뀐다 — 사람이 손댈 자리가 아니다.
    """

    guide_section_id = fields.BigIntField(primary_key=True)
    guide_document: fields.ForeignKeyRelation[GuideDocument] = fields.ForeignKeyField(
        "models.GuideDocument",
        related_name="sections",
        on_delete=OnDelete.CASCADE,
    )
    section_key = fields.CharEnumField(enum_type=GuideSectionKey)
    generated_body = fields.TextField()
    edited_body = fields.TextField(null=True)
    locked = fields.BooleanField(default=False)
    #: AI 가 스스로 자신 없는 곳 · 지난번과 달라진 곳 · 값이 빠진 곳.
    #: 화면의 ⚠ 는 이 값이 있을 때만 뜬다 — 화면이 판정하지 않는다.
    warn = fields.CharField(max_length=200, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "guide_section"
        unique_together = (("guide_document", "section_key"),)

    @property
    def body(self) -> str:
        """지금 환자에게 나갈 글. 고친 것이 있으면 그것이다."""
        return self.edited_body if self.edited_body is not None else self.generated_body


class GuideEvent(models.Model):
    """승인 · 반려 · 수정 이력.

    「누가 언제 무엇을 했나」가 남아야 나중에 되짚을 수 있다. 특히 반려는
    **사유가 함께 남아야** 한다 — 스탭이 무엇을 고쳐야 하는지가 그 문장이다.

    상태를 바꾸는 것과 이력을 남기는 것은 **한 트랜잭션**이다. 갈라 두면
    상태만 바뀌고 이력이 빈 행이 생기고, 그러면 감사가 성립하지 않는다.
    """

    guide_event_id = fields.BigIntField(primary_key=True)
    guide_document: fields.ForeignKeyRelation[GuideDocument] = fields.ForeignKeyField(
        "models.GuideDocument",
        related_name="events",
        on_delete=OnDelete.CASCADE,
    )
    event_type = fields.CharEnumField(enum_type=GuideEventType)
    #: 수정이면 어느 갈래를 고쳤는가. 승인 · 반려면 비어 있다.
    section_key = fields.CharEnumField(enum_type=GuideSectionKey, null=True)
    #: 반려 사유. 반려가 아니면 비어 있다.
    reason = fields.CharField(max_length=200, null=True)
    actor_id = fields.BigIntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "guide_event"
        indexes = (("guide_document", "created_at"),)
