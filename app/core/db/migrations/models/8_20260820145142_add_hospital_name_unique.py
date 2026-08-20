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
        ALTER TABLE `hospital` ADD UNIQUE INDEX `name` (`name`);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `hospital` DROP INDEX `name`;
        DROP TABLE IF EXISTS `ocr_document_text`;
        DROP TABLE IF EXISTS `ocr_job`;
        DROP TABLE IF EXISTS `ocr_result`;
        DROP TABLE IF EXISTS `visit`;
        DROP TABLE IF EXISTS `ocr_field_candidate`;
        DROP TABLE IF EXISTS `ocr_field`;
        DROP TABLE IF EXISTS `ocr_job_document`;
        DROP TABLE IF EXISTS `patient`;"""


MODELS_STATE = (
    "eJztXW1z2rgW/isa7pd2JtsLBALJ/UQIaWkTyBDS3btNhxG2AG+NzfolaWan//1K8rssG5"
    "tXm6vJDMGyjiw/ejvn0dHhn8pSl5FqfuggQ5EWlSvwT0WDS4S/MHfOQAWuVkE6SbDgVKVZ"
    "YZBnaloGlCycOoOqiXCSjEzJUFaWoms4VbNVlSTqEs6oaPMgydaUv200sfQ5shbIwDe+fc"
    "fJiiajn8j0Llc/JjMFqXKkqopMnk3TJ9bbiqb1NeuWZiRPm04kXbWXWpB59WYtdM3PrWgW"
    "SZ0jDRnQQqR4y7BJ9Unt3Pf03sipaZDFqWJIRkYzaKtW6HUzYiDpGsEP18akLzgnT/mtXm"
    "u0Gu3zi0YbZ6E18VNav5zXC97dEaQIDMaVX/Q+tKCTg8IY4PaCDJNUKQZedwENPnohEQZC"
    "XHEWQg+wNAy9hADEoOPsCMUl/DlRkTa3SAevN5spmH3tjLqfOqN3ONd78jY67sxOHx+4t+"
    "rOPQJsACQZGjlAdLOXE8BatZoBQJwrEUB6LwogfqKFnDEYBfHz43DABzEkwgD5pOEX/CYr"
    "knUGVMW0vhcT1hQUyVuTSi9N8281DN67+84fLK7du+E1RUE3rblBS6EFXGOMyZQ5+xEa/C"
    "RhCqUfr9CQJ7E7el1Pyhu/tawv2RSowTnFirwxeT93EXky6YQeW1xoeurSYuMcZrFWlmtl"
    "fkKLy2W9fn7eqlfPL9rNRqvVbFf9VSZ+K225ue5/JCtOpG+uX4LQEipqnrnTFyjn7NnIMn"
    "k2kufORmzqXEBzgeTJCprmq25w+msylhzRcqJaq7ezrEn1dvKaRO5FgaX/c6Dp5S8nhPUs"
    "HbOe3DHrsY6J31h2pvc4gj3NXlIU+7hKUJNQDM1A+sh4Vu47d70rQD6ftduec+X8r2yA80"
    "UGmC8SUb5gQZ4qhrWQ4Vsc5hsMDr+jhmUYcPE8jSxliT6QL8Xstin43XTGPQafFX47NMG9"
    "bZrUFfkYsXLlHNS1WpZpsZY8K9bY/qaYE6yEKS+cmfFa11UEtQTFKCzHgDnFgvtC01eadt"
    "3XrofDu4iKft1nlJ/B0/11D8NL0cWZFCuiE0UxlZcKxw5fC6kndkBE82rfR4FUhaY1UfU5"
    "D9Qbd47joxqVTJseyZcMILs9sBgz5Lh/33scd+4fIjiTeZPcqdPUNyY1thz5hYDf++NPgF"
    "yCP4eDHmuE+vnGf1ZInaBt6RNNf8XdNvzaXrKXFCUGDESgnUAON5DekFHJHTTkMWZz/A7y"
    "UFPf3H5UkpZ1u3xqw9orecOGjUqKhj1qw9LKF4RleoCWQhhBDtHk3TpL45pWoUzr2KZKB0"
    "iqoinSb6akr5AMXGGgyPhTsd6AiXVLnD59A1BVwYtiKpb5gbUYtiiGw2p9qyx0c6VYUJ04"
    "RJR/6RaLG63yneG+YkKeHUvNhAk1BLBILBvVkJ3SuNSZ98i8FFpUTlBpmak0pn2yI8427F"
    "rICzKHHhB1DsqhIRVDO4Vy44uX07xsZuGMmsmcUTPGGf1/cW67xy80Z3O1qhRCyJc6dUqo"
    "fLxk5WnwZTD8nW4JMmpIlJB81sJk5XD8qTe6AvTfs+aWcQXCheXssGnTp9dfW4ndtcX2Vk"
    "eFyDHcfYFyjvfdc+zm0pyQR3L3zlPZI0ZSEEiJwG5kpPLkBZl0ZDKJNIq+Ig2i29aGjcrK"
    "i0YtQKO6I23iUUNTzn5YmgWUXMZGxtDhG/Q4tpAgZ0+CwxPk7Ik2bF5yNuQZTHlGziTqyt"
    "1+GSEVWnxPYJdz/UrKKGYL//K6rZcaBmtf9LSDB4ec9oFKpqZf/CxriemhhhhOGWmSbmM9"
    "1ABTpOraHCMDLB2gn7gc9Q1gk8qjneP89NalrXe+jDHL9GWdOYQSzyFePnwrkXmmmXKzoG"
    "EpwToL1rkAqAco43pZupEb44iYUGXTAEYraFhLLo+SzEdFpTYipY4A8P6Pc4Sm6Zz6Y1Sy"
    "nPpjSfTFTNa1syqa9nIJDY5RPUY/U5fTkGBJRkda4/X+GEfaLXYqx2+7u+Hgo5edParDnd"
    "k1nbdlkwwvIybA5YJrWtCyOWZMtq2eQPqAWz3d4f3DXW/cu+Fs9jx2P/Vunu56N1fA//qs"
    "+RJXwP+KUzuDbo9m9b5tsuFzmWFtuExcGS5jGz4q1DQ8u5uWzjkwmbpfwYqKDQvBxZ0gZS"
    "O4uBNtWLfyh/ePK0g7Hsyqi/GdMcjjeN/qBlLm2hf0FtMI+NxmyJ+0eFgnsZs42YCvPmHG"
    "9CT8kvjVkLO+jHDnHvW7GM8sbLEuGZO/9OmWfPFQMj7r03JBulfCGANyo0s2oReIIVDhUM"
    "dslrM0Epk0k+zmnlhe9rWE8hgtV3iQGW9g2B0BIvcfoFhgaZsWmCKwsg1ce/CqWAtgLRDA"
    "zzf0F5xi6rYhIeA9Mc4t77Jgrjc0eWE8X5MO4DzbeXXc31kn6EQuOYZZ7vk6qQTBMWfmmM"
    "Mtlwt7RlAslms4ZreTEnxiOGezmWOFHPv0du9+dAXwx7P2gBe17qj/MO4PB1cgfPWs3XWu"
    "Jzjh6W58BYLvm1jMtXqmSAQpgQhYo5ms2d5snZUeCssIbojLDXkQTZx1ZgP7il+CcAgTR0"
    "aFwSyYENGwWZmQQE3fSLmOiAoVLwcfErWPtqREsCk68ssqHuBZSZFYj4rwIt3OY7dz08tG"
    "i7hp8Q6djxTxe35RtYaDsyK3MTOdg1Y6DzLzs2U46Y1z2JJlk3PYL1C1kcNJDLujMyDpho"
    "EkkvUMQE3G19pMMZa0VQHlKzQybHgHv3dUagbmI9T9chEfjtwmc3JYUhAdmYmOEMgxyJO9"
    "kKJS5Twad9HIYDZfNJIDozVYsxkbZmRcY62Pjq481jNHVBjRXCPanag2AZkjKkBOABnP/j"
    "JytS/G7kGSsoRqEsRhQdbscSQ/uCWUDembXrd/37l71zxrML4R4SiqjFtiUrzzZKfwxHDn"
    "e7QsalsvY1tGjI+EpnN1D8TTAtaEp4uICoedKLRYMVXwI/IfVmQEhVt3yp6Gj1V+zogRFb"
    "TusWldbzLJPWBYSTFi0s70+mBtwJ8zsmLMHHvMiK2QU2DMxVbIiTZsbCvkWK5GhZh5j7Pg"
    "id0nsftUtt2nxCljN0iyLqWFmymywsmbDCOIPvbGYPB0d5dtQ0+CmqyQpXFHm3pdr7xydd"
    "qDbO8F2KTs80UAzLDhN5EiAhm2/gyo/UAygKqFDA2SH7AABrIwGMQzeYE0Gu+Clg0W0ARL"
    "jLuyUkkmKGNsuRGfd1Jm4rafv7NJHrPJfp+P0RY7f2wZYg8w8x5gAF3+LZW4aFl2A8WeSg"
    "GQ3mRPhc4yMQgf8durifOEJ1Mydfm83rrwpwJykTb4HzGQd5y4ovTsSu4IzYzYliGai9Xp"
    "4hGaFXNiYhWNbA7n33QKS4o9J3FI/ARpozgfeEhvrYI0ZlEoDF/f3t7uzurpWSBb8IxDYI"
    "S7U17v2T2bluSAMd+edI8epxuRf7mZcv86EDngiltGsqkH50w3qI1HYySt/02gdcIbhFgM"
    "QtuEJvbvJNiiH2kyfCPVasSgcGedZIfFqNRuTJS9G4d7cVcUcRWPS/6XMEDUw2jY7T0+9g"
    "cfK/F5J7hJTrh635NiRN12+jRClPOfnYeyjINatuCBKbEDYyGiDJ3oRZw2Sbcpw3KH6/PV"
    "rTv8LoxKA+Eam5sEvmclxWyxZrYwNvw5kIik8Is5tl+MvlwRpXQzJ6eorGjMIzfmDCqqbS"
    "DcRHK+YzOMXElOH+z73IzgiE6UIxI+YyfRsDGfsUP83EFB2rAInJ9PkGzJ95Xw51HOGLIv"
    "3Ie2CB/obW65zjo7CSPouTCVC+B8njVhA5DvRufhNtTQWMcfmdDL7EdXHL+vXxsxwX4fSW"
    "SEw71oLTPsd+CMFLEG7JWqQxnJfihDgIG08bXi+ABFiF8OT7xJCYl+Qy63nRYl8Vv8bior"
    "vHHcvoQChBeRCJlYANRFyMSih0wUNuxJmDp8P4di7DeWk+hZ48vg6gDbezKULpA3a9pEu0"
    "zBvBhcDZ2vtgbqe7rGGtgM63XVr04YDNcXQbetlW3RwFSKZQIDvSjo9d+RGFXQlkkkb2RB"
    "oqHEVdddFLje7SFVQT3cmS+hlIY76YRe5Zi9o1LlnL338it7DjCJQW3WIZoc26YcWx/NLJ"
    "A2kxFtivhAW8cHEkFsRBAbsVctgtgUbMSIIDanNGYEmXOaZI5wSDiJhuXG8y8GSVfGQwEx"
    "ii7LFvru9s5zxv4oEIUXdQp0QNoWjRKeyOL4EGQgeT0Pgb1TvPseknsjeLcibT+5h3IqHM"
    "7Wv3eWRtkuwrnWErbP9lSSa8+2dCFXwbMtN5ttnFS9bH/AV1MIyVUDkVvSpdTAF21JInfO"
    "W1Wc1GrhJLl2jr9DqUpz4STy72KKJeWqhO9MLyERkZqNNvmUnWxtUnIdNeKU7/Gr9KzhP1"
    "u+IA+WWpdYoFqdtsLPc6TIQ6UGCB2kAqGnkuKwBH0crSG54zyb1IPWQK41JK/SU1RrBLVt"
    "Shf0063Tu4cR+Fe9CTz5qTyrvicVxdVp4msoz2hlW22KmOSg46Lo1RZKbfK0Wo3i5YNM5B"
    "rOQ6dT8rjLBq1t+9yvDpTIm0vNlvzuS++/v9UvALnExtl7v/atlnQWeWrQWuettvMMWt9L"
    "At+0IUv+o9yHyPUZqcusdu5V2K0q23Qu7qRatcsAstp5m+ZthHrWFtz/4Q7WCd7fhTwv47"
    "9brv+wSuBemH5hAp+EpSRM4BNtWF/vzm24YUV7NtvSTnkkZRSzhXfj6JxT2Xbw4GjaPlDJ"
    "arbpZ8miY/N0tHag/1SpTtNqS1xtOLOwo7fiBJkoZzXJy0m0UEfdhURnwrqzcyCdapMtCa"
    "hoZgHvQa6yOpWINgpnU8nVpoCvzVYvqTaLiI6NZeRAAwv+kXLaDV+zZFTfhluNmCGweYSK"
    "ZCdj2lK5lbiwlNDgMmtwqj5XtJyEXlimjJrc7v0LVtA0X3U8vS2gucgDZUywpF4w9XYmT9"
    "92iqtvmwX1uMZF+Z1eDF3lxTP+/Dgc8AH0BRgEnzT8Zt9kRbLOgKqY1vdi4pmCH3nniH4Z"
    "izTKBhVlFEdSABtpVDEn+isGgbNOrYlk6IuJMIaMQ4xtWhNpAbU5mnhTY054k4o4INT+4l"
    "VgpP2Fx4FqE0M1oQjhVnFkt4oShr7C5pjy4tSFOUvZHfe/9q6Ak+FZu+vdjq+o/cMaXpn2"
    "cbNs4ybv4rILLKnGBuMmJCbGypHHigrxauHYMxs0JCssmlN4lAnWVdDpomGzepSJYKhHCH"
    "QT9jjZ8kRo2MWleGhndRliOlPuiDe73/P49T9/F4GI"
)
