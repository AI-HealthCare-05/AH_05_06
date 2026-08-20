# KEY-47 환자·진료 모델·합성데이터 검수

> 검수일: 2026-08-20
> 기준 브랜치: `develop` (`0cf2f2d`)
> Jira: https://leehee.atlassian.net/browse/KEY-47

## 판정 요약

| 대상 | 판정 | 근거 |
|---|---|---|
| 환자·진료 모델 관계 | PASS | `visit.patient_id` FK, `ON DELETE RESTRICT`, 환자 1:N 진료, 병원별 차트번호 유일 조건 확인 |
| API 필드 계약 | PASS | 자동 생성 OpenAPI와 합성데이터 필드 매핑, 요청 범위 ID 금지 계약 확인 |
| 병원 범위 조회 계층 | PASS | 정상 관계는 반환하고 병원이 다른 환자-진료 관계는 반환하지 않는 단위 테스트 통과 |
| API DB 통합 테스트 | BLOCKED | 로컬 MySQL `root` 계정 인증 실패(1045)로 실행 불가 |
| 합성데이터 관계 | PASS | 시나리오·차트번호 100개 고유, 진료 99건, 모든 진료 담당의가 H1 의사 계정으로 해석됨 |
| 합성데이터 저장 형식 | FIXED | 시드가 전화번호 하이픈을 그대로 저장해 API 검색 계약과 달랐던 문제를 숫자 정규화로 수정 |
| 시드 입력 검증 | FIXED | 전화번호·중복 차트 환자정보·담당의 관계를 DB 쓰기 전에 전체 검증해 입력 오류의 부분 적재 방지 |
| 비밀값·토큰 미포함 | PASS | 저장소 비밀값·민감정보 회귀검사 통과 |
| 실제 개인정보 미포함 | 확인 필요 | 문서에는 독립 생성 합성값이라고 적혀 있으나 생성 원본·절차를 코드만으로 증명할 수 없음 |

## 정상·예외 케이스

- 정상: `SYN-EMS-01` 환자와 진료가 H1 의사 계정에 연결되고 전화번호가 API 계약과 같은 숫자 형식으로 저장된다.
- 예외: 같은 병원 안에 동명이인 의사가 있으면 이름만으로 담당의를 고르지 않고 시드를 중단한다.
- 예외: 같은 차트번호의 환자정보가 행마다 다르거나 담당의가 H1 의사로 해석되지 않으면 DB 쓰기 전에 시드를 중단한다.
- 예외: `visit.hospital_id`와 연결 환자의 병원이 다른 비정상 데이터는 조회 저장소에서 반환하지 않는다. API의 `404 VISIT_NOT_FOUND` 변환은 DB 통합 환경에서 재확인이 필요하다.

## 남은 제한사항

- `patient.hospital_id`, `visit.hospital_id`, `visit.doctor_id`는 현재 DB 외래키가 아닌 bigint 경계 필드다. 서비스 계층은 병원 범위를 검사하지만 DB 직접 쓰기까지 관계 불일치를 막지는 못한다.
- Notion API 명세 상위 페이지는 확인했으나 상세 하위 페이지는 현재 연결 계정에서 404로 접근되지 않았다. 저장소의 `docs/contracts/patient-visit-api-v1.md`와 자동 생성 OpenAPI를 정본으로 검수했다.
- 전화번호는 합성값이어도 실제 가입자와 우연히 겹칠 수 있다. 개발·테스트 환경의 실제 SMS 공급자 호출 차단은 별도 실행 검수가 필요하다.

## 실행 명령

```bash
UV_CACHE_DIR=/private/tmp/key47-uv-cache uv run --python 3.13 --group app --group dev pytest -q \
  --confcutdir=app/tests/fixtures \
  app/tests/fixtures/test_key47_patient_visit_integrity.py \
  app/tests/fixtures/test_key36_fixtures.py \
  app/tests/fixtures/test_field_mapping.py \
  app/tests/models/test_patient_visit_models.py \
  app/tests/contracts/test_patient_visit_contract.py \
  app/tests/security/test_secrets_not_committed.py \
  app/tests/security/test_sensitive_data_regression.py
```

결과: `150 passed`. DB 기반 `app/tests/patient_visit_apis/test_patient_visit_apis.py`는 로컬 MySQL 인증 실패(1045)로 실행하지 못했다.

PR 작성 시 위 실행 결과와 실제 개인정보 출처 확인 필요 사항을 제한사항으로 기록한다.
