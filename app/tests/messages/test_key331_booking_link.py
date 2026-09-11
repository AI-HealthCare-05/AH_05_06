"""`{예약링크}` 는 안내문 링크가 아니다 — KEY-331.

**있었던 일.** 소진(`RUN_OUT`)·재진 문자의 기본 문구는 「재진 예약을
잡아주세요: {예약링크}」인데, 그 값을 채울 데가 없었다 — `hospital` 표에는
이름 한 칸뿐이고 A1-4(의원 정보) 화면도 없었다. 발송 코드는 `{링크}` 에 넣던
값(그 환자의 안내문 링크)을 `{예약링크}` 에도 그대로 넣었다.

    values["링크"] = link
    values["예약링크"] = link      # ← 같은 값

그래서 환자가 「예약을 잡아주세요」를 누르면 **제 안내문이 다시 열렸다.**
주석도 검사도 없어서, 누른 환자 말고는 아무도 몰랐다.

여기서 재는 것 셋.

    다른 값     한 문구에 둘이 같이 있어도 서로 다른 곳을 가리킨다
    안 보냄     예약 주소가 비어 있으면 빈칸을 채워 보내지 않고 붙든다
    문구 기준   회차 이름이 아니라 **그 의원이 실제로 쓰는 문구**로 잰다
"""

from tortoise.contrib.test import TestCase

from app.models.catalog import MessageTemplate, MessageTemplateKind
from app.models.staffs import Hospital
from app.models.visits import (
    GuideMessage,
    GuideMessageHold,
    GuideMessageKind,
    GuideMessageStatus,
    PatientGuideLink,
)
from app.services.dispatch_gate import gate_hold_reason
from app.services.message_dispatch import dispatch_message, render_message_body
from app.services.sms_sender import MockSmsSender
from app.tests.messages.test_key249_dispatch_pipeline import make_due_message

BOOKING_URL = "https://booking.example.com/dorothy"


async def _set_booking_url(message: GuideMessage, url: str | None) -> Hospital:
    guide = await message.guide_document
    hospital = await Hospital.get(hospital_id=guide.hospital_id)
    hospital.booking_url = url  # type: ignore[assignment]  # 빈 문자열·None 둘 다 재 본다
    await hospital.save(update_fields=["booking_url"])
    return hospital


async def _set_template(message: GuideMessage, body: str) -> None:
    guide = await message.guide_document
    await MessageTemplate.update_or_create(
        hospital_id=guide.hospital_id,
        kind=MessageTemplateKind(message.kind.value),
        defaults={"body": body},
    )


class TestTheTwoLinksAreDifferentThings(TestCase):
    async def test_the_booking_variable_is_the_clinic_booking_page(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)
        await _set_booking_url(message, BOOKING_URL)

        body = await render_message_body(message)

        assert "{예약링크}" not in body
        assert BOOKING_URL in body

    async def test_the_booking_variable_is_not_the_guide_link(self) -> None:
        """**이것이 그 버그다.** 예약 링크 자리에 안내문 링크가 들어가면 안 된다.

        안내문 링크는 `…/otp.html#t=<원문>` 모양이다. 그 경로가 예약 문구에
        나타나면 환자가 예약 화면 대신 제 안내문을 연다.
        """
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)
        await _set_booking_url(message, BOOKING_URL)

        body = await render_message_body(message)

        assert "otp.html" not in body, "예약 링크 자리에 안내문 링크가 들어갔다"
        assert await PatientGuideLink.filter(guide_document_id=message.guide_document_id).count() == 0, (
            "아무도 안 받을 링크 토큰을 발급했다"
        )

    async def test_both_in_one_body_point_to_different_places(self) -> None:
        """한 문구가 둘을 다 쓰면 **두 값이 서로 달라야** 뜻이 산다."""
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)
        await _set_booking_url(message, BOOKING_URL)
        await _set_template(message, "안내는 {링크} · 예약은 {예약링크}")

        body = await render_message_body(message)

        assert "{링크}" not in body and "{예약링크}" not in body
        assert BOOKING_URL in body
        assert "otp.html" in body, "안내문 링크가 안 채워졌다"
        guide_link, booking = body.split("안내는 ")[1].split(" · 예약은 ")
        assert guide_link != booking, "두 변수에 같은 값이 들어갔다"


class TestAnEmptyBookingUrlHoldsTheMessage(TestCase):
    async def test_the_gate_holds_when_the_clinic_has_no_booking_url(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)

        assert await gate_hold_reason(message) is GuideMessageHold.BOOKING_URL_MISSING

    async def test_the_gate_lets_it_through_once_the_url_is_filled(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)
        await _set_booking_url(message, BOOKING_URL)

        assert await gate_hold_reason(message) is None

    async def test_a_blank_url_counts_as_missing(self) -> None:
        """A1-4 가 공백을 `None` 으로 접지만(`_clean`), 표에 옛 줄이 있을 수 있다."""
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)
        await _set_booking_url(message, "")

        assert await gate_hold_reason(message) is GuideMessageHold.BOOKING_URL_MISSING

    async def test_dispatch_holds_instead_of_sending_a_dangling_sentence(self) -> None:
        """**빈칸을 채워 보내지 않는다.**

        「재진 예약을 잡아주세요: 」가 나가면 환자는 누를 것이 없고, 의원은 그
        환자가 예약을 안 잡았다고 읽는다. 붙들어 두면 보류 목록(S2-3)이
        관리자가 A1-4 에서 채워야 할 일을 가리킨다.
        """
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)
        sender = MockSmsSender()

        result = await dispatch_message(message.guide_message_id, sender)

        assert result is not None
        assert result.status is GuideMessageStatus.HELD
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.hold_reason is GuideMessageHold.BOOKING_URL_MISSING
        assert updated.sent_at is None and updated.sent_body is None
        assert updated.claim_token is None

    async def test_the_same_message_goes_out_after_the_admin_fills_it_in(self) -> None:
        """보류는 **끝이 아니다** — 채우고 나면 그 문자가 제 일을 한다."""
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)
        await _set_booking_url(message, BOOKING_URL)

        result = await dispatch_message(message.guide_message_id, MockSmsSender())

        assert result is not None
        assert result.status is GuideMessageStatus.SENT
        updated = await GuideMessage.get(guide_message_id=message.guide_message_id)
        assert updated.sent_body is not None
        assert BOOKING_URL in updated.sent_body


class TestTheGateReadsTheBodyNotTheKind(TestCase):
    """**회차 이름으로 재지 않는다.**

    기본 문구에서는 소진·재진만 `{예약링크}` 를 쓰지만, 의원은 D2-5 에서 아무
    회차 문구에나 그 변수를 넣을 수 있다(`KNOWN_VARIABLES` 가 전 회차 공통).
    회차로 재면 그렇게 고친 의원의 문자만 빈칸으로 나가고, 그것은 **고친
    사람만 겪는 버그**라 제일 늦게 발견된다.
    """

    async def test_a_guide_message_that_uses_the_variable_is_held_too(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.GUIDE)
        await _set_template(message, "{환자명}님 안내 {링크} · 다음 예약은 {예약링크}")

        assert await gate_hold_reason(message) is GuideMessageHold.BOOKING_URL_MISSING

    async def test_a_run_out_message_that_does_not_use_it_is_not_held(self) -> None:
        """반대쪽도 재 둔다 — 회차로 쟀으면 이 문자가 **까닭 없이 붙들린다.**"""
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)
        await _set_template(message, "{환자명}님, 약이 {D}일 뒤 떨어집니다. 의원으로 전화 주세요.")

        assert await gate_hold_reason(message) is None

    async def test_dispatch_actually_sends_that_one(self) -> None:
        message = await make_due_message(kind=GuideMessageKind.RUN_OUT)
        await _set_template(message, "{환자명}님, 약이 {D}일 뒤 떨어집니다. 의원으로 전화 주세요.")

        result = await dispatch_message(message.guide_message_id, MockSmsSender())

        assert result is not None
        assert result.status is GuideMessageStatus.SENT
