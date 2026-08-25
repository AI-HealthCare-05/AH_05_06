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
| 환자 수정 | PASS | 정상 수정 확인. **타 병원 환자 PATCH 차단은 검수 전 테스트 공백** — 이번 작업으로 추가·확인 |
| 진료 생성/조회 | PASS | 정상 생성·목록·상세·수정과 같은 날 중복 `409 VISIT_ALREADY_REGISTERED` 확인 |
| 타 병원 차단 | PASS(보강) | GET 상세는 기존 테스트로 확인되어 있었으나 PATCH·검색·진료 목록·진료 생성 4개 경로는 테스트가 없어 이번에 추가 |

## 정상·예외 케이스

- 정상: 합성 환자를 등록·검색·상세조회·수정하고 진료를 생성·조회·수정하는 흐름이 계약대로 동작한다.
- 예외: 같은 병원 안에서 차트번호·같은 날짜 진료가 중복되면 각각 `409 DUPLICATE_HOSPITAL_PATIENT_NO`/`409 VISIT_ALREADY_REGISTERED`로 막힌다.
- 예외(타 병원 차단, 신규): `patient_id`/`visit_id`만 알아도 다른 병원 소속이면 상세·수정·검색·진료 목록·진료 생성 어디서도 노출·변경되지 않고 `404 PATIENT_NOT_FOUND`/`404 VISIT_NOT_FOUND`로 숨는다.
  - `PATCH /patients/{id}`: 값이 실제로 바뀌지 않았음을 `refresh_from_db()`로 재확인
  - `PATCH /visits/{id}`: 상태가 바뀌지 않았음을 재확인
  - `GET /patients?keyword=`: 검색어가 겹쳐도(이름·전화번호) 타 병원 환자는 결과에 나타나지 않음
  - `GET /patients/{id}/visits`, `POST /patients/{id}/visits`: 환자 소속 병원을 먼저 확인해 `PATIENT_NOT_FOUND`로 막힘

## 코드 검토

서비스 계층(`app/services/patients.py`, `app/services/visits.py`)은 모든 조회·수정·생성 경로에서 인증된 `ClinicalActor.hospital_id` 기준으로 저장소 계층(`PatientRepository.get_scoped`/`list_scoped`, `VisitRepository.get_scoped`/`list_scoped`)을 거치며, 요청 본문의 `hospital_id`는 DTO 단계에서 거부된다(`INVALID_REQUEST`). 검수 전에도 운영 코드는 이미 병원 스코프를 일관되게 적용하고 있었고, 이번 작업은 **그 사실을 증명하는 테스트가 없던 4개 경로**(수정 2건, 검색 1건, 진료 목록/생성 1건)를 보강한 것이다. 운영 코드 변경은 없다.

## 추가한 테스트

`app/tests/patient_visit_apis/test_patient_visit_apis.py`에 4개 테스트(5개 차단 경로 검증) 추가:

- `test_other_hospital_patient_update_is_hidden_as_not_found`
- `test_other_hospital_visit_update_is_hidden_as_not_found`
- `test_other_hospital_patient_is_excluded_from_search`
- `test_other_hospital_patient_blocks_visit_list_and_creation` (목록·생성 두 경로를 한 케이스로 확인)

## 남은 제한사항

- `app/tests/patient_links/`는 환자 링크 발급·조회(KEY-90·KEY-151)의 범위라 KEY-52 검수에서 다루지 않았다. 그쪽 검사 15개는 별도로 유지되고 있다.
- 프런트엔드(`frontend/patients.html`, `frontend/js/patients-api.js`)의 환자 선택→진료 이력 화면 동작은 이번 검수에서 확인하지 않았다. Jira 설명이 명시한 범위는 API 흐름과 타 병원 차단이며, 화면 목업-서버 정합성은 별도 작업(예: KEY-86 계열)의 관례를 따른다.
- Notion API 명세서(`docs/qa` 상위 링크)는 세션에서 접근하지 않았다. 필드·계약은 저장소 정본인 자동 생성 OpenAPI와 `docs/api/` 문서로 교차 확인했다.

## 실행 명령

```bash
uv run --python 3.13 --group app --group dev pytest -q \
  app/tests/patient_visit_apis/ \
  app/tests/fixtures/test_key47_patient_visit_integrity.py \
  app/tests/models/test_patient_visit_models.py \
  app/tests/contracts/test_patient_visit_contract.py \
  app/tests/security/test_secrets_not_committed.py \
  app/tests/security/test_sensitive_data_regression.py
```

결과: `70 passed`.

전체 회귀 검사:

```bash
uv run --python 3.13 --group app --group dev coverage run -m pytest app -q
uv run --python 3.13 --group app --group dev coverage report -m
```

결과: `967 passed, 12 subtests passed in 186.95s`, `TOTAL 9352 statements, 433 missed, 95% coverage`.

정적 검사:

```bash
uv run --python 3.13 --group app --group dev ruff check app/tests/patient_visit_apis/test_patient_visit_apis.py
uv run --python 3.13 --group app --group dev ruff format app/tests/patient_visit_apis/test_patient_visit_apis.py --check
```

결과: 둘 다 통과(`All checks passed!`, `1 file already formatted`).
