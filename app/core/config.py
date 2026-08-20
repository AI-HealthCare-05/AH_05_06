import os
import uuid
import zoneinfo
from dataclasses import field
from enum import StrEnum
from pathlib import Path

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
    DB_PASSWORD: str = "pw1234"
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
