"""반려된 안내문이 다시 살아나는가 — KEY-234 (`#176` 리뷰 대응).

리뷰어 지적(Gomin-art): 「`return_to_staff()` 가 상태를 `APPROVAL_RETURNED` 로
바꾸지만 서버는 `STAFF_REVIEW` 와 `APPROVAL_PENDING` 에서만 수정을 허용한다」,
「`submit()` 은 `STAFF_REVIEW` 만 허용해서 재제출이 409 로 막힌다」.

**반려는 「고쳐서 다시 올려라」는 뜻이다.** 고칠 수도 다시 올릴 수도 없으면
반려된 안내문은 영영 그 자리에 갇히고, 화면의 「고친 뒤 다시 넘겨 주세요」는
지킬 수 없는 안내가 된다.

여기서 재는 것은 **한 바퀴 전체**다:

    승인 요청 → 반려 → 스탭 수정 → 재제출 → 의사 승인

토막으로 재면 각 걸음은 통과하는데 이어 붙이면 막히는 자리를 못 본다 —
실제로 그랬다.
"""

from app.models.visits import (
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideSectionKey,
    GuideStatus,
)
from app.tests.guide_apis.test_guide_generate import (
    BASE,
    GenerateGuideTestCase,
    attach_confirmed_ocr,
    make_clinic,
    make_staff,
    make_visit,
)


class TestReturnAndResubmit(GenerateGuideTestCase):
    async def make_world(self, chart: str):
        clinic = await make_clinic()
        staff = await make_staff(clinic, f"{chart}staff", ["staff"])
        doctor = await make_staff(clinic, f"{chart}doctor", ["doctor"])
        visit = await make_visit(clinic, f"SYN-{chart.upper()}")
        await attach_confirmed_ocr(visit, staff.staff_id)
        return clinic, staff, doctor, visit

    async def test_the_whole_round_trip_actually_works(self) -> None:
        """**한 바퀴가 돈다.** 리뷰어가 적어 준 전이 그대로 잰다."""
        _, staff, doctor, visit = await self.make_world("k234rt")

        async with self.client() as client:
            staff_headers = await self.sign_in(staff)
            doctor_headers = await self.sign_in(doctor)

            generated = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=staff_headers)
            submitted = await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)
            returned = await client.post(
                f"{BASE}/{visit.visit_id}/guide/return",
                headers=doctor_headers,
                json={"reason": "복약 안내에 식후 여부를 적어 주세요"},
            )
            # 반려된 뒤 **스탭이** 고친다 — 이 자리가 막혀 있었다
            edited = await client.patch(
                f"{BASE}/{visit.visit_id}/guide/sections/{GuideSectionKey.MEDICATION}",
                headers=staff_headers,
                json={"body": "아침 식후 30분에 한 알 드세요"},
            )
            # 고쳤으니 다시 넘긴다 — 이 자리도 막혀 있었다
            resubmitted = await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)
            approved = await client.post(f"{BASE}/{visit.visit_id}/guide/approve", headers=doctor_headers)

        assert [
            generated.status_code,
            submitted.status_code,
            returned.status_code,
            edited.status_code,
            resubmitted.status_code,
            approved.status_code,
        ] == [201, 200, 200, 200, 200, 200], "한 바퀴 어딘가에서 막힌다"

        guide = await GuideDocument.get(visit_id=visit.visit_id)
        assert guide.status is GuideStatus.SCHEDULED_TO_SEND

    async def test_resubmitting_clears_the_reason_but_keeps_the_history(self) -> None:
        """**지우는 것은 「지금 상태」뿐이다.**

        반려 사유는 스탭 알림에 그대로 뜨는 문장이라, 고쳐서 올린 뒤에도 남아
        있으면 화면이 아직 반려된 것으로 읽는다. 그렇다고 이력까지 지우면
        「왜 한 번 돌아왔는가」의 답이 사라진다 — 그건 감사 기록이다.
        """
        _, staff, doctor, visit = await self.make_world("k234rs")
        why = "용법이 빠졌습니다"

        async with self.client() as client:
            staff_headers = await self.sign_in(staff)
            doctor_headers = await self.sign_in(doctor)
            await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=staff_headers)
            await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)
            await client.post(
                f"{BASE}/{visit.visit_id}/guide/return",
                headers=doctor_headers,
                json={"reason": why},
            )

            guide = await GuideDocument.get(visit_id=visit.visit_id)
            assert guide.returned_reason == why, "반려 사유가 안 담겼다"

            await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)

        guide = await GuideDocument.get(visit_id=visit.visit_id)
        assert guide.status is GuideStatus.APPROVAL_PENDING
        assert guide.returned_reason is None, "다시 올렸는데 지난 반려 사유가 남아 있다"

        # 이력에는 남는다
        events = await GuideEvent.filter(guide_document__visit_id=visit.visit_id).order_by(
            "created_at", "guide_event_id"
        )
        returned_events = [one for one in events if one.event_type is GuideEventType.RETURNED]
        assert len(returned_events) == 1, "반려 이력이 사라졌다"
        assert returned_events[0].reason == why, "이력의 사유가 지워졌다"

        assert [one.event_type for one in events] == [
            GuideEventType.GENERATED,
            GuideEventType.SUBMITTED,
            GuideEventType.RETURNED,
            GuideEventType.SUBMITTED,
        ], "무슨 일이 있었는지 차례대로 읽혀야 한다"

    async def test_approved_guides_still_cannot_be_edited(self) -> None:
        """**뚫은 것은 반려 하나뿐이다.**

        수정 허용 목록에 상태를 하나 더 넣었으니, 승인돼 발송을 기다리는 글까지
        열리지 않았는지 확인한다 — 그건 환자가 받을 것과 승인한 것이 달라지는
        자리다.
        """
        _, staff, doctor, visit = await self.make_world("k234ap")

        async with self.client() as client:
            staff_headers = await self.sign_in(staff)
            doctor_headers = await self.sign_in(doctor)
            await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=staff_headers)
            await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)
            await client.post(f"{BASE}/{visit.visit_id}/guide/approve", headers=doctor_headers)

            blocked = await client.patch(
                f"{BASE}/{visit.visit_id}/guide/sections/{GuideSectionKey.MEDICATION}",
                headers=doctor_headers,
                json={"body": "승인 뒤에 몰래 고친 문장"},
            )

        assert blocked.status_code == 409, "승인된 안내문이 열렸다"
        assert blocked.json()["code"] == "GUIDE_NOT_PENDING"

    async def test_a_returned_guide_is_not_submitted_twice(self) -> None:
        """다시 올린 것을 또 올리지 않는다 — 넘긴 이력이 두 번 쌓인다."""
        _, staff, doctor, visit = await self.make_world("k234tw")

        async with self.client() as client:
            staff_headers = await self.sign_in(staff)
            doctor_headers = await self.sign_in(doctor)
            await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=staff_headers)
            await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)
            await client.post(
                f"{BASE}/{visit.visit_id}/guide/return",
                headers=doctor_headers,
                json={"reason": "고쳐 주세요"},
            )
            await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)
            again = await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)

        assert again.status_code == 409
        assert again.json()["code"] == "GUIDE_NOT_IN_REVIEW"
