import os
import uuid
import zoneinfo
from dataclasses import field
from enum import StrEnum
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


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
    CLOVA_OCR_SECRET_KEY: str = ""
    CLOVA_OCR_TIMEOUT_SECONDS: float = 30.0

    @property
    def clova_enabled(self) -> bool:
        return bool(self.CLOVA_OCR_INVOKE_URL and self.CLOVA_OCR_SECRET_KEY)

    @model_validator(mode="after")
    def _fixture_fallback_is_local_only(self) -> "Config":
        if self.OCR_FIXTURE_FALLBACK and self.ENV is not Env.LOCAL:
            raise ValueError(f"OCR_FIXTURE_FALLBACK은 로컬 환경에서만 사용할 수 있습니다. (ENV={self.ENV.value})")
        return self

    @field_validator("DB_PASSWORD")
    @classmethod
    def _db_password_must_be_set(cls, value: str) -> str:
        """비어 있으면 여기서 이름을 대며 멈춘다.

        예전에는 기본값이 박혀 있어서, 설정을 안 해도 그 값으로 붙었다.
        그 값이 저장소 이력에 공개돼 있었다는 것이 문제였다 (KEY-110).
        지금은 조용히 붙는 길이 없다.
        """
        if not value:
            raise ValueError("DB_PASSWORD 가 비어 있다. `.env` 에 설정하거나 환경변수로 넘겨라 (KEY-110).")
        return value
