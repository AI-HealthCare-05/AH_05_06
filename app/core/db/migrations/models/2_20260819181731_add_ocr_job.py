from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ocr_job` (
    `ocr_job_id` VARCHAR(64) NOT NULL PRIMARY KEY,
    `hospital_id` BIGINT NOT NULL,
    `status` VARCHAR(10) NOT NULL COMMENT 'PROCESSING: PROCESSING\nCOMPLETED: COMPLETED\nFAILED: FAILED' DEFAULT 'PROCESSING',
    `progress` SMALLINT NOT NULL DEFAULT 0,
    `requested_by` BIGINT NOT NULL,
    `started_at` DATETIME(6),
    `completed_at` DATETIME(6),
    `failure_code` VARCHAR(64),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `visit_id` BIGINT NOT NULL,
    CONSTRAINT `fk_ocr_job_visit_a295eab6` FOREIGN KEY (`visit_id`) REFERENCES `visit` (`visit_id`) ON DELETE RESTRICT,
    KEY `idx_ocr_job_hospita_b96ec1` (`hospital_id`, `status`, `created_at`),
    KEY `idx_ocr_job_visit_i_146246` (`visit_id`, `created_at`)
) CHARACTER SET utf8mb4 COMMENT='A clinic-scoped OCR execution for one visit.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ocr_job`;"""


MODELS_STATE = (
    "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"
)
