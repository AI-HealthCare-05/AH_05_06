"""합성 CSV 한 행 → 판독 필드들 — KEY-271 P1.

`scripts/seed.py` 가 이것을 쓴다. 규칙을 시드 안에 두지 않는 까닭은
`prescriptions.py` 와 같다 — **검사가 닿아야 하기 때문**이다. 시드 함수 안에
두면 DB 를 띄우고 스크립트를 통째로 돌려야만 확인할 수 있고, 그러면 아무도
확인하지 않는다.

## 왜 시드에 판독이 필요한가

시드는 `Prescription` 을 CSV 에서 **곧장** 만든다(`_seed_prescription`). 판독을
거치지 않는다. 그래서 지금까지 시드가 만든 진료 99건에는 `ocr_job` 이 하나도
없었고, 판독 확인 화면(S1-5~S1-9)이 볼 것이 없었다. 시연·QA 데이터가 그것이다.

## 셋으로 가른다 — 전부 확정으로 심으면 확인 화면이 죽는다

`진료상태` 가 그 축이다. 전부 확정으로 심으면 확인 화면에 「확인할 항목 0개」가
뜨고, 다시 확정하면 409 `OCR_FIELD_CONFIRMED` 라 S1-6·S1-7 을 볼 수 없다.

    판독 없음    진료기록 없음                 ocr_job 자체를 안 만든다
    미확정      스탭 확인 중                  값은 있고 아무도 확정하지 않았다
    확정        나머지 여섯 상태               사람이 확인해 안내문까지 간 것

**파이프라인 뜻을 따른다.** 「승인 대기」·「보완」은 안내문이 이미 있다는 뜻이고,
안내문은 확정 없이 못 만든다. 그래서 미확정으로 심지 않는다 — 화면에 표본을 더
두려고 상태의 뜻을 비틀면, 이 데이터를 믿고 짠 다음 사람이 틀린다.

## 판독이 읽은 것만 넣는다

CSV 칸 중 **담을 `field_type` 이 있는 것만** 필드로 만든다. 없는 이름을 지어
넣으면 그 이름이 진짜인 줄 아는 사람이 생긴다(AGENTS.md). 무엇을 버렸는지는
`UNMAPPED_LAB_LABELS` 가 들고 있고 검사가 그것을 잰다.

**못 읽은 칸을 지어내지 않는다.** CSV 에 「판독이 못 읽었다」를 적는 칸이 없다.
빈 칸은 「그 검사를 안 했다」는 뜻이라(`mapping.py` 의 `PENDING` 주석) 아예 줄을
안 만든다. S1-7 의 「못 읽음」 표본은 실제 업로드로 만들어야 한다.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.models.ocr import DurationUnit, course_days
from app.tests.fixtures.mapping import PENDING
from app.tests.fixtures.prescriptions import SEPARATOR

#: CSV `총투단위` → `OcrField.unit`. 「3」이 3통인지 3일인지를 **읽은 자리에** 남긴다.
UNIT_FOR = {"일수": DurationUnit.DAYS, "통수": DurationUnit.PACK}


class ReadStage(StrEnum):
    """이 진료의 판독이 어디까지 왔는가."""

    NONE = "판독 없음"
    UNCONFIRMED = "미확정"
    CONFIRMED = "확정"


#: `진료상태` → 판독 단계. **모르는 값은 막는다** — 조용히 확정으로 떨어지면
#: 상태가 하나 늘 때마다 미확정 표본이 소리 없이 사라진다.
_STAGE_BY_VISIT_STATE = {
    "진료기록 없음": ReadStage.NONE,
    "스탭 확인 중": ReadStage.UNCONFIRMED,
    "생성 중": ReadStage.CONFIRMED,
    "승인 대기": ReadStage.CONFIRMED,
    "발송 예정": ReadStage.CONFIRMED,
    "발송 완료": ReadStage.CONFIRMED,
    "보완": ReadStage.CONFIRMED,
    "계획된 중단": ReadStage.CONFIRMED,
}


class OcrRowError(ValueError):
    """CSV 한 행을 판독으로 옮길 수 없다."""


#: 검사 칸 → `field_type`. 이름은 추출기가 쓰는 것을 그대로 따른다
#: (`ai_worker/tasks/field_extractor.py` 의 `_LAB_TEST_NAME_KEYWORDS`).
#: 여기 없는 이름을 지어내면 화면이 그 줄을 못 그린다.
LAB_FIELD_FOR = {
    "혈색소": "HEMOGLOBIN",
    "자궁내막종": "ENDOMETRIOMA_SIZE",
    "내막두께": "ENDOMETRIAL_THICKNESS",
    "ASTALT": "AST_ALT",
    "총테스토스테론": "TESTOSTERONE",
    "DHEAS": "DHEA_S",
    "LH_FSH": "LH_FSH_RATIO",
    "AMH": "AMH",
}

#: **일부러 안 옮기는 칸.** 값이 있는데도 버린다 — 담을 `field_type` 이 없다.
#:
#: `월경주기` 는 「규칙적 (28~31일)」 같은 자유 문장인데 추출기의
#: `IRREGULAR_CYCLE` 는 「있다/없다」만 받는다. 문장을 둘 중 하나로 접으면
#: **판독이 안 한 판단을 시드가 하는 것**이 된다.
#:
#: `기타검사` 는 「CA-125 48 U/mL · HbA1c 5.7% · BMI 27.3」처럼 여럿이 섞여
#: 있고, HbA1c·BMI 는 `field_type` 이 아예 없다.
UNMAPPED_LAB_LABELS = ("월경주기", "기타검사")


@dataclass(frozen=True)
class FieldRow:
    """판독 필드 한 줄."""

    field_type: str
    value: str
    confidence: Decimal
    unit: str | None = None
    is_pending_report: bool = False


@dataclass(frozen=True)
class ReadRow:
    """CSV 한 행이 만들 판독 한 벌."""

    stage: ReadStage
    fields: tuple[FieldRow, ...] = ()
    dropped: tuple[str, ...] = field(default=(), repr=False)


def stage_for(visit_state: str) -> ReadStage:
    """`진료상태` 를 판독 단계로 옮긴다."""
    key = visit_state.strip()
    if not key:
        return ReadStage.NONE
    if key not in _STAGE_BY_VISIT_STATE:
        raise OcrRowError(
            f"모르는 진료상태 {key!r} — 판독을 어디까지 심을지 정할 수 없다. _STAGE_BY_VISIT_STATE 에 더해 주세요"
        )
    return _STAGE_BY_VISIT_STATE[key]


def duration_row(total_raw: str, unit_label: str, days_column: str) -> FieldRow | None:
    """`총투원문` 과 `총투단위` 로 처방일수 한 줄을 만든다.

    **판독은 원문 숫자를 읽는다.** `1/1/3` 의 `3` 이 그것이다. 그것이 3통인지
    3일인지는 숫자에 안 적혀 있어서 `unit` 에 남긴다 — 그 칸이 있는 까닭이다.

    `처방일수` 칸은 **답안지**다. 환산이 그 값과 어긋나면 여기서 멈춘다. 시드가
    조용히 틀린 날짜를 심으면 소진 문자가 엉뚱한 날 예약된다.
    """
    raw = total_raw.strip()
    label = unit_label.strip()
    if not raw or not label:
        return None
    if label not in UNIT_FOR:
        raise OcrRowError(f"모르는 총투단위 {label!r} — 아는 것은 {sorted(UNIT_FOR)} 다")

    parts = [p.strip() for p in raw.split("/")]
    if len(parts) != 3 or not parts[2].isdigit():
        raise OcrRowError(f"총투원문 {raw!r} 이 `1회량/일투/총투` 모양이 아니다")

    unit = UNIT_FOR[label]
    read = int(parts[2])
    days = course_days(str(read), unit)

    wanted = days_column.strip()
    if wanted.isdigit() and int(wanted) != days:
        raise OcrRowError(
            f"총투 {read}{unit} 을 {days}일로 셌는데 CSV 처방일수는 {wanted}일이다 — 환산 규칙과 데이터가 어긋난다"
        )

    return FieldRow(field_type="DURATION_DAYS", value=str(read), confidence=Decimal("0.96"), unit=unit)


def _lab_rows(row: dict[str, str]) -> tuple[list[FieldRow], list[str]]:
    made: list[FieldRow] = []
    for label, field_type in LAB_FIELD_FOR.items():
        text = row.get(label, "").strip()
        if not text:
            # 빈 칸은 「그 방문에 그 검사를 안 했다」는 뜻이다 — 줄을 안 만든다.
            continue
        if text == PENDING:
            # **「값이 없다」와 「아직 안 나왔다」는 다르다.** 앞은 못 읽은 것이고
            # 뒤는 결과가 늦는 것이다 — 화면이 그 줄만 점선 + ? 로 그린다.
            made.append(FieldRow(field_type=field_type, value=text, confidence=Decimal("0.96"), is_pending_report=True))
            continue
        made.append(FieldRow(field_type=field_type, value=text, confidence=Decimal("0.94")))
    dropped = [label for label in UNMAPPED_LAB_LABELS if row.get(label, "").strip()]
    return made, dropped


def read_from_row(row: dict[str, str]) -> ReadRow:
    """CSV 한 행 → 그 진료에 심을 판독 한 벌.

    `stage` 가 `NONE` 이면 필드도 없다 — 판독 작업 자체를 안 만든다는 뜻이다.
    """
    stage = stage_for(row.get("진료상태", ""))
    if stage is ReadStage.NONE:
        return ReadRow(stage=stage)

    rows: list[FieldRow] = []

    diagnosis = row.get("진단", "").strip()
    if diagnosis:
        rows.append(FieldRow(field_type="DIAGNOSIS", value=diagnosis, confidence=Decimal("0.92")))

    prescription_set = row.get("처방세트", "").strip()
    if prescription_set:
        rows.append(FieldRow(field_type="PRESCRIPTION_SET", value=prescription_set, confidence=Decimal("0.95")))

    names = [n.strip() for n in row.get("약", "").split(SEPARATOR) if n.strip()]
    frequencies = [f.strip() for f in row.get("용법", "").split(SEPARATOR) if f.strip()]
    if len(names) != len(frequencies):
        raise OcrRowError(f"약 {len(names)}개와 용법 {len(frequencies)}개가 어긋난다 — 짝지을 수 없다")

    for index, (name, frequency) in enumerate(zip(names, frequencies, strict=True)):
        suffix = "" if index == 0 else f"_{index + 1}"
        rows.append(FieldRow(field_type=f"MEDICATION_NAME{suffix}", value=name, confidence=Decimal("0.94")))
        rows.append(FieldRow(field_type=f"FREQUENCY{suffix}", value=frequency, confidence=Decimal("0.93")))

    duration = duration_row(row.get("총투원문", ""), row.get("총투단위", ""), row.get("처방일수", ""))
    if duration is not None:
        rows.append(duration)

    lab, dropped = _lab_rows(row)
    rows.extend(lab)

    return ReadRow(stage=stage, fields=tuple(rows), dropped=tuple(dropped))
