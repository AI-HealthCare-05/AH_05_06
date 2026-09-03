"""실제 OCR Worker와 fallback이 같은 환자 여정을 완주하는가 — KEY-69.

외부 CLOVA HTTP만 결정적인 실측 응답/오류로 대체한다. 업로드, 파일 읽기,
Worker 저장, OCR 수정·확정, 안내 생성·승인, 링크·OTP, 환자 조회와 D+7 저장은
모두 운영 API와 서비스를 그대로 탄다. 실제 계정 키와 환자정보는 사용하지 않는다.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, Mock, patch

from httpx import ASGITransport, AsyncClient

from ai_worker.tasks.ocr_task import _CLOVA_MODEL_NAME, process_ocr_job
from app.apis.v1.patient_otp_routers import _otp_service
from app.core.storage import LocalFileStorage
from app.documents.api import get_document_service
from app.documents.service import DocumentUploadService
from app.main import app
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.prescriptions import Prescription, PrescriptionItem
from app.models.staffs import Hospital, Staff
from app.models.visits import CheckIn, GuideDocument, GuideStatus, PatientGuideLink, Visit
from app.ocr.service import FIXTURE_MODEL_NAME
from app.services.patient_otp import PatientOtpService
from app.tests.auth_base import AuthTestCase, login_headers, make_staff_account
from app.tests.fixtures.ocr import SYN_EMS_01_CLOVA_RESULT, SYN_EMS_01_REQUIRED_FIELDS
from app.tests.patient_links.test_patient_otp import RecordingDelivery

PATIENT_OTP = "069069"
PATIENT_OTP_SECRET = "synthetic-key69-test-secret-never-used-outside-tests"
EMR_UPLOAD_BYTES = b"\xff\xd8\xff\xe0SYN-EMS-01-synthetic-emr-no-real-patient-data"
APPROVED_TEXT = "[합성 승인 문구] 처방 지시에 따라 복용하고 불편하면 병원에 문의하세요."


@dataclass(frozen=True, slots=True)
class JourneyEvidence:
    mode: str
    model_name: str
    elapsed_ms: int
    field_types: frozenset[str]
    failure_code: str | None


class RecordingLogHandler(logging.Handler):
    """한 여정 동안 애플리케이션 전 계층이 실제로 내보낸 로그를 모은다."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def rendered(self) -> str:
        return "\n".join(record.getMessage() for record in self.records)


class TestKey69RealOcrJourney(AuthTestCase):
    """CLOVA 성공과 실패 후 fallback을 같은 E2E 계약으로 잰다."""

    def setUp(self) -> None:
        super().setUp()
        self.upload_dir = TemporaryDirectory(prefix="key69-")
        self.delivery = RecordingDelivery()
        app.dependency_overrides[_otp_service] = lambda: PatientOtpService(
            self.delivery,
            secret_key=PATIENT_OTP_SECRET,
        )
        app.dependency_overrides[get_document_service] = lambda: DocumentUploadService(
            LocalFileStorage(self.upload_dir.name),
            max_upload_bytes=1024 * 1024,
        )
        # root는 app.* 계층을, 두 non-propagating 로거는 앱 공용 로거와 Worker를
        # 잡는다. Worker 호출부는 아래에서 Mock으로 구조까지 따로 검사한다.
        self.log_handler = RecordingLogHandler()
        self.observed_loggers = [
            logging.getLogger(),
            logging.getLogger("ai_worker"),
            logging.getLogger("AI Worker"),
        ]
        for logger in self.observed_loggers:
            logger.addHandler(self.log_handler)

    def tearDown(self) -> None:
        for logger in self.observed_loggers:
            logger.removeHandler(self.log_handler)
        app.dependency_overrides.clear()
        self.upload_dir.cleanup()
        super().tearDown()

    async def _seed_visit(self, suffix: str) -> tuple[Staff, Staff, Visit]:
        hospital = await Hospital.create(name=f"KEY-69 합성여성의원 {suffix}")
        staff = await make_staff_account(hospital, f"key69-staff-{suffix}", ["staff"], name="합성스탭")
        doctor = await make_staff_account(hospital, f"key69-doctor-{suffix}", ["doctor"], name="합성의사")
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no=f"SYN-EMS-01-{suffix}",
            name="합성환자",
            birth_date=date(1990, 1, 2),
            phone=f"0100000690{1 if suffix == 'clova' else 2}",
            sms_consent=True,
        )
        visit = await Visit.create(
            hospital_id=hospital.hospital_id,
            patient=patient,
            doctor_id=doctor.staff_id,
            visited_at=datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
        )
        prescription = await Prescription.create(
            visit=visit,
            prescription_set="자궁내막증 · 비잔 (계속)",
        )
        await PrescriptionItem.create(
            prescription=prescription,
            name="비잔정(디에노게스트)2mg",
            frequency="1일 1회",
            duration_days=84,
        )
        return staff, doctor, visit

    async def _run_journey(self, *, fallback: bool) -> JourneyEvidence:
        suffix = "fallback" if fallback else "clova"
        staff, doctor, visit = await self._seed_visit(suffix)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as hospital_client:
            staff_headers = await login_headers(hospital_client, staff.login_id)
            doctor_headers = await login_headers(hospital_client, doctor.login_id)

            if fallback:
                # KEY-199: fixture seed는 업로드(_persist)가 단독 소유한다.
                # OCR_FIXTURE_FALLBACK=True이면 _persist가 직접 seed하고 COMPLETED로 전환한다.
                # 워커는 관여하지 않는다.
                observed_logger = Mock()  # 워커 없음 — 보안 로그는 self.log_handler로만 확인
                with patch("app.documents.service.config.OCR_FIXTURE_FALLBACK", True):
                    uploaded = await hospital_client.post(
                        f"/api/v1/front-desk/visits/{visit.visit_id}/documents",
                        headers=staff_headers,
                        files={"files": ("SYN-EMS-01.emr.v1.jpg", EMR_UPLOAD_BYTES, "image/jpeg")},
                        data={"document_type": "EMR"},
                    )
                assert uploaded.status_code == 201, uploaded.text
                upload_body = uploaded.json()
                job = await OcrJob.get(ocr_job_id=upload_body["ocr_job_id"])
                result = await OcrResult.get(ocr_job=job)
            else:
                # OCR_FIXTURE_FALLBACK=False → 큐잉 → Worker → CLOVA
                with patch("app.documents.service.config.OCR_FIXTURE_FALLBACK", False):
                    uploaded = await hospital_client.post(
                        f"/api/v1/front-desk/visits/{visit.visit_id}/documents",
                        headers=staff_headers,
                        files={"files": ("SYN-EMS-01.emr.v1.jpg", EMR_UPLOAD_BYTES, "image/jpeg")},
                        data={"document_type": "EMR"},
                    )
                assert uploaded.status_code == 201, uploaded.text
                upload_body = uploaded.json()
                assert upload_body["status"] == OcrJobStatus.PROCESSING

                clova_call = AsyncMock(return_value=SYN_EMS_01_CLOVA_RESULT)
                observed_logger = Mock()
                with (
                    patch("ai_worker.tasks.ocr_task.config") as worker_config,
                    patch("ai_worker.tasks.ocr_task.call_clova_ocr", clova_call),
                    patch("ai_worker.tasks.ocr_task.default_logger", observed_logger),
                ):
                    worker_config.clova_enabled = True
                    await process_ocr_job(upload_body["ocr_job_id"])

                clova_call.assert_awaited_once_with(EMR_UPLOAD_BYTES, "image/jpeg")
                job = await OcrJob.get(ocr_job_id=upload_body["ocr_job_id"])
                result = await OcrResult.get(ocr_job=job)

                # 외부 API 응답의 원문이나 합성 환자 값 대신 mode·시간·코드·job id만
                # 한 줄로 남기는 운영 관측 계약을 확인한다.
                completion_calls = [
                    call
                    for call in observed_logger.info.call_args_list
                    if call.args and call.args[0].startswith("ocr_job_complete")
                ]
                assert len(completion_calls) == 1
                log_args = completion_calls[0].args
                assert log_args[1] == "clova"
                assert isinstance(log_args[2], int) and log_args[2] >= 0
                assert log_args[5] == job.ocr_job_id

            assert job.status == OcrJobStatus.COMPLETED
            assert job.started_at is not None
            assert job.completed_at is not None
            assert job.completed_at >= job.started_at
            elapsed_ms = round((job.completed_at - job.started_at).total_seconds() * 1000)

            status_response = await hospital_client.get(
                f"/api/v1/ocr/jobs/{job.ocr_job_id}",
                headers=staff_headers,
            )
            fields_response = await hospital_client.get(
                f"/api/v1/ocr/jobs/{job.ocr_job_id}/fields",
                headers=staff_headers,
            )
            assert status_response.status_code == 200, status_response.text
            assert fields_response.status_code == 200, fields_response.text
            fields = fields_response.json()
            field_types = frozenset(item["field_type"] for item in fields)
            if fallback:
                assert field_types == {"DIAGNOSIS"}
            else:
                assert SYN_EMS_01_REQUIRED_FIELDS <= field_types

            # 사람이 진단을 한 번 수정·확정하고, 나머지 판독값도 눈으로 확인해
            # 확정한다. Worker 저장만 확인하고 안내로 건너뛰지 않는다.
            for item in fields:
                payload: dict[str, object] = {
                    "base_version": item["version"],
                    "confirm": True,
                }
                if item["field_type"] == "DIAGNOSIS":
                    payload["corrected_value"] = "자궁내막증(N80.9)"
                confirmed = await hospital_client.patch(
                    f"/api/v1/ocr/fields/{item['ocr_field_id']}",
                    headers=staff_headers,
                    json=payload,
                )
                assert confirmed.status_code == 200, confirmed.text
                assert confirmed.json()["is_confirmed"] is True

            diagnosis = await OcrField.get(ocr_result=result, field_type="DIAGNOSIS")
            assert diagnosis.corrected_value == "자궁내막증(N80.9)"
            assert diagnosis.is_confirmed is True

            generated = await hospital_client.post(
                f"/api/v1/visits/{visit.visit_id}/guide/generate",
                headers=staff_headers,
            )
            assert generated.status_code == 201, generated.text
            assert generated.json()["status"] == GuideStatus.STAFF_REVIEW
            edited = await hospital_client.patch(
                f"/api/v1/visits/{visit.visit_id}/guide/sections/medication",
                headers=staff_headers,
                json={"body": APPROVED_TEXT},
            )
            assert edited.status_code == 200, edited.text
            submitted = await hospital_client.post(
                f"/api/v1/visits/{visit.visit_id}/guide/submit",
                headers=staff_headers,
            )
            assert submitted.status_code == 200, submitted.text
            approved = await hospital_client.post(
                f"/api/v1/visits/{visit.visit_id}/guide/approve",
                headers=doctor_headers,
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == GuideStatus.SCHEDULED_TO_SEND

            issued = await hospital_client.post(
                f"/api/v1/visits/{visit.visit_id}/guide/link",
                headers=staff_headers,
            )
            assert issued.status_code == 201, issued.text
            raw_token = issued.json()["path"].rsplit("/", 1)[-1]

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as patient_client:
                with patch("app.services.patient_otp.secrets.randbelow", return_value=int(PATIENT_OTP)):
                    otp_issued = await patient_client.post(
                        "/api/v1/patient-auth/otp/issue",
                        json={"link_token": raw_token},
                    )
                assert otp_issued.status_code == 200, otp_issued.text
                verified = await patient_client.post(
                    "/api/v1/patient-auth/otp/verify",
                    json={"link_token": raw_token, "code": PATIENT_OTP},
                )
                assert verified.status_code == 200, verified.text

                patient_guide = await patient_client.get(issued.json()["path"])
                assert patient_guide.status_code == 200, patient_guide.text
                assert APPROVED_TEXT in [section["body"] for section in patient_guide.json()["sections"]]
                assert raw_token not in patient_guide.text

                d7 = await patient_client.post(
                    f"/api/v1/checkins/{raw_token}",
                    json={"medication": "taking", "pain": {"had": True, "score": 2, "types": ["menstrual"]}},
                )
                assert d7.status_code == 201, d7.text

            hospital_read = await hospital_client.get(
                f"/api/v1/visits/{visit.visit_id}/checkin",
                headers=staff_headers,
            )
            assert hospital_read.status_code == 200, hospital_read.text
            assert hospital_read.json()["medication"] == "taking"
            assert raw_token not in hospital_read.text

            # Worker 구조 검사는 Mock으로, 문서·OCR·안내·OTP 등 API/서비스
            # 계층은 실제 logging.Handler로 함께 본다. Worker 한 곳만 가로채고
            # "전체 로그"라고 부르는 거짓 초록불을 만들지 않는다.
            all_observed_logs = repr(observed_logger.mock_calls) + self.log_handler.rendered()
            for forbidden in (
                "합성환자",
                "010000069",
                SYN_EMS_01_CLOVA_RESULT.raw_text,
                raw_token,
            ):
                assert forbidden not in all_observed_logs

        guide = await GuideDocument.get(visit=visit)
        link = await PatientGuideLink.get(guide_document=guide)
        check_in = await CheckIn.get(guide_document=guide)
        assert guide.status == GuideStatus.SCHEDULED_TO_SEND
        assert check_in.guide_document_id == guide.guide_document_id
        assert link.token_digest == hashlib.sha256(raw_token.encode()).hexdigest()
        assert raw_token not in repr(link.__dict__)

        return JourneyEvidence(
            mode="fixture" if fallback else "clova",
            model_name=result.model_name,
            elapsed_ms=elapsed_ms,
            field_types=field_types,
            failure_code=job.failure_code,
        )

    async def test_syn_ems_01_clova_worker_completes_the_full_journey(self) -> None:
        evidence = await self._run_journey(fallback=False)

        assert evidence.mode == "clova"
        assert evidence.model_name == _CLOVA_MODEL_NAME
        assert evidence.failure_code is None
        assert SYN_EMS_01_REQUIRED_FIELDS <= evidence.field_types
        assert evidence.elapsed_ms >= 0

    async def test_upload_fixture_fallback_completes_the_same_journey(self) -> None:
        # KEY-199: fixture seed는 업로드(_persist)가 단독 소유한다.
        # OCR_FIXTURE_FALLBACK=True이면 업로드 시 COMPLETED — 워커는 관여하지 않는다.
        evidence = await self._run_journey(fallback=True)

        assert evidence.mode == "fixture"
        assert evidence.model_name == FIXTURE_MODEL_NAME
        assert evidence.failure_code is None
        assert evidence.field_types == {"DIAGNOSIS"}
        assert evidence.elapsed_ms >= 0
