import unittest
from dataclasses import replace
from datetime import date

from app.models.catalog import ApprovalStatus, SourceGrade
from app.services.knowledge_search import KnowledgeChunk, KnowledgeSearchScope
from experiments.guide_rag.hybrid_search import bm25, rrf, search, weighted_fusion

V = (1.0,) + (0.0,) * 383
ORTHOGONAL = (0.0, 1.0) + (0.0,) * 382
SCOPE = KnowledgeSearchScope(1, frozenset({"life"}), date(2026, 9, 15))


def chunk(key="a", **changes):
    base = KnowledgeChunk(
        key,
        key,
        None,
        "life",
        "테스트 수면",
        V,
        ApprovalStatus.APPROVED,
        True,
        SourceGrade.A,
        True,
        date(2026, 9, 1),
        None,
    )
    return replace(base, **changes)


class HybridTests(unittest.TestCase):
    def test_custom_tokenizer_recovers_inflected_word(self):
        def lexical(text):
            return [word.removesuffix("을") for word in text.split()]

        safe = chunk("safe", body="식생활", embedding=ORTHOGONAL)
        self.assertEqual(search("식생활을", V, [safe], SCOPE).candidates, ())
        result = search("식생활을", V, [safe], SCOPE, lexical_tokenizer=lexical)
        self.assertEqual([c.chunk_id for c in result.candidates], ["safe"])

    def test_custom_tokenizer_cannot_bypass_eligibility(self):
        def lexical(text):
            return ["always-match"]

        unsafe = chunk("unsafe", hospital_id=99)
        result = search("anything", V, [unsafe], SCOPE, lexical_tokenizer=lexical)
        self.assertEqual(result.candidates, ())

    def test_weighted_fusion_hand_calculation(self):
        result = dict(weighted_fusion({"a": 0.8, "b": 0.4}, {"b": 10}, 0.7))
        self.assertAlmostEqual(result["a"], 0.7)
        self.assertAlmostEqual(result["b"], 0.65)

    def test_weighted_fusion_scale_invariance(self):
        self.assertEqual(
            weighted_fusion({"a": 0.8}, {"b": 10}, 0.5),
            weighted_fusion({"a": 8}, {"b": 1000}, 0.5),
        )

    def test_weighted_endpoints_and_empty_scores(self):
        self.assertEqual(weighted_fusion({"a": 0.8}, {"b": 10}, 1), [("a", 1)])
        self.assertEqual(weighted_fusion({"a": 0.8}, {"b": 10}, 0), [("b", 1)])
        self.assertEqual(weighted_fusion({}, {}, 0.5), [])
        self.assertEqual(weighted_fusion({"a": 0}, {}, 0.5), [])

    def test_weighted_rejects_bad_numbers(self):
        for weight in [-1, 2, float("nan")]:
            with self.assertRaises(ValueError):
                weighted_fusion({}, {}, weight)
        for score in [-1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                weighted_fusion({"a": score}, {}, 0.5)

    def test_wide_fusion_still_blocks_unsafe_candidates(self):
        for fusion in ["rrf", "weighted"]:
            with self.subTest(fusion=fusion):
                safe = chunk("safe", embedding=ORTHOGONAL)
                bad = chunk("bad", hospital_id=99)
                result = search("수면", V, [safe, bad], SCOPE, dense_threshold=0, fusion=fusion)
                self.assertEqual([c.chunk_id for c in result.candidates], ["safe"])
                conflict = [
                    chunk("a", claim_key="rule", claim_value="A"),
                    chunk("b", claim_key="rule", claim_value="B"),
                ]
                self.assertEqual(
                    search("수면", V, conflict, SCOPE, dense_threshold=0, fusion=fusion).outcome,
                    "source_conflict",
                )
                self.assertEqual(
                    search(
                        "수면",
                        V,
                        [chunk(embedding=(1.0,))],
                        SCOPE,
                        dense_threshold=0,
                        fusion=fusion,
                    ).outcome,
                    "index_invalid",
                )

    def test_filters_are_shared(self):
        for change in [
            dict(approval_status=ApprovalStatus.DRAFT),
            dict(hospital_id=99),
            dict(section_key="medication"),
            dict(is_current=False),
            dict(license_verified=False),
            dict(review_due_at=date(2026, 9, 14)),
            dict(source_grade=SourceGrade.C),
        ]:
            with self.subTest(change=change):
                result = search("수면", V, [chunk(**change)], SCOPE)
                self.assertEqual(result.outcome, "no_evidence")

    def test_lexical_can_recover_low_dense_match(self):
        result = search("수면", V, [chunk(embedding=ORTHOGONAL)], SCOPE)
        self.assertEqual(result.candidates[0].chunk_id, "a")
        self.assertIsNone(result.candidates[0].dense_score)
        self.assertGreater(result.candidates[0].sparse_score, 0)

    def test_invalid_embedding_cannot_be_bypassed(self):
        for vector in [(1.0,), (0.0,) * 384]:
            self.assertEqual(
                search("수면", V, [chunk(embedding=vector)], SCOPE).outcome,
                "index_invalid",
            )

    def test_conflict_below_sparse_cutoff_blocks(self):
        chunks = [chunk(str(i), embedding=ORTHOGONAL) for i in range(12)]
        chunks += [
            chunk("z", embedding=ORTHOGONAL, claim_key="same", claim_value="A"),
            chunk("zz", embedding=ORTHOGONAL, claim_key="same", claim_value="B"),
        ]
        self.assertEqual(search("수면", V, chunks, SCOPE).outcome, "source_conflict")

    def test_rrf_rewards_agreement(self):
        self.assertEqual(rrf([["a", "b"], ["b", "c"]])[0][0], "b")

    def test_rrf_rejects_duplicate_votes(self):
        with self.assertRaises(ValueError):
            rrf([["a", "a"]])

    def test_no_evidence(self):
        self.assertEqual(
            search("우주선", V, [chunk(embedding=ORTHOGONAL)], SCOPE).outcome,
            "no_evidence",
        )

    def test_bm25_hand_calculation(self):
        # N=1, df=1, tf=1 and dl=avgdl => score=ln(4/3).
        import math

        self.assertAlmostEqual(bm25("수면", [chunk(body="수면")])[0][1], math.log(4 / 3))

    def test_input_order_does_not_change_ties(self):
        docs = [chunk("b"), chunk("a")]
        self.assertEqual(
            search("수면", V, docs, SCOPE),
            search("수면", V, list(reversed(docs)), SCOPE),
        )

    def test_duplicate_chunk_ids_rejected(self):
        with self.assertRaises(ValueError):
            search("수면", V, [chunk(), chunk()], SCOPE)


if __name__ == "__main__":
    unittest.main()
