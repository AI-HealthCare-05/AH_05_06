"""절의 **보이는 차례**를 사람이 정한다 — KEY-317.

차례가 지금까지 세 곳에서 따로 정해졌다.

    병원 화면 탭        서버가 준 `sections` 차례 (계약 표)
    환자 응답 배열      `guide_section_id` — **넣은 차례**
    환자 화면 탭        화면에 박힌 상수

셋이 같아 보인 것은 생성 경로가 계약 순서대로 넣기 때문이지 규칙이 아니었다
(KEY-161 이 병원 쪽에서 한 번 걷어 낸 그 「우연」이 환자 쪽에 남아 있었다).
사람이 차례를 바꿀 수 있게 되는 순간 셋은 갈린다. 이제 **저장된 한 값**에서
읽는다.

여기서 재는 것은 인수조건 전부다. 안전 절 정책은
`app/services/guide_section_order.py` 한 곳이 정하고, 이 파일은 그 정책이
**요청으로도 못 뚫린다**는 것을 잰다 — 화면만 막으면 요청을 직접 보내는
것으로 넘어간다.
"""

from datetime import UTC, datetime
from typing import Any

from app.models.visits import (
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
)
from app.services import guide_section_order
from app.tests.guide_apis.test_guide_approval import (
    BASE,
    GuideTestCase,
    make_clinic,
    make_guide,
    make_staff,
)

ORDER_URL = "/guide/sections/order"

#: 계약이 정한 차례 — 「복약지도 · 주의사항 · 응급 · 생활지도 · 문자 설정」.
CONTRACT = [key.value for key in GuideSectionKey]


async def fill_sections(guide: GuideDocument) -> None:
    """`make_guide` 가 만드는 셋에 나머지 둘을 더해 **다섯 갈래를 채운다.**"""
    for key in (GuideSectionKey.LIFE, GuideSectionKey.MESSAGES):
        await GuideSection.create(guide_document=guide, section_key=key, generated_body=f"합성 {key.value} 본문")


class SectionOrderTestCase(GuideTestCase):
    async def whole_guide(self, status: GuideStatus = GuideStatus.STAFF_REVIEW) -> tuple[Any, GuideDocument]:
        clinic = await make_clinic()
        guide = await make_guide(clinic, status)
        await fill_sections(guide)
        return clinic, guide

    async def put(self, guide: GuideDocument, order: list[str], staff: Any) -> Any:
        async with self.client() as client:
            return await client.put(
                f"{BASE}/{guide.visit_id}{ORDER_URL}",
                headers=await self.sign_in(staff),
                json={"order": order},
            )

    async def read(self, guide: GuideDocument, staff: Any) -> list[str]:
        async with self.client() as client:
            response = await client.get(f"{BASE}/{guide.visit_id}/guide", headers=await self.sign_in(staff))
        assert response.status_code == 200, response.text
        return [section["key"] for section in response.json()["sections"]]

    async def stored_order(self, guide: GuideDocument) -> list[str]:
        rows = await GuideSection.filter(guide_document=guide)
        return [key.value for key in guide_section_order.current_order(rows)]


class TestTheDefaultOrderComesFromTheContract(SectionOrderTestCase):
    async def test_every_key_gets_its_own_slot(self) -> None:
        """**이름을 적어 두지 않는다.** 여섯째 갈래가 생기는 날 이 검사가 먼저 운다.

        절을 만드는 자리가 다섯 군데라, 새 갈래에서 차례 한 줄을 빠뜨리면 그
        절만 맨 앞으로 튀어나온다 — 응급 문장이 복약지도 앞에 설 수 있다는 뜻이다.
        """
        _, guide = await self.whole_guide()

        rows = await GuideSection.filter(guide_document=guide)

        assert len(rows) == len(GuideSectionKey), "다섯 갈래를 다 안 만들었다 — 검사가 헛돈다"
        assert await self.stored_order(guide) == CONTRACT
        assert sorted(row.display_order for row in rows) == list(range(len(GuideSectionKey))), (
            "자리가 겹치거나 비었다 — 차례가 매번 달라진다"
        )


class TestGeneralSectionsCanSwap(SectionOrderTestCase):
    async def test_the_saved_order_survives_a_refresh(self) -> None:
        """인수조건 — 저장 후 새로고침해도 순서가 유지된다."""
        clinic, guide = await self.whole_guide()
        staff = await make_staff(clinic, "staff01", ["staff"])
        wanted = ["life", "caution", "emergency", "medication", "messages"]

        saved = await self.put(guide, wanted, staff)

        assert saved.status_code == 200, saved.text
        assert [section["key"] for section in saved.json()["sections"]] == wanted
        assert await self.read(guide, staff) == wanted, "새로고침하니 차례가 돌아갔다"
        assert await self.stored_order(guide) == wanted


class TestSafetySectionsCannotMove(SectionOrderTestCase):
    """🚨 **화면만 막으면 요청을 직접 보내는 것으로 넘어간다.**

    응급 안내가 생활관리 뒤로 가면 환자는 그것을 못 보고 창을 닫는다. 넘겨도
    되는 문장이 아니다.
    """

    async def test_pushing_the_caution_down_is_refused(self) -> None:
        clinic, guide = await self.whole_guide()
        staff = await make_staff(clinic, "staff01", ["staff"])

        refused = await self.put(guide, ["medication", "life", "caution", "emergency", "messages"], staff)

        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "SECTION_ORDER_INVALID"
        assert await self.stored_order(guide) == CONTRACT, "막혔다면서 저장은 됐다"

    async def test_tearing_the_emergency_off_the_caution_is_refused(self) -> None:
        """응급은 **주의사항 바로 뒤**다 — 둘 다 안 움직이니 저절로 붙어 있다."""
        clinic, guide = await self.whole_guide()
        staff = await make_staff(clinic, "staff01", ["staff"])

        refused = await self.put(guide, ["medication", "caution", "life", "emergency", "messages"], staff)

        assert refused.status_code == 422, refused.text
        assert await self.stored_order(guide) == CONTRACT

    async def test_a_document_missing_a_section_is_judged_by_its_own_slots(self) -> None:
        """절이 빠진 옛 안내문도 같은 규칙으로 잰다.

        계약 표의 번호로 재면 `life`·`messages` 가 없는 문서에서 번호가 밀려
        **멀쩡한 차례가 거절당한다.** 그 문서에서 지금 앉아 있는 자리로 잰다.
        """
        clinic = await make_clinic()
        guide = await make_guide(clinic, GuideStatus.STAFF_REVIEW)  # 셋뿐이다
        staff = await make_staff(clinic, "staff01", ["staff"])

        assert await self.stored_order(guide) == ["medication", "caution", "emergency"]
        moved = await self.put(guide, ["medication", "caution", "emergency"], staff)

        assert moved.status_code == 200, moved.text


class TestTheListMustBeWholeAndOnce(SectionOrderTestCase):
    """인수조건 — 빈 섹션·동일 순서·동시 수정에서도 중복 순번이 안 생긴다."""

    async def test_leaving_one_out_is_refused(self) -> None:
        clinic, guide = await self.whole_guide()
        staff = await make_staff(clinic, "staff01", ["staff"])

        refused = await self.put(guide, ["medication", "caution", "emergency", "life"], staff)

        assert refused.status_code == 422, refused.text
        assert await self.stored_order(guide) == CONTRACT

    async def test_sending_one_twice_is_refused(self) -> None:
        """그대로 저장하면 **순번이 겹치고** 그 뒤로 차례가 매번 달라진다."""
        clinic, guide = await self.whole_guide()
        staff = await make_staff(clinic, "staff01", ["staff"])

        refused = await self.put(guide, ["medication", "medication", "caution", "emergency", "life"], staff)

        assert refused.status_code == 422, refused.text
        assert await self.stored_order(guide) == CONTRACT

    async def test_a_name_the_server_does_not_know_is_refused(self) -> None:
        clinic, guide = await self.whole_guide()
        staff = await make_staff(clinic, "staff01", ["staff"])

        refused = await self.put(guide, ["medication", "caution", "emergency", "life", "nosuch"], staff)

        assert refused.status_code == 422, refused.text


class TestApprovalLocksTheOrder(SectionOrderTestCase):
    """인수조건 — 승인 후 직접 순서 변경이 차단된다.

    **차례도 환자가 보는 것**이다. 승인 뒤에 조용히 옮기면 원장님이 승인한
    화면과 환자가 받는 화면이 달라진다.
    """

    async def test_an_approved_guide_refuses(self) -> None:
        clinic, guide = await self.whole_guide(GuideStatus.SCHEDULED_TO_SEND)
        doctor = await make_staff(clinic, "doctor01", ["doctor"])

        refused = await self.put(guide, ["life", "caution", "emergency", "medication", "messages"], doctor)

        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "GUIDE_NOT_PENDING"
        assert await self.stored_order(guide) == CONTRACT

    async def test_a_staff_cannot_touch_what_the_doctor_is_reading(self) -> None:
        """승인 요청 중에는 의사만 — `edit_section` 과 같은 판단이다."""
        clinic, guide = await self.whole_guide(GuideStatus.APPROVAL_PENDING)
        staff = await make_staff(clinic, "staff01", ["staff"])
        doctor = await make_staff(clinic, "doctor01", ["doctor"])
        wanted = ["life", "caution", "emergency", "medication", "messages"]

        refused = await self.put(guide, wanted, staff)
        allowed = await self.put(guide, wanted, doctor)

        assert refused.status_code == 403, refused.text
        assert allowed.status_code == 200, allowed.text


class TestTheHospitalFenceHolds(SectionOrderTestCase):
    async def test_another_clinics_guide_is_not_found(self) -> None:
        """다른 병원 것은 **403 이 아니라 404** 다 — 있다는 사실도 알리지 않는다."""
        _, guide = await self.whole_guide()
        neighbour = await make_clinic("옆동네의원")
        outsider = await make_staff(neighbour, "staff02", ["staff"])

        refused = await self.put(guide, ["life", "caution", "emergency", "medication", "messages"], outsider)

        assert refused.status_code == 404, refused.text
        assert await self.stored_order(guide) == CONTRACT


class TestTheChangeIsAudited(SectionOrderTestCase):
    """인수조건 — 변경자·변경 시각·이전 순서·이후 순서가 남는다."""

    async def test_before_and_after_are_both_written(self) -> None:
        clinic, guide = await self.whole_guide()
        staff = await make_staff(clinic, "staff01", ["staff"])
        wanted = ["life", "caution", "emergency", "medication", "messages"]

        await self.put(guide, wanted, staff)

        event = await GuideEvent.filter(guide_document=guide, event_type=GuideEventType.SECTION_REORDERED).first()
        assert event is not None, "차례를 바꿨는데 기록이 없다"
        assert event.actor_id == staff.staff_id
        assert event.created_at is not None
        assert event.order_before == ",".join(CONTRACT)
        assert event.order_after == ",".join(wanted)
        #: 글은 안 담는다 — 감사 기록에 본문·환자 정보가 새로 실리면 안 된다.
        assert "합성" not in f"{event.order_before} {event.order_after}"

    async def test_saving_the_same_order_changes_nothing(self) -> None:
        """새로고침 뒤 다시 누른 것이다. 판을 올리고 기록을 쌓으면
        「누가 무엇을 옮겼나」가 **안 옮긴 줄로** 흐려진다."""
        clinic, guide = await self.whole_guide()
        staff = await make_staff(clinic, "staff01", ["staff"])
        before = (await GuideDocument.get(guide_document_id=guide.guide_document_id)).version

        same = await self.put(guide, CONTRACT, staff)

        assert same.status_code == 200, same.text
        assert (await GuideDocument.get(guide_document_id=guide.guide_document_id)).version == before
        assert await GuideEvent.filter(guide_document=guide, event_type=GuideEventType.SECTION_REORDERED).count() == 0


class TestEveryEventTypeHasAKoreanSummary:
    """감사 뷰어가 **모르는 갈래**를 만나면 영문 상수를 그대로 찍는다.

    관리자 화면에 `SECTION_REORDERED` 가 뜬다는 뜻이다. 이름을 적어 두는 대신
    **빠진 것이 있으면 운다**로 잰다 — 다음에 갈래가 하나 더 늘 때도 걸린다.
    """

    def test_no_guide_event_type_is_left_untranslated(self) -> None:
        from app.services.admin_audit import _SUMMARY, AuditSource

        missing = [event_type.value for event_type in GuideEventType if (AuditSource.GUIDE, event_type) not in _SUMMARY]

        assert not missing, f"감사 뷰어가 한국어로 못 옮기는 갈래: {missing}"


class TestTheHospitalAndThePatientSeeOneOrder(SectionOrderTestCase):
    """인수조건 — 병원 미리보기와 **실제 발급 링크의 환자 화면**이 같은 차례다.

    환자 종점은 `guide_section_id`, 곧 **넣은 차례**로 늘어놓고 있었다. 지금은
    생성 경로가 계약 순서대로 넣으니 결과가 같지만, 사람이 차례를 정하는
    순간 갈린다 — 원장님이 옮겨 놓고 승인한 차례와 환자가 받는 차례가 다르다.
    """

    async def test_the_patient_gets_what_the_doctor_arranged(self) -> None:
        from unittest.mock import patch as mock_patch

        from app.dependencies.patient_auth import require_patient_session
        from app.main import app as fastapi_app

        clinic, guide = await self.whole_guide()
        doctor = await make_staff(clinic, "doctor01", ["doctor"])
        wanted = ["life", "caution", "emergency", "medication", "messages"]

        arranged = await self.put(guide, wanted, doctor)
        assert arranged.status_code == 200, arranged.text
        hospital_side = [section["key"] for section in arranged.json()["sections"]]

        #: 링크는 **승인 완료**만 발급한다 — 승인 시각까지 있어야 한다.
        guide.status = GuideStatus.SCHEDULED_TO_SEND
        guide.approved_at = datetime(2026, 9, 11, 1, 0, tzinfo=UTC)
        await guide.save(update_fields=["status", "approved_at", "updated_at"])

        token = "syn-key317-token"
        fastapi_app.dependency_overrides[require_patient_session] = lambda: None
        try:
            with mock_patch("app.services.patient_links.secrets.token_urlsafe", return_value=token):
                async with self.client() as client:
                    issued = await client.post(
                        f"{BASE}/{guide.visit_id}/guide/link", headers=await self.sign_in(doctor)
                    )
                    assert issued.status_code == 201, issued.text
                    seen = await client.get(f"/api/v1/guides/{token}")
        finally:
            fastapi_app.dependency_overrides.pop(require_patient_session, None)

        assert seen.status_code == 200, seen.text
        patient_side = [section["key"] for section in seen.json()["sections"]]

        assert patient_side == hospital_side, (
            f"원장님이 늘어놓은 차례와 환자가 받는 차례가 다르다 — 병원 {hospital_side} · 환자 {patient_side}"
        )
        assert patient_side == wanted
