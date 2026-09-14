"""안내 생성 품질·의료안전 합성 시나리오 검증 — KEY-127.

docs/synthetic-data-spec.md §3~§5 시나리오 매트릭스와 연결하여
두 질환(자궁내막증·PCOS) 정상·누락·안전 차단 합성 시나리오를 검증한다.

test_key277_generation.py 가 파이프라인 계약(소스 취소·처방 변경·중복 요청 등)
을 담당하므로, 이 파일은 질환 컨텍스트와 차단 사유 구분에 집중한다.
"""

import json
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from tortoise.timezone import now

from app.core import config
from app.models.catalog import (
    DrugCatalog,
    PrescriptionSet,
    SetDisease,
)
from app.models.ocr import OcrField
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

_SAFE_ANSWER = json.dumps({"body": "검증된 합성 교육 안내입니다.", "drug_names": []})


class TestKey127QualityScenarios(GenerateGuideTestCase):
    """KEY-127: 두 질환 × 정상·누락·안전 차단 합성 시나리오 검증."""

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

    async def _add_sources(self):
        return await make_rag_sources(self.clinic.pk)

    @staticmethod
    def _assert_all_sections_passed(checks) -> None:
        """모든 섹션이 PASS이고 단계별 개수가 기대값(pre 4 · post 3)과 같은지 확인한다."""
        blocked = [c for c in checks if c.verdict is not SafetyCheckVerdict.PASS]
        assert not blocked, f"차단된 검증 — {[(c.section_key, c.reason_code) for c in blocked]}"
        by_stage = Counter(c.stage for c in checks)
        assert dict(by_stage) == {
            SafetyCheckStage.PRE_GENERATE: 4,
            SafetyCheckStage.POST_GENERATE: 3,
        }, f"단계별 개수가 달라졌다 — {dict(by_stage)}"

    async def _setup_ems_visit_with_pending_report(self, chart: str = "SYN-EMS-02"):
        """자궁내막증 · AMH 판독 누락 방문 — SYN-EMS-02 기준 케이스.

        확정된 판독에 is_pending_report=True 필드(AMH)가 함께 있다.
        spec: 「그 줄만 점선 + ?. 추측해서 채우지 않는다. 나머지는 정상 진행」
        """
        visit = await self._setup_ems_visit(chart)
        # 같은 OcrResult에 AMH 검사 결과 누락 필드 추가 (추후보고예정)
        base_field = await OcrField.filter(ocr_result__ocr_job__visit_id=visit.pk).first()
        assert base_field is not None
        await OcrField.create(
            ocr_result_id=base_field.ocr_result_id,
            document_text_id=base_field.document_text_id,
            field_type="AMH",
            extracted_value="추후보고예정",
            confidence=Decimal("0.96"),
            is_pending_report=True,
            is_confirmed=True,
            confirmed_by=self.staff.pk,
        )
        return visit

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
        await make_caution_contents(prescription_set)
        return visit

    async def _setup_both_disease_visit(self, chart: str = "SYN-BOTH-01"):
        """자궁내막증(주 질환) + PCOS 동시 처방 방문 — SYN-BOTH-01 기준 케이스.

        처방 세트는 자궁내막증으로 확정하고 야즈정(PCOS)까지 항목에 포함한다.
        두 약이 모두 DrugCatalog에 등록돼 있어 unrecognized_prescription으로
        차단되지 않고, _pick_prescription_set이 EMS 세트를 선택하는 경로를 실행한다.
        """
        visit = await make_visit(self.clinic, chart)
        await attach_confirmed_ocr(visit, self.staff.pk)
        await DrugCatalog.get_or_create(name="비잔정 2mg")
        await DrugCatalog.get_or_create(name="야즈정")
        prescription = await Prescription.create(
            visit=visit,
            prescription_set="자궁내막증 · 비잔 (계속)",
        )
        await PrescriptionItem.create(
            prescription=prescription, name="비잔정 2mg", frequency="1일 1회", duration_days=84
        )
        await PrescriptionItem.create(prescription=prescription, name="야즈정", frequency="1일 1회", duration_days=84)
        ems_set = await PrescriptionSet.create(name="자궁내막증 · 비잔 (계속)", disease=SetDisease.ENDOMETRIOSIS)
        await make_caution_contents(ems_set)
        pcos_set = await PrescriptionSet.create(name="PCOS · 야즈 (계속)", disease=SetDisease.PCOS)
        await make_caution_contents(pcos_set)
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
        await make_caution_contents(prescription_set)
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
        self._assert_all_sections_passed(checks)

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
        self._assert_all_sections_passed(checks)

    # ── 판독 누락 (SYN-EMS-02) ───────────────────────────────────────────────

    async def test_pending_report_field_does_not_block_generation(self) -> None:
        """판독 누락(SYN-EMS-02): is_pending_report 필드가 있어도 안내 정상 생성.

        AMH 검사 결과가 아직 없는(추후보고예정) 상태에서도 안내는 정상 생성된다.
        누락 값을 추측해서 채우거나 생성 자체를 차단해선 안 된다.
        """
        visit = await self._setup_ems_visit_with_pending_report()
        await self._add_sources()

        job = await self._request_job(visit)
        await self._run()
        await job.refresh_from_db()

        assert job.completed_at is not None, f"생성 실패: {job.failure_reason}"
        guide = await GuideDocument.get(visit_id=visit.pk)
        checks = await GuideSafetyCheck.filter(guide_document=guide).all()
        self._assert_all_sections_passed(checks)

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
        await make_caution_contents(prescription_set)

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
        """두 질환 동시 처방(SYN-BOTH-01): 주 질환 세트로 RAG 경로 안내 정상 생성.

        비잔정(EMS) + 야즈정(PCOS)이 같은 처방 항목에 있고 처방 세트는 EMS로 확정된다.
        양쪽 약이 DrugCatalog에 있어 차단되지 않고, 카탈로그에 PCOS 세트도 있는
        상태에서 _pick_prescription_set이 EMS 세트를 선택해 RAG 경로로 안내가
        정상 생성되고 섹션별 PASS 안전검증이 기록된다.
        """
        visit = await self._setup_both_disease_visit("SYN-BOTH-01")
        await self._add_sources()

        job = await self._request_job(visit)
        await self._run()
        await job.refresh_from_db()

        assert job.completed_at is not None, f"생성 실패: {job.failure_reason}"
        # RAG 소스가 있으면 모델이 실제로 호출된다 — 템플릿 폴백이 아닌 경로 확인
        self.model.generate.assert_awaited()
        guide = await GuideDocument.get(visit_id=visit.pk)
        checks = await GuideSafetyCheck.filter(guide_document=guide).all()
        self._assert_all_sections_passed(checks)
