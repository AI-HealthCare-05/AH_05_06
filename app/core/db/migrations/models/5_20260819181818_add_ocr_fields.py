from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `ocr_field` (
    `ocr_field_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `field_type` VARCHAR(64) NOT NULL,
    `extracted_value` LONGTEXT,
    `corrected_value` LONGTEXT,
    `confidence` DECIMAL(5,4),
    `version` INT NOT NULL DEFAULT 1,
    `is_confirmed` BOOL NOT NULL DEFAULT 0,
    `modified_by` BIGINT,
    `modified_at` DATETIME(6),
    `confirmed_by` BIGINT,
    `confirmed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `ocr_document_text_id` BIGINT,
    `ocr_result_id` BIGINT NOT NULL,
    CONSTRAINT `fk_ocr_fiel_ocr_docu_af0cbc95` FOREIGN KEY (`ocr_document_text_id`) REFERENCES `ocr_document_text` (`ocr_document_text_id`) ON DELETE SET NULL,
    CONSTRAINT `fk_ocr_fiel_ocr_resu_ee76876f` FOREIGN KEY (`ocr_result_id`) REFERENCES `ocr_result` (`ocr_result_id`) ON DELETE CASCADE,
    UNIQUE KEY `uid_ocr_field_ocr_res_b32ce7` (`ocr_result_id`, `field_type`)
) CHARACTER SET utf8mb4 COMMENT='A structured value with OCR, correction, and confirmation provenance.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ocr_field`;"""


MODELS_STATE = (
    "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"
)
