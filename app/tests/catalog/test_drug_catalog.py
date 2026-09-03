"""의원이 쓰는 약 목록 — 설정의 「처방」 묶음.

대표 처방에 약을 적을 때 손으로 치지 않고 고르라고 둔다. 약 넷이 여덟 세트에
열세 번 되풀이되고, 손으로 치면 표기가 갈린다 — 이미 갈려 있다(검사·주석은
「비잔정 2mg」, OCR·CSV 는 「비잔정(디에노게스트) 2mg」).

**이 표를 읽는 것은 아직 설정 화면뿐이다.** 안내문·환자 화면·챗봇은 안 읽는다.
그것들이 읽으려면 판독 확정이 `Prescription` 을 만드는 다리(KEY-66)가 먼저
서야 한다. 그러니 이번 성과는 **「설정 입력이 편해졌다」**이지 그 이상이 아니다.
"""

import os
from unittest.mock import patch

from app.models.catalog import DrugCatalog, SetStatus
from app.tests.catalog.test_prescription_settings import PrescriptionSettingsTestCase

NAME = "비잔정(디에노게스트) 2mg"


class DrugCatalogTestCase(PrescriptionSettingsTestCase):
    async def add(self, staff, **over):
        body = {"name": NAME, "frequency": "1일 1회", "note": "매일 같은 시간"}
        body.update(over)
        async with self.client() as client:
            return await client.post("/api/v1/prescription-drugs", json=body, headers=await self.sign_in(staff))

    async def test_it_registers_one(self) -> None:
        staff = await self.make_staff(["staff"])

        answer = await self.add(staff)

        assert answer.status_code == 201, answer.text
        got = answer.json()
        assert got["name"] == NAME
        assert got["frequency"] == "1일 1회"
        assert got["hidden"] is False

    async def test_the_name_is_trimmed_like_a_prescription_set(self) -> None:
        """**앞뒤 공백은 `unique` 가 안 막는다.**

        `utf8mb4_0900_ai_ci` 는 NO PAD 라 「비잔정 2mg 」이 그냥 통과한다.
        화면에서는 눈으로 구별이 안 되고, 이름은 한 번 정하면 못 바꾸므로
        오타난 행이 표에 영구히 남는다.
        """
        staff = await self.make_staff(["staff"])
        await self.add(staff)

        answer = await self.add(staff, name=f"  {NAME}  ")

        assert answer.status_code == 409, answer.text
        assert await DrugCatalog.filter(name=NAME).count() == 1

    async def test_a_hidden_name_is_still_taken(self) -> None:
        """**감춘 약의 이름도 못 쓴다 — 500 이 아니라 409 로.**

        이름이 `unique` 라 그대로 두면 `IntegrityError` 가 500 으로 나가고,
        화면은 「잠시 후 다시 시도해 주세요」만 말한다. 몇 번을 눌러도 같은
        500 이고 까닭을 알 길이 없다.
        """
        staff = await self.make_staff(["staff"])
        made = (await self.add(staff)).json()
        async with self.client() as client:
            await client.put(
                f"/api/v1/prescription-drugs/{made['drug_catalog_id']}",
                json={"frequency": "1일 1회", "note": None, "hidden": True},
                headers=await self.sign_in(staff),
            )

        answer = await self.add(staff)

        assert answer.status_code == 409, answer.text
        assert answer.json()["code"] == "DRUG_EXISTS"
        assert "감춘 것도 포함" in answer.json()["message"]

    async def test_a_blank_name_is_refused(self) -> None:
        staff = await self.make_staff(["staff"])

        answer = await self.add(staff, name="   ")

        assert answer.status_code == 422, answer.text
        assert answer.json()["code"] == "NAME_REQUIRED"

    async def test_a_long_name_is_refused_not_crashed(self) -> None:
        """표 한계(100자)를 넘으면 계약에서 막는다 — 500 이 아니라."""
        staff = await self.make_staff(["staff"])

        answer = await self.add(staff, name="가" * 101)

        assert answer.status_code == 400, answer.text

    async def test_the_name_can_be_changed_while_drafting(self) -> None:
        """**제작 중에는 이름을 고친다** (2026-09-03 결정).

        아직 만드는 중이라 잘못 지은 이름을 고쳐야 한다. 다 만들고 나면
        잠근다 — 아래 검사가 그 쪽을 잰다.
        """
        staff = await self.make_staff(["staff"])
        made = (await self.add(staff)).json()

        async with self.client() as client:
            answer = await client.put(
                f"/api/v1/prescription-drugs/{made['drug_catalog_id']}",
                json={"name": "야즈정 1정", "frequency": "1일 2회", "note": None, "hidden": False},
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 200, answer.text
        assert answer.json()["name"] == "야즈정 1정"

    async def test_the_name_locks_when_drafting_ends(self) -> None:
        """**다 만들면 잠긴다.** 환경변수로 걸어 실제 배포와 같은 길을 잰다.

        규칙을 지우지 않고 스위치로 둔 까닭이 이것이다 — 잠긴 쪽 동작이
        코드에 남아 있어야, 배포 전에 스위치를 끄는 것만으로 규칙이 선다.
        지워 버리면 그때 처음부터 다시 만들어야 한다.

        받아 놓고 무시하면 안 된다: 「바꿔 달라 보냈는데 200 이 오고 안 바뀐」
        조용한 성공이 제일 나쁘다.
        """
        staff = await self.make_staff(["staff"])
        made = (await self.add(staff)).json()

        with patch.dict(os.environ, {"CATALOG_DRAFT_MODE": "false"}):
            async with self.client() as client:
                answer = await client.put(
                    f"/api/v1/prescription-drugs/{made['drug_catalog_id']}",
                    json={"name": "다른 이름", "frequency": "1일 1회", "note": None, "hidden": False},
                    headers=await self.sign_in(staff),
                )

        assert answer.status_code == 409, answer.text
        assert answer.json()["code"] == "CATALOG_LOCKED"
        assert await DrugCatalog.filter(name=NAME).exists(), "튕겼는데 이름이 바뀌었다"

    async def test_hiding_keeps_the_row_and_the_list_still_shows_it(self) -> None:
        """**지우지 않는다. 감춘다.** 목록은 감춘 것도 다 준다 —
        거르면 되살릴 화면이 없어진다."""
        staff = await self.make_staff(["staff"])
        made = (await self.add(staff)).json()

        async with self.client() as client:
            headers = await self.sign_in(staff)
            hid = await client.put(
                f"/api/v1/prescription-drugs/{made['drug_catalog_id']}",
                json={"frequency": "1일 1회", "note": None, "hidden": True},
                headers=headers,
            )
            listed = await client.get("/api/v1/prescription-drugs", headers=headers)

        assert hid.status_code == 200, hid.text
        assert hid.json()["hidden"] is True
        row = await DrugCatalog.filter(drug_catalog_id=made["drug_catalog_id"]).first()
        assert row is not None and row.status is SetStatus.HIDDEN
        assert row.hidden_at is not None, "언제 감췄는지 안 남았다"
        assert [d["name"] for d in listed.json()["items"]] == [NAME], "감췄더니 목록에서 사라졌다"

    async def test_unhiding_clears_the_time(self) -> None:
        staff = await self.make_staff(["staff"])
        made = (await self.add(staff)).json()

        async with self.client() as client:
            headers = await self.sign_in(staff)
            for hidden in (True, False):
                answer = await client.put(
                    f"/api/v1/prescription-drugs/{made['drug_catalog_id']}",
                    json={"frequency": "1일 1회", "note": None, "hidden": hidden},
                    headers=headers,
                )

        assert answer.json()["hidden"] is False
        row = await DrugCatalog.filter(drug_catalog_id=made["drug_catalog_id"]).first()
        assert row is not None and row.hidden_at is None

    async def test_deleting_works_while_drafting(self) -> None:
        """제작 중에는 지운다 — 잘못 등록한 것을 치워야 하니까."""
        staff = await self.make_staff(["staff"])
        made = (await self.add(staff)).json()

        async with self.client() as client:
            answer = await client.delete(
                f"/api/v1/prescription-drugs/{made['drug_catalog_id']}",
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 204, answer.text
        assert not await DrugCatalog.filter(drug_catalog_id=made["drug_catalog_id"]).exists()

    async def test_deleting_locks_when_drafting_ends(self) -> None:
        """**다 만들면 못 지운다.** 의료 데이터라 삭제가 금지되고, 지난
        진료기록이 약 이름을 문자열로 들고 있다."""
        staff = await self.make_staff(["staff"])
        made = (await self.add(staff)).json()

        with patch.dict(os.environ, {"CATALOG_DRAFT_MODE": "false"}):
            async with self.client() as client:
                answer = await client.delete(
                    f"/api/v1/prescription-drugs/{made['drug_catalog_id']}",
                    headers=await self.sign_in(staff),
                )

        assert answer.status_code == 409, answer.text
        assert answer.json()["code"] == "CATALOG_LOCKED"
        assert await DrugCatalog.filter(drug_catalog_id=made["drug_catalog_id"]).exists()

    async def test_the_page_says_whether_drafting(self) -> None:
        """**제작 중인지를 서버가 알려 준다.**

        화면이 이것을 상수로 들고 있으면 서버와 갈린다 — 열어 둔 화면이 잠긴
        서버에 이름을 보내면 409 가 나고, 사용자는 까닭을 모른다.
        """
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            headers = await self.sign_in(staff)
            on = await client.get("/api/v1/prescription-drugs", headers=headers)
            with patch.dict(os.environ, {"CATALOG_DRAFT_MODE": "false"}):
                off = await client.get("/api/v1/prescription-drugs", headers=headers)

        assert on.json()["draft"] is True
        assert off.json()["draft"] is False, "잠갔는데 화면에는 열렸다고 말한다"

    async def test_two_drugs_in_one_row_are_refused(self) -> None:
        """**한 줄에 약 하나.**

        판독이 읽어 오는 값에 실제로 이런 것이 있다 —
        「야즈정(드로스피레논/에티닐에스트라디올) + 메트포르민 500mg」.
        그대로 등록하면 목록에 **약이 아닌 것**이 한 줄 생기고, 자동완성에 떠서
        사람이 고르고, 그렇게 퍼진다. 목록을 둔 까닭이 표기를 하나로 모으는
        것인데 정반대가 된다.
        """
        staff = await self.make_staff(["staff"])

        answer = await self.add(staff, name="야즈정(드로스피레논/에티닐에스트라디올) + 메트포르민 500mg")

        assert answer.status_code == 422, answer.text
        assert answer.json()["code"] == "ONE_DRUG_PER_ROW"
        assert not await DrugCatalog.filter(name__contains="+").exists()

    async def test_a_slash_is_not_a_join(self) -> None:
        """**`/` 는 성분이 둘인 한 약이다.** 막으면 실제 제품을 못 넣는다."""
        staff = await self.make_staff(["staff"])

        answer = await self.add(staff, name="야즈정(드로스피레논/에티닐에스트라디올)")

        assert answer.status_code == 201, answer.text

    async def test_renaming_cannot_join_two_drugs_either(self) -> None:
        """등록은 막고 수정은 안 막으면 뒷문이 남는다."""
        staff = await self.make_staff(["staff"])
        made = (await self.add(staff)).json()

        async with self.client() as client:
            answer = await client.put(
                f"/api/v1/prescription-drugs/{made['drug_catalog_id']}",
                json={"name": "비잔정 2mg + 진통제", "frequency": None, "note": None, "hidden": False},
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 422, answer.text
        assert answer.json()["code"] == "ONE_DRUG_PER_ROW"

    async def test_a_prescription_set_may_still_join(self) -> None:
        """**대표 처방 이름에는 이 규칙을 안 건다.**

        「PCOS · 야즈 + 메트포르민」은 두 약을 함께 쓰는 **처방 한 벌**의
        이름이라 `+` 가 제자리다. 약에 건 규칙을 세트까지 끌고 가면 씨앗
        여덟 중 하나를 못 만든다.
        """
        staff = await self.make_staff(["staff"])

        async with self.client() as client:
            answer = await client.post(
                "/api/v1/prescription-sets",
                json={"name": "PCOS · 야즈 + 메트포르민 (2026)", "disease": "PCOS"},
                headers=await self.sign_in(staff),
            )

        assert answer.status_code == 201, answer.text
