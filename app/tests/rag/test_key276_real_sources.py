"""KEY-276 실제 출처 adapter·운영 진입점 안전 계약."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.models.knowledge import KnowledgeSourceKind
from app.services.knowledge_sources import MFDS_ENDPOINTS, MfdsDataset, MfdsSnapshotClient, MfdsSnapshotError
from scripts.ingest_approved_knowledge import _build_request, _read_manifest


@pytest.mark.asyncio
async def test_mfds_snapshot_uses_allowlisted_endpoint_and_never_persists_key() -> None:
    encoded_key = "secret%2Bvalue%3D%3D"
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        assert parse_qs(request.url.query.decode())["serviceKey"] == ["secret+value=="]
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {"items": [{"INGR_NAME": "검증 성분"}], "totalCount": 1},
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        payload = await MfdsSnapshotClient(service_key=encoded_key, client=client).fetch_snapshot(
            MfdsDataset.DUR_INGREDIENT
        )

    snapshot = json.loads(payload)
    endpoint = MFDS_ENDPOINTS[MfdsDataset.DUR_INGREDIENT]
    assert seen_urls[0].startswith(endpoint.request_url)
    assert snapshot["dataset"] == "dur_ingredient"
    assert snapshot["pages"][0]["items"][0]["INGR_NAME"] == "검증 성분"
    assert b"secret" not in payload


@pytest.mark.asyncio
async def test_mfds_failure_exposes_only_safe_error_code() -> None:
    marker = "do-not-leak-service-key"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"upstream echoed {marker}", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MfdsSnapshotError) as caught:
            await MfdsSnapshotClient(service_key=marker, client=client).fetch_snapshot(
                MfdsDataset.DRUG_PRODUCT_APPROVAL
            )

    assert str(caught.value) == "MFDS_FETCH_FAILED"
    assert marker not in str(caught.value)


@pytest.mark.asyncio
async def test_mfds_rejects_invalid_total_count_without_leaking_response() -> None:
    marker = "upstream-private-value"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {"items": [{"private": marker}], "totalCount": "invalid"},
                }
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MfdsSnapshotError) as caught:
            await MfdsSnapshotClient(service_key="secret", client=client).fetch_snapshot(MfdsDataset.DUR_PRODUCT)

    assert str(caught.value) == "MFDS_RESPONSE_INVALID"
    assert marker not in str(caught.value)


def test_manifest_refuses_embedded_service_key(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"sources": [{"input_type": "mfds_api", "service_key": "must-not-be-here"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="KNOWLEDGE_MANIFEST_SECRET_FORBIDDEN"):
        _read_manifest(manifest)


@pytest.mark.asyncio
async def test_pdf_manifest_builds_real_file_request_without_copying_source(tmp_path: Path) -> None:
    pdf_path = tmp_path / "approved.pdf"
    pdf_path.write_bytes(b"%PDF-real-approved-bytes")
    source = {
        "input_type": "text_pdf",
        "title": "승인 PDF",
        "source_org": "검증 기관",
        "source_url": "https://authority.example/guideline",
        "version_label": "2026",
        "license_basis": "검증된 이용조건",
        "path": pdf_path.name,
    }

    request = await _build_request(source, manifest_dir=tmp_path, mfds_client=None)

    assert request.source_kind is KnowledgeSourceKind.TEXT_PDF
    assert request.payload == b"%PDF-real-approved-bytes"
    assert request.mime_type == "application/pdf"
