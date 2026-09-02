"""문자 설정을 서버가 담는다 — KEY-234, 와이어프레임 S1-14.

회차를 켜고 끈 것도, 고친 문구도, 확인 문자 시각도 **화면 안에만** 있었다.
새로고침하면 사라졌고, 승인이 예약을 잡을 때는 코드에 박힌 값을 썼다 —
화면에서 「한 달 뒤」를 켜도 예약은 안 생겼고, 시각을 오후 2시로 바꿔도
10시에 잡혔다. **고른 것과 나가는 것이 갈렸다.**

여기서 재는 것은 그 둘이 같은가다.
"""

from tortoise.contrib.test import TestCase

from app.models.visits import (
    GuideMessage,
    GuideMessageKind,
    GuideMessageSetting,
)
from app.services.guides import CHECK_HOUR, RUN_OUT_BEFORE_DAYS, GuideService

from .test_send_schedule import World


class Plan:
    """라우터의 요청 몸을 흉내낸다 — 서비스가 보는 모양만."""

    def __init__(self, check_hour: int, rounds: list) -> None:
        self.check_hour = check_hour
        self.rounds = rounds


class Round:
    def __init__(self, kind, enabled=True, body=None, days_before=None) -> None:
        self.kind = kind
        self.enabled = enabled
        self.body = body
        self.days_before = days_before


class MessagePlanTestCase(World, TestCase):
    async def test_untouched_plan_answers_with_defaults(self) -> None:
        """한 번도 안 만진 진료도 **기본값으로 답한다.**

        「설정이 없다」와 「기본값이다」를 화면이 가를 이유가 없다. 가르게 하면
        화면마다 기본값을 따로 알게 되고, 서버가 기본값을 바꿔도 안 따라온다.
        """
        actor, visit, _ = await self.make_world("PL-01")

        plan = await GuideService().message_plan(actor, visit.visit_id)

        assert plan["check_hour"] == CHECK_HOUR
        by = {r["kind"]: r for r in plan["rounds"]}
        assert by["CHECK_D7"]["enabled"] is True
        assert by["CHECK_D15"]["enabled"] is True
        assert by["CHECK_D30"]["enabled"] is False, "한 달 뒤는 기본이 꺼짐이다 (S1-14)"
        assert by["RUN_OUT"]["enabled"] is True
        assert by["RUN_OUT"]["days_before"] == RUN_OUT_BEFORE_DAYS

        assert not await GuideMessageSetting.filter(guide_document__visit_id=visit.visit_id).exists(), (
            "안 만졌는데 행을 미리 채웠다"
        )

    async def test_plan_says_which_round_is_fixed(self) -> None:
        """**끌 수 없는 회차를 서버가 알려 준다.**

        화면이 스스로 알면 화면마다 다르게 알게 되고, 한쪽에서만 꺼진다.
        """
        actor, visit, _ = await self.make_world("PL-02")
        by = {r["kind"]: r for r in (await GuideService().message_plan(actor, visit.visit_id))["rounds"]}
        assert by["CHECK_D7"]["fixed"] is True, "일주일 뒤가 고정이 아니다"
        assert by["CHECK_D15"]["fixed"] is False
        assert by["RUN_OUT"]["fixed"] is False

    async def test_saved_plan_comes_back(self) -> None:
        """저장한 것이 그대로 돌아온다 — 새로고침하면 사라지던 자리다."""
        actor, visit, _ = await self.make_world("PL-03")

        saved = await GuideService().save_message_plan(
            actor,
            visit.visit_id,
            Plan(
                14,
                [
                    Round(GuideMessageKind.CHECK_D15, enabled=False),
                    Round(GuideMessageKind.CHECK_D30, enabled=True, body="{환자명}님, 한 달째입니다. {링크}"),
                    Round(GuideMessageKind.RUN_OUT, enabled=True, days_before=5),
                ],
            ),
        )

        assert saved["check_hour"] == 14
        by = {r["kind"]: r for r in saved["rounds"]}
        assert by["CHECK_D15"]["enabled"] is False
        assert by["CHECK_D30"]["enabled"] is True
        assert by["CHECK_D30"]["body"] == "{환자명}님, 한 달째입니다. {링크}"
        assert by["RUN_OUT"]["days_before"] == 5

        again = await GuideService().message_plan(actor, visit.visit_id)
        assert again == saved, "다시 읽으니 다른 것이 나온다"

    async def test_the_first_week_cannot_be_turned_off(self) -> None:
        """**일주일 뒤는 끌 수 없다.**

        원문이 「(고정)」이라 적고 주석도 「여기서도 끌 수 없다」고 못박는다 —
        복약 첫 주가 가장 잘 끊기는 구간이다. 화면이 체크박스를 잠그지만,
        요청은 그냥 온다.
        """
        actor, visit, _ = await self.make_world("PL-04")

        saved = await GuideService().save_message_plan(
            actor, visit.visit_id, Plan(CHECK_HOUR, [Round(GuideMessageKind.CHECK_D7, enabled=False)])
        )

        by = {r["kind"]: r for r in saved["rounds"]}
        assert by["CHECK_D7"]["enabled"] is True, "일주일 뒤가 꺼졌다"

    async def test_emptying_the_body_means_back_to_default(self) -> None:
        """문구를 다 지운 것은 「빈 문자를 보내라」가 아니라 「기본으로」다."""
        actor, visit, _ = await self.make_world("PL-05")

        await GuideService().save_message_plan(
            actor, visit.visit_id, Plan(CHECK_HOUR, [Round(GuideMessageKind.CHECK_D15, body="고친 문구")])
        )
        saved = await GuideService().save_message_plan(
            actor, visit.visit_id, Plan(CHECK_HOUR, [Round(GuideMessageKind.CHECK_D15, body="   ")])
        )

        by = {r["kind"]: r for r in saved["rounds"]}
        assert by["CHECK_D15"]["body"] is None, "빈 문구가 저장됐다 — 빈 문자가 나간다"

    async def test_a_time_nobody_can_pick_is_refused(self) -> None:
        """**새벽 3시에 문자가 가지 않는다.** 화면이 못 고르는 값은 서버도 안 받는다."""
        actor, visit, _ = await self.make_world("PL-06")

        try:
            await GuideService().save_message_plan(actor, visit.visit_id, Plan(3, []))
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 422, f"막긴 했는데 {exc} 다"
        else:
            raise AssertionError("새벽 3시가 저장됐다")

    async def test_days_before_stays_in_range(self) -> None:
        """소진 0일 전은 임박이 아니라 당일이고, 너무 크면 처방 시작 전이 된다."""
        actor, visit, _ = await self.make_world("PL-07")

        for bad in (0, 99):
            try:
                await GuideService().save_message_plan(
                    actor,
                    visit.visit_id,
                    Plan(CHECK_HOUR, [Round(GuideMessageKind.RUN_OUT, days_before=bad)]),
                )
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 422, f"{bad} 을 막긴 했는데 {exc} 다"
            else:
                raise AssertionError(f"소진 {bad}일 전이 저장됐다")

    async def test_approved_guides_are_locked(self) -> None:
        """**승인 뒤에는 못 고친다.**

        고치면 이미 잡힌 예약과 어긋난다 — 화면에는 새 문구가, 예약에는 옛
        문구가 남는다. 고치려면 승인을 거두고 고친 뒤 다시 승인한다.
        """
        actor, visit, guide = await self.make_world("PL-08")
        await GuideService().approve(actor, visit.visit_id)

        try:
            await GuideService().save_message_plan(actor, visit.visit_id, Plan(14, []))
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 409, f"막긴 했는데 {exc} 다"
        else:
            raise AssertionError("승인된 뒤에 문자 설정이 바뀌었다")

        await guide.refresh_from_db()
        assert guide.check_hour == CHECK_HOUR, "막았는데 시각이 바뀌었다"


class PlanDrivesScheduleTestCase(World, TestCase):
    """**고른 것이 실제로 예약된다** — 이것이 저장하는 이유 전부다."""

    async def test_turning_a_round_on_schedules_it(self) -> None:
        """한 달 뒤를 켜면 그 문자가 예약된다 — 예전에는 켜도 안 생겼다."""
        actor, visit, guide = await self.make_world("PD-01")

        await GuideService().save_message_plan(
            actor, visit.visit_id, Plan(CHECK_HOUR, [Round(GuideMessageKind.CHECK_D30, enabled=True)])
        )
        await GuideService().approve(actor, visit.visit_id)

        kinds = {m.kind for m in await GuideMessage.filter(guide_document=guide)}
        assert GuideMessageKind.CHECK_D30 in kinds, "켰는데 예약이 안 생겼다"

    async def test_turning_a_round_off_skips_it(self) -> None:
        """보름 뒤를 끄면 그 문자는 안 나간다."""
        actor, visit, guide = await self.make_world("PD-02")

        await GuideService().save_message_plan(
            actor, visit.visit_id, Plan(CHECK_HOUR, [Round(GuideMessageKind.CHECK_D15, enabled=False)])
        )
        await GuideService().approve(actor, visit.visit_id)

        kinds = {m.kind for m in await GuideMessage.filter(guide_document=guide)}
        assert GuideMessageKind.CHECK_D15 not in kinds, "껐는데 예약이 생겼다"
        assert GuideMessageKind.CHECK_D7 in kinds, "안 끈 회차까지 사라졌다"

    async def test_the_chosen_hour_is_the_hour_it_goes(self) -> None:
        """고른 시각에 나간다 — 오후 2시로 바꿔도 10시에 잡히던 자리다."""
        actor, visit, guide = await self.make_world("PD-03")

        await GuideService().save_message_plan(actor, visit.visit_id, Plan(14, []))
        await GuideService().approve(actor, visit.visit_id)

        row = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.CHECK_D7)
        from app.core import config

        assert row.scheduled_at.astimezone(config.TIMEZONE).hour == 14, (
            f"오후 2시로 골랐는데 {row.scheduled_at.astimezone(config.TIMEZONE).hour}시에 잡혔다"
        )

    async def test_the_first_week_goes_out_even_if_a_row_says_off(self) -> None:
        """표에 꺼짐이 적혀 있어도 일주일 뒤는 나간다 — 마지막 그물이다."""
        actor, visit, guide = await self.make_world("PD-04")

        doc = await guide.__class__.get(visit_id=visit.visit_id)
        await GuideMessageSetting.create(
            guide_document_id=doc.guide_document_id, kind=GuideMessageKind.CHECK_D7, enabled=False
        )
        await GuideService().approve(actor, visit.visit_id)

        kinds = {m.kind for m in await GuideMessage.filter(guide_document=guide)}
        assert GuideMessageKind.CHECK_D7 in kinds, "일주일 뒤가 안 나간다"

    async def test_run_out_uses_the_chosen_days_before(self) -> None:
        """소진 며칠 전도 고른 값을 쓴다."""
        actor, visit, guide = await self.make_world("PD-05")
        await self.confirm_course_days(visit, "84")

        await GuideService().save_message_plan(
            actor, visit.visit_id, Plan(CHECK_HOUR, [Round(GuideMessageKind.RUN_OUT, days_before=7)])
        )
        await GuideService().approve(actor, visit.visit_id)

        row = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.RUN_OUT)
        want = GuideService.check_at(visit.visited_at, 84 - 7, CHECK_HOUR)
        assert row.scheduled_at == want, f"{want} 이어야 하는데 {row.scheduled_at} 이다"

    async def test_run_out_can_be_turned_off(self) -> None:
        """소진 임박도 끌 수 있다 — 회차와 같은 규칙이다."""
        actor, visit, guide = await self.make_world("PD-06")
        await self.confirm_course_days(visit, "84")

        await GuideService().save_message_plan(
            actor, visit.visit_id, Plan(CHECK_HOUR, [Round(GuideMessageKind.RUN_OUT, enabled=False)])
        )
        await GuideService().approve(actor, visit.visit_id)

        kinds = {m.kind for m in await GuideMessage.filter(guide_document=guide)}
        assert GuideMessageKind.RUN_OUT not in kinds, "껐는데 소진 임박이 예약됐다"


class HeldTestCase(World, TestCase):
    """**보류는 실패와 다른 축이다** — 와이어프레임 S2-3.

    실패는 「보내려 했고 안 됐다」(지난 일), 보류는 「아직 안 보냈고, 지금
    보내면 안 될 것을 안다」(앞일)다. 같은 번호가 08-11 에는 실패, 08-14 에는
    보류인 것이 원문이다.

    **아직 아무것도 이 상태를 만들지 않는다** — 문자를 보내는 것이 없다.
    여기서 재는 것은 표와 화면이 그 상태를 **담고 나를 수 있는가**다.
    """

    async def test_a_held_row_survives(self) -> None:
        """보류 한 줄이 사유와 함께 남는다."""
        from app.models.visits import GuideMessageFailure, GuideMessageHold, GuideMessageStatus

        actor, visit, guide = await self.make_world("HD-01")
        await GuideService().approve(actor, visit.visit_id)

        row = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.CHECK_D7)
        row.status = GuideMessageStatus.HELD
        row.hold_reason = GuideMessageHold.NO_CREDIT
        await row.save(update_fields=["status", "hold_reason"])

        again = await GuideMessage.get(guide_message_id=row.guide_message_id)
        assert again.status == GuideMessageStatus.HELD
        assert again.hold_reason == GuideMessageHold.NO_CREDIT
        assert again.failure_code is None, "보류인데 실패 사유가 찼다"

        # 실패는 실패대로 담긴다 — 두 칸이 서로를 밀어내지 않는다
        other = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.GUIDE)
        other.status = GuideMessageStatus.FAILED
        other.failure_code = GuideMessageFailure.INVALID_PHONE
        await other.save(update_fields=["status", "failure_code"])

        back = await GuideMessage.get(guide_message_id=other.guide_message_id)
        assert back.failure_code == GuideMessageFailure.INVALID_PHONE
        assert back.hold_reason is None

    async def test_the_timeline_carries_both(self) -> None:
        """화면이 그릴 수 있게 두 칸을 **함께** 내려 준다."""
        from app.dependencies.patient_access import ClinicalActor
        from app.models.visits import GuideMessageHold, GuideMessageStatus
        from app.services.visit_timeline import VisitTimelineService

        actor, visit, guide = await self.make_world("HD-02")
        await GuideService().approve(actor, visit.visit_id)

        row = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.CHECK_D7)
        row.status = GuideMessageStatus.HELD
        row.hold_reason = GuideMessageHold.INVALID_PHONE
        await row.save(update_fields=["status", "hold_reason"])

        # `World` 의 가짜 액터는 `user_id` 를 쓴다 — 라우터를 안 거치고 규칙만
        # 재려고 만든 것이라 서비스가 보는 것만 흉내낸다. 이력 서비스는
        # `ClinicalActor` 를 요구하므로 여기서 옮겨 준다.
        who = ClinicalActor(staff_id=actor.user_id, hospital_id=actor.hospital_id, roles=actor.roles)
        seen = await VisitTimelineService().timeline(who, visit.visit_id)
        held = [m for m in seen.messages if m.status == "HELD"]
        assert held, "보류 줄이 화면까지 안 간다"
        assert held[0].hold_reason == "INVALID_PHONE", "사유가 안 간다 — 화면이 「보류」로만 적는다"

    async def test_the_two_lists_are_not_the_same(self) -> None:
        """**사유 목록이 갈려 있다** — 보류는 둘(S2-3), 실패는 넷(D1-7).

        한 목록으로 합치고 싶어지는 자리다. 겹치는 낱말이 있기 때문이다.
        그러나 재는 것이 다르다 — 「보내기 전에 이미 아는 것」과 「보내 보고
        안 것」이다.
        """
        from app.models.visits import GuideMessageFailure, GuideMessageHold

        assert {m.value for m in GuideMessageHold} == {"INVALID_PHONE", "NO_CREDIT"}
        assert {m.value for m in GuideMessageFailure} == {
            "INVALID_PHONE",
            "OPT_OUT",
            "CARRIER",
            "SENDER_UNREGISTERED",
        }
        assert {m.value for m in GuideMessageHold} != {m.value for m in GuideMessageFailure}

    async def test_nothing_produces_these_yet(self) -> None:
        """**아직 아무것도 보류·실패를 만들지 않는다.**

        문자를 보내는 것이 없기 때문이다. 이 검사는 그 사실을 기록해 두는
        자리다 — 발송기가 붙는 날 여기가 먼저 깨져서, 화면의 「[demo] 문자
        발송기는 아직 붙지 않았습니다」를 지우는 것을 잊지 않게 한다.
        """
        import pathlib

        service = pathlib.Path("app/services/guides.py").read_text(encoding="utf-8")
        # 승인 철회가 「이미 나갔나」를 묻느라 SENT 를 읽기는 한다. **쓰지는** 않는다.
        assert "status=GuideMessageStatus.SENT," in service, "읽는 자리까지 사라졌다"
        assert "= GuideMessageStatus.SENT" not in service, (
            "무언가 SENT 로 바꾸기 시작했다 — 발송기가 붙었으면 화면의 [demo] 문구를 지워야 한다"
        )
        assert "GuideMessageStatus.HELD" not in service, (
            "무언가 보류를 만들기 시작했다 — 화면의 [demo] 문구를 지워야 한다"
        )

    async def test_a_reason_outside_the_list_is_refused(self) -> None:
        """**목록 밖의 사유는 안 들어간다.**

        자유 문자열로 두면 발송기를 붙이는 사람마다 다른 낱말을 넣고
        (`SMS_FAIL_3`, `번호오류`, …), 화면은 그중 아는 것만 사람 말로 옮긴다 —
        나머지는 「못 나감」으로만 보여 무엇을 고쳐야 하는지 알 수 없다.
        """
        from app.models.visits import GuideMessageStatus

        actor, visit, guide = await self.make_world("HD-03")
        await GuideService().approve(actor, visit.visit_id)
        row = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.GUIDE)

        row.status = GuideMessageStatus.FAILED
        # **일부러 목록에 없는 값을 넣는다.** mypy 를 달래려고 올바른 값으로
        # 바꾸면 「막는가」를 재는 검사가 「통과하는가」를 재는 검사가 된다.
        row.failure_code = "SMS_FAIL_3"  # type: ignore[assignment]
        try:
            await row.save(update_fields=["status", "failure_code"])
        except ValueError:
            pass
        else:
            raise AssertionError("목록에 없는 실패 사유가 저장됐다")

        row2 = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.CHECK_D7)
        row2.status = GuideMessageStatus.HELD
        row2.hold_reason = "잔량없음"  # type: ignore[assignment]  # 목록 밖 값 — 그것이 이 검사다
        try:
            await row2.save(update_fields=["status", "hold_reason"])
        except ValueError:
            pass
        else:
            raise AssertionError("목록에 없는 보류 사유가 저장됐다")

    async def test_a_failure_reason_is_not_a_hold_reason(self) -> None:
        """**두 목록을 서로의 칸에 넣을 수 없다.**

        「보류 · 발신번호 미등록」처럼 적히면, 보내 본 적이 없는데 보내 봤다는
        말이 된다. 화면에서 가르는 것만으로는 부족하다 — 표가 먼저 막는다.
        """
        from app.models.visits import GuideMessageStatus

        actor, visit, guide = await self.make_world("HD-04")
        await GuideService().approve(actor, visit.visit_id)
        row = await GuideMessage.get(guide_document=guide, kind=GuideMessageKind.CHECK_D7)

        row.status = GuideMessageStatus.HELD
        # `CARRIER` 를 고른 이유는 **짧기 때문**이다. `SENDER_UNREGISTERED` 는
        # 19자라 칸 길이(13)에 먼저 걸려, 목록이 갈려 있어서 막힌 것인지
        # 길어서 막힌 것인지 알 수 없다 — 검사가 헛돈다.
        # 아래 무시 표시는 목록 밖 값을 일부러 넣기 때문이다
        row.hold_reason = "CARRIER"  # type: ignore[assignment]  # 실패 목록에만 있는 값 (7자)
        try:
            await row.save(update_fields=["status", "hold_reason"])
        except ValueError:
            pass
        else:
            raise AssertionError("실패 사유가 보류 칸에 들어갔다")
