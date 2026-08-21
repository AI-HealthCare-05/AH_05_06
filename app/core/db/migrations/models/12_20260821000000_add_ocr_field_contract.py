from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ocr_field`
            ADD COLUMN `unit` VARCHAR(32) NULL AFTER `field_type`,
            ADD COLUMN `source_line` INT NULL AFTER `corrected_value`,
            ADD COLUMN `is_pending_report` BOOL NOT NULL DEFAULT 0 AFTER `source_line`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ocr_field`
            DROP COLUMN `unit`,
            DROP COLUMN `source_line`,
            DROP COLUMN `is_pending_report`;"""
