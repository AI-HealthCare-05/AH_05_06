from datetime import datetime
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
    """환자 화면의 차례와 같다 — P2 · P3 · P4, 그리고 문자 설정.

    `EMERGENCY` 는 `CAUTION` 바로 뒤다. **화면에서 둘은 같은 「주의사항」 탭
    안에 이어 붙는다** — 응급 문장만 따로 탭을 만들면 원장님이 그 탭을 안 열고
    넘길 수 있고, 그 문장은 넘겨도 되는 문장이 아니다.

    나눈 까닭은 잠금 단위 때문이다. `locked` 는 섹션 단위라, 🚨 응급 문장을
    지키려고 `caution` 전체를 잠그면 **고칠 수 있어야 할 일반 주의 문구까지
    잠긴다**(와이어프레임 D1-2 — 「🚨 응급 문장만 수정 불가」).
    """

    MEDICATION = "medication"
    CAUTION = "caution"
    EMERGENCY = "emergency"
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
    """안내문 다섯 갈래. 한 갈래가 한 행이다.

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


class PatientGuideLink(models.Model):
    """승인 안내 한 건을 여는 개발용 링크 — KEY-90 최소 범위.

    원문 토큰은 발급 응답에서 한 번만 전달하고 저장하지 않는다. DB에는
    SHA-256 digest만 남겨 DB 덤프만으로 환자 화면을 열 수 없게 한다.

    한 안내에 링크를 하나만 허용한다. 폐기·재발급 정책이 확정되기 전에
    발급 API를 반복 호출해 유효 링크가 여러 개 생기는 일을 막기 위해서다.
    """

    patient_guide_link_id = fields.BigIntField(primary_key=True)
    guide_document: fields.OneToOneRelation[GuideDocument] = fields.OneToOneField(
        "models.GuideDocument",
        related_name="patient_link",
        on_delete=OnDelete.CASCADE,
        source_field="guide_document_id",
    )
    guide_document_id: int
    token_digest = fields.CharField(max_length=64, unique=True)
    expires_at = fields.DatetimeField()
    issued_by = fields.BigIntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "patient_guide_link"
        indexes = (("expires_at",),)


class PatientOtpChallenge(models.Model):
    """환자 링크 한 건의 현재 OTP 상태 — KEY-91.

    OTP 원문은 저장하지 않는다. 링크마다 행을 하나만 두고 재발급 때 digest를
    교체해 이전 OTP를 즉시 무효화한다. 실패 횟수와 잠금은 같은 행에 남기므로
    재발급으로 실패 제한을 우회할 수 없다.
    """

    patient_otp_challenge_id = fields.BigIntField(primary_key=True)
    patient_guide_link: fields.OneToOneRelation[PatientGuideLink] = fields.OneToOneField(
        "models.PatientGuideLink",
        related_name="otp_challenge",
        on_delete=OnDelete.CASCADE,
        source_field="patient_guide_link_id",
    )
    patient_guide_link_id: int
    otp_digest = fields.CharField(max_length=64)
    otp_salt = fields.CharField(max_length=32)
    expires_at = fields.DatetimeField()
    failed_attempts = fields.SmallIntField(default=0)
    locked_until: datetime | None = fields.DatetimeField(null=True)
    consumed_at: datetime | None = fields.DatetimeField(null=True)
    issued_at = fields.DatetimeField()
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "patient_otp_challenge"
        indexes = (("expires_at",), ("locked_until",))


class CheckInMedication(StrEnum):
    TAKING = "taking"
    UNCOMFORTABLE = "uncomfortable"
    MISSING = "missing"
    STOPPED_SIDE_EFFECT = "stopped_side_effect"
    STOPPED_IMPROVED = "stopped_improved"


class CheckIn(models.Model):
    """승인 안내 한 건에 연결된 D+7 복약·통증 응답 — KEY-151.

    `visit_id`를 다시 저장하지 않는다. 응답은 `guide_document_id`를 거쳐
    `GuideDocument.visit_id`로 추적하므로 진료 관계가 두 곳에서 어긋나지 않는다.
    Walking Skeleton은 한 안내에 응답 한 건만 허용한다.
    """

    check_in_id = fields.BigIntField(primary_key=True)
    guide_document: fields.OneToOneRelation[GuideDocument] = fields.OneToOneField(
        "models.GuideDocument",
        related_name="check_in",
        on_delete=OnDelete.CASCADE,
        source_field="guide_document_id",
    )
    guide_document_id: int
    medication = fields.CharEnumField(enum_type=CheckInMedication)
    pain_had = fields.BooleanField(null=True)
    pain_score = fields.SmallIntField(null=True)
    pain_types: fields.Field[list[str]] = fields.JSONField(default=list)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "check_in"
        indexes = (("created_at",),)


class PatientUsageEventType(StrEnum):
    """환자가 한 일. **무엇을 했는지만 남기고 무엇을 말했는지는 남기지 않는다.**"""

    GUIDE_VIEWED = "GUIDE_VIEWED"
    CHATBOT_ANSWERED = "CHATBOT_ANSWERED"


class PatientQuestionKind(StrEnum):
    """물음의 **갈래**. 물음 자체가 아니다.

    「비잔 먹고 머리가 아픈데 계속 먹어도 되나요」를 `MEDICATION` 으로만
    남긴다. 원문을 남기면 그것이 곧 의료 상담 기록이 되고, 병원이 열람할 수
    있게 되는 순간 KEY-5 의 「환자 대화 원문은 병원이 못 본다」가 깨진다.
    """

    MEDICATION = "MEDICATION"
    LIFESTYLE = "LIFESTYLE"
    SYMPTOM = "SYMPTOM"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    OTHER = "OTHER"


class PatientAnswerOutcome(StrEnum):
    """물음에 무엇으로 답했나.

    `BLOCKED` 와 `FALLBACK` 을 가른다 — 둘 다 「제대로 못 답했다」지만
    **막은 것과 못 한 것은 다른 문제**다. 막은 것이 늘면 규칙을 손봐야 하고,
    못 한 것이 늘면 지식이나 연동을 손봐야 한다.
    """

    ANSWERED = "ANSWERED"
    BLOCKED = "BLOCKED"
    FALLBACK = "FALLBACK"


class PatientUsageEvent(models.Model):
    """환자가 안내를 열람하고 챗봇을 쓴 **결과**만 남기는 이벤트 — KEY-170.

    KEY-143 의 환류 기반이다. 「몇 명이 열었나 · 무엇을 주로 묻나 · 얼마나
    막히나」를 세려면 이 표가 있어야 한다.

    **원문을 담지 않는다.** 질문·프롬프트·답변·링크 토큰 어느 것도 칸이 없다 —
    담을 자리를 만들지 않는 것이 담지 않겠다는 약속을 지키는 가장 확실한
    방법이다. 나중에 누가 「분석하려면 원문이 필요하다」고 할 때, 칸이 없으면
    그 이야기가 계약 변경으로 올라온다.

    `guide_document` 에 건다 — 안내문이 진료를 알고 진료가 병원을 안다.
    `visit_id` 를 사본으로 두면 두 값이 어긋날 자리가 생긴다(`#25` 리뷰).
    """

    patient_usage_event_id = fields.BigIntField(primary_key=True)
    guide_document: fields.ForeignKeyRelation[GuideDocument] = fields.ForeignKeyField(
        "models.GuideDocument",
        related_name="usage_events",
        on_delete=OnDelete.CASCADE,
        source_field="guide_document_id",
    )
    guide_document_id: int
    event_type = fields.CharEnumField(enum_type=PatientUsageEventType)
    #: 챗봇 답이면 어느 갈래의 물음이었나. 열람 이벤트면 비어 있다.
    question_kind = fields.CharEnumField(enum_type=PatientQuestionKind, null=True)
    #: 챗봇 답이면 무엇으로 답했나. 열람 이벤트면 비어 있다.
    answer_outcome = fields.CharEnumField(enum_type=PatientAnswerOutcome, null=True)
    #: 답의 근거가 된 안내 갈래. **원문이 아니라 어디를 봤는지**만 남긴다.
    grounded_section = fields.CharEnumField(enum_type=GuideSectionKey, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "patient_usage_event"
        indexes = (
            ("guide_document", "created_at"),
            ("event_type", "created_at"),
        )
