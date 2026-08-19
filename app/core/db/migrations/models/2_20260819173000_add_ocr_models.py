from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE IF NOT EXISTS `ocr_job` (
    `ocr_job_id` VARCHAR(64) NOT NULL PRIMARY KEY,
    `hospital_id` BIGINT NOT NULL,
    `visit_id` BIGINT NOT NULL,
    `status` VARCHAR(10) NOT NULL DEFAULT 'PROCESSING',
    `progress` SMALLINT NOT NULL DEFAULT 0,
    `requested_by` BIGINT NOT NULL,
    `started_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `completed_at` DATETIME(6),
    `failure_code` VARCHAR(64),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT `fk_ocr_job_visit` FOREIGN KEY (`visit_id`) REFERENCES `visit` (`visit_id`) ON DELETE RESTRICT,
    CONSTRAINT `chk_ocr_job_progress` CHECK (`progress` BETWEEN 0 AND 100),
    KEY `idx_ocr_job_hospital_status_created` (`hospital_id`, `status`, `created_at`),
    KEY `idx_ocr_job_visit_created` (`visit_id`, `created_at`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ocr_result` (
    `ocr_result_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `ocr_job_id` VARCHAR(64) NOT NULL,
    `model_name` VARCHAR(100) NOT NULL,
    `model_version` VARCHAR(50),
    `version` INT NOT NULL DEFAULT 1,
    `modified_by` BIGINT,
    `modified_at` DATETIME(6),
    `confirmed_by` BIGINT,
    `confirmed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_ocr_result_job` (`ocr_job_id`),
    CONSTRAINT `fk_ocr_result_job` FOREIGN KEY (`ocr_job_id`) REFERENCES `ocr_job` (`ocr_job_id`) ON DELETE CASCADE,
    CONSTRAINT `chk_ocr_result_version` CHECK (`version` >= 1)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ocr_job_document` (
    `ocr_job_document_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `ocr_job_id` VARCHAR(64) NOT NULL,
    `document_id` BIGINT NOT NULL,
    `document_type` VARCHAR(12) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_ocr_job_document` (`ocr_job_id`, `document_id`),
    KEY `idx_ocr_job_document_id` (`document_id`),
    CONSTRAINT `fk_ocr_job_document_job` FOREIGN KEY (`ocr_job_id`) REFERENCES `ocr_job` (`ocr_job_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ocr_document_text` (
    `ocr_document_text_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `ocr_result_id` BIGINT NOT NULL,
    `document_id` BIGINT NOT NULL,
    `document_type` VARCHAR(12) NOT NULL,
    `raw_text` LONGTEXT,
    `raw_text_purged_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_ocr_document_result_document` (`ocr_result_id`, `document_id`),
    CONSTRAINT `fk_ocr_document_result` FOREIGN KEY (`ocr_result_id`) REFERENCES `ocr_result` (`ocr_result_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ocr_field` (
    `ocr_field_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `ocr_result_id` BIGINT NOT NULL,
    `ocr_document_text_id` BIGINT,
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
    CONSTRAINT `fk_ocr_field_result` FOREIGN KEY (`ocr_result_id`) REFERENCES `ocr_result` (`ocr_result_id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ocr_field_document` FOREIGN KEY (`ocr_document_text_id`) REFERENCES `ocr_document_text` (`ocr_document_text_id`) ON DELETE SET NULL,
    CONSTRAINT `chk_ocr_field_confidence` CHECK (`confidence` IS NULL OR (`confidence` >= 0 AND `confidence` <= 1)),
    CONSTRAINT `chk_ocr_field_version` CHECK (`version` >= 1),
    KEY `idx_ocr_field_result_type` (`ocr_result_id`, `field_type`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ocr_field_candidate` (
    `ocr_field_candidate_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `ocr_field_id` BIGINT NOT NULL,
    `candidate_value` LONGTEXT NOT NULL,
    `confidence` DECIMAL(5,4),
    `rank` SMALLINT NOT NULL,
    `source_date` DATE,
    `is_selected` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_ocr_candidate_field_rank` (`ocr_field_id`, `rank`),
    CONSTRAINT `fk_ocr_candidate_field` FOREIGN KEY (`ocr_field_id`) REFERENCES `ocr_field` (`ocr_field_id`) ON DELETE CASCADE,
    CONSTRAINT `chk_ocr_candidate_confidence` CHECK (`confidence` IS NULL OR (`confidence` >= 0 AND `confidence` <= 1)),
    CONSTRAINT `chk_ocr_candidate_rank` CHECK (`rank` >= 1)
) CHARACTER SET utf8mb4;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS `ocr_field_candidate`;
DROP TABLE IF EXISTS `ocr_field`;
DROP TABLE IF EXISTS `ocr_document_text`;
DROP TABLE IF EXISTS `ocr_job_document`;
DROP TABLE IF EXISTS `ocr_result`;
DROP TABLE IF EXISTS `ocr_job`;
"""


MODELS_STATE = "KEY-59: OCR model migration; regenerate with Aerich after dependency branches are merged."
