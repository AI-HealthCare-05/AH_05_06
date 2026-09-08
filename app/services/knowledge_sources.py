"""식약처 공공데이터를 KEY-276 구조화 snapshot으로 가져오는 좁은 어댑터."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import unquote

import httpx


class MfdsDataset(StrEnum):
    DRUG_PRODUCT_APPROVAL = "drug_product_approval"
    DUR_INGREDIENT = "dur_ingredient"
    DUR_PRODUCT = "dur_product"


@dataclass(frozen=True)
class MfdsEndpoint:
    title: str
    base_url: str
    operation: str
    source_url: str

    @property
    def request_url(self) -> str:
        return f"{self.base_url}/{self.operation}"


# 노션 「RAG 전환 위한 서치」 하단에 승인된 세 서비스의 현행 URL이다.
# DUR은 같은 서비스 안에 여러 상세 기능이 있으므로 실제 적재 smoke에서는
# 병용금기 목록 한 종류를 고정한다. 다른 상세 기능은 검토 후 registry에 추가한다.
MFDS_ENDPOINTS: dict[MfdsDataset, MfdsEndpoint] = {
    MfdsDataset.DRUG_PRODUCT_APPROVAL: MfdsEndpoint(
        title="식품의약품안전처 의약품 제품 허가정보",
        base_url="https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07",
        operation="getDrugPrdtPrmsnInq07",
        source_url="https://www.data.go.kr/data/15095677/openapi.do",
    ),
    MfdsDataset.DUR_INGREDIENT: MfdsEndpoint(
        title="식품의약품안전처 DUR 성분 병용금기정보",
        base_url="https://apis.data.go.kr/1471000/DURIrdntInfoService03",
        operation="getUsjntTabooInfoList02",
        source_url="https://www.data.go.kr/data/15056780/openapi.do",
    ),
    MfdsDataset.DUR_PRODUCT: MfdsEndpoint(
        title="식품의약품안전처 DUR 품목 병용금기정보",
        base_url="https://apis.data.go.kr/1471000/DURPrdlstInfoService03",
        operation="getUsjntTabooInfoList03",
        source_url="https://www.data.go.kr/data/15059486/openapi.do",
    ),
}


class MfdsSnapshotError(RuntimeError):
    """인증키·원문 응답을 노출하지 않는 외부 API 오류."""


def _response_body(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise MfdsSnapshotError("MFDS_RESPONSE_INVALID")
    response = parsed.get("response")
    if not isinstance(response, dict):
        raise MfdsSnapshotError("MFDS_RESPONSE_INVALID")
    header = response.get("header")
    if not isinstance(header, dict):
        raise MfdsSnapshotError("MFDS_RESPONSE_INVALID")
    raw_code = header.get("resultCode", header.get("result_code"))
    if raw_code is None:
        raise MfdsSnapshotError("MFDS_RESPONSE_INVALID")
    code = str(raw_code)
    if code not in {"00", "0", "0000"}:
        raise MfdsSnapshotError("MFDS_RESPONSE_REJECTED")
    body = response.get("body")
    if not isinstance(body, dict):
        raise MfdsSnapshotError("MFDS_RESPONSE_INVALID")
    return body


def _total_count(body: dict[str, Any]) -> int:
    value = body.get("totalCount", body.get("total_count", 0))
    try:
        total = int(value or 0)
    except (TypeError, ValueError):
        invalid_count = True
    else:
        invalid_count = False
    if invalid_count:
        raise MfdsSnapshotError("MFDS_RESPONSE_INVALID")
    if total < 0:
        raise MfdsSnapshotError("MFDS_RESPONSE_INVALID")
    return total


class MfdsSnapshotClient:
    """허용 목록에 든 식약처 endpoint만 호출해 재현 가능한 JSON을 만든다."""

    def __init__(
        self,
        *,
        service_key: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        normalized_key = unquote(service_key.strip())
        if not normalized_key:
            raise ValueError("MFDS_SERVICE_KEY_REQUIRED")
        self._service_key = normalized_key
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def fetch_snapshot(
        self,
        dataset: MfdsDataset,
        *,
        page_size: int = 100,
        max_pages: int = 1,
    ) -> bytes:
        if not 1 <= page_size <= 100:
            raise ValueError("MFDS_PAGE_SIZE_OUT_OF_RANGE")
        if not 1 <= max_pages <= 50:
            raise ValueError("MFDS_MAX_PAGES_OUT_OF_RANGE")

        endpoint = MFDS_ENDPOINTS[dataset]
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds, follow_redirects=False)
        pages: list[dict[str, Any]] = []
        try:
            for page_no in range(1, max_pages + 1):
                try:
                    response = await client.get(
                        endpoint.request_url,
                        params={
                            "serviceKey": self._service_key,
                            "pageNo": page_no,
                            "numOfRows": page_size,
                            "type": "json",
                        },
                    )
                    response.raise_for_status()
                    body = _response_body(response.json())
                except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                    fetch_failed = True
                else:
                    fetch_failed = False
                if fetch_failed:
                    # 예외를 except 블록 밖에서 새로 만들어 URL(serviceKey 포함)이
                    # __cause__/__context__ 사슬로 붙는 것까지 막는다.
                    raise MfdsSnapshotError("MFDS_FETCH_FAILED")
                pages.append(body)
                total_count = _total_count(body)
                if total_count <= page_no * page_size:
                    break
        finally:
            if own_client:
                await client.aclose()

        snapshot = {
            "dataset": dataset.value,
            "operation": endpoint.operation,
            "pages": pages,
            "source_url": endpoint.source_url,
        }
        return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
