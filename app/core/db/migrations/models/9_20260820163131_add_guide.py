from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `guide_document` (
    `guide_document_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `hospital_id` BIGINT NOT NULL,
    `status` VARCHAR(17) NOT NULL COMMENT 'STAFF_REVIEW: STAFF_REVIEW\nAPPROVAL_PENDING: APPROVAL_PENDING\nSCHEDULED_TO_SEND: SCHEDULED_TO_SEND\nAPPROVAL_RETURNED: APPROVAL_RETURNED' DEFAULT 'STAFF_REVIEW',
    `version` INT NOT NULL DEFAULT 1,
    `approved_by` BIGINT COMMENT '승인한 사람과 시각. 「누가 이 글을 환자에게 내보냈는가」의 답이다.',
    `approved_at` DATETIME(6),
    `scheduled_at` DATETIME(6) COMMENT '발송 예정 시각. 승인이 이 값을 채운다 — 승인과 예약이 한 동작이다.',
    `returned_reason` VARCHAR(200) COMMENT '마지막 반려 사유. 스탭 알림에 그대로 뜨는 문장이라 여기 남긴다.',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `visit_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_guide_do_visit_010d7d7e` FOREIGN KEY (`visit_id`) REFERENCES `visit` (`visit_id`) ON DELETE CASCADE,
    KEY `idx_guide_docum_hospita_ba043d` (`hospital_id`, `status`)
) CHARACTER SET utf8mb4 COMMENT='진료 한 건이 만들어 내는 안내문. `visit` 과 1:1 이다.';
        CREATE TABLE IF NOT EXISTS `guide_event` (
    `guide_event_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `event_type` VARCHAR(8) NOT NULL COMMENT 'EDITED: EDITED\nAPPROVED: APPROVED\nRETURNED: RETURNED',
    `section_key` VARCHAR(10) COMMENT 'MEDICATION: medication\nCAUTION: caution\nLIFE: life\nMESSAGES: messages',
    `reason` VARCHAR(200) COMMENT '반려 사유. 반려가 아니면 비어 있다.',
    `actor_id` BIGINT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `guide_document_id` BIGINT NOT NULL,
    CONSTRAINT `fk_guide_ev_guide_do_bb990088` FOREIGN KEY (`guide_document_id`) REFERENCES `guide_document` (`guide_document_id`) ON DELETE CASCADE,
    KEY `idx_guide_event_guide_d_476c26` (`guide_document_id`, `created_at`)
) CHARACTER SET utf8mb4 COMMENT='승인 · 반려 · 수정 이력.';
        CREATE TABLE IF NOT EXISTS `guide_section` (
    `guide_section_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `section_key` VARCHAR(10) NOT NULL COMMENT 'MEDICATION: medication\nCAUTION: caution\nLIFE: life\nMESSAGES: messages',
    `generated_body` LONGTEXT NOT NULL,
    `edited_body` LONGTEXT,
    `locked` BOOL NOT NULL DEFAULT 0,
    `warn` VARCHAR(200) COMMENT 'AI 가 스스로 자신 없는 곳 · 지난번과 달라진 곳 · 값이 빠진 곳.',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `guide_document_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_guide_secti_guide_d_b4862d` (`guide_document_id`, `section_key`),
    CONSTRAINT `fk_guide_se_guide_do_d5cf94a7` FOREIGN KEY (`guide_document_id`) REFERENCES `guide_document` (`guide_document_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='안내문 네 갈래. 한 갈래가 한 행이다.';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    """이 마이그레이션이 만든 셋만 지운다. **자식부터 지운다.**

    aerich 가 만들어 준 순서는 `guide_document` 가 먼저였는데, `guide_event`
    와 `guide_section` 이 그것을 FK 로 물고 있어 `errno 3730` 으로 멈췄다.
    되돌리다 중간에 멈추면 반쯤 지워진 DB 가 남는다.

    `ALTER TABLE staff MODIFY COLUMN roles JSON NOT NULL` 는 양쪽에서 지웠다.
    7번이 이미 그렇게 만들어 뒀고 지금 DB 도 `json NOT NULL` 이라 아무것도
    바꾸지 않는다 — aerich 가 JSONField 를 볼 때마다 다시 뱉는 줄이다.
    이 마이그레이션이 직원 표를 건드리는 것처럼 보이면 다음 사람이 헷갈린다.
    """
    return """
        DROP TABLE IF EXISTS `guide_event`;
        DROP TABLE IF EXISTS `guide_section`;
        DROP TABLE IF EXISTS `guide_document`;"""


MODELS_STATE = (
    "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"
    "0pI="
)
