# KEY-52 환자 선택→진료 이력 통합·인수 검수

> 검수일: 2026-08-25
> 기준 브랜치: `develop` (`2c96e55`) 위 `test/KEY-52-patient-visit-cross-hospital-review`
> Jira: https://leehee.atlassian.net/browse/KEY-52 (부모 [KEY-38](https://leehee.atlassian.net/browse/KEY-38), 완료)

## 판정 요약

| 대상 | 판정 | 근거 |
|---|---|---|
| 합성 환자 등록 | PASS | 정상 등록·전화번호 정규화 저장, 같은 병원 중복 차트번호 `409 DUPLICATE_HOSPITAL_PATIENT_NO` 확인 |
| 환자 검색 | PASS | 이름·차트번호·전화번호(하이픈/공백/국가번호/뒷자리) 정규화 검색과 무관 검색어 0건 확인 |
| 환자 상세 | PASS | 정상 조회 및 타 병원 환자 `404 PATIENT_NOT_FOUND` 확인 |
| 환자 수정 | PASS | 정상 수정 확인. 타 병원 환자 PATCH 차단은 `test_endpoint_blocking.py`가 실토큰으로 이미 확인 중이었고, 이번 작업은 서비스 계층 관점의 보강 신호를 겹쳐 두었다 |
| 진료 생성/조회 | PASS | 정상 생성·목록·상세·수정과 같은 날 중복 `409 VISIT_ALREADY_REGISTERED` 확인 |
| 타 병원 차단 | PASS(보강) | GET 상세·PATCH 환자·PATCH 진료·GET 진료 목록은 `app/tests/blocking/test_endpoint_blocking.py`(KEY-153, PR #87로 이 브랜치 시작 전에 이미 병합)가 실토큰으로 확인 중이었다. 이번에 새로 덮은 것은 **검색 키워드 분기**와 **진료 생성(POST)** 2개 경로다 |

## 정상·예외 케이스

- 정상: 합성 환자를 등록·검색·상세조회·수정하고 진료를 생성·조회·수정하는 흐름이 계약대로 동작한다.
- 예외: 같은 병원 안에서 차트번호·같은 날짜 진료가 중복되면 각각 `409 DUPLICATE_HOSPITAL_PATIENT_NO`/`409 VISIT_ALREADY_REGISTERED`로 막힌다.
- 예외(타 병원 차단): `patient_id`/`visit_id`만 알아도 다른 병원 소속이면 상세·수정·검색·진료 목록·진료 생성 어디서도 노출·변경되지 않고 `404 PATIENT_NOT_FOUND`/`404 VISIT_NOT_FOUND`로 숨는다.
  - GET 상세, `PATCH /patients/{id}`, `PATCH /visits/{id}`, `GET /patients/{id}/visits`: `app/tests/blocking/test_endpoint_blocking.py`의 `CLINICAL_ROUTES`가 실제 로그인 토큰으로 이미 확인. 존재하지 않는 자료와 응답이 같은지(`test_the_answer_is_the_same_as_for_data_that_never_existed`)까지 검증됨
  - `GET /patients?keyword=`(신규): 검색어가 겹쳐도(이름·전화번호) 타 병원 환자는 결과에 나타나지 않음
  - `POST /patients/{id}/visits`(신규): 환자 소속 병원을 먼저 확인해 `PATIENT_NOT_FOUND`로 막힘
  - 서비스 계층 관점의 보강: `PATCH /patients/{id}`·`PATCH /visits/{id}`는 값이 실제로 바뀌지 않았음을 `refresh_from_db()`로 재확인(스코프 검사가 먼저 걸려 쓰기까지 도달하지 않는다는 것을 보이는 신호이며, 스코프 자체가 깨졌는지는 위 404 단언이 감지한다)

## 코드 검토

서비스 계층(`app/services/patients.py`, `app/services/visits.py`)은 모든 조회·수정·생성 경로에서 인증된 `ClinicalActor.hospital_id` 기준으로 저장소 계층(`PatientRepository.get_scoped`/`list_scoped`, `VisitRepository.get_scoped`/`list_scoped`)을 거치며, 요청 본문의 `hospital_id`는 DTO 단계에서 거부된다(`INVALID_REQUEST`). 검수 전에도 운영 코드는 이미 병원 스코프를 일관되게 적용하고 있었다. GET 상세·PATCH 환자·PATCH 진료·GET 진료 목록의 타 병원 차단은 이 브랜치 작업 시작 전에 병합된 `app/tests/blocking/test_endpoint_blocking.py`(KEY-153, PR #87)가 실토큰 기준으로 이미 증명하고 있었고, 이번 작업은 **거기에 없던 2개 경로**(검색 키워드 분기, 진료 생성)를 보강한 것이다. 운영 코드 변경은 없다.

## 추가한 테스트

`app/tests/patient_visit_apis/test_patient_visit_apis.py`에 4개 테스트 추가:

- `test_other_hospital_patient_is_excluded_from_search` — **신규 경로.** `GET /patients?keyword=`는 `test_endpoint_blocking.py`가 재지 않는 키워드 분기다
- `test_other_hospital_patient_blocks_visit_list_and_creation` — 목록(`GET .../visits`)은 기존 커버리지와 겹치고, 생성(`POST .../visits`)이 **신규 경로**다. 같은 `get_scoped` 관문을 타므로 한 케이스로 묶었다
- `test_other_hospital_patient_update_is_hidden_as_not_found`, `test_other_hospital_visit_update_is_hidden_as_not_found` — `PATCH` 두 경로는 `test_endpoint_blocking.py`가 이미 실토큰으로 덮고 있어 이 자체는 새 신호가 아니다. `get_clinical_actor`를 갈아 끼운 서비스 계층 관점에서 값이 실제로 바뀌지 않았음을 겹쳐 확인하는 보강용으로 남겨 둔다

## 남은 제한사항

- `app/tests/patient_links/`는 환자 링크 발급·조회(KEY-90·KEY-151)의 범위라 KEY-52 검수에서 다루지 않았다. 그쪽 검사 15개는 별도로 유지되고 있다.
- 프런트엔드(`frontend/patients.html`, `frontend/js/patients-api.js`)의 환자 선택→진료 이력 화면 동작은 이번 검수에서 확인하지 않았다. Jira 설명이 명시한 범위는 API 흐름과 타 병원 차단이며, 화면 목업-서버 정합성은 별도 작업(예: KEY-86 계열)의 관례를 따른다.
- Notion API 명세서(`docs/qa` 상위 링크)는 세션에서 접근하지 않았다. 필드·계약은 저장소 정본인 자동 생성 OpenAPI와 `docs/api/` 문서로 교차 확인했다.

## 실행 명령

```bash
uv run --python 3.13 --group app --group dev pytest -q \
  app/tests/patient_visit_apis/ \
  app/tests/blocking/ \
  app/tests/fixtures/test_key47_patient_visit_integrity.py \
  app/tests/models/test_patient_visit_models.py \
  app/tests/contracts/test_patient_visit_contract.py \
  app/tests/security/test_secrets_not_committed.py \
  app/tests/security/test_sensitive_data_regression.py
```

결과: `110 passed`(`app/tests/blocking/`의 실토큰 차단 검사 포함).

전체 회귀 검사:

```bash
uv run --python 3.13 --group app --group dev coverage run -m pytest app -q
uv run --python 3.13 --group app --group dev coverage report -m
```

결과: `967 passed, 12 subtests passed in 190.44s`, `TOTAL 9352 statements, 433 missed, 95% coverage`. (@iljun-sys 님 확인 기준으로는 `965 passed` — `#109`(KEY-167) 병합 시점 차이이며, 병합 커밋 기준 CI가 최종이므로 그대로 둔다.)

정적 검사:

```bash
uv run --python 3.13 --group app --group dev ruff check app/tests/patient_visit_apis/test_patient_visit_apis.py
uv run --python 3.13 --group app --group dev ruff format app/tests/patient_visit_apis/test_patient_visit_apis.py --check
```

결과: 둘 다 통과(`All checks passed!`, `1 file already formatted`).
