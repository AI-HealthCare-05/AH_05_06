# KEY-31 Patient·Visit 마이그레이션 검증

## 범위

- `patient`는 병원별 차트번호를 유일하게 관리한다.
- `patient.gender`는 Notion S2-1 계약의 네 값(`FEMALE`, `MALE`, `OTHER`, `UNKNOWN`)을 저장하며 미입력은 `UNKNOWN`이다.
- `visit.patient_id`는 `patient.patient_id`를 참조하며 한 환자에 여러 진료 건을 허용한다.
- `visit.planned_stop=true`는 계획된 처방 중단을 뜻하며 후속 확인·소진·재진 알림과 이탈 판정에서 제외하는 서비스 규칙의 근거다.
- 환자 검색과 방문 이력 조회를 위해 모든 업무 인덱스의 선두에 병원 또는 환자 식별자를 둔다.
- `hospital_id`, `doctor_id`, `sms_consent_updated_by`는 `Hospital`·`Staff` 모델이 확정되기 전까지 bigint 경계 필드로 유지한다. 기존 단일 병원 `User` 모델에 잘못 연결하지 않는다.
- `visit.status`의 기본값은 진료가 끝난 뒤 등록하는 S1 흐름에 맞춰 `COMPLETED`로 둔다.

현재 저장소에는 `Hospital` 테이블과 로그인 직원의 `hospital_id`가 아직 없다. 따라서 `patient.hospital_id`와 `visit.hospital_id`는 KEY-73에서 실제 Hospital·Staff FK를 연결하기 전까지 독립 bigint 경계 필드이며, 이 PR만으로 로그인 주체에서 병원 값을 얻는 흐름까지 증명하지 않는다.

이 한계와 별개로 데이터 자체가 어긋나지 않도록 DB에서 다음 불변식을 보장한다.

- `patient(patient_id, hospital_id)`를 복합 유일 키로 두고 `visit(patient_id, hospital_id)`가 이를 참조한다. 서비스 계층 버그가 있어도 다른 병원 환자에 진료를 연결할 수 없다.
- `visited_at`은 `use_tz=true`로 UTC 저장한다. 표시와 날짜 그룹화는 `Asia/Seoul`을 사용한다.
- `visited_on`은 UTC `visited_at`에 9시간을 더해 계산하는 DB 내부 생성 컬럼이다. `(hospital_id, patient_id, visited_on)` 유일 키가 동시 요청에서도 같은 현지 날짜의 중복 진료를 막는다.
- ORM을 거치지 않는 시드·운영 SQL은 세션 시간대를 UTC로 설정하거나 UTC 값을 명시해야 한다. `CURRENT_TIMESTAMP`와 애플리케이션 시간이 섞이지 않도록 KEY-13 시드 검증에서 확인한다.

클라이언트가 `hospital_id`를 지정하는 API는 허용하지 않는다. 환자 이름 검색은 `(hospital_id, name, birth_date)` 인덱스를 사용할 수 있도록 앞부분 일치(`name LIKE '김%'`)를 기준으로 구현하며, 포함 검색이 필요해지면 별도 검색 인덱스를 설계한다.

## 적용과 롤백

MySQL이 실행 중이고 저장소 환경변수가 설정된 상태에서 실행한다.

```bash
uv run python -m aerich.cli upgrade
uv run python -m aerich.cli downgrade -v 0_20260204142014_init
```

운영 또는 공유 DB에서는 롤백이 `visit`, `patient` 테이블과 데이터를 삭제하므로 백업과 변경 승인 후 수행한다.

## 로컬 검증

```bash
uv run pytest --confcutdir=app/tests/models app/tests/models/test_patient_visit_models.py
uv run ruff check app/core/db/databases.py app/models app/tests/models
uv run ruff format --check app/core/db/databases.py app/models app/tests/models
```

테스트는 모델 등록, 환자 1:N 진료 관계, 병원 범위 복합 FK, 현지 날짜 중복 방지, UTC 저장 설정, 마이그레이션 생성·롤백 순서를 확인한다. 리뷰어는 수정 전 버전을 로컬 MySQL에서 전체 테스트 160개와 함께 검증했다. 이번 복합 FK·생성 컬럼 변경은 대상 계약 테스트를 통과했으며, 실제 마이그레이션 적용·롤백은 통합 환경에서 추가 확인한다.
