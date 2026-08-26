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

from tortoise.transactions import in_transaction

from app.models.catalog import ApprovalStatus, CautionSectionKey, DrugCautionContent, PrescriptionSet

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

        content = await DrugCautionContent.filter(
            prescription_set=ps,
            section_key=section_key,
            approval_status=ApprovalStatus.APPROVED,
        ).first()

        if content is None:
            LOGGER.warning(
                "승인된 %s 문구 없음 (세트: %r) — 범용 문구로 폴백",
                section_key,
                set_name,
            )

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
