"""Sprint 3 OCR 권한·비노출 회귀 — KEY-70.

기존 테스트가 이미 확정 전 안내 생성 차단(KEY-150), CLOVA 비밀값·OCR 원문
로그 비노출(KEY-175), OCR 조회·수정의 병원 격리(KEY-61)를 각각 검증한다.
이 파일은 그 검사를 복제하지 않고 HTTP 경계에 남아 있던 두 틈을 잰다.

* 다른 병원 진료로 업로드를 시도하면 저장소에 쓰기 전에 404로 막힌다.
* 정상 OCR 응답 스키마에도 내부 저장 경로와 원본 파일명 필드는 없다.
"""

from io import BytesIO

from httpx import ASGITransport, AsyncClient

from app.documents.api import get_document_service
from app.documents.service import DocumentUploadService
from app.main import app
from app.tests.document_apis.test_document_upload_security import UnusedStorage
from app.tests.ocr.test_ocr_contract_permissions import OcrContractTestCase

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
FILENAME_MARKER = "synthetic-key70-private-name.jpg"
FORBIDDEN_UPLOAD_METADATA = {"file_path", "original_filename"}


class TestKey70OcrSecurityRegression(OcrContractTestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_document_service, None)
        super().tearDown()

    async def test_other_hospital_upload_is_hidden_before_storage(self) -> None:
        """타 병원 진료는 존재 여부를 숨기고 파일도 저장하지 않는다."""
        owner = await self.make_staff(login_id="key70owner", roles=["staff"], hospital_name="알파의원")
        outsider = await self.make_staff(login_id="key70outsider", roles=["staff"], hospital_name="베타의원")
        visit = await self.make_visit(owner, "UPLOAD-FENCE")
        app.dependency_overrides[get_document_service] = lambda: DocumentUploadService(
            storage=UnusedStorage(),
            max_upload_bytes=1024,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/front-desk/visits/{visit.visit_id}/documents",
                headers={"Authorization": f"Bearer {await self.login(outsider.login_id)}"},
                files={"files": (FILENAME_MARKER, BytesIO(JPEG_BYTES), "image/jpeg")},
                data={"document_type": "EMR"},
            )

        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
        assert str(visit.visit_id) not in response.text
        assert FILENAME_MARKER not in response.text

    async def test_ocr_result_schema_excludes_internal_upload_metadata(self) -> None:
        """소유 병원 OCR 응답에도 내부 업로드 메타데이터 필드는 계약 밖이다."""
        staff = await self.make_staff(login_id="key70reader", roles=["staff"], hospital_name="감마의원")
        job, _, _ = await self.make_completed_result(staff, job_id="syn-key70-private-metadata")

        response = await self.get(f"/ocr/jobs/{job.ocr_job_id}/result", await self.login(staff.login_id))

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        document = response.json()["documents"][0]
        assert FORBIDDEN_UPLOAD_METADATA.isdisjoint(document)
