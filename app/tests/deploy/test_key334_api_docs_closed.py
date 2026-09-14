"""API 명세는 **밖으로 안 연다** — KEY-334.

앱에도 문이 하나 있다. `app/main.py` 가 `ENV=prod` 면 `docs_url`·`redoc_url`·
`openapi_url` 을 `None` 으로 꺼 둔다. 그런데 그 문은 **`ENV` 에 달려 있다.**

2026-09-14 에 `ENV=dev` 로 내리자(KEY-248 검증기가 `ENV=prod` + `SMS_PROVIDER=mock`
을 거부해서, 솔라피 값이 없는 동안 택한 조치) 그 분기가 풀려 Swagger·ReDoc·
`openapi.json` 이 **인터넷에 그대로 열렸다.** 종점·요청 모양·오류 코드가 다 보인다.

그래서 nginx 에도 문을 단다. **두 문은 서로를 대신하지 않는다** — 앱 쪽은 코드가
어떤 환경에서 도는지를 말하고, nginx 쪽은 **밖에서 닿을 수 있는가**를 말한다.
`ENV` 를 누가 또 내려도 이쪽은 안 열린다.

`prod_https.conf` 는 서버 블록이 둘이다(80 리다이렉트 · 443). **둘 다** 막혀야
한다 — 한쪽만 막으면 HTTPS 로 바로 들어오는 요청이 지나간다.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

#: 막아야 하는 자리. 앱이 `ENV=prod` 에서 끄는 것과 같은 셋이다(`app/main.py`).
DOC_ROUTES = ("docs", "redoc", "openapi.json")

BLOCK = re.compile(r"location\s+~\s+\^/api/\((?P<routes>[^)]+)\)\s*\{(?P<body>[^}]*)\}")


def _configs() -> dict[str, str]:
    return {
        name: (ROOT / "infra/nginx" / name).read_text(encoding="utf-8")
        for name in ("prod_http.conf", "prod_https.conf")
    }


def test_every_server_block_closes_the_api_docs() -> None:
    """서버 블록마다 하나씩 — 80 도 443 도."""
    for name, config in _configs().items():
        servers = config.count("\nserver {")
        blocks = BLOCK.findall(config)
        assert len(blocks) == servers, (
            f"{name}: server 블록 {servers} 개인데 문서 차단은 {len(blocks)} 개다 — "
            "한쪽만 막으면 그쪽으로 들어온 요청이 지나간다"
        )
        for routes, body in blocks:
            for route in DOC_ROUTES:
                assert route.replace(".", "\\.") in routes or route in routes, f"{name}: {route} 가 차단 목록에 없다"
            assert "return 404" in body, f"{name}: 404 가 아니라 다른 것을 준다: {body.strip()}"


def test_the_app_still_closes_them_too() -> None:
    """**이중 방어다.** nginx 를 달았다고 앱 쪽 분기를 걷지 않는다 —
    터널로 `fastapi:8000` 에 직접 붙는 길이 남아 있다.
    """
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")

    for route in ("docs_url", "redoc_url", "openapi_url"):
        assert re.search(rf"{route}=None if _is_prod", main), f"앱 쪽 {route} 분기가 사라졌다"


def test_health_and_login_are_not_caught_by_the_rule() -> None:
    """막는 것은 문서 셋뿐이다. 확인 경로와 화면까지 막으면 배포를 못 잰다.

    🚩 **이 검사는 한 번 헛돌았다** (`#304` 리뷰, 2heej). 설정 파일에서 규칙
    **글자**를 찾는 정규식을 만들어 놓고 그것을 URL 에 들이댔다. `^` 로 시작하는
    URL 은 없으니 무엇을 넣어도 거짓이었다 — `/api/docs` 를 넣어도 통과했다.
    「막지 않는다」를 재는 검사가 **아무것도 재지 않고** 늘 초록이었다.

    그래서 지금은 설정에서 **경로 목록을 뽑아 nginx 가 쓰는 규칙을 다시 세운다.**
    막아야 하는 쪽도 같이 잰다 — 한쪽만 재면 「전부 막는 규칙」도 통과한다.
    설정이 바뀌면 이 검사도 따라 바뀐다.
    """
    for name, config in _configs().items():
        blocks = BLOCK.findall(config)
        assert blocks, f"{name}: 차단 규칙을 못 찾았다 — 검사가 헛돈다"

        for routes, _ in blocks:
            rule = re.compile(rf"^/api/({routes})")

            for closed in ("/api/docs", "/api/redoc", "/api/openapi.json", "/api/docs/oauth2-redirect"):
                assert rule.search(closed), f"{name}: {closed} 가 안 막힌다"

            for safe in ("/api/v1/health", "/api/v1/guides/abc", "/login.html", "/"):
                assert not rule.search(safe), f"{name}: {safe} 까지 막는다"
