"""승인이 나갈 문자를 세운다 — KEY-234, 와이어프레임 D1-6.

전에는 `guide_document.scheduled_at` 하나뿐이라 **진료 안내문 한 통만**
예약됐다. 확인 회차와 소진 임박은 담길 데가 없어서, 화면이 「예정」이라
적어도 실제로는 아무것도 예약돼 있지 않았다.
"""

from datetime import UTC, datetime

from tortoise.contrib.test import TestCase

from app.core import config
from app.models.ocr import OcrField, OcrJob, OcrResult
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    GuideDocument,
    GuideMessage,
    GuideMessageKind,
    GuideMessageStatus,
    GuideStatus,
    Visit,
)
from app.services.guides import CHECK_HOUR, RUN_OUT_BEFORE_DAYS, GuideService


class Actor:
    """서비스가 보는 것만 흉내낸다 — 라우터를 거치지 않고 규칙만 잰다."""

    def __init__(self, staff: Staff) -> None:
        self.user_id = staff.staff_id
        self.hospital_id = staff.hospital_id
        self.roles = frozenset(staff.roles or [])


class World:
    """세계를 세우는 도구만. **검사는 없다.**

    이걸 `TestCase` 에 섞어 두면, 물려받는 파일마다 부모의 검사가 통째로 다시
    돈다 — 같은 것을 세 번 재게 된다. 도구와 검사를 갈라 둔다.
    """

    async def make_world(self, chart: str = "SCH-01") -> tuple[Actor, Visit, GuideDocument]:
        clinic = await Hospital.create(name="여성의원")
        doctor = await Staff.create(
            hospital=clinic,
            login_id=f"sch_{chart}",
            password_hash="x",
            name="박연",
            roles=["doctor"],
            must_change_password=False,
        )
        patient = await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no=chart,
            name="김서연",
            birth_date="1990-01-01",
            phone="01000000000",
        )
        visit = await Visit.create(
            hospital_id=clinic.hospital_id,
            patient=patient,
            visited_at=datetime(2026, 8, 13, 10, 32, tzinfo=UTC),
        )
        guide = await GuideDocument.create(
            hospital_id=clinic.hospital_id,
            visit=visit,
            status=GuideStatus.APPROVAL_PENDING,
        )
        return Actor(doctor), visit, guide

    async def confirm_course_days(self, visit: Visit, days: str) -> None:
        """판독이 확정한 처방일수를 심는다 — 소진 임박은 이것이 있어야 선다."""
        job = await OcrJob.create(
            ocr_job_id=f"sch-{visit.visit_id}",
            hospital_id=visit.hospital_id,
            visit=visit,
            requested_by=1,
        )
        result = await OcrResult.create(ocr_job=job, model_name="test")
        await OcrField.create(
            ocr_result=result,
            field_type="DURATION_DAYS",
            extracted_value=days,
            is_confirmed=True,
        )


class SendScheduleTestCase(World, TestCase):
    async def test_approval_schedules_the_rounds(self) -> None:
        """승인하면 진료 안내문과 확인 회차가 **함께** 선다."""
        actor, visit, guide = await self.make_world()

        await GuideService().approve(actor, visit.visit_id)

        rows = {m.kind: m for m in await GuideMessage.filter(guide_document=guide).all()}
        assert GuideMessageKind.GUIDE in rows, "진료 안내문이 예약되지 않았다"
        assert GuideMessageKind.CHECK_D7 in rows, "일주일 뒤 확인이 예약되지 않았다"
        assert GuideMessageKind.CHECK_D15 in rows, "보름 뒤가 예약되지 않았다"

        for row in rows.values():
            assert row.status == GuideMessageStatus.SCHEDULED
            assert row.sent_at is None

    async def test_check_rounds_count_from_the_visit_not_the_approval(self) -> None:
        """확인 회차는 **진료일** 기준이다.

        승인일 기준으로 세면 승인이 하루 늦어질 때 「복약 7일째」가 8일째에
        간다 — 환자에게 적는 숫자다.
        """
        actor, visit, guide = await self.make_world("SCH-02")

        await GuideService().approve(actor, visit.visit_id)

        d7 = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.CHECK_D7)
        local = d7.scheduled_at.astimezone(config.TIMEZONE)
        started = visit.visited_at.astimezone(config.TIMEZONE)

        assert (local.date() - started.date()).days == 7, f"7일이 아니라 {local.date()} 다"
        assert local.hour == CHECK_HOUR, f"확인 문자가 {local.hour}시에 간다 — {CHECK_HOUR}시여야 한다"

    async def test_run_out_needs_confirmed_course_days(self) -> None:
        """**처방일수를 모르면 소진 임박을 만들지 않는다.**

        지어낸 날짜로 예약하면 엉뚱한 날 문자가 간다.
        """
        actor, visit, guide = await self.make_world("SCH-03")

        await GuideService().approve(actor, visit.visit_id)
        assert not await GuideMessage.filter(guide_document=guide, kind=GuideMessageKind.RUN_OUT).exists()

    async def test_run_out_lands_before_the_medicine_runs_out(self) -> None:
        """소진 임박은 **소진일보다 앞**이다 — 뒤면 약이 떨어진 뒤에 간다."""
        actor, visit, guide = await self.make_world("SCH-04")
        await self.confirm_course_days(visit, "84")

        await GuideService().approve(actor, visit.visit_id)

        row = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.RUN_OUT)
        local = row.scheduled_at.astimezone(config.TIMEZONE)
        started = visit.visited_at.astimezone(config.TIMEZONE)

        assert (local.date() - started.date()).days == 84 - RUN_OUT_BEFORE_DAYS

    async def test_course_days_with_a_unit_still_counts(self) -> None:
        """「84일」처럼 단위가 붙어 와도 센다 — 판독이 그렇게 읽는 일이 있다."""
        actor, visit, guide = await self.make_world("SCH-05")
        await self.confirm_course_days(visit, "84일")

        await GuideService().approve(actor, visit.visit_id)
        assert await GuideMessage.filter(guide_document=guide, kind=GuideMessageKind.RUN_OUT).exists()

    async def test_unreadable_course_days_makes_nothing(self) -> None:
        """숫자가 아예 없으면 안 만든다 — 지어낸 값으로 예약하지 않는다."""
        actor, visit, guide = await self.make_world("SCH-06")
        await self.confirm_course_days(visit, "알 수 없음")

        await GuideService().approve(actor, visit.visit_id)
        assert not await GuideMessage.filter(guide_document=guide, kind=GuideMessageKind.RUN_OUT).exists()

    async def test_unconfirmed_course_days_is_not_used(self) -> None:
        """**확정된 것만 본다.** 스탭이 아직 확인하지 않은 값으로 발송일을
        잡으면, 고친 뒤에도 옛 날짜로 예약된 채 남는다."""
        actor, visit, guide = await self.make_world("SCH-07")
        job = await OcrJob.create(
            ocr_job_id=f"sch-un-{visit.visit_id}",
            hospital_id=visit.hospital_id,
            visit=visit,
            requested_by=1,
        )
        result = await OcrResult.create(ocr_job=job, model_name="test")
        await OcrField.create(
            ocr_result=result,
            field_type="DURATION_DAYS",
            extracted_value="84",
            is_confirmed=False,  # 아직 확인 전
        )

        await GuideService().approve(actor, visit.visit_id)
        assert not await GuideMessage.filter(guide_document=guide, kind=GuideMessageKind.RUN_OUT).exists()

    async def test_approving_twice_does_not_duplicate(self) -> None:
        """**다시 승인해도 두 번 만들지 않는다.**

        반려됐다가 다시 올라오는 길이 있어서, 그때마다 새로 만들면 환자가
        같은 문자를 두 번 받는다.
        """
        actor, visit, guide = await self.make_world("SCH-08")

        await GuideService().approve(actor, visit.visit_id)
        before = await GuideMessage.filter(guide_document=guide).count()

        # 다시 승인 요청 상태로 되돌려 한 번 더 승인한다.
        # (반려 → 재작성 → 재승인이 실제 경로이고, 여기서 재는 것은 그 끝의
        #  「또 만들지 않는가」다.)
        guide.status = GuideStatus.APPROVAL_PENDING
        await guide.save(update_fields=["status"])
        await GuideService().approve(actor, visit.visit_id)

        after = await GuideMessage.filter(guide_document=guide).count()
        assert after == before, f"다시 승인하니 {before} → {after} 로 늘었다"


class UnapproveTestCase(SendScheduleTestCase):
    """승인을 거둔다 — 승인했는데 잘못된 것을 발견했을 때."""

    async def test_unapprove_cancels_the_schedule(self) -> None:
        """거두면 **예약된 문자를 끈다.** 안 끄면 승인 안 한 글이 나간다."""
        actor, visit, guide = await self.make_world("UN-01")
        await GuideService().approve(actor, visit.visit_id)

        await GuideService().unapprove(actor, visit.visit_id)

        await guide.refresh_from_db()
        assert guide.status == GuideStatus.APPROVAL_PENDING
        assert guide.approved_at is None, "승인 흔적이 남았다"
        assert guide.scheduled_at is None

        rows = await GuideMessage.filter(guide_document=guide).all()
        assert rows, "예약 줄이 사라졌다 — 껐다는 것도 기록이다"
        for row in rows:
            assert row.status == GuideMessageStatus.CANCELED, f"{row.kind} 가 아직 예약돼 있다"

    async def test_sent_messages_block_unapproval(self) -> None:
        """**이미 나간 문자가 있으면 거두지 않는다.**

        환자가 이미 받았는데 「승인 안 한 것」으로 되돌리면, 화면에 안 보이는
        글이 환자 손에 있는 상태가 된다.
        """
        actor, visit, guide = await self.make_world("UN-02")
        await GuideService().approve(actor, visit.visit_id)

        row = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.GUIDE)
        row.status = GuideMessageStatus.SENT
        await row.save(update_fields=["status"])

        try:
            await GuideService().unapprove(actor, visit.visit_id)
        except Exception as exc:  # ApiError
            assert getattr(exc, "status_code", None) == 409, f"막긴 했는데 {exc} 다"
            # 화면이 「새 안내를 보내세요」를 띄우려면 이 코드를 봐야 한다 —
            # 상태만 맞고 코드가 다르면 그냥 「알 수 없는 오류」가 뜬다.
            assert getattr(exc, "code", None) == "GUIDE_ALREADY_SENT", f"코드가 {exc.code} 다"
        else:
            raise AssertionError("이미 나간 문자가 있는데 철회됐다")

        await guide.refresh_from_db()
        assert guide.status == GuideStatus.SCHEDULED_TO_SEND, "막았는데 상태가 바뀌었다"

    async def test_only_approved_can_be_unapproved(self) -> None:
        """승인된 것만 거둔다 — 아직 승인 안 한 것을 거두면 뜻이 없다."""
        actor, visit, _ = await self.make_world("UN-03")

        try:
            await GuideService().unapprove(actor, visit.visit_id)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 409
            assert getattr(exc, "code", None) == "GUIDE_NOT_SCHEDULED", f"코드가 {exc.code} 다"
        else:
            raise AssertionError("승인 요청 상태인데 철회됐다")

    async def test_unapprove_leaves_a_trace(self) -> None:
        """거뒀다는 것이 이력에 남는다 — 지우면 「왜 예약이 사라졌지」에 답할 수 없다."""
        from app.models.visits import GuideEvent, GuideEventType

        actor, visit, guide = await self.make_world("UN-04")
        await GuideService().approve(actor, visit.visit_id)
        await GuideService().unapprove(actor, visit.visit_id)

        kinds = [e.event_type for e in await GuideEvent.filter(guide_document=guide).all()]
        assert GuideEventType.APPROVED in kinds, "승인 줄이 지워졌다"
        assert GuideEventType.UNAPPROVED in kinds, "거둔 것이 안 남았다"

    async def test_reapproving_reuses_the_canceled_rows(self) -> None:
        """다시 승인하면 **껐던 줄을 되살린다** — 새로 만들면 같은 회차가 둘이 된다."""
        actor, visit, guide = await self.make_world("UN-05")
        await GuideService().approve(actor, visit.visit_id)
        before = await GuideMessage.filter(guide_document=guide).count()

        await GuideService().unapprove(actor, visit.visit_id)
        await GuideService().approve(actor, visit.visit_id)

        after = await GuideMessage.filter(guide_document=guide).count()
        assert after == before, f"다시 승인하니 {before} → {after} 로 늘었다"

        live = await GuideMessage.filter(guide_document=guide, status=GuideMessageStatus.SCHEDULED).count()
        assert live == before, f"되살아난 것이 {live}개뿐이다 — 껐던 채로 남으면 문자가 안 나간다"
