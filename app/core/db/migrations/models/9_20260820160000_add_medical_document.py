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
    CONSTRAINT `fk_medical__visit_d8e3b1a2` FOREIGN KEY (`visit_id`) REFERENCES `visit` (`visit_id`) ON DELETE RESTRICT,
    KEY `idx_medical__hospita_f3c2a1` (`hospital_id`, `visit_id`)
) CHARACTER SET utf8mb4 COMMENT='An uploaded medical document stored temporarily before OCR and source deletion.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `medical_document`;"""
