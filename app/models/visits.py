from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from tortoise import fields, models
from tortoise.fields import OnDelete

from app.models.patients import Patient

if TYPE_CHECKING:
    from app.models.catalog import DrugCautionContent


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
    #: 스탭이 확인을 마치고 의사에게 넘겼다 (와이어프레임 S1-11).
    #: 누가 언제 넘겼는지가 남아야, 승인이 늦을 때 어디서 멈췄는지 안다.
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    #: 승인을 거뒀다 — 승인했는데 잘못된 것을 발견했을 때.
    #: 승인 줄을 지우지 않고 이 줄을 더한다: 승인했다가 거뒀다는 것이
    #: 기록이고, 지우면 「왜 예약이 사라졌지」에 답할 수 없다.
    UNAPPROVED = "UNAPPROVED"
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
    sections: fields.ReverseRelation[GuideSection]
    events: fields.ReverseRelation[GuideEvent]

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

    #: 확인 문자를 몇 시에 보낼지 (와이어프레임 S1-14 「확인 문자 시각」).
    #: 회차마다 따로 두지 않는 이유는 **화면에 고르는 자리가 하나**이기
    #: 때문이다 — 원문 주석: 「확인 · 재진 문자에 적용」. 회차별로 담아 두면
    #: 화면이 못 만드는 상태(회차마다 다른 시각)를 표가 허용하게 된다.
    #: 안내문 자신은 이 값을 따르지 않는다 — 승인 시각 규칙(기본 18:00)이다.
    check_hour = fields.SmallIntField(default=10)

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

    `drug_caution_content_id` 는 caution·emergency 섹션 생성 시 사용한
    `DrugCautionContent` 버전의 ID다(KEY-165, KEY-180 §6). null 이면 범용 문구를
    사용했거나 caution/emergency 가 아닌 섹션이다. 근거 버전은 `generated_body`
    기준이며 의사가 고친 `edited_body` 와는 무관하다.
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
    # KEY-165: generated_body 생성에 사용한 DrugCautionContent 버전 추적.
    # DrugCautionContent는 삭제되지 않고 DEPRECATED되므로 SET_NULL은 비상 안전망이다.
    drug_caution_content_id: int | None
    drug_caution_content: fields.ForeignKeyRelation[DrugCautionContent] | None = fields.ForeignKeyField(
        "models.DrugCautionContent",
        related_name="guide_sections",
        on_delete=OnDelete.SET_NULL,
        null=True,
        source_field="drug_caution_content_id",
    )
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


class GuideMessageKind(StrEnum):
    """문자 한 통이 무엇인가 — 와이어프레임 D1-6 「발송 · 예정」.

    회차를 값으로 두는 것이 중요하다. 「일곱째 날」을 시각에서 되계산하면
    진료일이 고쳐질 때 어느 회차였는지를 잃는다.
    """

    #: 승인 직후 나가는 진료 안내문. 링크가 이것으로 간다.
    GUIDE = "GUIDE"
    #: 확인 문자 — 복약을 이어 가고 있는지 묻는다.
    CHECK_D7 = "CHECK_D7"
    CHECK_D15 = "CHECK_D15"
    CHECK_D30 = "CHECK_D30"
    #: 약이 떨어지기 전에 알린다. 처방일수를 알아야 셈할 수 있다.
    RUN_OUT = "RUN_OUT"


class GuideMessageHold(StrEnum):
    """**왜 붙들고 있나** — 와이어프레임 S2-3.

    원문이 딱 둘로 못박는다: 「스탭이 손댈 일은 보류 두 가지뿐이다 — 번호가
    잘못됐을 때와 문자가 떨어졌을 때.」

    실패 사유(`GuideMessageFailure`)와 **다른 목록**이다. 겹치는 낱말이 있어
    한 목록으로 합치고 싶어지지만, 재는 것이 다르다 — 이쪽은 「보내기 전에
    이미 아는 것」이고 저쪽은 「보내 보고 안 것」이다.
    """

    #: 이 환자 번호로는 못 보낸다는 것을 이미 안다 (앞 통이 그 번호로 실패했다).
    INVALID_PHONE = "INVALID_PHONE"
    #: 의원의 문자 잔량이 없다. **환자마다 다르지 않다** — 그래서 실패가 아니다.
    NO_CREDIT = "NO_CREDIT"


class GuideMessageFailure(StrEnum):
    """**보내 봤는데 안 됐다** — 와이어프레임 D1-7 「실패 이유 넷」.

    원문: 「ⓘ 실패 이유 넷 — 잘못된 번호 · 수신 거부 · 통신사 오류 ·
    발신번호 미등록」. 넷으로 못박혀 있으므로 자유 문자열로 두지 않는다 —
    자유롭게 두면 발송기를 붙이는 사람마다 다른 낱말을 넣고, 화면은 그중
    아는 것만 사람 말로 옮긴다.
    """

    INVALID_PHONE = "INVALID_PHONE"
    OPT_OUT = "OPT_OUT"
    CARRIER = "CARRIER"
    #: 이것만 처리 경로가 다르다 — 어드민 A1-5 에서 발신번호를 등록한다(D1-7).
    SENDER_UNREGISTERED = "SENDER_UNREGISTERED"


class GuideMessageStatus(StrEnum):
    """문자 한 통이 지금 어디에 있는가.

    **한 통 단위다.** 다섯 통 중 어느 것이든 실패할 수 있고, 실패한 것만
    고쳐 다시 보낸다 (D1-6 캡션 — 「발송 상태는 문자 한 통 단위다」).

    `CANCELED` 는 사람이 회차를 끈 것이다. 줄을 지우지 않는 이유는, 껐다는
    것도 기록이기 때문이다 — 나중에 「왜 안 갔지」를 물을 때 답이 있어야 한다.
    """

    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    #: **보내려 했고 안 됐다.** 지난 일이다 — 사유는 `GuideMessageFailure`.
    FAILED = "FAILED"
    #: **아직 안 보냈고, 지금 보내면 안 될 것을 안다.** 앞일이다.
    #:
    #: 와이어프레임 S2-3 이 실패와 나란히 두고 따로 센다(「안 나간 것 3건
    #: (실패 1 · 보류 2)」). 박수빈의 08-11 진료 안내문은 「⚠ 잘못된 번호」로
    #: 실패했고, 같은 번호로 예약된 08-14 것은 「⏸ 보류 · 번호」다 — **같은
    #: 원인인데 상태가 다르다.** 지난 것은 실패, 앞으로 나갈 것은 보류다.
    #:
    #: 실패로 뭉치면 「고칠 수 있는 것」과 「이미 벌어진 것」이 한 무더기가
    #: 되어, 스탭이 무엇을 손대야 하는지 안 보인다.
    HELD = "HELD"
    CANCELED = "CANCELED"


class GuideMessageSetting(models.Model):
    """이 진료의 문자 회차 설정 — 와이어프레임 S1-14 「문자 설정」.

    **`GuideMessage` 와 다른 표다.** 저쪽은 「나갈 문자 한 통」이고 승인해야
    생긴다. 여기는 「이 환자에게 어떤 회차를 어떤 문구로 보낼지」이고, 승인
    **전에** 스탭이 정한다. 한 표로 합치면 승인 전에는 담을 데가 없다.

    행이 없는 회차는 **기본값**이다 (`_DEFAULT_ON`). 화면을 한 번도 안 만진
    진료까지 미리 다섯 줄을 채우지 않는다 — 안 만졌다는 것과 기본값으로
    정했다는 것은 여기서 같은 뜻이라, 굳이 갈라 적을 이유가 없다.

    `body` 가 비면 기본 문구다. 원문의 우선순위는 「이 환자만 적용」 >
    의원 템플릿(D2-5) > 기본인데, 이 표가 담는 것은 **맨 앞 하나**다 —
    의원 템플릿은 아직 없다.
    """

    guide_message_setting_id = fields.BigIntField(primary_key=True)
    guide_document: fields.ForeignKeyRelation[GuideDocument] = fields.ForeignKeyField(
        "models.GuideDocument",
        related_name="message_settings",
        on_delete=OnDelete.CASCADE,
        source_field="guide_document_id",
    )
    guide_document_id: int

    kind = fields.CharEnumField(enum_type=GuideMessageKind)
    enabled = fields.BooleanField(default=True)

    #: 이 환자에게만 적용할 문구. 비면 기본 문구를 쓴다.
    body = fields.TextField(null=True)

    #: 소진 임박을 며칠 전에 보낼지. `RUN_OUT` 에만 쓴다 — 다른 회차는
    #: 날수가 이름에 박혀 있다(D7 · D15 · D30).
    days_before = fields.SmallIntField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "guide_message_setting"
        unique_together = (("guide_document", "kind"),)


class GuideMessage(models.Model):
    """환자에게 나갈 문자 한 통 — 와이어프레임 D1-6 · S1-14.

    승인이 이 줄들을 만든다. 「승인했는데 왜 안 나갔지」가 생기지 않게
    승인과 예약을 한 동작으로 두는 것과 같은 이유다 (`GuideService.approve`).

    **문구를 여기 담지 않는다.** 보낼 때 그 시점의 템플릿으로 만든다 —
    미리 굳혀 두면 의원이 문구를 고쳐도 예약된 것만 옛 글로 나간다.
    보낸 뒤에는 `sent_body` 에 남긴다: 그때는 이미 나간 글이라 바뀌면 안 된다.
    """

    guide_message_id = fields.BigIntField(primary_key=True)
    guide_document_id: int
    guide_document: fields.ForeignKeyRelation["GuideDocument"] = fields.ForeignKeyField(
        "models.GuideDocument",
        related_name="messages",
        on_delete=OnDelete.CASCADE,
        source_field="guide_document_id",
    )
    kind = fields.CharEnumField(enum_type=GuideMessageKind)
    status = fields.CharEnumField(enum_type=GuideMessageStatus, default=GuideMessageStatus.SCHEDULED)
    scheduled_at = fields.DatetimeField()
    sent_at = fields.DatetimeField(null=True)
    #: 못 나간 이유 — **넷뿐이다**(D1-7). 자유 문자열로 두면 발송기를 붙이는
    #: 사람마다 다른 낱말을 넣고, 화면은 그중 아는 것만 사람 말로 옮긴다.
    #: 화면이 코드를 그대로 보여 주지는 않는다.
    failure_code = fields.CharEnumField(enum_type=GuideMessageFailure, null=True)

    #: 왜 붙들고 있나 — **둘뿐이다**(S2-3). `status` 가 `HELD` 일 때만 찬다.
    #: 실패 사유와 목록이 다르다 — 재는 것이 다르기 때문이다.
    hold_reason = fields.CharEnumField(enum_type=GuideMessageHold, null=True)
    #: 실제로 나간 글. 보내기 전에는 비어 있다.
    sent_body = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "guide_message"
        #: 한 안내문에 같은 회차가 둘이면 환자가 같은 문자를 두 번 받는다.
        unique_together = (("guide_document", "kind"),)
        indexes = (("status", "scheduled_at"),)


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
