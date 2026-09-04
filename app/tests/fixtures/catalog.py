"""처방 세트·주의·응급 문구 합성 픽스처 — KEY-165.

합성 데이터 CSV(docs/data/synthetic-patients.csv)에 등장하는 4종 처방 세트와
각 세트의 caution·emergency 마스터 콘텐츠를 정의한다.

**이 파일의 모든 값은 테스트·개발용 합성 데이터다.**
실제 환자정보·운영 비밀값·인증된 처방 원문을 포함하지 않는다.

드러그 콘텐츠 커버리지 — **네 세트 모두 APPROVED 완비**(caution+emergency 8행):
  - 자궁내막증 · 비잔 (처음) / (계속) — 각자의 문구
  - PCOS · 야즈 (처음) / (계속)      — 약이 같아 문구도 같다

**KEY-262 전에는 일부러 빈 자리를 두었다.** 「emergency만 승인」·「콘텐츠 없음」인
세트를 seed 에 남겨 D-2(미등록·미승인 폴백)를 재현했었다. 세트를 넷으로 줄이면서
그 두 세트가 사라졌고, 지금은 커버리지가 고르다.

D-2 는 그 빈 자리에 기대지 않는다. `test_key165_drug_caution.py` 의 D-2 는
없는 세트 이름(`"미등록세트XYZ"`)과 DRAFT 콘텐츠를 테스트 안에서 직접 만들어
쓴다. seed 분포와 무관하게 서므로 이 픽스처를 줄여도 그대로 동작한다.
D-1(정상 생성)만 이 seed 를 그대로 쓴다.
"""

from dataclasses import dataclass, field
from datetime import date

from app.models.catalog import ApprovalStatus, CautionSectionKey, SetDisease, SourceGrade

# ── 출처 메타데이터 ─────────────────────────────────────────────────────────
#
# **주의사항 넷은 자문이 근거다.** 응급과 다르다.
#
# 이 글은 식약처 허가사항에서 온 것이 아니라 **박영 산부인과 전문의 자문**에서
# 왔고, 2026-09-04 에 원장님이 정본으로 승인하셨다. 허가사항 주소를 붙이면
# **출처가 틀린다** — 그 경고를 `docs/guide-copy-worksheet.md` 4절이 적어 두었다.
#
# 팀이 이미 이 방식을 쓴다. 노션 「안내 부품 카탈로그 — 확정본 40개」가 원천을
# 「박영 산부인과 전문의 복약지도 자문 내용」으로 적고 있고 그 40개가 전부 자문
# 근거다. 새로 정한 것이 아니라 따른 것이다.
#
# 🚩 **등급은 이희진 님 확인이 필요하다.** `SourceGrade` 주석은 A 를 「허가정보·
# 진료지침」으로 적었는데, 전문의 직접 자문이 A 에 해당한다는 근거가 저장소
# 안에는 없다. A 가 아니면 `drug_caution.py` 가 조용히 걸러 폴백한다.
_ADVICE_SOURCE_NAME = "박영 산부인과 전문의 복약지도 — 자문 내용"
_ADVICE_SOURCE_ORG = "박영 산부인과"
_ADVICE_SOURCE_URL = "https://app.notion.com/p/3ba0c3b3380580068fa1f32666a8b68c"
_APPROVED_AT = date(2026, 9, 4)
_APPROVED_VERSION = "2026-09-04"

# 응급 넷은 이번 범위 밖이라 예전 값을 그대로 둔다 (KEY-265 는 열두 칸만 다룬다).
_SOURCE_NAME = "의약품안전나라 제품 허가사항"
_SOURCE_ORG = "식품의약품안전처"
_VERIFIED_AT = date(2026, 8, 25)
_CONTENT_VERSION = "2026-08-25"


@dataclass(frozen=True)
class PrescriptionSetRow:
    """대표 처방 한 줄.

    🚩 **`disease` 를 반드시 적는다.** 모델 기본값이 `ENDOMETRIOSIS` 라
    (`app/models/catalog.py`) 안 적으면 PCOS 세트가 **조용히 자궁내막증 밑으로
    들어간다** — 설정 화면 레일이 질환으로 묶으므로 다낭성난소증후군 묶음이
    통째로 사라진다. 터지지 않아서 씨앗을 새로 부어 보기 전에는 안 보인다.
    """

    name: str
    disease: SetDisease


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


# ── 처방 세트 4종 ────────────────────────────────────────────────────────────
# 합성 CSV 에 실제로 등장하는 이름을 그대로 사용한다.
#
# **여덟에서 넷으로 줄였다** (KEY-262, 팀 회의 결정). 질환 둘 × 처음·계속이다.
# 나머지 다섯이 가리키던 진료 25 건은 각자의 「처음」으로 옮겼다
# (`docs/data/synthetic-patients.csv`).
#
# 🚩 **`PCOS · 초진 (야즈 불가)` 도 「야즈 (처음)」으로 옮겼다.** 흡연으로 야즈가
# 금기인 환자(`SYN-PCOS-06`)라 야즈 세트가 맞지 않는데, 팀에서 그렇게 정했다.
# 그래서 **「금기로 처방 경로가 바뀐다」 시나리오는 이제 데이터로 재현되지
# 않는다** — 명세에도 적어 두었다.
PRESCRIPTION_SETS: tuple[PrescriptionSetRow, ...] = (
    PrescriptionSetRow("자궁내막증 · 비잔 (처음)", SetDisease.ENDOMETRIOSIS),
    PrescriptionSetRow("자궁내막증 · 비잔 (계속)", SetDisease.ENDOMETRIOSIS),
    PrescriptionSetRow("PCOS · 야즈 (처음)", SetDisease.PCOS),
    PrescriptionSetRow("PCOS · 야즈 (계속)", SetDisease.PCOS),
)

# ── 주의·응급 문구 마스터 ────────────────────────────────────────────────────
# [합성] 접두어: 테스트·개발용 합성 콘텐츠임을 표시한다.
# 실제 운영에서는 의료 안전 검수 책임자(이희진)가 승인한 정본으로 교체한다.
DRUG_CAUTION_CONTENTS: tuple[DrugCautionContentRow, ...] = (
    # ── 자궁내막증 · 비잔 (처음) ─────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (처음)",
        section_key=CautionSectionKey.CAUTION,
        # 정본 A-2 — 정리본 2.4 의 ✅+🔶, 원장님 승인 2026-09-04
        body=(
            "질출혈이 가장 흔해요. 팬티라이너에 묻을 정도로 나왔다 안 나왔다 합니다. 가슴이 단단해지는 "
            "느낌, 몸이 붓는 느낌도 시간이 지나면 좋아져요.\n\n"
            "드물게 기분이 가라앉는 분들이 있어요. 우울감이나 감정 기복이 평소와 다르게 느껴지면 참지 "
            "마시고 알려주세요. 약을 조절하거나 바꿀 수 있어요.\n\n"
            "비잔을 드시면 생리가 없어지는데, 이건 폐경이 아니에요. 호르몬을 일정하게 유지시켜서 생리가 "
            "안 나오게 하는 것뿐이고, 약을 끊으면 다시 돌아옵니다."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (처음)",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "한쪽 다리에 심한 통증·부기·발적이 생기거나, "
            "갑작스러운 흉통·호흡 곤란·시야 이상이 나타나면 "
            "즉시 복용을 중단하고 응급실을 방문하세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/dienogest-emergency",
    ),
    # ── 자궁내막증 · 비잔 (계속) ─────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (계속)",
        section_key=CautionSectionKey.CAUTION,
        # 정본 B-2 — 문서가 「A-2 와 같다」로 못박았다
        body=(
            "질출혈이 가장 흔해요. 팬티라이너에 묻을 정도로 나왔다 안 나왔다 합니다. 가슴이 단단해지는 "
            "느낌, 몸이 붓는 느낌도 시간이 지나면 좋아져요.\n\n"
            "드물게 기분이 가라앉는 분들이 있어요. 우울감이나 감정 기복이 평소와 다르게 느껴지면 참지 "
            "마시고 알려주세요. 약을 조절하거나 바꿀 수 있어요.\n\n"
            "비잔을 드시면 생리가 없어지는데, 이건 폐경이 아니에요. 호르몬을 일정하게 유지시켜서 생리가 "
            "안 나오게 하는 것뿐이고, 약을 끊으면 다시 돌아옵니다."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (계속)",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "한쪽 다리에 심한 통증·부기·발적이 생기거나, "
            "갑작스러운 흉통·호흡 곤란·시야 이상이 나타나면 "
            "즉시 복용을 중단하고 응급실을 방문하세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/dienogest-long-emergency",
    ),
    # ── PCOS · 야즈 (계속) ──────────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (계속)",
        section_key=CautionSectionKey.CAUTION,
        # 정본 D-2 — 문서가 「C-2 와 같다」로 못박았다
        body=(
            "예상치 못한 질출혈이 가장 흔해요. 특히 처음 몇 달 동안 그렇습니다. 대부분 시간이 지나면서 "
            "줄어드니 그러려니 하셔도 괜찮아요.\n\n"
            "약을 한두 알 드시고 구역질·구토가 심하게 나면 다음 방문 때 알려주세요. 약을 드시기 "
            "시작하자마자 온몸에 두드러기가 나는 경우도 알려주세요. 3주 이상 잘 드시다가 두드러기가 "
            "생겼다면 약보다 다른 원인일 가능성이 높지만, 그래도 알려주세요.\n\n"
            "흡연을 하시거나 전조증상이 있는 편두통이 있으시면 미리 꼭 말씀해 주세요."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (계속)",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "한쪽 다리에 심한 통증·부기·발적, 갑작스러운 흉통, 호흡 곤란, "
            "심한 두통 또는 시야 이상이 나타나면 즉시 복용을 중단하고 응급실을 방문하세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/drsp-ee-emergency",
    ),
    # ── PCOS · 야즈 (처음) ──────────────────────────────────────────────────
    # **약이 같으니 글도 같다.** 「처음」과 「계속」을 가르는 것은 방문 주기이지
    # 약이 아니다 — 문구가 갈릴 근거가 생기면 그때 나눈다 (KEY-265).
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (처음)",
        section_key=CautionSectionKey.CAUTION,
        # 정본 C-2 — 정리본 1.4 의 ✅+🔶, 원장님 승인 2026-09-04
        body=(
            "예상치 못한 질출혈이 가장 흔해요. 특히 처음 몇 달 동안 그렇습니다. 대부분 시간이 지나면서 "
            "줄어드니 그러려니 하셔도 괜찮아요.\n\n"
            "약을 한두 알 드시고 구역질·구토가 심하게 나면 다음 방문 때 알려주세요. 약을 드시기 "
            "시작하자마자 온몸에 두드러기가 나는 경우도 알려주세요. 3주 이상 잘 드시다가 두드러기가 "
            "생겼다면 약보다 다른 원인일 가능성이 높지만, 그래도 알려주세요.\n\n"
            "흡연을 하시거나 전조증상이 있는 편두통이 있으시면 미리 꼭 말씀해 주세요."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (처음)",
        section_key=CautionSectionKey.EMERGENCY,
        body=(
            "한쪽 다리에 심한 통증·부기·발적, 갑작스러운 흉통, 호흡 곤란, "
            "심한 두통 또는 시야 이상이 나타나면 즉시 복용을 중단하고 응급실을 방문하세요."
        ),
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/drsp-ee-emergency",
    ),
    # ── 복약지도·생활지도 — 원장님 승인 정본 (KEY-265) ─────────────────
    # **원본이다.** `guide_copy.py` 의 `_origins()` 가 승인된 카탈로그 행을
    # 원본으로 삼고, 없으면 `guide_defaults` 로 내려간다 — 네 갈래 다 그렇다.
    # 이 여덟을 `DoctorGuideCopy`(고친 문구)에 넣었더니 화면이 정본을 「고친
    # 문구」로 보였고, 「원본으로 되돌리기」를 누르면 정본이 날아갔다.
    # A-1 · 정리본 2.1 + 2.2
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (처음)",
        section_key=CautionSectionKey.MEDICATION,
        body=(
            "자궁내막증을 그냥 두면 염증 물질이 나와서 주변 장기와 들러붙게 만들고, 난소 기능에도 "
            "부담을 줘요. 비잔은 자궁내막증 병변이 더 자라지 못하게 막고 크기를 줄여주는 약이에요.\n\n"
            "하루 한 번, 매일 같은 시간에 쉬는 기간 없이 계속 드세요. 깜빡하셨다면 생각난 즉시 "
            "드시고, 다음부터는 원래 시간에 드시면 됩니다. 한 번 걸렀다고 처음부터 다시 시작하실 "
            "필요는 없어요.\n\n"
            "처음 한 달 드신 뒤 내원하시면 부작용을 확인하고, 특별한 부작용이 없으면 이후에는 석 "
            "달분씩 처방해 드립니다."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # A-3 · 질병관리청(B) + 식약처(A). 뼈 건강 문단은 보류라 빠졌다
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (처음)",
        section_key=CautionSectionKey.LIFE,
        body=(
            "비잔은 정해진 기간이 아니라 상태를 보며 이어 가는 약이라, 3~6개월마다 정기 진찰을 "
            "받으시는 것이 중요합니다. 재발 여부를 일찍 알 수 있는 유일한 방법입니다.\n\n"
            "약을 드시고 3~4시간 안에 구토나 설사를 하셨다면 약효가 줄 수 있으니 다음 진료 때 "
            "말씀해 주세요."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # B-1 · 정리본 2.1 🎯 + 2.3 — 이 일감의 핵심 칸
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (계속)",
        section_key=CautionSectionKey.MEDICATION,
        body=(
            "통증이 사라졌다고 병변까지 없어진 것은 아니에요. 남아 있으면 계속 염증을 일으켜 유착과 "
            "만성 골반통의 원인이 됩니다. 임의로 중단하지 마시고, 끊을 시기는 진료 때 함께 정해요.\n\n"
            "하루 한 번, 매일 같은 시간에 쉬는 기간 없이 계속 드세요.\n\n"
            "석 달마다 오실 때 생리통 정도와 생리양을 확인합니다. 보통 1~2년 드신 뒤 쉬어갈 "
            "시기를 함께 봅니다. 해마다 혈액검사로 호르몬 상태도 확인해요."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # B-3 · A-3 에 자문 Ⅱ-9 한 문단을 더한 것
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 (계속)",
        section_key=CautionSectionKey.LIFE,
        body=(
            "비잔은 정해진 기간이 아니라 상태를 보며 이어 가는 약이라, 3~6개월마다 정기 진찰을 "
            "받으시는 것이 중요합니다. 재발 여부를 일찍 알 수 있는 유일한 방법입니다.\n\n"
            "약을 드시고 3~4시간 안에 구토나 설사를 하셨다면 약효가 줄 수 있으니 다음 진료 때 "
            "말씀해 주세요.\n\n"
            "오래 드시는 동안에도 해마다 혈액검사로 호르몬 상태를 확인합니다. 생리가 없는 기간이 "
            "길어지므로, 검사로 몸의 상태를 대신 확인하는 것입니다."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # C-1 · 정리본 1.1 + 1.2 — 열두 칸 중 가장 길다
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (처음)",
        section_key=CautionSectionKey.MEDICATION,
        body=(
            "검사에서 LH 수치가 FSH보다 높게 나왔고, DHEA-S 도 정상 범위보다 높았어요. "
            "몸의 호르몬 신호를 조절하는 곳이 널뛰기를 하고 있다는 뜻이에요. 야즈에는 여성호르몬 성분 "
            "두 가지가 들어 있어서 그 신호를 일정하게 잡아줍니다. 신호가 안정되면 LH 와 "
            "DHEA-S 가 서서히 내려가고, 생리 주기와 피부 상태도 함께 좋아져요.\n\n"
            "생리 주기를 따로 계산하실 필요 없어요. 분홍색 알약을 먼저 다 드시고, 이어서 흰색 "
            "알약을 드세요. 한 판을 다 드시면 쉬는 날 없이 바로 다음 판을 시작합니다. 매일 같은 "
            "시간에 드시는 것이 가장 중요해요.\n\n"
            "깜빡 잊으셨다면 생각난 즉시 한 알 드시고, 그날 정해진 시간에 원래 알약을 그대로 "
            "드세요. 12시간이 넘게 지났거나 이틀 이상 잊으셨다면, 남은 판은 계속 드시되 7일간은 "
            "다른 피임 방법을 함께 사용하시고 병원에 문의해 주세요."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # C-3 · 자문 Ⅰ-14 — 자문 원문이 넉넉한 유일한 칸
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (처음)",
        section_key=CautionSectionKey.LIFE,
        body=(
            "다낭성난소증후군에서 가장 중요한 것은 수면 습관입니다. 하루 7~8시간, 자기 전 두 "
            "시간은 휴대폰을 보지 않기, 방을 어둡게 하기, 그리고 밤 10시에서 새벽 2시 사이에 "
            "잠들어 계시는 것이 중요해요. 같은 8시간을 자도 시간대에 따라 수면의 질이 크게 "
            "다릅니다.\n\n"
            "배달 음식 용기에서 나오는 물질이 호르몬을 교란할 수 있어 배달 음식은 줄이시는 편이 "
            "좋아요. 채소와 기름기 적은 단백질을 챙겨 드시고, 운동을 곁들이면 인슐린 저항성을 줄이는 "
            "데 도움이 됩니다."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # D-1 · 정리본 1.1 🎯 + 1.3, 자문 Ⅰ-9
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (계속)",
        section_key=CautionSectionKey.MEDICATION,
        body=(
            "다낭성난소증후군은 '완치'가 아니라 '관리'하는 상태예요. 혈압이나 체중처럼 꾸준히 살펴 "
            "나갑니다. 증상이 심할 때는 약으로 조절하고, 안정되면 상황을 봐가며 조절해요. 평생 못 "
            "끊는 약이라는 뜻이 아니니 부담 갖지 않으셔도 돼요.\n\n"
            "시작하고 넉 달쯤에 혈액검사로 LH·DHEA-S 를 다시 봅니다. 수치가 잡혀도 바로 끊지 "
            "않고 보통 1~2년 유지해요. 호르몬이 한 바퀴 도는 데 석 달쯤 걸려서, 두세 바퀴는 "
            "지나야 약을 줄여도 원래대로 돌아가지 않습니다.\n\n"
            "해마다 혈액검사로 간 수치와 난소 기능을 확인합니다."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # D-3 · 문서가 「C-3 과 같다」로 못박았다
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 (계속)",
        section_key=CautionSectionKey.LIFE,
        body=(
            "다낭성난소증후군에서 가장 중요한 것은 수면 습관입니다. 하루 7~8시간, 자기 전 두 "
            "시간은 휴대폰을 보지 않기, 방을 어둡게 하기, 그리고 밤 10시에서 새벽 2시 사이에 "
            "잠들어 계시는 것이 중요해요. 같은 8시간을 자도 시간대에 따라 수면의 질이 크게 "
            "다릅니다.\n\n"
            "배달 음식 용기에서 나오는 물질이 호르몬을 교란할 수 있어 배달 음식은 줄이시는 편이 "
            "좋아요. 채소와 기름기 적은 단백질을 챙겨 드시고, 운동을 곁들이면 인슐린 저항성을 줄이는 "
            "데 도움이 됩니다."
        ),
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
)
