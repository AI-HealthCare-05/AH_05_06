"""SYN-EMS-01의 실측 CLOVA 블록을 공유하는 테스트 픽스처 — KEY-69."""

from ai_worker.adapters.clova import ClovaOcrResult, ClovaTextField

SYN_EMS_01_REQUIRED_FIELDS = frozenset({"DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"})

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
