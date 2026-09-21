"""KEY-371: PCOS 생활관리 생성 E2E — RAG 경로 진입 및 출처·버전·확인일 저장 검증."""

import json
from unittest.mock import AsyncMock, patch

from app.core import config
from app.models.catalog import DrugCatalog, PrescriptionSet, SetDisease
from app.models.prescriptions import Prescription, PrescriptionItem
from app.models.visits import GuideDocument, GuideGenerationJob, GuideSectionKey, GuideSectionSourceSnapshot
from app.services.approved_knowledge_search import ApprovedKnowledgeSearchService
from app.services.chatbot import ModelAnswer
from app.services.guide_generation import RagGuideGenerator
from app.services.guide_generation_jobs import process_next_generation
from app.tests.guide_apis.test_guide_generate import (
    GenerateGuideTestCase,
    attach_confirmed_ocr,
    make_caution_contents,
    make_clinic,
    make_rag_sources,
    make_staff,
    make_visit,
)
from app.tests.rag.test_key276_approved_knowledge_pipeline import FakeEmbeddingProvider

_PCOS_SET_NAME = "PCOS · 합성처방정"


class TestPcosLifeRagGeneration(GenerateGuideTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.clinic = await make_clinic()
        self.staff = await make_staff(self.clinic, "synthetic-pcos-rag", ["staff"])
        self.visit = await make_visit(self.clinic)
        await attach_confirmed_ocr(self.visit, self.staff.pk)
        await DrugCatalog.create(name="합성처방정")
        # attach_prescription은 처방 세트 이름이 하드코딩돼 있어 PCOS 세트와 이름이
        # 어긋난다. 처방과 세트 이름을 일치시키기 위해 직접 생성한다.
        self.prescription_set = await PrescriptionSet.create(name=_PCOS_SET_NAME, disease=SetDisease.PCOS)
        prescription = await Prescription.create(visit=self.visit, prescription_set=_PCOS_SET_NAME)
        await PrescriptionItem.create(
            prescription=prescription, name="합성처방정", frequency="1일 1회", duration_days=28
        )
        await make_caution_contents(self.prescription_set)
        self.model = AsyncMock()
        self.model.generate.return_value = ModelAnswer(
            json.dumps({"body": "검증된 합성 PCOS 교육 안내입니다.", "drug_names": []})
        )
        self.generator = RagGuideGenerator(ApprovedKnowledgeSearchService(FakeEmbeddingProvider()), self.model)
        self.flag = patch.object(config, "GUIDE_RAG_ENABLED", True)
        self.flag.start()
        self.addCleanup(self.flag.stop)

    async def _request_job(self):
        async with self.client() as client:
            response = await client.post(
                f"/api/v1/visits/{self.visit.pk}/guide/generate",
                headers=await self.sign_in(self.staff),
            )
        assert response.status_code == 202, response.text
        return await GuideGenerationJob.get(job_id=response.json()["job_id"])

    async def _run_job(self):
        with patch("app.services.guide_generation_jobs.build_generator", return_value=self.generator):
            assert await process_next_generation()

    async def test_pcos_life_uses_rag_path_and_stores_source_attribution(self):
        """KEY-371 인수조건 ①: PCOS 생활관리 섹션이 RAG 경로로 생성되고 출처·버전·확인일이 저장된다."""
        await make_rag_sources(self.clinic.pk)
        job = await self._request_job()
        await self._run_job()
        await job.refresh_from_db()

        assert job.completed_at is not None, job.failure_reason

        # PCOS: emergency만 fixed_template → model은 medication·caution·life 3회 호출
        assert self.model.generate.await_count == 3

        guide = await GuideDocument.get(visit=self.visit)
        life_snapshot = await GuideSectionSourceSnapshot.get(
            guide_document=guide,
            section_key=GuideSectionKey.LIFE,
            position=0,
        )

        # RAG 경로 확인 — 폴백이 아니어야 한다
        assert life_snapshot.generation_mode == "rag"
        assert life_snapshot.template_id is None
        assert life_snapshot.fallback_reason is None

        # 출처·버전·확인일 표기 확인 (인수조건 ①)
        assert life_snapshot.source_org is not None
        assert life_snapshot.version is not None
        assert life_snapshot.verified_at is not None

    async def test_pcos_life_falls_back_to_template_when_no_rag_sources(self):
        """RAG 소스 없을 때 PCOS 생활관리도 승인 폴백 템플릿으로 안전하게 처리된다."""
        job = await self._request_job()
        await self._run_job()
        await job.refresh_from_db()

        assert job.completed_at is not None, job.failure_reason
        self.model.generate.assert_not_awaited()

        guide = await GuideDocument.get(visit=self.visit)
        life_snapshot = await GuideSectionSourceSnapshot.get(
            guide_document=guide,
            section_key=GuideSectionKey.LIFE,
            position=0,
        )
        assert life_snapshot.generation_mode == "template"
        assert life_snapshot.template_id is not None
