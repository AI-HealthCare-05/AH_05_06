"""확인 항목의 답 — KEY-234, 와이어프레임 S1-6.

처방을 내기 전에 스탭이 환자에게 여쭙는 것들이다. 담을 자리가 없어 체크박스가
꺼진 채로 서 있었다 — 켤 수 있게 두면 스탭이 「우울증 병력」을 체크하고 저장됐다고
믿는데 아무 데도 안 남았기 때문이다. 안전에 걸리는 항목이라 그 오해가 가장 나쁘다.

여기서 재는 것은 **안 물어본 것과 「아니오」를 가르는가**다.
"""

from datetime import UTC, datetime

from tortoise.contrib.test import TestCase

from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit, VisitCheckAnswer, VisitCheckKey
from app.services.visits import VisitCheckService


class Actor:
    def __init__(self, staff: Staff) -> None:
        self.user_id = staff.staff_id
        self.hospital_id = staff.hospital_id
        self.roles = frozenset(staff.roles or [])


class Answer:
    """라우터의 요청 몸을 흉내낸다."""

    def __init__(self, item_key, checked) -> None:
        self.item_key = item_key
        self.checked = checked


class Plan:
    def __init__(self, answers: list) -> None:
        self.answers = answers


class CheckAnswerTestCase(TestCase):
    async def make_world(self, chart: str) -> tuple[Actor, Visit]:
        # 병원 이름은 유일하다 — 한 검사에서 두 병원을 세울 때 부딪힌다
        clinic = await Hospital.create(name=f"여성의원 {chart}")
        staff = await Staff.create(
            hospital=clinic,
            login_id=f"chk_{chart}",
            password_hash="x",
            name="한소영",
            roles=["staff"],
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
            visited_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        )
        return Actor(staff), visit

    async def test_untouched_answers_are_unasked(self) -> None:
        """한 번도 안 여쭌 진료는 **전부 `None`** 이다.

        `False` 로 주면 「여쭤서 아니라고 했다」가 되고, 안내문이 「우울증 병력
        없음」을 확인한 것처럼 적을 수 있다 — 실제로는 아무도 안 물었는데.
        """
        actor, visit = await self.make_world("CK-01")

        got = await VisitCheckService().read(actor, visit.visit_id)

        assert got["visit_id"] == visit.visit_id
        assert len(got["answers"]) == len(VisitCheckKey), "물어볼 항목을 다 안 준다"
        for row in got["answers"]:
            assert row["checked"] is None, f"{row['item_key']} 가 안 여쭌 것으로 안 온다"

    async def test_every_item_comes_back_even_without_an_answer(self) -> None:
        """**물어볼 항목 전부**를 준다 — 답이 있는 것만 주면 안 된다.

        화면이 나머지를 스스로 세워야 하고, 그러면 항목 목록이 두 곳에 생겨
        한쪽만 바뀐다.
        """
        actor, visit = await self.make_world("CK-02")
        await VisitCheckService().save(actor, visit.visit_id, Plan([Answer(VisitCheckKey.DIABETES, True)]))

        got = await VisitCheckService().read(actor, visit.visit_id)
        keys = [r["item_key"] for r in got["answers"]]
        assert keys == [k.value for k in VisitCheckKey], "항목이 빠지거나 차례가 다르다"

    async def test_yes_and_no_are_both_kept(self) -> None:
        """**「예」와 「아니오」를 둘 다 남긴다.**"""
        actor, visit = await self.make_world("CK-03")

        got = await VisitCheckService().save(
            actor,
            visit.visit_id,
            Plan(
                [
                    Answer(VisitCheckKey.DEPRESSION, True),
                    Answer(VisitCheckKey.DIABETES, False),
                ]
            ),
        )

        by = {r["item_key"]: r["checked"] for r in got["answers"]}
        assert by["DEPRESSION"] is True
        assert by["DIABETES"] is False, "「아니오」가 안 여쭌 것으로 뭉개졌다"
        assert by["HYPERTENSION"] is None, "안 여쭌 것이 「아니오」가 됐다"

    async def test_null_clears_the_answer(self) -> None:
        """`None` 으로 보내면 **안 여쭌 것으로 되돌린다** — 행을 지운다.

        `False` 로 담아 두면 여쭤서 아니라고 한 것과 섞인다.
        """
        actor, visit = await self.make_world("CK-04")
        await VisitCheckService().save(actor, visit.visit_id, Plan([Answer(VisitCheckKey.DEPRESSION, False)]))
        assert await VisitCheckAnswer.filter(visit_id=visit.visit_id).exists()

        got = await VisitCheckService().save(actor, visit.visit_id, Plan([Answer(VisitCheckKey.DEPRESSION, None)]))

        by = {r["item_key"]: r["checked"] for r in got["answers"]}
        assert by["DEPRESSION"] is None
        assert not await VisitCheckAnswer.filter(visit_id=visit.visit_id, item_key=VisitCheckKey.DEPRESSION).exists(), (
            "되돌렸는데 행이 남았다"
        )

    async def test_saving_twice_does_not_duplicate(self) -> None:
        """같은 항목을 다시 답해도 줄이 늘지 않는다."""
        actor, visit = await self.make_world("CK-05")

        for value in (True, False, True):
            await VisitCheckService().save(actor, visit.visit_id, Plan([Answer(VisitCheckKey.DEPRESSION, value)]))

        rows = await VisitCheckAnswer.filter(visit_id=visit.visit_id, item_key=VisitCheckKey.DEPRESSION)
        assert len(rows) == 1, f"줄이 {len(rows)}개다"
        assert rows[0].checked is True, "마지막 답이 안 남았다"

    async def test_who_answered_is_kept(self) -> None:
        """누가 답했는지 남는다 — 나중에 「누가 이걸 확인했나」를 물을 자리다."""
        actor, visit = await self.make_world("CK-06")

        await VisitCheckService().save(actor, visit.visit_id, Plan([Answer(VisitCheckKey.PREGNANCY_PLAN, True)]))

        row = await VisitCheckAnswer.get(visit_id=visit.visit_id, item_key=VisitCheckKey.PREGNANCY_PLAN)
        assert row.answered_by == actor.user_id, "답한 사람이 안 남았다"
        assert row.answered_at is not None, "답한 시각이 안 남았다"

    async def test_another_clinic_cannot_read_or_write(self) -> None:
        """**다른 병원의 진료는 없는 것과 같다.**"""
        actor, visit = await self.make_world("CK-07")
        stranger, _ = await self.make_world("CK-08")

        for run in (
            lambda: VisitCheckService().read(stranger, visit.visit_id),
            lambda: VisitCheckService().save(stranger, visit.visit_id, Plan([Answer(VisitCheckKey.DIABETES, True)])),
        ):
            try:
                await run()
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 404, f"막긴 했는데 {exc} 다"
            else:
                raise AssertionError("다른 병원 진료의 확인 항목에 닿았다")

    async def test_an_unknown_item_is_refused(self) -> None:
        """목록에 없는 항목은 안 담긴다 — 화면 문구가 바뀌어도 옛 답이 미아가 되지 않게."""
        actor, visit = await self.make_world("CK-09")

        try:
            await VisitCheckService().save(actor, visit.visit_id, Plan([Answer("흡연 여부", True)]))
        except ValueError:
            pass
        else:
            raise AssertionError("목록에 없는 항목이 저장됐다")
