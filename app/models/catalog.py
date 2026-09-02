"""처방 세트·주의·응급 문구 마스터 카탈로그 — KEY-165.

`PrescriptionSet`은 안내 생성 시 참조하는 8종 처방 유형의 사전 등록표다.
기존 `Prescription.prescription_set`은 진료 당시 이름의 스냅샷 문자열로 그대로 유지하고
(KEY-137 결정), 이 표는 caution/emergency 매핑 기준점 역할만 한다(KEY-180 §1).

`DrugCautionContent`는 세트별 주의·응급 문구와 근거 메타데이터를 저장한다.
승인된 버전만 안내 생성에 사용되고, 새 버전 승인 시 이전 버전은 같은 트랜잭션에서
DEPRECATED로 바뀐다.

**같은 세트·섹션에 승인 버전이 둘이 되는 경합 방지(KEY-180 §3)**

MySQL 8.0은 조건부 유니크 인덱스를 지원하지 않아 `unique_together`로
"승인 상태일 때만 하나"를 표현할 수 없다. 대신 `approved_key`(nullable) 칼럼에
승인 상태일 때만 `"{prescription_set_id}:{section_key}"` 값을 채우고, 이 칼럼에
유니크 인덱스를 건다. NULL은 유니크 인덱스에서 여럿 허용되므로 비승인 행은 제약에
걸리지 않는다.
"""

from enum import StrEnum

from tortoise import fields, models
from tortoise.fields import OnDelete

from app.models.visits import VisitCheckKey


class SourceGrade(StrEnum):
    """근거 자료 등급 — Notion '의학지식 출처 관리' DB 기준(KEY-180 §2).

    A 등급 자료만 caution/emergency 단독 근거로 사용할 수 있다.
    B 등급은 표현 다듬기 보조 자료로만 허용하고 단독 근거로 쓰지 않는다.
    C 등급은 이번 범위에서 사용하지 않는다.
    """

    A = "A"
    B = "B"
    C = "C"


class ApprovalStatus(StrEnum):
    """문구 승인 상태(KEY-180 §3).

    DRAFT      작성 완료, 검수 전
    APPROVED   의료 안전 검수 책임자 승인 완료 — 안내 생성에 사용 가능
    DEPRECATED 새 버전 승인으로 폐기됨 — 안내 생성에 사용 불가
    """

    DRAFT = "draft"
    APPROVED = "approved"
    DEPRECATED = "deprecated"


class CautionSectionKey(StrEnum):
    """caution·emergency 두 갈래만 마스터 콘텐츠 대상이다.

    나머지 섹션(medication·life·messages)은 약물별 근거가 필요 없어
    DrugCautionContent 매핑 대상이 아니다.
    """

    CAUTION = "caution"
    EMERGENCY = "emergency"


class SetDisease(StrEnum):
    """이 처방이 어느 병에 쓰이나 — 와이어프레임 D2-3 「질환」.

    이 의원이 보는 둘이다. 판독 확인 화면의 진단 고르개와 같은 어휘를 쓴다 —
    갈리면 「가장 유사한 처방 세트」를 찾을 때 못 맞춘다.
    """

    ENDOMETRIOSIS = "ENDOMETRIOSIS"
    PCOS = "PCOS"


class SetPhase(StrEnum):
    """언제 쓰는 처방인가 — 와이어프레임 D2-3 「적용 시점」.

    같은 약이라도 처음 내는 것과 계속 내는 것은 안내가 다르다. 「비잔 (처음)」과
    「비잔 (계속)」이 따로 있는 이유다.
    """

    FIRST = "FIRST"
    CONTINUE = "CONTINUE"
    REST = "REST"


class SetDaysMode(StrEnum):
    """EMR 「총투」 칸이 무엇을 뜻하나 — 와이어프레임 D2-3 ★.

    의원마다 다르다. 「3」이 3통일 수도 3일일 수도 있는데, **소진 예정일과 발송
    시각이 이 값으로 셈해진다** — 틀리면 문자가 엉뚱한 날 간다.
    """

    #: 통·상자 수. `days_per_pack` 을 곱해 일수를 얻는다.
    PACK = "PACK"
    #: 적힌 숫자가 곧 일수다.
    DAYS = "DAYS"


class PrescriptionSet(models.Model):
    """처방 세트 카탈로그 — KEY-165, KEY-180 §1.

    8종 처방 유형을 사전 등록한다. `Prescription.prescription_set`의 텍스트 스냅샷은
    그대로 유지하고(KEY-137), 이 표는 caution/emergency 매핑의 기준점 역할만 한다.
    세트 밖 대증약물(소화제·감기약 등)은 이 표에 등록하지 않는다(KEY-180 §1).
    """

    prescription_set_id = fields.BigIntField(primary_key=True)
    name = fields.CharField(max_length=100, unique=True)

    #: ── 설정 화면(D2-3)이 정하는 것들 ────────────────────────────────
    disease: SetDisease = fields.CharEnumField(enum_type=SetDisease, default=SetDisease.ENDOMETRIOSIS)
    phase = fields.CharEnumField(enum_type=SetPhase, default=SetPhase.CONTINUE)

    #: EMR 「총투」 칸의 의미. **소진 예정일이 이 값으로 셈해진다.**
    days_mode = fields.CharEnumField(enum_type=SetDaysMode, default=SetDaysMode.DAYS)
    #: 한 통이 며칠치인가. `days_mode` 가 `PACK` 일 때만 쓴다.
    days_per_pack: int | None = fields.SmallIntField(null=True)

    #: 이 코드가 적힌 진료를 안내 대상으로 본다. 의원이 쓰는 코드를 그대로 적는다.
    emr_code: str | None = fields.CharField(max_length=100, null=True)  # type: ignore[assignment]
    #: 「3개월 복용 후 내원」처럼 한 줄. 소견에 다른 조건이 있으면 그쪽이 이긴다.
    revisit_note: str | None = fields.CharField(max_length=200, null=True)  # type: ignore[assignment]

    #: ── 자동 발송 기본값 ────────────────────────────────────────────
    #: 「필요하면 켜세요」로 두면 아무도 안 켠다(D2-3 주석). 처방마다 여기서 정해
    #: 두고, 환자별로 바꾸는 것은 S1-14 다.
    #: 일주일 뒤는 칸이 없다 — 어느 처방에서도 못 끄기 때문이다.
    check_d15_on = fields.BooleanField(default=True)
    check_d30_on = fields.BooleanField(default=False)
    run_out_on = fields.BooleanField(default=True)
    run_out_before_days = fields.SmallIntField(default=3)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    caution_contents: fields.ReverseRelation["DrugCautionContent"]
    check_items: fields.ReverseRelation["PrescriptionCheckItem"]
    drugs: fields.ReverseRelation["PrescriptionSetDrug"]

    class Meta:
        table = "prescription_set"


class PrescriptionSetDrug(models.Model):
    """처방 세트에 든 약 — 와이어프레임 D2-3 「처방 약」.

    **진료의 처방(`PrescriptionItem`)과 다른 층이다.** 저쪽은 「이 환자에게 이날
    무엇을 냈나」이고, 이쪽은 「이 세트를 고르면 무엇을 내는가」다. 세트를 고쳐도
    지난 진료의 처방은 안 바뀐다.

    약이 여럿일 수 있다 — 「야즈 + 메트포르민」이 그렇다. `position` 이 화면
    차례이고, 안내문에 적히는 차례이기도 하다.
    """

    prescription_set_drug_id = fields.BigIntField(primary_key=True)
    prescription_set_id: int
    prescription_set: fields.ForeignKeyRelation[PrescriptionSet] = fields.ForeignKeyField(
        "models.PrescriptionSet",
        related_name="drugs",
        on_delete=OnDelete.CASCADE,
        source_field="prescription_set_id",
    )

    #: 「비잔정 2mg」처럼 용량까지. 안내문에 그대로 나간다.
    name = fields.CharField(max_length=100)
    #: 「1일 1회」
    frequency = fields.CharField(max_length=50, null=True)
    #: 「매일 같은 시간」처럼 먹는 방법 한 줄
    note = fields.CharField(max_length=200, null=True)
    position = fields.SmallIntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "prescription_set_drug"


class PrescriptionCheckItem(models.Model):
    """처방 세트가 여쭙는 확인 항목 — 와이어프레임 S1-6 「확인 항목 · 처방별」.

    **무엇을 여쭐지는 처방이 정한다.** 비잔이면 우울증 병력을 묻고, 야즈면
    고혈압을 묻는다 — 약마다 조심할 것이 다르기 때문이다. 전에는 다섯을 모든
    진료에 똑같이 세웠는데, 그러면 안 물어도 될 것을 묻게 되고 물어야 할 것이
    빠져도 아무도 모른다.

    답은 진료에 붙는다(`VisitCheckAnswer`). 이 표는 **질문지**이고 저 표는
    **답안지**다 — 질문이 바뀌어도 지난 답은 그대로 남는다.

    `position` 은 화면 차례다. 이름순으로 세우면 「임신 계획」이 맨 앞에 오는
    식으로 물어보는 순서가 뒤집힌다.
    """

    prescription_check_item_id = fields.BigIntField(primary_key=True)
    prescription_set_id: int
    prescription_set: fields.ForeignKeyRelation[PrescriptionSet] = fields.ForeignKeyField(
        "models.PrescriptionSet",
        related_name="check_items",
        on_delete=OnDelete.CASCADE,
        source_field="prescription_set_id",
    )
    item_key = fields.CharEnumField(enum_type=VisitCheckKey)
    position = fields.SmallIntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "prescription_check_item"
        unique_together = (("prescription_set", "item_key"),)


class DrugCautionContent(models.Model):
    """처방 세트별 주의·응급 문구 마스터 — KEY-165.

    **한 세트·섹션에 승인 버전은 항상 하나뿐이다.** `approved_key`(nullable unique)로 DB가 보장한다.
    새 버전 승인 시 `approved_key = f"{prescription_set_id}:{section_key}"`를 채우고,
    이전 버전의 `approved_key`를 NULL로 비운다 — 같은 트랜잭션에서 처리한다.

    새 버전이 승인돼도 이미 생성된 안내문(`GuideSection.generated_body`)은 바뀌지 않는다.
    어느 버전이 사용됐는지는 `GuideSection.drug_caution_content_id`로 추적한다(KEY-180 §6).
    """

    drug_caution_content_id = fields.BigIntField(primary_key=True)
    prescription_set_id: int
    prescription_set: fields.ForeignKeyRelation[PrescriptionSet] = fields.ForeignKeyField(
        "models.PrescriptionSet",
        related_name="caution_contents",
        on_delete=OnDelete.RESTRICT,
        source_field="prescription_set_id",
    )
    section_key = fields.CharEnumField(enum_type=CautionSectionKey)
    body = fields.TextField()

    # 근거 메타데이터 — Notion '의학지식 출처 관리' DB 항목(KEY-180 §3)
    source_name = fields.CharField(max_length=200)
    source_org = fields.CharField(max_length=100)
    source_url = fields.CharField(max_length=500)
    verified_at = fields.DateField()
    content_version = fields.CharField(max_length=50)
    source_grade = fields.CharEnumField(enum_type=SourceGrade)

    approval_status = fields.CharEnumField(enum_type=ApprovalStatus, default=ApprovalStatus.DRAFT)
    # KEY-180 §3: 승인 상태일 때만 "{prescription_set_id}:{section_key}"를 채운다.
    # NULL은 유니크 인덱스에서 여럿 허용 → "승인은 세트·섹션당 하나"를 DB가 보장.
    approved_key = fields.CharField(max_length=30, null=True, unique=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "drug_caution_content"
        indexes = (("prescription_set", "section_key", "approval_status"),)


class MessageTemplateKind(StrEnum):
    """의원이 고칠 수 있는 문자 — 와이어프레임 D2-5.

    **인증번호는 여기 없다.** 원문이 「수정 불가 · 시스템」으로 못박는다 —
    문구를 잘못 고치면 환자가 인증을 못 하고, 그건 의원이 감당할 일이 아니다.
    고칠 수 없는 것에 칸을 만들지 않는다.

    `REVISIT` 은 `GuideMessageKind` 에 없다. 저쪽은 **승인이 세워 두는 회차**
    이고, 재진 안내는 스탭이 그때그때 보내는 것이다(S1-14) — 예약 줄이 생기지
    않으므로 회차가 아니다.
    """

    GUIDE = "GUIDE"
    CHECK_D7 = "CHECK_D7"
    CHECK_D15 = "CHECK_D15"
    CHECK_D30 = "CHECK_D30"
    RUN_OUT = "RUN_OUT"
    REVISIT = "REVISIT"


class MessageTemplate(models.Model):
    """의원이 고친 문자 본문 — 와이어프레임 D2-5.

    **줄이 없으면 기본 문구다.** 한 번도 안 고친 의원까지 여섯 줄을 미리 깔지
    않는다 — 안 고쳤다는 것과 기본값으로 정했다는 것이 여기서는 같은 뜻이라,
    굳이 갈라 적을 이유가 없다 (`GuideMessageSetting` 과 같은 판단이다).

    그래서 「원본으로 되돌리기」가 **줄을 지우는 일**이 된다. 기본 문구를 다시
    베껴 넣지 않는 이유는, 그러면 나중에 기본 문구를 고쳐도 되돌린 의원은 옛
    글을 계속 쓰게 되기 때문이다.

    **안내문과 층이 다르다.** 환자 카드의 안내문 탭은 링크로 열리는 안내문
    (콘텐츠)을 다루고, 이 표는 그 링크를 실어 나르는 **문자 본문**을 다룬다.
    """

    message_template_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    kind = fields.CharEnumField(enum_type=MessageTemplateKind)
    body = fields.TextField()
    #: 누가 고쳤나. 원문 「바뀐 문구는 다음 발송부터 적용되고 로그에 남는다」.
    updated_by = fields.BigIntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "message_template"
        #: 한 의원에 같은 회차가 둘이면 어느 것으로 보낼지 알 수 없다.
        unique_together = (("hospital_id", "kind"),)


class BaselineDirection(StrEnum):
    """이 값을 **어느 쪽으로** 끌고 가나 — 와이어프레임 D2-4 「방향」.

    D1 「나의 목표」가 남은 거리를 셈할 때 이 값이 부호를 정한다. 「참고」는
    목표가 없다는 뜻이다 — LH/FSH 비율처럼 보기는 하되 올리고 내릴 값이
    아닌 것들이 있다.
    """

    KEEP = "KEEP"
    LOWER = "LOWER"
    REFERENCE = "REFERENCE"


class LabBaseline(models.Model):
    """검사 항목 하나의 기준선 — 와이어프레임 D2-4.

    **기준선을 비워 둘 수 있다.** 원문: 「비워 두면 값과 추이만 표시하고 목표
    대비 수치는 계산하지 않습니다」. 검사기관과 나이에 따라 다르기 때문이고,
    모르는 채로 셈해 「목표까지 3 남았습니다」라고 말하는 것이 제일 나쁘다.

    **`keywords` 가 이 표의 다른 절반이다.** EMR 마다 표기가 다르다
    (DHEA-S / DHEAS / 황체호르몬). 판독이 진료기록에서 그 항목을 찾으려면
    의원이 쓰는 표기를 알아야 한다.

    `doctor_id` 가 비면 **의원 공통**이다. 원문의 「누구 기준」 드롭다운이
    그것이고, 의사가 둘 이상일 때만 화면에 뜬다.
    """

    lab_baseline_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    #: 비면 의원 공통. 차면 그 의사 담당 환자에게만 쓴다.
    doctor_id = fields.BigIntField(null=True)
    disease = fields.CharEnumField(enum_type=SetDisease)

    #: 화면에 뜨는 이름 — 「총 테스토스테론」·「간수치 AST/ALT」.
    name = fields.CharField(max_length=100)
    direction = fields.CharEnumField(enum_type=BaselineDirection, default=BaselineDirection.KEEP)

    #: 기준선. **둘 다 비면 목표를 셈하지 않는다.**
    #:   21~35    → low 21 · high 35
    #:   12.0 이상 → low 12.0
    #:   40 미만   → high 40
    low = fields.DecimalField(max_digits=8, decimal_places=2, null=True)
    high = fields.DecimalField(max_digits=8, decimal_places=2, null=True)
    #: 나이별 기준 — 숫자 하나로 못 적는 것들(AMH). 켜면 low·high 를 안 쓴다.
    by_age = fields.BooleanField(default=False)

    #: 판독이 진료기록에서 찾을 표기들. 쉼표로 잇는다.
    keywords = fields.CharField(max_length=200, default="")
    #: 「일」·「ng/dL」·「비율」. BMI 처럼 단위가 없는 것도 있다.
    unit = fields.CharField(max_length=20, default="")

    #: 판독 결과 확인 화면에 늘 보일 것인가. 끄면 「＋ 항목 추가」에서 고른다.
    always_shown = fields.BooleanField(default=True)
    position = fields.SmallIntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "lab_baseline"
        #: 같은 항목이 둘이면 어느 기준으로 셈할지 알 수 없다.
        unique_together = (("hospital_id", "doctor_id", "disease", "name"),)


class DoctorGuideCopy(models.Model):
    """원장님 문구 — 와이어프레임 D2-2 「안내문 고치기 — 원본 ↔ 원장님 문구」.

    원문 주석: 「의사마다 말하는 방식이 다르고 같은 의사도 일정하지 않다.
    문구를 하나로 강제하면 원장님이 안 쓰신다. 대신 **원본을 위에 두어 무엇이
    사실이고 무엇이 표현인지 보이게 한다.** 원본은 지워지지 않으므로 언제든
    되돌아간다.」

    **원본을 덮어쓰지 않는다.** `DrugCautionContent` 는 근거와 승인이 붙은
    자료라 손대면 안 되고, 이 표는 그 위에 덧씌우는 표현일 뿐이다. 줄을 지우면
    원본으로 돌아간다 — 되돌리기가 그것이다.

    **의사마다 따로다.** 원문: 「이 문구는 박연 원장 담당 환자에게만
    발송됩니다」. 그래서 `doctor_id` 가 비지 않는다.

    **🚨 응급 문구는 여기 들어오지 않는다.** 원문: 「🚨 문구는 이 화면이 열리지
    않는다」. 표현을 다듬는 자리이지 안전 문장을 고치는 자리가 아니다.
    """

    doctor_guide_copy_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    #: 비지 않는다 — 의원 공통 문구라는 것은 곧 원본이다.
    doctor_id = fields.BigIntField()
    prescription_set_id: int
    prescription_set: fields.ForeignKeyRelation[PrescriptionSet] = fields.ForeignKeyField(
        "models.PrescriptionSet",
        related_name="doctor_copies",
        on_delete=OnDelete.CASCADE,
        source_field="prescription_set_id",
    )
    section_key = fields.CharEnumField(enum_type=CautionSectionKey)
    body = fields.TextField()

    updated_by = fields.BigIntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "doctor_guide_copy"
        unique_together = (("hospital_id", "doctor_id", "prescription_set", "section_key"),)


class DoctorGuideReview(models.Model):
    """「확인 완료」 — 와이어프레임 D2-1 아래 단추.

    원문 주석: 「조각을 하나씩 승인하게 하면 확인할 것이 54개가 되지만 **약
    단위로 묶으면 5장이면 끝난다**」. 그래서 확인은 구역이 아니라 한 장 단위다
    (우리 자료에서 그 한 장은 처방 세트다).

    **줄이 있으면 확인했다는 뜻이다.** 확인 뒤에 문구를 고치면 그 줄을 지운다 —
    고친 글은 다시 봐야 하고, 「확인 완료」가 붙은 채로 바뀐 글이 나가면 그
    표시가 거짓말이 된다.
    """

    doctor_guide_review_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    doctor_id = fields.BigIntField()
    prescription_set_id: int
    prescription_set: fields.ForeignKeyRelation[PrescriptionSet] = fields.ForeignKeyField(
        "models.PrescriptionSet",
        related_name="doctor_reviews",
        on_delete=OnDelete.CASCADE,
        source_field="prescription_set_id",
    )
    reviewed_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "doctor_guide_review"
        unique_together = (("hospital_id", "doctor_id", "prescription_set"),)
