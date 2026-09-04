#!/usr/bin/env python3
"""서버 DTO에서 OpenAPI 계약 산출물을 만든다 — KEY-231.

사용법

    uv run --group app python scripts/generate_openapi.py
    uv run --group app python scripts/generate_openapi.py --check

첫 명령은 ``docs/api/openapi.json``을 갱신한다. 두 번째 명령은 파일을 쓰지
않고, 현재 서버에서 다시 만든 결과와 저장소의 산출물이 다르면 1로 끝난다.
OpenAPI는 마크다운 API 문서를 대체하지 않는다. 실행 중인 FastAPI DTO의
기계 판독 가능한 정본이며, 사람이 내린 계약 결정과 영향은 ``docs/api/``의
문서·Jira·PR에 남긴다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "api" / "openapi.json"

# ``python scripts/generate_openapi.py``로 실행하면 Python은 scripts/만
# 모듈 경로에 넣는다. 저장소 루트의 app 패키지를 같은 방식으로 찾게 한다.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_document() -> dict[str, Any]:
    """현재 FastAPI 앱의 DTO·라우터에서 계약을 다시 뽑는다."""
    # app.main은 Config를 만들 때 환경을 검증한다. 따라서 이 도구도 서버와
    # 같은 설정 검증을 받고, DB에는 연결하지 않는다.
    from app.main import app

    return app.openapi()


def serialize(document: dict[str, Any]) -> bytes:
    """플랫폼·실행 순서와 무관한 한 가지 JSON 표현으로 고정한다."""
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def generate() -> bytes:
    return serialize(build_document())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FastAPI OpenAPI 계약 산출물 생성·검사")
    parser.add_argument("--check", action="store_true", help="파일을 쓰지 않고 저장소 산출물과 비교")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="산출물 경로 (기본: docs/api/openapi.json)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output: Path = args.output
    rendered = generate()

    if args.check:
        if not output.is_file() or output.read_bytes() != rendered:
            print(
                f"OpenAPI 산출물이 현재 서버 DTO와 다릅니다: {output}\n"
                "`uv run --group app python scripts/generate_openapi.py`를 실행한 뒤 변경 내용을 검토·커밋하세요."
            )
            return 1
        print(f"OpenAPI 산출물이 현재 서버 DTO와 일치합니다: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rendered)
    print(f"OpenAPI 산출물을 갱신했습니다: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
