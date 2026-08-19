from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `staff` (
    `staff_id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `hospital_id` BIGINT NOT NULL,
    `login_id` VARCHAR(50) NOT NULL UNIQUE,
    `password_hash` VARCHAR(128) NOT NULL,
    `name` VARCHAR(50) NOT NULL,
    `roles` JSON NOT NULL,
    `is_owner` BOOL NOT NULL DEFAULT 0,
    `status` VARCHAR(6) NOT NULL COMMENT 'ACTIVE: active\nLEFT: left' DEFAULT 'active',
    `must_change_password` BOOL NOT NULL DEFAULT 1,
    `left_at` DATETIME(6),
    `last_login_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_staff_hospita_953a91` (`hospital_id`, `status`)
) CHARACTER SET utf8mb4 COMMENT='로그인하는 사람. 직원 개인정보(생년월일·연락처)는 들지 않는다.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `staff`;"""


MODELS_STATE = (
    "eJztWm1z2jgQ/isef0pnchlwbHDyDVJy5SYJnYb2blo6HlkWoIktU0tuyvTy30+S8bsNJp"
    "cG6PDFwatde/fZlXZ5yE/V8x3k0rMeCjCcq5fKT5UAD/EPhZVTRQWLRSoXAgZsV6qCVMem"
    "LACQcekUuBRxkYMoDPCCYZ9wKQldVwh9yBUxmaWikOBvIbKYP0NsjgK+8OUrF2PioB+Ixr"
    "eLB2uKkevkXMWOeLeUW2y5kLIhYddSUbzNtqDvhh5JlRdLNvdJoo0JE9IZIigADInHsyAU"
    "7gvvVnHGEUWepiqRixkbB01B6LJMuA0xgD4R+HFvqAxwJt7yh9bWu7p53tFNriI9SSTdpy"
    "i8NPbIUCJwN1af5DpgINKQMKa4fUcBFS6VwLuag6AavYxJAULueBHCGLB1GMaCFMS0cF4I"
    "RQ/8sFxEZkwUuGYYazD71Ptw9a734YRrvRHR+LyYoxq/Wy1p0ZoANgVSbI0tQFypHyaA7V"
    "arAYBcqxZAuZYHkL+RoWgP5kH86350Vw1ixqQApIMhU/5VXExLm3o/AF2Dn4hXOO1R+s3N"
    "wnZy2/uniOjVzagv4/cpmwXyKfIBfY6uOCynD5ltLwQ2gA+PIHCs0oqv+XW65SVP84oSQM"
    "BMYiUiFvGt2sc9A9NpVV+JFta2FZqobOoq6iS0TQNOQuBMzUkIu11+dQyDX23tQle4qAX4"
    "st014Zm4u4Btfu04LX4DYBvGNtBsG1wNTvUTYeM4/Kat61JXl0pctdWyu/yzMW2JJ3a5Do"
    "QX5pvkXbaOdPkO8XRo6CBaEVekn6mFEjk03zf36S/q3KcLzIBrRc2WJ5KFVP1a28Blpq2q"
    "Nt7Hs9pOnrU6pH5+oWnn512tdd4xDb3bNcxW0tjLS+s6fH/4p2jyuUNhc9cvJKc53gXDzZ"
    "Dvx2n7mqinKLv+DJNKiOvngqzNywwHv7yic6OB0WQyMOoHA6M0FywApY8+b0JzQOfbQFky"
    "PNBhSzObDFuaWT9sibU8qPLvFljG+ocJ4csXZeC7iG4zqiYGx0G1PKhmkcXU8h85CBV9ye"
    "cYAlLzlT5jVoDY5na/CtttGY7m4PZHo5scuP1hoeHcfbztD/jOl0hzJcxq+tBq9qrc7gMS"
    "ehLRIXcMEIiqRqyV9ettfpVP+vh75Et+yu9djYefBpdKpDAhN4Pr8aXioikrDtVNDoZOg3"
    "OhU3ssdIqnghdSZsE5IDNkxd1nyzque8Qr1nQyH+xxSYuEW6CCLHjLwWDYQzXTVWpWPIdX"
    "dmfxhwboroDaj8N4PLwd3I97t+9zCL/tjQdiRZPSZUFaqu3kIcrfw/E7Rdwqn0d3g+LBne"
    "iNP6vCJxAy3yL+owWcbNixOBblUwh4pUfj7jMSWTQ+pnPH6YQBEtA+I5d5yxdI5C7mTR6D"
    "MyLuclVHB5LZVcmvTWy4cJ6Z2LzlMbE7Tax0fk8Y4Y9UkoYlQljKT9fxwSHXoPv1K+M6uu"
    "xITJ5uR0wiD2B3G2IiMThMZkJvwkzo9cyEXmImBNnFz9z6rx/1WFaYHiaqR8rs//9G3qQw"
    "tfrC1EqFySN2qmidZixEar1jPNXb3s3gUhHXCbkeRHfR3z1gIGwcsLkDltWjWnWhZm3WDW"
    "n7WbZr8BNDVvHHBB4dsni12XWlWPNbQsHuMDd1u93kWGzXn4rtYr1haqVU3XZ0bWp35LZK"
    "mDoervifrI2QxmZHBrxAFyZ00fOJpiPLdGSZdn2a/y5kxJFl+k0Tu3uW6ek/M/Dq8Q=="
)
