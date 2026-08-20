# KEY-29 hospital.name 유니크 제약

## 범위

- `hospital.name`에 `UNIQUE INDEX`를 추가한다 (aerich 마이그레이션 `8_...`).

## 이유

`seed_staff()`는 `Hospital.get_or_create(name=name)`으로 병원을 조회·생성한다.
`name`에 유니크 제약이 없으면 다른 경로로 중복 row가 생겼을 때 이후 모든 seed 실행이
`MultipleObjectsReturned`로 실패한다.

`hospital.name`은 seed 전용 식별값(`기준의원` · `격리의원`)이며 사용자가 입력하는 값이
아니다. 값이 중복될 의도가 없으므로 DB가 보장한다.

## 적용

```bash
uv run aerich upgrade
```

마이그레이션 적용 전 `hospital` 테이블에 중복 `name`이 있으면 `ALTER TABLE`이 실패한다.
적용 전 `SELECT name, COUNT(*) FROM hospital GROUP BY name HAVING COUNT(*) > 1;`로
중복을 확인하고 정리한다.
