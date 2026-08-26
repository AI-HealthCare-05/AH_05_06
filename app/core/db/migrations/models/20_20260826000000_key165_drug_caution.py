"""KEY-165 — 처방 세트 카탈로그와 주의·응급 문구 마스터 표를 추가한다.

**이 파일의 SQL 은 손으로 썼다.**

새 표 둘(prescription_set, drug_caution_content)을 만들고
기존 guide_section 에 근거 버전 추적 칼럼(drug_caution_content_id)을 더한다.

approved_key 설계(KEY-180 §3):
  MySQL 8.0 은 조건부 유니크 인덱스를 지원하지 않는다. "승인 상태일 때만 하나"
  제약을 nullable unique 칼럼으로 표현한다. 승인 시에만 값을 채우면 NULL 은
  유니크 인덱스에서 여럿 허용되므로 비승인 행은 제약에 걸리지 않는다.

MODELS_STATE 주의:
  이 마이그레이션은 수작업으로 작성했으므로 MODELS_STATE 가 실제 모델 상태와
  다를 수 있다. 이 파일을 병합한 뒤 `aerich migrate` 를 실행해
  다음 마이그레이션에서 사용할 올바른 MODELS_STATE 를 확보해야 한다.
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `prescription_set` (
            `prescription_set_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `name` VARCHAR(100) NOT NULL UNIQUE COMMENT '처방 세트 이름 — 8종 중 하나',
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
        ) CHARACTER SET utf8mb4 COMMENT='처방 세트 카탈로그 — KEY-165';

        CREATE TABLE IF NOT EXISTS `drug_caution_content` (
            `drug_caution_content_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `section_key` VARCHAR(9) NOT NULL COMMENT 'CAUTION: caution\nEMERGENCY: emergency',
            `body` LONGTEXT NOT NULL,
            `source_name` VARCHAR(200) NOT NULL COMMENT '자료명',
            `source_org` VARCHAR(100) NOT NULL COMMENT '발행기관',
            `source_url` VARCHAR(500) NOT NULL COMMENT '출처 링크',
            `verified_at` DATE NOT NULL COMMENT '확인일',
            `content_version` VARCHAR(50) NOT NULL COMMENT '버전·기준일',
            `source_grade` VARCHAR(1) NOT NULL COMMENT 'A: A\nB: B\nC: C',
            `approval_status` VARCHAR(10) NOT NULL DEFAULT 'draft' COMMENT 'draft: draft\napproved: approved\ndeprecated: deprecated',
            `approved_key` VARCHAR(30) NULL UNIQUE COMMENT '승인 상태일 때만 채움: {prescription_set_id}:{section_key}',
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `prescription_set_id` BIGINT NOT NULL,
            CONSTRAINT `fk_drug_cau_prescrip_a1b2c3d4` FOREIGN KEY (`prescription_set_id`) REFERENCES `prescription_set` (`prescription_set_id`) ON DELETE RESTRICT,
            KEY `idx_drug_cau_set_section_status` (`prescription_set_id`, `section_key`, `approval_status`)
        ) CHARACTER SET utf8mb4 COMMENT='처방 세트별 주의·응급 문구 마스터 — KEY-165';

        ALTER TABLE `guide_section`
            ADD COLUMN `drug_caution_content_id` BIGINT NULL
            COMMENT '생성 시 사용한 DrugCautionContent 버전 — KEY-165. null 이면 범용 문구 또는 caution/emergency 외 섹션';

        ALTER TABLE `guide_section`
            ADD CONSTRAINT `fk_guide_se_drug_cau_e5f6a7b8`
            FOREIGN KEY (`drug_caution_content_id`) REFERENCES `drug_caution_content` (`drug_caution_content_id`) ON DELETE SET NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `guide_section`
            DROP FOREIGN KEY `fk_guide_se_drug_cau_e5f6a7b8`;

        ALTER TABLE `guide_section`
            DROP COLUMN `drug_caution_content_id`;

        DROP TABLE IF EXISTS `drug_caution_content`;

        DROP TABLE IF EXISTS `prescription_set`;"""
