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
    KEY `idx_ocr_field_ocr_res_53e411` (`ocr_result_id`, `field_type`)
) CHARACTER SET utf8mb4 COMMENT='A structured value with OCR, correction, and confirmation provenance.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `ocr_field`;"""


MODELS_STATE = (
    "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"
)
