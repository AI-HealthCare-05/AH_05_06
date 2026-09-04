"""처방 세트별 주의·응급 문구 마스터 서비스 — KEY-165.

두 가지 역할을 한다.

  get_approved_content  — 안내 생성 시 승인된 현재 버전 문구를 조회한다.
  approve_version       — 새 버전을 승인하고 이전 버전을 자동으로 폐기한다.

조회(get_approved_content)는 트랜잭션 없이 단순 SELECT 다. None 을 반환하면
호출 쪽(guides.py)이 범용 문구로 폴백한다(KEY-180 §4).

승인(approve_version)은 이전 버전의 approved_key 를 NULL 로 비운 뒤
새 버전에 채우는 두 쓰기를 한 트랜잭션으로 묶는다. 중간에 실패하면 롤백돼
비승인 상태가 유지된다(KEY-180 §3).
"""

import logging
from typing import TYPE_CHECKING

from tortoise.transactions import in_transaction

from app.models.catalog import ApprovalStatus, CautionSectionKey, DrugCautionContent, PrescriptionSet, SourceGrade

if TYPE_CHECKING:
    from tortoise.queryset import QuerySet

LOGGER = logging.getLogger("app.drug_caution")


class DrugCautionService:
    @staticmethod
    async def get_approved_content(
        set_name: str | None,
        section_key: CautionSectionKey,
    ) -> DrugCautionContent | None:
        """처방 세트·섹션의 승인된 현재 버전 문구를 반환한다.

        미등록 세트이거나 승인된 버전이 없으면 None.
        None 을 받은 생성 로직은 범용 문구로 폴백한다(KEY-180 §4).

        이 메서드는 트랜잭션 없이 읽기만 한다 — 호출 측이 트랜잭션을 열기
        전에 실행해 락 보유 시간을 최소화한다.
        """
        if not set_name:
            return None

        ps = await PrescriptionSet.filter(name=set_name).first()
        if ps is None:
            LOGGER.info("미등록 처방 세트: %r — %s 범용 문구로 폴백", set_name, section_key)
            return None

        return await DrugCautionService.approved_content_of(ps, section_key)

    @staticmethod
    def generation_ready() -> "QuerySet[DrugCautionContent]":
        """**생성이 쓸 수 있는 문구만 지나는 문.**

        승인 도장(`approval_status`)만으로는 모자란다. 등급이 B·C 인 근거는
        주의·응급의 단독 근거가 못 된다(KEY-180 §2).

        **설정 화면의 「원본」도 이 문을 지난다.** 두 잣대가 갈리면 화면은
        자문 문구를 「원본」이라 보여 주는데 환자에게는 기본 한 줄이 나간다 —
        고치라고 만든 화면이 거짓말을 하는 셈이다 (이희진 님 `#214` ③).
        """
        return DrugCautionContent.filter(
            approval_status=ApprovalStatus.APPROVED,
            source_grade=SourceGrade.A,
        )

    @staticmethod
    def has_evidence(content: DrugCautionContent) -> bool:
        """**근거가 다 채워졌는가** — KEY-180 §4.

        하나라도 비면 생성에 쓰지 않는다. 출처를 못 대는 글이 환자에게 나가면
        「누가 그렇게 말했나」에 답할 수 없다. `generation_ready()` 와 짝이다 —
        표로 거를 수 없는 조건이라 파이썬에서 본다.
        """
        return all([content.source_name, content.source_org, content.source_url, content.content_version])

    @staticmethod
    async def approved_content_of(
        prescription_set: PrescriptionSet | None,
        section_key: CautionSectionKey,
    ) -> DrugCautionContent | None:
        """**세트를 이미 찾아 둔 쪽을 위한 갈래.**

        안내 생성은 한 진료에서 갈래를 둘 넘게 묻는다. 갈래마다 이름으로 다시
        찾으면 같은 `SELECT` 가 그만큼 돈다 — 한 번 찾아 넘겨 쓰면 된다
        (`#191` 리뷰, 2heej).

        이름으로 부르는 길(`get_approved_content`)은 그대로 둔다. 부르는 쪽이
        세트를 안 들고 있을 수도 있고, 그 길이 「없는 세트」를 로그로 남기는
        자리이기도 하다.

        **`None` 을 받는다.** 처방이 아직 안 붙은 진료가 정상 경로라서다
        (KEY-66 다리가 아직 없어 새 진료는 세트 이름이 비어 있다). 부르는
        쪽마다 `if` 를 두게 하면 그중 하나를 빠뜨린다.
        """
        if prescription_set is None:
            return None
        ps = prescription_set

        # approved_key 로 조회: 값이 채워진 행이 곧 현재 승인본이며 유니크(KEY-180 §3).
        # 승인·등급 조건은 `generation_ready()` 가 갖는다 — 설정 화면이 같은 문을
        # 쓰게 하려고 한자리에 모았다.
        content = (
            await DrugCautionService.generation_ready()
            .filter(
                approved_key=f"{ps.prescription_set_id}:{section_key.value}",
            )
            .first()
        )

        if content is None:
            LOGGER.warning(
                "승인된 %s 문구 없음 (세트: %r) — 범용 문구로 폴백",
                section_key,
                ps.name,
            )
            return None

        if not DrugCautionService.has_evidence(content):
            LOGGER.warning("근거가 비어 있어 폴백 — %s / %r", section_key, ps.name)
            return None

        return content

    @staticmethod
    async def approve_version(content_id: int) -> DrugCautionContent:
        """새 버전을 승인하고 이전 승인 버전을 자동으로 폐기한다.

        KEY-180 §3: 같은 세트·섹션에 승인 버전은 항상 하나뿐이어야 한다.
        두 쓰기(이전 버전 폐기 + 새 버전 승인)를 한 트랜잭션으로 묶어
        중간 실패 시 롤백되도록 한다.

        이미 APPROVED 인 행은 그대로 반환한다(멱등).
        """
        async with in_transaction() as conn:
            content = (
                await DrugCautionContent.filter(drug_caution_content_id=content_id)
                .select_for_update()
                .using_db(conn)
                .first()
            )
            if content is None:
                raise ValueError(f"DrugCautionContent {content_id} 를 찾을 수 없습니다.")
            if content.approval_status == ApprovalStatus.APPROVED:
                return content

            new_approved_key = f"{content.prescription_set_id}:{content.section_key.value}"

            # 이전 승인 버전 폐기 — approved_key 가 같은 행이 기존 승인 버전이다.
            # approved_key 를 NULL 로 비워야 새 버전이 같은 값을 채울 수 있다
            # (유니크 인덱스 충돌 방지).
            await (
                DrugCautionContent.filter(approved_key=new_approved_key)
                .exclude(drug_caution_content_id=content_id)
                .using_db(conn)
                .update(approval_status=ApprovalStatus.DEPRECATED, approved_key=None)
            )

            content.approval_status = ApprovalStatus.APPROVED
            content.approved_key = new_approved_key
            await content.save(
                update_fields=["approval_status", "approved_key", "updated_at"],
                using_db=conn,
            )

        return content
