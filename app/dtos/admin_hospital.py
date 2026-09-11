"""어드민 — 의원 정보 (A1-4) 계약. KEY-331.

이 화면이 오래 비어 있는 동안 **그 빈자리가 환자에게 나갔다.** 소진·재진
문자의 `{예약링크}` 를 채울 곳이 없어서 발송 코드가 `{링크}`(그 환자의 안내문
링크)를 그대로 넣었고, 「재진 예약을 잡아주세요: …」를 누른 환자는 예약이
아니라 제 안내문을 다시 열었다. 여기서 그 값을 받는다.

**담는 것은 셋뿐이다.** 사업자번호·대표자·팩스 같은 값은 지금 아무도 안
기다린다 — 칸을 먼저 만들면 「이 값은 어디서 쓰나」에 아무도 답하지 못하고,
관리자는 채워야 할 것처럼 읽는다.

  * `phone` — 환자 화면의 「문의하기」가 거는 번호 (P5-1 · P6-1)
  * `booking_url` — `{예약링크}` 와 「예약하기」가 여는 곳
  * `address` — 문자·안내문에 쓰지 않는다. 관리자가 제 의원을 알아보는 표시다
"""

import re
from typing import Annotated, Self

from pydantic import AfterValidator, model_validator

from app.dtos.base import StrictModel

#: 의원 대표번호. **`validate_phone_number` 를 안 쓴다** — 그것은 `010` 으로
#: 시작하는 휴대폰만 통과시키는데, 의원 대표번호는 대개 `02-123-4567` 같은
#: 유선이다. 그 검사를 재사용하면 관리자가 제 의원 번호를 못 넣는다.
#:
#: 숫자·하이픈만 받고 숫자 아홉에서 열둘까지 본다 — 지역번호(2~4) + 국번 +
#: 번호. 나라 번호(`+82`)는 안 받는다: 환자가 눌러 거는 번호라 국내 표기가
#: 맞고, 둘을 다 받으면 화면마다 다른 모양이 뜬다.
_PHONE = re.compile(r"^\d{2,4}-?\d{3,4}-?\d{4}$")

#: 예약 링크. **`http`/`https` 만이다.** 이 값은 그대로 문자에 실려 환자
#: 휴대폰에서 열린다 — `javascript:` 든 `data:` 든 받아 두면 관리자가 실수로
#: 붙여넣은 것을 우리가 환자에게 배달하는 꼴이 된다. 화이트리스트로 막는다.
_BOOKING_URL = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)

#: 예약 링크 최대 길이. 문자 한 통이 90바이트(EUC-KR)를 넘으면 장문이 되어
#: 단가가 달라지는데(A1-5), 링크 하나가 그 한도를 혼자 먹을 수 있다. 칸
#: 자체는 넉넉히 두고, **너무 길면 문자가 장문이 된다**고 화면이 말한다.
BOOKING_URL_MAX = 500

#: 주소 최대 길이 — `Hospital.address` 칸 길이와 같다. 여기서 안 막으면
#: DB 가 `Data too long` 으로 500 을 낸다.
ADDRESS_MAX = 200


def _clean(value: str | None) -> str | None:
    """앞뒤 공백을 걷고, 빈 문자열은 `None` 으로 접는다.

    「지웠다」를 `""` 로 두면 표에 빈 문자열과 NULL 두 가지 「없음」이 생기고,
    `booking_url or ""` 같은 판정이 둘 중 하나만 본다. 없음은 하나여야 한다.
    """
    if value is None:
        return None
    value = value.strip()
    return value or None


def _phone(value: str | None) -> str | None:
    value = _clean(value)
    if value is not None and not _PHONE.fullmatch(value):
        raise ValueError("의원 전화번호 형식이 아닙니다. 예: 02-123-4567")
    return value


def _booking_url(value: str | None) -> str | None:
    value = _clean(value)
    if value is None:
        return None
    if len(value) > BOOKING_URL_MAX:
        raise ValueError(f"예약 링크는 {BOOKING_URL_MAX}자를 넘을 수 없습니다.")
    if not _BOOKING_URL.fullmatch(value):
        raise ValueError("예약 링크는 http:// 또는 https:// 로 시작해야 합니다.")
    return value


def _address(value: str | None) -> str | None:
    value = _clean(value)
    if value is not None and len(value) > ADDRESS_MAX:
        raise ValueError(f"주소는 {ADDRESS_MAX}자를 넘을 수 없습니다.")
    return value


class HospitalResponse(StrictModel):
    """A1-4 가 그리는 것.

    **이름도 함께 준다.** 화면이 「도로시여성의원의 정보를 고치는 중」임을
    보여야 하는데, 그 이름을 상단 골격에서 따로 가져오면 두 값이 어긋날 수
    있다. 다만 이름은 **여기서 못 고친다** — `HospitalUpdateRequest` 에 칸이
    없다: 의원 이름은 배포 한 판의 정체라 시드가 정하고, 바꾸면 이미 나간
    문자의 `{의원명}` 과 앞으로 나갈 것이 갈린다.
    """

    hospital_id: int
    name: str
    phone: str | None
    address: str | None
    booking_url: str | None


class HospitalUpdateRequest(StrictModel):
    """세 칸 전부를 **매번 함께 보낸다** — PATCH 지만 화면은 부분 갱신을 안 쓴다.

    직원 수정(A1-3)은 「안 보낸 칸은 그대로」인데 여기는 화면이 다르다: 저쪽은
    역할만 · 상태만 고치는 자리가 따로 있고, 이쪽은 세 칸이 한 폼에 함께 있어
    **관리자가 보고 있는 것이 곧 보내려는 전부**다.

    **그래도 서버는 그 약속을 믿지 않는다** — 안 보낸 칸은 손대지 않는다.
    화면 말고 다른 손님(검사 · 스크립트 · 다음 화면)이 칸 하나만 보내는 순간
    나머지 둘이 조용히 사라지면 안 된다. 지우는 것은 **`null` 을 보낸 것**만이다.
    """

    phone: Annotated[str | None, AfterValidator(_phone)] = None
    address: Annotated[str | None, AfterValidator(_address)] = None
    booking_url: Annotated[str | None, AfterValidator(_booking_url)] = None

    @model_validator(mode="after")
    def _at_least_one_key(self) -> Self:
        """**칸 이름 셋 중 하나는 실제로 와야 한다.**

        빈 몸(`{}`)은 세 칸을 다 지우라는 뜻으로도, 아무것도 안 바꾸겠다는
        뜻으로도 읽힌다. 앞으로 읽으면 관리자가 실수로 빈 요청 하나에 예약
        링크를 잃는다 — 그 뒤 소진 문자는 전부 보류된다. 거절한다.
        """
        if not self.model_fields_set:
            raise ValueError("고칠 값을 하나도 보내지 않았습니다.")
        return self
