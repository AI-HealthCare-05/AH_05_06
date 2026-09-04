"""**씨앗은 비우지 않은 DB 에도 다시 부을 수 있어야 한다.**

`scripts/seed.py` 는 전체가 「같은 명령을 반복 실행해도 쌓이지 않는다」로 짜여
있다 — 병원·직원·환자·진료 모두 `get_or_create` 다. 문구만 예외였다.

문구의 중복 검사는 (세트, 섹션, **버전**) 단위다. 버전이 올라가면 검사를
통과해 `create` 까지 가는데, 옛 승인 행이 같은 `approved_key` 를 들고 있다.
그 칼럼은 unique 라 **씨앗이 IntegrityError 로 통째로 멈춘다.**

2026-09-04 에 원장님이 확인한 글로 열두 칸의 `content_version` 이
`2026-08-25` → `2026-09-04` 로 올라가면서 이 자리가 실제로 열렸다
(이희진 님 `#214` ①). 파일럿처럼 **이미 부어 둔 DB** 에 다시 부으면 걸린다.

고침은 지우는 것이 아니라 **도장을 옮기는 것**이다(KEY-180 §3) — 옛 판은
`approved_key` 를 비우고 `DEPRECATED` 로 내린다. 지우면 이미 나간 안내문의
`GuideSection.drug_caution_content_id` 가 가리키던 근거가 사라진다.
"""

from datetime import UTC, datetime

from tortoise.contrib.test import TestCase

from app.models.catalog import (
    ApprovalStatus,
    CautionSectionKey,
    DrugCautionContent,
    PrescriptionSet,
    SetDisease,
    SourceGrade,
)
from app.tests.fixtures.catalog import DRUG_CAUTION_CONTENTS, PRESCRIPTION_SETS
from scripts.seed import seed_catalog


class SeedIsRerunnableTestCase(TestCase):
    async def an_older_approved_row(self) -> tuple[PrescriptionSet, DrugCautionContent]:
        """**예전 판이 이미 승인 도장을 쥔 DB.** 파일럿이 그 상태다."""
        row = PRESCRIPTION_SETS[0]
        ps = await PrescriptionSet.create(name=row.name, disease=row.disease)
        old = await DrugCautionContent.create(
            prescription_set=ps,
            section_key=CautionSectionKey.CAUTION,
            body="[합성] 옛 판 주의사항",
            source_name="옛 출처",
            source_org="옛 기관",
            source_url="https://example.invalid/old",
            verified_at=datetime(2026, 8, 25, tzinfo=UTC),
            content_version="2026-08-25",
            source_grade=SourceGrade.A,
            approval_status=ApprovalStatus.APPROVED,
            approved_key=f"{ps.prescription_set_id}:{CautionSectionKey.CAUTION.value}",
        )
        return ps, old

    async def test_seeding_again_over_an_older_approved_row_does_not_blow_up(self) -> None:
        """터지지 않는다 — 예전에는 여기서 씨앗이 멈췄다."""
        await self.an_older_approved_row()

        await seed_catalog()  # IntegrityError 가 나면 여기서 끝난다

        assert await DrugCautionContent.filter(approval_status=ApprovalStatus.APPROVED).exists()

    async def test_the_old_stamp_moves_to_the_new_one(self) -> None:
        """**도장은 옮겨진다.** 옛 판은 남되 폐기로 내려간다."""
        ps, old = await self.an_older_approved_row()

        await seed_catalog()

        await old.refresh_from_db()
        assert old.approval_status == ApprovalStatus.DEPRECATED, "옛 판이 승인인 채로 남았다"
        assert old.approved_key is None, "도장을 안 거뒀다 — 다음 판이 또 걸린다"
        assert old.body == "[합성] 옛 판 주의사항", "지우지 않고 남긴다 — 나간 안내문이 이 행을 가리킨다"

    async def test_a_set_stuck_on_the_default_disease_gets_put_back(self) -> None:
        """**옛 줄의 질환도 되돌린다** — `defaults` 는 INSERT 때만 쓰기 때문이다.

        29 번 마이그레이션이 이름으로 백필을 하지만 **그때 이미 있던 줄**만
        고친다. 그 뒤에 모델 기본값(ENDOMETRIOSIS)으로 심긴 PCOS 세트는 다시
        부어도 그대로였다. 설정 레일은 빈 묶음을 안 내므로
        (`settings-rail.js` 의 `setsByDisease`) **다낭성난소증후군 묶음이 통째로
        화면에서 사라진다** — 터지지 않고 조용하다 (이희진 님 `#214` ⑦).
        """
        pcos = next(row for row in PRESCRIPTION_SETS if row.disease is SetDisease.PCOS)
        stuck = await PrescriptionSet.create(name=pcos.name, disease=SetDisease.ENDOMETRIOSIS)

        await seed_catalog()

        await stuck.refresh_from_db()
        assert stuck.disease is SetDisease.PCOS, "기본값에 걸린 세트가 그대로 남았다 — 레일에서 묶음이 사라진다"

    async def test_every_set_ends_up_with_all_four_sections(self) -> None:
        """**터지면 새 세트가 문구 하나 없이 남는다** — 응급까지 폴백이다.

        씨앗은 세트를 먼저 다 만들고(`PrescriptionSet.get_or_create`) 그 다음에
        문구를 넣는다. 문구 첫 줄에서 터지면 **새로 생긴 세트는 문구가 0 행**인
        채 DB 에 남는다. 그 세트를 가리키는 진료의 안내문은 주의·복약·생활만이
        아니라 **응급까지** 범용 문구로 내려간다(`guides.py` 의
        `emergency_content.body if emergency_content else guide_defaults.EMERGENCY`).

        「터지지 않는다」만 재면 이 자리를 놓친다 — 세트마다 네 갈래가 다 찼는지
        본다.
        """
        await self.an_older_approved_row()

        await seed_catalog()

        for row in PRESCRIPTION_SETS:
            ps = await PrescriptionSet.get(name=row.name)
            keys = set(
                await DrugCautionContent.filter(
                    prescription_set=ps, approval_status=ApprovalStatus.APPROVED
                ).values_list("section_key", flat=True)
            )
            assert keys == {key.value for key in CautionSectionKey}, (
                f"{row.name}: 승인 문구가 {sorted(keys)} 뿐이다 — 빠진 갈래는 범용 문구로 나간다"
            )

    async def test_one_stamp_per_set_and_section(self) -> None:
        """**세트·섹션마다 승인은 하나다** — 씨앗을 몇 번 부어도."""
        await self.an_older_approved_row()

        await seed_catalog()
        await seed_catalog()

        stamped = await DrugCautionContent.filter(approved_key__not_isnull=True).values_list("approved_key", flat=True)
        assert len(stamped) == len(set(stamped)), "같은 도장이 둘이다"
        assert len(stamped) == len(DRUG_CAUTION_CONTENTS), (
            f"승인 도장이 {len(stamped)}개 — 픽스처의 {len(DRUG_CAUTION_CONTENTS)}개와 다르다"
        )
