"""처방 세트·주의·응급 문구 합성 픽스처 — KEY-165.

합성 데이터 CSV(docs/data/synthetic-patients.csv)에 등장하는 4종 처방 세트와
각 세트의 caution·emergency 마스터 콘텐츠를 정의한다.

**이 파일의 모든 값은 테스트·개발용 합성 데이터다.**
실제 환자정보·운영 비밀값·인증된 처방 원문을 포함하지 않는다.

드러그 콘텐츠 커버리지 — **네 세트 × 네 갈래, 16 행**이 목표다:
  - 자궁내막증 · 비잔 O / 자궁내막증 · 비잔 X
  - PCOS · 야즈 O / PCOS · 야즈 X

  갈래는 복약지도·주의사항·응급·생활지도 넷이다. O 세트는 16 칸 모두 APPROVED.
  X 세트의 caution·emergency 는 이희진 검토 확정 후 추가한다 (KEY-357).
  그때까지 X 세트는 medication·life 2 칸만 APPROVED 상태이며,
  GUIDE_RAG_ENABLED=true 경로에서 X 세트 안내문 생성이 실패할 수 있다.

**KEY-357: 처음/계속 축 → 약 처방 여부 O/X 축으로 변경.**
O 세트는 기존 (처음) 세트의 승인 문구를 세트 이름 기준으로 재등록했다.
(처음)과 (계속)의 caution·emergency 는 같은 글이고,
medication·life 는 초진 안내(처음)를 기준으로 통합했다.
X 세트 medication 은 짧은 약사 복약지도 안내 문구(SourceGrade.B),
X 세트 life 는 같은 질환 O 세트와 동일한 글이다.

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
# KEY-283에서 두 축을 분리했다. 이 자문은 출처 성격대로 C로 남기되,
# `drug_caution.py`가 승인 상태와 전문의 검토 기록을 별도 안전축으로 확인한다.
_ADVICE_SOURCE_NAME = "박영 산부인과 전문의 복약지도 — 자문 내용"
_ADVICE_SOURCE_ORG = "박영 산부인과"
_ADVICE_SOURCE_URL = "https://app.notion.com/p/3ba0c3b3380580068fa1f32666a8b68c"
_APPROVED_AT = date(2026, 9, 4)
_APPROVED_VERSION = "2026-09-04"

# 승인 당시 KEY-265 정본의 고정 해시. 본문 수정만으로 갱신하지 않는다.
# 변경된 문구는 재검토 후 버전·승인 기록과 함께 명시적으로 갱신해야 한다.
#
# KEY-357: (처음)/(계속) → O/X 축 변경에 맞춰 키를 새 세트 이름으로 갱신했다.
# O 세트는 기존 (처음) 세트의 해시를 그대로 사용한다(본문이 동일하다).
# X 세트 life 는 O 세트와 같은 글이므로 같은 해시 값을 참조한다.
_APPROVED_BODY_HASHES = {
    (
        "자궁내막증 · 비잔 O",
        "caution",
        "2026-09-04",
    ): "27c7cece535c9cbdf79edf469619dcfd411947cea38a26366d6c9ebf326e5262",
    (
        "PCOS · 야즈 O",
        "caution",
        "2026-09-04",
    ): "dd71789145edce33d24f95b8a9590c32e0df36af58f0b8f4a1f1aefe1fb9e5db",
    (
        "자궁내막증 · 비잔 O",
        "medication",
        "2026-09-04",
    ): "c5f3d0944356c1f4cdb842ee3b2b4e5ddb2f5497a3d78fd9e3b18d663929d38c",
    (
        "자궁내막증 · 비잔 O",
        "life",
        "2026-09-04",
    ): "ee109954cde9dcb819ef5a9fadb3d6d453dd121f037e7b85fc6b73ed453fffd6",
    # X 세트 life: 질환 기준이므로 O 세트와 같은 글 → 같은 해시
    (
        "자궁내막증 · 비잔 X",
        "life",
        "2026-09-04",
    ): "ee109954cde9dcb819ef5a9fadb3d6d453dd121f037e7b85fc6b73ed453fffd6",
    (
        "PCOS · 야즈 O",
        "medication",
        "2026-09-04",
    ): "e2013a3fad67639c5853b2217a1ec4e94d7ab1dbd99a63290b67e64f2f8f7875",
    (
        "PCOS · 야즈 O",
        "life",
        "2026-09-04",
    ): "41a196afe2f7eaa9cb526c20f25bf97c5f7ad9cdad92f68fe646bc0bca7017c9",
    # X 세트 life: 질환 기준이므로 O 세트와 같은 글 → 같은 해시
    (
        "PCOS · 야즈 X",
        "life",
        "2026-09-04",
    ): "41a196afe2f7eaa9cb526c20f25bf97c5f7ad9cdad92f68fe646bc0bca7017c9",
}

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
    # KEY-283: 기본값을 두지 않는다. 등록자가 외부 근거 등급인지 전문의 승인
    # 템플릿인지 반드시 판단해 명시해야 한다.
    source_grade: SourceGrade
    source_name: str = _SOURCE_NAME
    source_org: str = _SOURCE_ORG
    source_url: str = ""
    verified_at: date = field(default=_VERIFIED_AT)
    content_version: str = _CONTENT_VERSION
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED

    @property
    def physician_review(self) -> dict[str, str] | None:
        """KEY-265에서 승인된 정본의 검토 기록. 본문 변경 시 재검토가 필요하다."""
        if self.source_grade is not SourceGrade.C or self.content_version != _APPROVED_VERSION:
            return None
        return {
            "reviewer": "박영 산부인과 전문의",
            "hospital": _ADVICE_SOURCE_ORG,
            "reviewed_at": _APPROVED_AT.isoformat(),
            "body_sha256": _APPROVED_BODY_HASHES.get(
                (self.prescription_set_name, self.section_key.value, self.content_version), ""
            ),
        }


# ── 처방 세트 4종 ────────────────────────────────────────────────────────────
# 합성 CSV 에 실제로 등장하는 이름을 그대로 사용한다.
#
# **KEY-357: 처음/계속 축 → 약 처방 여부 O/X 축으로 변경** (팀 회의 결정, 이희진).
# 판독지에 처음인지 계속인지 정보가 없어 스탭이 직접 판단해야 했고,
# 문구 마스터도 두 축이 사실상 같은 글이라 의미 없는 구분이었다.
#
# O: 해당 약(비잔·야즈)이 처방됨 / X: 해당 약 없이 다른 약(진통제 등)만 처방됨
PRESCRIPTION_SETS: tuple[PrescriptionSetRow, ...] = (
    PrescriptionSetRow("자궁내막증 · 비잔 O", SetDisease.ENDOMETRIOSIS),
    PrescriptionSetRow("자궁내막증 · 비잔 X", SetDisease.ENDOMETRIOSIS),
    PrescriptionSetRow("PCOS · 야즈 O", SetDisease.PCOS),
    PrescriptionSetRow("PCOS · 야즈 X", SetDisease.PCOS),
)

# ── 네 갈래 문구 마스터 ──────────────────────────────────────────────────────
# **여기 O 세트 열두 칸은 더 이상 합성이 아니다.** 예전에는 모든 body 에 `[합성]` 을
# 붙여 「지어낸 글」임을 표시했는데, 2026-09-04 에 원장님이 확인한 글로
# 바뀌면서 그 접두어를 걷었다(KEY-265). 출처·승인일·판 번호가 아래 상수에
# 붙어 있고, 그것이 채워져 있어야 생성이 이 글을 쓴다(KEY-180 §4).
#
# KEY-357: (처음)/(계속) 두 세트가 사실상 같은 글이라 O 세트 하나로 통합했다.
# medication·life 는 초진 안내(처음)를 기준으로 통합했다.
#
# ── X 세트 caution·emergency 는 미완성 ───────────────────────────────────────
# 질환 공통 주의·응급 문구는 이희진 검토 확정 후 별도 커밋으로 추가한다.
# 그때까지 X 세트는 medication·life 2 칸만 APPROVED 상태다.
# GUIDE_RAG_ENABLED=true 경로에서 X 세트로 안내문 생성 시 unverified_context 로
# 실패할 수 있으며, 이는 PR 제한사항으로 명시한다.

_BIJAN_CAUTION = (
    "질출혈이 가장 흔해요. 팬티라이너에 묻을 정도로 나왔다 안 나왔다 합니다. 가슴이 단단해지는 "
    "느낌, 몸이 붓는 느낌도 시간이 지나면 좋아져요.\n\n"
    "드물게 기분이 가라앉는 분들이 있어요. 우울감이나 감정 기복이 평소와 다르게 느껴지면 참지 "
    "마시고 알려주세요. 약을 조절하거나 바꿀 수 있어요.\n\n"
    "비잔을 드시면 생리가 없어지는데, 이건 폐경이 아니에요. 호르몬을 일정하게 유지시켜서 생리가 "
    "안 나오게 하는 것뿐이고, 약을 끊으면 다시 돌아옵니다."
)

_BIJAN_EMERGENCY = (
    "한쪽 다리에 심한 통증·부기·발적이 생기거나, "
    "갑작스러운 흉통·호흡 곤란·시야 이상이 나타나면 "
    "즉시 복용을 중단하고 응급실을 방문하세요."
)

_YAZ_CAUTION = (
    "예상치 못한 질출혈이 가장 흔해요. 특히 처음 몇 달 동안 그렇습니다. 대부분 시간이 지나면서 "
    "줄어드니 그러려니 하셔도 괜찮아요.\n\n"
    "약을 한두 알 드시고 구역질·구토가 심하게 나면 다음 방문 때 알려주세요. 약을 드시기 "
    "시작하자마자 온몸에 두드러기가 나는 경우도 알려주세요. 3주 이상 잘 드시다가 두드러기가 "
    "생겼다면 약보다 다른 원인일 가능성이 높지만, 그래도 알려주세요.\n\n"
    "흡연을 하시거나 전조증상이 있는 편두통이 있으시면 미리 꼭 말씀해 주세요."
)

_YAZ_EMERGENCY = (
    "한쪽 다리에 심한 통증·부기·발적, 갑작스러운 흉통, 호흡 곤란, "
    "심한 두통 또는 시야 이상이 나타나면 즉시 복용을 중단하고 응급실을 방문하세요."
)

_YAZ_LIFE = (
    "다낭성난소증후군에서 가장 중요한 것은 수면 습관입니다. 하루 7~8시간, 자기 전 두 "
    "시간은 휴대폰을 보지 않기, 방을 어둡게 하기, 그리고 밤 10시에서 새벽 2시 사이에 "
    "잠들어 계시는 것이 중요해요. 같은 8시간을 자도 시간대에 따라 수면의 질이 크게 "
    "다릅니다.\n\n"
    "배달 음식 용기에서 나오는 물질이 호르몬을 교란할 수 있어 배달 음식은 줄이시는 편이 "
    "좋아요. 채소와 기름기 적은 단백질을 챙겨 드시고, 운동을 곁들이면 인슐린 저항성을 줄이는 "
    "데 도움이 됩니다."
)

# X 세트 medication: 처방 약 종류에 무관한 짧은 약사 복약지도 안내 (SourceGrade.B)
# 전문의 자문이 아니라 일반 안내라 출처를 별도로 둔다 — _ADVICE_SOURCE_NAME 을 쓰면
# test_reseeding_removes_the_wrong_a_label 이 「전문의」 필터로 B 등급 행을 잡아 실패한다.
_X_MEDICATION = "처방된 약의 복용법은 약사 복약지도를 참고하세요."
_X_MED_SOURCE_NAME = "약사 복약지도 일반 안내"
_X_MED_SOURCE_ORG = "박영 산부인과"


DRUG_CAUTION_CONTENTS: tuple[DrugCautionContentRow, ...] = (
    # ── 자궁내막증 · 비잔 O ──────────────────────────────────────────────────
    # KEY-357: 기존 (처음) 세트의 승인 문구를 새 세트 이름으로 재등록.
    # caution·emergency 는 (처음)/(계속) 동일, medication·life 는 (처음) 기준 통합.
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 O",
        section_key=CautionSectionKey.CAUTION,
        body=_BIJAN_CAUTION,
        source_grade=SourceGrade.C,
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 O",
        section_key=CautionSectionKey.EMERGENCY,
        body=_BIJAN_EMERGENCY,
        source_grade=SourceGrade.A,
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/dienogest-emergency",
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 O",
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
        source_grade=SourceGrade.C,
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 O",
        section_key=CautionSectionKey.LIFE,
        body=(
            "비잔은 정해진 기간이 아니라 상태를 보며 이어 가는 약이라, 3~6개월마다 정기 진찰을 "
            "받으시는 것이 중요합니다. 재발 여부를 일찍 알 수 있는 유일한 방법입니다.\n\n"
            "약을 드시고 3~4시간 안에 구토나 설사를 하셨다면 약효가 줄 수 있으니 다음 진료 때 "
            "말씀해 주세요."
        ),
        source_grade=SourceGrade.C,
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # ── 자궁내막증 · 비잔 X ──────────────────────────────────────────────────
    # KEY-357: caution·emergency 는 이희진 검토 확정 후 추가 예정.
    # medication: 약사 복약지도 안내(SourceGrade.B), life: O 세트와 동일.
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 X",
        section_key=CautionSectionKey.MEDICATION,
        body=_X_MEDICATION,
        source_grade=SourceGrade.B,
        source_name=_X_MED_SOURCE_NAME,
        source_org=_X_MED_SOURCE_ORG,
        source_url="",
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 X",
        section_key=CautionSectionKey.LIFE,
        body=(
            "비잔은 정해진 기간이 아니라 상태를 보며 이어 가는 약이라, 3~6개월마다 정기 진찰을 "
            "받으시는 것이 중요합니다. 재발 여부를 일찍 알 수 있는 유일한 방법입니다.\n\n"
            "약을 드시고 3~4시간 안에 구토나 설사를 하셨다면 약효가 줄 수 있으니 다음 진료 때 "
            "말씀해 주세요."
        ),
        source_grade=SourceGrade.C,
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # ── PCOS · 야즈 O ────────────────────────────────────────────────────────
    # KEY-357: 기존 (처음) 세트의 승인 문구를 새 세트 이름으로 재등록.
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 O",
        section_key=CautionSectionKey.CAUTION,
        body=_YAZ_CAUTION,
        source_grade=SourceGrade.C,
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 O",
        section_key=CautionSectionKey.EMERGENCY,
        body=_YAZ_EMERGENCY,
        source_grade=SourceGrade.A,
        source_url="https://nedrug.mfds.go.kr/TEST-ONLY/drsp-ee-emergency",
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 O",
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
        source_grade=SourceGrade.C,
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 O",
        section_key=CautionSectionKey.LIFE,
        body=_YAZ_LIFE,
        source_grade=SourceGrade.C,
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    # ── PCOS · 야즈 X ────────────────────────────────────────────────────────
    # KEY-357: caution·emergency 는 이희진 검토 확정 후 추가 예정.
    # medication: 약사 복약지도 안내(SourceGrade.B), life: O 세트와 동일(_YAZ_LIFE).
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 X",
        section_key=CautionSectionKey.MEDICATION,
        body=_X_MEDICATION,
        source_grade=SourceGrade.B,
        source_name=_X_MED_SOURCE_NAME,
        source_org=_X_MED_SOURCE_ORG,
        source_url="",
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 X",
        section_key=CautionSectionKey.LIFE,
        body=_YAZ_LIFE,
        source_grade=SourceGrade.C,
        source_name=_ADVICE_SOURCE_NAME,
        source_org=_ADVICE_SOURCE_ORG,
        source_url=_ADVICE_SOURCE_URL,
        verified_at=_APPROVED_AT,
        content_version=_APPROVED_VERSION,
    ),
)
