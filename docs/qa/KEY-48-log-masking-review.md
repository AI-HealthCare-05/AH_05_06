# KEY-48 민감정보·토큰·로그 마스킹 검수

> 검수일: 2026-08-21
> 기준 브랜치: `develop` (`d385cbe`) 위 `fix/KEY-48-log-masking-review`
> Jira: https://leehee.atlassian.net/browse/KEY-48 (부모 [KEY-37](https://leehee.atlassian.net/browse/KEY-37))

## 요약

비밀번호·JWT·OTP·환자 링크 토큰·휴대폰번호를 로그·응답에서 가리는 공통 마스킹은
`KEY-11`·`KEY-25`·`KEY-28`·`KEY-110`에서 이미 구현·회귀검증되어 있었다. 이번 검수는
새 마스킹 정책을 만들지 않고 **현재 코드 기준으로 그 구현이 여전히 유효한지**
확인했고, 검수 과정에서 실제 공백 1건을 찾아 고쳤다.

## 판정 요약

| 대상 | 판정 | 근거 |
|---|---|---|
| 로그 — 비밀번호·JWT·OTP·링크토큰 제거 | PASS | `app/core/masking.py`의 `scrub()`이 `app/core/logger.py`의 `MaskingFilter`로 모든 로거에 자동 적용됨을 재확인 |
| 로그 — 휴대폰번호 뒤 4자리만 유지 | PASS | `mask_phone()`이 가운데 자리만 가림을 재확인 |
| 로그 — 포맷 인자·`exc_info` traceback | PASS | 메시지뿐 아니라 `%s` 인자와 예외 렌더링 결과까지 가려짐을 재확인 |
| 오류 응답(422) — 요청 원문 미노출 | PASS | `masked_validation_handler`가 `input`을 제거함을 재확인 |
| 오류 응답(`HTTPException`) — `detail` 마스킹 | PASS | `masked_http_exception_handler`가 `scrub()` 적용함을 재확인 |
| 오류 응답(`OcrApiError`) — 마스킹 미적용 | FIXED | `app/main.py`의 `ocr_api_error_handler`가 공통 핸들러 경로를 안 거치고 `exc.message`를 그대로 응답하던 것을 발견 — `scrub()` 적용 |
| 저장소 비밀값 미포함 | PASS | `test_secrets_not_committed.py`, `test_exposed_secrets_not_reused.py`(KEY-110) 통과 |
| 오탐 방지 — 진단코드·상태코드·차트번호·요청ID 유지 | PASS | `test_masking.py::TestFalsePositives` 통과 |

## 정상·예외 케이스

- 정상: 로그인 실패 로그에 `password=...`가 `[REDACTED]`로 바뀌고 `login_id`는 남아 원인 추적이 된다.
- 정상: 전화번호는 `010-****-5678`처럼 뒤 4자리만 남아 어느 환자 건인지 추적할 수 있다.
- 예외: 처리되지 않은 예외(500)에서도 예외 메시지에 심어둔 비밀번호·링크 토큰이 응답 본문과 로그 traceback 모두에서 사라진다.
- 예외: `OcrApiError`로 502를 던지며 메시지에 토큰을 심은 경우, 수정 전에는 응답에 그대로 노출됐고 수정 후에는 가려진다 — `test_error_responses.py::TestOcrErrorHandlerIsAlsoScrubbed`로 회귀 고정.

## 이번 검수에서 고친 것

`app/main.py`의 `ocr_api_error_handler`는 `register_error_handlers()`가 등록하는
`masked_http_exception_handler` 경로를 타지 않는 별도 핸들러였다. 현재
`OcrApiError`를 만드는 모든 호출부(`app/ocr/service.py`, `app/ocr/security.py`)는
고정된 한글 문구만 쓰고 있어 지금 당장 새는 값은 없었지만, **공통 마스킹을
안 거치는 유일한 예외 핸들러**였다. 이후 OCR 벤더(CLOVA 등) 응답 원문을 그대로
실어 던지는 코드가 생겨도 여기서 걸리도록 `scrub(exc.message)`를 적용했다.

## 남은 제한사항

- uvicorn access log(`uvicorn.access` 로거)는 `app/core/logger.py`의
  `MaskingFilter`를 타지 않는다. 요청 경로·쿼리스트링을 그대로 찍는다. 현재
  토큰을 쿼리스트링으로 받는 API가 없어(환자 링크·OTP는 `KEY-4` 범위로 아직
  이 브랜치에 없음) 즉시 노출되는 값은 없다고 확인했다. 해당 API가 구현되면
  access log 경로를 반드시 다시 검토해야 한다 — 이번 검수의 완료 판정을
  막지는 않되, 후속 확인 항목으로 남긴다.
- Notion API 명세서는 이번 검수에서 열람하지 않았다. 마스킹 대상·범위의
  정본으로는 `docs/qa/KEY-25-sensitive-data-regression.md`의 적용 범위표를
  사용했다.

## 실행 명령

```bash
UV_CACHE_DIR=/private/tmp/key48-uv-cache ENV=local uv run --python 3.13 --group app --group dev pytest -q app/tests/security
UV_CACHE_DIR=/private/tmp/key48-uv-cache ENV=local uv run --python 3.13 --group app --group dev pytest -q app
UV_CACHE_DIR=/private/tmp/key48-uv-cache uv run --python 3.13 --group app --group dev coverage run -m pytest -q app
UV_CACHE_DIR=/private/tmp/key48-uv-cache uv run --python 3.13 --group app --group dev coverage report -m
uv run ruff check app/main.py app/tests/security/test_error_responses.py
uv run ruff format app/main.py app/tests/security/test_error_responses.py --check
```

결과:

```text
app/tests/security: 65 passed
전체 app: 513 passed, 1 skipped
coverage: TOTAL 91%
ruff check / format: All checks passed
```

전체 `app` 실행은 로컬 Docker MySQL 컨테이너(`mysql:8.0`, 3306)가 떠 있어야
한다. 로컬 기본 Python(3.14)에서는 `pytest-asyncio` 이벤트 루프 초기화가
깨져 DB 연동 테스트가 실패하므로, 이 문서의 명령처럼 `--python 3.13`을
명시해 실행했다 — KEY-48 코드 변경과는 무관한 로컬 인터프리터 문제다.

PR 작성 시 위 실행 결과와 남은 제한사항을 함께 기록한다.
