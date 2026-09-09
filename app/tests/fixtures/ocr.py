"""OCR 4상태 합성 fixture — KEY-227.

Worker·테스트가 같은 고정 입력 데이터를 쓴다.
반복 실행해도 동일한 결과를 보장한다 (인수조건 1).

상태별 대응:
  SYN_EMS_01_CLOVA_RESULT     정상   — COMPLETED + 고신뢰 (confidence ≥ 0.75)
  SYN_LOW_CONF_CLOVA_RESULT   저신뢰 — COMPLETED + 저신뢰 (confidence < 0.75) 항목 포함
  SYN_FAIL_CLOVA_CODE         실패   — 구조적 오류, 재시도 없이 FAILED
  SYN_TIMEOUT_CLOVA_CODE      타임아웃 — 일시 오류, 재시도 후 FAILED
"""

from ai_worker.adapters.clova import ClovaOcrResult, ClovaTextField

SYN_EMS_01_REQUIRED_FIELDS = frozenset({"DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"})

# ── 정상 (COMPLETED + 고신뢰) ────────────────────────────────────────────────
# PR #147 / KEY-190에서 기록한 CLOVA General V2 블록 순서다. 필드 추출
# 단위 테스트와 전체 E2E가 같은 판독 표본을 써야, 서로 다른 가짜 응답이 각각
# 통과하면서 실제 여정만 깨지는 일을 막을 수 있다.
SYN_EMS_01_CLOVA_BLOCKS = (
    ClovaTextField(text="[진단]", confidence=0.99),
    ClovaTextField(text="N809", confidence=0.96),
    ClovaTextField(text="ICD코드", confidence=0.98),
    ClovaTextField(text="상병명", confidence=0.99),
    ClovaTextField(text="자궁내막증", confidence=0.92),
    ClovaTextField(text="주/부상병", confidence=0.97),
    ClovaTextField(text="주상병", confidence=0.95),
    ClovaTextField(text="약품명", confidence=0.99),
    ClovaTextField(text="1회량", confidence=0.98),
    ClovaTextField(text="일일횟수", confidence=0.97),
    ClovaTextField(text="처방일수", confidence=0.99),
    ClovaTextField(text="비잔정(디에노게스트)2mg", confidence=0.94),
    ClovaTextField(text="1", confidence=0.98),
    ClovaTextField(text="1", confidence=0.97),
    ClovaTextField(text="84", confidence=0.99),
)

SYN_EMS_01_CLOVA_RESULT = ClovaOcrResult(
    raw_text="\n".join(block.text for block in SYN_EMS_01_CLOVA_BLOCKS),
    fields=list(SYN_EMS_01_CLOVA_BLOCKS),
    elapsed_ms=37,
)

# ── 저신뢰 (COMPLETED + confidence < 0.75 항목 포함) ────────────────────────
# _seed는 LAB_RESULT 문서를 생성하므로 LAB_RESULT 파서(_extract_lab)가 동작한다.
# CA_125·AMH 블록의 confidence가 임계값(0.75) 미만으로 고정한다.
# OcrJob은 COMPLETED이지만 화면은 해당 항목을 저신뢰로 표시한다.
SYN_LOW_CONF_CLOVA_BLOCKS = (
    ClovaTextField(text="CA-125 : 48 U/mL", confidence=0.62),  # 저신뢰
    ClovaTextField(text="AMH : 2.8 ng/mL", confidence=0.58),  # 저신뢰
)

SYN_LOW_CONF_CLOVA_RESULT = ClovaOcrResult(
    raw_text="CA-125 : 48 U/mL\nAMH : 2.8 ng/mL",
    fields=list(SYN_LOW_CONF_CLOVA_BLOCKS),
    elapsed_ms=41,
)

# ── EMR 저신뢰 (COMPLETED + EMR 값 블록 confidence < 0.75) ──────────────────
# _extract_from_clova_blocks 은 값 블록의 confidence를 그대로 OcrField.confidence에 저장한다.
# 헤더 블록은 고신뢰로 유지해 파서가 구조를 인식하게 하고,
# 진단명("자궁내막증")·약품명 블록만 0.75 미만으로 설정한다.
SYN_LOW_CONF_EMR_CLOVA_BLOCKS = (
    ClovaTextField(text="[진단]", confidence=0.99),
    ClovaTextField(text="N809", confidence=0.99),
    ClovaTextField(text="ICD코드", confidence=0.98),
    ClovaTextField(text="상병명", confidence=0.99),
    ClovaTextField(text="자궁내막증", confidence=0.62),  # 저신뢰 — DIAGNOSIS 값 블록
    ClovaTextField(text="주/부상병", confidence=0.97),
    ClovaTextField(text="주상병", confidence=0.95),
    ClovaTextField(text="약품명", confidence=0.99),
    ClovaTextField(text="1회량", confidence=0.98),
    ClovaTextField(text="일일횟수", confidence=0.97),
    ClovaTextField(text="처방일수", confidence=0.99),
    ClovaTextField(text="비잔정(디에노게스트)2mg", confidence=0.58),  # 저신뢰 — MEDICATION_NAME 값 블록
    ClovaTextField(text="1", confidence=0.98),
    ClovaTextField(text="1", confidence=0.97),
    ClovaTextField(text="84", confidence=0.99),
)

SYN_LOW_CONF_EMR_CLOVA_RESULT = ClovaOcrResult(
    raw_text="\n".join(b.text for b in SYN_LOW_CONF_EMR_CLOVA_BLOCKS),
    fields=list(SYN_LOW_CONF_EMR_CLOVA_BLOCKS),
    elapsed_ms=43,
)

# ── 실패·타임아웃 오류 코드 상수 ────────────────────────────────────────────
# ClovaOcrError(code=...) 의 code 값으로 사용한다.
# 반복 실행해도 같은 오류 코드를 사용한다 (인수조건 1).
SYN_FAIL_CLOVA_CODE = "CLOVA_PARSE_ERROR"  # 구조적 실패 — 재시도 없이 즉시 FAILED
SYN_TIMEOUT_CLOVA_CODE = "CLOVA_TIMEOUT"  # 일시 오류 — 재시도 대상, 소진 후 FAILED

# ── LAB_RESULT 자동 분류 fixture (KEY-278) ───────────────────────────────────
# "검사항목" + "검사결과" 헤더가 있는 표 구조 — _find_lab_columns 이 LAB_RESULT 로 감지한다.
# 바운딩 박스를 부여해야 rows 가 생성되고, detect_document_type 이 작동한다.
_LAB_HEADER_ROW = [
    ClovaTextField(text="검사항목", confidence=1.0, left=100.0, top=10.0, right=200.0, bottom=30.0),
    ClovaTextField(text="검사결과", confidence=1.0, left=210.0, top=10.0, right=310.0, bottom=30.0),
]
_LAB_DATA_ROW = [
    ClovaTextField(text="AST(GOT)", confidence=1.0, left=100.0, top=40.0, right=200.0, bottom=60.0),
    ClovaTextField(text="21", confidence=1.0, left=210.0, top=40.0, right=310.0, bottom=60.0),
]

SYN_LAB_01_CLOVA_RESULT = ClovaOcrResult(
    raw_text="검사항목\t검사결과\nAST(GOT)\t21",
    fields=[*_LAB_HEADER_ROW, *_LAB_DATA_ROW],
    rows=[_LAB_HEADER_ROW, _LAB_DATA_ROW],
    elapsed_ms=40,
)
