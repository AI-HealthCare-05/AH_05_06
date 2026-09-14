from dataclasses import replace
from datetime import date
from hashlib import sha256
from uuid import uuid4

from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.models.catalog import ApprovalStatus
from app.models.visits import GuideDocument, GuideSection, GuideSectionKey, GuideSectionSourceSnapshot
from app.services.guide_knowledge_context import GuideSourceValidation, VerifiedGuideSource
from app.services.guide_source_snapshots import persist_guide_fallback, persist_guide_sources
from app.services.knowledge_search import (
    ApprovedFallbackTemplate,
    KnowledgeSearchOutcome,
    KnowledgeSearchResult,
    PocEvaluationApproval,
    admit_generation_context,
)
from app.tests.guide_apis.test_guide_generate import make_clinic, make_visit


class TestGuideSourceSnapshots(TestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.hospital = await make_clinic()
        visit = await make_visit(self.hospital)
        guide = await GuideDocument.create(hospital_id=self.hospital.pk, visit=visit)
        self.section = await GuideSection.create(
            guide_document=guide, section_key=GuideSectionKey.MEDICATION, generated_body="합성 안내"
        )
        self.source = VerifiedGuideSource(
            document_id=str(uuid4()),
            chunk_id=str(uuid4()),
            section_key="medication",
            source_org="합성 기관",
            source_url="https://example.invalid",
            version="v1",
            verified_at=date(2026, 9, 1),
            hospital_id=self.hospital.pk,
            score=0.9,
            body_sha256=sha256("합성 근거".encode()).hexdigest(),
            body="합성 근거",
        )

    async def save_sources(self, validation):
        async with in_transaction() as connection:
            await persist_guide_sources(self.section, validation, hospital_id=self.hospital.pk, connection=connection)

    async def test_multiple_sources_are_copied_and_never_overwritten(self):
        other = replace(self.source, chunk_id=str(uuid4()), version="v2")
        validation = GuideSourceValidation(sources=(self.source, other))
        await self.save_sources(validation)
        rows = await GuideSectionSourceSnapshot.filter(guide_section=self.section).order_by("position")
        assert [row.version for row in rows] == ["v1", "v2"]
        assert rows[0].body_sha256 == self.source.body_sha256
        assert "body" not in rows[0]._meta.fields
        self.source = replace(self.source, version="v3", source_org="새 기관")
        with self.assertRaises(IntegrityError):
            await self.save_sources(GuideSourceValidation(sources=(self.source,)))
        await rows[0].refresh_from_db()
        assert rows[0].version == "v1"
        assert rows[0].source_org == "합성 기관"

    async def test_failure_and_cross_scope_do_not_write(self):
        for validation in (
            GuideSourceValidation(block_reason="source_conflict"),
            GuideSourceValidation(sources=(replace(self.source, hospital_id=self.hospital.pk + 1),)),
            GuideSourceValidation(sources=(replace(self.source, section_key="life"),)),
        ):
            with self.assertRaises(ValueError):
                await self.save_sources(validation)
        assert await GuideSectionSourceSnapshot.all().count() == 0

    async def test_rollback_removes_all_snapshots(self):
        with self.assertRaises(RuntimeError):
            async with in_transaction() as connection:
                await persist_guide_sources(
                    self.section,
                    GuideSourceValidation(sources=(self.source,)),
                    hospital_id=self.hospital.pk,
                    connection=connection,
                )
                raise RuntimeError("synthetic rollback")
        assert await GuideSectionSourceSnapshot.all().count() == 0

    async def test_regeneration_keeps_previous_version_sources(self):
        await self.save_sources(GuideSourceValidation(sources=(self.source,)))
        guide = await self.section.guide_document
        old_id = self.section.pk
        await self.section.delete()
        guide.version += 1
        await guide.save(update_fields=["version"])
        self.section = await GuideSection.create(
            guide_document=guide, section_key=GuideSectionKey.MEDICATION, generated_body="새 합성 안내"
        )
        self.source = replace(self.source, version="v2")
        await self.save_sources(GuideSourceValidation(sources=(self.source,)))
        rows = await GuideSectionSourceSnapshot.filter(guide_document=guide).order_by("guide_version")
        assert len(rows) == 2
        assert rows[0].guide_section_id is None
        assert rows[0].guide_version == 1
        assert rows[0].version == "v1"
        assert rows[1].guide_section_id != old_id
        assert rows[1].guide_version == 2
        assert rows[1].version == "v2"

    async def test_fixed_fallback_and_conflict_cannot_be_confused(self):
        template = ApprovedFallbackTemplate(
            template_id="synthetic-template",
            version="v1",
            body=self.section.generated_body,
            body_sha256=sha256(self.section.generated_body.encode()).hexdigest(),
            approval_status=ApprovalStatus.APPROVED,
            is_current=True,
            approved_by="합성 검토자",
            approved_at=date(2026, 9, 1),
        )
        approval = PocEvaluationApproval("synthetic", True, "합성 검토자", date(2026, 9, 1), "a" * 64)
        admission = admit_generation_context(
            KnowledgeSearchResult(KnowledgeSearchOutcome.NO_EVIDENCE),
            evaluation_approval=approval,
            fallback_template=template,
        )
        for reason in ("source_conflict", "index_invalid"):
            with self.assertRaises(ValueError):
                async with in_transaction() as connection:
                    await persist_guide_fallback(
                        self.section,
                        admission,
                        hospital_id=self.hospital.pk,
                        reason=reason,
                        connection=connection,
                    )
        async with in_transaction() as connection:
            await persist_guide_fallback(
                self.section,
                admission,
                hospital_id=self.hospital.pk,
                reason="no_evidence",
                connection=connection,
            )
        row = await GuideSectionSourceSnapshot.get(guide_section=self.section)
        assert row.template_id == template.template_id
        assert row.version == "v1"
        assert row.body_sha256 == template.body_sha256
        assert row.fallback_reason == "no_evidence"

    async def test_unverified_fallback_is_not_saved(self):
        admission = admit_generation_context(
            KnowledgeSearchResult(KnowledgeSearchOutcome.SOURCE_CONFLICT),
            evaluation_approval=None,
        )
        with self.assertRaises(ValueError):
            async with in_transaction() as connection:
                await persist_guide_fallback(
                    self.section,
                    admission,
                    hospital_id=self.hospital.pk,
                    reason="no_evidence",
                    connection=connection,
                )
        assert await GuideSectionSourceSnapshot.all().count() == 0

    async def test_staff_response_contains_current_metadata_only(self):
        from app.apis.v1.guide_routers import _to_response

        await self.save_sources(GuideSourceValidation(sources=(self.source,)))
        guide = await self.section.guide_document
        await guide.fetch_related("visit__patient", "sections")
        response = await _to_response(guide)
        assert response.sections[0].sources[0].document_id == self.source.document_id
        assert "합성 근거" not in response.model_dump_json()
        guide.version += 1
        await guide.save(update_fields=["version"])
        response = await _to_response(guide)
        assert response.sections[0].sources == []
