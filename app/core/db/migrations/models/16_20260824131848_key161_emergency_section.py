"""KEY-161 — 안내문에 다섯째 갈래 `emergency` 를 더한다.

**표도 컬럼도 바뀌지 않는다.** `section_key` 는 `CharEnumField` 라 DB 에서는
`VARCHAR` 이고, 길이는 가장 긴 값이 정한다 — `medication`(10) 이 그대로 가장
길므로 `VARCHAR(10)` 도 그대로다. `emergency` 는 9 자다.

바뀌는 것은 **컬럼 주석에 적힌 열거값 목록**뿐이다. 사람이 스키마를 읽을 때
쓰는 것이라 코드와 어긋나면 다음 사람이 「넷뿐이구나」로 읽는다.

`guide_event.section_key` 도 같은 열거를 쓰므로 함께 고친다 — 수정 이력이
`emergency` 를 가리킬 수 있어야 한다.

---

**이 파일의 SQL 은 손으로 썼다.** `aerich migrate` 가 만든 것을 그대로 쓸 수
없었다. 14 번의 `MODELS_STATE` 에 표 여섯(`guide_document` · `guide_event` ·
`guide_section` · `patient_number_correction` · `prescription` ·
`prescription_item`)이 빠져 있어, aerich 가 그 표들이 **없다고 보고 다시 만드는**
SQL 을 뱉었다. 그대로 뒀다면 `downgrade` 가 살아 있는 표 여섯을 지웠을 것이다.

아래 `MODELS_STATE` 는 aerich 가 현재 모델에서 계산한 것을 그대로 둔 것이라
**열아홉 표가 모두 들어 있다** — 다음 `aerich migrate` 는 정상으로 돌아온다.
빠진 경위 자체는 이 일감 밖이라 PR 에 따로 적는다.
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `guide_section` MODIFY COLUMN `section_key` VARCHAR(10) NOT NULL COMMENT 'MEDICATION: medication
CAUTION: caution
EMERGENCY: emergency
LIFE: life
MESSAGES: messages';
        ALTER TABLE `guide_event` MODIFY COLUMN `section_key` VARCHAR(10) COMMENT 'MEDICATION: medication
CAUTION: caution
EMERGENCY: emergency
LIFE: life
MESSAGES: messages';
        ALTER TABLE `guide_section` COMMENT='안내문 다섯 갈래. 한 갈래가 한 행이다.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `guide_section` MODIFY COLUMN `section_key` VARCHAR(10) NOT NULL COMMENT 'MEDICATION: medication
CAUTION: caution
LIFE: life
MESSAGES: messages';
        ALTER TABLE `guide_event` MODIFY COLUMN `section_key` VARCHAR(10) COMMENT 'MEDICATION: medication
CAUTION: caution
LIFE: life
MESSAGES: messages';
        ALTER TABLE `guide_section` COMMENT='안내문 네 갈래. 한 갈래가 한 행이다.';"""


MODELS_STATE = (
    "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"
)
