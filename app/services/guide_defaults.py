"""안내문 갈래별 **기본 문구** — 승인된 세트별 문구가 없을 때 쓰는 글.

한동안 이 문장들이 `guides.py` 안에 박혀 있었다. 그래서 설정 화면(D2-2)이
「원본」으로 보여 줄 것이 없었고, 복약지도·생활지도는 **고칠 자리 자체가
없었다** — 원문 D2-2 는 넷 다 [수정] 이라 적어 두었는데도.

여기 모아 두면 두 곳이 같은 글을 본다:

    안내문 생성  `guides.py`        세트별 승인 문구가 없을 때 이 글로 만든다
    설정 화면    `guide_copy.py`    「원본」 칸에 이 글을 보인다

**두 곳이 정말 같은 글을 봐야 한다.** 한동안 `guides.py` 가 이 모듈을 쓰지
않고 제 것을 따로 들고 있었다. 셋은 우연히 같았고 복약지도만 달랐는데, 그
바람에 설정 화면이 「원본」이라며 **실제로 나가지 않는 글**을 보였다.

**이기는 차례는 부르는 쪽이 정한다** — 고친 문구 → 세트별 승인 문구 → 여기.
"""

from app.models.catalog import CautionSectionKey

#: 복약지도는 **지도 문장만** 여기 둔다. 안내문에는 이 앞에 그 진료의
#: 「확정된 항목: …」 한 줄이 붙는데, 그것은 진료마다 다른 사실이라 기본
#: 문구가 될 수 없다. **설정에서 고치는 것도 이 문장이다** — 진료별 줄은
#: 고쳐도 남는다.
MEDICATION = "복약 지시에 따라 정해진 시간에 복용해 주세요."

CAUTION = (
    "[합성 주의 안내]\n복용 중 의사 또는 약사에게 미리 안내받지 않은 증상이나 "
    "불편감이 나타나면 의료진에게 알려 주세요.\n미리 안내받은 증상이라도 심해지거나 "
    "계속되면 알려 주세요."
)

#: 🚨 누구도 못 고친다 (KEY-150). 설정 화면에도 「수정 불가」로 뜬다.
EMERGENCY = "처방약 복용 중 두드러기, 호흡 곤란, 심한 복통이 생기면 즉시 복용을 중단하고 응급실을 방문하세요."

LIFE = "처방 기간 중 음주는 피해 주세요. 충분한 수분 섭취와 규칙적인 수면을 유지해 주세요."

#: 사람이 **문구를 고칠 수 있는** 갈래. 응급만 빠진다 — `locked=True` 로
#: 누구도 못 고치는 글이다(KEY-150).
#:
#: 이 목록이 여기 있는 까닭: 설정(`guide_copy.py`)과 안내 생성(`guides.py`)이
#: **같은 목록을 봐야 한다.** 한쪽만 넓히면 「고칠 수 있는데 안 나가는」 갈래가
#: 생긴다 — 실제로 그렇게 됐다. 설정이 셋으로 넓혔는데 생성은 `caution` 하나만
#: 읽고 있어서, 복약지도·생활지도를 고치면 저장은 되고 환자에게는 안 갔다.
EDITABLE_SECTIONS = (
    CautionSectionKey.MEDICATION,
    CautionSectionKey.CAUTION,
    CautionSectionKey.LIFE,
)

BY_SECTION: dict[CautionSectionKey, str] = {
    CautionSectionKey.MEDICATION: MEDICATION,
    CautionSectionKey.CAUTION: CAUTION,
    CautionSectionKey.EMERGENCY: EMERGENCY,
    CautionSectionKey.LIFE: LIFE,
}
