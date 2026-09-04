"""env변수 + 실행 인자 이중 요구에서 쓰는 진위값 파싱 — KEY-200, KEY-264가 공유한다.

값 집합이 두 군데에 따로 있으면 한쪽만 고치고 잊어버리기 쉽다. 파싱 로직은
각자 필요한 모양이 달라서(호출 자리 수, argv 처리 방식) 그대로 두고, 값
집합만 여기 하나로 둔다.
"""

TRUE_VALUES = frozenset({"1", "true"})


def is_flag_env_value_true(raw: str | None) -> bool:
    """환경변수 원본 문자열이 "1" 또는 "true"인지 본다 (대소문자 무시, 공백 제거)."""
    return raw is not None and raw.strip().lower() in TRUE_VALUES
