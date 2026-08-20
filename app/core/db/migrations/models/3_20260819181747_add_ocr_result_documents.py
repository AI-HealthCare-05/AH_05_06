from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ocr_job_document` (
    `ocr_job_document_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `document_id` BIGINT NOT NULL,
    `document_type` VARCHAR(12) NOT NULL COMMENT 'EMR: EMR\nPRESCRIPTION: PRESCRIPTION\nLAB_RESULT: LAB_RESULT',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `ocr_job_id` VARCHAR(64) NOT NULL,
    UNIQUE KEY `uid_ocr_job_doc_ocr_job_361307` (`ocr_job_id`, `document_id`),
    CONSTRAINT `fk_ocr_job__ocr_job_4aab3f50` FOREIGN KEY (`ocr_job_id`) REFERENCES `ocr_job` (`ocr_job_id`) ON DELETE CASCADE,
    KEY `idx_ocr_job_doc_documen_1487d6` (`document_id`)
) CHARACTER SET utf8mb4 COMMENT='An uploaded document queued in one OCR execution.';
        CREATE TABLE IF NOT EXISTS `ocr_result` (
    `ocr_result_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `model_name` VARCHAR(100) NOT NULL,
    `model_version` VARCHAR(50),
    `version` INT NOT NULL DEFAULT 1,
    `modified_by` BIGINT,
    `modified_at` DATETIME(6),
    `confirmed_by` BIGINT,
    `confirmed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `ocr_job_id` VARCHAR(64) NOT NULL UNIQUE,
    CONSTRAINT `fk_ocr_resu_ocr_job_ae4413c3` FOREIGN KEY (`ocr_job_id`) REFERENCES `ocr_job` (`ocr_job_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='Versioned OCR output and its review/confirmation audit metadata.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ocr_result`;
        DROP TABLE IF EXISTS `ocr_job_document`;"""


MODELS_STATE = (
    "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"
)
