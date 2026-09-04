"""env변수 + 실행 인자 이중 요구에서 쓰는 진위값 파싱 — KEY-200(scripts/seed.py),
KEY-264(app/core/config.py)가 공유한다.

값 집합이 두 군데에 따로 있으면 한쪽만 고치고 잊어버리기 쉽다.
"""

TRUE_VALUES = frozenset({"1", "true"})


def is_flag_env_value_true(raw: str | None) -> bool:
    """환경변수 원본 문자열이 "1" 또는 "true"인지 본다 (대소문자 무시, 공백 제거)."""
    return raw is not None and raw.strip().lower() in TRUE_VALUES
