"""SYN-EMS-01이 로그인부터 D+7 병원 조회까지 한 번에 이어지는가 — KEY-152."""

import hashlib
from datetime import UTC, date, datetime
from tempfile import TemporaryDirectory
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase
from tortoise.transactions import in_transaction

from app.apis.v1.patient_otp_routers import _otp_service
from app.core import config
from app.core.redis_client import get_redis
from app.core.storage import LocalFileStorage
from app.core.utils.security import hash_password
from app.documents.api import get_document_service
from app.documents.service import DocumentUploadService
from app.main import app
from app.models.ocr import OcrDocumentType, OcrField, OcrJob, OcrJobStatus
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import CheckIn, GuideDocument, GuideStatus, PatientGuideLink, Visit
from app.ocr.service import seed_fixture_result
from app.services.patient_otp import PatientOtpService
from app.tests.fakes import FakeRedis
from app.tests.patient_links.test_patient_otp import RecordingDelivery

PASSWORD = "Synthetic-KEY152-only-1!"
LOGIN = "/api/v1/auth/login"
PATIENT_OTP = "152027"
PATIENT_OTP_SECRET = "synthetic-key152-test-secret-never-used-outside-tests"


class TestKey152WalkingSkeleton(TestCase):
    """단일 병원의 정상 여정만 연결한다.

    병원 간 격리와 역할별 거부는 각 API의 권한 테스트가 담당하고, 여기서는
    동일한 ``visit_id``가 업로드부터 D+7 조회까지 끊기지 않는지만 검증한다.
    """

    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        self.upload_dir = TemporaryDirectory(prefix="key152-")
        self.cookie_domain = config.COOKIE_DOMAIN
        config.COOKIE_DOMAIN = ""
        app.dependency_overrides[get_redis] = lambda: self.redis
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(
            RecordingDelivery(),
            secret_key=PATIENT_OTP_SECRET,
        )
        app.dependency_overrides[get_document_service] = lambda: DocumentUploadService(
            LocalFileStorage(self.upload_dir.name),
            max_upload_bytes=1024 * 1024,
        )

    def tearDown(self) -> None:
        config.COOKIE_DOMAIN = self.cookie_domain
        app.dependency_overrides.clear()
        self.upload_dir.cleanup()
        super().tearDown()

    async def _account(self, hospital: Hospital, login_id: str, name: str, roles: list[str]) -> Staff:
        return await Staff.create(
            hospital=hospital,
            login_id=login_id,
            password_hash=hash_password(PASSWORD),
            name=name,
            roles=roles,
            must_change_password=False,
        )

    async def _login(self, client: AsyncClient, login_id: str) -> dict[str, str]:
        response = await client.post(LOGIN, json={"login_id": login_id, "password": PASSWORD})
        assert response.status_code == 200, response.text
        assert "refresh_token" not in response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    async def test_syn_ems_01_completes_the_demo_journey_with_one_visit_id(self) -> None:
        hospital = await Hospital.create(name="기준의원")
        staff = await self._account(hospital, "staff01", "한소영", ["staff"])
        doctor = await self._account(hospital, "doctor01", "박연", ["doctor"])
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no="12401",
            name="윤지아",
            birth_date=date(1989, 3, 12),
            phone="01024317788",
            sms_consent=True,
        )
        visit = await Visit.create(
            hospital_id=hospital.hospital_id,
            patient=patient,
            doctor_id=doctor.staff_id,
            visited_at=datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            staff_headers = await self._login(client, staff.login_id)
            doctor_headers = await self._login(client, doctor.login_id)

            uploaded = await client.post(
                f"/api/v1/front-desk/visits/{visit.visit_id}/documents",
                headers=staff_headers,
                files={"files": ("syn-ems-01.jpg", b"\xff\xd8\xff\xe0synthetic-key152", "image/jpeg")},
                data={"document_type": "EMR"},
            )
            assert uploaded.status_code == 201, uploaded.text
            upload_body = uploaded.json()
            assert upload_body["status"] == OcrJobStatus.PROCESSING

            # KEY-149의 W1 fixture 경계: 운영 코드와 같은 fixture 완료 경로를 실행한다.
            job = await OcrJob.get(ocr_job_id=upload_body["ocr_job_id"])
            async with in_transaction() as connection:
                await seed_fixture_result(
                    job,
                    [(upload_body["document_ids"][0], OcrDocumentType.EMR)],
                    connection,
                )
            field = await OcrField.get(ocr_result__ocr_job=job)

            confirmed = await client.patch(
                f"/api/v1/ocr/fields/{field.ocr_field_id}",
                headers=staff_headers,
                json={"base_version": 1, "confirm": True},
            )
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["is_confirmed"] is True

            generated = await client.post(
                f"/api/v1/visits/{visit.visit_id}/guide/generate",
                headers=staff_headers,
            )
            assert generated.status_code == 201, generated.text
            assert generated.json()["visit_id"] == visit.visit_id
            assert generated.json()["status"] == GuideStatus.APPROVAL_PENDING

            edited_text = "[합성 최종 승인 문구] 처방에 따라 복용하고 이상 증상이 있으면 병원에 문의하세요."
            edited = await client.patch(
                f"/api/v1/visits/{visit.visit_id}/guide/sections/medication",
                headers=doctor_headers,
                json={"body": edited_text},
            )
            assert edited.status_code == 200, edited.text
            assert edited.json()["body"] == edited_text

            approved = await client.post(
                f"/api/v1/visits/{visit.visit_id}/guide/approve",
                headers=doctor_headers,
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == GuideStatus.SCHEDULED_TO_SEND

            issued = await client.post(
                f"/api/v1/visits/{visit.visit_id}/guide/link",
                headers=staff_headers,
            )
            assert issued.status_code == 201, issued.text
            guide_path = issued.json()["path"]
            raw_token = guide_path.rsplit("/", 1)[-1]

            patient_guide = await client.get(guide_path)
            assert patient_guide.status_code == 200, patient_guide.text
            sections = patient_guide.json()["sections"]
            assert sections
            assert all(section["body"].strip() for section in sections)
            assert edited_text in [section["body"] for section in sections]

            checkin_path = f"/api/v1/checkins/{raw_token}"
            with patch("app.services.patient_otp.secrets.randbelow", return_value=int(PATIENT_OTP)):
                otp_issued = await client.post(
                    "/api/v1/patient-auth/otp/issue",
                    json={"link_token": raw_token},
                )
            assert otp_issued.status_code == 200, otp_issued.text
            otp_verified = await client.post(
                "/api/v1/patient-auth/otp/verify",
                json={"link_token": raw_token, "code": PATIENT_OTP},
            )
            assert otp_verified.status_code == 200, otp_verified.text

            submitted = await client.post(
                checkin_path,
                json={"medication": "taking", "pain": {"had": True, "score": 3, "types": ["menstrual"]}},
            )
            assert submitted.status_code == 201, submitted.text

            hospital_read = await client.get(
                f"/api/v1/visits/{visit.visit_id}/checkin",
                headers=staff_headers,
            )
            assert hospital_read.status_code == 200, hospital_read.text
            assert hospital_read.json()["visit_id"] == visit.visit_id
            assert hospital_read.json()["medication"] == "taking"

        guide = await GuideDocument.get(visit_id=visit.visit_id)
        link = await PatientGuideLink.get(guide_document=guide)
        check_in = await CheckIn.get(guide_document=guide)
        assert guide.status == GuideStatus.SCHEDULED_TO_SEND
        assert check_in.guide_document_id == guide.guide_document_id
        assert link.token_digest == hashlib.sha256(raw_token.encode()).hexdigest()
        assert raw_token not in hospital_read.text
