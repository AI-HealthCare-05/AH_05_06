# KEY-31 Patient·Visit 마이그레이션 검증

## 범위

- `patient`는 병원별 차트번호를 유일하게 관리한다.
- `patient.gender`는 Notion S2-1 계약의 네 값(`FEMALE`, `MALE`, `OTHER`, `UNKNOWN`)을 저장하며 미입력은 `UNKNOWN`이다.
- `visit.patient_id`는 `patient.patient_id`를 참조하며 한 환자에 여러 진료 건을 허용한다.
- `visit.planned_stop=true`는 계획된 처방 중단을 뜻하며 후속 확인·소진·재진 알림과 이탈 판정에서 제외하는 서비스 규칙의 근거다.
- 환자 검색과 방문 이력 조회를 위해 모든 업무 인덱스의 선두에 병원 또는 환자 식별자를 둔다.
- `hospital_id`, `doctor_id`, `sms_consent_updated_by`는 `Hospital`·`Staff` 모델이 확정되기 전까지 bigint 경계 필드로 유지한다. 기존 단일 병원 `User` 모델에 잘못 연결하지 않는다.

`visit.hospital_id`와 연결된 환자의 `hospital_id`가 같은지는 후속 환자·진료 API가 인증 컨텍스트에서 두 값을 서버 생성하고 조회마다 병원 조건을 적용해 보장해야 한다. 클라이언트가 `hospital_id`를 지정하는 API는 허용하지 않는다.

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

테스트는 모델 등록, 환자 1:N 진료 관계, 병원 범위 인덱스, 마이그레이션 생성·롤백 순서를 확인한다. 실제 적용·롤백은 MySQL 인스턴스가 있는 통합 환경에서 추가 확인한다.
