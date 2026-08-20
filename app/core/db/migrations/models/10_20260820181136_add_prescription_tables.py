from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `prescription` (
    `prescription_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `prescription_set` VARCHAR(100) NOT NULL COMMENT '진료 당시 처방 세트 이름의 **스냅샷**이다 — \"자궁내막증 · 비잔 (계속)\".',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `visit_id` BIGINT NOT NULL,
    CONSTRAINT `fk_prescrip_visit_44f5913c` FOREIGN KEY (`visit_id`) REFERENCES `visit` (`visit_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='한 진료의 처방 묶음.';
        CREATE TABLE IF NOT EXISTS `prescription_item` (
    `prescription_item_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(100) NOT NULL,
    `frequency` VARCHAR(50) NOT NULL,
    `duration_days` INT COMMENT '**`null` 이 허용된다. 그게 이 칸의 요점이다.**',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `prescription_id` BIGINT NOT NULL,
    CONSTRAINT `fk_prescrip_prescrip_0339d6c5` FOREIGN KEY (`prescription_id`) REFERENCES `prescription` (`prescription_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='처방 안의 약 한 줄.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `prescription`;
        DROP TABLE IF EXISTS `prescription_item`;"""


MODELS_STATE = (
    "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"
    "13vFl9zOPn/wPkSef1"
)
