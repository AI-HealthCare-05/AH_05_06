from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `medical_document` (
    `document_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `hospital_id` BIGINT NOT NULL,
    `document_type` VARCHAR(12) COMMENT 'EMR: EMR\nPRESCRIPTION: PRESCRIPTION\nLAB_RESULT: LAB_RESULT',
    `file_path` VARCHAR(500) NOT NULL,
    `file_size` BIGINT NOT NULL,
    `mime_type` VARCHAR(100) NOT NULL,
    `uploaded_by` BIGINT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `visit_id` BIGINT NOT NULL,
    CONSTRAINT `fk_medical__visit_c481d6ba` FOREIGN KEY (`visit_id`) REFERENCES `visit` (`visit_id`) ON DELETE RESTRICT,
    KEY `idx_medical_doc_hospita_a7ee6f` (`hospital_id`, `visit_id`)
) CHARACTER SET utf8mb4 COMMENT='An uploaded medical document stored temporarily before OCR and source deletion.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `medical_document`;"""


MODELS_STATE = (
    "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"
    "Jho9y522cSfvwfxpwOjQ=="
)
