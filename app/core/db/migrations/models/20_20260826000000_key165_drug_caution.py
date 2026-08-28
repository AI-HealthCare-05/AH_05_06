"""KEY-165 — 처방 세트 카탈로그와 주의·응급 문구 마스터 표를 추가한다.

**이 파일의 SQL 은 손으로 썼다.**

새 표 둘(prescription_set, drug_caution_content)을 만들고
기존 guide_section 에 근거 버전 추적 칼럼(drug_caution_content_id)을 더한다.

approved_key 설계(KEY-180 §3):
  MySQL 8.0 은 조건부 유니크 인덱스를 지원하지 않는다. "승인 상태일 때만 하나"
  제약을 nullable unique 칼럼으로 표현한다. 승인 시에만 값을 채우면 NULL 은
  유니크 인덱스에서 여럿 허용되므로 비승인 행은 제약에 걸리지 않는다.

MODELS_STATE:
  이 파일의 SQL 은 손으로 썼지만 아래 MODELS_STATE 는 **aerich 자신의 함수**로
  만들었다 (`aerich.utils.get_formatted_compressed_data`). 형식을 사람이
  지어내지 않는다.

  원래 여기 「이 파일을 병합한 뒤 `aerich migrate` 를 실행해 올바른
  MODELS_STATE 를 확보해야 한다」고 적혀 있었는데, 그 후속이 안 됐다.
  그 사이 `aerich upgrade` 가 「Old format」으로 멈춰서 **배포 경로에
  마이그레이션 단계를 넣을 수가 없었다** (KEY-196).

  aerich 는 마지막 마이그레이션 파일 하나만 보고 형식을 판정한다. 그래서
  21 개 중 이 파일 하나가 비어 있는 것으로 전체가 막혔다.
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


MODELS_STATE = (
    "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"
)
