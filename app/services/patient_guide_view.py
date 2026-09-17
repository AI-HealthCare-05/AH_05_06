"""환자 화면이 받는 파생을 **한 곳에서** 짓는다 — KEY-294.

스탭·의사의 「환자 화면 미리보기」(`GET /visits/{id}/guide`)와 환자
종점(`GET /p/{token}`)이 같은 카드를 그린다. 두 곳에서 따로 지으면 미리보기가
「환자가 받는 그대로」라고 적어 놓고 다른 것을 보이게 된다 — KEY-286 이
없애려던 바로 그 거짓이다.

여기 있는 것은 **모양을 바꾸는 일**뿐이다. 값을 읽어 오는 것은
`PatientLinkService.build_patient_guide_data()` 하나이고, 승인·만료 게이트는
부르는 쪽이 각자 친다 — 환자는 승인된 것만 보고, 스탭은 승인 전에도 본다.

## 「■ 소제목」 — KEY-365

승인 문구 본문에 `■ 소제목` 줄이 있으면 그 줄에서 나눠 **카드 제목**으로 쓴다
(표기는 ESHRE 생활관리 템플릿, `app/services/guide_generation.py`). 소제목 줄
자체는 문단으로 내보내지 않는다. `■` 이 없는 본문(RAG 생성문, 의사 수정 문구,
옛 안내문)은 **손대지 않고** 예전처럼 카드 하나로 보낸다.
"""

import re
import textwrap
from dataclasses import dataclass

from app.dtos.patient_links import (
    PatientCareBlockResponse,
    PatientCareResponse,
    PatientGuideDetailResponse,
    PatientGuideDrugResponse,
    PatientGuideGoalResponse,
    PatientLifeAxisResponse,
    PatientLifeResponse,
    PatientMedicationStatResponse,
)
from app.models.catalog import SetDisease
from app.models.visits import GuideSectionKey
from app.services.patient_links import PatientGuideData

#: 줄 맨 앞의 `■` 만 소제목이다. 문장 가운데의 `■` 는 본문이다.
_SUBHEADING = re.compile(r"^[ \t]*■[ \t]*(?P<title>\S[^\n]*?)[ \t]*$", re.MULTILINE)

#: 고정 카드와 짝이 있는 복약지도 소제목. 그 카드 제목이 이미 화면에 있으므로
#: 소제목은 제목으로 안 쓰고 문단만 그 카드에 넣는다.
_MEDICATION_WHY = "이 약을 복용하는 이유"  # → 「이 약을 왜 드시나요」
_MEDICATION_HOW = "복용 방법"  # → 「약별 복용 방법」 (처방 용법 아래)

#: 소제목 없는 앞부분이 들어갈 카드 — `■` 없는 본문이 예전에 들어가던 자리다.
_CAUTION_CARD = "주의사항"
_LIFE_AXIS = "생활관리"

#: 「오늘 진료 요약」의 질환명. 처방 세트 카탈로그의 질환이다(확정 진단 아님).
_DISEASE_LABELS: dict[SetDisease, str] = {
    SetDisease.ENDOMETRIOSIS: "자궁내막증",
    SetDisease.PCOS: "다낭성 난소 증후군",
}

#: 숫자로 끝나는 이름의 받침 — 영·일·이·삼·사·오·육·칠·팔·구.
_DIGIT_FINALS = {"0": 21, "1": 8, "2": 0, "3": 16, "4": 0, "5": 0, "6": 1, "7": 8, "8": 8, "9": 0}
_RIEUL = 8


@dataclass(frozen=True, slots=True)
class BodyPart:
    """본문 한 토막. `title` 이 `None` 이면 첫 소제목 앞의 글이다."""

    title: str | None
    text: str


def split_subheadings(body: str | None) -> list[BodyPart]:
    """본문을 `■` 소제목 줄에서 나눈다.

    - `■` 가 없으면 본문을 **그대로** 한 토막으로 준다 — 공백 하나 안 건드린다.
    - 내용이 빈 토막(소제목만 있고 문단이 없는 것)은 버린다. 빈 카드를 안 세운다.
    """
    if not body:
        return []
    matches = list(_SUBHEADING.finditer(body))
    if not matches:
        return [BodyPart(title=None, text=body)]

    parts: list[BodyPart] = []
    lead = _clean(body[: matches[0].start()])
    if lead:
        parts.append(BodyPart(title=None, text=lead))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        text = _clean(body[match.end() : end])
        if text:
            parts.append(BodyPart(title=" ".join(match.group("title").split()), text=text))
    return parts


def _clean(text: str) -> str:
    return textwrap.dedent(text).strip()


def _cards(parts: list[BodyPart], *, untitled: str) -> dict[str, list[str]]:
    """제목별로 문단을 모은다. 같은 제목이 두 번 나와도 카드는 하나다."""
    cards: dict[str, list[str]] = {}
    for part in parts:
        cards.setdefault(part.title or untitled, []).append(part.text)
    return cards


def _final_consonant(word: str) -> int | None:
    """마지막 글자의 받침 번호(0 = 받침 없음). 읽는 법을 모르면 `None`."""
    last = word.rstrip()[-1:]
    if "가" <= last <= "힣":
        return (ord(last) - ord("가")) % 28
    return _DIGIT_FINALS.get(last)


def _object_particle(word: str) -> str:
    final = _final_consonant(word)
    if final is None:
        return "을(를)"
    return "를" if final == 0 else "을"


def _direction_particle(word: str) -> str:
    final = _final_consonant(word)
    if final is None:
        return "(으)로"
    return "로" if final in (0, _RIEUL) else "으로"


def visit_summary_of(data: PatientGuideData) -> str | None:
    """「오늘 진료 요약」 — 확정 데이터만으로 짓는 고정 문장 (KEY-365).

    안내 본문을 넣지 않는다. 질환명은 처방 세트의 질환, 약 이름은 확정된 처방
    항목에서만 온다. 처방 목적·효과 같은 의료 설명은 붙이지 않는다.
    처방 세트를 못 찾으면 `None` — 요약 카드가 안 선다.
    """
    if data.set_disease is None:
        return None
    disease = _DISEASE_LABELS[data.set_disease]
    visited = f"{disease}{_direction_particle(disease)} 진료받으셨"
    names = data.drug_names
    if not names:
        return f"{visited}어요."
    drugs = names[0] if len(names) == 1 else f"{names[0]} 외 {len(names) - 1}개"
    return f"{visited}고, {drugs}{_object_particle(drugs)} 처방받으셨어요."


def medication_stat_of(data: PatientGuideData) -> PatientMedicationStatResponse | None:
    """현황(P1)의 복약 진행 카드. 처방이 없으면 카드가 아예 안 선다.

    `why` 는 비운다(KEY-365). 복약지도 본문은 「이 약을 왜 드시나요」에 있다 —
    여기 또 실으면 같은 문단이 두 탭에 나온다.
    """
    medication = data.medication
    if medication is None:
        return None

    progress = medication.progress
    return PatientMedicationStatResponse(
        drug_name=medication.drug_name,
        drug_sub=medication.stat_sub,
        prescribed=medication.prescribed,
        day_on=progress.day_on if progress is not None else None,
        remaining=progress.remaining if progress is not None else None,
        pct=progress.pct if progress is not None else None,
        out=(
            f"ⓘ {progress.depletion_date.month}월 {progress.depletion_date.day}일경 약이 소진돼요"
            if progress is not None
            else None
        ),
        why=None,
    )


def guide_detail_of(data: PatientGuideData) -> PatientGuideDetailResponse | None:
    """복약지도(P2)의 카드들 — 오늘 진료 요약 · 처방받은 약 · 왜 드시나요 · 복용 방법 · 소제목 카드.

    **값이 없는 카드는 안 세운다.** 환자 렌더러가 `if (g.drug)` · `if (g.how)` ·
    `if (g.next)` 로 그렇게 하므로, 여기서 빈 껍데기를 만들면 미리보기만 환자와
    달라진다.
    """
    medication = data.medication
    summary = visit_summary_of(data)
    why: list[str] = []
    how: list[str] = []
    blocks: list[PatientCareBlockResponse] = []
    for title, texts in _cards(split_subheadings(data.sections.get(GuideSectionKey.MEDICATION)), untitled="").items():
        if title in ("", _MEDICATION_WHY):
            why.extend(texts)
        elif title == _MEDICATION_HOW:
            how.extend(texts)
        else:
            blocks.append(PatientCareBlockResponse(t=title, p=texts))

    if not why and not how and not blocks and medication is None and not data.goals and summary is None:
        return None

    directions = medication.directions if medication is not None else None
    return PatientGuideDetailResponse(
        summary=summary,
        goals=[
            PatientGuideGoalResponse(
                n=goal.name,
                now=goal.current,
                t=goal.target,
                has_chart=goal.has_chart,
                range_label=goal.range_label,
            )
            for goal in data.goals
        ],
        drug=(
            PatientGuideDrugResponse(
                n=medication.drug_name,
                s=medication.ingredient_label,
                d=medication.directions,
            )
            if medication is not None
            else None
        ),
        why=why,
        how="\n\n".join(part for part in (directions, *how) if part) or None,
        blocks=blocks or None,
        # `messages`는 병원 안내/발송 행정 문구다. 전용 재진 계획 소스가
        # 생기기 전에는 P2의 `next`로 의미를 바꿔 내보내지 않는다.
        next=None,
    )


def care_of(data: PatientGuideData) -> PatientCareResponse | None:
    """주의사항(P3). 소제목마다 카드 하나, 응급 본문은 🚨 카드에 **그대로** 둔다."""
    caution_body = data.sections.get(GuideSectionKey.CAUTION)
    emergency_body = data.sections.get(GuideSectionKey.EMERGENCY)
    if not caution_body and not emergency_body:
        return None
    return PatientCareResponse(
        blocks=[
            PatientCareBlockResponse(t=title, p=texts)
            for title, texts in _cards(split_subheadings(caution_body), untitled=_CAUTION_CARD).items()
        ],
        danger=[emergency_body] if emergency_body else [],
        # 일반 병원 안내를 증상별 문의 기준으로 오해시키지 않는다.
        ask=None,
    )


def life_of(data: PatientGuideData) -> PatientLifeResponse | None:
    """생활관리(P4). 소제목마다 칩 하나 — 환자 화면이 칩으로 카드를 고른다."""
    life_body = data.sections.get(GuideSectionKey.LIFE)
    if not life_body and not data.disease_name:
        return None
    return PatientLifeResponse(
        sub=data.disease_name,
        axes={
            title: PatientLifeAxisResponse(title=title, p=texts)
            for title, texts in _cards(split_subheadings(life_body), untitled=_LIFE_AXIS).items()
        },
    )
