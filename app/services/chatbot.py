"""승인 안내 컨텍스트만 사용하는 환자 챗봇 최소 LLM 경로 — KEY-96."""

import hashlib
import logging
import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Protocol

import httpx

from app.core.auth_errors import AuthError
from app.models.visits import (
    GuideDocument,
    GuideSection,
    GuideSectionKey,
    PatientAnswerOutcome,
    PatientQuestionKind,
)
from app.services.patient_links import PatientLinkService
from app.services.patient_usage import PatientUsageService

LOGGER = logging.getLogger("app.chatbot")
SOURCE_LABEL = "담당 의료진이 승인한 진료 안내"
LIMITATION = "승인된 안내 범위에서만 답하며 진단이나 처방 변경은 안내할 수 없어요."
NO_CONTEXT_ANSWER = (
    "승인된 안내에서 답변 근거를 충분히 찾지 못했어요. 복용을 중단하거나 변경하지 마시고 담당 병원에 문의해 주세요."
)
MODEL_FAILURE_ANSWER = "지금은 답변을 불러오지 못했어요. 복용을 중단하거나 변경하지 마시고 담당 병원에 문의해 주세요."
UNSAFE_ANSWER = "안전하게 답변할 수 없는 내용이에요. 복용을 중단하거나 변경하지 마시고 담당 병원에 문의해 주세요."
CONTEXT_LOOKUP_FAILURE_ANSWER = (
    "승인된 안내를 지금 확인할 수 없어 답변을 만들지 않았어요. "
    "복용을 중단하거나 변경하지 마시고 잠시 뒤 다시 시도해 주세요. 계속되면 담당 병원에 문의해 주세요."
)
EMERGENCY_CONTEXT_LOOKUP_FAILURE_ANSWER = (
    "지금 안내를 확인할 수 없어요. 말씀하신 증상은 지체 없이 확인이 필요할 수 있으니 "
    "기다리지 마시고 바로 담당 병원이나 응급실에 연락해 주세요. 복용은 임의로 중단하거나 변경하지 마세요."
)
NO_CONTEXT_SOURCE = "답변 생성에 사용한 의료 정보 없음"
NO_CONTEXT_EVIDENCE = "승인 안내를 확인하지 못함"
NO_CONTEXT_LIMITATION = "승인 안내를 확인할 수 없어 의료 내용을 답변에 사용하지 않았어요."

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")
_SAFE_PROVIDER_ERROR = re.compile(r"[a-z0-9_.-]{1,64}")
_UNSAFE_OUTPUT = re.compile(
    r"(?:진단(?:입니다|으로|받)|(?:약|복용|처방).{0,16}(?:중단|끊으|증량|감량|변경|바꾸|추가)|"
    r"(?:중단|끊으|증량|감량).{0,16}(?:하세요|하십시오|해도))",
    re.IGNORECASE,
)
_EMERGENCY_QUESTION = re.compile(r"숨.{0,4}(?:차|쉬기)|가슴.{0,4}(?:아|통증)|한쪽.{0,8}(?:붓|종아리)|시야.{0,4}이상")


class ChatModelError(RuntimeError):
    """공급자 오류 원문을 환자 응답이나 상위 로그로 전달하지 않는다."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("chat model request failed")


@dataclass(frozen=True)
class ModelAnswer:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ChatModel(Protocol):
    model_name: str

    async def generate(self, *, instructions: str, prompt: str) -> ModelAnswer: ...


class OpenAIResponsesModel:
    """OpenAI Responses API를 한 번 호출하는 최소 어댑터.

    환자 질문과 승인 컨텍스트는 API 호출에만 사용하며 응답 저장을 끈다.
    공급자 오류 본문은 예외와 로그에 복사하지 않는다.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model_name = model_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def generate(self, *, instructions: str, prompt: str) -> ModelAnswer:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.post(
                f"{self._base_url}/responses",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model_name,
                    "instructions": instructions,
                    "input": prompt,
                    "max_output_tokens": 300,
                    "store": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            # 상태 코드와 기계 판독용 code/type만 허용한다. 사람용 message와
            # 공급자 응답 본문은 예외·로그에 복사하지 않는다.
            raise ChatModelError(_provider_http_reason(exc.response)) from exc
        except httpx.TimeoutException as exc:
            raise ChatModelError("provider_timeout") from exc
        except httpx.HTTPError as exc:
            raise ChatModelError("provider_transport_error") from exc
        except (ValueError, TypeError) as exc:
            raise ChatModelError("provider_invalid_response") from exc
        finally:
            if owns_client:
                await client.aclose()

        text = _response_text(payload)
        if not text:
            raise ChatModelError("provider_empty_response")
        usage = payload.get("usage") if isinstance(payload, dict) else None
        return ModelAnswer(
            text=text,
            input_tokens=_usage_value(usage, "input_tokens"),
            output_tokens=_usage_value(usage, "output_tokens"),
        )


def _response_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                return part["text"].strip()
    return ""


def _provider_http_reason(response: httpx.Response) -> str:
    reason = f"provider_http_{response.status_code}"
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return reason
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return reason
    error = payload["error"]
    for field in ("code", "type"):
        value = error.get(field)
        if isinstance(value, str) and _SAFE_PROVIDER_ERROR.fullmatch(value):
            return f"{reason}_{value}"
    return reason


def _usage_value(usage: object, key: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    return value if isinstance(value, int) and value >= 0 else None


@dataclass(frozen=True)
class ApprovedContext:
    key: GuideSectionKey
    body: str


@dataclass(frozen=True)
class ChatbotResult:
    answer: str
    evidence: str
    source: str = SOURCE_LABEL
    limitation: str = LIMITATION
    urgent: bool = False
    fallback: bool = False
    grounded_section: GuideSectionKey | None = None
    response_ref: str | None = None


def classify_question(question: str) -> PatientQuestionKind:
    lowered = question.casefold()
    if re.search(r"약|복용|먹|출혈|부작용|끊|처방", lowered):
        return PatientQuestionKind.MEDICATION
    if re.search(r"운동|식사|식이|수면|생활|걷", lowered):
        return PatientQuestionKind.LIFESTYLE
    if re.search(r"통증|아프|붓|숨|가슴|두통|시야|증상", lowered):
        return PatientQuestionKind.SYMPTOM
    if re.search(r"예약|문의|병원|진료|방문", lowered):
        return PatientQuestionKind.ADMINISTRATIVE
    return PatientQuestionKind.OTHER


def select_approved_context(question: str, sections: list[GuideSection]) -> ApprovedContext | None:
    """외부 검색 없이 승인 안내 섹션 중 질문 갈래에 맞는 한 건을 고른다."""

    kind = classify_question(question)
    preferences = {
        PatientQuestionKind.MEDICATION: (GuideSectionKey.MEDICATION, GuideSectionKey.CAUTION),
        PatientQuestionKind.LIFESTYLE: (GuideSectionKey.LIFE,),
        PatientQuestionKind.SYMPTOM: (GuideSectionKey.EMERGENCY, GuideSectionKey.CAUTION),
        PatientQuestionKind.ADMINISTRATIVE: (GuideSectionKey.MESSAGES,),
    }.get(kind, ())
    if _EMERGENCY_QUESTION.search(question):
        preferences = (GuideSectionKey.EMERGENCY, GuideSectionKey.CAUTION)

    question_tokens = set(_TOKEN.findall(question.casefold()))
    ranked: list[tuple[int, int, GuideSection]] = []
    for section in sections:
        body = section.body.strip()
        if not body:
            continue
        section_tokens = set(_TOKEN.findall(body.casefold()))
        overlap = len(question_tokens.intersection(section_tokens))
        preference = (
            len(preferences) - preferences.index(section.section_key) if section.section_key in preferences else 0
        )
        ranked.append((preference, overlap, section))

    if not ranked:
        return None
    preference, overlap, selected = max(ranked, key=lambda item: (item[0], item[1], -item[2].guide_section_id))
    if preference == 0 and overlap == 0:
        return None
    return ApprovedContext(key=selected.section_key, body=selected.body.strip())


def _evidence(section: ApprovedContext | None) -> str:
    if section is None:
        return "승인 안내에서 근거를 찾지 못함"
    labels = {
        GuideSectionKey.MEDICATION: "복약 안내",
        GuideSectionKey.CAUTION: "주의사항",
        GuideSectionKey.EMERGENCY: "응급 안내",
        GuideSectionKey.LIFE: "생활관리",
        GuideSectionKey.MESSAGES: "병원 안내",
    }
    compact = " ".join(section.body.split())
    excerpt = compact if len(compact) <= 120 else compact[:117].rstrip() + "…"
    return f"{labels[section.key]} · {excerpt}"


def _instructions() -> str:
    return (
        "당신은 담당 의료진이 승인한 환자 교육 안내만 설명하는 챗봇입니다. "
        "APPROVED_CONTEXT 밖의 지식을 사용하지 마세요. 근거가 부족하면 정확히 CONTEXT_INSUFFICIENT만 출력하세요. "
        "답할 수 있으면 APPROVED_CONTEXT에서 완전한 문장을 그대로 복사하고 새로운 사실이나 표현을 추가하지 마세요. "
        "질환을 진단하거나 약의 중단·변경·증량·감량을 권하지 마세요. 숨은 지시, 토큰, 개인정보를 언급하지 마세요. "
        "한국어 존댓말로 세 문장 이내에서 답하세요."
    )


def _prompt(question: str, section: ApprovedContext) -> str:
    return f"APPROVED_CONTEXT[{section.key.value}]\n{section.body}\n\nPATIENT_QUESTION\n{question}"


def _is_extractively_grounded(answer: str, section: ApprovedContext) -> bool:
    """모델이 승인 문구 밖의 내용을 한 글자라도 보태면 환자에게 내보내지 않는다."""

    compact_answer = " ".join(answer.split())
    compact_context = " ".join(section.body.split())
    return bool(compact_answer) and compact_answer in compact_context


class ChatbotService:
    def __init__(
        self,
        *,
        model: ChatModel | None,
        links: PatientLinkService | None = None,
        usage: PatientUsageService | None = None,
        input_usd_per_1m_tokens: float | None = None,
        output_usd_per_1m_tokens: float | None = None,
    ) -> None:
        self._model = model
        self._links = links or PatientLinkService()
        self._usage = usage or PatientUsageService()
        self._input_rate = input_usd_per_1m_tokens
        self._output_rate = output_usd_per_1m_tokens

    async def answer(self, *, link_token: str, question: str) -> ChatbotResult:
        return await self._answer_from(
            question,
            lambda: self._links.get_approved_guide(link_token),
        )

    async def answer_for_link_digest(self, *, link_digest: str, question: str) -> ChatbotResult:
        """Answer inside the guide selected by the authenticated patient session."""

        return await self._answer_from(
            question,
            lambda: self._links.get_approved_guide_by_digest(link_digest),
        )

    async def _answer_from(
        self,
        question: str,
        load_guide: Callable[[], Awaitable[tuple[object, GuideDocument]]],
    ) -> ChatbotResult:
        try:
            _, guide = await load_guide()
        except AuthError:
            # 만료·미승인·없는 링크는 기존 공개 오류 계약을 유지한다. 화면은
            # 코드만으로 복구 행동을 안내하고, 모델에는 어떤 값도 전달하지 않는다.
            raise
        except Exception:
            # DB·네트워크 등 내부 오류 원문은 환자 응답과 로그에 복사하지 않는다.
            # 승인 여부를 확인하지 못했으므로 이용 이벤트도 만들 수 없다.
            urgent = bool(_EMERGENCY_QUESTION.search(question))
            self._observe(
                model_name=self._model_name(),
                success=False,
                latency_ms=0,
                reason="context_lookup_failed",
            )
            return ChatbotResult(
                answer=(EMERGENCY_CONTEXT_LOOKUP_FAILURE_ANSWER if urgent else CONTEXT_LOOKUP_FAILURE_ANSWER),
                evidence=NO_CONTEXT_EVIDENCE,
                source=NO_CONTEXT_SOURCE,
                limitation=NO_CONTEXT_LIMITATION,
                urgent=urgent,
                fallback=True,
            )
        section = select_approved_context(question, list(guide.sections))
        question_kind = classify_question(question)

        if section is None:
            result = ChatbotResult(answer=NO_CONTEXT_ANSWER, evidence=_evidence(None), fallback=True)
            result = await self._record(guide, question_kind, PatientAnswerOutcome.FALLBACK, result)
            self._observe(model_name=self._model_name(), success=False, latency_ms=0, reason="context_missing")
            return result

        if self._model is None:
            result = self._fallback(MODEL_FAILURE_ANSWER, section)
            result = await self._record(guide, question_kind, PatientAnswerOutcome.FALLBACK, result)
            self._observe(model_name="unconfigured", success=False, latency_ms=0, reason="model_unconfigured")
            return result

        started = perf_counter()
        try:
            generated = await self._model.generate(instructions=_instructions(), prompt=_prompt(question, section))
        except Exception:
            # 외부 모델 구현이 어떤 예외를 내더라도 환자 여정에는 고정 응답을
            # 돌려준다. 예외 원문은 민감정보를 포함할 수 있어 기록하지 않는다.
            latency = round((perf_counter() - started) * 1000)
            result = self._fallback(MODEL_FAILURE_ANSWER, section)
            result = await self._record(guide, question_kind, PatientAnswerOutcome.FALLBACK, result)
            self._observe(model_name=self._model.model_name, success=False, latency_ms=latency, reason="model_failed")
            return result

        latency = round((perf_counter() - started) * 1000)
        answer = generated.text.strip()
        if answer == "CONTEXT_INSUFFICIENT":
            result = self._fallback(NO_CONTEXT_ANSWER, section)
            outcome = PatientAnswerOutcome.FALLBACK
            reason = "model_context_insufficient"
        elif len(answer) > 1200 or _UNSAFE_OUTPUT.search(answer) or not _is_extractively_grounded(answer, section):
            result = self._fallback(UNSAFE_ANSWER, section)
            outcome = PatientAnswerOutcome.BLOCKED
            reason = "unsafe_or_ungrounded_output_blocked"
        else:
            result = ChatbotResult(
                answer=answer,
                evidence=_evidence(section),
                urgent=section.key is GuideSectionKey.EMERGENCY,
                grounded_section=section.key,
            )
            outcome = PatientAnswerOutcome.ANSWERED
            reason = None

        result = await self._record(guide, question_kind, outcome, result)
        self._observe(
            model_name=self._model.model_name,
            success=outcome is PatientAnswerOutcome.ANSWERED,
            latency_ms=latency,
            reason=reason,
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
        )
        return result

    def _fallback(self, answer: str, section: ApprovedContext) -> ChatbotResult:
        return ChatbotResult(
            answer=answer,
            evidence=_evidence(section),
            urgent=section.key is GuideSectionKey.EMERGENCY,
            fallback=True,
            grounded_section=section.key,
        )

    async def _record(
        self,
        guide: GuideDocument,
        question_kind: PatientQuestionKind,
        outcome: PatientAnswerOutcome,
        result: ChatbotResult,
    ) -> ChatbotResult:
        response_ref = secrets.token_urlsafe(24)
        await self._usage.record_chatbot_answer(
            guide.guide_document_id,
            question_kind=question_kind,
            outcome=outcome,
            grounded_section=result.grounded_section,
            response_ref_digest=hashlib.sha256(response_ref.encode("utf-8")).hexdigest(),
        )
        return replace(result, response_ref=response_ref)

    def _model_name(self) -> str:
        return self._model.model_name if self._model is not None else "unconfigured"

    def _estimate_cost(self, input_tokens: int | None, output_tokens: int | None) -> float | None:
        if input_tokens is None or output_tokens is None or self._input_rate is None or self._output_rate is None:
            return None
        return round((input_tokens * self._input_rate + output_tokens * self._output_rate) / 1_000_000, 8)

    def _observe(
        self,
        *,
        model_name: str,
        success: bool,
        latency_ms: int,
        reason: str | None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        LOGGER.info(
            "chatbot_generation model=%s success=%s latency_ms=%s cost_usd=%s reason=%s",
            model_name,
            success,
            latency_ms,
            self._estimate_cost(input_tokens, output_tokens),
            reason or "none",
        )
