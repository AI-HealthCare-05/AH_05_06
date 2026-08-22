"""합성 CSV 칸 → 저장 위치 매핑 — KEY-30.

「데이터 생성자가 추가 해석 없이 fixture 를 만들 수 있음」이 이 파일의 목표다.
칸마다 **어디에 들어가는지 · 무슨 타입인지 · 필수인지**를 적어 둔다.

세 칸은 **저장하지 않는다.** 무엇을 안 넣는지도 적어야
시드가 「이건 왜 빠졌지」 하며 억지로 컬럼을 만들지 않는다.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, NamedTuple


class Kind(StrEnum):
    """값을 어떻게 읽어야 하는가."""

    TEXT = "text"
    DATE = "date"  # YYYY-MM-DD
    INT = "int"
    BOOL = "bool"  # Y / N
    ENUM = "enum"
    DECIMAL = "decimal"
    LAB = "lab"  # 검사 수치 — 값이 있거나, 아직 안 나왔거나
    FREE = "free"  # 사람이 읽는 자유 문자열. 파싱하지 않는다


#: 검사는 「값이 없다」와 「아직 안 나왔다」가 다르다.
#: 빈 칸은 그 방문에 검사를 안 한 것이고(S1-9), 이 표시는 검사는 했는데
#: 결과가 늦는 것이다(S1-7). 화면이 그 줄만 점선 + ? 로 그린다.
#: 추측해서 채우지 않으려면 시드가 이 둘을 갈라 넣어야 한다.
PENDING = "추후보고예정"


class Where(StrEnum):
    """어느 표로 가는가."""

    PATIENT = "patient"
    VISIT = "visit"
    PRESCRIPTION = "prescription"
    PRESCRIPTION_ITEM = "prescription_item"
    VISIT_FLAG = "visit_flag"
    LAB_RESULT = "lab_result"
    OCR_INPUT = "ocr_input"  # DB 가 아니라 판독이 읽어야 할 원문
    DERIVED = "derived"  # 다른 값에서 계산한다
    EVENT = "event"  # event_log · message 에서 파생한다
    DOC_ONLY = "doc_only"  # 문서용. 어디에도 안 들어간다


@dataclass(frozen=True)
class Field:
    where: Where
    name: str  # 표 안의 필드명. 저장하지 않으면 빈 문자열
    kind: Kind
    required: bool = False
    note: str = ""
    choices: tuple[str, ...] = ()


#: 정본은 docs/data/synthetic-patients.csv 다. 이 표는 그 칸을 어디에 넣을지만 정한다.
MAPPING: dict[str, Field] = {
    "시나리오ID": Field(Where.DOC_ONLY, "", Kind.TEXT, True, "팀이 서로에게 쓰는 이름"),
    "차트번호": Field(Where.PATIENT, "hospital_patient_no", Kind.TEXT, True, "병원 내 환자번호"),
    "이름": Field(Where.PATIENT, "name", Kind.TEXT, True),
    "생년월일": Field(Where.PATIENT, "birth_date", Kind.DATE, True, "환자 본인확인에 그대로 쓴다"),
    "휴대폰": Field(Where.PATIENT, "phone", Kind.TEXT, True, "화면에는 뒤 4자리만"),
    "문자수신동의": Field(Where.PATIENT, "sms_consent", Kind.BOOL, True, "N 이면 sms_opt_out 도 참"),
    "진료일": Field(Where.VISIT, "visited_at", Kind.DATE, note="Asia/Seoul 현지 시각으로 변환해 저장"),
    "담당의": Field(Where.VISIT, "doctor_id", Kind.TEXT, note="이름 → 직원 픽스처의 uuid 로 푼다"),
    "진단": Field(Where.DERIVED, "", Kind.FREE, note="처방 세트가 질환을 담는다. 별도 컬럼이 아니다"),
    "초진재진": Field(Where.DERIVED, "", Kind.ENUM, choices=("초진", "재진"), note="지난 방문이 있는지로 정한다"),
    "처방세트": Field(
        Where.PRESCRIPTION,
        # `prescription_set_version_id` 였는데 KEY-137 에서 고쳤다. 실제 값이
        # "자궁내막증 · 비잔 (계속)" 같은 **사람이 읽는 이름**이고 세트 템플릿
        # 표는 없다. `..._id` 로 부르면 다음 사람이 조인할 표를 찾게 된다.
        "prescription_set",
        Kind.TEXT,
        note="진료 당시 세트 이름의 스냅샷. 템플릿 표가 생기면 FK 를 따로 더한다",
    ),
    "약": Field(
        Where.PRESCRIPTION_ITEM,
        "name",
        Kind.FREE,
        note="한 줄에 ` + ` 로 여럿일 수 있다 — 항목별로 갈라 넣는다",
    ),
    "용법": Field(
        Where.PRESCRIPTION_ITEM,
        "frequency",
        Kind.FREE,
        note="`약` 과 ` + ` 개수가 같다(전수 확인). 같은 순서로 짝짓는다",
    ),
    "총투원문": Field(Where.OCR_INPUT, "", Kind.TEXT, note="판독이 읽어야 할 원문. DB 에 넣지 않는다"),
    "총투단위": Field(Where.OCR_INPUT, "", Kind.ENUM, choices=("일수", "통수"), note="통수면 × 28 일"),
    "처방일수": Field(
        Where.PRESCRIPTION_ITEM,
        "duration_days",
        Kind.INT,
        note="소진일 계산의 근거. 행에 하나뿐이라 `필요시` 약에는 넣지 않는다(KEY-137)",
    ),
    "소진예정일": Field(Where.DERIVED, "", Kind.DATE, note="visited_at 현지 날짜 + duration_days"),
    "혈색소": Field(Where.LAB_RESULT, "value", Kind.LAB, note="g/dL"),
    "자궁내막종": Field(Where.LAB_RESULT, "value", Kind.LAB, note="cm"),
    "내막두께": Field(Where.LAB_RESULT, "value", Kind.LAB, note="cm"),
    "ASTALT": Field(Where.LAB_RESULT, "value", Kind.FREE, note="AST/ALT 두 값을 / 로 잇는다"),
    "월경주기": Field(Where.LAB_RESULT, "value", Kind.FREE),
    "총테스토스테론": Field(Where.LAB_RESULT, "value", Kind.LAB, note="ng/mL"),
    "DHEAS": Field(Where.LAB_RESULT, "value", Kind.LAB, note="µg/dL"),
    "LH_FSH": Field(Where.LAB_RESULT, "value", Kind.LAB, note="비율"),
    "AMH": Field(Where.LAB_RESULT, "value", Kind.LAB, note="ng/mL"),
    "기타검사": Field(Where.LAB_RESULT, "value", Kind.FREE, note="CA-125 · HbA1c · BMI 를 · 로 잇는다"),
    "특이사항": Field(Where.VISIT_FLAG, "code", Kind.FREE, note="사람 말 → flag code 로 옮긴다"),
    "진료상태": Field(
        Where.EVENT,
        "",
        Kind.ENUM,
        note="저장하지 않는다. event_log 에서 파생(v2.2)",
        choices=(
            "생성 중",
            "스탭 확인 중",
            "승인 대기",
            "발송 예정",
            "발송 완료",
            "보완",
            "계획된 중단",
            "진료기록 없음",
        ),
    ),
    "확인문자회차": Field(Where.EVENT, "", Kind.FREE, note="message 발송 이벤트로 만든다"),
    "열람여부": Field(Where.EVENT, "", Kind.ENUM, choices=("열람", "미열람"), note="열람 이벤트로 만든다"),
    "이탈표시": Field(
        Where.EVENT,
        "",
        Kind.ENUM,
        note="저장하지 않는다. 이벤트에서 파생하는 플래그 넷",
        choices=("3회 연속 미열람", "소진 후 7일 경과", "6개월 이상 미내원", "복약 중단 응답"),
    ),
    "케이스의도": Field(Where.DOC_ONLY, "", Kind.FREE, True, "왜 이 행이 있는가"),
}

#: 저장하지 않는 자리. 시드가 억지로 컬럼을 만들지 않게 한다.
NOT_STORED = frozenset({Where.OCR_INPUT, Where.DERIVED, Where.EVENT, Where.DOC_ONLY})


#: **저장 대상인데 표가 아직 없다** — KEY-136.
#:
#: 이 파일은 지금까지 자리를 둘로만 갈랐다. 「저장한다」와 「저장 안 한다」다.
#: 그런데 저장 대상 여섯 중 **넷은 갈 표가 실제로 없다.** 그 상태가 파일에
#: 안 보여서, 읽는 사람은 `patient` 처럼 이미 있는 표인 줄 알고 시드를 짜게 된다.
#:
#: 그래서 세 번째 자리를 만든다. 여기 있는 것은 「언젠가 만들 표」이고,
#: **왜 아직 없는지가 값으로 붙어 있다.**
#:
#: 검사가 양방향으로 지킨다(`test_field_mapping.py`).
#:
#:     여기 없는 저장 대상 → 표가 **있어야** 한다. 없으면 죽는다
#:     여기 있는 것       → 표가 **없어야** 한다. 생기면 죽어서 「빼라」고 한다
#:
#: 뒤쪽이 중요하다. 표를 만든 사람이 이 파일을 고치는 것을 잊어도 검사가 잡는다.
#: 「만든다」인가 「계획」인가를 **문자열에서 읽지 않는다.**
#:
#: 예전에는 판정·티켓·근거를 자유 문장 하나에 담고 `why.startswith("만든다")` 로
#: 갈랐다. 문구를 조금만 다듬어도(마커 앞에 수식어 하나) 그 항목이 **조용히 검사
#: 대상에서 빠진다** — 검사는 계속 통과하는데 아무것도 안 잡는 상태가 된다
#: (이희진 님 `#68` 리뷰). 판정을 칸으로 분리하면 그 실수가 타입에서 막힌다.
class Planned(NamedTuple):
    """아직 표가 없는 자리. 판정과 근거를 따로 둔다."""

    status: Literal["만든다", "계획"]
    why: str


PLANNED_TABLES: dict[Where, Planned] = {
    # `prescription` · `prescription_item` 은 KEY-137 에서 만들어 여기서 뺐다.
    # 표가 생기면 이 목록에 남아 있는 것 자체가 검사를 죽인다.
    Where.LAB_RESULT: Planned(
        "계획",
        "`ocr_field` 와 겹친다. 그 표가 이미 `field_type` + `value` + "
        "`is_confirmed` 로 진료별 검사값을 담는다. 별도 표가 필요한지는 「환자의 "
        "**지난** 검사값을 읽어야 하는가」에 달렸고, 그것이 KEY-109 의 미결 항목이다. "
        "여기서 정하면 그 결정을 앞지른다.",
    ),
    Where.VISIT_FLAG: Planned(
        "계획",
        "**코드 집합이 아직 안 닫혔다.** `docs/synthetic-data-spec.md` §8 이 "
        "`DEPRESSION`·`HTN`·`SMOKING`·`DM`·`PREGNANCY_PLAN` 「등」으로 열어 두었고, "
        "이 파일은 같은 칸을 `Kind.FREE` 로 적어 두 정본이 어긋나 있다(문서는 `enum`). "
        "실제 값은 '임신 계획'·'우울증 병력'·'당뇨'(28/100행)이고, 임신부 금기 약물 같은 "
        "**안전 차단의 근거**가 된다 — 코드를 임의로 닫으면 안 되는 자리라 "
        "표보다 그 결정이 먼저다.",
    ),
}

#: OpenAPI 스키마에서 찾을 이름 → 우리 표. API 가 생기면 대조가 켜진다.
API_SCHEMA_FOR = {
    Where.PATIENT: ("Patient", "PatientResponse", "PatientInfoResponse"),
    Where.VISIT: ("Visit", "VisitResponse", "VisitInfoResponse"),
}
