-- 로컬 pytest용 test DB 생성
-- CI는 root로 실행되어 자동 생성되지만, 로컬은 ozcoding 유저 권한으로 CREATE DATABASE가 불가능하여 명시 생성
CREATE DATABASE IF NOT EXISTS test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL ON test.* TO 'ozcoding'@'%';
