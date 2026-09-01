from fastapi import FastAPI
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise

from app.core import config

TORTOISE_APP_MODELS = [
    "aerich.models",
    "app.models.users",
    "app.models.patients",
    "app.models.visits",
    "app.models.prescriptions",
    "app.models.ocr",
    "app.models.staffs",
    "app.models.documents",
    "app.models.catalog",
    "app.models.feedback",
]

TORTOISE_ORM = {
    "connections": {
        "default": {
            "engine": "tortoise.backends.mysql",
            "dialect": "asyncmy",
            "credentials": {
                "host": config.DB_HOST,
                "port": config.DB_PORT,
                "user": config.DB_USER,
                "password": config.DB_PASSWORD,
                "database": config.DB_NAME,
                "connect_timeout": config.DB_CONNECT_TIMEOUT,
                "maxsize": config.DB_CONNECTION_POOL_MAXSIZE,
            },
        },
    },
    "apps": {
        "models": {
            "models": TORTOISE_APP_MODELS,
        },
    },
    "use_tz": True,
    "timezone": "Asia/Seoul",
}


#: **워커는 `aerich.models` 를 안 싣는다** — KEY-198.
#:
#: 워커가 하는 일에 마이그레이션 이력 표는 필요 없다. 그런데 이 한 줄이
#: 목록에 있으면 `Tortoise.init` 이 `aerich` 패키지를 **런타임에 임포트**하고,
#: 그러면 이미지에 `aerich upgrade` · `aerich downgrade` CLI 가 함께 들어간다.
#: 워커는 이미 DB 크리덴셜을 쥐고 있으므로, 스키마를 갈아엎는 명령까지 같은
#: 이미지에 두면 한 번 뚫렸을 때 번지는 범위가 커진다.
#:
#: **`TORTOISE_ORM` 자체는 건드리지 않는다.** `pyproject.toml` 의
#: `[tool.aerich] tortoise_orm = "app.core.db.databases.TORTOISE_ORM"` 이 그것을
#: 그대로 읽는다 — 거기서 `aerich.models` 를 빼면 마이그레이션이 자기 이력 표를
#: 잃는다. 그래서 **워커용 사본을 따로 둔다.**
WORKER_TORTOISE_MODELS = [m for m in TORTOISE_APP_MODELS if m != "aerich.models"]

WORKER_TORTOISE_ORM = {
    **TORTOISE_ORM,
    "apps": {"models": {"models": WORKER_TORTOISE_MODELS}},
}


def initialize_tortoise(app: FastAPI) -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    register_tortoise(app, config=TORTOISE_ORM)
