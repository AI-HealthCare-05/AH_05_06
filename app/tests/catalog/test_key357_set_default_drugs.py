"""**대표 처방에는 기본 약이 있어야 한다** — KEY-357.

세트 넷은 9/17 에 심겼는데 **약은 안 들어갔다.** 그래서 판독 화면이 「선택한
약속처방에 기본 약이 없습니다」를 띄우고, 스탭이 약 이름을 손으로 적었다.

손으로 적은 이름은 RAG 를 켠 생성에서 카탈로그와 **글자까지** 맞춰진다
(`app/services/guides.py` 의 `catalog_names`). 2026-09-18 파일럿에서 판독이 읽은

    비잔정(디에노게스트)2mg      ← 공백 없음
    비잔정(디에노게스트) 2mg     ← 카탈로그

가 **공백 한 칸** 달라 생성이 `unrecognized_prescription` 으로 막혔다. 화면에는
「안내문을 만들지 못했습니다」만 나오고, 저장된 약품명은 화면에서 고칠 수도 없다.

그래서 여기서 재는 것은 셋이다.

    세트마다 약이 있나            비어 있으면 손으로 적게 된다
    그 이름이 카탈로그와 같나      한 글자만 달라도 생성이 막힌다
    씨앗을 다시 부어도 되나        쌓이지 않고, 바뀐 용법은 따라온다
"""

from tortoise.contrib.test import TestCase

from app.models.catalog import DrugCatalog, PrescriptionSet, PrescriptionSetDrug
from app.tests.fixtures.catalog import CLINIC_DRUG_NAMES, CLINIC_DRUGS, PRESCRIPTION_SETS
from scripts.seed import seed_catalog


class TestTheFixtureNamesTheDrugsExactly:
    """DB 없이 재는 것 — 명단끼리 어긋났는지."""

    def test_every_set_names_at_least_one_drug(self) -> None:
        for row in PRESCRIPTION_SETS:
            assert row.drugs, f"{row.name} 에 기본 약이 없다 — 스탭이 손으로 적게 된다"

    def test_set_drugs_match_the_clinic_catalog_letter_for_letter(self) -> None:
        """한 글자만 달라도 RAG 를 켠 생성이 그 세트에서 통째로 막힌다."""
        for row in PRESCRIPTION_SETS:
            for name in row.drugs:
                assert name in CLINIC_DRUG_NAMES, f"{row.name} 의 {name!r} 가 CLINIC_DRUGS 에 없다"

    def test_the_catalog_has_no_duplicate_names(self) -> None:
        """이름이 열쇠다 — 겹치면 어느 용법이 실릴지 알 수 없다."""
        names = [row.name for row in CLINIC_DRUGS]
        assert len(names) == len(set(names))


class SeedPlantsTheDefaultDrugsTestCase(TestCase):
    async def _drugs_of(self, set_name: str) -> list[PrescriptionSetDrug]:
        prescription_set = await PrescriptionSet.get(name=set_name)
        return await PrescriptionSetDrug.filter(prescription_set=prescription_set).order_by("position")

    async def test_seed_plants_each_sets_drugs_with_the_catalog_usage(self) -> None:
        await seed_catalog()

        by_name = {row.name: row for row in CLINIC_DRUGS}
        for row in PRESCRIPTION_SETS:
            planted = await self._drugs_of(row.name)
            assert [drug.name for drug in planted] == list(row.drugs), f"{row.name} 의 기본 약이 다르다"
            for position, drug in enumerate(planted):
                source = by_name[drug.name]
                assert (drug.frequency, drug.note, drug.position) == (source.frequency, source.note, position)

    async def test_the_planted_names_pass_the_generation_gate(self) -> None:
        """`app/services/guides.py` 가 보는 것과 **같은 집합**으로 잰다.

        거기서 걸리면 화면에는 「안내문을 만들지 못했습니다」만 나온다 — 어느
        약이 왜 거절됐는지는 서버 로그에만 남는다.
        """
        await seed_catalog()

        catalog_names = set(await DrugCatalog.all().values_list("name", flat=True))
        catalog_names.update(await PrescriptionSetDrug.all().values_list("name", flat=True))
        for row in PRESCRIPTION_SETS:
            for name in row.drugs:
                assert name in catalog_names, f"{row.name} 의 {name!r} 로 만든 진료는 생성이 막힌다"

    async def test_reseeding_does_not_pile_up_drugs(self) -> None:
        await seed_catalog()
        await seed_catalog()

        for row in PRESCRIPTION_SETS:
            assert len(await self._drugs_of(row.name)) == len(row.drugs)

    async def test_reseeding_fixes_usage_that_drifted(self) -> None:
        """`defaults` 는 INSERT 때만 먹는다 — `DrugCatalog` 에서 겪은 그 자리다."""
        await seed_catalog()
        first = (await self._drugs_of(PRESCRIPTION_SETS[0].name))[0]
        first.frequency = "1일 9회"
        first.note = "손으로 고친 값"
        first.position = 7
        await first.save()

        await seed_catalog()

        await first.refresh_from_db()
        source = {row.name: row for row in CLINIC_DRUGS}[first.name]
        assert (first.frequency, first.note, first.position) == (source.frequency, source.note, 0)

    async def test_seed_keeps_drugs_the_clinic_added_itself(self) -> None:
        """씨앗은 **제가 아는 줄만** 손댄다 — 화면에서 넣은 약을 치우지 않는다."""
        await seed_catalog()
        prescription_set = await PrescriptionSet.get(name=PRESCRIPTION_SETS[0].name)
        await PrescriptionSetDrug.create(
            prescription_set=prescription_set, name="의원이 직접 넣은 약", frequency="1일 1회", position=9
        )

        await seed_catalog()

        names = [drug.name for drug in await self._drugs_of(PRESCRIPTION_SETS[0].name)]
        assert "의원이 직접 넣은 약" in names
