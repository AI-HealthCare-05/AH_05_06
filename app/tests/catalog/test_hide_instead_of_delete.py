"""**지우지 않는다. 감춘다.** — KEY-255

의료 데이터라 삭제가 금지된다(2026-09-02 팀 결정). 여기서는 이유가 하나 더
있다: 지난 진료기록이 이 세트를 **이름 문자열로** 가리키므로, 행이 사라지거나
이름이 바뀌면 그 진료들의 안내문 문구가 조용히 떨어진다.

**핵심 불변식: 감춤은 「없다」가 아니라 「새로 못 고른다」다.** 감춘 세트라도
이미 그것으로 나간 진료기록에서는 문구가 그대로 붙어야 한다. 이 파일이 그것을
지킨다.
"""

from app.models.catalog import CautionSectionKey, PrescriptionSet, SetStatus
from app.services.drug_caution import DrugCautionService
from app.tests.catalog.test_prescription_settings import PrescriptionSettingsTestCase
from app.tests.guide_apis.test_key165_drug_caution import make_approved_content


class HideInsteadOfDeleteTestCase(PrescriptionSettingsTestCase):
    async def test_hiding_keeps_the_row(self) -> None:
        """감춰도 행은 남는다 — 지난 진료기록이 이 이름을 가리킨다."""
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            answer = await client.post(
                f"/api/v1/prescription-sets/{row.prescription_set_id}/hide",
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 200, answer.text
        assert answer.json()["hidden"] is True
        await row.refresh_from_db()
        assert row.status is SetStatus.HIDDEN
        assert row.hidden_at is not None, "언제 감췄는지 안 남았다 — 되돌릴 근거가 없다"
        assert await PrescriptionSet.filter(prescription_set_id=row.prescription_set_id).exists()

    async def test_a_hidden_set_still_carries_its_wording(self) -> None:
        """**이것이 이 기능의 전부다.**

        감춘 세트라도 그 이름을 든 진료기록에는 승인 문구가 그대로 붙어야 한다.
        여기가 깨지면 감추는 순간 지난 환자들의 안내문이 범용 문장으로 바뀐다 —
        터지지 않고, 로그 한 줄만 남고, 화면은 아무 말도 안 한다.
        """
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])
        await make_approved_content(row.name, CautionSectionKey.CAUTION, "[합성 승인 주의]")

        async with self.client() as client:
            await client.post(
                f"/api/v1/prescription-sets/{row.prescription_set_id}/hide",
                headers=await self.sign_in(staff),
            )

        found = await DrugCautionService.get_approved_content(row.name, CautionSectionKey.CAUTION)
        assert found is not None, "감췄더니 승인 문구가 떨어졌다 — 지난 환자의 안내문이 바뀐다"
        assert found.body == "[합성 승인 주의]"

    async def test_the_list_still_shows_a_hidden_set(self) -> None:
        """**목록은 감춘 것도 다 준다.**

        거르면 되살릴 화면이 없어지고, 감춘 세트로 저장된 진료를 다시 열 때
        확인 항목이 통째로 사라진다(`ocr-groups.js` 가 이름으로 되찾는다).
        거르는 것은 **새로 고르는 칸** 하나뿐이다.
        """
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            headers = await self.sign_in(staff)
            await client.post(f"/api/v1/prescription-sets/{row.prescription_set_id}/hide", headers=headers)
            answer = await client.get("/api/v1/prescription-sets", headers=headers)

        assert answer.status_code == 200, answer.text
        mine = [s for s in answer.json() if s["prescription_set_id"] == row.prescription_set_id]
        assert mine, "감췄더니 목록에서 사라졌다 — 되살릴 길이 없다"
        assert mine[0]["hidden"] is True, "감춘 것을 감췄다고 말하지 않는다"

    async def test_unhiding_brings_it_back(self) -> None:
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            headers = await self.sign_in(staff)
            await client.post(f"/api/v1/prescription-sets/{row.prescription_set_id}/hide", headers=headers)
            answer = await client.post(f"/api/v1/prescription-sets/{row.prescription_set_id}/unhide", headers=headers)

        assert answer.status_code == 200, answer.text
        assert answer.json()["hidden"] is False
        await row.refresh_from_db()
        assert row.status is SetStatus.ACTIVE
        assert row.hidden_at is None, "되살렸는데 감춘 시각이 남았다"

    async def test_hiding_twice_is_the_same_as_once(self) -> None:
        """배포가 두 번 눌릴 수도 있고, 화면이 두 번 보낼 수도 있다."""
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            headers = await self.sign_in(staff)
            first = await client.post(f"/api/v1/prescription-sets/{row.prescription_set_id}/hide", headers=headers)
            await row.refresh_from_db()
            was = row.hidden_at
            second = await client.post(f"/api/v1/prescription-sets/{row.prescription_set_id}/hide", headers=headers)

        assert first.status_code == second.status_code == 200
        await row.refresh_from_db()
        assert row.hidden_at == was, "두 번째가 감춘 시각을 덮어썼다"


class CreateSetTestCase(PrescriptionSettingsTestCase):
    """**새로 만들기** — 이름은 여기서 한 번만 정한다."""

    async def post(self, staff, **body):
        async with self.client() as client:
            return await client.post(
                "/api/v1/prescription-sets",
                json={"name": "자궁내막증 · 비잔 (2026)", "disease": "ENDOMETRIOSIS", **body},
                headers=await self.sign_in(staff),
            )

    async def test_it_makes_one(self) -> None:
        staff = await self.make_staff(["staff"])

        answer = await self.post(staff)

        assert answer.status_code == 201, answer.text
        assert answer.json()["name"] == "자궁내막증 · 비잔 (2026)"
        assert answer.json()["hidden"] is False

    async def test_a_duplicate_name_is_refused(self) -> None:
        """같은 이름이 둘이면 **어느 세트로 풀릴지 모른다.**

        `filter(name=…).first()` 에 `ORDER BY` 가 없어서, 그 갈림이 곧 지난
        진료기록의 안내문 문구가 갈리는 것이다.
        """
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        answer = await self.post(staff, name=row.name)

        assert answer.status_code == 409, answer.text
        assert answer.json()["code"] == "PRESCRIPTION_SET_EXISTS"

    async def test_a_hidden_name_is_still_taken(self) -> None:
        """**감춘 이름도 못 쓴다.** 그 이름을 든 진료기록이 이미 있다."""
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])
        async with self.client() as client:
            await client.post(
                f"/api/v1/prescription-sets/{row.prescription_set_id}/hide",
                headers=await self.sign_in(staff),
            )

        answer = await self.post(staff, name=row.name)

        assert answer.status_code == 409, answer.text

    async def test_padding_does_not_sneak_a_twin_past_unique(self) -> None:
        """**앞뒤 공백은 `unique` 가 안 막는다.**

        `utf8mb4_0900_ai_ci` 는 NO PAD 라 「비잔 (계속)」과 「비잔 (계속) 」이
        나란히 앉는다. 화면에서는 **눈으로 구별되지 않는다.** 엑셀이나
        메신저에서 붙여 넣으면 흔히 붙고, 이름은 한 번 정하면 못 바꾸므로
        오타난 행이 표에 영구히 남는다.
        """
        row = await self.a_furnished_set()
        staff = await self.make_staff(["staff"])

        for sneaky in (f"{row.name} ", f" {row.name}", row.name.replace(" · ", "  ·  ")):
            answer = await self.post(staff, name=sneaky)
            assert answer.status_code == 409, f"{sneaky!r} 가 쌍둥이로 들어갔다 — {answer.text}"

        assert await PrescriptionSet.filter(name=row.name).count() == 1

    async def test_a_blank_name_is_refused(self) -> None:
        staff = await self.make_staff(["staff"])

        answer = await self.post(staff, name="   ")

        assert answer.status_code == 422, answer.text
        assert answer.json()["code"] == "NAME_REQUIRED"
