"""같은 답을 다시 보내면 성공이다 — KEY-335.

예전에는 두 번째 저장이 무조건 `409 CHECKIN_ALREADY_ANSWERED` 였다. 그런데
**저장은 이미 성공한 뒤**라, 두 번 누르거나 응답이 유실돼 다시 시도한 환자는
**된 일을 실패로 본다.** D+7 화면은 환자가 한 번 열고 마는 자리여서, 거기서
오류를 보면 그대로 닫는다.

멱등의 뜻대로 가른다.

    같은 답이면  →  그때 그 줄을 그대로 돌려준다 (201)
    다른 답이면  →  막는다 (409). 먼저 저장된 값은 안 바뀐다

환자 피드백(`patient_feedback.py::_same_or_conflict`)이 같은 모양이다.
"""

from app.models.visits import CheckIn
from app.tests.patient_links.test_key151_checkins import (
    TOKEN,
    CheckInTestCase,
    make_linked_guide,
)
from app.tests.patient_links.test_patient_links import make_hospital, make_staff

SAME = {"medication": "taking", "pain": {"had": True, "score": 4, "types": ["menstrual", "chronic_pelvic"]}}


class TestTheSameAnswerIsAccepted(CheckInTestCase):
    async def test_sending_the_same_answer_twice_returns_the_stored_row(self) -> None:
        await make_linked_guide(await make_hospital("KEY-335 같은 답"))

        async with self.client() as client:
            first = await client.post(f"/api/v1/checkins/{TOKEN}", json=SAME)
            second = await client.post(f"/api/v1/checkins/{TOKEN}", json=SAME)

        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert second.json()["check_in_id"] == first.json()["check_in_id"], "새 줄을 만들었다"
        assert second.json() == first.json()
        assert await CheckIn.all().count() == 1

    async def test_the_order_of_pain_types_does_not_make_it_a_different_answer(self) -> None:
        """🚩 화면이 **체크박스**라 고른 차례가 그대로 실려 온다.

        순서까지 따지면 **같은 답인데 conflict** 가 난다 — 고치려던 문제를 다시
        만드는 셈이다.
        """
        await make_linked_guide(await make_hospital("KEY-335 순서"))
        flipped = {
            "medication": "taking",
            "pain": {"had": True, "score": 4, "types": ["chronic_pelvic", "menstrual"]},
        }

        async with self.client() as client:
            first = await client.post(f"/api/v1/checkins/{TOKEN}", json=SAME)
            second = await client.post(f"/api/v1/checkins/{TOKEN}", json=flipped)

        assert second.status_code == 201, second.text
        assert second.json()["check_in_id"] == first.json()["check_in_id"]
        assert await CheckIn.all().count() == 1

    async def test_an_answer_without_pain_is_not_the_same_as_no_pain(self) -> None:
        """**안 물어본 것**과 **없다고 답한 것**은 다르다.

        `pain: null` 은 통증 칸 자체가 없는 요청이고, `had: false` 는 환자가
        「없다」고 고른 것이다. 둘을 같게 보면 다른 답이 조용히 통과한다.
        """
        await make_linked_guide(await make_hospital("KEY-335 통증 없음"))

        async with self.client() as client:
            first = await client.post(f"/api/v1/checkins/{TOKEN}", json={"medication": "taking", "pain": None})
            second = await client.post(
                f"/api/v1/checkins/{TOKEN}",
                json={"medication": "taking", "pain": {"had": False, "score": None, "types": []}},
            )

        assert first.status_code == 201
        assert second.status_code == 409, second.text
        assert second.json()["code"] == "CHECKIN_ALREADY_ANSWERED"


class TestADifferentAnswerIsStillBlocked(CheckInTestCase):
    async def test_a_different_answer_is_blocked_and_the_first_one_survives(self) -> None:
        """**조용히 덮지 않는다.** 어느 쪽이 환자의 뜻인지 서버가 모른다."""
        await make_linked_guide(await make_hospital("KEY-335 다른 답"))
        changed = {"medication": "stopped_side_effect", "pain": {"had": True, "score": 9, "types": ["menstrual"]}}

        async with self.client() as client:
            first = await client.post(f"/api/v1/checkins/{TOKEN}", json=SAME)
            second = await client.post(f"/api/v1/checkins/{TOKEN}", json=changed)
            form = await client.get(f"/api/v1/checkins/{TOKEN}")

        assert second.status_code == 409
        assert second.json()["code"] == "CHECKIN_ALREADY_ANSWERED"
        assert form.json()["answered"] is True

        stored = await CheckIn.all().first()
        assert stored is not None
        assert stored.check_in_id == first.json()["check_in_id"]
        assert stored.medication == "taking", "먼저 저장한 답이 덮였다"
        assert stored.pain_score == 4, "먼저 저장한 답이 덮였다"
        assert await CheckIn.all().count() == 1

    async def test_only_the_pain_score_changing_is_also_a_different_answer(self) -> None:
        """한 칸만 달라도 다른 답이다 — 넷을 다 본다."""
        await make_linked_guide(await make_hospital("KEY-335 점수만"))
        louder = {"medication": "taking", "pain": {"had": True, "score": 9, "types": ["menstrual", "chronic_pelvic"]}}

        async with self.client() as client:
            await client.post(f"/api/v1/checkins/{TOKEN}", json=SAME)
            second = await client.post(f"/api/v1/checkins/{TOKEN}", json=louder)

        assert second.status_code == 409, second.text


class TestTheHospitalSeesTheFirstAnswer(CheckInTestCase):
    async def test_the_hospital_view_shows_the_stored_answer_after_a_retry(self) -> None:
        """병원 화면이 보는 값이 두 경우 모두 **첫 저장값**이어야 한다."""
        hospital = await make_hospital("KEY-335 병원 조회")
        guide = await make_linked_guide(hospital)
        staff = await make_staff(hospital, "key335-staff", ["staff"])

        async with self.client() as client:
            await client.post(f"/api/v1/checkins/{TOKEN}", json=SAME)
            await client.post(f"/api/v1/checkins/{TOKEN}", json=SAME)
            seen = await client.get(
                f"/api/v1/visits/{guide.visit_id}/checkin",
                headers=await self.headers(staff),
            )

        assert seen.status_code == 200, seen.text
        assert seen.json()["medication"] == "taking"
        assert seen.json()["pain"]["score"] == 4
        assert sorted(seen.json()["pain"]["types"]) == ["chronic_pelvic", "menstrual"]
