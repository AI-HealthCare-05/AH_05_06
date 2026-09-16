"""Experimental retrieval only: existing eligibility + BM25 + equal-weight RRF.

Results are candidates, NOT admitted generation context. RRF scores are not cosine
similarities and must never be passed to the existing 0.72 validation gate.
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from app.services.knowledge_search import (
    KnowledgeChunk,
    KnowledgeSearchHit,
    KnowledgeSearchOutcome,
    KnowledgeSearchScope,
    _eligible,
    _has_conflict,
    search_approved_knowledge,
)


def tokenize(text: str) -> list[str]:
    # Deliberately simple baseline: no Korean morphology or inferred synonyms.
    return re.findall(r"[a-z0-9]+|[가-힣]+", unicodedata.normalize("NFKC", text).casefold())


def bm25(query: str, chunks: list[KnowledgeChunk], *, tokenizer=tokenize) -> list[tuple[str, float]]:
    terms = set(tokenizer(query))
    documents = [Counter(tokenizer(chunk.body)) for chunk in chunks]
    if not terms or not documents:
        return []
    lengths = [sum(doc.values()) for doc in documents]
    average = sum(lengths) / len(lengths)
    if not average:
        return []
    frequencies = Counter(term for doc in documents for term in doc)
    scores = []
    for chunk, document, length in zip(chunks, documents, lengths, strict=True):
        score = 0.0
        for term in sorted(terms):
            tf = document[term]
            if not tf:
                continue
            idf = math.log(1 + (len(documents) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average))
        if score > 0:
            scores.append((chunk.chunk_id, score))
    return sorted(scores, key=lambda row: (-row[1], row[0]))


def rrf(rankings: list[list[str]], constant: int = 60) -> list[tuple[str, float]]:
    if constant < 1:
        raise ValueError("RRF constant must be positive")
    scores: dict[str, float] = {}
    for ranking in rankings:
        if len(set(ranking)) != len(ranking):
            raise ValueError("duplicate ID in a ranking")
        for rank, key in enumerate(ranking, 1):
            scores[key] = scores.get(key, 0) + 1 / (constant + rank)
    return sorted(scores.items(), key=lambda row: (-row[1], row[0]))


@dataclass(frozen=True)
class Candidate:
    chunk_id: str
    fusion_score: float
    dense_score: float | None
    sparse_score: float | None


@dataclass(frozen=True)
class HybridResult:
    outcome: str
    candidates: tuple[Candidate, ...] = ()


def weighted_fusion(dense: dict[str, float], sparse: dict[str, float], weight: float):
    """Max-normalize each query's positive scores; missing scores are zero.

    This is rank fusion, not a confidence estimate or an abstention threshold.
    """
    if not math.isfinite(weight) or not 0 <= weight <= 1:
        raise ValueError("dense weight must be finite and within [0, 1]")
    for scores in (dense, sparse):
        if any(not math.isfinite(v) or v < 0 for v in scores.values()):
            raise ValueError("scores must be finite and nonnegative")
    dense_max = max(dense.values(), default=0) or 1
    sparse_max = max(sparse.values(), default=0) or 1
    combined = {
        key: weight * dense.get(key, 0) / dense_max + (1 - weight) * sparse.get(key, 0) / sparse_max
        for key in dense.keys() | sparse.keys()
    }
    return sorted(
        ((k, v) for k, v in combined.items() if v > 0),
        key=lambda row: (-row[1], row[0]),
    )


def search(
    text: str,
    vector: tuple[float, ...],
    chunks: list[KnowledgeChunk],
    scope: KnowledgeSearchScope,
    *,
    top_k: int = 3,
    candidate_k: int = 10,
    dense_threshold: float = 0.72,
    fusion: str = "rrf",
    dense_weight: float = 0.5,
    lexical_tokenizer=tokenize,
) -> HybridResult:
    if top_k < 1 or candidate_k < top_k:
        raise ValueError("require candidate_k >= top_k >= 1")
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise ValueError("duplicate chunk IDs")
    if fusion not in {"rrf", "weighted"}:
        raise ValueError("unknown fusion method")
    if not math.isfinite(dense_weight) or not 0 <= dense_weight <= 1:
        raise ValueError("invalid dense weight")
    # Reuse production filtering and invalid-vector/conflict behavior.
    dense = search_approved_knowledge(vector, chunks, scope, top_k=candidate_k, min_similarity=dense_threshold)
    if dense.outcome in (
        KnowledgeSearchOutcome.INDEX_INVALID,
        KnowledgeSearchOutcome.SOURCE_CONFLICT,
    ):
        return HybridResult(dense.outcome.value)
    eligible = [chunk for chunk in chunks if _eligible(chunk, scope)]
    sparse = bm25(text, eligible, tokenizer=lexical_tokenizer)
    # Check ALL sparse matches, including conflicts below the candidate cutoff.
    by_id = {chunk.chunk_id: chunk for chunk in eligible}
    union = {hit.chunk.chunk_id: hit.chunk for hit in dense.hits}
    union.update({key: by_id[key] for key, _ in sparse})
    if _has_conflict([KnowledgeSearchHit(chunk, 0.0) for chunk in union.values()]):
        return HybridResult("source_conflict")
    dense_scores = {hit.chunk.chunk_id: hit.score for hit in dense.hits}
    sparse_scores = dict(sparse[:candidate_k])
    fused = (
        rrf([list(dense_scores), list(sparse_scores)])
        if fusion == "rrf"
        else weighted_fusion(dense_scores, sparse_scores, dense_weight)
    )
    candidates = tuple(
        Candidate(key, score, dense_scores.get(key), sparse_scores.get(key)) for key, score in fused[:top_k]
    )
    return HybridResult("candidates_found" if candidates else "no_evidence", candidates)
