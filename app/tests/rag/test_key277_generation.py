"""Synthetic API → durable queue → search/revalidation → model → DB evidence."""

import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from tortoise.timezone import now

from app.core import config
from app.models.catalog import (
    ApprovalStatus,
    CautionSectionKey,
    DrugCatalog,
    DrugCautionContent,
    PrescriptionSet,
    SetDisease,
    SourceGrade,
)
from app.models.knowledge import KnowledgeChunkRecord, KnowledgeDocument, KnowledgeSourceKind, KnowledgeVersion
from app.models.prescriptions import PrescriptionItem
from app.models.visits import (
    GuideDocument,
    GuideGenerationJob,
    GuideSafetyCheck,
    GuideSection,
    GuideSectionSourceSnapshot,
)
from app.services.approved_knowledge_search import (
    ApprovedKnowledgeOutcome,
    ApprovedKnowledgeResult,
    ApprovedKnowledgeSearchService,
)
from app.services.chatbot import ChatModelError, ModelAnswer
from app.services.guide_generation import KEY82_GENERATION_APPROVAL, RagGuideGenerator
from app.services.guide_generation_jobs import process_next_generation
from app.services.knowledge_search import EMBEDDING_DIMENSION, EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION
from app.tests.guide_apis.test_guide_generate import (
    GenerateGuideTestCase,
    attach_confirmed_ocr,
    attach_prescription,
    make_clinic,
    make_staff,
    make_visit,
)
from app.tests.rag.test_key276_approved_knowledge_pipeline import FakeEmbeddingProvider


class TestRagGenerationPipeline(GenerateGuideTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.clinic = await make_clinic()
        self.staff = await make_staff(self.clinic, "synthetic-rag", ["staff"])
        self.visit = await make_visit(self.clinic)
        await attach_confirmed_ocr(self.visit, self.staff.pk)
        await attach_prescription(self.visit, [("합성처방정", "1일 1회", 28)])
        await DrugCatalog.create(name="합성처방정")
        self.prescription_set = await PrescriptionSet.create(
            name="자궁내막증 · 비잔 (계속)", disease=SetDisease.ENDOMETRIOSIS
        )
        for section in CautionSectionKey:
            body = f"합성 승인 안내 {section.value}"
            await DrugCautionContent.create(
                prescription_set=self.prescription_set,
                section_key=section,
                body=body,
                source_name="합성 문서",
                source_org="합성 기관",
                source_url="https://example.invalid/approved",
                verified_at=date(2026, 9, 1),
                content_version="synthetic-v1",
                source_grade=SourceGrade.A,
                approval_status=ApprovalStatus.APPROVED,
                approved_key=f"{self.prescription_set.pk}:{section.value}",
                physician_review={
                    "reviewer": "합성 검토자",
                    "hospital": "합성 기관",
                    "reviewed_at": "2026-09-01",
                    "body_sha256": sha256(body.encode()).hexdigest(),
                },
            )
        self.model = AsyncMock()
        self.model.generate.return_value = ModelAnswer(
            json.dumps({"body": "검증된 합성 교육 안내입니다.", "drug_names": []})
        )
        self.generator = RagGuideGenerator(ApprovedKnowledgeSearchService(FakeEmbeddingProvider()), self.model)
        self.flag = patch.object(config, "GUIDE_RAG_ENABLED", True)
        self.flag.start()
        self.addCleanup(self.flag.stop)

    async def add_sources(self, *, approved=True):
        document = await KnowledgeDocument.create(
            source_key=str(uuid4()),
            title="합성 자료",
            source_org="합성 기관",
            source_url="https://example.invalid/source",
            source_kind=KnowledgeSourceKind.TEXT_PDF,
            hospital_id=self.clinic.pk,
        )
        version = await KnowledgeVersion.create(
            document=document,
            version_label="synthetic-v1",
            source_sha256="a" * 64,
            source_object_key="synthetic/source.pdf",
            source_mime_type="application/pdf",
            extractor_version="synthetic",
            approval_status=ApprovalStatus.APPROVED if approved else ApprovalStatus.DRAFT,
            is_current=approved,
            current_approved_key=str(document.pk) if approved else None,
            source_grade=SourceGrade.A,
            license_verified=True,
            approved_by="합성 검토자",
            approved_at=datetime(2026, 9, 1, tzinfo=UTC),
            verified_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        for section in CautionSectionKey:
            body = f"검증된 합성 근거 {section.value}"
            await KnowledgeChunkRecord.create(
                version=version,
                section_key=section.value,
                position=list(CautionSectionKey).index(section),
                body=body,
                body_sha256=sha256(body.encode()).hexdigest(),
                embedding=[1.0] + [0.0] * (EMBEDDING_DIMENSION - 1),
                embedding_model=EMBEDDING_MODEL,
                embedding_revision=EMBEDDING_MODEL_REVISION,
                embedding_dimension=EMBEDDING_DIMENSION,
            )
        return version

    async def request_job(self):
        async with self.client() as client:
            response = await client.post(
                f"/api/v1/visits/{self.visit.pk}/guide/generate", headers=await self.sign_in(self.staff)
            )
        assert response.status_code == 202, response.text
        return await GuideGenerationJob.get(job_id=response.json()["job_id"])

    async def run_job(self):
        with patch("app.services.guide_generation_jobs.build_generator", return_value=self.generator):
            assert await process_next_generation()

    async def finish_retries(self, job):
        for _ in range(3):
            await GuideGenerationJob.filter(job_id=job.pk).update(available_at=now() - timedelta(seconds=1))
            await self.run_job()
        await job.refresh_from_db()

    async def test_normal_generation_persists_sources_and_has_no_patient_identifiers(self):
        await self.add_sources()
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.completed_at is not None, job.failure_reason
        assert self.model.generate.await_count == 3  # emergency stays approved fixed text
        assert await GuideSectionSourceSnapshot.all().count() == 4
        assert await GuideSafetyCheck.all().count() == 7
        assert await GuideSection.filter(drug_caution_content_id__not_isnull=True).count() == 1
        for call in self.model.generate.await_args_list:
            assert "합성환자" not in call.kwargs["prompt"]
            assert "01012345678" not in call.kwargs["prompt"]
            assert "1990-05-15" not in call.kwargs["prompt"]
            assert "SYN-GEN-01" not in call.kwargs["prompt"]

    async def test_no_evidence_uses_only_approved_versioned_templates(self):
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.completed_at is not None, job.failure_reason
        self.model.generate.assert_not_awaited()
        rows = await GuideSectionSourceSnapshot.all()
        assert len(rows) == 4
        assert all(row.template_id and row.version == "synthetic-v1" for row in rows)

    async def test_unapproved_sources_never_reach_model(self):
        await self.add_sources(approved=False)
        await self.test_no_evidence_uses_only_approved_versioned_templates()

    async def test_source_conflict_blocks_without_fallback(self):
        self.generator.search.search = AsyncMock(
            return_value=ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.SOURCE_CONFLICT)
        )
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "source_conflict"
        assert await GuideDocument.all().count() == 0
        self.model.generate.assert_not_awaited()

    async def test_index_error_blocks_without_fallback(self):
        self.generator.search.search = AsyncMock(
            return_value=ApprovedKnowledgeResult(ApprovedKnowledgeOutcome.INDEX_INVALID)
        )
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "index_invalid"
        assert await GuideDocument.all().count() == 0

    async def test_search_outage_retries_then_records_template_reason(self):
        self.generator.search.search = AsyncMock(side_effect=TimeoutError("synthetic"))
        job = await self.request_job()
        await self.finish_retries(job)
        assert job.completed_at is not None, job.failure_reason
        assert job.attempts == 3
        assert await GuideSectionSourceSnapshot.filter(fallback_reason="search_infrastructure_exhausted").count() == 4
        self.model.generate.assert_not_awaited()

    async def test_llm_failure_exhausts_then_fails_without_partial_guide(self):
        await self.add_sources()
        self.model.generate.side_effect = ChatModelError("synthetic_timeout")
        job = await self.request_job()
        await self.finish_retries(job)
        assert job.failed_at is not None
        assert job.failure_reason == "llm_failure"
        assert await GuideDocument.all().count() == 0
        assert await GuideSectionSourceSnapshot.all().count() == 0

    async def test_safety_block_cannot_save_model_text(self):
        await self.add_sources()
        self.model.generate.return_value = ModelAnswer(json.dumps({"body": "약 복용을 중단하세요.", "drug_names": []}))
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "DRUG_CHANGE_ADVICE"
        assert await GuideDocument.all().count() == 0
        check = await GuideSafetyCheck.get(generation_job=job)
        assert check.verdict.value == "BLOCK"
        assert check.stage.value == "POST_GENERATE"
        assert check.guide_document_id is None
        assert check.section_key.value == "medication"

    async def test_changed_prescription_invalidates_queued_request(self):
        job = await self.request_job()
        await PrescriptionItem.all().update(frequency="합성 변경")
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "input_changed"
        self.model.generate.assert_not_awaited()

    async def test_duplicate_requests_reuse_one_job(self):
        first = await self.request_job()
        second = await self.request_job()
        assert first.pk == second.pk
        assert await GuideGenerationJob.all().count() == 1

    async def test_poll_is_hospital_scoped_and_returns_saved_sources(self):
        await self.add_sources()
        job = await self.request_job()
        other = await make_staff(await make_clinic("다른 합성 의원"), "other-rag", ["doctor"])
        path = f"/api/v1/visits/{self.visit.pk}/guide/generation/{job.pk}"
        async with self.client() as client:
            denied = await client.get(path, headers=await self.sign_in(other))
            assert denied.status_code == 404
            pending = await client.get(path, headers=await self.sign_in(self.staff))
            assert pending.json()["state"] == "queued"
            await self.run_job()
            ready = await client.get(path, headers=await self.sign_in(self.staff))
        assert ready.status_code == 200, ready.text
        assert len([s for s in ready.json()["sections"] if s["sources"]]) == 4

    async def test_prescription_changed_during_model_call_cannot_save(self):
        await self.add_sources()

        async def change_input(**kwargs):
            await PrescriptionItem.all().update(frequency="합성 변경")
            return ModelAnswer(json.dumps({"body": "합성 교육 안내입니다.", "drug_names": []}))

        self.model.generate.side_effect = change_input
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "input_changed"
        assert await GuideDocument.all().count() == 0

    async def test_source_revoked_during_model_call_cannot_save(self):
        version = await self.add_sources()

        async def revoke(**kwargs):
            await KnowledgeVersion.filter(pk=version.pk).update(is_current=False)
            return ModelAnswer(json.dumps({"body": "합성 교육 안내입니다.", "drug_names": []}))

        self.model.generate.side_effect = revoke
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "unverified_context"
        assert await GuideDocument.all().count() == 0

    async def test_out_of_scope_cached_hit_cannot_reach_model(self):
        version = await self.add_sources()
        cached = await self.generator.search.search(
            "합성",
            hospital_id=self.clinic.pk,
            allowed_sections=frozenset({"medication"}),
            searched_at=date.today(),
        )
        await KnowledgeDocument.filter(pk=version.document_id).update(hospital_id=self.clinic.pk + 1)
        self.generator.search.search = AsyncMock(return_value=cached)
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "unverified_context"
        self.model.generate.assert_not_awaited()

    async def test_missing_template_approval_blocks_instead_of_default_text(self):
        await DrugCautionContent.all().update(physician_review=None)
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "unverified_context"
        assert await GuideDocument.all().count() == 0
        self.model.generate.assert_not_awaited()

    async def test_unknown_free_text_drug_does_not_enter_prompt(self):
        await PrescriptionItem.all().update(name="합성환자 01012345678")
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "unrecognized_prescription"
        self.model.generate.assert_not_awaited()

    async def test_model_cannot_hide_known_unprescribed_drug_by_omitting_metadata(self):
        await self.add_sources()
        await DrugCatalog.create(name="합성비처방정 20mg")
        self.model.generate.return_value = ModelAnswer(json.dumps({"body": "합성비처방정을 드세요.", "drug_names": []}))
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "EXTRA_DRUG"
        assert await GuideDocument.all().count() == 0

    async def test_no_provider_configuration_still_allows_exact_approved_fallback(self):
        self.generator.model = None
        await self.test_no_evidence_uses_only_approved_versioned_templates()

    async def test_rag_preserves_prescription_facts_and_configured_doctor_copy(self):
        from app.models.catalog import DoctorGuideCopy

        await self.add_sources()
        await DoctorGuideCopy.create(
            hospital_id=self.clinic.pk,
            doctor_id=None,
            prescription_set=self.prescription_set,
            section_key=CautionSectionKey.MEDICATION,
            body="의료진이 정한 합성 문구",
        )
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.completed_at is not None, job.failure_reason
        section = await GuideSection.get(section_key="medication")
        assert "합성처방정 · 1일 1회 · 28일분" in section.generated_body
        assert "검증된 합성 교육 안내입니다." in section.generated_body
        assert "의료진이 정한 합성 문구" in section.edited_body
        assert "합성처방정 · 1일 1회 · 28일분" in section.body
        assert "의료진이 정한 합성 문구" not in section.generated_body

    async def test_template_guidance_is_fixed_but_confirmed_prescription_facts_are_kept(self):
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.completed_at is not None, job.failure_reason
        section = await GuideSection.get(section_key="medication")
        assert "합성처방정 · 1일 1회 · 28일분" in section.body
        assert section.body.endswith("합성 승인 안내 medication")
        snapshot = await GuideSectionSourceSnapshot.get(guide_section=section)
        assert snapshot.body_sha256 == sha256("합성 승인 안내 medication".encode()).hexdigest()

    async def test_snapshot_failure_rolls_back_guide_and_completed_job(self):
        await self.add_sources()
        job = await self.request_job()
        with patch("app.services.guide_source_snapshots.persist_guide_sources", side_effect=RuntimeError("synthetic")):
            await self.run_job()
        await job.refresh_from_db()
        assert job.failed_at is not None
        assert job.completed_at is None
        assert await GuideDocument.all().count() == 0

    async def test_approval_constant_matches_signed_decision(self):
        assert (
            KEY82_GENERATION_APPROVAL.result_sha256
            == "0a6c9161d77a65dbf860c3d4d7eaf9c0efe5ee768bced68db514f5716da87bb5"
        )
        assert KEY82_GENERATION_APPROVAL.approved_by == "이희진"
        assert KEY82_GENERATION_APPROVAL.approved_at == date(2026, 9, 10)
