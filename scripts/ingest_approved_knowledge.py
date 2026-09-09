#!/usr/bin/env python3
"""KEY-276 실제 PDF·식약처 snapshot을 private 저장소에 적재하는 운영 명령.

인증키는 manifest나 argv로 받지 않는다. 실행 프로세스의
``MFDS_SERVICE_KEY`` 환경변수에서만 읽으며 출력하지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tortoise import Tortoise  # noqa: E402
from tortoise.timezone import now as db_now  # noqa: E402

from ai_worker.adapters.knowledge_ocr import ClovaKnowledgeOcrExtractor  # noqa: E402
from app.core import config  # noqa: E402
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.catalog import ApprovalStatus, SourceGrade  # noqa: E402
from app.models.knowledge import KnowledgeDocument, KnowledgeSourceKind, KnowledgeVersion  # noqa: E402
from app.services.knowledge_pipeline import (  # noqa: E402
    KnowledgeApprovalService,
    KnowledgeIngestionRequest,
    KnowledgeIngestionService,
    LocalSentenceTransformerEmbeddingProvider,
    TortoiseKnowledgeRepository,
    stable_source_key,
)
from app.services.knowledge_sources import (  # noqa: E402
    MFDS_ENDPOINTS,
    MfdsDataset,
    MfdsSnapshotClient,
    MfdsSnapshotError,
)
from app.services.knowledge_storage import build_configured_knowledge_store  # noqa: E402

MFDS_SERVICE_KEY_ENV = "MFDS_SERVICE_KEY"
MFDS_DATASET_SERVICE_KEY_ENVS = {
    MfdsDataset.DRUG_PRODUCT_APPROVAL: "MFDS_DRUG_PRODUCT_APPROVAL_SERVICE_KEY",
    MfdsDataset.DUR_INGREDIENT: "MFDS_DUR_INGREDIENT_SERVICE_KEY",
    MfdsDataset.DUR_PRODUCT: "MFDS_DUR_PRODUCT_SERVICE_KEY",
}
_FORBIDDEN_MANIFEST_KEYS = frozenset({"service_key", "servicekey", "api_key", "secret", "password"})
_SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,80}$")


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("KNOWLEDGE_MANIFEST_INVALID") from exc
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list) or not sources:
        raise ValueError("KNOWLEDGE_MANIFEST_EMPTY")
    if not all(isinstance(item, dict) for item in sources):
        raise ValueError("KNOWLEDGE_MANIFEST_INVALID")
    if any(_FORBIDDEN_MANIFEST_KEYS.intersection({str(key).lower() for key in item}) for item in sources):
        raise ValueError("KNOWLEDGE_MANIFEST_SECRET_FORBIDDEN")
    return sources


def _required_text(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"KNOWLEDGE_MANIFEST_{key.upper()}_REQUIRED")
    return value.strip()


def _mfds_client_for(source: dict[str, Any]) -> MfdsSnapshotClient:
    dataset = MfdsDataset(_required_text(source, "dataset"))
    dataset_key = os.environ.get(MFDS_DATASET_SERVICE_KEY_ENVS[dataset], "")
    fallback_key = os.environ.get(MFDS_SERVICE_KEY_ENV, "")
    return MfdsSnapshotClient(service_key=dataset_key or fallback_key)


def _source_identity_request(source: dict[str, Any]) -> KnowledgeIngestionRequest:
    """원문/API 호출 없이 manifest의 고정 출처 식별자를 계산한다."""

    input_type = _required_text(source, "input_type")
    if input_type == "mfds_api":
        dataset = MfdsDataset(_required_text(source, "dataset"))
        source_kind = KnowledgeSourceKind.STRUCTURED_API
        source_url = MFDS_ENDPOINTS[dataset].source_url
    else:
        source_kind = KnowledgeSourceKind(input_type)
        source_url = _required_text(source, "source_url")
    return KnowledgeIngestionRequest(
        title=_required_text(source, "title"),
        source_org=_required_text(source, "source_org"),
        source_url=source_url,
        version_label=_required_text(source, "version_label"),
        source_kind=source_kind,
        payload=b"identity-only",
        mime_type="application/octet-stream",
    )


async def _completed_reviewed_version(source: dict[str, Any]) -> KnowledgeVersion | None:
    """같은 출처·버전이 이미 승인/대체 완료됐으면 해당 버전을 반환한다."""

    identity = _source_identity_request(source)
    document = await KnowledgeDocument.filter(source_key=stable_source_key(identity)).first()
    if document is None:
        return None
    return (
        await KnowledgeVersion.filter(document=document, version_label=identity.version_label)
        .exclude(approval_status=ApprovalStatus.DRAFT)
        .first()
    )


async def _build_request(
    source: dict[str, Any],
    *,
    manifest_dir: Path,
    mfds_client: MfdsSnapshotClient | None,
) -> KnowledgeIngestionRequest:
    input_type = _required_text(source, "input_type")
    title = _required_text(source, "title")
    source_org = _required_text(source, "source_org")
    version_label = _required_text(source, "version_label")
    license_basis = _required_text(source, "license_basis")

    if input_type == "mfds_api":
        if mfds_client is None:
            raise ValueError("MFDS_SERVICE_KEY_REQUIRED")
        dataset = MfdsDataset(_required_text(source, "dataset"))
        endpoint = MFDS_ENDPOINTS[dataset]
        payload = await mfds_client.fetch_snapshot(
            dataset,
            page_size=int(source.get("page_size", 100)),
            max_pages=int(source.get("max_pages", 1)),
        )
        return KnowledgeIngestionRequest(
            title=title,
            source_org=source_org,
            source_url=endpoint.source_url,
            version_label=version_label,
            source_kind=KnowledgeSourceKind.STRUCTURED_API,
            payload=payload,
            mime_type="application/json",
            license_basis=license_basis,
        )

    source_kind = KnowledgeSourceKind(input_type)
    if source_kind not in {KnowledgeSourceKind.TEXT_PDF, KnowledgeSourceKind.SCANNED_DOCUMENT}:
        raise ValueError("KNOWLEDGE_MANIFEST_INPUT_TYPE_INVALID")
    file_path = Path(_required_text(source, "path")).expanduser()
    if not file_path.is_absolute():
        file_path = manifest_dir / file_path
    try:
        payload = file_path.read_bytes()
    except OSError as exc:
        raise ValueError("KNOWLEDGE_SOURCE_FILE_UNREADABLE") from exc
    mime_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "image/png"
    return KnowledgeIngestionRequest(
        title=title,
        source_org=source_org,
        source_url=_required_text(source, "source_url"),
        version_label=version_label,
        source_kind=source_kind,
        payload=payload,
        mime_type=mime_type,
        license_basis=license_basis,
    )


async def run(
    manifest_path: Path,
    *,
    approved_by: str | None,
    review_days: int,
    only_input_type: str | None = None,
) -> None:
    sources = _read_manifest(manifest_path)
    if only_input_type is not None:
        sources = [source for source in sources if source.get("input_type") == only_input_type]
        if not sources:
            raise ValueError("KNOWLEDGE_MANIFEST_FILTER_EMPTY")
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        ingestion = KnowledgeIngestionService(
            repository=TortoiseKnowledgeRepository(),
            object_store=build_configured_knowledge_store(),
            embedding_provider=LocalSentenceTransformerEmbeddingProvider(),
            ocr_extractor=ClovaKnowledgeOcrExtractor() if config.clova_enabled else None,
        )
        for source in sources:
            completed = await _completed_reviewed_version(source)
            if completed is not None:
                # 승인/대체 완료본은 불변으로 유지하고 다음 manifest 항목을 계속 처리한다.
                print(
                    json.dumps(
                        {
                            "title": _required_text(source, "title"),
                            "document_id": str(completed.document_id),
                            "version_id": str(completed.version_id),
                            "status": "already_reviewed_skipped",
                        },
                        ensure_ascii=False,
                    )
                )
                continue
            mfds_client = _mfds_client_for(source) if source.get("input_type") == "mfds_api" else None
            request = await _build_request(source, manifest_dir=manifest_path.parent, mfds_client=mfds_client)
            prepared = await ingestion.ingest(request)
            grade = SourceGrade(str(source.get("source_grade", "C")).upper())
            license_verified = source.get("license_verified") is True
            await KnowledgeVersion.filter(version_id=prepared.version_id).update(
                source_grade=grade,
                license_verified=license_verified,
            )
            approved = False
            if approved_by is not None and source.get("approve") is True:
                reviewed_at = db_now()
                await KnowledgeApprovalService().approve(
                    prepared.version_id,
                    approved_by=approved_by,
                    verified_at=reviewed_at,
                    review_due_at=reviewed_at + timedelta(days=review_days),
                )
                approved = True
            # 경로·원문·인증키는 출력하지 않는다.
            print(
                json.dumps(
                    {
                        "title": request.title,
                        "document_id": prepared.document_id,
                        "version_id": prepared.version_id,
                        "status": "approved" if approved else "ready_for_review",
                    },
                    ensure_ascii=False,
                )
            )
    finally:
        await Tortoise.close_connections()


def main() -> int:
    parser = argparse.ArgumentParser(description="KEY-276 실제 승인 의료지식 적재")
    parser.add_argument("manifest", type=Path, help="로컬 manifest JSON 경로")
    parser.add_argument("--approved-by", help="A등급 자료 승인자 식별자; 생략하면 승인하지 않음")
    parser.add_argument("--review-days", type=int, default=365)
    parser.add_argument(
        "--only",
        choices=("text_pdf", "scanned_document", "mfds_api"),
        help="선택한 입력 유형만 적재",
    )
    args = parser.parse_args()
    if not 1 <= args.review_days <= 3650:
        parser.error("--review-days는 1~3650이어야 합니다")
    try:
        asyncio.run(
            run(
                args.manifest.resolve(),
                approved_by=args.approved_by,
                review_days=args.review_days,
                only_input_type=args.only,
            )
        )
    except (MfdsSnapshotError, ValueError) as exc:
        code = str(exc)
        if _SAFE_ERROR_CODE.fullmatch(code) is None:
            code = "KNOWLEDGE_INGEST_FAILED"
        print(json.dumps({"error": code}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
