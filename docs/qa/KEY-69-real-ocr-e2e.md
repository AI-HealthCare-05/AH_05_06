# KEY-69 실제 OCR 1종 전체 여정 E2E 증적

## 범위

- 시나리오: `SYN-EMS-01`
- 문서 유형: `EMR`
- 필수 판독 필드: `DIAGNOSIS`, `MEDICATION_NAME`, `DURATION_DAYS`
- 데이터: 저장소의 합성 환자·진료·처방만 사용
- 외부 경계: CLOVA HTTP 호출만 대체하고, 업로드부터 D+7 저장까지 운영 코드 경로를 사용

## 자동화된 전체 여정

`app/tests/e2e/test_key69_real_ocr_journey.py`는 다음 두 경로를 같은 시나리오로 검증한다.

1. 합성 EMR 업로드
2. OCR Worker의 파일 읽기·판독 결과 저장
3. OCR 진단값 수정 및 전체 필드 확정
4. 안내 생성·직원 검토·의사 승인
5. 환자 링크 발급·OTP 인증·안내 열람
6. D+7 응답 제출 및 병원 화면 재조회

| 경로 | 외부 CLOVA 경계 | 저장 결과 | 최종 결과 |
|---|---|---|---|
| 실제 OCR 모드 | 기존 실측 `SYN-EMS-01` CLOVA General V2 응답을 결정적으로 재생 | `model_name=clova-ocr-v2`, 필수 필드 3종 이상 | 전체 여정 완료 |
| fallback 모드 | 합성 timeout 오류 | `model_name=fixture-v0`, `failure_code=CLOVA_API_ERROR` | 같은 전체 여정 완료 |

외부 HTTP 응답만 재생하므로 테스트는 네트워크·개발 키 유무와 무관하게 반복할 수 있다. 업로드 API, Worker, DB 저장, 수정·확정 API, 안내·환자 API는 mock하지 않는다.

## 2026-09-02 실행 결과

```text
KEY-69 + field extractor                 16 passed, 1 xfailed
E2E + OCR worker 회귀                    30 passed, 1 xfailed
security + document + guide + patient   287 passed
backend full suite                       1574 passed, 1 xfailed, 14 subtests passed
Ruff                                    passed
mypy                                    passed
```

테스트 DB는 프로젝트 데이터와 분리된 로컬 MySQL 8의 임시 계정을 사용했고, 실행 후 계정을 제거한다.

## 보안·관측 증적

- `started_at`과 `completed_at`으로 처리시간을 계산할 수 있다.
- fallback이 Worker에서 시작된 경우 기존 `started_at`을 보존한다.
- 완료 로그에는 mode, 처리시간, 실패 코드, job ID만 남고 OCR 원문·환자명·전화번호는 남지 않는다.
- 환자 링크 원문은 DB에 저장하지 않고 SHA-256 digest만 저장한다.
- 실제 환자정보, 운영 토큰, CLOVA URL·키는 테스트·문서·커밋에 포함하지 않는다.

## 실제 CLOVA 1회 호출 증적

현재 로컬에는 CLOVA 개발 계정의 invoke URL과 secret key가 없어 외부 네트워크 호출은 실행하지 못했다. 따라서 위 자동화 결과를 "실제 CLOVA 호출 완료"로 표기하지 않는다.

개발 키와 MinIO의 합성 EMR 이미지가 제공되면 아래 명령으로 실제 호출을 추가 검증한다. 키 값과 OCR 원문은 커밋하거나 PR에 붙이지 않는다.

```bash
DB_HOST=127.0.0.1 uv run python scripts/test_clova_ocr.py \
  <MinIO에서 받은 SYN-EMS-01 이미지의 로컬 경로> EMR
```

PR에는 다음 비민감 항목만 요약한다.

- 성공 여부
- `model_name`
- 처리시간
- 추출된 필드 이름 목록(값 제외)
- 실패 시 `failure_code`와 fallback 전체 여정 통과 여부
