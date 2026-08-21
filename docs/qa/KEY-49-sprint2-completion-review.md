# KEY-49 Sprint 2 미통과 항목·완료 판정

> 검수일: 2026-08-21
> 기준 브랜치: `develop` (`b6c2f55`) 위 `test/KEY-49-sprint2-completion-review`
> Jira: https://leehee.atlassian.net/browse/KEY-49 (부모 [KEY-37](https://leehee.atlassian.net/browse/KEY-37))

## 결론

**최종 완료**로 판정한다.

- KEY-46 결과물인 PR #83의 승인·병합을 확인했다.
- PR #83 병합 이후 최신 `develop` 기준 전체 백엔드 회귀검사와 품질 검사는 모두 통과했다.
- 재현 가능한 제품 결함과 Sprint 2 릴리스 차단 버그는 발견되지 않았다.
- KEY-37과 Sprint 2의 최종 완료 조건을 충족했다.

## 하위 검수 결과

| 항목 | 현재 상태 | 판정 근거 |
|---|---|---|
| KEY-45 환경·실행 경로 검수 | Jira 완료 | KEY-37 하위 작업에서 완료 처리됨 |
| KEY-46 인증·RBAC 시나리오 | PASS | 정상·차단 시나리오와 회귀 테스트 작성 완료, PR #83 승인·병합 및 병합 후 전체 회귀검사 통과 |
| KEY-47 환자·진료·합성데이터 | PASS | 모델 관계·병원 범위·합성데이터 무결성 검수 및 전체 회귀검사 통과 |
| KEY-48 민감정보·로그 마스킹 | PASS | OCR 오류 응답의 마스킹 공백 수정 후 보안·전체 회귀검사 통과, PR #75로 `develop` 병합 완료 |
| KEY-49 통합 회귀검사 | PASS | 최신 `develop` 기준 전체 백엔드 테스트 `703 passed`, 프론트엔드 `17 passed`, 품질 검사 통과 |

## 정상·예외 케이스

- 정상: 유효한 인증·역할 조합에서 허용된 API가 성공하고, 환자·진료 데이터 관계와 합성 fixture가 유지된다.
- 정상: 비밀번호·JWT·OTP·환자 링크 토큰·휴대폰번호가 로그와 오류 응답에서 정책대로 가려진다.
- 예외: 권한이 없는 역할, 알 수 없는 역할·권한, 만료·폐기·종류가 다른 토큰은 기본 차단된다.
- 예외: 병원이 다른 환자·진료 관계, 잘못된 합성데이터 관계와 운영 환경의 합성 계정 적재는 차단된다.

## 미통과 항목·버그 등록 결과

이번 검수에서 재현 가능한 제품 결함은 발견되지 않아 신규 버그 티켓을 등록하지 않는다.

검수 중 인증·OCR 테스트가 대량 실패한 적이 있었지만, 공용 `app/tests/conftest.py`를 제외하는 `--confcutdir` 옵션으로 DB 테스트를 잘못 실행한 것이 원인이었다. 공용 설정을 포함해 다시 실행한 결과 당시 전체 `636 passed`였고, PR #83 병합 후 최신 `develop`에서 전체 `703 passed`를 재확인했으므로 제품 버그로 분류하지 않는다.

아래 항목은 Sprint 2 완료를 막지 않는 후속 확인 사항이다.

1. 이후 인증·RBAC 또는 안내 승인 API가 변경되면 역할별 엔드포인트 수준 `403`을 해당 기능 PR에서 재확인한다.
2. 환자 링크·OTP처럼 민감값을 URL에 실을 가능성이 있는 API가 생기면 uvicorn access log 마스킹을 다시 검토한다.

## 실행 결과

```text
ruff check: All checks passed
ruff format --check: 149 files already formatted
mypy: Success — 149 source files
프론트엔드: 17 passed
전체 app: 703 passed in 58.07s
```

최종 전체 회귀 명령:

```bash
DB_USER=root DB_HOST=127.0.0.1 DB_PASSWORD='<local root password>' uv run pytest -q app
```

비밀번호 값은 로컬 `.env`에서 런타임에만 읽었으며 문서·로그·커밋에 남기지 않았다.

## 최종 완료 체크

- [x] 정상 케이스 1개 이상 확인
- [x] 예외·차단 케이스 1개 이상 확인
- [x] 범위에 맞는 테스트 실행 및 결과 기록
- [x] 실제 개인정보·토큰·운영 비밀값 미사용
- [x] 재현 가능한 미통과 항목의 버그 등록 여부 판단
- [x] PR #83 승인·병합 및 병합 후 회귀검사 확인
- [x] KEY-37 및 Sprint 2 최종 완료 조건 충족
- [ ] PR #86 병합 후 Jira 최종 상태 반영
