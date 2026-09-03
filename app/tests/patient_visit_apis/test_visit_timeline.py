"""GET /visits/{visit_id}/timeline — KEY-242 (와이어프레임 S1-4).

진료 한 건의 이력을 이미 적재된 사건에서 모아 시간순으로 돌려준다. 새 사건을
만들지 않으므로 여기서 확인하는 것은 (1) 병합·정렬, (2) 병원 범위와 역할,
(3) 사건이 없는 진료의 빈 응답이다.

각 사건의 시각은 만든 뒤 `.filter().update()` 로 직접 박는다 — `.create()` 와
`.update()` 가 시간대를 다루는 방식이 달라 섞으면 저장값에 가짜 시차가 생긴다.
"""

from datetime import UTC, date, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.dependencies.patient_access import ClinicalActor, get_clinical_actor
from app.main import app
from app.models.documents import MedicalDocument
from app.models.ocr import OcrDocumentType, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.visits import GuideDocument, GuideEvent, GuideEventType, GuideSectionKey, Visit
from app.services.patient_history import GUIDE_PAGES

BASE_URL = "http://test"
STAFF = ClinicalActor(staff_id=101, hospital_id=1, roles=frozenset({"staff"}))
DOCTOR = ClinicalActor(staff_id=102, hospital_id=1, roles=frozenset({"doctor"}))
ADMIN_ONLY = ClinicalActor(staff_id=103, hospital_id=1, roles=frozenset({"admin"}))
OTHER_HOSPITAL_STAFF = ClinicalActor(staff_id=201, hospital_id=2, roles=frozenset({"staff"}))

BASE = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


async def make_patient(hospital_id: int, number: str) -> Patient:
    return await Patient.create(
        hospital_id=hospital_id,
        hospital_patient_no=number,
        name=f"합성환자-{number}",
        birth_date=date(1994, 7, 22),
        phone="01039457702",
        sms_consent=True,
    )


async def make_visit(hospital_id: int, patient: Patient) -> Visit:
    """**진료가 사건들보다 먼저다.**

    `visited_at` 이 `BASE` 보다 여덟 시간 **뒤**(18:00 KST)였다. 문서 업로드가
    10:00 KST 인데 진료는 18:00 이라, 진료가 열리기도 전에 문서가 올라온 셈이
    었다. 사건 목록만 보던 때는 드러나지 않다가 `VISIT_CREATED` 가 생기면서
    맨 뒤로 밀려 걸렸다.

    **`create` 가 아니라 `update` 로 넣는다.** 이 저장소는 지금 둘이 시각을
    다르게 저장한다 — `create` 는 UTC 를 KST 로 옮겨 넣고, `update` 는 벽시계를
    그대로 넣는다(`#183` 이 고치는 중이다). 이 파일의 다른 사건들이 전부
    `update` 로 들어가므로 여기만 `create` 로 넣으면 아홉 시간이 어긋난다.
    `#183` 이 병합되면 둘이 같아져 이 우회는 필요 없어진다.
    """
    visit = await Visit.create(hospital_id=hospital_id, patient=patient, visited_at=BASE)
    await Visit.filter(visit_id=visit.visit_id).update(visited_at=BASE - timedelta(minutes=30))
    return await Visit.get(visit_id=visit.visit_id)


def override_actor(actor: ClinicalActor) -> None:
    async def _actor() -> ClinicalActor:
        return actor

    app.dependency_overrides[get_clinical_actor] = _actor


async def get_timeline(actor: ClinicalActor, visit_id: int):
    override_actor(actor)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
            return await client.get(f"/api/v1/visits/{visit_id}/timeline")
    finally:
        app.dependency_overrides.pop(get_clinical_actor, None)


async def guide_event(
    guide: GuideDocument,
    event_type: GuideEventType,
    actor_id: int,
    at: datetime,
    *,
    section_key: GuideSectionKey | None = None,
    reason: str | None = None,
) -> None:
    event = await GuideEvent.create(
        guide_document=guide,
        event_type=event_type,
        section_key=section_key,
        reason=reason,
        actor_id=actor_id,
    )
    await GuideEvent.filter(guide_event_id=event.guide_event_id).update(created_at=at)


class TestTimelineMerge(TestCase):
    async def test_events_from_every_source_merge_in_time_order(self) -> None:
        patient = await make_patient(1, "SYN-KEY242-A")
        visit = await make_visit(1, patient)

        document = await MedicalDocument.create(
            hospital_id=1,
            visit=visit,
            document_type=OcrDocumentType.PRESCRIPTION,
            file_path="s3://tmp/doc-1",
            file_size=1024,
            mime_type="image/png",
            uploaded_by=STAFF.staff_id,
        )
        await MedicalDocument.filter(document_id=document.document_id).update(created_at=BASE)

        job = await OcrJob.create(
            ocr_job_id="ocr-key242-a",
            hospital_id=1,
            visit=visit,
            status=OcrJobStatus.COMPLETED,
            requested_by=STAFF.staff_id,
        )
        await OcrJob.filter(ocr_job_id=job.ocr_job_id).update(
            created_at=BASE + timedelta(minutes=1),
            completed_at=BASE + timedelta(minutes=5),
        )

        result = await OcrResult.create(ocr_job=job, model_name="synthetic", confirmed_by=STAFF.staff_id)
        await OcrResult.filter(ocr_result_id=result.ocr_result_id).update(confirmed_at=BASE + timedelta(minutes=10))

        guide = await GuideDocument.create(hospital_id=1, visit=visit)
        await guide_event(guide, GuideEventType.GENERATED, STAFF.staff_id, BASE + timedelta(minutes=15))
        await guide_event(
            guide,
            GuideEventType.EDITED,
            DOCTOR.staff_id,
            BASE + timedelta(minutes=20),
            section_key=GuideSectionKey.CAUTION,
        )
        await guide_event(
            guide,
            GuideEventType.RETURNED,
            DOCTOR.staff_id,
            BASE + timedelta(minutes=25),
            reason="처방전 재업로드 필요",
        )

        response = await get_timeline(STAFF, visit.visit_id)

        assert response.status_code == 200
        body = response.json()
        assert body["visit_id"] == visit.visit_id
        events = [(entry["category"], entry["event"]) for entry in body["entries"]]
        assert events == [
            # 진료가 열린 것이 첫 줄이다 — `#176` 을 합치며 더해졌다.
            ("VISIT", "VISIT_CREATED"),
            ("DOCUMENT", "DOCUMENT_UPLOADED"),
            ("OCR", "OCR_STARTED"),
            ("OCR", "OCR_COMPLETED"),
            ("OCR", "OCR_CONFIRMED"),
            ("GUIDE", "GUIDE_GENERATED"),
            ("GUIDE", "GUIDE_EDITED"),
            ("GUIDE", "GUIDE_RETURNED"),
        ]
        assert [e["at"] for e in body["entries"]] == sorted(e["at"] for e in body["entries"])

        edited_entry = next(e for e in body["entries"] if e["event"] == "GUIDE_EDITED")
        assert edited_entry["section_key"] == "caution"
        assert edited_entry["actor_id"] == DOCTOR.staff_id
        returned_entry = next(e for e in body["entries"] if e["event"] == "GUIDE_RETURNED")
        assert returned_entry["note"] == "처방전 재업로드 필요"
        document_entry = next(e for e in body["entries"] if e["event"] == "DOCUMENT_UPLOADED")
        assert document_entry["document_type"] == "PRESCRIPTION"
        assert document_entry["actor_id"] == STAFF.staff_id

    async def test_failed_ocr_job_records_failure_entry(self) -> None:
        patient = await make_patient(1, "SYN-KEY242-F")
        visit = await make_visit(1, patient)
        job = await OcrJob.create(
            ocr_job_id="ocr-key242-f",
            hospital_id=1,
            visit=visit,
            status=OcrJobStatus.FAILED,
            requested_by=STAFF.staff_id,
            failure_code="TIMEOUT",
        )
        await OcrJob.filter(ocr_job_id=job.ocr_job_id).update(created_at=BASE, completed_at=BASE + timedelta(minutes=2))

        response = await get_timeline(DOCTOR, visit.visit_id)

        assert response.status_code == 200
        events = [(e["event"], e["note"]) for e in response.json()["entries"]]
        assert events == [("VISIT_CREATED", None), ("OCR_STARTED", None), ("OCR_FAILED", "TIMEOUT")]

    async def test_a_completed_job_without_a_finish_time_still_shows(self) -> None:
        """**같은 값의 결측을 두 가지로 다루지 않는다.**

        `OcrJob.completed_at` 은 `null=True` 다. 실패 쪽은 `updated_at` 으로
        대비해 두었는데 완료 쪽만 없었다. 그래서 상태만 `COMPLETED` 로 바뀌고
        시각이 안 채워진 작업은 이력에 `OCR_STARTED` 만 남았다 — **스탭이
        판독이 아직 도는 중으로 읽는다.**

        한쪽 규칙을 고칠 때 다른 쪽을 놓치기 쉬운 자리라 검사로 묶어 둔다.
        """
        patient = await make_patient(1, "SYN-KEY242-NC")
        visit = await make_visit(1, patient)
        job = await OcrJob.create(
            ocr_job_id="ocr-key242-nc",
            hospital_id=1,
            visit=visit,
            status=OcrJobStatus.COMPLETED,
            requested_by=STAFF.staff_id,
        )
        await OcrJob.filter(ocr_job_id=job.ocr_job_id).update(
            created_at=BASE, completed_at=None, updated_at=BASE + timedelta(minutes=3)
        )

        response = await get_timeline(STAFF, visit.visit_id)

        assert response.status_code == 200
        events = [e["event"] for e in response.json()["entries"]]
        assert "OCR_COMPLETED" in events, "완료가 이력에서 사라졌다 — 스탭이 도는 중으로 읽는다"

    async def test_a_visit_with_nothing_done_still_has_a_beginning(self) -> None:
        """**빈 목록을 주면 화면이 통째로 빈다.**

        전에는 `entries: []` 였다. 등록만 하고 아무것도 안 한 환자를 열면
        「이력 없음」이 뜨는데, 스탭이 보기에 그것은 「기록이 안 남았다」로도
        읽힌다. 진료가 열린 것 자체가 첫 사건이라 그 줄을 준다.

        `messages` 는 승인 전이라 비어 있다 — 예약은 승인이 만든다.
        """
        patient = await make_patient(1, "SYN-KEY242-E")
        visit = await make_visit(1, patient)

        response = await get_timeline(STAFF, visit.visit_id)

        assert response.status_code == 200
        body = response.json()
        assert [(e["category"], e["event"]) for e in body["entries"]] == [("VISIT", "VISIT_CREATED")]
        assert body["messages"] == []

    async def test_it_says_how_many_guide_pages_there_are(self) -> None:
        """🚩 **분모를 서버가 준다.**

        D1-6 화면이 제 목록으로 장수를 세고 있었다. S2-2 이력 모달은 서버
        값을 쓰는데, 장 목록이 바뀌면 **같은 환자를 두 화면이 다르게 센다**
        (`#189` 리뷰, 2heej).

        이력 모달과 **같은 목록**(`patient_history.GUIDE_PAGES`)에서 온다 —
        여기서 딴 값을 주면 고치려던 불일치가 그대로다.
        """
        patient = await make_patient(1, "SYN-KEY256-T")
        visit = await make_visit(1, patient)

        response = await get_timeline(STAFF, visit.visit_id)

        assert response.status_code == 200
        assert response.json()["guide_pages_total"] == len(GUIDE_PAGES) == 4


class TestTimelineAccess(TestCase):
    async def test_admin_only_account_is_forbidden(self) -> None:
        patient = await make_patient(1, "SYN-KEY242-ADM")
        visit = await make_visit(1, patient)

        response = await get_timeline(ADMIN_ONLY, visit.visit_id)

        assert response.status_code == 403

    async def test_other_hospital_visit_is_not_found(self) -> None:
        patient = await make_patient(1, "SYN-KEY242-X")
        visit = await make_visit(1, patient)

        response = await get_timeline(OTHER_HOSPITAL_STAFF, visit.visit_id)

        assert response.status_code == 404
        assert response.json()["code"] == "VISIT_NOT_FOUND"

    async def test_unknown_visit_is_not_found(self) -> None:
        response = await get_timeline(STAFF, 9_999_999)

        assert response.status_code == 404
