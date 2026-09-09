"""시드가 진료에 판독을 심는다 — KEY-271 P1.

규칙(`app/tests/fixtures/ocr_rows.py`)이 아니라 **심는 동작**을 잰다 — 작업
상태, 확정 도장, 재실행, 그리고 심은 것으로 실제 처방이 서는지.
"""

from datetime import UTC, datetime

from tortoise.contrib.test import TestCase

from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit
from app.ocr.security import OcrActor
from app.ocr.service import TortoiseOcrRepository
from app.services.message_dispatch import _course_days as dispatch_course_days
from app.tests.fixtures.ocr_rows import patient_row, patient_rows
from scripts.seed import _seed_ocr


class SeedPlantsReadingsTestCase(TestCase):
    async def make_world(self, chart: str) -> tuple[Hospital, Staff, Visit]:
        clinic = await Hospital.create(name=f"여성의원 {chart}")
        doctor = await Staff.create(
            hospital=clinic,
            login_id=f"seed_{chart}",
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
            phone="01044521234",
        )
        visit = await Visit.create(
            hospital_id=clinic.hospital_id,
            patient=patient,
            doctor_id=doctor.staff_id,
            visited_at=datetime(2026, 9, 3, 3, 0, tzinfo=UTC),
        )
        return clinic, doctor, visit

    async def test_a_visit_with_no_document_gets_no_job(self) -> None:
        """**판독 없는 진료를 남긴다.**

        판독 작업이 하나라도 있으면 `VisitService._refuse_if_locked` 가 담당의·
        진료일·진료과 변경을 409 `VISIT_LOCKED` 로 막는다 — **확정과 무관하다.**
        전부 심으면 시연에서 「진료 정보 고치기」를 보일 진료가 하나도 없다.
        """
        clinic, _, visit = await self.make_world("NO-DOC")

        planted = await _seed_ocr(visit, patient_row("SYN-PCOS-06"), clinic.hospital_id)

        assert planted == (0, 0)
        assert not await OcrJob.filter(visit_id=visit.visit_id).exists()

    async def test_the_planted_job_is_completed_not_processing(self) -> None:
        """**기본값이 `PROCESSING` 이다.**

        그대로 두면 판독 결과 조회가 409 `OCR_RESULT_NOT_READY` 로 떨어져
        확인 화면이 아예 안 뜬다 — 심어 놓고 못 보는 상태가 된다.
        """
        clinic, _, visit = await self.make_world("DONE")

        await _seed_ocr(visit, patient_row("SYN-PCOS-02"), clinic.hospital_id)

        job = await OcrJob.filter(visit_id=visit.visit_id).first()
        assert job is not None
        assert job.status == OcrJobStatus.COMPLETED, f"작업이 {job.status} 다 — 화면이 409 를 받는다"
        assert job.progress == 100
        assert job.excluded_from_guide is False, "제외된 작업은 finalize·generate 가 안 본다"

    async def test_a_staff_review_visit_is_left_unconfirmed(self) -> None:
        """**전부 확정으로 심으면 확인 화면이 죽는다.**

        「확인할 항목 0개」가 뜨고, 다시 확정하면 409 `OCR_FIELD_CONFIRMED` 다.
        S1-6·S1-7 을 볼 표본이 이 두 진료다.
        """
        clinic, _, visit = await self.make_world("REVIEW")

        await _seed_ocr(visit, patient_row("SYN-PCOS-08"), clinic.hospital_id)

        fields = await OcrField.filter(ocr_result__ocr_job__visit_id=visit.visit_id)
        assert fields, "필드를 하나도 안 심었다"
        assert all(not field.is_confirmed for field in fields), "확인 화면에 볼 것이 없다"
        result = await OcrResult.filter(ocr_job__visit_id=visit.visit_id).first()
        assert result is not None and result.confirmed_by is None

    async def test_a_confirmed_visit_carries_the_stamp_of_a_person(self) -> None:
        """**사람 없이 사람이 한 일을 만들지 않는다.**

        확정은 담당의가 찍은 것으로 남긴다 — `seed_smoke_fixture` 가 승인자
        없이는 승인 상태를 안 만드는 것과 같은 까닭이다.
        """
        clinic, doctor, visit = await self.make_world("STAMP")

        await _seed_ocr(visit, patient_row("SYN-PCOS-02"), clinic.hospital_id)

        fields = await OcrField.filter(ocr_result__ocr_job__visit_id=visit.visit_id)
        assert all(field.is_confirmed for field in fields)
        assert all(field.confirmed_by == doctor.staff_id for field in fields)
        assert all(field.confirmed_at is not None for field in fields)

    async def test_a_confirmed_visit_actually_builds_a_prescription(self) -> None:
        """**도장만 찍고 필드가 모자란 상태**를 잡는다.

        「확정으로 심었다」가 참이어도 `PRESCRIPTION_SET` 이나 `FREQUENCY` 가
        빠지면 「확인 완료」가 422 로 멈춘다. 심은 것으로 사슬이 끝까지 도는지를
        여기서 잰다.
        """
        clinic, doctor, visit = await self.make_world("BUILD")
        await _seed_ocr(visit, patient_row("SYN-PCOS-02"), clinic.hospital_id)
        actor = OcrActor(staff_id=doctor.staff_id, hospital_id=clinic.hospital_id, roles=frozenset(["doctor"]))

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        items = await prescription.items.all()
        assert [item.name for item in items] == ["야즈정(드로스피레논/에티닐에스트라디올)"]
        assert prescription.prescription_set == "PCOS · 야즈 (처음)"

    async def test_a_pack_count_becomes_days(self) -> None:
        """**「3통이면 84일. 일수로 읽으면 3일」** — `SYN-PCOS-02` 의 케이스의도 그대로다.

        판독은 원문 `3` 을 읽고 `unit` 에 「통」을 남긴다. 일수로 바꾸는 것은
        읽는 쪽 몫이다 — 안 하면 소진 문자가 81일 일찍 예약된다.
        """
        clinic, doctor, visit = await self.make_world("PACK")
        row = patient_row("SYN-PCOS-02")
        assert (row["총투원문"], row["총투단위"], row["처방일수"]) == ("1/1/3", "통수", "84")
        await _seed_ocr(visit, row, clinic.hospital_id)

        stored = await OcrField.filter(ocr_result__ocr_job__visit_id=visit.visit_id, field_type="DURATION_DAYS").first()
        assert stored is not None
        assert (stored.extracted_value, stored.unit) == ("3", "통"), "환산한 값을 심으면 판독이 읽은 것이 아니다"

        actor = OcrActor(staff_id=doctor.staff_id, hospital_id=clinic.hospital_id, roles=frozenset(["doctor"]))
        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)
        item = (await prescription.items.all())[0]
        assert item.duration_days == 84, f"{item.duration_days}일로 섰다 — 3통을 3일로 읽었다"

    async def test_a_day_count_is_not_multiplied(self) -> None:
        """같은 세트라도 일수 처방은 그대로다 — 단위는 세트가 아니라 그 줄의 성질이다."""
        clinic, doctor, visit = await self.make_world("DAYS")
        row = next(
            r
            for r in patient_rows()
            if r["총투단위"] == "일수" and r["처방일수"] == "84" and r["진료상태"] == "발송 완료"
        )
        await _seed_ocr(visit, row, clinic.hospital_id)
        actor = OcrActor(staff_id=doctor.staff_id, hospital_id=clinic.hospital_id, roles=frozenset(["doctor"]))

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        assert (await prescription.items.all())[0].duration_days == 84

    async def test_the_second_drug_gets_its_own_course_days(self) -> None:
        """**둘째 약도 처방일수를 받는다** — 이희진 님 `#236` ①.

        예전 판은 `next(...)` 로 CSV 에서 처음 걸리는 2약 행을 집고 **개수만** 셌다.
        하필 그 행(`SYN-EMS-08`)의 둘째 약이 「필요시」라, 접미사 없는
        `DURATION_DAYS` 하나만 심던 결함을 통째로 못 봤다 — 개수는 늘 맞았으니까.

        그래서 행을 **이름으로** 집고 소진일까지 잰다. `SYN-PCOS-07` 은 통수(3통)
        처방이라 84일이 되어야 하고, 둘째 약(메트포르민)도 같은 기간을 받는다.
        """
        clinic, doctor, visit = await self.make_world("TWO")
        await _seed_ocr(visit, patient_row("SYN-PCOS-07"), clinic.hospital_id)
        actor = OcrActor(staff_id=doctor.staff_id, hospital_id=clinic.hospital_id, roles=frozenset(["doctor"]))

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        got = [(item.name, item.duration_days) for item in await prescription.items.all()]
        assert len(got) == 2, f"약이 {len(got)}개다 — {got}"
        for name, days in got:
            assert days == 84, f"{name} 의 처방일수가 {days} 다 — 3통은 84일이어야 한다"

    async def test_the_message_pipeline_reads_the_same_days(self) -> None:
        """**문자도 같은 셈을 쓴다** — 이희진 님 `#236` ②.

        `message_dispatch._course_days` 에 사본이 하나 더 있었고, 독스트링이
        「`guides.py` 의 같은 이름과 동일 로직」이라 적어 두었는데 그 짝만 고쳐졌다.
        그러면 예약은 84일 뒤로 맞게 잡히는데 `{일수}` 를 쓰는 RUN_OUT 문구에는
        원문 「3」이 그대로 들어가 **문자가 「3일분」이라고 말한다.**

        같은 규칙을 세 곳에 적어 두면 한 곳만 고쳐진다 — 그것이 이미 한 번 났다.
        """
        clinic, _, visit = await self.make_world("MSG")
        await _seed_ocr(visit, patient_row("SYN-PCOS-07"), clinic.hospital_id)

        assert await dispatch_course_days(visit.visit_id) == 84, "문자 쪽이 통수를 안 보고 원문 숫자를 쓴다"

    async def test_excluded_job_is_skipped_for_message_course_days(self) -> None:
        """**제외된 job 의 처방일수는 문자 본문에 쓰지 않는다.**

        job1(84일)을 제외하고 job2(28일)를 최신으로 두면
        `_course_days` 는 28을 반환해야 한다. 제외 필터 없이 first() 를 부르면
        가장 오래된 84일을 집어 문자 본문이 틀려진다.
        """
        clinic, doctor, visit = await self.make_world("EXCL")
        await _seed_ocr(visit, patient_row("SYN-PCOS-07"), clinic.hospital_id)

        job1 = await OcrJob.filter(visit_id=visit.visit_id).first()
        assert job1 is not None
        job1.excluded_from_guide = True
        await job1.save(update_fields=("excluded_from_guide",))

        job2 = await OcrJob.create(
            ocr_job_id=f"ocr_seed_{visit.visit_id}_v2",
            hospital_id=clinic.hospital_id,
            visit=visit,
            status=OcrJobStatus.COMPLETED,
            progress=100,
            requested_by=doctor.staff_id,
            completed_at=visit.visited_at,
            excluded_from_guide=False,
        )
        result2 = await OcrResult.create(
            ocr_job=job2,
            model_name="seed-test",
            confirmed_by=doctor.staff_id,
            confirmed_at=visit.visited_at,
        )
        await OcrField.create(
            ocr_result=result2,
            field_type="DURATION_DAYS",
            extracted_value="28",
            unit=None,
            confidence=None,
            is_confirmed=True,
            confirmed_by=doctor.staff_id,
            confirmed_at=visit.visited_at,
        )

        assert await dispatch_course_days(visit.visit_id) == 28, (
            "제외된 job(84일)이 아니라 최신 비제외 job(28일)을 봐야 한다"
        )

    async def test_an_as_needed_drug_gets_no_course_days(self) -> None:
        """**「필요시」 약에는 소진일이 없다** — 심는 쪽도 그 규칙을 따른다.

        `_collect_item_rows` 가 `frequency != AS_NEEDED` 로 거르는데, 시드가 그
        약에도 처방일수를 심으면 두 규칙이 어긋난 채로 굴러간다.
        """
        clinic, doctor, visit = await self.make_world("ASNEED")
        await _seed_ocr(visit, patient_row("SYN-EMS-08"), clinic.hospital_id)
        actor = OcrActor(staff_id=doctor.staff_id, hospital_id=clinic.hospital_id, roles=frozenset(["doctor"]))

        prescription = await TortoiseOcrRepository().finalize_ocr(visit.visit_id, actor)

        by_frequency = {item.frequency: item.duration_days for item in await prescription.items.all()}
        assert by_frequency.get("1일 1회") == 56, f"정기 복용 약이 56일을 못 받았다 — {by_frequency}"
        assert by_frequency.get("필요시") is None, f"필요시 약에 소진일이 붙었다 — {by_frequency}"

        #: **심은 것 자체를 본다.** 위 단언만으로는 부족하다 — `_collect_item_rows`
        #: 가 「필요시」를 스스로 거르므로, 시드가 잘못 심어도 결과는 같다. 그러면
        #: 두 규칙이 어긋난 채로 굴러가고, 소비 쪽 가드가 언젠가 바뀌면 그때 드러난다.
        planted = {
            field.field_type
            for field in await OcrField.filter(ocr_result__ocr_job__visit_id=visit.visit_id)
            if field.field_type.startswith("DURATION_DAYS")
        }
        assert planted == {"DURATION_DAYS"}, f"필요시 약에도 처방일수를 심었다 — {sorted(planted)}"

    async def test_seeding_twice_does_not_stack(self) -> None:
        """**같은 명령을 반복해도 쌓이지 않는다** — 시드 전체가 그 규칙으로 짜여 있다."""
        clinic, _, visit = await self.make_world("AGAIN")
        first = await _seed_ocr(visit, patient_row("SYN-PCOS-02"), clinic.hospital_id)

        second = await _seed_ocr(visit, patient_row("SYN-PCOS-02"), clinic.hospital_id)

        assert second == (0, 0), "두 번째 실행이 또 심었다"
        assert await OcrJob.filter(visit_id=visit.visit_id).count() == 1
        assert await OcrField.filter(ocr_result__ocr_job__visit_id=visit.visit_id).count() == first[1]

    async def test_a_visit_without_a_doctor_is_refused(self) -> None:
        """**담당의가 없으면 아예 안 심는다.**

        `requested_by` 는 「누가 읽어 달라고 했는가」다. 적을 사람이 없는데 `0`
        같은 값을 넣으면 아무도 아닌 사람이 판독을 요청한 것이 된다.
        """
        clinic = await Hospital.create(name="담당의 없는 의원")
        patient = await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no="NO-DOC-2",
            name="이지우",
            birth_date="1995-04-02",
            phone="01011112222",
        )
        visit = await Visit.create(
            hospital_id=clinic.hospital_id,
            patient=patient,
            visited_at=datetime(2026, 9, 3, 3, 0, tzinfo=UTC),
        )

        planted = await _seed_ocr(visit, patient_row("SYN-PCOS-02"), clinic.hospital_id)

        assert planted == (0, 0)
        assert not await OcrJob.filter(visit_id=visit.visit_id).exists()
