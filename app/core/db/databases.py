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
    #: **의원 시간대(KST) 벽시계로 담는다.**
    #:
    #: `use_tz: True` 였는데, 그 설정에서는 `tortoise.timezone.now()` 가 UTC 를
    #: 준다. 그런데 asyncmy 는 값을 넣을 때 **tzinfo 를 버리고 벽시계만** 적고
    #: (KEY-181), 읽을 때는 여기 적힌 `timezone` 으로 도장을 찍는다. 그래서
    #: `auto_now_add` 로 적힌 값은 UTC 벽시계가 KST 라고 읽혀 **아홉 시간**
    #: 어긋났다 — 직접 KST 로 넣는 `visited_at` 만 멀쩡했다.
    #:
    #: 눈에 보이는 것보다 나쁜 것은 **시각 비교**였다. 링크 만료와 인증번호
    #: 잠금이 `expires_at <= now()` 로 재는데, 왼쪽은 아홉 시간 이른 값이고
    #: 오른쪽은 UTC 라 **잠금이 즉시 풀렸다.**
    #:
    #: `use_tz: False` 로 두면 `now()` 가 KST 를 주고 `auto_now_add` 도 KST
    #: 벽시계로 적힌다 — 읽는 쪽과 같아진다. 이 저장소가 이미 고른 모양
    #: (「`visited_at` 열에는 KST 벽시계가 담겨 있다」)에 나머지를 맞추는 것이다.
    #:
    #: 저장을 UTC 로 정규화하는 근본 정리는 별건이다. 그때는 MySQL 세션
    #: 시간대와 이 두 줄을 함께 옮긴다.
    "use_tz": False,
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
