# KEY-152 전체 여정 원클릭 E2E 증적

## 실행

깨끗한 테스트 DB가 준비된 저장소 루트에서 실행한다.

```bash
DB_HOST=127.0.0.1 \
DB_PORT=3306 \
DB_USER=root \
DB_PASSWORD='<로컬 테스트 DB 비밀번호>' \
DB_NAME=ai_health \
scripts/run_key152_e2e.sh
```

운영 비밀번호, 실제 환자정보, 운영 링크·토큰을 사용하지 않는다.

## 고정 시나리오

- 시나리오: `SYN-EMS-01`
- 병원: H1 기준의원
- 직원: `staff01` 한소영
- 의사: `doctor01` 박연
- 환자: 차트번호 `12401` 윤지아, 1989-03-12
- 진료일: 2026-07-29

모든 값은 `docs/data/synthetic-patients.csv`와 `docs/data/synthetic-staff.csv`의 합성 데이터다.

## 단계별 검증과 경계

| 단계 | 검증 | 구분 |
|---|---|---|
| 직원·의사 로그인 | 실제 `POST /api/v1/auth/login`, Access Token 발급 및 Refresh Token 본문 비노출 | 실제 구현 |
| 환자·진료 연결 | 동일한 `hospital_id`·`patient_id`·`visit_id`를 끝까지 사용 | 합성 DB fixture |
| 문서 업로드 | 실제 multipart 업로드, 문서와 `PROCESSING` OCR 작업 생성 | 실제 구현 |
| OCR 완료 | 운영 코드의 `_seed_fixture_result` 경로로 원문·판독값을 만들고 작업을 `COMPLETED`로 전환 | W1 fixture (`KEY-149`) |
| OCR 확정 | 실제 `PATCH /api/v1/ocr/fields/{id}` | 실제 구현 |
| 안내 생성 | 실제 `POST /api/v1/visits/{visit_id}/guide/generate` | 고정 템플릿 구현 (`KEY-150`) |
| 안내 수정 | 실제 의사 계정으로 `PATCH /api/v1/visits/{visit_id}/guide/sections/medication`, 합성 최종 문구 저장 | 실제 구현 |
| 의사 승인 | 실제 의사 계정으로 승인, `SCHEDULED_TO_SEND` 확인 | 실제 구현 |
| 환자 링크 | 실제 개발용 링크 발급·조회, 최종 승인 문구와 모든 본문 비어 있지 않음을 확인 | W1 개발용 구현 (`KEY-90`) |
| D+7 제출 | 실제 토큰 경로로 복약·통증 응답 저장 | 실제 구현 (`KEY-151`) |
| 병원 조회 | 같은 `visit_id`로 저장 응답 조회 | 실제 구현 (`KEY-99`) |

## DB·보안 확인

- 안내 상태가 `SCHEDULED_TO_SEND`인지 확인한다.
- D+7 응답이 동일 안내문과 진료에 연결됐는지 확인한다.
- 환자 링크 원문을 SHA-256으로 해시한 값이 DB의 `token_digest`와 일치해야 한다.
- 환자 링크 원문은 병원 조회 응답에 나타나지 않아야 한다.
- 로그인 응답 본문에 Refresh Token이 없어야 한다.
- 업로드 파일은 테스트별 임시 디렉터리에 저장하고 종료 시 제거한다.

## 현재 제한사항과 교체 경계

- 실제 OCR worker는 아직 사용하지 않는다. `OCR 작업 완료 + 판독 결과 입력` 구간만 합성 fixture다.
- 실제 SMS와 운영용 OTP 인증은 이 Walking Skeleton 범위에 포함되지 않는다.
- 이 테스트는 단일 병원의 정상 여정만 다룬다. 병원 간 격리와 역할별 거부는 각 API의 권한 테스트가 담당한다.
- 로그인·계정·쿠키 테스트 헬퍼의 공통화는 여러 테스트 모듈에 걸친 별도 리팩터링으로 분리한다.
- 다음 주 실제 OCR을 연결할 때는 E2E 테스트의 OCR fixture 입력 구간만 worker 완료 대기로 교체하고, 이후 확정·생성·승인·링크·D+7 검증은 유지한다.

## 2026-08-25 로컬 실행 결과

```text
app/tests/e2e/test_key152_walking_skeleton.py  1 passed
ruff check                                    passed
ruff format --check                           passed
mypy                                           passed
```

테스트 DB는 프로젝트 데이터와 분리한 임시 MySQL 8.0을 사용했다.
