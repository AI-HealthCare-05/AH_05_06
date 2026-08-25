"""SYN-EMS-01이 로그인부터 D+7 병원 조회까지 한 번에 이어지는가 — KEY-152."""

from datetime import UTC, date, datetime
from tempfile import TemporaryDirectory

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core import config
from app.core.redis_client import get_redis
from app.core.storage import LocalFileStorage
from app.core.utils.security import hash_password
from app.documents.api import get_document_service
from app.documents.service import DocumentUploadService
from app.main import app
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import CheckIn, GuideDocument, GuideStatus, PatientGuideLink, Visit
from app.tests.fakes import FakeRedis

PASSWORD = "Synthetic-KEY152-only-1!"
LOGIN = "/api/v1/auth/login"


class TestKey152WalkingSkeleton(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        self.upload_dir = TemporaryDirectory(prefix="key152-")
        self.cookie_domain = config.COOKIE_DOMAIN
        config.COOKIE_DOMAIN = ""
        app.dependency_overrides[get_redis] = lambda: self.redis
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

            # KEY-149의 W1 fixture 경계: 업로드가 만든 작업을 완료시키고 합성 판독값을 채운다.
            job = await OcrJob.get(ocr_job_id=upload_body["ocr_job_id"])
            job.status = OcrJobStatus.COMPLETED
            job.progress = 100
            job.started_at = now()
            job.completed_at = now()
            await job.save(update_fields=("status", "progress", "started_at", "completed_at"))
            result = await OcrResult.create(ocr_job=job, model_name="synthetic-fixture-key152")
            field = await OcrField.create(
                ocr_result=result,
                field_type="DIAGNOSIS",
                extracted_value="자궁내막증",
                confidence=0.99,
            )

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
            assert patient_guide.json()["sections"]

            checkin_path = f"/api/v1/checkins/{raw_token}"
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
        assert raw_token not in repr(link.__dict__)
        assert raw_token not in hospital_read.text
