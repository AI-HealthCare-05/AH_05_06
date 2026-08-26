"""LLM 관측 로그 테스트 — KEY-175.

검증 경로:
  민감정보 비노출
    - chatbot_generation 로그에 질문 원문·응답 원문·link_token이 포함되지 않는다.
    - model_failed 경로에서 예외 내부 메시지가 로그에 포함되지 않는다.

  구조화 로그 형식
    - 성공(success=True): model·latency_ms·cost_usd·reason=none 확인
    - context_missing(success=False): reason=context_missing, latency_ms=0 확인
    - model_unconfigured(success=False): model=unconfigured, reason=model_unconfigured 확인
    - model_failed(success=False): reason=model_failed, latency_ms>=0 확인
    - model_context_insufficient(success=False): reason=model_context_insufficient 확인
    - unsafe_or_ungrounded_output_blocked(success=False): 안전 차단 reason 확인

  모든 종료 경로에서 chatbot_generation 한 줄만 남긴다.
"""

import hashlib
from dataclasses import dataclass

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.models.visits import (
    GuideDocument,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    PatientGuideLink,
)
from app.services.chatbot import (
    ChatbotService,
    ChatModelError,
    ModelAnswer,
)
from app.tests.patient_links.test_patient_links import make_guide, make_hospital

_LOGGER = "app.chatbot"
TOKEN = "synthetic-key175-llm-obs-token"


@dataclass
class FakeModel:
    answer: str = "매일 저녁 같은 시간에 복용하세요."
    fail: bool = False
    fail_reason: str = "provider_timeout"
    model_name: str = "synthetic-obs-model"
    input_tokens: int = 100
    output_tokens: int = 20

    async def generate(self, *, instructions: str, prompt: str) -> ModelAnswer:
        if self.fail:
            raise ChatModelError(self.fail_reason)
        return ModelAnswer(self.answer, input_tokens=self.input_tokens, output_tokens=self.output_tokens)


async def _setup_guide(name: str, token: str = TOKEN) -> GuideDocument:
    hospital = await make_hospital(name)
    guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
    # edited_body를 FakeModel 기본 응답과 일치시켜 extractive grounding을 통과시킨다.
    medication = await GuideSection.get(guide_document=guide, section_key=GuideSectionKey.MEDICATION)
    medication.edited_body = "매일 저녁 같은 시간에 복용하세요."
    await medication.save(update_fields=["edited_body"])
    await PatientGuideLink.create(
        guide_document=guide,
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now().replace(year=now().year + 1),
        issued_by=1,
    )
    return guide


# ---------------------------------------------------------------------------
# _observe() 단위 테스트 — DB 불필요, 서비스 인스턴스에서 직접 호출
# ---------------------------------------------------------------------------


class TestObserveUnit(TestCase):
    """_observe() 가 올바른 chatbot_generation 구조화 로그를 남기는지 검증한다."""

    def _service(self, *, with_rates: bool = True) -> ChatbotService:
        return ChatbotService(
            model=FakeModel(),
            input_usd_per_1m_tokens=1.0 if with_rates else None,
            output_usd_per_1m_tokens=2.0 if with_rates else None,
        )

    def test_success_log_format(self) -> None:
        svc = self._service()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            svc._observe(
                model_name="synthetic-obs-model",
                success=True,
                latency_ms=420,
                reason=None,
                input_tokens=100,
                output_tokens=20,
            )
        log = "\n".join(cap.output)
        assert "chatbot_generation" in log
        assert "model=synthetic-obs-model" in log
        assert "success=True" in log
        assert "latency_ms=420" in log
        assert "cost_usd=" in log
        assert "reason=none" in log

    def test_context_missing_log_format(self) -> None:
        svc = self._service()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            svc._observe(model_name="synthetic-obs-model", success=False, latency_ms=0, reason="context_missing")
        log = "\n".join(cap.output)
        assert "chatbot_generation" in log
        assert "success=False" in log
        assert "latency_ms=0" in log
        assert "reason=context_missing" in log

    def test_model_unconfigured_log_format(self) -> None:
        svc = self._service()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            svc._observe(model_name="unconfigured", success=False, latency_ms=0, reason="model_unconfigured")
        log = "\n".join(cap.output)
        assert "model=unconfigured" in log
        assert "reason=model_unconfigured" in log

    def test_model_failed_log_format(self) -> None:
        svc = self._service()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            svc._observe(model_name="synthetic-obs-model", success=False, latency_ms=310, reason="model_failed")
        log = "\n".join(cap.output)
        assert "success=False" in log
        assert "latency_ms=310" in log
        assert "reason=model_failed" in log

    def test_cost_usd_is_none_when_rates_not_configured(self) -> None:
        svc = self._service(with_rates=False)
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            svc._observe(model_name="synthetic-obs-model", success=False, latency_ms=0, reason="context_missing")
        log = "\n".join(cap.output)
        assert "cost_usd=None" in log

    def test_no_sensitive_data_in_observe_log(self) -> None:
        """_observe() 로그에 질문·응답 원문·토큰·API 키가 없어야 한다."""
        sensitive = [
            "환자질문원문_노출금지",
            "LLM응답원문_노출금지",
            "sk-secret-api-key",
            TOKEN,
        ]
        svc = self._service()
        with self.assertLogs(_LOGGER, level="INFO") as cap:
            svc._observe(
                model_name="synthetic-obs-model",
                success=True,
                latency_ms=200,
                reason=None,
                input_tokens=50,
                output_tokens=10,
            )
        log = "\n".join(cap.output)
        for secret in sensitive:
            assert secret not in log, f"민감정보 노출: {secret!r}"


# ---------------------------------------------------------------------------
# ChatbotService.answer() 통합 테스트 — 실제 DB + assertLogs
# ---------------------------------------------------------------------------


class TestLlmObservabilityIntegration(TestCase):
    """각 answer() 경로에서 chatbot_generation 로그가 올바르게 남는지 검증."""

    # --- 정상 경로 ---

    async def test_success_logs_true_and_reason_none(self) -> None:
        """정상 응답 시 success=True, reason=none, latency_ms 기록."""
        await _setup_guide("KEY-175 LLM 정상 합성의원")
        svc = ChatbotService(model=FakeModel(), input_usd_per_1m_tokens=1.0, output_usd_per_1m_tokens=2.0)

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=TOKEN, question="약은 언제 먹나요?")

        log = "\n".join(cap.output)
        assert "chatbot_generation" in log
        assert "success=True" in log
        assert "reason=none" in log
        assert "latency_ms=" in log
        assert "cost_usd=" in log

    # --- context_missing ---

    async def test_context_missing_logs_success_false_and_zero_latency(self) -> None:
        """승인 컨텍스트 매칭 실패 시 success=False, reason=context_missing, latency_ms=0."""
        await _setup_guide("KEY-175 LLM context_missing 합성의원")
        svc = ChatbotService(model=FakeModel())

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=TOKEN, question="오늘 날씨 어때요?")

        log = "\n".join(cap.output)
        assert "success=False" in log
        assert "reason=context_missing" in log
        assert "latency_ms=0" in log

    # --- model_unconfigured ---

    async def test_model_none_logs_unconfigured_and_reason(self) -> None:
        """model=None 시 model=unconfigured, reason=model_unconfigured."""
        await _setup_guide("KEY-175 LLM unconfigured 합성의원")
        svc = ChatbotService(model=None)

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=TOKEN, question="약은 언제 먹나요?")

        log = "\n".join(cap.output)
        assert "model=unconfigured" in log
        assert "reason=model_unconfigured" in log
        assert "success=False" in log

    # --- model_failed (타임아웃·외부 오류 포함) ---

    async def test_model_exception_logs_model_failed(self) -> None:
        """모델 예외 발생 시 success=False, reason=model_failed, latency_ms 기록."""
        await _setup_guide("KEY-175 LLM model_failed 합성의원")
        svc = ChatbotService(model=FakeModel(fail=True, fail_reason="provider_timeout"))

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=TOKEN, question="약은 언제 먹나요?")

        log = "\n".join(cap.output)
        assert "success=False" in log
        assert "reason=model_failed" in log
        assert "latency_ms=" in log

    async def test_model_failed_does_not_log_exception_internals(self) -> None:
        """모델 실패 시 ChatModelError 내부 reason 문자열이 로그에 포함되지 않는다."""
        await _setup_guide("KEY-175 LLM 예외원문비노출 합성의원")
        secret_reason = "INTERNAL_SECRET_PROVIDER_MESSAGE_노출금지"
        svc = ChatbotService(model=FakeModel(fail=True, fail_reason=secret_reason))

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=TOKEN, question="약은 언제 먹나요?")

        log = "\n".join(cap.output)
        assert secret_reason not in log
        assert "reason=model_failed" in log

    # --- model_context_insufficient ---

    async def test_context_insufficient_response_logs_correct_reason(self) -> None:
        """모델이 CONTEXT_INSUFFICIENT 반환 시 reason=model_context_insufficient."""
        await _setup_guide("KEY-175 LLM context_insufficient 합성의원")
        svc = ChatbotService(model=FakeModel(answer="CONTEXT_INSUFFICIENT"))

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=TOKEN, question="약은 언제 먹나요?")

        log = "\n".join(cap.output)
        assert "success=False" in log
        assert "reason=model_context_insufficient" in log

    # --- unsafe_or_ungrounded_output_blocked ---

    async def test_unsafe_output_logs_blocked_reason(self) -> None:
        """안전 차단 응답(처방 변경 권유 등) 시 reason=unsafe_or_ungrounded_output_blocked."""
        await _setup_guide("KEY-175 LLM 안전차단 합성의원")
        svc = ChatbotService(model=FakeModel(answer="지금 약을 중단하세요."))

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=TOKEN, question="약은 언제 먹나요?")

        log = "\n".join(cap.output)
        assert "success=False" in log
        assert "reason=unsafe_or_ungrounded_output_blocked" in log

    # --- 민감정보 비노출 (통합 경로) ---

    async def test_no_question_or_answer_text_in_success_log(self) -> None:
        """성공 경로 로그에 질문 원문·응답 원문이 남지 않는다."""
        await _setup_guide("KEY-175 LLM 민감정보 합성의원")
        question = "로그에_남으면_안_되는_합성_질문_약복용"
        answer = "매일 저녁 같은 시간에 복용하세요."
        svc = ChatbotService(model=FakeModel(answer=answer))

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=TOKEN, question=question)

        log = "\n".join(cap.output)
        assert question not in log
        assert answer not in log

    async def test_no_link_token_in_any_log_path(self) -> None:
        """어떤 경로에서도 link_token 원문이 로그에 남지 않는다."""
        secret_token = "SECRET-PATIENT-LINK-TOKEN-노출금지"
        await _setup_guide("KEY-175 LLM 토큰비노출 합성의원", token=secret_token)
        svc = ChatbotService(model=FakeModel())

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=secret_token, question="약은 언제 먹나요?")

        log = "\n".join(cap.output)
        assert secret_token not in log

    # --- 로그 중복 없음 ---

    async def test_exactly_one_observe_log_per_answer_call(self) -> None:
        """하나의 answer() 호출에서 chatbot_generation 로그가 정확히 한 줄 남는다."""
        await _setup_guide("KEY-175 LLM 중복없음 합성의원")
        svc = ChatbotService(model=FakeModel())

        with self.assertLogs(_LOGGER, level="INFO") as cap:
            await svc.answer(link_token=TOKEN, question="약은 언제 먹나요?")

        observe_lines = [line for line in cap.output if "chatbot_generation" in line]
        assert len(observe_lines) == 1, f"chatbot_generation이 {len(observe_lines)}번 기록됨"
