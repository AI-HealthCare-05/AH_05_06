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
) CHARACTER SET utf8mb4 COMMENT='One clinic-scoped encounter belonging to exactly one patient.';
        CREATE TABLE IF NOT EXISTS `guide_document` (
    `guide_document_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `hospital_id` BIGINT NOT NULL,
    `status` VARCHAR(17) NOT NULL COMMENT 'STAFF_REVIEW: STAFF_REVIEW\nAPPROVAL_PENDING: APPROVAL_PENDING\nSCHEDULED_TO_SEND: SCHEDULED_TO_SEND\nAPPROVAL_RETURNED: APPROVAL_RETURNED' DEFAULT 'STAFF_REVIEW',
    `version` INT NOT NULL DEFAULT 1,
    `approved_by` BIGINT COMMENT '승인한 사람과 시각. 「누가 이 글을 환자에게 내보냈는가」의 답이다.',
    `approved_at` DATETIME(6),
    `scheduled_at` DATETIME(6) COMMENT '발송 예정 시각. 승인이 이 값을 채운다 — 승인과 예약이 한 동작이다.',
    `returned_reason` VARCHAR(200) COMMENT '마지막 반려 사유. 스탭 알림에 그대로 뜨는 문장이라 여기 남긴다.',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `visit_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_guide_do_visit_010d7d7e` FOREIGN KEY (`visit_id`) REFERENCES `visit` (`visit_id`) ON DELETE CASCADE,
    KEY `idx_guide_docum_hospita_ba043d` (`hospital_id`, `status`)
) CHARACTER SET utf8mb4 COMMENT='진료 한 건이 만들어 내는 안내문. `visit` 과 1:1 이다.';
        CREATE TABLE IF NOT EXISTS `guide_event` (
    `guide_event_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `event_type` VARCHAR(8) NOT NULL COMMENT 'EDITED: EDITED\nAPPROVED: APPROVED\nRETURNED: RETURNED',
    `section_key` VARCHAR(10) COMMENT 'MEDICATION: medication\nCAUTION: caution\nLIFE: life\nMESSAGES: messages',
    `reason` VARCHAR(200) COMMENT '반려 사유. 반려가 아니면 비어 있다.',
    `actor_id` BIGINT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `guide_document_id` BIGINT NOT NULL,
    CONSTRAINT `fk_guide_ev_guide_do_bb990088` FOREIGN KEY (`guide_document_id`) REFERENCES `guide_document` (`guide_document_id`) ON DELETE CASCADE,
    KEY `idx_guide_event_guide_d_476c26` (`guide_document_id`, `created_at`)
) CHARACTER SET utf8mb4 COMMENT='승인 · 반려 · 수정 이력.';
        CREATE TABLE IF NOT EXISTS `guide_section` (
    `guide_section_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `section_key` VARCHAR(10) NOT NULL COMMENT 'MEDICATION: medication\nCAUTION: caution\nLIFE: life\nMESSAGES: messages',
    `generated_body` LONGTEXT NOT NULL,
    `edited_body` LONGTEXT,
    `locked` BOOL NOT NULL DEFAULT 0,
    `warn` VARCHAR(200) COMMENT 'AI 가 스스로 자신 없는 곳 · 지난번과 달라진 곳 · 값이 빠진 곳.',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `guide_document_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_guide_secti_guide_d_b4862d` (`guide_document_id`, `section_key`),
    CONSTRAINT `fk_guide_se_guide_do_d5cf94a7` FOREIGN KEY (`guide_document_id`) REFERENCES `guide_document` (`guide_document_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='안내문 네 갈래. 한 갈래가 한 행이다.';
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
) CHARACTER SET utf8mb4 COMMENT='Versioned OCR output and its review/confirmation audit metadata.';
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
) CHARACTER SET utf8mb4 COMMENT='Temporary OCR text; it must be purged with the approved source document.';
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
    UNIQUE KEY `uid_ocr_field_ocr_res_53e411` (`ocr_result_id`, `field_type`),
    CONSTRAINT `fk_ocr_fiel_ocr_docu_af0cbc95` FOREIGN KEY (`ocr_document_text_id`) REFERENCES `ocr_document_text` (`ocr_document_text_id`) ON DELETE SET NULL,
    CONSTRAINT `fk_ocr_fiel_ocr_resu_ee76876f` FOREIGN KEY (`ocr_result_id`) REFERENCES `ocr_result` (`ocr_result_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='A structured value with OCR, correction, and confirmation provenance.';
        CREATE TABLE IF NOT EXISTS `ocr_field_candidate` (
    `ocr_field_candidate_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `candidate_value` LONGTEXT NOT NULL,
    `confidence` DECIMAL(5,4),
    `rank` SMALLINT NOT NULL,
    `source_date` DATE,
    `is_selected` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `ocr_field_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_ocr_field_c_ocr_fie_ede909` (`ocr_field_id`, `rank`),
    CONSTRAINT `fk_ocr_fiel_ocr_fiel_e2cf222c` FOREIGN KEY (`ocr_field_id`) REFERENCES `ocr_field` (`ocr_field_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='A ranked alternative retained when one field has multiple readings.';
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
) CHARACTER SET utf8mb4 COMMENT='A clinic-scoped OCR execution for one visit.';
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
        ALTER TABLE `staff` MODIFY COLUMN `roles` JSON NOT NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `staff` MODIFY COLUMN `roles` JSON NOT NULL;
        DROP TABLE IF EXISTS `guide_event`;
        DROP TABLE IF EXISTS `guide_section`;
        DROP TABLE IF EXISTS `ocr_document_text`;
        DROP TABLE IF EXISTS `guide_document`;
        DROP TABLE IF EXISTS `visit`;
        DROP TABLE IF EXISTS `ocr_field_candidate`;
        DROP TABLE IF EXISTS `ocr_result`;
        DROP TABLE IF EXISTS `ocr_job_document`;
        DROP TABLE IF EXISTS `ocr_field`;
        DROP TABLE IF EXISTS `patient`;
        DROP TABLE IF EXISTS `ocr_job`;"""


MODELS_STATE = (
    "eJztXW1zm0i2/iuU75fMlCcXJCSQ7yfFVjKecSyXrWT27mhLgaZls5FAC8iJazf/ffsFmu"
    "ZVgGQJabpcZZtWn6Z5+u2c5xyO/n22dC248N8OoWeDp7ML6d9njrGE6J/UJ+fSmbFaxeW4"
    "IDDMBalqxHVMP/AMEKDSubHwISqyoA88exXYroNKnfVigQtdgCrazmNctHbsf63hLHAfYf"
    "AEPfTBn/9AxbZjwe/Qjy5XX2dzGy6sRFdtC9+blM+ClxUpu3aC96Qivps5A+5ivXTiyquX"
    "4Ml1WG3bCXDpI3SgZwQQNx94a9x93LvwOaMnoj2Nq9AucjIWnBvrRcA9bkUMgOtg/FBvfP"
    "KAj/guv3QUVVP1bl/VURXSE1ai/aCPFz87FSQI3E7OfpDPjcCgNQiMMW7P0PNxlzLgXT4Z"
    "Xj56nEgKQtTxNIQRYGUYRgUxiPHE2RGKS+P7bAGdxwBP8E6vV4LZ5+H95a/D+zeo1k/4aV"
    "w0mekcvw0/6tDPMLAxkHhp1AAxrH6cACqyXAFAVKsQQPJZEkB0xwDSNZgE8beH8W0+iJxI"
    "CkjLBoH0H2lh+5lF3Q5AS/DDz4s7vfT9fy142N58HP4tjejlzfgdeX7XDx490gpp4B1CF2"
    "+W86/csscFpgG+fjM8a5b5xO24RXWzHy07y3SJ4RiPBCv8xPj5wuPjk0+28syxQspLD5U1"
    "quG360x5Zz+e0LEy6HS6Xa0jd/t6T9W0ni6z8yX7UdlB8+76Az5rEnNz8+EDl4a9qLNrMo"
    "Hj3DfVKtumWrxrqplN88nwn6A1Wxm+/831cuZrMZY5oseJqtLRq5xGHb34NMKfJYElf2ug"
    "GdU/Tgg7VSZmp3hidjITEz2xRbf3LIIjZ70kKF6jLhkOgBk0Y+kD43n2cXgzupDw76nzfk"
    "Sv6N+zBjj3K8DcL0S5nwbZtL3gyTJesjBfIXDyJyovk1aakFBgL+Fb/E87p20JflfDySiF"
    "zwo9HZyh2WYWTcV8jNJyx7moFaXKtqgU74pKer7Z/gwpYfZzzs74znUX0HAKFCNeLgWmiQ"
    "RfC02mNO16rr0bj28SKvq765Tyc/vp47sRgpegiyrZQUInSmJqLe0cC3wjpJHYHhGtq30f"
    "BNKF4QezhfuYB+pVuMflo5qULNse8T8VQA5nYDt2yMn1x9HDZPjxLoEz3jfxJx1S+pIqzR"
    "xHrBHpj+vJrxK+lP4+vh2ljVBWb/L3M9wnYx24M8f9hqYt/9hRcVSUpAQ8iKGdGTmsQPlA"
    "JiV3MJCH2M3RM1hjZ/ESzqMjGdlwypcO7HplNRzYpKQY2IMOLOl8S1imOyOwMReYQzRFH5"
    "2XcU0rrtImtulsKIGF7djgFx+4K2hJobBkW+i3HbxIPtItUbn5IhmLhfRs+3bgv01bDFs0"
    "k8Nq/Xn25PorOzAWM0pEscuwWTRoZ/9IcV8ZociOJWbCjBgCSCRTjWjItLVc6iy6ZV0KLS"
    "knqLTKVFpqfKojnh7YjZC3ZA/dI+o5KHNLKoN2CeWWL36c5mWvCmfUK+aMehnO6K/Fue0e"
    "P27PztWqSgghJnXqlNDx8ZJnn25/vx3/QVyCKTUkSUhOHZ6sHE9+Hd1fSOTP1AnbuJD4xm"
    "pO2LLtM5qvWuF01dKzlaoQNZY7EzjO9b57jt1f+jN8y1yveSl7lJIUBFIhsI2M1Dx5QSYd"
    "mEzCg+Ku8IC466DhoKblxaC2YFDDlTaLqCEzxx9WZgEVt9HIGNr/gB7GFhLk7ElweIKcPd"
    "GBrUvOcjHBhGfM2URDufe/38OFEeTHAIec62fcRjtH+Ec0baNSHqzXoqc/rG0LXrlgvSwg"
    "qZMVzsuo6kdcdWbxdTcy1tM1GAB1ujZ1AKTp2ur18B8DaKgMaJqKLswBAOi3CnFRzyRFso"
    "llOgN8AXqqzorMrv5W+kJmyhfS0BxIyoUi0dawDFSzhPdBejF10E90r/j+uClLzmkx7ora"
    "oxdEsKPopDLo03bRRUdW8B+rT+sNZNwFGbdpAsVkXTaA3mWNon6Quw30qJMG7BKRngr4Ds"
    "S9J//gHlggBZBpaPQGygALqTK5gU4uejqDDvSNQfxUQMGSsgywIJQRfjSg/4vE6oB+B9cZ"
    "aDo3kpsjaTNuAj8wgrVf4idITuXa5HWuuPAaCK9BC1DnjBS6CjIAV+McY+k9co5I03j/fn"
    "Y/+nw9+iOHeOQ/vpD4q6kzvLu7H38e3szuRrdX17cfLqR0ydR5uPx1dPXpZnQ1m4xnD6gU"
    "NZIu4lq6H00+3d+OrrimoqImRKZShclUiqlMJcNlFr5FVbiAil+iesXFo2y9crZ8Dy3xup"
    "TnPjew1lOChzXRsULTMenZqsc6hmzgE1rTQaiS0LObKAfKW3TVJYev2ZFVpjCEB68BZZmc"
    "5Gm9AusqRJMAsUIE5uQgBzrVNGhbpHUrVgA6895GnewIH6EVGzubi/VN5ZSoIBIPTSSCJ2"
    "itF83o/pRsmwbzjCj82NhRDGIX9WW8IHWll1nS/DYQ2QFaZF902JIGQCUmhamm7SC+gWjT"
    "oLfraRZvAJENoGuRygNl0/Z0dP0/4WXiwWDtOWime9Dw6702niPaSKHd6dIY4JMHDIBM/h"
    "9Q8xgfRnpHZccgQMcGnWAGGmZLhhZlDfABODBjIsGw5li0i08wU6ezROvojAeIbHsjPs5C"
    "bqEHQcwDyIZOLsqWxDH0GzMXYXW9Q5arjrUFABibQziv0TMOeWRaBFqr/UgZKDztU471ap"
    "71Mtd69m104d04BRJceDdOdGDDzqecFrV5LF5qN3b46RCHjXxHEO/mW/qO4mOhnYuo0IGU"
    "MCggwO3uAooH2tSRgZH1pqUWaxaZsQMnLvqVIUR37GN87TVahAkq9oxvzA2S2H3Q46GHgj"
    "Qk7XL4cDm8Gp392LEDki6qIu8jW3KbXI/wuY7fkVlVSLuTZVNLK6thGXawxZYd0xvLCatm"
    "TVKPYB6F1TOpAKBqL/FBAi2ms3o6c95Rjiry9xHlF+nWREKjDBdx8Q0UhSnapkr6M7CM2B"
    "oN3YqaHrna8G3I81moLPFgoVrs/Pwzr+GzPli9PlHALT2nQz//HJquWaM3Mg5iD2H2wbGj"
    "EKvulsyeL3RkEkWdWiKRBo/MiXyrIfbGAhko+K4WsUUoXsQvaczN2PCgjtPIFGfjx3rFTA"
    "4542tVZQnDFBrrCFDcqjYgmBn4UZWeTnCMe0ZtEJ1ZN6bak6mLNdtjEPeY86SmO0nRhKrO"
    "uWUpLyFbVtRxLHkeW2EaNqliv64cDXU0Q5WuQsw3KxoBjD2164yM3VTFZZuNJuAsmE2eW7"
    "ITNHTb8rLCZ1s9aRKBjSCVAb2aRzHZwqEzrIyurifYtUf/Rl6/2NmHy2IH4DZ+vyppgoqT"
    "BGVSBIUa3uwrzHFhVfTtJps4MB/2EQ3B5XByPb69kJbQsgFRTqfO5fATLQTIACMlN9fvRx"
    "fSwp7DqYMMt4fhh9EDlvF9pHz4uSd2dBKzPZJucTjEh2xbMrf94oMzPBWigwdGpx/ZCJN0"
    "b54SwG6Att84kog7ZjfSSkq1HIclKQ7TE6YJZ9oeqrSYX+RRZ4qUSgaMOPY2D0SW8X+9e+"
    "2fS0QKsuvVPiR5KRFfIyLRT57Sy3K1h4kObMmwHo7nKxqALPrvXQ/aj87v8KUiZZOJcm4f"
    "8FXJm9zZVYHF2VtGlAR3WMT5cNziJtbH56pW4X1SYdX4WFY6akLNeytxQeCx7scIDWq8M8"
    "u5JITp1W6G+QpKuFgWNb9JWAAmQijDEdETXMQUCzsguisMbxkSE2o+VcM5TiOuhlFNEd/A"
    "CAmJslfD69hvGjEPskZjrAhn0dUA4wS6msx6TlkZs2MlQyV4+YzujX9TzisibGhUuqaSx7"
    "dooAThOowwYqMjM+oLqIQUykTRT503uFOqHPWAGgRWT6a9IR3UVelK+aUTk1bph2cx8XLB"
    "4BQ9dWqITJmKsGfMGyiAfjuFj89RZjEIMVcmxSOhzhO4/kSm2peFC75C64vEqlt6F3M90K"
    "A8YU8hIXaDYoaNwEwmKw1bAYNQkkWyWKrOrLEwBC+0tqw5oZo0LhLAJLTUwCCPic4aOhEJ"
    "J1YSGMAFzPA0WaSfc4JmF2SXRCiiyBm6MrvMgIKjC82uTB+TXAx4yoy3D0qYsTwqjDfQ07"
    "mTNlBjkWgzrSUpLeixyvRYS1iZHRJkr0XLVAqV3zkJwnCbma6VM0QT+L1oYWQkjyURSJlJ"
    "NvrbJGGNZb7sgVlkN+PbD1H19DdAJDFGk6QJwCmxw1JOrQWXHtA5e3pZwpVYSORaScKJ7J"
    "xalGhU/8CEaEL1Ji5U+jvUmsI3HjpUIQ213dBBOe/GhHUYwiljx6QJ9FhjRYoKoOoUqZSV"
    "jGKaQ76zLyfq5eSabHmHyTu6/V5I3E+jlz86fUOOdeFUPLcW07uRRziMbgVhEGvG3Z28BQ"
    "3o7hIvK9GGN7tURSjqfrf3E6Y3RSjqSQxsJvRP0NaCtha0dVPamkZ15vDVLNyzmKhmcaWb"
    "CeqxA1PZt6ED3LUTQE8y4cJ1HhHaUuBK8DtqZ/EiuUggzNub1a62bq1Bcg3ysGGYFk7RzW"
    "Uw5z8qpKn2ETEvaCmRaWOPkQCoX01CLRJiIulfGcBwZXhB/qlabLMnpY6EV9rDV95y23RN"
    "AyApeZwGwJEo/JXei6anor9eLg2vFueaETyS1bFv1jXcoh03L7l9MbwpMQFuLrhHmKDqcv"
    "zx7mY0CQPBU9mpolRSXFapqcMkLiT2L3ai3V6OSNXovyZuskGFs2FQeDIMMqnxF4aDMyX4"
    "gZvzpfKljoa0qHA3CDL1BDk3Qaae6MBmyNR9fZNYS8axDfQpRyRtyZty37zXPqyrMqbJmZ"
    "SgSu/R5L6/vpyUcaUxri7wZv90zS1TAoyB95trHhek9VJrp4j8YriifAEV8yjUIPAPpvPn"
    "Q1eDPkfTI3pObBad5RDp6SrnZZQ6nrTMWxBE1TfS6xO4XKEtx3uRxpf3Epb7P8kOpOXaDy"
    "QTSqu1h3ovfbODJyl4glKUDlHy3bUHoBTdMcu077Lh3CBQ/MDo9MJjSu/NHCWVA0AzmNU+"
    "vYpaEIx7Zca9sf9VeF7rMe7hJN3ihfRMI4cOuR19vL+Q0K+pc4eO+Mv76zsaactfTZ2b4b"
    "sZKvh0M7mQ4v+b8AdKpwq53CnmljuZd42RBhPt1lXJMl5GMGW5TFkE0YyeMw2szfwW2pQy"
    "9i9J4Ate6CToA8ELnejAZnihWE1vpFwnRIWKV4MdStpHWxJEyBS9Z221D/CqFFFmRtUNqI"
    "vhDcuyE7oeRcRmflu1hv1+/RpDJJ8OYWiV8yBzVm0j/zGUUI01CNYetKRnY7GGlJMYX96f"
    "S8D1PPqO4blkOBa6dua2tySjKhG+wsHLJucljl21WoH54KZfLeKDyjXZk3lJQXRUJjo4kD"
    "OQF8dkJaWO5U3KpNncVyuYzX210GzGH6XenPxO1jXS+sjqqmM954gKIzrXiA43qiYg54gK"
    "kAtARru/BUPtK2X3QGAvjUURxLxg2uyhkm/DFo4N6avR5fXH4c2b3rmaihSJEFezQZriu9"
    "1qfrebTb5PHesetd+TTouK8KUktEgxtdEt6n9tXkpQBLmX+DQYVvU5o5SooHUPTetGm0nt"
    "BZOWFCumLAMnA6sBf56SFWvm0GtGuEJOgTEXrpATHdiMK+RQoUat2HkPc+AJ75PwPh2b96"
    "lwy9gNkumQ0tbtFFXhzNsME4g+jCbS7aebm2oOPWA4lo2Pxh059S6j9o5r0u7FvRdjU+Ln"
    "SwBYweE3AwmBCq4/z3C+QksyFgH0HDSsz1DyYIDAwJHJT9Ah2T9I29KT4UtLhLu9WuBKho"
    "Ww9fMcfztps9Dtxzyb+DZN/H0Moy08f+k2hA+wsg8whq6+SyUreizeQOFTaQHSTXwqZJfJ"
    "QPiAnn5RuE9EMkemLnc7Wp9tBfiibPE/ICBvstYGfXdlFh1BWcs9H7GUWJnZfnSTDlndWa"
    "+Tj1Q07Byu73TiJYXPSbwyf4K0UZYP3Ge0VksGsy0UBtO3t7e7q0Z6tsgWPM8hMPjp1KZ0"
    "lOHr1vn2ZPgidrkR+c+wUgXDMZlCEr/gikYGkG93kOauR2w8kjEqz0KsJ9wg4WSc6If/hm"
    "CcepLl3az01cEhKLm7TnHAYlJqNybKqxuHrxKuKLJMHpb8P8J0WXf348vRw8P17Yez7L4T"
    "f4jfcI3+L8qY9X54TfJl0b/pfajKOtj9l8qsPBfrRTljUm5T8nL7m/Py1hN+F0alB1GP/a"
    "BBaExaUuwWG3YLr5n5lJQUcTGHjotxlyuslDYLckrKisE88GDODXux9iAaorwEQyWvzaTk"
    "juTtg9d+b0ZwRCfKEYmYsZMY2EzM2D6+/KElY9gGzo8RJFvyfew7UNqHc1Wyj59DWyRTjJ"
    "xbYbDOTpIqHuc3/DRNrlgURlc/u2KdOLr2xH01yKzIz5FCRpifRRuZ4cS3VFWgiB1pvVq4"
    "hgUtlspQQkCu0bVNY4ASxG8OT9ykhcK4oZDbLsuS+Gf201JWuHHevoIGRBSRSJnYAtRFys"
    "S2p0wUNuxJmDr5cQ7t8DceJ9GzIZYh1AG2j2Q4urTmadMmOWVaFsUQauj5amusvpdrrLHN"
    "sFlX/UzTYISxCO46WK0DkpjKDnzJg882/Pa/iRxVxtrCmbxhYGANJau67qLBzWEPpQrq/t"
    "75EkopP0ln5KrG7p2UOs7d+1W+c5ACU5jUZhOixbltjsP10asCaa8Y0Z7ID7R1fiCRxEYk"
    "sRG+apHEpmUrRiSxOaU1I8ic0yRzREDCSQxsbj7/dpB0x/hSQIaiq+JC353vvGbujxZReM"
    "mgQArStmgc4RtZOTEEFUjeKELg1Sne116Sr0bwbkXa/hq+lHOWw9myz87LKNsnvtZGwna6"
    "NoGlTNegb8nSdG31ejoqkgf6W3RlGga+UiH+CAyAii50APAnXU1GRZqGiiyli/43gExqoS"
    "L8p28iSUsG6BNzYGAR0FN1/Nui1XTccgeqWcr38F2aOuhnbfXxjYE2QAKybGr8/agUvilQ"
    "Je5FKom7K24OSZDbkR7iT+i9cT9IDyxFBVGnTaiocW97oE9+h316c3cv/U+nJ0XypjWXf8"
    "IdRd3poWvDmpPOajpBDFB0QhSj3hpAx3dTFIIXAxnLqfSmpolvN1BJb/Uu644B8JODnma9"
    "+X30/790+hK+RMbZT6z3mgbOE3eNR6ur6fQepL8DDJ+pWoDdKryJ1ZnjvsyVbtThsKvpoQ"
    "txx91SBjFkSlcndVVuZm3B/e/vxTrB+4eQ12X8BdefoaaFEXwStpIwgk90YJnmXdt0Q6r2"
    "fL6lpfKA22jnCO8m1Lmmuk3xyNG1GVDFirbPqlTRsvO0ND3WgGSi1Wg6yNWHKwtTzRUVWF"
    "g9U0BUE+uhVOE1sNaEtGf6SjrRJzUgLeA8kKIbheqqCbA+asxNEOpTEtNn5QHRZyHWspGM"
    "Fetg8R/cjq4y3TKl/KphNzKmQPMcFcVhxmSkaqtxvJTQ4SrrcAv30XZqUnq8zDESeruPMF"
    "gZvv/NRdvbk+E/1YEyI3ikunFHrxTrq5cE++ppUP9a5sXuJ6XnLvIyGv/2ML7NB5AJpJVO"
    "GwTSf6SF7bebOs5DDj9tQrPMZBlNJxRNqYy4gXSWUdufud8QCDkn1IYshkxMpDBMBcOs/W"
    "AGngznEc6iTbEmvEVN7BFqdmy1GGl25FCompioBU2IkIoDh1QcYdorZIjZz7QvqfcoLyfX"
    "n0cXEq0wdW5G7ycXxPJJm1yVfLhVXLjFHtz00Yq70WDdcGJirRx4rSwMdFpQS6bBQKaFxX"
    "CKaDLBtwoiXQxs1WgykQj1AElu+GiTLd8G5cNb2od21XCh1GSqne1m996OH/8FD0fTKA=="
)
