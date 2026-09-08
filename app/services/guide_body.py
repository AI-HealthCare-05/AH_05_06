"""안내문 본문을 짓는 규칙 — 생성과 미리보기가 **같은 것을 부른다**. KEY-258.

## 왜 잎 모듈인가

D2-2 「안내문 고치기」 화면이 보여 주는 글과 실제로 환자에게 나가는 글이
**같아야 한다.** 그것을 지키는 길은 원리상 하나뿐이다 — 두 쪽이 같은 함수를
부르는 것. 「지금은 같다」로는 모자란다. 이 저장소는 그 부류로 이미 여러 번
데었다.

* `guides.py:320` — 「설정 화면이 `guide_copy.py` 로 보여 주는 「원본」과 실제로
  나가는 글이 **갈렸다**」
* `guide_copy.py:212` — 「화면은 그것을 「원본」이라 보여 주고 환자에게는 기본
  한 줄이 나갔다」 (이희진 님 `#214` ③)

`guides.py`(생성)와 `guide_copy.py`(설정 화면)가 서로를 안 import 하도록
**아무것도 안 부르는 잎**에 둔다. 둘 다 이쪽으로 내려온다.

## 여기 있는 것은 전부 순수 함수다

DB 도 시각도 안 본다. 그래야 검사가 두 쪽의 답을 **같은 자리에서** 맞대 볼 수
있다 — 그것이 KEY-258 인수조건 2 를 지키는 유일한 방법이다.
"""

from typing import TYPE_CHECKING

from app.models.catalog import CautionSectionKey

if TYPE_CHECKING:
    from app.models.prescriptions import PrescriptionItem

#: 🚨 응급 문장에는 원장님 문구가 얹히지 않는다 — KEY-150 · KEY-165.
#:
#: 식약처 의약품정보를 근거로 미리 써 둔 문장이라 표현을 다듬는 자리가 아니다.
#: D2-2 도 이 갈래를 `editable=False` 로 잠그고, 생성도 `copies` 를 아예 안
#: 본다. **두 쪽이 같은 이유로 같은 판단을 하므로 여기 한 줄로 적는다** —
#: 두 곳에 흩어져 있으면 한쪽만 열리는 날 조용히 갈린다.
FIXED_SECTIONS = frozenset({CautionSectionKey.EMERGENCY})


def resolved_copy(section_key: CautionSectionKey, copies: dict[CautionSectionKey, str], origin: str) -> str:
    """**지금 환자에게 나갈 글.** 원장님 문구가 있으면 그것, 없으면 원본.

    `origin` 은 「그 세트의 승인 문구, 없으면 기본 문구」까지 이미 풀린 값이다
    — 생성은 `DrugCautionService.approved_content_of(...)` 로, 설정 화면은
    `GuideCopyService._origins()` 로 푸는데 **둘이 같은 문**을 지난다
    (`generation_ready()` + `has_evidence`).

    `copies` 는 **담당 의사 것이 의원 공통을 덮은 뒤**의 한 벌이다. 겹치는
    차례는 부르는 쪽이 정한다 — 생성은 진료의 담당의를 알고, 설정 화면은
    보고 있는 사람을 안다.

    화면 쪽 짝은 `frontend/js/guide-copy-rules.js` 의 `copyShown()` 이다.
    """
    if section_key in FIXED_SECTIONS:
        return origin
    return copies.get(section_key, origin)


def medication_body(items: "list[PrescriptionItem]", guidance: str) -> str:
    """구조화 처방 항목을 환자가 읽는 복약 안내로 옮긴다.

    약명·복용 빈도·기간은 ``PrescriptionItem`` 에 실제로 저장된 값만 쓴다.
    기간이 없는 필요시 약에 다른 약의 기간을 붙이지 않고, 처방 항목 자체가
    없으면 승인된 기본 지도 문장만 내보낸다 — 없는 값을 OCR 원문이나 임의
    문장으로 대신 만들지 않는다(KEY-224).

    **`guides.py` 에서 옮겨 왔다** (KEY-258). 미리보기가 같은 조립을 지나야
    하는데, 생성 모듈 안에 있으면 설정 화면이 그것을 부르려고 생성을 import
    하게 된다.
    """
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        facts = [item.name.strip(), item.frequency.strip()]
        if item.duration_days is not None:
            facts.append(f"{item.duration_days}일분")
        lines.append(f"{index}. {' · '.join(fact for fact in facts if fact)}")

    if not lines:
        return guidance
    return "\n".join(("처방된 복약 정보", *lines, guidance))


def preview_body(section_key: CautionSectionKey, copies: dict[CautionSectionKey, str], origin: str) -> str:
    """**설정 화면이 보여 줄 「실제로 나가는 글」** — KEY-258.

    ## 이것은 근사치가 아니다

    `generate()` 가 **처방 행이 없는 진료**에 대해 내놓는 값과 글자까지 같다.
    복약지도는 문구를 처방 행으로 감싸는데(`medication_body`), 감쌀 행이 없으면
    `if not lines: return guidance` 로 문구가 그대로 나간다.

    설정 화면에는 진료가 없다 — 그러니 **감쌀 행도 없다.** 지어낼 수도 없다:

    * `PrescriptionSetDrug` 에는 **처방일수가 없다.** 그것으로 예시를 만들면
      실제 본문에 있는 「84일분」이 빠진 글을 「실제로 나가는 글」이라 보이게 된다
    * `frontend/js/drug-lines.js` 는 이미 그 화면에 실려 있지만 **줄 모양이
      다르다**(판독 화면 S1-6 의 것). 재사용하면 틀린 글을 보이게 된다

    그래서 **약 목록 자리는 비워 두고, 화면이 그 사실을 말한다.** 없는 것을
    있는 척하지 않는 쪽이 이 저장소의 태도다.
    """
    return medication_body([], resolved_copy(section_key, copies, origin))
