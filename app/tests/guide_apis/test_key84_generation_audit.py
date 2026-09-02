"""안내 생성과 감사 이력이 한 사건으로 남는지 검증한다 — KEY-84."""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from aerich.utils import decompress_dict

from app.dependencies.staff_auth import StaffActor
from app.models.visits import GuideDocument, GuideEvent, GuideEventType, GuideSection, GuideSectionKey
from app.services.guides import GuideService
from app.tests.guide_apis.test_guide_generate import (
    BASE,
    GenerateGuideTestCase,
    attach_confirmed_ocr,
    make_clinic,
    make_staff,
    make_visit,
)


class TestGeneratedAuditEvent(GenerateGuideTestCase):
    async def test_success_leaves_exactly_one_generated_event_with_actor(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "key84staff", ["staff"])
        visit = await make_visit(clinic, "SYN-KEY84-SUCCESS")
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            response = await client.post(
                f"{BASE}/{visit.visit_id}/guide/generate",
                headers=await self.sign_in(staff),
            )

        assert response.status_code == 201
        guide = await GuideDocument.get(visit_id=visit.visit_id)
        events = await GuideEvent.filter(guide_document=guide).all()
        assert len(events) == 1
        assert events[0].event_type is GuideEventType.GENERATED
        assert events[0].actor_id == staff.staff_id
        assert events[0].created_at is not None
        assert events[0].section_key is None
        assert events[0].reason is None

    async def test_duplicate_failure_does_not_add_an_event(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "key84duplicate", ["staff"])
        visit = await make_visit(clinic, "SYN-KEY84-DUPLICATE")
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            headers = await self.sign_in(staff)
            first = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=headers)
            second = await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=headers)

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["code"] == "GUIDE_ALREADY_EXISTS"
        assert await GuideEvent.filter(event_type=GuideEventType.GENERATED).count() == 1

    async def test_unconfirmed_ocr_failure_leaves_no_guide_or_audit(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "key84blocked", ["staff"])
        visit = await make_visit(clinic, "SYN-KEY84-BLOCKED")

        async with self.client() as client:
            response = await client.post(
                f"{BASE}/{visit.visit_id}/guide/generate",
                headers=await self.sign_in(staff),
            )

        assert response.status_code == 422
        assert response.json()["code"] == "OCR_NOT_CONFIRMED"
        assert not await GuideDocument.filter(visit_id=visit.visit_id).exists()
        assert await GuideEvent.all().count() == 0

    async def test_audit_write_failure_rolls_back_guide_and_all_sections(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "key84rollback", ["staff"])
        visit = await make_visit(clinic, "SYN-KEY84-ROLLBACK")
        await attach_confirmed_ocr(visit, staff.staff_id)
        actor = StaffActor(
            user_id=staff.staff_id,
            hospital_id=staff.hospital_id,
            roles=frozenset(staff.roles),
        )

        with patch.object(
            GuideEvent,
            "create",
            new=AsyncMock(side_effect=RuntimeError("synthetic audit write failure")),
        ):
            with pytest.raises(RuntimeError, match="synthetic audit write failure"):
                await GuideService().generate(actor, visit.visit_id)

        assert not await GuideDocument.filter(visit_id=visit.visit_id).exists()
        assert await GuideSection.all().count() == 0
        assert await GuideEvent.all().count() == 0

    async def test_generated_edit_and_approval_events_keep_their_order(self) -> None:
        clinic = await make_clinic()
        staff = await make_staff(clinic, "key84orderstaff", ["staff"])
        doctor = await make_staff(clinic, "key84orderdoctor", ["doctor"])
        visit = await make_visit(clinic, "SYN-KEY84-ORDER")
        await attach_confirmed_ocr(visit, staff.staff_id)

        async with self.client() as client:
            generated = await client.post(
                f"{BASE}/{visit.visit_id}/guide/generate",
                headers=await self.sign_in(staff),
            )
            doctor_headers = await self.sign_in(doctor)
            edited = await client.patch(
                f"{BASE}/{visit.visit_id}/guide/sections/{GuideSectionKey.MEDICATION}",
                headers=doctor_headers,
                json={"body": "합성 환자용으로 검토한 복약 안내"},
            )
            # **승인 앞에 「의사에게 넘김」이 한 단계 있다** (KEY-234, 와이어프레임
            # D1-5). 전에는 스탭 확인 중인 글을 곧장 승인할 수 있었는데, 그러면
            # 「누가 언제 의사에게 넘겼는가」가 어디에도 안 남는다. 이 검사가
            # 재는 것은 **이벤트가 일어난 차례**지 단계 수가 아니므로, 늘어난
            # 단계를 지나서 같은 것을 잰다.
            submitted = await client.post(
                f"{BASE}/{visit.visit_id}/guide/submit",
                headers=await self.sign_in(staff),
            )
            approved = await client.post(
                f"{BASE}/{visit.visit_id}/guide/approve",
                headers=doctor_headers,
            )

        assert [
            generated.status_code,
            edited.status_code,
            submitted.status_code,
            approved.status_code,
        ] == [201, 200, 200, 200]
        events = await GuideEvent.filter(guide_document__visit_id=visit.visit_id).order_by(
            "created_at", "guide_event_id"
        )
        assert [event.event_type for event in events] == [
            GuideEventType.GENERATED,
            GuideEventType.EDITED,
            GuideEventType.SUBMITTED,
            GuideEventType.APPROVED,
        ]
        assert [event.created_at for event in events] == sorted(event.created_at for event in events)


def _load_key84_migration():
    migration_dir = Path(__file__).parents[2] / "core" / "db" / "migrations" / "models"
    paths = list(migration_dir.glob("*_key84_guide_generated_event.py"))
    assert len(paths) == 1
    spec = importlib.util.spec_from_file_location("key84_guide_generated_event", paths[0])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_key84_migration_widens_and_restores_event_type_contract() -> None:
    migration = _load_key84_migration()

    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)
    state = decompress_dict(migration.MODELS_STATE)
    event_type = next(field for field in state["models.GuideEvent"]["data_fields"] if field["name"] == "event_type")

    assert "VARCHAR(9)" in upgrade_sql
    assert "GENERATED: GENERATED" in upgrade_sql
    assert "VARCHAR(8)" in downgrade_sql
    assert "GENERATED: GENERATED" not in downgrade_sql
    assert event_type["constraints"]["max_length"] == 9
    assert "GENERATED: GENERATED" in event_type["description"]
