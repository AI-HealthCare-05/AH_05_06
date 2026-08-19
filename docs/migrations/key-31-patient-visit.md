# KEY-31 Patient·Visit 마이그레이션 검증

## 범위

- `patient`는 병원별 차트번호를 유일하게 관리한다.
- `patient.gender`는 Notion S2-1 계약의 네 값(`FEMALE`, `MALE`, `OTHER`, `UNKNOWN`)을 저장하며 미입력은 `UNKNOWN`이다.
- `visit.patient_id`는 `patient.patient_id`를 참조하며 한 환자에 여러 진료 건을 허용한다.
- `visit.planned_stop=true`는 계획된 처방 중단을 뜻하며 후속 확인·소진·재진 알림과 이탈 판정에서 제외하는 서비스 규칙의 근거다.
- 환자 검색과 방문 이력 조회를 위해 모든 업무 인덱스의 선두에 병원 또는 환자 식별자를 둔다.
- `hospital_id`, `doctor_id`, `sms_consent_updated_by`는 `Hospital`·`Staff` 모델이 확정되기 전까지 bigint 경계 필드로 유지한다. 기존 단일 병원 `User` 모델에 잘못 연결하지 않는다.
- `visit.status`의 기본값은 진료가 끝난 뒤 등록하는 S1 흐름에 맞춰 `COMPLETED`로 둔다.
- 차트번호는 EMR 식별값을 보존하되 DB의 `utf8mb4_unicode_ci` 유일 키에 따라 대소문자만 다른 값을 같은 번호로 취급한다. 대소문자 차이로 환자 식별자가 중복되는 것보다 충돌로 거부하는 쪽을 선택한다.
- 차트번호의 빈 문자열·공백 문자열 거부와 trim은 KEY-26 후속 DTO 검증 책임이다. `models/`에 업무 검증을 넣거나 생성 마이그레이션 SQL을 손으로 고치지 않는다. API 구현 전까지 ORM 우회 입력은 합성 시드 검수 절차에서 비어 있지 않은지 확인해야 한다.

현재 저장소에는 `Hospital` 테이블과 로그인 직원의 `hospital_id`가 아직 없다. 따라서 `patient.hospital_id`와 `visit.hospital_id`는 KEY-73에서 실제 Hospital·Staff FK를 연결하기 전까지 독립 bigint 경계 필드이며, 이 PR만으로 로그인 주체에서 병원 값을 얻는 흐름까지 증명하지 않는다.

현재 모델과 동결 후보 계약 안에서 다음 규칙을 적용한다.

- `visited_at`은 `use_tz=true`로 UTC 저장한다. 표시와 날짜 그룹화는 `Asia/Seoul`을 사용한다.
- ORM을 거치지 않는 시드·운영 SQL은 세션 시간대를 UTC로 설정하거나 UTC 값을 명시해야 한다. `CURRENT_TIMESTAMP`와 애플리케이션 시간이 섞이지 않도록 KEY-13 시드 검증에서 확인한다.
- `visit.hospital_id == patient.hospital_id`는 KEY-26 계약대로 서비스 계층에서 검증한다. DB 복합 FK는 Hospital·Staff 모델과 병원 FK가 생기는 KEY-73에서 모델 관계로 먼저 정의한 뒤 Aerich가 생성해야 한다.
- 같은 현지 날짜의 중복 진료는 KEY-26 계약대로 서비스 계층에서 `409 VISIT_ALREADY_REGISTERED`로 처리한다. DB 동시성 방어를 추가하려면 `visited_on` 저장 여부를 계약에 먼저 확정하고 모델 변경에서 Aerich 마이그레이션을 생성해야 한다.

`docs/models-layout.md` 규칙에 따라 기존 Aerich 마이그레이션 SQL을 손으로 고치지 않는다. 위 두 DB 강화안은 모델·계약 없이 이 PR의 생성된 SQL에 직접 추가하지 않는다.

Aerich가 생성한 `RUN_IN_TRANSACTION = True`는 그대로 유지하지만 MySQL DDL은 자동 커밋되므로 원자적 롤백을 보장하지 않는다. 적용 중 `visit` 생성이 실패하면 `patient`만 남을 수 있으며, 운영자는 적용을 중단하고 생성된 테이블과 Aerich 버전 상태를 확인한 뒤 승인된 복구 절차로 재실행해야 한다.

`PatientGender`는 직원 계정의 기존 `Gender`와 의도적으로 분리한다. 직원 계정은 현재 `MALE/FEMALE` 계약이고, 환자 데이터는 외부 입력을 위해 `OTHER/UNKNOWN`까지 필요하다. 기존 `users` 스키마를 KEY-31에서 확장하지 않는다.

테이블명 `patient`와 `visit`은 `docs/models-layout.md` 및 합성 데이터 정본의 명칭을 따른다. 기존 `users`의 복수형 관례에 맞추기 위한 이름 변경은 동결된 환자·진료 계약을 깨므로 이 PR에서 수행하지 않는다.

클라이언트가 `hospital_id`를 지정하는 API는 허용하지 않는다. 환자 이름 검색은 `(hospital_id, name, birth_date)` 인덱스를 사용할 수 있도록 앞부분 일치(`name LIKE '김%'`)를 기준으로 구현하며, 포함 검색이 필요해지면 별도 검색 인덱스를 설계한다.

## 적용과 롤백

MySQL이 실행 중이고 저장소 환경변수가 설정된 상태에서 실행한다.

```bash
uv run python -m aerich.cli upgrade
uv run python -m aerich.cli downgrade --version 1 --yes
```

운영 또는 공유 DB에서는 롤백이 `visit`, `patient` 테이블과 데이터를 삭제하므로 백업과 변경 승인 후 수행한다.

## 로컬 검증

```bash
uv run pytest --confcutdir=app/tests/models app/tests/models/test_patient_visit_models.py
uv run ruff check app/core/db/databases.py app/models app/tests/models
uv run ruff format --check app/core/db/databases.py app/models app/tests/models
```

테스트는 모델 등록, 환자 1:N 진료 관계, 병원 범위 인덱스, UTC 저장 설정, 마이그레이션 생성·롤백 순서를 확인한다. MySQL 8.0 임시 환경에서 전체 테스트 `160 passed, 3 skipped`, 마이그레이션 적용, 환자 1:N 진료, 병원 범위 차트번호 유일성, 환자 삭제 제한, 롤백 후 테이블 제거, 재적용을 확인했다.
