"""KEY-96 실제 모델 1회 호출 재현.

합성 승인 문구와 합성 질문만 보내며 API 키·프롬프트·응답 원문은 출력하지
않는다. `OPENAI_API_KEY`가 없으면 성공으로 가장하지 않고 종료 코드 2를 낸다.
"""

import asyncio
import json
import os
from time import perf_counter

# 이 smoke는 DB를 사용하지 않지만 `app.core`의 공통 설정은 import 시 DB 비밀번호
# 존재를 검증한다. 실제 값이 없을 때만 사용되지 않는 합성값을 넣는다.
os.environ.setdefault("DB_PASSWORD", "synthetic-key96-smoke-not-used")

from app.models.visits import GuideSectionKey
from app.services.chatbot import (
    OpenAIResponsesModel,
    RetrievedSection,
    _instructions,
    _is_extractively_grounded,
    _prompt,
)

SYNTHETIC_CONTEXT = "합성 승인 복약 안내입니다. 매일 저녁 같은 시간에 복용하세요."
SYNTHETIC_QUESTION = "약은 언제 먹나요?"


async def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print(json.dumps({"success": False, "reason": "OPENAI_API_KEY_NOT_SET"}))
        return 2

    model_name = os.environ.get("OPENAI_MODEL", "gpt-5.6")
    model = OpenAIResponsesModel(
        api_key=api_key,
        model_name=model_name,
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        timeout_seconds=float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "20")),
    )
    section = RetrievedSection(GuideSectionKey.MEDICATION, SYNTHETIC_CONTEXT)
    started = perf_counter()
    try:
        answer = await model.generate(
            instructions=_instructions(),
            prompt=_prompt(SYNTHETIC_QUESTION, section),
        )
    except Exception:
        print(
            json.dumps(
                {
                    "model": model_name,
                    "success": False,
                    "latency_ms": round((perf_counter() - started) * 1000),
                    "reason": "MODEL_CALL_FAILED",
                }
            )
        )
        return 1

    grounded = _is_extractively_grounded(answer.text, section)
    print(
        json.dumps(
            {
                "model": model_name,
                "success": grounded,
                "latency_ms": round((perf_counter() - started) * 1000),
                "grounded": grounded,
            }
        )
    )
    return 0 if grounded else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
