"""선택 이탈·역순·최종 저장·병원 확인의 실제 DB/API 계약."""

import asyncio
from datetime import timedelta

from tortoise.timezone import now

from app.dependencies.patient_auth import require_patient_session
from app.main import app
from app.models.visits import CheckIn, CheckInSignal, CheckInSignalAcknowledgement, CheckInSignalState
from app.tests.messages.test_key306_message_resend import MessageResendTestCase
from app.tests.patient_links.test_key151_checkins import TOKEN, CheckInTestCase, make_linked_guide
from app.tests.patient_links.test_patient_links import make_hospital, make_staff
from app.tests.patient_links.test_patient_otp import LINK_TOKEN, make_link
from app.tests.patient_links.test_patient_session import PatientSessionTestCase


def stamp(answer="stopped_side_effect", sequence=1, client="device-a"):
    return dict(answer_key=answer, client_id=client, client_session_id="tab-a", client_sequence=sequence)


class TestKey238Signals(CheckInTestCase):
    async def seed(self):
        hospital = await make_hospital("KEY-238 합성의원")
        guide = await make_linked_guide(hospital)
        staff = await make_staff(hospital, "key238-staff", ["staff"])
        return hospital, guide, staff

    async def test_selection_is_persisted_without_final_save_and_ack_is_separate(self):
        _, guide, staff = await self.seed()
        async with self.client() as client:
            response = await client.post(f"/api/v1/checkins/{TOKEN}/signals", json=stamp())
            assert response.status_code == 201, response.text
            assert response.json()["notify"] is True
            assert await CheckIn.all().count() == 0
            headers = await self.headers(staff)
            path = f"/api/v1/visits/{guide.visit_id}/checkin/signals"
            state = (await client.get(path, headers=headers)).json()[0]
            assert state["status"] == "OPEN"
            ack = await client.post(
                path + f"/{state['state_id']}/acknowledge",
                headers=headers,
                json={"signal_id": state["signal_id"], "updated_at": state["updated_at"]},
            )
            assert ack.status_code == 200, ack.text
            assert ack.json()["status"] == "ACKNOWLEDGED"
            assert ack.json()["acknowledged_by"] == staff.staff_id
            assert await CheckInSignal.all().count() == 1
            assert await CheckInSignalAcknowledgement.all().count() == 1
            assert TOKEN not in ack.text

    async def test_order_dedup_and_cross_device(self):
        await self.seed()
        async with self.client() as client:
            path = f"/api/v1/checkins/{TOKEN}/signals"
            for body in (stamp("taking", 3), stamp("stopped_side_effect", 2)):
                response = await client.post(path, json=body)
                assert response.status_code == 201, response.text
            assert response.json()["current"] is False
            assert response.json()["current_answer_key"] == "taking"
            other = await client.post(path, json=stamp("stopped_improved", 1, "device-b"))
            assert other.json()["current"] is True
            await client.post(path, json=stamp("stopped_improved", 1, "device-b"))
            assert await CheckInSignal.all().count() == 3
            conflict = await client.post(path, json=stamp("taking", 1, "device-b"))
            assert conflict.status_code == 409

    async def test_final_save_corrects_signal_and_late_signal_cannot_reverse_it(self):
        await self.seed()
        async with self.client() as client:
            path = f"/api/v1/checkins/{TOKEN}"
            await client.post(path + "/signals", json=stamp())
            payload = dict(
                medication="taking",
                note="  합성 메모  ",
                client_id="device-a",
                client_session_id="tab-a",
                client_sequence=2,
            )
            saved = await client.post(path, json=payload)
            assert saved.status_code == 201, saved.text
            assert saved.json()["note"] == "합성 메모"
            assert saved.json()["signal_answer_key"] == "taking"
            repeated = await client.post(path, json=payload)
            assert repeated.json()["check_in_id"] == saved.json()["check_in_id"]
            late = await client.post(path + "/signals", json=stamp("stopped_improved", 5))
            assert late.json()["current_answer_key"] == "taking"
            assert await CheckInSignal.all().count() == 2
            assert await CheckIn.all().count() == 1

    async def test_unauthorized_other_hospital_and_admin_cannot_read_or_ack(self):
        _, guide, _ = await self.seed()
        other = await make_hospital("KEY-238 타원")
        outsider = await make_staff(other, "key238-outsider", ["staff"])
        admin = await make_staff(other, "key238-admin", ["admin"])
        async with self.client() as client:
            await client.post(f"/api/v1/checkins/{TOKEN}/signals", json=stamp())
            state = await CheckInSignalState.get()
            path = f"/api/v1/visits/{guide.visit_id}/checkin/signals"
            for actor, status in ((outsider, 404), (admin, 403)):
                headers = await self.headers(actor)
                assert (await client.get(path, headers=headers)).status_code == status
                ack = await client.post(
                    path + f"/{state.pk}/acknowledge",
                    headers=headers,
                    json={"signal_id": state.signal_id, "updated_at": state.updated_at.isoformat()},
                )
                assert ack.status_code == status
            assert await CheckInSignalAcknowledgement.all().count() == 0

    async def test_stale_ack_does_not_ack_new_selection(self):
        _, guide, staff = await self.seed()
        async with self.client() as client:
            path = f"/api/v1/checkins/{TOKEN}/signals"
            await client.post(path, json=stamp())
            headers = await self.headers(staff)
            hospital_path = f"/api/v1/visits/{guide.visit_id}/checkin/signals"
            old = (await client.get(hospital_path, headers=headers)).json()[0]
            await client.post(path, json=stamp("stopped_improved", 2))
            ack = await client.post(
                hospital_path + f"/{old['state_id']}/acknowledge",
                headers=headers,
                json={"signal_id": old["signal_id"], "updated_at": old["updated_at"]},
            )
            assert ack.status_code == 409

    async def test_repeated_duplicates_have_one_append_only_event(self):
        await self.seed()
        async with self.client() as client:
            results = [await client.post(f"/api/v1/checkins/{TOKEN}/signals", json=stamp()) for _ in range(2)]
        assert [response.status_code for response in results] == [201, 201]
        assert await CheckInSignal.all().count() == 1

    async def test_metadata_note_validation_and_empty_note(self):
        await self.seed()
        async with self.client() as client:
            path = f"/api/v1/checkins/{TOKEN}"
            form = (await client.get(path)).json()
            assert form["answers"]["stopped_side_effect"]["notify"] is True
            assert form["answers"]["stopped_improved"]["ask"] is True
            assert form["answers"]["uncomfortable"]["notify"] is False
            assert (await client.post(path, json=dict(medication="taking", note="x" * 1001))).status_code == 422
            assert (await client.post(path + "/signals", json={**stamp(), "note": "not allowed"})).status_code == 422
            saved = await client.post(path, json=dict(medication="taking", note="  "))
            assert saved.status_code == 201
            assert saved.json()["note"] is None

    async def test_signal_reaches_patient_list_history_and_note_only_after_save(self):
        _, guide, staff = await self.seed()
        patient_id = (await guide.visit).patient_id
        async with self.client() as client:
            await client.post(f"/api/v1/checkins/{TOKEN}/signals", json=stamp())
            headers = await self.headers(staff)
            listing = await client.get("/api/v1/patients", headers=headers)
            assert listing.status_code == 200, listing.text
            row = next(row for row in listing.json()["items"] if row["patient_id"] == patient_id)
            assert "CHECKIN_SIGNAL" in row["flags"]
            history = await client.get(f"/api/v1/patients/{patient_id}/history", headers=headers)
            assert history.status_code == 200, history.text
            block = history.json()["visits"][0]
            assert block["checkin_signals"][0]["status"] == "OPEN"
            assert block["checkin_note"] is None
            await client.post(f"/api/v1/checkins/{TOKEN}", json={"medication": "taking", "note": "합성 메모"})
            history = (await client.get(f"/api/v1/patients/{patient_id}/history", headers=headers)).json()
            assert history["visits"][0]["checkin_note"] == "합성 메모"
            assert history["visits"][0]["checkin_signals"][0]["status"] == "NOT_REQUIRED"


class TestKey238Concurrency(MessageResendTestCase):
    """독립 connection의 commit으로 경쟁시킨다. 외부 rollback TestCase로는 재현할 수 없다."""

    def setUp(self):
        super().setUp()
        app.dependency_overrides[require_patient_session] = lambda: None

    async def test_concurrent_duplicate_signals(self):
        await make_linked_guide(await make_hospital("KEY-238 동시 신호"))
        async with self.client() as client:
            results = await asyncio.gather(
                *[client.post(f"/api/v1/checkins/{TOKEN}/signals", json=stamp()) for _ in range(2)]
            )
        assert [response.status_code for response in results] == [201, 201]
        assert await CheckInSignal.all().count() == 1

    async def test_concurrent_different_final_answers_preserve_winner(self):
        await make_linked_guide(await make_hospital("KEY-238 동시 최종 답"))
        async with self.client() as client:
            results = await asyncio.gather(
                *[
                    client.post(f"/api/v1/checkins/{TOKEN}", json={"medication": answer})
                    for answer in ("taking", "missing")
                ]
            )
        assert sorted(response.status_code for response in results) == [201, 409]
        saved = await CheckIn.get()
        winner = next(response for response in results if response.status_code == 201)
        assert saved.medication == winner.json()["medication"]
        assert (await CheckInSignalState.get()).answer_key == saved.medication


class TestKey238SessionSecurity(PatientSessionTestCase):
    async def test_signal_requires_session_and_expiry_blocks_new_events(self):
        await make_link()
        async with self.client() as browser:
            path = f"/api/v1/checkins/{LINK_TOKEN}/signals"
            assert (await browser.post(path, json=stamp())).status_code == 401
            await self.authenticate(browser)
            assert (await browser.post(path, json=stamp())).status_code == 201
            for key in list(self.redis.values):
                if key.startswith("patient_session:"):
                    await self.redis.delete(key)
            assert (await browser.post(path, json=stamp(sequence=2))).status_code == 401
            assert await CheckInSignal.all().count() == 1

    async def test_expired_link_blocks_signal_even_with_authenticated_session(self):
        link = await make_link()
        async with self.client() as browser:
            await self.authenticate(browser)
            link.expires_at = now() - timedelta(seconds=1)
            await link.save(update_fields=["expires_at"])
            response = await browser.post(f"/api/v1/checkins/{LINK_TOKEN}/signals", json=stamp())
            assert response.status_code in (401, 410), response.text
            assert await CheckInSignal.all().count() == 0

    async def test_logout_blocks_signal(self):
        await make_link()
        async with self.client() as browser:
            await self.authenticate(browser)
            await browser.delete("/api/v1/patient-auth/otp/session")
            assert (await browser.post(f"/api/v1/checkins/{LINK_TOKEN}/signals", json=stamp())).status_code == 401
            assert await CheckInSignal.all().count() == 0

    async def test_rotated_link_blocks_old_signal(self):
        link = await make_link()
        async with self.client() as browser:
            await self.authenticate(browser)
            link.token_digest = "a" * 64
            await link.save(update_fields=["token_digest"])
            response = await browser.post(f"/api/v1/checkins/{LINK_TOKEN}/signals", json=stamp())
            assert response.status_code in (401, 404, 410), response.text
            assert await CheckInSignal.all().count() == 0
