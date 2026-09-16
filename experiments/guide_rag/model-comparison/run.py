"""Fixed-fixture comparison; candidate ranking only, never generation admission."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import date
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=BASE.parents[1])
    parser.add_argument("--reranker-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    reranker_path = args.reranker_path.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(BASE))
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        ENV="local",
        DB_PASSWORD="synthetic-only",
        OMP_NUM_THREADS="2",
    )
    # Enter before product imports so the user's .env is never read.
    with tempfile.TemporaryDirectory() as work:
        previous = Path.cwd()
        try:
            os.chdir(work)
            run(repo, reranker_path, output)
        finally:
            os.chdir(previous)


def run(repo, reranker_path, output):
    import torch

    # Optional evaluation dependency; the normal app CI does not install Kiwi.
    from kiwipiepy import Kiwi  # type: ignore[import-not-found]
    from sentence_transformers import SentenceTransformer
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from app.models.catalog import ApprovalStatus, SourceGrade
    from app.services.knowledge_search import (
        EMBEDDING_MODEL,
        EMBEDDING_MODEL_REVISION,
        KnowledgeChunk,
        KnowledgeSearchScope,
        _eligible,
    )
    from experiments.guide_rag.hybrid_search import bm25, search, tokenize

    torch.set_num_threads(2)
    kiwi = Kiwi(num_workers=1)

    @lru_cache(maxsize=256)
    def korean_tokens(text):
        normalized = unicodedata.normalize("NFKC", text).casefold()
        return [
            t.form
            for t in kiwi.tokenize(normalized)
            if t.tag.startswith(("N", "V")) or t.tag in {"MAG", "SL", "SN", "XR"}
        ]

    assert "식생활" in korean_tokens("식생활을")
    assert "식생활" in korean_tokens("식생활에")
    assert "을" not in korean_tokens("식생활을")
    fixture = json.loads((BASE / "hybrid-fixture.json").read_text())
    queries = [{**q, "group": "original"} for q in fixture["queries"]]
    queries += [
        {**q, "group": "challenge"} for q in json.loads((BASE / "alternative-fixture-queries.json").read_text())
    ]
    dense = SentenceTransformer(
        EMBEDDING_MODEL,
        revision=EMBEDDING_MODEL_REVISION,
        local_files_only=True,
        device="cpu",
    )
    texts = [d["body"] for d in fixture["documents"]] + [q["text"] for q in queries]
    vectors = dense.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    chunks = [
        KnowledgeChunk(
            chunk_id=d["id"],
            document_id=d["id"],
            hospital_id=d["hospital_id"],
            section_key=d["section"],
            body=d["body"],
            embedding=tuple(map(float, vectors[i])),
            approval_status=ApprovalStatus.APPROVED if d["approved"] else ApprovalStatus.DRAFT,
            is_current=d["current"],
            source_grade=SourceGrade.A,
            license_verified=d["license_verified"],
            verified_at=date(2026, 9, 1),
            review_due_at=None,
        )
        for i, d in enumerate(fixture["documents"])
    ]
    by_id = {c.chunk_id: c for c in chunks}
    manifest = json.loads((reranker_path / "evaluation-manifest.json").read_text())
    if manifest != {"repo": "BAAI/bge-reranker-v2-m3", "revision": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"}:
        raise ValueError("reranker manifest does not match the pinned experiment")
    tokenizer = AutoTokenizer.from_pretrained(str(reranker_path), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(str(reranker_path), local_files_only=True).eval()
    rows = []
    for i, q in enumerate(queries, len(chunks)):
        scope = KnowledgeSearchScope(1, frozenset({q["section"]}), date(2026, 9, 15))
        vector = tuple(map(float, vectors[i]))
        rankings, pools, durations = {}, {}, {}
        eligible = [c for c in chunks if _eligible(c, scope)]
        for label, lex in [("simple", tokenize), ("kiwi", korean_tokens)]:
            rankings[f"bm25_{label}"] = [key for key, _ in bm25(q["text"], eligible, tokenizer=lex)[:3]]
            started = time.perf_counter()
            found = search(
                q["text"],
                vector,
                chunks,
                scope,
                dense_threshold=0,
                top_k=10,
                candidate_k=10,
                lexical_tokenizer=lex,
            )
            durations[f"hybrid_{label}"] = time.perf_counter() - started
            pools[label] = [c.chunk_id for c in found.candidates]
            rankings[f"hybrid_{label}"] = pools[label][:3]
        # Score each unique admitted candidate once; reuse identical pair scores
        # across both fusion pools for a fair deterministic comparison.
        union = sorted(set(pools["simple"]) | set(pools["kiwi"]))
        started = time.perf_counter()
        scores = {}
        with torch.inference_mode():
            for offset in range(0, len(union), 4):
                keys = union[offset : offset + 4]
                inputs = tokenizer(
                    [[q["text"], by_id[k].body] for k in keys],
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                )
                values = model(**inputs).logits.reshape(-1).float()
                assert len(values) == len(keys) and torch.isfinite(values).all()
                scores.update(zip(keys, values.tolist(), strict=True))
        durations["rerank_unique_pool"] = time.perf_counter() - started
        for label, pool in pools.items():
            rankings[f"hybrid_{label}_rerank"] = sorted(pool, key=lambda k: (-scores[k], k))[:3]
        forbidden = {"draft", "other-hospital", "old", "license"}
        assert all(not forbidden.intersection(ids) for ids in rankings.values())
        assert all(set(ids) <= set(by_id) for ids in rankings.values())
        rows.append(
            {
                **q,
                "rankings": rankings,
                "pools": pools,
                "reranker_logits": scores,
                "seconds": durations,
                "kiwi_query_tokens": korean_tokens(q["text"]),
            }
        )
        print(q["id"], "done", flush=True)
    groups = summarize(rows)
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [
            BASE / "hybrid-fixture.json",
            BASE / "alternative-fixture-queries.json",
            BASE / "hybrid_search.py",
            Path(__file__),
            repo / "app/services/knowledge_search.py",
        ]
    }
    result = {
        "dense": {"repo": EMBEDDING_MODEL, "revision": EMBEDDING_MODEL_REVISION},
        "reranker": manifest,
        "source_revision": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        "versions": {
            name: version(name)
            for name in [
                "kiwipiepy",
                "kiwipiepy_model",
                "torch",
                "transformers",
                "sentence-transformers",
            ]
        },
        "hashes": hashes,
        "config": {
            "dense_threshold": 0,
            "candidate_k": 10,
            "top_k": 3,
            "rrf_constant": 60,
            "rerank_max_length": 512,
            "rerank_rejection_threshold": None,
            "device": "cpu",
            "threads": 2,
        },
        "forbidden_candidates": 0,
        "groups": groups,
        "rows": rows,
    }
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    lines = [
        "# 안내문 RAG: 한국어 분석 · 재순위 모델 실측",
        "",
        "합성 주제 문서 16개, 질의 20개(정답 있음 15개·없음 5개). 실제 의료 근거나 생성 안내문 품질 평가가 아닙니다.",
        "",
        "Dense는 기존 고정 MiniLM, 한국어 분석은 Kiwi, 재순위 모델은 BAAI/bge-reranker-v2-m3입니다. 모델 버전과 파일 해시는 results.json에 기록했습니다.",
        "",
        "모든 Hybrid는 Dense 후보 임계값 0, BM25 양수 점수, RRF 60, 후보 최대 10개, 최종 최대 3개로 통일했습니다. 임계값 0은 후보 회수 실험값이며 운영 적용 제안이 아닙니다.",
        "",
    ]
    for group, methods in groups.items():
        lines += [
            f"## {group}",
            "",
            "| 조합 | 정답 Top3 | 정답 1위 | MRR@3 | 근거 없는 질문에 후보 반환 |",
            "|---|---:|---:|---:|---:|",
        ]
        for method, m in methods.items():
            lines.append(
                f"| {method} | {m['hit_at_3']}/{m['positive_count']} | {m['top1']}/{m['positive_count']} | {m['mrr']:.3f} | {m['negative_with_candidates']}/{m['negative_count']} |"
            )
        lines.append("")
    lines += [
        "## 해석 범위",
        "",
        "- BM25 단독 행은 형태소 분석의 효과를 분리해서 보는 보조 비교입니다.",
        "- 재순위 모델은 후보 순서만 변경합니다. 별도 거절 기준을 적용하지 않았으므로 근거 없는 질문에도 후보를 반환할 수 있습니다. 원시 점수는 확률이 아닙니다.",
        "- 미승인·타 병원·과거 버전·라이선스 미확인 후보 반환은 모든 조합에서 0건입니다.",
        "- 같은 작은 합성셋으로 반복 탐색했습니다. 독립 검증이나 임상 성능 증명이 아니며, 실제 승인 문서의 혼동 사례로 다시 평가해야 합니다.",
        "- BGE-M3 Dense+Sparse 자체는 이번에 실행하지 않았습니다. 기존 Dense에 한국어 BM25와 reranker를 추가하는 조합을 비교했습니다.",
        "- 운영 코드·DB·안내문 생성 경로·챗봇 설정은 변경하지 않았습니다.",
        "",
        "## 질의별 순위",
        "",
    ]
    for r in rows:
        lines += [
            f"### {r['id']}: {r['text']}",
            "",
            f"정답: {', '.join(r['relevant']) or '없음'}",
            "",
        ]
        lines += [f"- {k}: {', '.join(v) or '없음'}" for k, v in r["rankings"].items()]
        lines.append("")
    (output / "report.md").write_text("\n".join(lines).rstrip() + "\n")
    print(json.dumps(groups, ensure_ascii=False), flush=True)


def summarize(rows):
    groups = {}
    for group in ["original", "challenge", "all"]:
        subset = [r for r in rows if group == "all" or r["group"] == group]
        positive = [r for r in subset if r["relevant"]]
        negative = [r for r in subset if not r["relevant"]]
        groups[group] = {}
        for method in rows[0]["rankings"]:
            ranks = [
                next(
                    (j for j, key in enumerate(r["rankings"][method], 1) if key in r["relevant"]),
                    0,
                )
                for r in positive
            ]
            groups[group][method] = {
                "positive_count": len(positive),
                "hit_at_3": sum(rank > 0 for rank in ranks),
                "top1": sum(rank == 1 for rank in ranks),
                "mrr": sum(1 / rank if rank else 0 for rank in ranks) / len(ranks),
                "negative_count": len(negative),
                "negative_with_candidates": sum(bool(r["rankings"][method]) for r in negative),
            }
    return groups


if __name__ == "__main__":
    main()
