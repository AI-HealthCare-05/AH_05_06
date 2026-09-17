"""안내 본문의 「■ 소제목」을 카드 제목으로 나누고, 「오늘 진료 요약」을 확정 데이터로 짓는다 — KEY-365.

재는 것은 **환자 화면이 받는 카드 모양**이다(`app/services/patient_guide_view.py`).
스탭 미리보기와 환자 종점이 같은 함수를 부르므로 여기서 한 번 재면 둘 다다
(두 종점의 응답이 실제로 같은지는 `test_key294_preview_payload.py` 가 잰다).
"""

import json
from datetime import date

import pytest

from app.dtos.patient_links import PatientGuideDetailResponse
from app.models.catalog import SetDisease
from app.models.visits import GuideSectionKey
from app.services.guide_generation import ENDOMETRIOSIS_LIFE_TEMPLATE_BODY
from app.services.patient_guide_view import (
    care_of,
    guide_detail_of,
    life_of,
    medication_stat_of,
    split_subheadings,
    visit_summary_of,
)
from app.services.patient_links import PatientGuideData, PatientMedicationData

MEDICATION = PatientMedicationData(
    drug_name="비잔정 2mg",
    short_name="비잔정",
    ingredient_label="성분 · 디에노게스트",
    directions="1일 1회 · 84일분",
    stat_sub="성분 · 디에노게스트 · 1일 1회 · 84일분",
    prescribed=84,
    progress=None,
)

#: KEY-357 이 넣는 모양 그대로 — 소제목 셋, 마지막 소제목은 문단이 둘이다.
MEDICATION_WITH_HEADINGS = (
    "■ 이 약을 복용하는 이유\n"
    "합성 이유 문단이에요.\n\n"
    "■ 복용 방법\n"
    "합성 방법 문단이에요.\n\n"
    "■ 복용 안내\n"
    "합성 안내 첫 문단이에요.\n\n"
    "합성 안내 둘째 문단이에요."
)
CAUTION_WITH_HEADINGS = (
    "■ 흔하고 괜찮은 반응\n합성 흔한 반응 문단이에요.\n\n■ 진료 시 알려주세요\n합성 알려 줄 증상 문단이에요."
)
#: 들여쓰기·끝 줄바꿈까지 그대로 나가야 한다 — `■` 없는 본문은 손대지 않는다.
PLAIN_MEDICATION = "  합성 승인 복약 안내\n\n둘째 줄도 그대로예요.\n"
PLAIN_CAUTION = "합성 승인 주의 안내"
PLAIN_LIFE = "합성 승인 생활관리 안내"
EMERGENCY = "■ 이런 제목이 있어도\n합성 응급 안내는 손대지 않아요."


def guide_data(
    sections: dict[GuideSectionKey, str] | None = None,
    *,
    medication: PatientMedicationData | None = MEDICATION,
    set_disease: SetDisease | None = SetDisease.ENDOMETRIOSIS,
    drug_names: tuple[str, ...] = ("비잔정",),
    disease_name: str | None = "자궁내막증 · 비잔정 복용 중",
) -> PatientGuideData:
    return PatientGuideData(
        visit_date=date(2026, 9, 17),
        clinic_name="합성여성의원",
        disease_name=disease_name,
        patient_name=None,
        medication=medication,
        goals=[],
        sections=sections or {},
        set_disease=set_disease,
        drug_names=drug_names,
    )


def with_headings() -> PatientGuideData:
    return guide_data(
        {
            GuideSectionKey.MEDICATION: MEDICATION_WITH_HEADINGS,
            GuideSectionKey.CAUTION: CAUTION_WITH_HEADINGS,
            GuideSectionKey.EMERGENCY: EMERGENCY,
            GuideSectionKey.LIFE: ENDOMETRIOSIS_LIFE_TEMPLATE_BODY,
        }
    )


def everything_shown(data: PatientGuideData) -> dict[str, list[str]]:
    """화면에 글로 나가는 칸 전부 — 카드 이름 → 그 카드의 글."""
    guide = guide_detail_of(data)
    care = care_of(data)
    life = life_of(data)
    stat = medication_stat_of(data)
    shown: dict[str, list[str]] = {}
    if guide is not None:
        shown["오늘 진료 요약"] = [guide.summary] if guide.summary else []
        shown["이 약을 왜 드시나요"] = list(guide.why)
        shown["약별 복용 방법"] = [guide.how] if guide.how else []
        for block in guide.blocks or []:
            shown[f"복약지도 · {block.t}"] = list(block.p)
    if stat is not None and stat.why:
        shown["현황"] = [stat.why]
    if care is not None:
        for block in care.blocks:
            shown[f"주의사항 · {block.t}"] = list(block.p)
    if life is not None:
        for name, axis in life.axes.items():
            shown[f"생활관리 · {name}"] = list(axis.p)
    return shown


class TestSubheadingsBecomeCardTitles:
    def test_mapped_headings_fill_the_fixed_cards_and_the_rest_get_their_own(self) -> None:
        guide = guide_detail_of(with_headings())

        assert guide is not None
        assert guide.why == ["합성 이유 문단이에요."], "「이 약을 복용하는 이유」는 「이 약을 왜 드시나요」 카드로 간다"
        assert guide.how == "1일 1회 · 84일분\n\n합성 방법 문단이에요.", "「복용 방법」은 처방 용법 아래에 붙는다"
        assert [(block.t, block.p) for block in guide.blocks or []] == [
            ("복용 안내", ["합성 안내 첫 문단이에요.\n\n합성 안내 둘째 문단이에요."]),
        ]

    def test_caution_headings_replace_the_lumped_caution_card(self) -> None:
        care = care_of(with_headings())

        assert care is not None
        assert [(block.t, block.p) for block in care.blocks] == [
            ("흔하고 괜찮은 반응", ["합성 흔한 반응 문단이에요."]),
            ("진료 시 알려주세요", ["합성 알려 줄 증상 문단이에요."]),
        ]

    def test_life_headings_become_axes_in_order(self) -> None:
        """ESHRE 고정 템플릿이 실제로 `■` 를 쓴다 — 그 본문으로 잰다."""
        life = life_of(with_headings())

        assert life is not None
        assert list(life.axes) == [
            "생활관리",
            "생활 속에서 권장되는 것",
            "아직 확실하지 않은 것",
            "마음 건강도 함께 살펴 주세요",
        ]
        assert all(axis.title == name for name, axis in life.axes.items())
        assert life.axes["아직 확실하지 않은 것"].p[0].startswith("특정 식이요법이나 영양제")

    def test_a_heading_is_only_ever_a_title(self) -> None:
        """`■` 문자도, 소제목 문장도 문단 안에 남지 않는다."""
        data = with_headings()
        shown = everything_shown(data)
        headings = [
            "이 약을 복용하는 이유",
            "복용 방법",
            "복용 안내",
            "흔하고 괜찮은 반응",
            "진료 시 알려주세요",
            "생활 속에서 권장되는 것",
            "아직 확실하지 않은 것",
            "마음 건강도 함께 살펴 주세요",
        ]
        for card, texts in shown.items():
            for text in texts:
                assert "■" not in text, f"{card} 문단에 ■ 가 남았다"
                for heading in headings:
                    assert not any(line.strip() == heading for line in text.splitlines()), (
                        f"{card} 문단에 소제목 「{heading}」이 줄로 남았다"
                    )

    def test_no_paragraph_shows_up_in_two_cards(self) -> None:
        seen: dict[str, str] = {}
        for card, texts in everything_shown(with_headings()).items():
            for text in texts:
                for paragraph in (chunk.strip() for chunk in text.split("\n\n")):
                    if not paragraph:
                        continue
                    assert paragraph not in seen, f"「{paragraph}」가 {seen.get(paragraph)} 와 {card} 에 둘 다 나온다"
                    seen[paragraph] = card

    def test_no_card_title_is_repeated_as_a_heading(self) -> None:
        guide = guide_detail_of(with_headings())

        assert guide is not None
        titles = [block.t for block in guide.blocks or []]
        assert "이 약을 복용하는 이유" not in titles
        assert "복용 방법" not in titles

    def test_the_emergency_card_is_untouched(self) -> None:
        """응급 본문은 `■` 가 있어도 나누지 않는다 — 🚨 카드에 제목이 이미 있다."""
        care = care_of(with_headings())

        assert care is not None
        assert care.danger == [EMERGENCY]


class TestBodiesWithoutHeadingsStayAsTheyWere:
    def test_the_medication_body_is_one_why_card_verbatim(self) -> None:
        guide = guide_detail_of(guide_data({GuideSectionKey.MEDICATION: PLAIN_MEDICATION}))

        assert guide is not None
        assert guide.why == [PLAIN_MEDICATION]
        assert guide.how == "1일 1회 · 84일분"
        assert guide.blocks is None

    def test_no_blocks_key_goes_out_for_a_plain_body(self) -> None:
        """환자 종점은 `exclude_none` — 옛 화면이 모르는 키가 생기지 않는다."""
        guide = guide_detail_of(guide_data({GuideSectionKey.MEDICATION: PLAIN_MEDICATION}))

        assert isinstance(guide, PatientGuideDetailResponse)
        assert "blocks" not in guide.model_dump(by_alias=True, exclude_none=True)

    def test_caution_and_life_keep_their_single_card(self) -> None:
        data = guide_data(
            {
                GuideSectionKey.CAUTION: PLAIN_CAUTION,
                GuideSectionKey.EMERGENCY: "합성 승인 응급 안내",
                GuideSectionKey.LIFE: PLAIN_LIFE,
            }
        )

        care = care_of(data)
        life = life_of(data)

        assert care is not None and life is not None
        assert care.model_dump(exclude_none=True) == {
            "blocks": [{"t": "주의사항", "p": [PLAIN_CAUTION]}],
            "danger": ["합성 승인 응급 안내"],
        }
        assert life.model_dump(exclude_none=True) == {
            "sub": "자궁내막증 · 비잔정 복용 중",
            "challenges": [],
            "axes": {"생활관리": {"title": "생활관리", "p": [PLAIN_LIFE]}},
        }

    def test_a_mid_sentence_square_is_body_text(self) -> None:
        body = "합성 문장 ■ 가운데에 있는 네모"

        assert [(part.title, part.text) for part in split_subheadings(body)] == [(None, body)]

    def test_no_sections_no_cards(self) -> None:
        data = guide_data({})

        assert care_of(data) is None
        assert life_of(guide_data({}, disease_name=None)) is None


class TestSplittingRules:
    def test_text_before_the_first_heading_keeps_the_default_card(self) -> None:
        data = guide_data(
            {
                GuideSectionKey.MEDICATION: "합성 머리 문단이에요.\n\n■ 복용 안내\n합성 안내예요.",
                GuideSectionKey.CAUTION: "합성 머리 주의예요.\n\n■ 흔하고 괜찮은 반응\n합성 반응이에요.",
            }
        )

        guide = guide_detail_of(data)
        care = care_of(data)

        assert guide is not None and care is not None
        assert guide.why == ["합성 머리 문단이에요."]
        assert [block.t for block in care.blocks] == ["주의사항", "흔하고 괜찮은 반응"]

    def test_a_heading_with_nothing_under_it_makes_no_card(self) -> None:
        care = care_of(guide_data({GuideSectionKey.CAUTION: "■ 빈 소제목\n\n■ 진료 시 알려주세요\n합성 내용이에요."}))

        assert care is not None
        assert [block.t for block in care.blocks] == ["진료 시 알려주세요"]

    def test_the_same_heading_twice_is_one_card(self) -> None:
        care = care_of(guide_data({GuideSectionKey.CAUTION: "■ 가\n하나\n\n■ 나\n둘\n\n■ 가\n셋"}))

        assert care is not None
        assert [(block.t, block.p) for block in care.blocks] == [("가", ["하나", "셋"]), ("나", ["둘"])]

    def test_heading_spacing_and_indentation_do_not_matter(self) -> None:
        guide = guide_detail_of(
            guide_data({GuideSectionKey.MEDICATION: "  ■   복용    방법  \n    합성 방법이에요.\n"})
        )

        assert guide is not None
        assert guide.how == "1일 1회 · 84일분\n\n합성 방법이에요."
        assert guide.blocks is None


class TestTodaysSummary:
    @pytest.mark.parametrize(
        ("disease", "drugs", "expected"),
        [
            (SetDisease.ENDOMETRIOSIS, (), "자궁내막증으로 진료받으셨어요."),
            (SetDisease.ENDOMETRIOSIS, ("비잔정",), "자궁내막증으로 진료받으셨고, 비잔정을 처방받으셨어요."),
            (SetDisease.PCOS, ("야즈",), "다낭성 난소 증후군으로 진료받으셨고, 야즈를 처방받으셨어요."),
            (
                SetDisease.ENDOMETRIOSIS,
                ("비잔정", "진통제"),
                "자궁내막증으로 진료받으셨고, 비잔정 외 1개를 처방받으셨어요.",
            ),
            (
                SetDisease.PCOS,
                ("야즈정", "록소펜정", "진통제"),
                "다낭성 난소 증후군으로 진료받으셨고, 야즈정 외 2개를 처방받으셨어요.",
            ),
        ],
    )
    def test_the_sentence_is_built_from_the_set_and_the_confirmed_drugs(
        self, disease: SetDisease, drugs: tuple[str, ...], expected: str
    ) -> None:
        assert visit_summary_of(guide_data(set_disease=disease, drug_names=drugs)) == expected

    @pytest.mark.parametrize(
        ("drug", "particle"),
        [("록소펜 60", "을"), ("타이레놀 2", "를"), ("Visanne", "을(를)")],
    )
    def test_the_object_particle_follows_how_the_name_is_read(self, drug: str, particle: str) -> None:
        summary = visit_summary_of(guide_data(drug_names=(drug,)))

        assert summary == f"자궁내막증으로 진료받으셨고, {drug}{particle} 처방받으셨어요."

    def test_no_prescription_set_means_no_summary_card(self) -> None:
        data = guide_data({GuideSectionKey.MEDICATION: MEDICATION_WITH_HEADINGS}, set_disease=None)

        guide = guide_detail_of(data)

        assert guide is not None
        assert guide.summary is None
        assert "summary" not in guide.model_dump(exclude_none=True)

    def test_the_summary_carries_no_guide_body(self) -> None:
        guide = guide_detail_of(guide_data({GuideSectionKey.MEDICATION: PLAIN_MEDICATION}))

        assert guide is not None
        assert guide.summary == "자궁내막증으로 진료받으셨고, 비잔정을 처방받으셨어요."
        assert PLAIN_MEDICATION.splitlines()[0] not in (guide.summary or "")

    def test_a_set_alone_still_raises_the_summary_card(self) -> None:
        guide = guide_detail_of(guide_data({}, medication=None, drug_names=()))

        assert guide is not None
        assert guide.model_dump(exclude_none=True) == {
            "summary": "자궁내막증으로 진료받으셨어요.",
            "goals": [],
            "why": [],
        }

    def test_nothing_at_all_is_no_guide(self) -> None:
        assert guide_detail_of(guide_data({}, medication=None, set_disease=None, drug_names=())) is None


class TestStatusTab:
    def test_the_status_card_no_longer_repeats_the_guide_body(self) -> None:
        stat = medication_stat_of(guide_data({GuideSectionKey.MEDICATION: PLAIN_MEDICATION}))

        assert stat is not None
        assert stat.why is None
        assert PLAIN_MEDICATION not in json.dumps(stat.model_dump(), ensure_ascii=False)
