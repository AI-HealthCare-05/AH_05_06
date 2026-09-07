from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum

from tortoise import fields, models
from tortoise.fields import OnDelete
from tortoise.timezone import now
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.visits import Visit


def confidence_validators() -> list[MinValueValidator | MaxValueValidator]:
    return [MinValueValidator(0), MaxValueValidator(1)]


class OcrJobStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OcrDocumentType(StrEnum):
    EMR = "EMR"
    PRESCRIPTION = "PRESCRIPTION"
    LAB_RESULT = "LAB_RESULT"


class OcrJob(models.Model):
    """A clinic-scoped OCR execution for one visit."""

    ocr_job_id = fields.CharField(max_length=64, primary_key=True)
    hospital_id = fields.BigIntField()
    visit_id: int
    visit: fields.ForeignKeyRelation[Visit] = fields.ForeignKeyField(
        "models.Visit",
        related_name="ocr_jobs",
        on_delete=OnDelete.RESTRICT,
        source_field="visit_id",
    )
    status = fields.CharEnumField(enum_type=OcrJobStatus, default=OcrJobStatus.PROCESSING)
    progress = fields.SmallIntField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    requested_by = fields.BigIntField()
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    failure_code = fields.CharField(max_length=64, null=True)
    excluded_from_guide = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    source_documents: fields.ReverseRelation["OcrJobDocument"]

    class Meta:
        table = "ocr_job"
        indexes = (
            ("hospital_id", "status", "created_at"),
            ("visit", "created_at"),
        )


class OcrResult(models.Model):
    """Versioned OCR output and its review/confirmation audit metadata."""

    ocr_result_id = fields.BigIntField(primary_key=True)
    ocr_job_id: str
    ocr_job: fields.OneToOneRelation[OcrJob] = fields.OneToOneField(
        "models.OcrJob",
        related_name="result",
        on_delete=OnDelete.CASCADE,
    )
    model_name = fields.CharField(max_length=100)
    model_version = fields.CharField(max_length=50, null=True)
    version = fields.IntField(default=1, validators=[MinValueValidator(1)])
    modified_by = fields.BigIntField(null=True)
    modified_at = fields.DatetimeField(null=True)
    confirmed_by = fields.BigIntField(null=True)
    confirmed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    # 역참조 어노테이션은 클래스 마지막에 둔다 — 위에 두면 이후의 `fields.XField(...)`가
    # 이 어노테이션의 `fields` 속성으로 가려져 mypy가 tortoise fields 모듈을 못 찾는다.
    documents: fields.ReverseRelation["OcrDocumentText"]
    fields: fields.ReverseRelation["OcrField"]

    class Meta:
        table = "ocr_result"


class OcrJobDocument(models.Model):
    """An uploaded document queued in one OCR execution."""

    ocr_job_document_id = fields.BigIntField(primary_key=True)
    ocr_job: fields.ForeignKeyRelation[OcrJob] = fields.ForeignKeyField(
        "models.OcrJob",
        related_name="source_documents",
        on_delete=OnDelete.CASCADE,
    )
    document_id = fields.BigIntField()
    document_type = fields.CharEnumField(enum_type=OcrDocumentType)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ocr_job_document"
        unique_together = (("ocr_job", "document_id"),)
        indexes = (("document_id",),)


class OcrDocumentText(models.Model):
    """Temporary OCR text; it must be purged with the approved source document."""

    ocr_document_text_id = fields.BigIntField(primary_key=True)
    ocr_result: fields.ForeignKeyRelation[OcrResult] = fields.ForeignKeyField(
        "models.OcrResult",
        related_name="documents",
        on_delete=OnDelete.CASCADE,
    )
    document_id = fields.BigIntField()
    document_type = fields.CharEnumField(enum_type=OcrDocumentType)
    raw_text: str | None = fields.TextField(null=True)
    raw_text_purged_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ocr_document_text"
        unique_together = (("ocr_result", "document_id"),)

    def purge_raw_text(self, *, purged_at: datetime | None = None) -> None:
        self.raw_text = None
        self.raw_text_purged_at = purged_at or now()


class OcrField(models.Model):
    """A structured value with OCR, correction, and confirmation provenance."""

    ocr_field_id = fields.BigIntField(primary_key=True)
    ocr_result: fields.ForeignKeyRelation[OcrResult] = fields.ForeignKeyField(
        "models.OcrResult",
        related_name="fields",
        on_delete=OnDelete.CASCADE,
    )
    document_text_id: int | None
    document_text: fields.ForeignKeyNullableRelation[OcrDocumentText] = fields.ForeignKeyField(
        "models.OcrDocumentText",
        related_name="fields",
        on_delete=OnDelete.SET_NULL,
        source_field="ocr_document_text_id",
        null=True,
    )
    field_type = fields.CharField(max_length=64)
    unit = fields.CharField(max_length=32, null=True)
    extracted_value = fields.TextField(null=True)
    corrected_value: str | None = fields.TextField(null=True)
    source_line = fields.IntField(null=True)
    is_pending_report = fields.BooleanField(default=False)
    confidence = fields.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        validators=confidence_validators(),
    )
    version = fields.IntField(default=1, validators=[MinValueValidator(1)])
    is_confirmed = fields.BooleanField(default=False)
    modified_by = fields.BigIntField(null=True)
    modified_at = fields.DatetimeField(null=True)
    # **비울 수 있다고 적어 둔다.** 칼럼은 처음부터 nullable 인데 형만 안 적혀
    # 있어서, 값이 바뀔 때 확정 도장을 떼는 자리(`_drop_confirmation`)가 mypy 에
    # 걸렸다. 뗄 수 있다는 것이 이 두 칸의 성질이다 (KEY-273).
    confirmed_by: int | None = fields.BigIntField(null=True)  # type: ignore[assignment]
    confirmed_at: datetime | None = fields.DatetimeField(null=True)  # type: ignore[assignment]
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ocr_field"
        unique_together = (("ocr_result", "field_type"),)

    @property
    def value(self) -> str | None:
        return self.corrected_value if self.corrected_value is not None else self.extracted_value

    # 역참조 어노테이션은 클래스 마지막에 둔다 — 위에 두면 이후의 `fields.XField(...)`가
    # 이 어노테이션의 `fields` 속성으로 가려져 mypy가 tortoise fields 모듈을 못 찾는다.
    candidates: fields.ReverseRelation["OcrFieldCandidate"]


class DurationUnit(StrEnum):
    """`DURATION_DAYS` 칸의 숫자가 무엇인가 — 「3」이 3일인지 3통인지.

    **소진 예정일과 확인 문자 시각이 이 값으로 셈해진다.** 틀리면 문자가
    엉뚱한 날 나간다.

    **세트에 붙이지 않는다.** 카탈로그에 같은 뜻의 칸이 있지만
    (`PrescriptionSet.days_mode` — 「의원마다 다르다」) 합성 100행에서 네 세트가
    **전부** 두 단위로 다 나온다. `자궁내막증 · 비잔 (계속)` 만 해도 일수 23 ·
    통수 11 이다. 단위는 세트의 성질이 아니라 **그 진료의 그 줄**의 성질이다.

    값이 화면에 그대로 나간다 — `frontend/js/field-labels.js` 의 `fieldUnit` 이
    서버가 준 단위를 무조건 우선한다. 숫자 뒤에 붙는 접미사이므로 「일수」가
    아니라 「일」이다.
    """

    DAYS = "일"
    PACK = "통"


#: 한 통이 며칠치인가. `docs/synthetic-data-spec.md` 의 불변식 —
#: 「`총투원문 × 단위 = 처방일수` — 통수면 `× 28`」. `app/tests/fixtures/mapping.py`
#: 도 같은 말을 적어 두었다.
DAYS_PER_PACK = 28


def course_days(value: str | None, unit: str | None) -> int | None:
    """판독이 읽은 숫자를 **일수**로.

    EMR 「총투」 칸의 「3」이 3통이면 84일이고 3일로 읽으면 3일이다. 그 차이가
    소진 예정일 81일을 만든다.

    **모르면 곱하지 않는다.** `unit` 이 빈 행은 여태 다 그렇게 살았고(이 칸에
    값을 쓰는 코드가 없었다), 지어낸 값으로 발송일을 잡는 것보다 하던 대로가
    낫다 — `_course_days` 가 「지어낸 값으로 예약하는 것보다 안 만드는 편이
    낫다」고 적어 둔 것과 같은 태도다.
    """
    if value is None:
        return None

    text = str(value).strip()
    try:
        read = int(text)
    except ValueError:
        #: **숫자만 뽑는 것은 마지막 수단이다** — 이희진 님 `#236` ③.
        #:
        #: 판독 원문에 단위 글자가 붙어 올 수 있어서(`"56일"`) 뽑아 쓰는 길을
        #: 남긴다. 그런데 곧장 뽑으면 **값의 뜻을 바꾸는 글자까지 지운다** —
        #: `"-5"` 가 `5`(통수면 140)로, `"1.5"` 가 `15` 로 조용히 통과했다.
        #: 옛 `_course_days` 는 `int()` 를 먼저 해서 부호를 지켰는데, 그 순서를
        #: 잃은 것이 이 회귀다.
        #:
        #: 부호나 소수점이 보이면 읽지 않는다. 소진 예정일을 지어내는 것보다
        #: 안 만드는 편이 낫다 — 위 독스트링이 정한 태도 그대로다.
        if any(mark in text for mark in ("-", "−", ".", ",")):
            return None
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return None
        read = int(digits)

    if read <= 0:
        return None
    return read * DAYS_PER_PACK if unit == DurationUnit.PACK else read


def read_but_unconfirmed(fields: "Iterable[OcrField]") -> "OcrField | None":
    """**값이 있는데 아무도 안 본 줄** — 확정 게이트가 막아야 하는 것.

    두 곳이 이 판정을 한다. `finalize_ocr` 이 처방 행을 세우기 전에, `generate`
    가 안내문을 만들기 전에. **둘이 어긋나면 처방은 섰는데 안내문은 없는 진료가
    생긴다** — 화면 사슬이 `확정 → finalize → generate` 라서 가운데만 통과한다.
    그래서 규칙을 한 벌로 둔다.

    빈 칸은 세지 않는다. 화면이 값 있는 항목만 확정하기 때문이다
    (`ocr-review.js` 의 `fieldsToConfirm`) — 빈 칸을 확정하면 그 빈 값이 안내문에
    그대로 나간다. 못 읽은 칸까지 요구하면 그 진료는 안내문을 영영 못 만들고,
    푸는 길도 없다(「이번 미시행」은 담을 칸이 서버에 없어 그려지지 않는다).
    와이어프레임 S1-7 이 「못 읽은 값 없이 생성」이라 적은 자리다.
    """
    return next((field for field in fields if field.value and not field.is_confirmed), None)


class OcrFieldCandidate(models.Model):
    """A ranked alternative retained when one field has multiple readings."""

    ocr_field_candidate_id = fields.BigIntField(primary_key=True)
    ocr_field: fields.ForeignKeyRelation[OcrField] = fields.ForeignKeyField(
        "models.OcrField",
        related_name="candidates",
        on_delete=OnDelete.CASCADE,
    )
    document_text_id: int | None
    document_text: fields.ForeignKeyNullableRelation[OcrDocumentText] = fields.ForeignKeyField(
        "models.OcrDocumentText",
        related_name="candidate_fields",
        on_delete=OnDelete.SET_NULL,
        source_field="ocr_document_text_id",
        null=True,
    )
    candidate_value = fields.TextField()
    confidence = fields.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        validators=confidence_validators(),
    )
    rank = fields.SmallIntField(validators=[MinValueValidator(1)])
    source_date = fields.DateField(null=True)
    source_line = fields.IntField(null=True)
    is_selected = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ocr_field_candidate"
        unique_together = (("ocr_field", "rank"),)
