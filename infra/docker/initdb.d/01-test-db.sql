-- 로컬 pytest용 test DB 생성
-- CI는 root로 실행되어 자동 생성되지만, 로컬은 ozcoding 유저 권한으로 CREATE DATABASE가 불가능하여 명시 생성
CREATE DATABASE IF NOT EXISTS test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL ON test.* TO 'ozcoding'@'%';

-- 자리를 나눈 실행이 쓰는 DB — `test_1`, `test_2`, … (KEY-282)
--
-- pytest 두 실행이 같은 이름을 쓰면 늦게 시작한 쪽이 먼저 돌던 쪽의 스키마를
-- 지운다. `app/tests/conftest.py` 가 `TEST_SLOT` 과 xdist 워커 번호로 이름을
-- 가르는데, **이름만 갈라서는 로컬에서 안 돈다** — 위 주석대로 앱 유저는
-- CREATE DATABASE 를 못 하고, 권한은 이름마다 따로 있어야 하기 때문이다.
--
-- 그래서 이름 하나가 아니라 **패턴**에 준다. `\_` 는 밑줄 그 글자를 뜻한다
-- (안 쓰면 `_` 가 「아무 글자 하나」가 되어 `tests` 같은 이름까지 걸린다).
--
-- 이걸 넣기 전에는 `pytest -n auto` 도 로컬에서 안 돌았다 — `test_gw0` 을
-- 못 만들어 전건이 setup 에서 죽었고, CI(root)에서만 돌아 아무도 몰랐다.
GRANT ALL ON `test\_%`.* TO 'ozcoding'@'%';
