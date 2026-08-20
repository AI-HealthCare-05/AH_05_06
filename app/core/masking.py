"""로그·응답에서 가려야 할 것 — KEY-11.

`AGENTS.md` 규칙이다. **실제 환자정보, 비밀번호, API 키, JWT·OTP·환자 링크 토큰을
코드·화면·로그·커밋에 남기지 않는다.**

사람이 기억해서 지키게 두지 않는다. `app/core/logger.py`가 이 모듈을 로깅 필터로
붙여서, **어떤 로거로 무엇을 찍든 여기를 거친다.** 잊어도 걸린다.

가리는 방법이 둘이다
------------------
**완전히 지운다** — 토큰 · 비밀번호 · OTP. 남겨 봐야 쓸 데가 없고, 새면 그대로 열쇠다.
**일부만 남긴다** — 전화번호. 뒤 4자리는 남긴다. 그래야 어느 환자 건인지 추적하면서도
전체 번호가 로그에 쌓이지 않는다. 화면 규칙(`P1-1`의 `010-****-7788`)과 같은 모양이다.

여기서 안 하는 것
----------------
화면에 무엇을 보여줄지는 화면 티켓이 정한다 — 의료진 화면은 전화번호를 전체로 쓴다.
이 모듈은 **로그와 오류 응답**만 맡는다.
"""

import re

REDACTED = "[REDACTED]"

#: 값이 어떤 이름으로 불리든 가린다. JSON · 쿼리스트링 · 파이썬 repr 을 함께 훑는다.
#: `password` 하나만 잡으면 `hashed_password` · `current_password` 를 놓친다.
#:
#: `code` 는 여기 없다 — 접두사를 허용하는 구조라 `status_code` · `error_code` ·
#: **`diagnosis_code`** 까지 삼킨다. 진단 코드가 로그에서 사라지면 추적이 안 된다.
#: OTP 의 `code` 는 아래 `OTP_CODE` 가 **여섯 자리 숫자일 때만** 따로 잡는다.
SECRET_KEYS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "otp",
    "refresh_token",
    "access_token",
)

_KEY_ALTERNATION = "|".join(re.escape(k) for k in SECRET_KEYS)

#: `"password": "..."` · `password=...` · `password: ...` 를 모두 잡는다.
#: 키 이름 앞뒤에 다른 글자가 붙어도(`hashed_password`) 걸리도록 경계를 느슨하게 둔다.
KEYED_SECRET = re.compile(
    rf"""
    (?P<key>["']?[\w.]*(?:{_KEY_ALTERNATION})["']?)      # 키 (앞에 hashed_ 같은 접두사 허용)
    (?P<sep>\s*[:=]\s*)                                   # : 또는 =
    (?P<quote>["']?)                                      # 값을 감싼 따옴표(있을 수도)
    (?P<value>[^\s,;&}}\]"']+)                            # 값
    (?P=quote)
    """,
    re.IGNORECASE | re.VERBOSE,
)

#: JWT — 헤더.페이로드.서명. 셋 다 base64url 이고 헤더는 늘 `eyJ` 로 시작한다.
JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")

#: `code` 라는 이름은 흔하다. OTP 일 때만 가린다 — **값이 정확히 여섯 자리 숫자**.
#: 그러면 `status_code=200`(세 자리) · `error_code=OTP_LOCKED`(문자) 는 남는다.
OTP_CODE = re.compile(r"""(?P<key>["']?\w*code["']?\s*[:=]\s*)(?P<quote>["']?)\d{6}(?P=quote)""", re.IGNORECASE)

#: 환자 링크 토큰 — `secrets.token_urlsafe(32)` 는 **정확히 43자** base64url 이다.
#:
#: 32자로 잡았더니 커밋 SHA(40자 hex) 와 요청 ID 까지 삼켰다. 그래서
#:   · 길이를 43자 이상으로 올리고
#:   · **hex 로만 된 것은 제외한다** — 커밋 SHA · MD5 · SHA-256 이 전부 hex 다
#: 실제 토큰은 대소문자와 `-` `_` 가 섞여 hex 가 될 수 없다.
URLSAFE_TOKEN = re.compile(r"\b(?![0-9a-fA-F]{43,}\b)[A-Za-z0-9_-]{43,}\b")

#: 휴대폰 — 하이픈이 있든 없든. 가운데 넷만 가리고 뒤 넷은 남긴다.
PHONE = re.compile(r"\b(01[016-9])[-.\s]?(\d{3,4})[-.\s]?(\d{4})\b")

#: 주민등록번호 — 우리는 수집하지 않는다. 그래도 어딘가로 흘러들면 로그에서 지운다.
RRN = re.compile(r"\b(\d{6})[-\s]?([1-4]\d{6})\b")


def mask_phone(value: str) -> str:
    """`010-1234-5678` → `010-****-5678`.

    뒤 4자리를 남기는 것은 화면 규칙과 같다. 로그에서도 「어느 환자 건인가」는
    따라갈 수 있어야 장애를 추적한다.
    """
    return PHONE.sub(lambda m: f"{m.group(1)}-****-{m.group(3)}", value)


def _mask_keyed(match: re.Match[str]) -> str:
    return f"{match.group('key')}{match.group('sep')}{match.group('quote')}{REDACTED}{match.group('quote')}"


def scrub(text: str) -> str:
    """로그 한 줄에서 가려야 할 것을 모두 가린다.

    순서가 중요하다.
    1. 키가 붙은 값(`password=...`)을 먼저 — 값이 짧아도 키를 보고 안다
    2. `code` 는 여섯 자리 숫자일 때만 — OTP 와 상태·진단 코드를 가른다
    3. JWT · 주민번호처럼 모양이 뚜렷한 것
    4. 긴 base64url 토큰 — 가장 넓게 걸리므로 마지막
    5. 전화번호는 지우지 않고 가운데만 덮는다
    """
    text = KEYED_SECRET.sub(_mask_keyed, text)
    text = OTP_CODE.sub(lambda m: f"{m.group('key')}{m.group('quote')}{REDACTED}{m.group('quote')}", text)
    text = JWT.sub(REDACTED, text)
    text = RRN.sub(lambda m: f"{m.group(1)}-{'*' * 7}", text)
    text = URLSAFE_TOKEN.sub(REDACTED, text)
    return mask_phone(text)
