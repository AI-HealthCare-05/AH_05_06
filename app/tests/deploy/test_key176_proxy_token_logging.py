"""운영 프록시가 URL의 환자 링크 토큰을 access log에 저장하지 않는가 — KEY-176."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[3]
SENSITIVE_PREFIXES = ("/api/v1/guides/", "/api/v1/checkins/")


def _location_bodies(config: str, prefix: str) -> list[str]:
    pattern = re.compile(rf"location \^~ {re.escape(prefix)} \{{(?P<body>.*?)\n    \}}", re.DOTALL)
    return [match.group("body") for match in pattern.finditer(config)]


def test_http_and_https_proxy_do_not_log_patient_link_paths() -> None:
    http = (ROOT / "infra/nginx/prod_http.conf").read_text(encoding="utf-8")
    https = (ROOT / "infra/nginx/prod_https.conf").read_text(encoding="utf-8")

    for prefix in SENSITIVE_PREFIXES:
        http_blocks = _location_bodies(http, prefix)
        https_blocks = _location_bodies(https, prefix)
        assert len(http_blocks) == 1, f"HTTP proxy에 {prefix} 전용 경계가 없다"
        assert len(https_blocks) == 2, f"HTTPS redirect·proxy에 {prefix} 전용 경계가 없다"
        assert all("access_log off;" in body for body in http_blocks + https_blocks)
        assert "proxy_pass http://fastapi;" in http_blocks[0]
        assert "return 301 https://$host$request_uri;" in https_blocks[0]
        assert "proxy_pass http://fastapi;" in https_blocks[1]


def test_general_api_access_log_is_not_disabled() -> None:
    """처리시간·실패율 수집용 일반 API 로그까지 끄면 KEY-144와 충돌한다."""
    for filename in ("prod_http.conf", "prod_https.conf"):
        config = (ROOT / "infra/nginx" / filename).read_text(encoding="utf-8")
        generic_blocks = re.findall(r"location /api/ \{(?P<body>.*?)\n    \}", config, re.DOTALL)
        assert generic_blocks
        assert all("access_log off;" not in body for body in generic_blocks)
