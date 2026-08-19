import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.patient.contracts import ApprovedGuidanceBundle, ApprovedKnowledge


@dataclass(frozen=True)
class ChatEvidence:
    source_id: str
    title: str
    source_label: str
    excerpt: str


@dataclass(frozen=True)
class GroundedAnswer:
    answer: str
    evidence: tuple[ChatEvidence, ...]
    limitation: str


class ApprovedKnowledgeChatbot:
    """Extractive RAG that cannot read drafts, OCR, or original documents."""

    LIMITATION = "승인된 안내와 지식 범위에서만 답변드려요. 진단이나 처방 변경은 의료진에게 문의해 주세요."

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {term.lower() for term in re.findall(r"[0-9A-Za-z가-힣]{2,}", text)}

    def answer(self, question: str, bundle: ApprovedGuidanceBundle) -> GroundedAnswer:
        query_terms = self._terms(question)
        ranked: list[tuple[int, ApprovedKnowledge]] = []
        for chunk in bundle.knowledge:
            content_terms = self._terms(f"{chunk.title} {chunk.content}")
            score = len(query_terms & content_terms)
            if score:
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        selected = [item[1] for item in ranked[:2]]
        if not selected:
            return GroundedAnswer(
                answer="승인된 안내에서 이 질문에 대한 내용을 찾지 못했어요. 병원에 문의해 주세요.",
                evidence=(),
                limitation=self.LIMITATION,
            )
        evidence = tuple(
            ChatEvidence(
                source_id=item.id,
                title=item.title,
                source_label=item.source_label,
                excerpt=item.content[:180],
            )
            for item in selected
        )
        answer = "\n\n".join(item.content for item in selected)
        return GroundedAnswer(answer=answer, evidence=evidence, limitation=self.LIMITATION)

    async def stream(self, question: str, bundle: ApprovedGuidanceBundle) -> AsyncIterator[str]:
        grounded = self.answer(question, bundle)
        words = grounded.answer.split(" ")
        for index, word in enumerate(words):
            yield word + (" " if index < len(words) - 1 else "")
