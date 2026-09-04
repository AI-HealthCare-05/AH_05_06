"""KEY-231: OpenAPI 산출물의 결정성·변경 감지 계약.

DB 초기화를 하는 app/tests 아래에 두지 않는다. 이 도구의 단위 계약은 DTO를
실제로 생성하지 않아도 검증 가능하며, CI가 별도로 현재 DTO와 산출물 일치를
검사한다.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import generate_openapi  # noqa: E402


def test_openapi_serialization_is_deterministic() -> None:
    document = {"z": {"b": 1, "a": 2}, "a": ["한글", "value"]}

    assert generate_openapi.serialize(document) == generate_openapi.serialize(document)
    assert generate_openapi.serialize(document).decode("utf-8") == (
        '{\n  "a": [\n    "한글",\n    "value"\n  ],\n  "z": {\n    "a": 2,\n    "b": 1\n  }\n}\n'
    )


def test_check_reports_a_stale_artifact(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "openapi.json"
    output.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(generate_openapi, "generate", lambda: b'{"openapi": "3.1.0"}\n')

    assert generate_openapi.main(["--check", "--output", str(output)]) == 1


def test_check_accepts_the_current_artifact(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "openapi.json"
    expected = b'{"openapi": "3.1.0"}\n'
    output.write_bytes(expected)
    monkeypatch.setattr(generate_openapi, "generate", lambda: expected)

    assert generate_openapi.main(["--check", "--output", str(output)]) == 0
