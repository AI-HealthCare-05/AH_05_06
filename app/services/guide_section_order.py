"""안내문 절의 **차례** — KEY-317.

스탭·의사가 승인 전에 절의 차례를 바꾼다. 바꿀 수 있는 것과 못 바꾸는 것을
**여기 한 곳**에서 정한다 — 서버가 검증하고, 화면은 여기서 나온 답을 보여
주기만 한다.

## 왜 서버가 막나

차례를 화면만 막으면 요청을 직접 보내는 것으로 넘어간다. 그러면 🚨 응급
안내가 생활관리 뒤로 갈 수 있고, 환자는 그것을 못 보고 창을 닫는다. 그 문장은
넘겨도 되는 문장이 아니다.

## 정책 — 안전 절은 앉은 자리를 지킨다

    복약지도  0   ← 일반. 남은 자리끼리 섞을 수 있다
    주의사항  1   ← **안전. 못 움직인다**
    응급      2   ← **안전. 못 움직인다** (주의사항 바로 뒤가 고정이다)
    생활지도  3   ← 일반
    문자 설정  4   ← 일반

안전 절의 자리를 그대로 두고 **남은 자리들끼리만** 일반 절을 섞는다. 그래서
「응급은 주의사항 바로 뒤」가 따로 규칙일 필요가 없다 — 둘 다 안 움직이니
저절로 붙어 있다.

절이 빠진 문서(옛 안내문에 `emergency` 가 없는 경우)도 같은 규칙으로 잰다.
**계약 표의 번호가 아니라 그 문서에서 지금 앉아 있는 자리**를 기준으로 보기
때문이다 — 계약 번호로 재면 절 하나가 없는 문서에서 번호가 밀려 멀쩡한 차례가
거절당한다.

2026-09-11 기준 이 정책은 이희진 님 확인 대기 중이다(KEY-317 코멘트).
바꿀 일이 생기면 **`SAFETY_SECTIONS` 한 줄**이다.
"""

from app.core.auth_errors import AuthError as ApiError
from app.models.visits import GuideSection, GuideSectionKey

#: 계약이 정한 기본 차례 — `docs/api/hospital.md` §5. 열거에 적힌 순서 그대로다.
CONTRACT_ORDER: tuple[GuideSectionKey, ...] = tuple(GuideSectionKey)

#: **의료 안전 절.** 사람이 자리를 못 바꾼다.
#:
#: `emergency` 가 여기 있는 까닭은 그 문장이 식약처 기준이라서가 아니라
#: (그것은 `locked` 가 맡는다) **환자가 반드시 마주쳐야 하는 자리**이기
#: 때문이다. 두 관심사를 나눠 둔다 — `locked` 는 글을, 여기는 자리를 지킨다.
SAFETY_SECTIONS: frozenset[GuideSectionKey] = frozenset(
    {
        GuideSectionKey.CAUTION,
        GuideSectionKey.EMERGENCY,
    }
)

#: 감사 기록에 적는 모양 — `medication,caution,emergency,life,messages`.
SEPARATOR = ","


def default_order(key: GuideSectionKey) -> int:
    """계약이 그 절에 준 자리."""
    return CONTRACT_ORDER.index(key)


def as_written(keys: list[GuideSectionKey]) -> str:
    """감사 기록에 남길 한 줄."""
    return SEPARATOR.join(key.value for key in keys)


def current_order(sections: list[GuideSection]) -> list[GuideSectionKey]:
    """그 문서가 **지금** 보이는 차례."""
    ordered = sorted(sections, key=lambda section: (section.display_order, section.guide_section_id))
    return [GuideSectionKey(section.section_key) for section in ordered]


def parse(raw: list[str]) -> list[GuideSectionKey]:
    """받은 이름들을 절 갈래로 옮긴다. 모르는 이름은 `422` 다."""
    try:
        return [GuideSectionKey(name) for name in raw]
    except ValueError as err:
        raise ApiError("SECTION_NOT_FOUND", 422, "그런 항목이 없습니다.") from err


def validate(current: list[GuideSectionKey], wanted: list[GuideSectionKey]) -> None:
    """바꿔도 되는 차례인가. 아니면 그 자리에서 막는다.

    두 가지를 본다.

    ① **그 문서가 가진 절이 하나도 빠지거나 늘지 않았다.** 빠뜨린 채 저장하면
       그 절의 자리가 비고, 늘리면 없는 절이 자리를 차지한다. 같은 절을 두 번
       보내는 것도 여기서 걸린다 — 그대로 저장하면 순번이 겹친다.

    ② **안전 절이 제자리에 있다.** 아래 `SAFETY_SECTIONS` 참고.
    """
    if sorted(wanted, key=lambda key: key.value) != sorted(current, key=lambda key: key.value):
        raise ApiError(
            "SECTION_ORDER_INVALID",
            422,
            "안내문에 있는 항목을 하나씩 모두 보내 주세요.",
        )

    for key in SAFETY_SECTIONS:
        if key not in current:
            continue
        if wanted.index(key) != current.index(key):
            raise ApiError(
                "SECTION_ORDER_INVALID",
                422,
                "주의사항·응급 안내는 자리를 옮길 수 없습니다.",
            )


def movable(current: list[GuideSectionKey]) -> list[GuideSectionKey]:
    """사람이 자리를 바꿀 수 있는 절 — 화면이 [↑][↓] 를 어디에 달지 정할 때 쓴다."""
    return [key for key in current if key not in SAFETY_SECTIONS]
