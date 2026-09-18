# 로컬 시연 계정과 셋업 절차

> 새로 clone 한 사람이 로컬에서 병원 업무 → 환자 안내 흐름을 한 바퀴 시연하기 위한 최소 절차.
> 기준 브랜치 `develop`. 합성 데이터만 쓴다.

## 1. 계정

로그인 아이디는 저장소의 `docs/data/synthetic-staff.csv` 에서 온다. **비밀번호는 저장소에 두지 않는다** —
시드할 때 `SEED_STAFF_PASSWORD` 로 넘긴 값이 곧 모든 합성 직원의 비밀번호이고, 팀 공용값은
Notion 자격증명 표에 있다. 아래의 `<공용PW>` 는 그 값으로 읽는다.

### 시연에 쓰는 계정 (H1 · 기준의원)

| 아이디 | 비밀번호 | 이름 | 역할 | 용도 |
|---|---|---|---|---|
| `staff01` | `<공용PW>` | 한소영 | staff | 기준 스탭 — 환자·진료 등록, 문서 업로드, OCR 확정 |
| `doctor01` | `<공용PW>` | 박연 | doctor | 기준 의사 — 안내문 검토·승인, 환자 링크 발급. 합성 환자 대부분의 담당의 |
| `doctor02` | `<공용PW>` | 김연우 | doctor | 두 번째 의사 |
| `admindoc01` | `<공용PW>` | 최다온 | doctor + admin | 원장이 관리자 겸임 — admin 이 있어도 승인이 되는지 확인용 |
| `admin01` | `<공용PW>` | 정미래 | admin | 운영 전용 — 진료 화면이 안 열리는 것을 보이는 용도 |

### 경계·예외 확인용 계정

| 아이디 | 역할 | 무엇을 보이나 |
|---|---|---|
| `adminstaff01` | staff + admin | 스탭 일은 되고 **의료 승인만 막힌다** |
| `newbie01` / `newdoc01` | staff / doctor | 첫 로그인 — 비밀번호 변경(L-3) 전에는 아무 데도 못 간다. **초기 비밀번호도 `<공용PW>`** |
| `left01` / `leftdoc01` | staff / doctor | 퇴사자 — roles 가 남아 있어도 로그인 거부 |
| `lock01` | staff | 5회 실패 잠금 시연 전용. 다른 시험에서 건드리지 말 것 |
| `lastadmin01` | admin | 마지막 관리자 — 이 계정에서 admin 을 빼는 저장은 거부돼야 한다 |
| `staff21` / `doctor21` / `admin21` | H2 · 격리의원 | 병원 간 격리 — H1 환자·진료가 보이면 안 된다. `doctor21` 은 H1 박연과 **동명이인** |

## 2. 셋업

전제: Docker Desktop 실행 중, 저장소 루트에서 `develop` 체크아웃.

### 2-1. 스택·환경 만들기 — `bootstrap-local.sh`

이 스크립트가 `.env` 생성(비밀값 자동 채움), 컨테이너 기동, `aerich upgrade`, 직원 시드,
스모크까지 한다.

```bash
# 워커 없음 — fixture 판독으로 보려면 2-2 에서 OCR_FIXTURE_FALLBACK=1 로 바꾼다
# (bootstrap 기본값은 false 라 그대로 두면 업로드한 판독이 워커를 기다리며 멈춘다)
./scripts/bootstrap-local.sh

# 실판독 OCR (CLOVA) · 예약 문자 발송 — ai-worker·minio 까지 함께
./scripts/bootstrap-local.sh --with-ocr-worker
```

스크립트가 만든 무작위 직원 비밀번호는 `.bootstrap.local.env` 의 `SEED_STAFF_PASSWORD` 에 있다.
이 값으로 로그인해도 되고, 서버와 같은 `<공용PW>` 로 맞추려면 2-3 의 재시드를 한다.

### 2-2. 데모에 필요한 값 세 개 추가

`bootstrap` 은 아래를 세팅하지 않으므로 저장소 루트의 **`.env`** 에 직접 넣는다.
(2-1 의 `bootstrap` 이 만든 파일이고, 컨테이너가 읽는 것도 이 파일 하나다 —
`envs/.local.env` 는 수동 설치 경로에서만 쓰는 이름이라 여기서는 건드리지 않는다.)

| 값 | 넣을 것 | 이유 |
|---|---|---|
| `MOCK_OTP_CODE` | `000000` | 없으면 환자 OTP 인증이 503 으로 막힌다. 로컬·개발 전용이고 `ENV=prod` 에서는 서버가 안 뜬다 — 단 Pilot 은 `PILOT_ALLOW_MOCK_OTP=1` 과 `--pilot-confirm-mock-otp` 가 **둘 다** 있으면 연다 (KEY-264) |
| `OCR_FIXTURE_FALLBACK` | fixture 모드면 `1`, 실판독이면 `0` | `bootstrap` 기본값은 `false`(=실판독). 워커 없이 fixture 로 볼 거면 `1` 로 바꾼다 |
| `CLOVA_OCR_INVOKE_URL` · `CLOVA_OCR_SECRET_KEY` | 실판독일 때만, 팀에서 받은 키 | 저장소에 없다 |

값을 바꿨으면 fastapi 컨테이너가 다시 읽도록 재생성한다.

```bash
docker compose up -d --force-recreate --no-deps fastapi
```

### 2-3. 화면 서버 + 환자·진료 데이터

`bootstrap` 은 nginx 를 안 띄우고 직원만 시드한다. 시연은 화면과 환자 데이터가 필요하다.

```bash
# 화면 서버(nginx)
docker compose --profile web up -d

# 직원 + 환자 + 진료 + 처방, 비밀번호를 <공용PW> 로 통일
# -e 에는 이름만 준다 — 값을 -e 뒤에 적으면 컨테이너 프로세스 목록(ps)에 남는다.
# 앞의 대입은 **셸 기록에는 그대로 남는다.** 지우려면 명령 앞에 공백을 하나 두거나
# (HISTCONTROL=ignorespace) 미리 export 한 뒤 이름만 넘긴다 (KEY-308).
SEED_STAFF_PASSWORD='<공용PW>' docker compose exec -T -e SEED_STAFF_PASSWORD fastapi \
  uv run --no-sync python scripts/seed.py --mode full

# 확인
docker compose exec -T fastapi uv run --no-sync python scripts/check_schema_drift.py
```

### 2-4. 접속

- 화면: <http://localhost>  (로그인 `login.html`)
- 진행 지도: <http://localhost/map.html>
- API 문서: <http://localhost/api/docs>
- 헬스: <http://localhost:8000/api/v1/health> → `status: ok` 확인

## 3. 시연 시나리오 (클릭 순서)

기준 합성 진료: **윤지아 · 차트 12401 · 2026-07-29 · 담당의 박연** (`SYN-EMS-01`).

1. `staff01` 로그인 → 오늘 목록에서 환자 검색 → 윤지아 선택
2. 진료 카드에서 진료기록 이미지 업로드 → OCR 작업 생성
3. `ocr-review.html` 에서 판독값 확인·수정 → 모든 항목 **확정** → 안내문 생성
4. `doctor01` 로 로그인 → 승인 대기 목록 → 안내문 미리보기 → **승인** (또는 반려 사유 입력 후 재제출)
5. 환자 링크를 만든다. **화면의 링크 발급 단추는 없다** — 2026-09-11 범위 조정으로 링크 블록이
   읽기 전용이 됐고(KEY-275·KEY-307), 운영에서는 발송기가 문자 직전에 발급한다(KEY-297).
   로컬 시연에서는 아직 남아 있는 API 로 한 번 발급한다.
   - `POST /api/v1/visits/{visit_id}/guide/link` — `staff`·`doctor` 역할, 직원 로그인 토큰(Bearer).
     안내문이 승인(`SCHEDULED_TO_SEND`)된 뒤에만 된다. 두 번째 호출은 `LINK_ALREADY_ISSUED` 409 —
     교체는 `…/guide/link/re-issue`.
   - 응답 `path` 는 `/api/v1/guides/<토큰>` 이다. 브라우저로는
     `http://localhost/patient_wireframe/html/otp.html#t=<토큰>` 을 연다(발송기·`doctor-api.js` 와 같은 모양).
   - 토큰은 합성 진료 것이라도 **티켓·PR·메신저에 붙이지 않는다** (`AGENTS.md`).
6. 환자 화면: 고정 OTP `000000` 입력 → 인증 → 복약지도·주의·생활·챗봇 열람
7. 챗봇에 질문 입력 → 승인된 지식 범위 안에서 응답
8. D+7 체크인 링크(`checkin.html`)에서 복약·통증 6단계 응답 제출
9. 병원 화면에서 같은 진료의 D+7 응답 확인

## 4. 시연에서 실물이 아닌 부분 (MVP 결정, 결함 아님)

표기는 화면·README와 동일하게 사용한다.

- `[구현중]` — 서버 자리는 있으나 일부만 동작하거나 운영 조건이 걸린 기능
- `[임시]` — 화면만 있거나 고정값·목 데이터로 동작하는 기능
- 표기 없음 — 실동작. 시연 범위만 제한되면 `이번 시연은 …까지 보여드립니다`라는 각주를 쓴다.

| 구간 | 현재 |
|---|---|
| 환자 OTP | `[임시]` 고정 `000000` (`MOCK_OTP_CODE`). 실제 SMS 발송 없음 |
| 문자 발송 | `[임시]` `SMS_PROVIDER=mock` — 실제로 안 나간다. 발송은 `ai-worker`(`--with-ocr-worker`)가 맡고, 원본 문서를 올린 진료는 `SOURCE_NOT_DELETED`, 의원 예약 주소가 빈 소진·재진 문자는 `BOOKING_URL_MISSING` 으로 보류된다 (`app/services/dispatch_gate.py`). `solapi` 로 바꾸면 KEY-338 좁은문·승인 번호 목록이 추가로 걸린다 — README 「문자 발송」 표 |
| 안내문 생성 | `[구현중]` 기본(`GUIDE_RAG_ENABLED=false`)은 확정 OCR 값 + 처방세트별 승인 문구/의사 수정 문구/기본 문구 조합. 승인 지식 기반 LLM 생성(KEY-277)은 스위치 뒤에 있고 승인 지식 적재(KEY-276)가 먼저다 — README 「OpenAI」 절 |
| 환자 챗봇 | `[구현중]` `OPENAI_API_KEY` 줄이 없으면 고정 폴백 문구만 나온다 (`app/apis/v1/chatbot_routers.py`). 키가 있으면 승인 안내에 근거가 있는 질문(복약·주의·생활·응급)은 실제 모델 답이 나온다. 답의 **문장 하나하나**가 고른 섹션 본문에 그대로 있어야 통과하므로, 본문에 없는 문장이 하나라도 섞이면 「안전하게 답변할 수 없는 내용이에요」로 막힌다 — 승인 안내 밖의 내용·약 변경/진단 요구도 그대로 막힌다 (KEY-351 — 그 전에는 답 전체의 연속 원문 일치와 「주의」 미분류로 근거가 있어도 대부분 거절됐다). 결과는 `patient_usage_event.answer_outcome` 에서 본다 |
| OCR (fixture 모드) | `[임시]` 업로드 이미지를 실제로 판독하지 않고 합성 판독값 주입. 실판독은 2-2 에서 `OCR_FIXTURE_FALLBACK=0` + CLOVA 키 + `--with-ocr-worker` |

## 5. 알아둘 것

- 비밀번호·CLOVA 키·JWT·환자 링크 토큰은 저장소·커밋·로그에 남기지 않는다 (`AGENTS.md`).
- `seed.py` 는 `SEED_STAFF_PASSWORD` 없이 실행되지 않는다. `ENV=prod` 에서는 `SEED_ALLOW_PROD=1`(환경변수)과
  `--allow-prod-seed`(명령줄)가 **둘 다** 있어야 열린다 (`scripts/seed.py`).
- 같은 명령을 다시 실행해도 데이터가 쌓이지 않는다(로그인 아이디·차트번호 기준 upsert).
- 직원 로그인에는 비밀번호 우회가 없다. `000000` 은 **환자 OTP 전용**이다.
- 초기화: `docker compose down -v` 후 2-1 부터 다시.
