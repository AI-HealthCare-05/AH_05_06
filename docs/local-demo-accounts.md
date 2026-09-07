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
# fixture OCR (빠름, 업로드 즉시 판독값)
./scripts/bootstrap-local.sh

# 실판독 OCR (CLOVA) — ai-worker·minio 까지 함께
./scripts/bootstrap-local.sh --with-ocr-worker
```

스크립트가 만든 무작위 직원 비밀번호는 `.bootstrap.local.env` 의 `SEED_STAFF_PASSWORD` 에 있다.
이 값으로 로그인해도 되고, 서버와 같은 `<공용PW>` 로 맞추려면 2-3 의 재시드를 한다.

### 2-2. 데모에 필요한 값 세 개 추가

`bootstrap` 은 아래를 세팅하지 않으므로 `envs/.local.env` 에 직접 넣는다.

| 값 | 넣을 것 | 이유 |
|---|---|---|
| `MOCK_OTP_CODE` | `000000` | 없으면 환자 OTP 인증 자체가 "발송 수단 없음" 으로 막힌다. 로컬·개발 전용이고 prod 에서는 config 가 거부한다 |
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
docker compose exec -T -e SEED_STAFF_PASSWORD='<공용PW>' fastapi \
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
5. 승인되면 의사 화면에서 **환자 링크 발급** → 새 탭으로 환자 안내 화면 열림
6. 환자 화면: 고정 OTP `000000` 입력 → 인증 → 복약지도·주의·생활·챗봇 열람
7. 챗봇에 질문 입력 → 승인된 지식 범위 안에서 응답
8. D+7 체크인 링크(`checkin.html`)에서 복약·통증 6단계 응답 제출
9. 병원 화면에서 같은 진료의 D+7 응답 확인

## 4. 시연에서 실물이 아닌 부분 (MVP 결정, 결함 아님)

| 구간 | 현재 |
|---|---|
| 환자 OTP | 고정 `000000` (`MOCK_OTP_CODE`). 실제 SMS 발송 없음 |
| 문자 발송 | `SMS_PROVIDER=mock`. 링크는 담당자가 화면에서 복사해 수동 전달 |
| 안내문 생성 | 확정 OCR 값 한 줄 + 처방세트별 승인 문구/의사 수정 문구/기본 문구 조합. LLM 생성은 미착수(KEY-75) |
| 환자 챗봇 | `OPENAI_API_KEY` 가 비면 3-7 의 챗봇 응답이 고정 폴백 문구로만 나온다. 실제 응답을 보려면 키가 필요하다 (`app/apis/v1/chatbot_routers.py`) |
| OCR (fixture 모드) | 업로드 이미지를 실제로 판독하지 않고 합성 판독값 주입. 실판독은 2-2 에서 `OCR_FIXTURE_FALLBACK=0` + CLOVA 키 + `--with-ocr-worker` |

## 5. 알아둘 것

- 비밀번호·CLOVA 키·JWT·환자 링크 토큰은 저장소·커밋·로그에 남기지 않는다 (`AGENTS.md`).
- `seed.py` 는 `SEED_STAFF_PASSWORD` 없이 실행되지 않고, `ENV=prod` 에서는 거부된다.
- 같은 명령을 다시 실행해도 데이터가 쌓이지 않는다(로그인 아이디·차트번호 기준 upsert).
- 직원 로그인에는 비밀번호 우회가 없다. `000000` 은 **환자 OTP 전용**이다.
- 초기화: `docker compose down -v` 후 2-1 부터 다시.
