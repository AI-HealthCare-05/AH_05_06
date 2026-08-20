from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `hospital` (
    `hospital_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4 COMMENT='병원 하나. 모든 진료 데이터가 이 울타리 안에 있다.';
        CREATE TABLE IF NOT EXISTS `staff` (
    `staff_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `login_id` VARCHAR(50) NOT NULL UNIQUE,
    `password_hash` VARCHAR(128) NOT NULL,
    `name` VARCHAR(50) NOT NULL,
    `roles` JSON NOT NULL,
    `is_owner` BOOL NOT NULL DEFAULT 0,
    `must_change_password` BOOL NOT NULL DEFAULT 1,
    `password_changed_at` DATETIME(6),
    `status` VARCHAR(6) NOT NULL COMMENT 'ACTIVE: active\nLEFT: left' DEFAULT 'active',
    `left_at` DATETIME(6),
    `last_login_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `hospital_id` BIGINT NOT NULL,
    CONSTRAINT `fk_staff_hospital_c53708d1` FOREIGN KEY (`hospital_id`) REFERENCES `hospital` (`hospital_id`) ON DELETE RESTRICT,
    KEY `idx_staff_hospita_953a91` (`hospital_id`, `status`)
) CHARACTER SET utf8mb4 COMMENT='로그인하는 사람.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    # staff 가 hospital 을 참조하므로 자식부터 지운다.
    # aerich 가 만든 순서(hospital 먼저)는 외래키에 걸려 롤백이 실패한다.
    return """
        DROP TABLE IF EXISTS `staff`;
        DROP TABLE IF EXISTS `hospital`;"""


MODELS_STATE = (
    "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"
)
