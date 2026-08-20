from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ocr_document_text` (
    `ocr_document_text_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `document_id` BIGINT NOT NULL,
    `document_type` VARCHAR(12) NOT NULL COMMENT 'EMR: EMR\nPRESCRIPTION: PRESCRIPTION\nLAB_RESULT: LAB_RESULT',
    `raw_text` LONGTEXT,
    `raw_text_purged_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `ocr_result_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_ocr_documen_ocr_res_1d4d51` (`ocr_result_id`, `document_id`),
    CONSTRAINT `fk_ocr_docu_ocr_resu_9e7e08ea` FOREIGN KEY (`ocr_result_id`) REFERENCES `ocr_result` (`ocr_result_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='Temporary OCR text; it must be purged with the approved source document.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ocr_document_text`;"""


MODELS_STATE = (
    "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"
)
