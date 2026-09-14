"""안내 생성 품질·의료안전 합성 시나리오 검증 — KEY-127.

docs/synthetic-data-spec.md §3~§5 시나리오 매트릭스와 연결하여
두 질환(자궁내막증·PCOS) 정상 케이스, 미등록 약물 차단,
안전 차단 사유 구분을 검증한다.

test_key277_generation.py 가 파이프라인 계약(소스 취소·처방 변경·중복 요청 등)
을 담당하므로, 이 파일은 질환 컨텍스트와 차단 사유 구분에 집중한다.
"""

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
from app.models.prescriptions import Prescription, PrescriptionItem
from app.models.visits import (
    GuideDocument,
    GuideGenerationJob,
    GuideSafetyCheck,
    SafetyCheckStage,
    SafetyCheckVerdict,
)
from app.services.approved_knowledge_search import ApprovedKnowledgeSearchService
from app.services.chatbot import ChatModelError, ModelAnswer
from app.services.guide_generation import RagGuideGenerator
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

_SAFE_ANSWER = json.dumps({"body": "검증된 합성 교육 안내입니다.", "drug_names": []})


async def _make_caution_contents(prescription_set: PrescriptionSet) -> None:
    """처방 세트의 섹션별 승인된 안내 문구를 등록한다."""
    for section in CautionSectionKey:
        body = f"합성 승인 안내 {section.value}"
        await DrugCautionContent.create(
            prescription_set=prescription_set,
            section_key=section,
            body=body,
            source_name="합성 문서",
            source_org="합성 기관",
            source_url="https://example.invalid/approved",
            verified_at=date(2026, 9, 1),
            content_version="synthetic-v1",
            source_grade=SourceGrade.A,
            approval_status=ApprovalStatus.APPROVED,
            approved_key=f"{prescription_set.pk}:{section.value}",
            physician_review={
                "reviewer": "합성 검토자",
                "hospital": "합성 기관",
                "reviewed_at": "2026-09-01",
                "body_sha256": sha256(body.encode()).hexdigest(),
            },
        )


class TestKey127QualityScenarios(GenerateGuideTestCase):
    """KEY-127: 두 질환 × 정상·안전 차단 합성 시나리오 검증."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.clinic = await make_clinic()
        self.staff = await make_staff(self.clinic, "key127-staff", ["staff"])
        self.model = AsyncMock()
        self.model.generate.return_value = ModelAnswer(_SAFE_ANSWER)
        self.flag = patch.object(config, "GUIDE_RAG_ENABLED", True)
        self.flag.start()
        self.addCleanup(self.flag.stop)

    def _generator(self) -> RagGuideGenerator:
        return RagGuideGenerator(ApprovedKnowledgeSearchService(FakeEmbeddingProvider()), self.model)

    async def _request_job(self, visit) -> GuideGenerationJob:
        async with self.client() as client:
            response = await client.post(
                f"/api/v1/visits/{visit.pk}/guide/generate",
                headers=await self.sign_in(self.staff),
            )
        assert response.status_code == 202, response.text
        return await GuideGenerationJob.get(job_id=response.json()["job_id"])

    async def _run(self) -> None:
        with patch("app.services.guide_generation_jobs.build_generator", return_value=self._generator()):
            await process_next_generation()

    async def _add_sources(self) -> KnowledgeVersion:
        """승인된 RAG 소스를 등록해 모델 호출 경로를 활성화한다.

        소스가 없으면 모든 섹션이 템플릿 폴백으로 처리되어 모델이 호출되지 않는다.
        안전 차단·LLM 실패 케이스는 모델이 실제로 호출되어야 트리거되므로
        이 헬퍼로 소스를 먼저 등록한다.
        """
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
            approval_status=ApprovalStatus.APPROVED,
            is_current=True,
            current_approved_key=str(document.pk),
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

    async def _setup_ems_visit(self, chart: str = "SYN-EMS-01"):
        """자궁내막증 비잔 처방 방문 — SYN-EMS-01 기준 케이스."""
        visit = await make_visit(self.clinic, chart)
        await attach_confirmed_ocr(visit, self.staff.pk)
        await DrugCatalog.get_or_create(name="비잔정 2mg")
        # attach_prescription 이 prescription_set="자궁내막증 · 비잔 (계속)"으로 생성함
        await attach_prescription(visit, [("비잔정 2mg", "1일 1회", 84)])
        prescription_set = await PrescriptionSet.create(
            name="자궁내막증 · 비잔 (계속)", disease=SetDisease.ENDOMETRIOSIS
        )
        await _make_caution_contents(prescription_set)
        return visit

    async def _setup_pcos_visit(self, chart: str = "SYN-PCOS-01"):
        """PCOS 야즈 처방 방문 — SYN-PCOS-01 기준 케이스."""
        visit = await make_visit(self.clinic, chart)
        await attach_confirmed_ocr(visit, self.staff.pk)
        await DrugCatalog.get_or_create(name="야즈정")
        prescription = await Prescription.create(
            visit=visit,
            prescription_set="PCOS · 야즈 (계속)",
        )
        await PrescriptionItem.create(
            prescription=prescription,
            name="야즈정",
            frequency="1일 1회",
            duration_days=84,
        )
        prescription_set = await PrescriptionSet.create(name="PCOS · 야즈 (계속)", disease=SetDisease.PCOS)
        await _make_caution_contents(prescription_set)
        return visit

    # ── 정상 케이스 ──────────────────────────────────────────────────────────

    async def test_ems_normal_generation_records_pass_safety_checks(self) -> None:
        """자궁내막증 정상 케이스(SYN-EMS-01): 안내 생성 성공 + PASS 안전검증 기록.

        RAG 소스가 있을 때 정상 생성 후 GuideSafetyCheck 에 섹션별 PASS 레코드가 남는다.
        4개 섹션 × pre + RAG 3섹션 × post = 7개 (emergency 는 고정 템플릿이라 post 없음).
        """
        visit = await self._setup_ems_visit()
        await self._add_sources()

        job = await self._request_job(visit)
        await self._run()
        await job.refresh_from_db()

        assert job.completed_at is not None, f"생성 실패: {job.failure_reason}"
        guide = await GuideDocument.get(visit_id=visit.pk)
        checks = await GuideSafetyCheck.filter(guide_document=guide).all()
        blocked = [c for c in checks if c.verdict != SafetyCheckVerdict.PASS]
        assert not blocked, f"차단된 검증이 있다 — {[c.reason_code for c in blocked]}"
        assert len(checks) == 7

    async def test_pcos_normal_generation_records_pass_safety_checks(self) -> None:
        """PCOS 정상 케이스(SYN-PCOS-01): 안내 생성 성공 + PASS 안전검증 기록."""
        visit = await self._setup_pcos_visit()
        await self._add_sources()

        job = await self._request_job(visit)
        await self._run()
        await job.refresh_from_db()

        assert job.completed_at is not None, f"생성 실패: {job.failure_reason}"
        guide = await GuideDocument.get(visit_id=visit.pk)
        checks = await GuideSafetyCheck.filter(guide_document=guide).all()
        blocked = [c for c in checks if c.verdict != SafetyCheckVerdict.PASS]
        assert not blocked, f"차단된 검증이 있다 — {[c.reason_code for c in blocked]}"
        assert len(checks) == 7

    # ── 미등록 약물 차단 (SYN-EMS-08) ─────────────────────────────────────

    async def test_unregistered_drug_blocks_without_guide(self) -> None:
        """미등록 약물(록소펜) 처방 시 생성 전 차단 · 안내문 없음 — SYN-EMS-08.

        처방에 DrugCatalog 에 없는 약물이 포함되면 unrecognized_prescription 으로
        차단되고 안내문은 만들어지지 않는다. 빈칸을 지어내지 않는다.
        """
        visit = await make_visit(self.clinic, "SYN-EMS-08")
        await attach_confirmed_ocr(visit, self.staff.pk)
        await DrugCatalog.get_or_create(name="비잔정 2mg")
        # 록소펜은 DrugCatalog 에 없음 — 미등록 약 폴백 시나리오
        prescription = await Prescription.create(
            visit=visit,
            prescription_set="자궁내막증 · 비잔 (계속)",
        )
        await PrescriptionItem.create(
            prescription=prescription, name="비잔정 2mg", frequency="1일 1회", duration_days=84
        )
        await PrescriptionItem.create(prescription=prescription, name="록소펜정", frequency="1일 3회", duration_days=5)
        prescription_set = await PrescriptionSet.create(
            name="자궁내막증 · 비잔 (계속)", disease=SetDisease.ENDOMETRIOSIS
        )
        await _make_caution_contents(prescription_set)

        job = await self._request_job(visit)
        await self._run()
        await job.refresh_from_db()

        assert job.failed_at is not None
        assert job.failure_reason == "unrecognized_prescription"
        assert not await GuideDocument.filter(visit_id=visit.pk).exists()
        self.model.generate.assert_not_awaited()

    # ── 안전 차단 사유별 reason_code 검증 ────────────────────────────────────

    async def test_extra_drug_block_records_reason_code(self) -> None:
        """모델이 처방 외 약물을 언급하면 EXTRA_DRUG 차단 + GuideSafetyCheck 기록."""
        visit = await self._setup_ems_visit("SYN-EMS-EXTRA")
        await self._add_sources()
        # 카탈로그에는 있지만 처방에는 없는 약 — 모델이 언급하면 EXTRA_DRUG
        await DrugCatalog.get_or_create(name="타이레놀")
        self.model.generate.return_value = ModelAnswer(
            json.dumps({"body": "타이레놀을 함께 복용하세요.", "drug_names": ["타이레놀"]})
        )

        job = await self._request_job(visit)
        await self._run()
        await job.refresh_from_db()

        assert job.failed_at is not None
        assert job.failure_reason == "EXTRA_DRUG"
        check = await GuideSafetyCheck.get(generation_job=job)
        assert check.verdict == SafetyCheckVerdict.BLOCK
        assert check.stage == SafetyCheckStage.POST_GENERATE
        assert check.reason_code == "EXTRA_DRUG"
        assert not await GuideDocument.filter(visit_id=visit.pk).exists()

    async def test_unsupported_diagnosis_block_records_reason_code(self) -> None:
        """모델이 진단 내용을 포함하면 UNSUPPORTED_DIAGNOSIS 차단 + GuideSafetyCheck 기록."""
        visit = await self._setup_ems_visit("SYN-EMS-DIAG")
        await self._add_sources()
        self.model.generate.return_value = ModelAnswer(
            json.dumps({"body": "자궁내막증으로 진단받으셨습니다.", "drug_names": []})
        )

        job = await self._request_job(visit)
        await self._run()
        await job.refresh_from_db()

        assert job.failed_at is not None
        assert job.failure_reason == "UNSUPPORTED_DIAGNOSIS"
        check = await GuideSafetyCheck.get(generation_job=job)
        assert check.verdict == SafetyCheckVerdict.BLOCK
        assert check.stage == SafetyCheckStage.POST_GENERATE
        assert check.reason_code == "UNSUPPORTED_DIAGNOSIS"
        assert not await GuideDocument.filter(visit_id=visit.pk).exists()

    # ── 생성 실패 vs 안전 차단 구분 ─────────────────────────────────────────

    async def test_llm_failure_leaves_no_safety_check_record(self) -> None:
        """LLM 실패(llm_failure)는 GuideSafetyCheck 를 남기지 않는다.

        안전 차단과의 차이: 안전 차단은 SafetyReasonCode 값이라 GuideSafetyCheck
        레코드가 생긴다. LLM 실패는 해당하지 않으므로 레코드가 없다.
        """
        visit = await self._setup_ems_visit("SYN-EMS-FAIL")
        await self._add_sources()
        self.model.generate.side_effect = ChatModelError("synthetic timeout")

        job = await self._request_job(visit)
        for _ in range(3):
            await GuideGenerationJob.filter(job_id=job.pk).update(available_at=now() - timedelta(seconds=1))
            await self._run()
        await job.refresh_from_db()

        assert job.failed_at is not None
        assert job.failure_reason == "llm_failure"
        assert not await GuideSafetyCheck.filter(generation_job=job).exists()
        assert not await GuideDocument.filter(visit_id=visit.pk).exists()

    async def test_safety_block_and_llm_failure_distinguished_in_api_response(self) -> None:
        """생성 실패와 안전 차단이 API 응답 failure_reason 으로 구분된다.

        검수자는 폴링 응답의 failure_reason 으로 두 상황을 구분할 수 있어야 한다.
        """
        # ── 안전 차단 케이스 ──
        visit_block = await self._setup_pcos_visit("SYN-PCOS-BLOCK")
        await self._add_sources()
        self.model.generate.return_value = ModelAnswer(json.dumps({"body": "약 복용을 중단하세요.", "drug_names": []}))
        job_block = await self._request_job(visit_block)
        await self._run()
        await job_block.refresh_from_db()

        # ── 생성 실패 케이스 ──
        visit_fail = await self._setup_ems_visit("SYN-EMS-FAIL2")
        self.model.generate.side_effect = ChatModelError("synthetic timeout")
        job_fail = await self._request_job(visit_fail)
        for _ in range(3):
            await GuideGenerationJob.filter(job_id=job_fail.pk).update(available_at=now() - timedelta(seconds=1))
            await self._run()
        await job_fail.refresh_from_db()

        # API 응답 확인
        async with self.client() as client:
            headers = await self.sign_in(self.staff)
            block_resp = await client.get(
                f"/api/v1/visits/{visit_block.pk}/guide/generation/{job_block.pk}",
                headers=headers,
            )
            fail_resp = await client.get(
                f"/api/v1/visits/{visit_fail.pk}/guide/generation/{job_fail.pk}",
                headers=headers,
            )

        assert block_resp.status_code == 200
        assert fail_resp.status_code == 200
        assert block_resp.json()["failure_reason"] == "DRUG_CHANGE_ADVICE"
        assert fail_resp.json()["failure_reason"] == "llm_failure"
        # 안전 차단은 GuideSafetyCheck 가 있고, 생성 실패는 없다
        assert await GuideSafetyCheck.filter(generation_job=job_block).exists()
        assert not await GuideSafetyCheck.filter(generation_job=job_fail).exists()

    # ── 두 질환 동시 처방 (SYN-BOTH-01) ─────────────────────────────────────

    async def test_both_disease_visit_generates_guide_with_primary_set(self) -> None:
        """두 질환 동시 처방(SYN-BOTH-01): 주 질환 세트로 안내 정상 생성.

        자궁내막증 + PCOS 방문이라도 처방 세트가 자궁내막증으로 확정되면
        안내가 정상 생성된다.
        """
        visit = await make_visit(self.clinic, "SYN-BOTH-01")
        await attach_confirmed_ocr(visit, self.staff.pk)
        await DrugCatalog.get_or_create(name="비잔정 2mg")
        # 두 질환 방문 — 처방 세트는 자궁내막증(주 질환)
        await attach_prescription(visit, [("비잔정 2mg", "1일 1회", 84)])
        prescription_set = await PrescriptionSet.create(
            name="자궁내막증 · 비잔 (계속)", disease=SetDisease.ENDOMETRIOSIS
        )
        await _make_caution_contents(prescription_set)

        job = await self._request_job(visit)
        await self._run()
        await job.refresh_from_db()

        assert job.completed_at is not None, f"생성 실패: {job.failure_reason}"
        assert await GuideDocument.filter(visit_id=visit.pk).exists()
