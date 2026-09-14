"""KEY-277 생성 원문 근거 저장. 호출자의 생성 트랜잭션에 참여한다."""

from tortoise import BaseDBAsyncClient

from app.models.prescriptions import Prescription, ordered_prescription_items
from app.models.visits import GuideSection, GuideSectionSourceSnapshot
from app.services.guide_body import medication_body
from app.services.guide_knowledge_context import GuideSourceValidation
from app.services.knowledge_search import ContextAdmissionOutcome, GenerationContextAdmission, fallback_body_checksum


async def persist_guide_sources(
    section: GuideSection,
    validation: GuideSourceValidation,
    *,
    hospital_id: int,
    connection: BaseDBAsyncClient,
) -> None:
    """부분 저장·덮어쓰기 없이 검증된 근거를 복사한다.

    생성 호출부가 승인 게이트·의료 안전검증을 통과한 뒤 사용해야 한다.
    이 함수 자체는 생성 허가가 아니다. fallback 저장은 별도 경로다.
    """
    if validation.block_reason is not None or not validation.sources:
        raise ValueError("verified_sources_required")
    if any(
        source.section_key != section.section_key.value or source.hospital_id not in (None, hospital_id)
        for source in validation.sources
    ):
        raise ValueError("source_scope_mismatch")
    guide = await section.guide_document
    if guide.hospital_id != hospital_id:
        raise ValueError("guide_scope_mismatch")
    rows = [
        GuideSectionSourceSnapshot(
            guide_section=section,
            guide_document=guide,
            guide_version=guide.version,
            section_key=section.section_key,
            position=position,
            generation_mode="rag",
            document_id=source.document_id,
            chunk_id=source.chunk_id,
            source_org=source.source_org,
            source_url=source.source_url,
            version=source.version,
            verified_at=source.verified_at,
            score=source.score,
            body_sha256=source.body_sha256,
        )
        for position, source in enumerate(validation.sources)
    ]
    # 같은 안내 버전·섹션의 근거를 두 번 덮어쓰지 않는다.
    await GuideSectionSourceSnapshot.bulk_create(rows, using_db=connection)


async def persist_guide_fallback(
    section: GuideSection,
    admission: GenerationContextAdmission,
    *,
    hospital_id: int,
    reason: str,
    connection: BaseDBAsyncClient,
) -> None:
    """안전 게이트가 허용한 고정 템플릿만 저장한다. 검색 오류를 재분류하지 않는다."""
    template = admission.fallback_template
    if admission.outcome is not ContextAdmissionOutcome.APPROVED_TEMPLATE_FALLBACK or template is None:
        raise ValueError("approved_template_required")
    if reason not in {"no_evidence", "search_infrastructure_exhausted", "fixed_approved_template"}:
        raise ValueError("fallback_reason_not_allowed")
    guide = await section.guide_document
    if guide.hospital_id != hospital_id:
        raise ValueError("guide_scope_mismatch")
    expected = template.body
    if section.section_key.value == "medication":
        prescription = (
            await Prescription.filter(visit_id=guide.visit_id).using_db(connection).prefetch_related("items").first()
        )
        expected = medication_body(ordered_prescription_items(prescription), template.body)
    if section.generated_body != expected or template.body_sha256 != fallback_body_checksum(template.body):
        raise ValueError("fallback_body_changed")
    await GuideSectionSourceSnapshot.create(
        guide_document=guide,
        guide_version=guide.version,
        section_key=section.section_key,
        guide_section=section,
        position=0,
        generation_mode="template",
        template_id=template.template_id,
        version=template.version,
        body_sha256=template.body_sha256,
        fallback_reason=reason,
        using_db=connection,
    )
