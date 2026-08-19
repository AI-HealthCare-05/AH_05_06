from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `patient` (
    `patient_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `hospital_id` BIGINT NOT NULL,
    `hospital_patient_no` VARCHAR(50) NOT NULL,
    `name` VARCHAR(50) NOT NULL,
    `birth_date` DATE NOT NULL,
    `gender` VARCHAR(7) NOT NULL COMMENT 'FEMALE: FEMALE\nMALE: MALE\nOTHER: OTHER\nUNKNOWN: UNKNOWN' DEFAULT 'UNKNOWN',
    `phone` VARCHAR(20) NOT NULL,
    `sms_consent` BOOL NOT NULL DEFAULT 0,
    `sms_consented_at` DATETIME(6),
    `sms_opted_out_at` DATETIME(6),
    `sms_consent_updated_by` BIGINT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_patient_hospita_41e3cd` (`hospital_id`, `hospital_patient_no`),
    KEY `idx_patient_hospita_eb6e76` (`hospital_id`, `name`, `birth_date`),
    KEY `idx_patient_hospita_720b1e` (`hospital_id`, `phone`)
) CHARACTER SET utf8mb4 COMMENT='A clinic-scoped patient identity shared by all visits.';
        CREATE TABLE IF NOT EXISTS `visit` (
    `visit_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `hospital_id` BIGINT NOT NULL,
    `doctor_id` BIGINT,
    `department` VARCHAR(100),
    `visited_at` DATETIME(6) NOT NULL,
    `visit_summary` LONGTEXT,
    `doctor_note` LONGTEXT,
    `status` VARCHAR(9) NOT NULL COMMENT 'SCHEDULED: SCHEDULED\nCOMPLETED: COMPLETED\nCANCELED: CANCELED' DEFAULT 'COMPLETED',
    `planned_stop` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT NOT NULL,
    CONSTRAINT `fk_visit_patient_1f676882` FOREIGN KEY (`patient_id`) REFERENCES `patient` (`patient_id`) ON DELETE RESTRICT,
    KEY `idx_visit_hospita_edff6d` (`hospital_id`, `visited_at`),
    KEY `idx_visit_patient_98c974` (`patient_id`, `visited_at`)
) CHARACTER SET utf8mb4 COMMENT='One clinic-scoped encounter belonging to exactly one patient.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `visit`;
        DROP TABLE IF EXISTS `patient`;"""


MODELS_STATE = (
    "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"
    "kQ=="
)
