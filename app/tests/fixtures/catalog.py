"""처방 세트·주의·응급 문구 합성 픽스처 — KEY-165.

합성 데이터 CSV(docs/data/synthetic-patients.csv)에 등장하는 8종 처방 세트와
각 세트의 caution·emergency 마스터 콘텐츠를 정의한다.

**이 파일의 모든 값은 테스트·개발용 합성 데이터다.**
실제 환자정보·운영 비밀값·인증된 처방 원문을 포함하지 않는다.

드러그 콘텐츠 커버리지:
  - APPROVED 완비(caution+emergency): 비잔 계열 3종, 야즈 계열 2종, 대사관리 1종
  - APPROVED emergency만:           PCOS · 초진 (야즈 불가) — caution 미승인 케이스 재현
  - 콘텐츠 없음:                     PCOS · 초진 — 미등록 콘텐츠 폴백 케이스 재현

이 분포 덕에 D-1(정상)·D-2(미등록·미승인·근거 누락 차단) 테스트가
별도 DB 조작 없이 seed 상태로 동작한다.
"""

from dataclasses import dataclass, field
from datetime import date

from app.models.catalog import ApprovalStatus, CautionSectionKey, SourceGrade

# 출처 메타데이터 공통값 — A등급 식약처 자료(KEY-180 §2)
_SOURCE_NAME = "의약품안전나라 제품 허가사항"
_SOURCE_ORG = "식품의약품안전처"
_VERIFIED_AT = date(2026, 8, 25)
_CONTENT_VERSION = "2026-08-25"


@dataclass(frozen=True)
class PrescriptionSetRow:
    name: str


@dataclass(frozen=True)
class DrugCautionContentRow:
    prescription_set_name: str
    section_key: CautionSectionKey
    body: str
    source_name: str = _SOURCE_NAME
    source_org: str = _SOURCE_ORG
    source_url: str = ""
    verified_at: date = field(default=_VERIFIED_AT)
    content_version: str = _CONTENT_VERSION
    source_grade: SourceGrade = SourceGrade.A
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED


# ── 처방 세트 8종 ────────────────────────────────────────────────────────────
# 합성 CSV 에 실제로 등장하는 이름을 그대로 사용한다.
PRESCRIPTION_SETS: tuple[PrescriptionSetRow, ...] = (
    PrescriptionSetRow("자궁내막증 · 비잔 (처음)"),
    PrescriptionSetRow("자궁내막증 · 비잔 (계속)"),
    PrescriptionSetRow("자궁내막증 · 통증관리"),
    PrescriptionSetRow("PCOS · 초진"),
    PrescriptionSetRow("PCOS · 초진 (야즈 불가)"),
    PrescriptionSetRow("PCOS · 야즈 (계속)"),
    PrescriptionSetRow("PCOS · 야즈 + 메트포르민"),
    PrescriptionSetRow("PCOS · 대사관리"),
)

# ── 주의·응급 문구 마스터 ────────────────────────────────────────────────────
# [합성] 접두어: 테스트·개발용 합성 콘텐츠임을 표시한다.
# 실제 운영에서는 의료 안전 검수 책임자(이희진)가 승인한 정본으로 교체한다.
DRUG_CAUTION_CONTENTS: tuple[DrugCautionContentRow, ...] = (
    # ── 자궁내막증 · 비잔 (처음) ─────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (처음)",
        section_key=CautionSectionKey.CAUTION,
        body=(
            "[합성] 복용 초기에 두통, 구역, 유방압통, 불규칙한 질출혈이 나타날 수 있으며 "
            "대개 2~3개월 내 호전됩니다. "
            "기분 변화나 우울 증상이 지속되면 의료진에게 알려 주세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/dienogest-caution",
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (처음)",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "[합성] 한쪽 다리에 심한 통증·부기·발적이 생기거나, "
            "갑작스러운 흉통·호흡 곤란·시야 이상이 나타나면 "
            "즉시 복용을 중단하고 응급실을 방문하세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/dienogest-emergency",
    ),
    # ── 자궁내막증 · 비잔 (계속) ─────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (계속)",
        section_key=CautionSectionKey.CAUTION,
        body=(
            "[합성] 장기 복용 중 두통, 체중 변화, 성욕 감소가 나타날 수 있습니다. "
            "골밀도 모니터링이 필요한 경우 의료진 안내를 따르세요. "
            "우울 증상이 이전보다 심해지면 즉시 알려 주세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/dienogest-long-caution",
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (계속)",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "[합성] 한쪽 다리에 심한 통증·부기·발적이 생기거나, "
            "갑작스러운 흉통·호흡 곤란·시야 이상이 나타나면 "
            "즉시 복용을 중단하고 응급실을 방문하세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/dienogest-long-emergency",
    ),
    # ── 자궁내막증 · 통증관리 ────────────────────────────────────────────────
    # 비잔 기준 안내. 진통제(대증약)는 범용 caution 으로 커버 (KEY-180 §1).
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 통증관리",
        section_key=CautionSectionKey.CAUTION,
        body=(
            "[합성] 복용 중 두통, 구역, 통증 부위 변화가 나타날 수 있습니다. "
            "진통제는 음식과 함께 복용하면 위장 불편감을 줄일 수 있습니다. "
            "통증이 이전보다 심해지거나 새로운 부위에 생기면 알려 주세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/pain-management-caution",
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 통증관리",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "[합성] 심한 복통, 혈변, 검은 변, 또는 토혈이 나타나면 "
            "즉시 복용을 중단하고 응급실을 방문하세요. "
            "한쪽 다리의 갑작스러운 부기·통증도 즉시 알려 주세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/pain-management-emergency",
    ),
    # ── PCOS · 초진 (야즈 불가) ─────────────────────────────────────────────
    # caution 없음(DRAFT 없음) — 테스트에서 "caution 근거 누락 → 범용 문구 폴백" 재현
    DrugCautionContentRow(
        prescription_set_name="PCOS · 초진 (야즈 불가)",
        section_key=CautionSectionKey.EMERGENCY,
        body=("[합성] 갑작스러운 흉통, 심한 두통, 시야 이상, 호흡 곤란이 나타나면 즉시 응급실을 방문하세요."),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/pcos-alt-emergency",
    ),
    # ── PCOS · 야즈 (계속) ──────────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (계속)",
        section_key=CautionSectionKey.CAUTION,
        body=(
            "[합성] 복용 중 구역, 두통, 유방압통이 나타날 수 있으며 대개 호전됩니다. "
            "칼륨을 높이는 약(스피로노락톤, ACEI, NSAID 등)을 함께 복용 중이면 "
            "반드시 의료진에게 알려 주세요. "
            "혈압이 갑자기 오르거나 다리가 부으면 알려 주세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/drsp-ee-caution",
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (계속)",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "[합성] 한쪽 다리에 심한 통증·부기·발적, 갑작스러운 흉통, 호흡 곤란, "
            "심한 두통 또는 시야 이상이 나타나면 즉시 복용을 중단하고 응급실을 방문하세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/drsp-ee-emergency",
    ),
    # ── PCOS · 야즈 + 메트포르민 ────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 + 메트포르민",
        section_key=CautionSectionKey.CAUTION,
        body=(
            "[합성] 야즈 복용 중 구역·두통·유방압통, 메트포르민 복용 중 소화기계 "
            "불편감(구역·설사·복통)이 나타날 수 있습니다. 메트포르민은 식사와 함께 "
            "복용하면 위장 증상이 줄어듭니다. 조영제를 사용하는 검사 전에 반드시 "
            "의료진에게 알려 주세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/drsp-metformin-caution",
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 + 메트포르민",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "[합성] 심한 피로감·근육 통증·호흡 곤란·복통이 동시에 나타나거나 소변량이 "
            "크게 줄면 즉시 응급실을 방문하세요. "
            "한쪽 다리의 심한 부기·통증·발적이나 갑작스러운 흉통도 즉시 알려 주세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/drsp-metformin-emergency",
    ),
    # ── PCOS · 대사관리 ──────────────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="PCOS · 대사관리",
        section_key=CautionSectionKey.CAUTION,
        body=(
            "[합성] 메트포르민 복용 초기에 구역, 설사, 복통이 나타날 수 있으며 "
            "식사와 함께 복용하면 줄어듭니다. 음주는 젖산산증 위험을 높이므로 "
            "복용 기간 중 삼가 주세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/metformin-metabolic-caution",
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 대사관리",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "[합성] 심한 피로감, 근육 통증, 호흡 곤란, 위장 불편감이 동시에 나타나거나 "
            "소변량이 크게 줄면 즉시 복용을 중단하고 응급실을 방문하세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/metformin-metabolic-emergency",
    ),
)
