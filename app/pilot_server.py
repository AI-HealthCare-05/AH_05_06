"""Pilot 전용 서버 기동 스크립트 (KEY-264).

uvicorn CLI는 모르는 플래그를 거부하기 때문에, --pilot-confirm-mock-otp를
sys.argv에 남기려면 uvicorn.run()으로 직접 띄워야 한다. 일반 운영은 그대로
app/Dockerfile 기본 CMD(uvicorn CLI)를 쓴다 — 이 스크립트는 Pilot 배포에서만
쓴다.

사용법:
    PILOT_ALLOW_MOCK_OTP=1 uv run --no-sync python -m app.pilot_server --pilot-confirm-mock-otp
"""

import argparse

import uvicorn

from app.core.config import PILOT_ALLOW_MOCK_OTP_FLAG


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(PILOT_ALLOW_MOCK_OTP_FLAG, action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    uvicorn.run("app.main:app", host=args.host, port=args.port, workers=args.workers)


if __name__ == "__main__":
    main()
