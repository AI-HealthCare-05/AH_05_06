# KEY-46 인증·RBAC 정상·차단 시나리오 검수

> 검수일: 2026-08-21
> 기준 브랜치: `develop` (`c17afb9`) 위 `test/KEY-46-auth-rbac-scenarios`
> Jira: https://leehee.atlassian.net/browse/KEY-46 (부모 [KEY-37](https://leehee.atlassian.net/browse/KEY-37))

## 판정 요약

| 대상 | 판정 | 근거 |
|---|---|---|
| 로그인·토큰 계약 | PASS | 로그인 응답, HttpOnly refresh 쿠키, access/refresh 수명 및 만료 테스트가 KEY-21 CI에서 통과 |
| RBAC 권한표와 서버 가드 | PASS | 역할 3개·권한 13개·7개 복수 역할 조합을 포함한 RBAC 테스트 149개 통과 |
| 환자·진료 허용 흐름 | PASS | `staff`와 `admin+staff`가 환자 목록 API에 접근하고 `200`을 받음 |
| 환자·진료 차단 흐름 | PASS | `admin` 단독 사용자가 환자 목록 API에 접근하면 `403 FORBIDDEN` |
| OCR 허용·차단 흐름 | PASS | `staff`, `doctor+admin` 허용 및 `admin` 단독·병원 범위 없는 사용자 403 테스트 통과 |
| 알 수 없는 역할·권한 | PASS | 오타·공백·대소문자 변형 역할과 미등록 권한은 기본 차단 |
| 민감정보·토큰 노출 | PASS | refresh token은 응답 본문에 없고 HttpOnly 쿠키로만 전달되며 관련 보안 회귀가 CI에서 통과 |

## 정상·예외 시나리오

- 정상: `staff`는 환자·진료 조회 및 수정 권한을 가진다.
- 정상: `admin+staff`는 역할 합집합의 OR 규칙에 따라 `staff`의 환자 접근 권한을 유지한다.
- 정상: `admin+doctor`는 `doctor`가 부여하는 의료 승인 권한을 유지한다.
- 예외: `admin` 단독 사용자는 의원 운영 권한만 가지며 환자·진료 및 OCR 접근에서 `403`을 받는다.
- 예외: `admin+staff`는 환자 업무를 수행할 수 있지만 의사 전용 안내 승인 권한은 얻지 못한다.
- 예외: 만료되었거나 종류가 다른 토큰, 폐기된 refresh token은 `401 token_expired`로 차단된다.
- 예외: `owner`, `superadmin`, `Doctor`, ` doctor`처럼 등록되지 않은 역할 문자열은 권한을 만들지 못한다.

## 이번 검수에서 추가한 회귀 테스트

`app/tests/patient_visit_apis/test_patient_visit_apis.py`에
`test_admin_plus_staff_keeps_patient_access`를 추가했다. 기존 테스트에는 `staff` 허용과
`admin` 단독 403만 있었기 때문에, 복수 역할 사용자가 단일 역할의 권한을 잃지 않는다는
KEY-46 핵심 정상 흐름을 실제 FastAPI 가드에서 고정했다.

## 실행 결과

```bash
uv run pytest -q --confcutdir=app/tests/rbac app/tests/rbac
# 149 passed

uv run pytest -q --confcutdir=app/tests/auth_apis app/tests/auth_apis/test_token_lifetime.py
# 8 passed

KEY34_SQLITE_TEST=1 uv run pytest -q \
  --confcutdir=app/tests/patient_visit_apis \
  app/tests/patient_visit_apis/test_patient_visit_apis.py
# 12 passed

PYTHONPATH=. uv run pytest -q --confcutdir=app/tests/ocr app/tests/ocr/test_ocr_api.py
# 8 passed
```

KEY-21 구현 커밋 `f7e638c`의 GitHub Actions `ci.yml` #223에서 Ruff, 포맷,
mypy 및 MySQL·Redis를 포함한 전체 테스트가 모두 통과했다. 로컬 분리 실행뿐 아니라
실제 CI 서비스 구성에서도 인증·세션·RBAC 변경이 회귀를 만들지 않았음을 확인했다.

## 제한사항

- 로컬 기본 MySQL 사용자 `ozcoding`은 `CREATE DATABASE test` 권한이 없어 저장소 전체
  pytest를 같은 명령으로 실행할 수 없다. 이는 제품 코드 실패가 아니며, MySQL root
  일회용 서비스와 Redis를 사용하는 GitHub Actions #223의 전체 테스트 성공으로 보완했다.
- 현재 `develop`에 실제 안내 승인 API는 아직 포함되지 않았다. `GUIDE_APPROVE`의 역할
  판정은 RBAC 전수조합 테스트로 검증했으며, 승인 API 병합 후 엔드포인트 수준 403은 해당
  기능 PR과 Sprint 통합 QA에서 재확인한다.
- 프론트 메뉴 노출은 편의 기능이다. 이 문서의 PASS 판정은 서버 가드가 직접 요청을
  차단하는지에만 근거한다.

PR에는 위 실행 결과와 로컬 DB 제한사항을 함께 기록한다.
