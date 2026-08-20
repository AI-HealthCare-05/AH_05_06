"""합성 CSV 칸 → 저장 위치 매핑 — KEY-30.

「데이터 생성자가 추가 해석 없이 fixture 를 만들 수 있음」이 이 파일의 목표다.
칸마다 **어디에 들어가는지 · 무슨 타입인지 · 필수인지**를 적어 둔다.

세 칸은 **저장하지 않는다.** 무엇을 안 넣는지도 적어야
시드가 「이건 왜 빠졌지」 하며 억지로 컬럼을 만들지 않는다.
"""

from dataclasses import dataclass
from enum import StrEnum


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
        "prescription_set_version_id",
        Kind.TEXT,
        note="템플릿 출처. Visit JSON에 저장하지 않는다",
    ),
    "약": Field(Where.PRESCRIPTION_ITEM, "name", Kind.FREE, note="실제 처방 항목의 약 이름"),
    "용법": Field(Where.PRESCRIPTION_ITEM, "frequency", Kind.FREE, note="실제 처방 항목의 용법"),
    "총투원문": Field(Where.OCR_INPUT, "", Kind.TEXT, note="판독이 읽어야 할 원문. DB 에 넣지 않는다"),
    "총투단위": Field(Where.OCR_INPUT, "", Kind.ENUM, choices=("일수", "통수"), note="통수면 × 28 일"),
    "처방일수": Field(Where.PRESCRIPTION_ITEM, "duration_days", Kind.INT, note="소진일 계산의 근거"),
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

#: OpenAPI 스키마에서 찾을 이름 → 우리 표. API 가 생기면 대조가 켜진다.
API_SCHEMA_FOR = {
    Where.PATIENT: ("Patient", "PatientResponse", "PatientInfoResponse"),
    Where.VISIT: ("Visit", "VisitResponse", "VisitInfoResponse"),
}
