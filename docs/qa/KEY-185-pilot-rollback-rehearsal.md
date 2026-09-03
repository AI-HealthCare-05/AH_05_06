# KEY-185 Pilot 롤백·재배포 복구 리허설

> 대상: 합성 데이터만 사용하는 Pilot 환경
> 담당: 유가은 · 최종 인수: 이희진 · 기술 확인: 권일준
> 기준 런북: [`docs/deploy-runbook.md`](../deploy-runbook.md) 4절·5절

## 판정

**PASS — 롤백·검증·현재 버전 재복구 완료**

2026-09-03 승인된 Pilot 변경 시간에 세 애플리케이션을 이전 정상 이미지로
롤백하고 health·auth·core smoke를 수행한 뒤, 시작 시 정상 이미지로 재복구했다.
롤백 후와 재복구 후 smoke가 모두 통과했으며 DB volume 삭제와 migration
downgrade는 수행하지 않았다. 합성 smoke 계정은 팀 Notion에서 확인해 Git이
무시하는 권한 `600` 로컬 파일에만 설정했다.

## 범위와 안전 경계

- 실제 환자정보가 없는 Pilot 환경에서만 수행한다.
- 앱 이미지 롤백·재배포와 복구 확인만 수행한다.
- DB 볼륨 삭제(`docker compose down -v`)와 운영 환경 변경은 범위 밖이다.
- DB migration downgrade는 별도 승인과 해당 migration 복구 문서 없이는 하지
  않는다.
- 비밀번호·PAT·SSH 키·환자 링크 토큰은 명령 인자, 터미널 캡처, 커밋, Jira
  댓글에 남기지 않는다.
- 실패하면 구현 범위를 넓히지 않고 재현 조건과 담당 영역을 기록해 후속 Jira로
  분리한다.

## 2026-09-03 사전 점검

| 확인 항목 | 결과 | 증적 |
|---|---|---|
| Jira 선행 KEY-174 | PASS | 상태 `완료` |
| Jira 선행 KEY-184 | PASS | 상태 `완료` |
| `GET /api/v1/health` | PASS | HTTP 200, api·db·redis 모두 `ok` |
| `/` 프런트 진입 | PASS | HTTP 200 |
| `/login.html` 진입 | PASS | HTTP 200 |
| Pilot SSH 키 | PASS | 등록된 전용 공개키와 로컬 개인키로 접속 확인 |
| smoke 합성 계정 | PASS | `staff01`, 비밀번호는 Git 제외·권한 `600` 로컬 파일에만 설정 |
| 기준 health·auth·core smoke | PASS | 2026-09-03 10:26 KST, 세 단계 정상 |
| 현재·이전 정상 이미지 태그 | PASS | 서버 설정·로컬 이미지·원격 manifest 교차 확인 |

대상 주소는 Jira KEY-192에 공유된 Pilot 주소를 사용했다. 응답 본문, 토큰,
비밀번호는 증적에 복사하지 않았다.

## 실제 실행 전 조건

다음 항목을 실행 담당자와 최종 인수자가 함께 확인한다.

- [x] Pilot 변경 시간과 실행 담당자 승인
- [x] SSH 접속 수단을 저장소 밖에서 전달받음
- [x] 합성 smoke 계정을 환경변수로만 전달받음
- [x] 현재 정상 태그 `APP_VERSION`, `AI_WORKER_VERSION`, `WEB_VERSION` 기록
- [x] 롤백 대상인 이전 정상 태그 세 개 기록
- [x] 세 이전 이미지가 Docker Hub에 실제로 존재함
- [x] DB schema가 이전 앱과 호환됨을 확인함
- [x] DB downgrade와 볼륨 삭제를 하지 않기로 재확인함

태그와 시각은 아래 표에 적되 비밀값은 적지 않는다.

| 구분 | fastapi | ai-worker | web |
|---|---|---|---|
| 시작 시 정상 태그 | `v1.0.2` | `v1.0.2` | `v1.0.4` |
| 롤백 대상 태그 | `v1.0.1` | `v1.0.1` | `v1.0.3` |
| 재복구 태그 | `v1.0.2` | `v1.0.2` | `v1.0.4` |

앱 `v1.0.1`과 `v1.0.2`의 migration 0~20 파일 목록과 내용 hash가 동일함을
확인했다. 따라서 이번 리허설에는 DB downgrade가 필요하지 않았다.

## 리허설 절차와 증적

### 1. 기준 상태 확인

1. 서버의 `.env`에서 세 이미지 태그의 **이름과 값만** 확인한다. 파일 전체를
   출력하거나 복사하지 않는다.
2. `docker compose ps`로 서비스 상태를 기록한다.
3. 로컬에서 기존 smoke를 실행한다.

```bash
export SMOKE_LOGIN_ID=staff01
export SMOKE_PASSWORD=<저장소 밖에서 전달받은 합성 비밀번호>
uv run python scripts/smoke.py http://<Pilot 주소>
```

| 항목 | 시작 | 종료 | 결과·제한사항 |
|---|---|---|---|
| 기준 smoke | 2026-09-03 10:26 KST | 2026-09-03 10:26 KST | PASS — health·auth·core 정상 |

### 2. 이전 정상 버전으로 롤백

1. 런북 4절에 따라 세 버전 태그를 승인된 이전 정상 태그로 변경한다.
2. 해당 이미지를 먼저 pull해 태그 존재 여부를 확인한다.
3. `docker compose up -d --pull always`로 앱을 교체한다.
4. `docker compose ps`와 smoke로 복구 여부를 판정한다.

| 항목 | 시작 | 종료 | 결과·제한사항 |
|---|---|---|---|
| 이전 버전 기동 | 2026-09-03 14:42 KST | 2026-09-03 14:43 KST | PASS — 세 이전 정상 이미지 기동 확인 |
| 롤백 후 smoke | 2026-09-03 14:43 KST | 2026-09-03 14:43 KST | PASS — health·auth·core 정상 |

### 3. 현재 정상 버전으로 재배포

1. 시작 전에 기록한 세 정상 태그로 되돌린다.
2. `docker compose up -d --pull always`로 다시 기동한다.
3. `docker compose ps`와 smoke가 모두 통과하는지 확인한다.

| 항목 | 시작 | 종료 | 결과·제한사항 |
|---|---|---|---|
| 현재 버전 재기동 | 2026-09-03 14:43 KST | 2026-09-03 14:45 KST | PASS — 시작 시 세 정상 이미지로 복구 |
| 최종 smoke | 2026-09-03 14:45 KST | 2026-09-03 14:49 KST | PASS — health·auth·core 정상 |

재기동 직후 첫 health 요청은 FastAPI가 포트를 열기 전에 Nginx에 도착해 1회
HTTP 502를 반환했다. FastAPI 로그에서 application startup 완료를 확인한 뒤
재시도한 최종 smoke는 세 단계 모두 통과했다. 전체 롤백 시작부터 최종 smoke
통과까지 약 7분이 걸렸으며, 수동 단계는 승인 확인, 이미지 태그 교체, smoke
실행, 원래 태그 복원이었다. 임시 `.env` 백업은 원복 확인 후 서버에서 삭제했다.

## 완료 판정

다음 조건을 모두 충족해야 `PASS`다.

- [x] 이전 정상 버전과 복구 대상 버전을 혼동 없이 식별함
- [x] 문서화된 절차로 이전 정상 버전이 기동됨
- [x] 롤백 후 health·auth·core smoke가 통과함
- [x] 시작 시 정상 버전으로 다시 복구함
- [x] 재복구 후 health·auth·core smoke가 통과함
- [x] 전체 복구 소요시간과 수동 단계를 기록함
- [x] 비밀값·토큰·환자정보가 증적에 없음
- [x] 실패가 있으면 재현 조건·영향 범위·후속 Jira를 기록함

실패로 분리할 항목은 없다. 재기동 직후의 일시적 502는 준비 완료 전 요청으로
재현 조건과 범위를 위에 기록했으며, 현재 Pilot은 시작 시 정상 버전으로 복구되어
최종 smoke를 통과했다.
