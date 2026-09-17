"""처방 세트·주의·응급 문구 합성 픽스처 — KEY-165.

합성 데이터 CSV(docs/data/synthetic-patients.csv)에 등장하는 4종 처방 세트와
각 세트의 caution·emergency 마스터 콘텐츠를 정의한다.

**이 파일의 모든 값은 테스트·개발용 합성 데이터다.**
실제 환자정보·운영 비밀값·인증된 처방 원문을 포함하지 않는다.

드러그 콘텐츠 커버리지 — **네 세트 × 네 갈래, 16 행**이 목표다:
  - 자궁내막증 · 비잔 O / 자궁내막증 · 비잔 X
  - PCOS · 야즈 O / PCOS · 야즈 X

  갈래는 복약지도·주의사항·응급·생활지도 넷이다. 16 칸 모두 APPROVED.
  자궁내막증 life 는 ESHRE Guideline 2022 기반(SourceGrade.A),
  서비스 팀 검토 6칸(X medication 2·X caution 2·야즈 emergency 2): SourceGrade.C, 전문의 아님,
  나머지는 전문의 자문(SourceGrade.C).

**KEY-357: 처음/계속 축 → 약 처방 여부 O/X 축으로 변경.**
O 세트는 기존 (처음) 세트의 승인 문구를 세트 이름 기준으로 재등록했다.
X 세트 caution·emergency 는 이희진 검토 확정(2026-09-17).
소제목(■)·응급 문구 교정은 2026-09-17-r2 판으로 갱신.

**판번호(content_version)는 칸마다 따로 명시한다.**
문구를 고친 칸만 새 판을 달고, 안 고친 칸은 이전 검토일·해시를 유지한다.
전역 상수 하나로 올리면 그날 보지 않은 칸도 reviewed_at 이 바뀌어 기록이
왜곡된다 — `_is_physician_reviewed(app/services/drug_caution.py)` 참고.

D-2 는 그 빈 자리에 기대지 않는다. `test_key165_drug_caution.py` 의 D-2 는
없는 세트 이름(`"미등록세트XYZ"`)과 DRAFT 콘텐츠를 테스트 안에서 직접 만들어
쓴다. seed 분포와 무관하게 서므로 이 픽스처를 줄여도 그대로 동작한다.
D-1(정상 생성)만 이 seed 를 그대로 쓴다.
"""

from dataclasses import dataclass, field
from datetime import date

from app.models.catalog import ApprovalStatus, CautionSectionKey, SetDisease, SourceGrade

# ── 출처 메타데이터 ─────────────────────────────────────────────────────────
_ADVICE_SOURCE_NAME = "산부인과 전문의 복약지도 — 자문 내용"
_ADVICE_SOURCE_ORG = "산부인과 전문의"
_ADVICE_SOURCE_URL = "https://app.notion.com/p/3ba0c3b3380580068fa1f32666a8b68c"

# 서비스 팀 검토 6칸 — X medication·X caution·야즈 emergency (전문의 아님, 이희진 확정)
_SVC_SOURCE_NAME = "서비스 팀 안내 문구 — 간호사 검토"
_SVC_SOURCE_ORG = "서비스 팀"
_SVC_MED_SOURCE_URL = "https://app.notion.com/p/3decaf5650aa809da074c68c6ce9cab0"
_SVC_OTHER_SOURCE_URL = "https://app.notion.com/p/3dea59d48d65809a9dc5f043814bc41f"
_SVC_REVIEWER = "서비스 팀장(간호사) 승인"

# 최초 승인 (KEY-265, 2026-09-04)
_APPROVED_AT = date(2026, 9, 4)
_APPROVED_VERSION = "2026-09-04"

# KEY-357 X 세트 확정 + 전체 문구 갱신 승인 (이희진, 2026-09-17)
_APPROVED_AT_2 = date(2026, 9, 17)
_APPROVED_VERSION_2 = "2026-09-17"

# 소제목(■) 추가·응급 문구 교정 재검토 (이희진, 2026-09-17)
_APPROVED_VERSION_3 = "2026-09-17-r2"

# **승인된 버전 집합.** physician_review 가 이것으로 유효성을 확인한다.
_APPROVED_VERSION_SET = frozenset({_APPROVED_VERSION, _APPROVED_VERSION_2, _APPROVED_VERSION_3})

_APPROVED_AT_MAP = {
    _APPROVED_VERSION: _APPROVED_AT,
    _APPROVED_VERSION_2: _APPROVED_AT_2,
    _APPROVED_VERSION_3: _APPROVED_AT_2,
}

# 자궁내막증 생활지도 — ESHRE Guideline 2022 (SourceGrade.A)
_ESHRE_SOURCE_NAME = "ESHRE Guideline: Endometriosis 2022"
_ESHRE_SOURCE_ORG = "European Society of Human Reproduction and Embryology"
_ESHRE_SOURCE_URL = "https://doi.org/10.1093/hropen/hoac009"

# 승인 당시 정본의 고정 해시.
# 키: (세트명, 절, 판번호) — 칸마다 독립적으로 관리한다.
_APPROVED_BODY_HASHES: dict[tuple[str, str, str], str] = {
    # ── 2026-09-04 (최초 승인, KEY-265) — 이후 버전으로 교체됨, 참조용 보존 ───
    (
        "자궁내막증 · 비잔 O",
        "medication",
        "2026-09-04",
    ): "c5f3d0944356c1f4cdb842ee3b2b4e5ddb2f5497a3d78fd9e3b18d663929d38c",
    (
        "PCOS · 야즈 O",
        "medication",
        "2026-09-04",
    ): "e2013a3fad67639c5853b2217a1ec4e94d7ab1dbd99a63290b67e64f2f8f7875",
    # ── 2026-09-17 (KEY-357 X 세트 확정) — 소제목 미포함 초판 ─────────────────
    # bizan emergency: 본문 변경 없으므로 v2 그대로
    (
        "자궁내막증 · 비잔 O",
        "emergency",
        "2026-09-17",
    ): "6bf07e209f5926b6edec89d6213c7b61d1a6a0208042795b9f505436810094ef",
    (
        "자궁내막증 · 비잔 X",
        "emergency",
        "2026-09-17",
    ): "6bf07e209f5926b6edec89d6213c7b61d1a6a0208042795b9f505436810094ef",
    # X 세트 medication: source_name·source_url 변경 + Grade B→C 전환 → r2 판 신규
    (
        "자궁내막증 · 비잔 X",
        "medication",
        "2026-09-17-r2",
    ): "864382e20161b1d75bdb0ef0d9031a435a633b1d304e6f726eba9076affdc406",
    (
        "PCOS · 야즈 X",
        "medication",
        "2026-09-17-r2",
    ): "864382e20161b1d75bdb0ef0d9031a435a633b1d304e6f726eba9076affdc406",
    # ── 2026-09-17-r2 (소제목 추가 · 응급 문구 교정) ─────────────────────────
    (
        "자궁내막증 · 비잔 O",
        "medication",
        "2026-09-17-r2",
    ): "37de427675a60023bca84b204401e30ef7900a8f017b845e785ac741ae826db4",
    (
        "자궁내막증 · 비잔 O",
        "caution",
        "2026-09-17-r2",
    ): "dda4f6a78fc3dc50cd20537832a6d3aab9ec5bcb3f2ceb16d0780794f506fa9c",
    (
        "자궁내막증 · 비잔 O",
        "life",
        "2026-09-17-r2",
    ): "d8df2a3eeb3e52f63dac5fd224af5205d27156cc2c97ce0a3de7120fd94cb845",
    (
        "자궁내막증 · 비잔 X",
        "caution",
        "2026-09-17-r2",
    ): "2b7cd3f089d9e77ab0e5c95046951be022c3e945f5d291acae60ea7fb5f1f803",
    (
        "자궁내막증 · 비잔 X",
        "life",
        "2026-09-17-r2",
    ): "d8df2a3eeb3e52f63dac5fd224af5205d27156cc2c97ce0a3de7120fd94cb845",
    (
        "PCOS · 야즈 O",
        "medication",
        "2026-09-17-r2",
    ): "01c941a3849e49f25140784d155b4802118809b494e2bea26e15deaefa786e2e",
    (
        "PCOS · 야즈 O",
        "caution",
        "2026-09-17-r2",
    ): "77da2c9252448f6e1aace8b58bd0f9ea894595a9ead60ec46a979c5d7f5d4515",
    # 야즈 O emergency: 시야 이상 추가 (기존 X 세트와 같은 본문 → 같은 해시)
    (
        "PCOS · 야즈 O",
        "emergency",
        "2026-09-17-r2",
    ): "514be84fd069bcde415459faf9733a8bd555d29392f3fc1ed94016d25b15b32f",
    (
        "PCOS · 야즈 O",
        "life",
        "2026-09-17-r2",
    ): "e9272c49720e2ee5d2408bda1c5d8fcde10625ccbb41ee147f19e6219ee7e018",
    (
        "PCOS · 야즈 X",
        "caution",
        "2026-09-17-r2",
    ): "ce30c8a3952111adecac807a2e6ca87c6a5b520798df15966cad93a747990773",
    # 야즈 X emergency: 시야 이상 제거 + 마지막 문단 변경
    (
        "PCOS · 야즈 X",
        "emergency",
        "2026-09-17-r2",
    ): "12102c52e68b026818d7227e2c09c2673b7b89aec2ef61f91ca2339c8015c67e",
    (
        "PCOS · 야즈 X",
        "life",
        "2026-09-17-r2",
    ): "e9272c49720e2ee5d2408bda1c5d8fcde10625ccbb41ee147f19e6219ee7e018",
}


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
    source_grade: SourceGrade
    # 판번호는 기본값 없이 칸마다 명시한다.
    content_version: str
    source_name: str = _ADVICE_SOURCE_NAME
    source_org: str = _ADVICE_SOURCE_ORG
    source_url: str = _ADVICE_SOURCE_URL
    # physician_review 의 reviewer 명. 전문의가 아닌 검토자는 명시적으로 지정한다.
    reviewer_name: str = "산부인과 전문의"
    verified_at: date = field(default=_APPROVED_AT_2)
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED

    @property
    def physician_review(self) -> dict[str, str] | None:
        """승인된 정본의 검토 기록. 본문 변경 시 재검토가 필요하다."""
        reviewed_on = _APPROVED_AT_MAP.get(self.content_version)
        if self.source_grade is not SourceGrade.C or reviewed_on is None:
            return None
        return {
            "reviewer": self.reviewer_name,
            "hospital": self.source_org,
            "reviewed_at": reviewed_on.isoformat(),
            "body_sha256": _APPROVED_BODY_HASHES.get(
                (self.prescription_set_name, self.section_key.value, self.content_version), ""
            ),
        }


# ── 처방 세트 4종 ────────────────────────────────────────────────────────────
PRESCRIPTION_SETS: tuple[PrescriptionSetRow, ...] = (
    PrescriptionSetRow("자궁내막증 · 비잔 O", SetDisease.ENDOMETRIOSIS),
    PrescriptionSetRow("자궁내막증 · 비잔 X", SetDisease.ENDOMETRIOSIS),
    PrescriptionSetRow("PCOS · 야즈 O", SetDisease.PCOS),
    PrescriptionSetRow("PCOS · 야즈 X", SetDisease.PCOS),
)

# ── 네 갈래 문구 마스터 ──────────────────────────────────────────────────────
# 16 칸 모두 APPROVED. 판번호는 각 칸에 명시되어 있다.

# ── 자궁내막증 · 비잔 O/X 공통 ───────────────────────────────────────────────

# 비잔 O/X 공통 emergency — 본문 변경 없어 v2 유지
_BIJAN_EMERGENCY = (
    "아랫배·골반 통증과 함께 출혈이 많거나, 심하게 어지럽고 쓰러질 것 같으면 즉시 응급실을 "
    "방문하세요. 의식을 잃거나 숨쉬기 힘들면 119에 도움을 요청하세요.\n\n"
    "한쪽 다리가 갑자기 붓고 아프면 당일 진료받으세요. 여기에 흉통이나 호흡곤란이 동반되면 "
    "즉시 119에 도움을 요청하세요.\n\n"
    "아랫배 통증과 함께 열·오한 또는 구토가 나타나거나, 임신 가능성이 있으면 당일 "
    "의료기관에 연락해 진료받으세요."
)

# 자궁내막증 O/X 공통 생활지도 — ESHRE Guideline 2022 (SourceGrade.A)
_ENDO_LIFE = (
    "자궁내막증은 오랜 기간 관리해 나가는 질환입니다.\n"
    "지금은 증상을 잘 조절하면서 편안한 일상을 유지하는 것이 가장 중요합니다.\n\n"
    "■ 생활 속에서 권장되는 것\n\n"
    "전반적인 건강을 지키는 습관이 도움이 됩니다.\n\n"
    "- 담배는 피우지 않기\n"
    "- 적정 체중 유지하기\n"
    "- 규칙적으로 몸을 움직이기\n"
    "- 과일과 채소를 충분히 드시기\n"
    "- 술은 되도록 적게 드시기\n\n"
    "■ 아직 확실하지 않은 것\n\n"
    "특정 식이요법이나 영양제, 침, 물리치료, 운동요법이 자궁내막증 통증을 줄여 준다는 "
    "근거는 아직 충분하지 않습니다.\n"
    "효과가 없다는 뜻은 아니며, 확실히 도움이 된다고 말씀드리기 어렵다는 의미입니다. "
    "시도해 보고 싶은 방법이 있으시면 먼저 진료받으신 의료진과 상의해 주세요.\n\n"
    "■ 마음 건강도 함께\n\n"
    "통증이 오래 이어지면 마음도 지치기 쉽습니다. 힘드실 때는 혼자 견디지 마시고 의료진에게 "
    "편하게 말씀해 주세요. 일상의 질과 마음 건강을 돌보는 방법을 함께 찾아볼 수 있습니다."
)

# X 세트 medication — 서비스 팀장 승인(Grade C), 전문의 아님
_X_MEDICATION = "처방된 약의 복용법은 약사 복약지도를 참고하세요."

# ── 자궁내막증 · 비잔 O ────────────────────────────────────────────────────

_BIJAN_MEDICATION = (
    "■ 이 약을 복용하는 이유\n\n"
    "자궁내막증을 그냥 두면 염증 물질이 나와서 주변 장기와 들러붙게 만들고, 난소 기능에도 "
    "부담을 줘요. 비잔은 자궁내막증 병변이 더 자라지 못하게 막고 크기를 줄여주는 약이에요.\n\n"
    "■ 복용 방법\n\n"
    "하루 한 번, 매일 같은 시간에 쉬는 기간 없이 계속 드세요. 깜빡하셨다면 생각난 즉시 "
    "드시고, 다음부터는 원래 시간에 드시면 됩니다. 한 번 걸렀다고 처음부터 다시 시작하실 "
    "필요는 없어요.\n\n"
    "통증이 사라졌다고 병변까지 없어진 것은 아니에요. 남아 있으면 계속 염증을 일으켜 유착과 "
    "만성 골반통의 원인이 됩니다. 임의로 중단하지 마시고, 끊을 시기는 진료 때 함께 정해요.\n\n"
    "석 달마다 오실 때 생리통 정도와 생리양을 확인합니다. 보통 1~2년 드신 뒤 쉬어갈 시기를 "
    "함께 봅니다. 해마다 혈액검사로 호르몬 상태도 확인해요.\n\n"
    "■ 복용 안내\n\n"
    "처음 한 달 드신 뒤 내원하시면 부작용을 확인하고, 특별한 부작용이 없으면 이후에는 석 "
    "달분씩 처방해 드립니다."
)

_BIJAN_CAUTION = (
    "■ 흔하고 괜찮은 반응\n\n"
    "질출혈이 가장 흔해요. 팬티라이너에 묻을 정도로 나왔다 안 나왔다 합니다. 가슴이 단단해지는 "
    "느낌, 몸이 붓는 느낌도 시간이 지나면 좋아져요.\n\n"
    "비잔을 드시면 생리가 없어지는데, 이건 폐경이 아니에요. 호르몬을 일정하게 유지시켜서 생리가 "
    "안 나오게 하는 것뿐이고, 약을 끊으면 다시 돌아옵니다.\n\n"
    "■ 진료 시 알려주세요\n\n"
    "드물게 기분이 가라앉는 분들이 있어요. 우울감이나 감정 기복이 평소와 다르게 느껴지면 참지 "
    "마시고 알려주세요. 약의 용량을 조절하거나 바꿀 수 있어요."
)

# ── 자궁내막증 · 비잔 X ────────────────────────────────────────────────────

_BIJAN_X_CAUTION = (
    "■ 진료 시 알려주세요\n\n"
    "생리통이 평소보다 심해지거나, 생리 기간이 아닌 때에도 아랫배·골반 통증이 계속되면 "
    "의료진에게 알려주세요. 통증이 나타난 시기와 정도를 기록해 두시면 진료에 도움이 됩니다.\n\n"
    "생리량이나 출혈 기간이 평소와 달라지거나, 생리 기간이 아닌 때 출혈이 있으면 "
    "진료를 상담해 주세요.\n\n"
    "배변·배뇨 시 통증이나 성관계 시 통증이 새로 생기거나 심해지면 의료진에게 알려주세요."
)

# ── PCOS · 야즈 O/X 공통 ──────────────────────────────────────────────────

# 야즈 O emergency: 시야 이상 포함 (이희진 교정 2026-09-17-r2)
_YAZ_EMERGENCY = (
    "아랫배·골반 통증과 함께 출혈이 많거나, 심하게 어지럽고 쓰러질 것 같으면 즉시 응급실을 "
    "방문하세요. 의식을 잃거나 숨쉬기 힘들면 119에 도움을 요청하세요.\n\n"
    "한쪽 다리가 갑자기 붓고 아프면 당일 진료받으세요. 여기에 흉통이나 호흡곤란, 시야 이상이 "
    "동반되면 즉시 119에 도움을 요청하세요.\n\n"
    "아랫배 통증과 함께 열·오한 또는 구토가 나타나거나, 임신 가능성이 있거나 임신검사 결과가 "
    "양성이면 약을 계속 복용하기 전에 의료진에게 알리고 가능한 빨리 진료를 상담하세요."
)

# 야즈 O/X 공통 생활지도 — 전문의 자문(SourceGrade.C)
_YAZ_LIFE = (
    "■ 생활 속에서 권장되는 것\n\n"
    "다낭성 난소 증후군에서 가장 중요한 것은 수면 습관입니다.\n\n"
    "하루 7~8시간, 자기 전 두 시간은 휴대폰을 보지 않기, 방을 어둡게 하기, 그리고 밤 10시에서 새벽 2시 "
    "사이에 잠들어 계시는 것이 중요해요. 같은 8시간을 자도 시간대에 따라 수면의 질이 크게 "
    "다릅니다.\n\n"
    "배달 음식 용기에서 나오는 물질이 호르몬을 교란할 수 있어 배달 음식은 줄이시는 편이 "
    "좋아요. 채소와 기름기 적은 단백질을 챙겨 드시고, 운동을 곁들이면 인슐린 저항성을 줄이는 "
    "데 도움이 됩니다."
)

# ── PCOS · 야즈 O ─────────────────────────────────────────────────────────

_YAZ_CAUTION = (
    "■ 흔하고 괜찮은 반응\n\n"
    "예상치 못한 질출혈이 가장 흔해요. 특히 처음 몇 달 동안 그렇습니다. 대부분 시간이 지나면서 "
    "줄어드니 그러려니 하셔도 괜찮아요.\n\n"
    "복용 중 구역, 두통, 유방압통이 나타날 수 있으며 대개 호전됩니다.\n\n"
    "■ 진료 시 알려주세요\n\n"
    "약을 한두 알 드시고 구역질·구토가 심하게 나면 다음 방문 때 알려주세요.\n\n"
    "약을 드시기 시작하자마자 온몸에 두드러기가 나는 경우도 알려주세요. 3주 이상 잘 드시다가 "
    "두드러기가 생겼다면 약보다 다른 원인일 가능성이 높지만, 그래도 알려주세요.\n\n"
    "칼륨을 높이는 약(스피로노락톤, ACEI, NSAID 등)을 함께 복용 중이면 반드시 의료진에게 "
    "알려 주세요.\n\n"
    "흡연을 하시거나 전조증상이 있는 편두통이 있으시면 미리 꼭 말씀해 주세요."
)

_YAZ_MEDICATION = (
    "■ 이 약을 복용하는 이유\n\n"
    "검사에서 LH 수치가 FSH보다 높게 나왔고, DHEA-S도 정상 범위보다 높았어요. "
    "몸의 호르몬 신호를 조절하는 곳이 널뛰기를 하고 있다는 뜻이에요. 야즈에는 여성호르몬 성분 "
    "두 가지가 들어 있어서 그 신호를 일정하게 잡아줍니다. 신호가 안정되면 LH 와 "
    "DHEA-S가 서서히 내려가고, 생리 주기와 피부 상태도 함께 좋아져요.\n\n"
    "■ 복용 방법\n\n"
    "생리 주기를 따로 계산하실 필요 없어요. 분홍색 알약을 먼저 다 드시고, 이어서 흰색 "
    "알약을 드세요. 한 판을 다 드시면 쉬는 날 없이 바로 다음 판을 시작합니다. 매일 같은 "
    "시간에 드시는 것이 가장 중요해요.\n\n"
    "깜빡 잊으셨다면 생각난 즉시 한 알 드시고, 그날 정해진 시간에 원래 알약을 그대로 "
    "드세요. 12시간이 넘게 지났거나 이틀 이상 잊으셨다면, 남은 판은 계속 드시되 7일간은 "
    "다른 피임 방법을 함께 사용하시고 병원에 문의해 주세요.\n\n"
    "■ 복용 안내\n\n"
    "다낭성 난소 증후군은 '완치'가 아니라 '관리'하는 상태예요. 혈압이나 체중처럼 꾸준히 "
    "살펴 나갑니다. 증상이 심할 때는 약으로 조절하고, 안정되면 상황을 봐가며 조절해요. "
    "평생 못 끊는 약이라는 뜻이 아니니 부담 갖지 않으셔도 돼요.\n\n"
    "시작하고 넉 달쯤에 혈액검사로 LH·DHEA-S를 다시 봅니다. 수치가 잡혀도 바로 끊지 않고 "
    "보통 1~2년 유지해요. 호르몬이 한 바퀴 도는 데 석 달쯤 걸려서, 두세 바퀴는 지나야 "
    "약을 줄여도 원래대로 돌아가지 않습니다.\n\n"
    "해마다 혈액검사로 간 수치와 난소 기능을 확인합니다."
)

# ── PCOS · 야즈 X ─────────────────────────────────────────────────────────

_PCOS_X_CAUTION = (
    "■ 진료 시 알려주세요\n\n"
    "생리가 오랫동안 없거나, 생리 주기·출혈 양상이 평소와 달라지면 의료진에게 알려주세요. "
    "마지막 생리 시작일과 출혈 기간을 기록해 두시면 진료에 도움이 됩니다.\n\n"
    "여드름·체모 증가·탈모가 새로 생기거나 빠르게 심해지면 진료를 상담해 주세요.\n\n"
    "평소와 다른 심한 갈증이나 잦은 소변이 계속되면 예정된 진료일까지 기다리지 말고, "
    "의료진에게 연락해 진료 시점을 상담해 주세요."
)

# 야즈 X emergency: 시야 이상 없음, 마지막 문단 변경 (이희진 교정 2026-09-17-r2)
_PCOS_X_EMERGENCY = (
    "아랫배·골반 통증과 함께 출혈이 많거나, 심하게 어지럽고 쓰러질 것 같으면 즉시 응급실을 "
    "방문하세요. 의식을 잃거나 숨쉬기 힘들면 119에 도움을 요청하세요.\n\n"
    "한쪽 다리가 갑자기 붓고 아프면 당일 진료받으세요. 여기에 흉통이나 호흡곤란이 동반되면 "
    "즉시 119에 도움을 요청하세요.\n\n"
    "아랫배 통증과 함께 열·오한 또는 구토가 나타나거나, 임신 가능성이 있거나 임신검사 결과가 "
    "양성이면 당일 의료기관에 연락해 진료받으세요."
)


DRUG_CAUTION_CONTENTS: tuple[DrugCautionContentRow, ...] = (
    # ── 자궁내막증 · 비잔 O ──────────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 O",
        section_key=CautionSectionKey.CAUTION,
        body=_BIJAN_CAUTION,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 O",
        section_key=CautionSectionKey.EMERGENCY,
        body=_BIJAN_EMERGENCY,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_2,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 O",
        section_key=CautionSectionKey.MEDICATION,
        body=_BIJAN_MEDICATION,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 O",
        section_key=CautionSectionKey.LIFE,
        body=_ENDO_LIFE,
        source_grade=SourceGrade.A,
        content_version=_APPROVED_VERSION_3,
        source_name=_ESHRE_SOURCE_NAME,
        source_org=_ESHRE_SOURCE_ORG,
        source_url=_ESHRE_SOURCE_URL,
    ),
    # ── 자궁내막증 · 비잔 X ──────────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 X",
        section_key=CautionSectionKey.MEDICATION,
        body=_X_MEDICATION,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
        source_name=_SVC_SOURCE_NAME,
        source_org=_SVC_SOURCE_ORG,
        source_url=_SVC_MED_SOURCE_URL,
        reviewer_name=_SVC_REVIEWER,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 X",
        section_key=CautionSectionKey.CAUTION,
        body=_BIJAN_X_CAUTION,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
        source_name=_SVC_SOURCE_NAME,
        source_org=_SVC_SOURCE_ORG,
        source_url=_SVC_OTHER_SOURCE_URL,
        reviewer_name=_SVC_REVIEWER,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 X",
        section_key=CautionSectionKey.EMERGENCY,
        body=_BIJAN_EMERGENCY,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_2,
    ),
    DrugCautionContentRow(
        prescription_set_name="자궁내막증 · 비잔 X",
        section_key=CautionSectionKey.LIFE,
        body=_ENDO_LIFE,
        source_grade=SourceGrade.A,
        content_version=_APPROVED_VERSION_3,
        source_name=_ESHRE_SOURCE_NAME,
        source_org=_ESHRE_SOURCE_ORG,
        source_url=_ESHRE_SOURCE_URL,
    ),
    # ── PCOS · 야즈 O ────────────────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 O",
        section_key=CautionSectionKey.CAUTION,
        body=_YAZ_CAUTION,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 O",
        section_key=CautionSectionKey.EMERGENCY,
        body=_YAZ_EMERGENCY,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
        source_name=_SVC_SOURCE_NAME,
        source_org=_SVC_SOURCE_ORG,
        source_url=_SVC_OTHER_SOURCE_URL,
        reviewer_name=_SVC_REVIEWER,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 O",
        section_key=CautionSectionKey.MEDICATION,
        body=_YAZ_MEDICATION,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 O",
        section_key=CautionSectionKey.LIFE,
        body=_YAZ_LIFE,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
    ),
    # ── PCOS · 야즈 X ────────────────────────────────────────────────────────
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 X",
        section_key=CautionSectionKey.MEDICATION,
        body=_X_MEDICATION,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
        source_name=_SVC_SOURCE_NAME,
        source_org=_SVC_SOURCE_ORG,
        source_url=_SVC_MED_SOURCE_URL,
        reviewer_name=_SVC_REVIEWER,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 X",
        section_key=CautionSectionKey.CAUTION,
        body=_PCOS_X_CAUTION,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
        source_name=_SVC_SOURCE_NAME,
        source_org=_SVC_SOURCE_ORG,
        source_url=_SVC_OTHER_SOURCE_URL,
        reviewer_name=_SVC_REVIEWER,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 X",
        section_key=CautionSectionKey.EMERGENCY,
        body=_PCOS_X_EMERGENCY,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
        source_name=_SVC_SOURCE_NAME,
        source_org=_SVC_SOURCE_ORG,
        source_url=_SVC_OTHER_SOURCE_URL,
        reviewer_name=_SVC_REVIEWER,
    ),
    DrugCautionContentRow(
        prescription_set_name="PCOS · 야즈 X",
        section_key=CautionSectionKey.LIFE,
        body=_YAZ_LIFE,
        source_grade=SourceGrade.C,
        content_version=_APPROVED_VERSION_3,
    ),
)
