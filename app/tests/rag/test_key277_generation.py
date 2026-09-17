"""Synthetic API → durable queue → search/revalidation → model → DB evidence."""

import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from unittest.mock import AsyncMock, patch

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
from app.models.knowledge import KnowledgeDocument, KnowledgeSourceKind, KnowledgeVersion
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
from app.services.guide_generation import ESHRE_ENDOMETRIOSIS_SOURCE_URL, KEY82_GENERATION_APPROVAL, RagGuideGenerator
from app.services.guide_generation_jobs import process_next_generation
from app.tests.guide_apis.test_guide_generate import (
    GenerateGuideTestCase,
    attach_confirmed_ocr,
    attach_prescription,
    make_caution_contents,
    make_clinic,
    make_rag_sources,
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
        await make_caution_contents(self.prescription_set)
        await self._make_eshre_fixture()
        self.model = AsyncMock()
        self.model.generate.return_value = ModelAnswer(
            json.dumps({"body": "검증된 합성 교육 안내입니다.", "drug_names": []})
        )
        self.generator = RagGuideGenerator(ApprovedKnowledgeSearchService(FakeEmbeddingProvider()), self.model)
        self.flag = patch.object(config, "GUIDE_RAG_ENABLED", True)
        self.flag.start()
        self.addCleanup(self.flag.stop)

    async def _make_eshre_fixture(self) -> None:
        """자궁내막증 생활관리 고정 템플릿에 필요한 ESHRE chunk_optional 레코드를 생성한다."""
        _approved_at = datetime(2026, 9, 1, tzinfo=UTC)
        doc = await KnowledgeDocument.create(
            source_key="eshre-endometriosis-2022-fixture",
            title="ESHRE Guideline: Endometriosis (2022)",
            source_org="European Society of Human Reproduction and Embryology",
            source_url=ESHRE_ENDOMETRIOSIS_SOURCE_URL,
            source_kind=KnowledgeSourceKind.TEXT_PDF,
        )
        await KnowledgeVersion.create(
            document=doc,
            version_label="2022",
            source_sha256="b" * 64,
            source_object_key="synthetic/eshre-endometriosis-2022.pdf",
            source_mime_type="text/plain",
            extractor_version="synthetic",
            approval_status=ApprovalStatus.APPROVED,
            is_current=True,
            current_approved_key=str(doc.pk),
            chunk_optional=True,
            source_grade=SourceGrade.A,
            license_verified=True,
            approved_by="합성 검토자",
            approved_at=_approved_at,
            verified_at=_approved_at,
        )

    async def add_sources(self, *, approved=True):
        return await make_rag_sources(self.clinic.pk, approved=approved)

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
        assert self.model.generate.await_count == 2  # emergency + endo life = fixed templates
        assert await GuideSectionSourceSnapshot.all().count() == 4
        assert await GuideSafetyCheck.all().count() == 6  # model 2회(medication·caution) × pre+post + fixed 2회 × pre
        assert await GuideSection.filter(drug_caution_content_id__not_isnull=True).count() == 2  # emergency + endo life
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
        assert all(row.template_id for row in rows)
        # LIFE 섹션(자궁내막증)은 ESHRE KnowledgeVersion 템플릿("2022"), 나머지는 synthetic-v1
        life_row = next(r for r in rows if r.section_key.value == "life")
        assert life_row.version == "2022"
        assert sum(1 for r in rows if r.version == "synthetic-v1") == 3

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
        # fixed_template 섹션(emergency, endo life)은 검색을 건너뛰어 항상 fixed_approved_template
        assert await GuideSectionSourceSnapshot.filter(fallback_reason="search_infrastructure_exhausted").count() == 2
        assert await GuideSectionSourceSnapshot.filter(fallback_reason="fixed_approved_template").count() == 2
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
        assert job.block_reason == "is_current"
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
        assert job.block_reason == "hospital_scope"
        await self.assert_block_reason_response(job, "hospital_scope")
        self.model.generate.assert_not_awaited()

    async def assert_block_reason_response(self, job, reason):
        async with self.client() as client:
            result = await client.get(
                f"/api/v1/visits/{self.visit.pk}/guide/generation/{job.pk}",
                headers=await self.sign_in(self.staff),
            )
        assert result.status_code == 200
        assert result.json()["failure_reason"] == "unverified_context"
        assert result.json()["block_reason"] == reason
        assert "sections" not in result.json()

    async def test_approval_revoked_after_search_preserves_final_reason(self):
        version = await self.add_sources()
        cached = await self.generator.search.search(
            "합성",
            hospital_id=self.clinic.pk,
            allowed_sections=frozenset({"medication"}),
            searched_at=date.today(),
        )
        await KnowledgeVersion.filter(pk=version.pk).update(approval_status=ApprovalStatus.DRAFT)
        self.generator.search.search = AsyncMock(return_value=cached)
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failed_at is not None
        assert job.block_reason == "approval_status"
        await self.assert_block_reason_response(job, "approval_status")
        self.model.generate.assert_not_awaited()

    async def test_completed_job_does_not_return_later_regeneration(self):
        first = await self.request_job()
        await self.run_job()
        await first.refresh_from_db()
        first_version = first.result_version
        assert first_version is not None
        second = await self.request_job()
        await self.run_job()
        await second.refresh_from_db()
        assert second.result_version == first_version + 1
        async with self.client() as client:
            headers = await self.sign_in(self.staff)
            old = await client.get(f"/api/v1/visits/{self.visit.pk}/guide/generation/{first.pk}", headers=headers)
            latest = await client.get(f"/api/v1/visits/{self.visit.pk}/guide/generation/{second.pk}", headers=headers)
        assert old.status_code == 200
        assert old.json()["state"] == "superseded"
        assert old.json()["result_version"] == first_version
        assert "sections" not in old.json()
        assert latest.status_code == 200
        assert latest.json()["version"] == second.result_version

    async def test_completed_job_with_unknown_result_identity_is_not_current(self):
        job = await self.request_job()
        await self.run_job()
        await GuideGenerationJob.filter(pk=job.pk).update(result_guide_document_id=None, result_version=None)
        async with self.client() as client:
            result = await client.get(
                f"/api/v1/visits/{self.visit.pk}/guide/generation/{job.pk}",
                headers=await self.sign_in(self.staff),
            )
        assert result.json()["state"] == "superseded"
        assert "sections" not in result.json()

    async def test_missing_template_approval_blocks_instead_of_default_text(self):
        # 승인 기록이 없는 템플릿(DRAFT·approved_key 없음)은 등급 무관하게 차단된다.
        await DrugCautionContent.all().update(approval_status=ApprovalStatus.DRAFT, approved_key=None)
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "unverified_context"
        assert await GuideDocument.all().count() == 0
        self.model.generate.assert_not_awaited()

    async def test_a_grade_emergency_without_physician_review_generates_successfully(self):
        """KEY-352: A등급 emergency는 physician_review 없이도 생성을 통과한다."""
        await DrugCautionContent.filter(section_key=CautionSectionKey.EMERGENCY).update(physician_review=None)
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.completed_at is not None, job.failure_reason

    async def test_a_grade_emergency_unapproved_is_still_blocked(self):
        """KEY-352: physician_review가 없어도 승인 기록 없는 emergency는 차단된다."""
        await DrugCautionContent.filter(section_key=CautionSectionKey.EMERGENCY).update(
            approval_status=ApprovalStatus.DRAFT, approved_key=None
        )
        job = await self.request_job()
        await self.run_job()
        await job.refresh_from_db()
        assert job.failure_reason == "unverified_context"
        assert await GuideDocument.all().count() == 0

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
        assert job.result_version is None
        assert job.result_guide_document_id is None
        assert await GuideDocument.all().count() == 0

    async def test_approval_constant_matches_signed_decision(self):
        assert (
            KEY82_GENERATION_APPROVAL.result_sha256
            == "0a6c9161d77a65dbf860c3d4d7eaf9c0efe5ee768bced68db514f5716da87bb5"
        )
        assert KEY82_GENERATION_APPROVAL.approved_by == "이희진"
        assert KEY82_GENERATION_APPROVAL.approved_at == date(2026, 9, 10)
