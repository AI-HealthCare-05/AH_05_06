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


class PrescriptionSet(models.Model):
    """처방 세트 카탈로그 — KEY-165, KEY-180 §1.

    8종 처방 유형을 사전 등록한다. `Prescription.prescription_set`의 텍스트 스냅샷은
    그대로 유지하고(KEY-137), 이 표는 caution/emergency 매핑의 기준점 역할만 한다.
    세트 밖 대증약물(소화제·감기약 등)은 이 표에 등록하지 않는다(KEY-180 §1).
    """

    prescription_set_id = fields.BigIntField(primary_key=True)
    name = fields.CharField(max_length=100, unique=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    caution_contents: fields.ReverseRelation["DrugCautionContent"]
    check_items: fields.ReverseRelation["PrescriptionCheckItem"]

    class Meta:
        table = "prescription_set"


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
