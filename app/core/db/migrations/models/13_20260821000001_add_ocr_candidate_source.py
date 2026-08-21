from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ocr_field_candidate`
            ADD COLUMN `source_line` INT NULL AFTER `source_date`,
            ADD COLUMN `ocr_document_text_id` BIGINT NULL AFTER `source_line`,
            ADD CONSTRAINT `fk_ocr_fiel_ocr_docu_candidate` FOREIGN KEY (`ocr_document_text_id`)
                REFERENCES `ocr_document_text` (`ocr_document_text_id`) ON DELETE SET NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `ocr_field_candidate`
            DROP FOREIGN KEY `fk_ocr_fiel_ocr_docu_candidate`,
            DROP COLUMN `source_line`,
            DROP COLUMN `ocr_document_text_id`;"""
