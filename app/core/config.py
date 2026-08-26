import os
import re
import uuid
import zoneinfo
from dataclasses import field
from enum import StrEnum
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic.types import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


# 예시 파일이 「여기에 무엇을 넣는지」 알려 주려고 쓰는 자리표시자 모양.
#
# **이 정의는 여기 하나뿐이다.** 예전에는 검증기·배포 검사·비밀 검사가 각자
# 적어 두고 있었고, 실제로 서로 어긋나 있었다 — 한쪽은 `changeme` 만 알고
# 다른 쪽은 `change-me` 만 알았다. `sed_inplace` 가 복제돼 양쪽에 같은 버그를
# 남긴 것과 같은 모양이다 (이희진 님 `#133` 리뷰).
PLACEHOLDER = re.compile(r"^(your[-_]|change[-_]?me|<|xxx+|\.\.\.|example)", re.IGNORECASE)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    ENV: Env = Env.LOCAL
    SECRET_KEY: str = f"default-secret-key{uuid.uuid4().hex}"
    TIMEZONE: zoneinfo.ZoneInfo = field(default_factory=lambda: zoneinfo.ZoneInfo("Asia/Seoul"))
    TEMPLATE_DIR: str = os.path.join(Path(__file__).resolve().parent.parent, "templates")

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    # 기본값에 실제 비밀번호를 박지 않는다. 박으면 공개 저장소에 공유 비밀이
    # 하나 생기고, `.env` 를 안 만든 사람이 그 값으로 조용히 붙는다. 예전에는
    # 이력에 새어 나간 값이 여기 있었다 (KEY-110).
    #
    # 빈 값을 기본으로 두되 아래 검증기가 막는다 — 비워 둔 채로는 못 뜬다.
    DB_PASSWORD: str = ""
    DB_NAME: str = "ai_health"
    DB_CONNECT_TIMEOUT: int = 5
    DB_CONNECTION_POOL_MAXSIZE: int = 10

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # 비워 두면 쿠키가 **그 호스트에만** 붙는다(host-only). 이게 안전한 기본값이다.
    # 값을 박아 두면 다른 호스트에서 브라우저가 쿠키를 통째로 버려서
    # refresh 가 조용히 안 된다 — 로그인은 되는데 30분 뒤 끊긴다.
    # 하위 도메인끼리 나눠 써야 할 때만 채운다.
    COOKIE_DOMAIN: str = ""

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 14 * 24 * 60
    JWT_LEEWAY: int = 5

    UPLOAD_DIR: str = "/tmp/medical_uploads"
    MAX_UPLOAD_SIZE_MB: int = 20

    # 실제 OCR 워커 없이 fixture 결과를 즉시 DB에 기록한다 — Walking Skeleton 데모 전용.
    OCR_FIXTURE_FALLBACK: bool = False

    # CLOVA OCR 연동 — 비어 있으면 Worker가 fixture fallback으로 동작한다.
    # 실제 키는 .env에만 기록하고 코드·로그에 남기지 않는다.
    CLOVA_OCR_INVOKE_URL: str = ""
    # **`SecretStr` 이다** — 이희진 님 `#137` ③. 바로 아래 `OPENAI_API_KEY` 는
    # 이미 그랬는데 이 칸만 맨 `str` 이었고, 그 차이가 실제로 드러났다:
    #
    #     CLOVA_OCR_SECRET_KEY='...'          ← 평문으로 찍혔다
    #     OPENAI_API_KEY=SecretStr('*****')
    #
    # `repr` · `str` · `model_dump` · `model_dump_json` 넷 다 값을 내놨다.
    # 설정 객체는 디버깅할 때 통째로 찍기 쉬운 물건이라 (`#137` 검토 때
    # 한금준 님이 짚은 자리) 타입으로 막는다. 읽을 때는 `.get_secret_value()`.
    CLOVA_OCR_SECRET_KEY: SecretStr = SecretStr("")
    # KEY-163 §8 기준값 10초. 실제 응답 시간은 8/27 멘토링 후 확인 예정.
    CLOVA_OCR_TIMEOUT_SECONDS: float = 10.0

    @property
    def clova_enabled(self) -> bool:
        return bool(self.CLOVA_OCR_INVOKE_URL and self.CLOVA_OCR_SECRET_KEY.get_secret_value())

    # KEY-96 환자 챗봇의 단일 실제 모델 경로. 키가 없거나 호출이 실패하면
    # 승인 안내 화면 전체를 멈추지 않고 안전한 고정 응답으로 대체한다.
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_TIMEOUT_SECONDS: float = 20.0

    # 공급자 가격은 바뀔 수 있으므로 코드에 고정하지 않는다. 배포 환경에서
    # 단가를 넣은 경우에만 토큰 사용량으로 추정 비용을 기록한다.
    LLM_INPUT_USD_PER_1M_TOKENS: float | None = None
    LLM_OUTPUT_USD_PER_1M_TOKENS: float | None = None

    @model_validator(mode="after")
    def _fixture_fallback_is_local_only(self) -> "Config":
        if self.OCR_FIXTURE_FALLBACK and self.ENV is not Env.LOCAL:
            raise ValueError(f"OCR_FIXTURE_FALLBACK은 로컬 환경에서만 사용할 수 있습니다. (ENV={self.ENV.value})")
        return self

    @model_validator(mode="after")
    def _secret_key_must_be_set_outside_local(self) -> "Config":
        """**운영에서 기본값으로 뜨는 길을 막는다** — KEY-174.

        기본값이 `f"default-secret-key{uuid4().hex}"` 라 설정을 안 해도 서버가
        뜬다. 그런데 그 값은 **프로세스마다 다르다.** 재배포하거나 컨테이너가
        재시작될 때마다 바뀌어서, 그 전에 발급한 액세스·리프레시 토큰이 전부
        한꺼번에 죽는다. 사용자에게는 「갑자기 로그아웃됐다」로 보인다.

        `DB_PASSWORD` 에 이미 같은 규칙이 있다(KEY-110). 이름을 대며 멈추는
        편이 조용히 뜨는 것보다 낫다.

        **자리표시자도 같이 막는다.** 예시 파일에는 값이 적혀 있어야 「여기에
        무엇을 넣는지」가 보이는데, 그러면 `DB_PASSWORD` 와 달리 **안 채우고
        넘어가기 쉽다** — 빈칸이 아니라 이미 뭔가 들어 있어 보이기 때문이다.
        그렇게 뜨면 서버는 조용히 살아나서 **공개 저장소에 적힌 값으로 JWT 를
        서명한다** (이희진 님 `#133` 리뷰).
        """
        if self.ENV is Env.LOCAL:
            return self
        if not self.SECRET_KEY.strip():
            raise ValueError(
                f"SECRET_KEY 가 비어 있다 (ENV={self.ENV.value}). 빈 값으로 서명하면 누구나 토큰을 위조한다 (KEY-174)."
            )
        if self.SECRET_KEY.startswith("default-secret-key"):
            raise ValueError(
                f"SECRET_KEY 가 설정되지 않았다 (ENV={self.ENV.value}). "
                "기본값은 프로세스마다 달라서 재시작하면 발급한 토큰이 전부 죽는다 — "
                "환경변수나 `.env` 로 넘겨라 (KEY-174)."
            )
        if PLACEHOLDER.match(self.SECRET_KEY):
            raise ValueError(
                f"SECRET_KEY 가 예시 파일의 자리표시자 그대로다 (ENV={self.ENV.value}). "
                "공개 저장소에 적힌 값이라 아무나 토큰을 위조할 수 있다 — "
                "진짜 무작위 값으로 바꿔라 (KEY-174)."
            )
        return self

    @field_validator("DB_PASSWORD")
    @classmethod
    def _db_password_must_be_set(cls, value: str) -> str:
        """비어 있으면 여기서 이름을 대며 멈춘다.

        예전에는 기본값이 박혀 있어서, 설정을 안 해도 그 값으로 붙었다.
        그 값이 저장소 이력에 공개돼 있었다는 것이 문제였다 (KEY-110).
        지금은 조용히 붙는 길이 없다.

        **임포트 시점에 터지는 것은 의도한 것이다** — KEY-139 에서 정한 방침.

        `app/core/__init__.py` 가 `Config()` 를 바로 만들고 `app/tests/conftest.py`
        가 그걸 임포트하므로, `.env` 없이 돌리면 **DB 와 무관한 검사도** 여기서
        멈춘다. 불편한 것이 맞다. 그래도 그대로 두는 이유는 셋이다.

            늦게 터지면 더 나쁘다   연결 시점으로 미루면 서버가 뜬 뒤 첫 질의에서
                                    죽는다. 그때는 이미 배포된 뒤다
            CI 는 이미 넘긴다       `checks.yml` 이 `DB_PASSWORD` 를 명시로 준다
            고치는 법이 한 줄이다   `README` 의 「환경변수」 절 — 예시를 복사해
                                    `.env` 로 잇는다

        방침을 바꾸려면 첫 줄(늦게 터지는 것이 낫다)을 먼저 뒤집어야 한다.
        """
        if not value:
            raise ValueError("DB_PASSWORD 가 비어 있다. `.env` 에 설정하거나 환경변수로 넘겨라 (KEY-110).")
        return value
