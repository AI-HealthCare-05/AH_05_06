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
    `gender` VARCHAR(6) NOT NULL COMMENT 'FEMALE: FEMALE\nMALE: MALE',
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
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `patient_id` BIGINT NOT NULL,
    CONSTRAINT `fk_visit_patient_1f676882` FOREIGN KEY (`patient_id`) REFERENCES `patient` (`patient_id`) ON DELETE RESTRICT,
    KEY `idx_visit_hospita_edff6d` (`hospital_id`, `visited_at`),
    KEY `idx_visit_patient_98c974` (`patient_id`, `visited_at`)
) CHARACTER SET utf8mb4 COMMENT='One clinic-scoped encounter belonging to exactly one patient.';
        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `visit`;
        DROP TABLE IF EXISTS `patient`;
        """


MODELS_STATE = (
    "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"
)
