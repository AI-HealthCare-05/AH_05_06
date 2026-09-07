# 케어온 — 복약 안내 도우미

다낭성난소증후군·자궁내막증 환자에게 **약을 어떻게 드시는지**를 진료 뒤에도 이어서
안내하는 서비스다. 의원이 종이로 주던 복약 안내를 자동으로 만들고, 환자 휴대폰으로
보내고, 복약 도중 확인 문자를 회차대로 보낸다.

**의료 안전이 이 저장소의 첫 규칙이다.** 안내문에 들어가는 의학 문장은 지어내지
않고, 판독이 못 읽은 값은 비워 두며(0 이나 「-」로 채우지 않는다), 의사 승인 없이는
환자에게 아무것도 나가지 않는다.

## 역할

| 역할 | 하는 일 | 화면 |
|---|---|---|
| **스탭** | 환자·진료 건 등록, 문서 업로드, OCR 판독 결과 확인·수정·확정 | `login` · `patients` · `ocr-review` · `manage` |
| **의사** | 확정된 판독으로 만든 안내문을 검토·승인. 승인 전에는 아무것도 안 나간다 | `doctor` |
| **어드민** | 병원·직원 계정 관리 | `admin` |
| **환자** | 링크·OTP 로 들어와 복약안내·생활관리·챗봇 이용, D+7·D+15 확인 응답 | `guide` · `checkin` (모바일) |

역할은 한 계정에 여러 개 붙을 수 있다(예: 의사+어드민). 서버가 매 요청마다 역할과
소유 병원을 검증한다.

## 한 진료가 지나가는 길 (Walking Skeleton)

```text
병원 로그인
  → 환자·진료 건 등록
  → EMR·처방전·검사결과지·약봉투 업로드
  → OCR 판독
  → 환자정보 일치 확인 · OCR 값 수정·확정
  → 승인 지식 기반 안내문 생성 · 의료 안전 검증
  → 의사 검토·승인
  → 원본 삭제 확인 후 환자 링크 발송
  → 환자 OTP 인증
  → 복약안내 · 생활관리 · 챗봇
  → D+7 · D+15 복약·통증 확인 · 소진 예정 알림
```

이 흐름을 합성 데이터 한 건으로 로컬에서 끝까지 재현하는 것이 이 저장소의 기준선이다.
정본 정의는 [`docs/journey-data-flow-v1.md`](docs/journey-data-flow-v1.md), E2E 근거는
[`docs/qa/KEY-152-e2e-evidence.md`](docs/qa/KEY-152-e2e-evidence.md).

---

## 📖 문서 지도

README 는 **처음 실행하는 데 필요한 최소 절차와 문서 지도**만 둔다. 상세는 아래 정본에 있다.

| 알고 싶은 것 | 정본 문서 |
|---|---|
| 작업 규칙·브랜치·커밋·PR·리뷰 | [`docs/project_workflow.md`](docs/project_workflow.md) · [`AGENTS.md`](AGENTS.md) · [`docs/git_branch_전략.md`](docs/git_branch_전략.md) |
| AI 도구로 작업 시작하기 | [`docs/AI_WORK_START.md`](docs/AI_WORK_START.md) · [`CLAUDE.md`](CLAUDE.md) |
| 전체 서비스 데이터 흐름 | [`docs/journey-data-flow-v1.md`](docs/journey-data-flow-v1.md) |
| API 계약 (공통·병원·환자) | [`docs/api/README.md`](docs/api/README.md) → `common.md` · `hospital.md` · `patient.md` |
| 라우터가 어느 경로를 갖나 | [`docs/router-ownership.md`](docs/router-ownership.md) |
| DB 모델 배치 | [`docs/models-layout.md`](docs/models-layout.md) |
| AI 워커 연동 (Redis Stream) | [`docs/ai-worker.md`](docs/ai-worker.md) |
| 합성 데이터 규격 (환자·진료·처방·검사) | [`docs/synthetic-data-spec.md`](docs/synthetic-data-spec.md) |
| OCR 샘플·기대값 규격 | [`docs/ocr-fixtures.md`](docs/ocr-fixtures.md) |
| 안내 문구 정본 | [`docs/guide-copy-worksheet.md`](docs/guide-copy-worksheet.md) |
| 로컬 시연 계정·셋업 | [`docs/local-demo-accounts.md`](docs/local-demo-accounts.md) |
| 로컬 헬스체크 절차 | [`docs/local-health-check.md`](docs/local-health-check.md) |
| Pilot 배포·롤백 런북 | [`docs/deploy-runbook.md`](docs/deploy-runbook.md) |
| 인프라 규모 판단 | [`docs/infra-scale.md`](docs/infra-scale.md) |
| 화면 정의 (와이어프레임) | [`docs/wireframes/README.md`](docs/wireframes/README.md) |
| 구현 현황 스냅샷 | [`docs/구현현황.md`](docs/구현현황.md) · [`docs/sprint4-plan.md`](docs/sprint4-plan.md) · [`docs/work-packages.md`](docs/work-packages.md) |
| 설계 결정 기록 | [`docs/decisions/`](docs/decisions/) |
| QA 시나리오·회귀 | [`docs/qa/`](docs/qa/) |

---

## 🚀 무엇으로 만들었나

- **FastAPI + Tortoise ORM** — 비동기 API 서버와 DB 모델. 마이그레이션은 `aerich`
- **AI Worker** — OCR 판독을 API 서버와 분리해 처리. API 와는 Redis Stream 으로
  주고받는다 ([`docs/ai-worker.md`](docs/ai-worker.md)). 지금은 스텁이라 `OCR_FIXTURE_FALLBACK` 로
  합성 결과를 잇는다
- **프런트엔드 — 빌드가 없다.** HTML·CSS·ES5 JavaScript 를 `<script src>` 로 그대로
  싣는다. 번들러도 `node_modules` 도 잠금파일도 없다. 파일을 고치고 새로고침하면
  끝이고, 대신 전역 이름이 곧 주소라 **이름이 겹치면 서로를 덮는다**(검사가 막는다)
- **UV Package Manager** — 의존성 설치와 가상환경
- **Docker Compose** — MySQL · Redis · FastAPI 기본 스택, 필요할 때 `web`(nginx)·`ocr`(ai-worker·minio) 프로필 옵트인
- **CI Scripts** — Ruff · Mypy · Pytest 자동화 (`scripts/ci/`)

---

## 📂 프로젝트 구조

```text
.
├── ai_worker/          # OCR 판독 워커 (API 서버와 분리)
│   ├── core/           # 워커 설정 및 로거
│   ├── models/         # AI 모델 파일 보관
│   ├── tasks/          # 실제 처리할 작업 정의
│   └── main.py         # 워커 진입점
├── app/                # FastAPI 서버 코드
│   ├── apis/           # API 라우터 (v1 버전 관리)
│   ├── core/           # 서버 설정(pydantic-settings), DB 설정, JWT, Validator
│   ├── dtos/           # 데이터 전송 객체 (Pydantic)
│   ├── models/         # DB 테이블 정의 (Tortoise)
│   ├── services/       # 비즈니스 로직
│   ├── tests/          # pytest (단위 + `tests/e2e/`)
│   └── main.py         # FastAPI 진입점
├── envs/               # 환경변수 예시 (버전 관리됨) — 실제 값은 .gitignore
│   ├── example.local.env
│   └── example.prod.env
├── frontend/           # 화면 — 빌드 없는 HTML·CSS·ES5 JS
│   ├── *.html          # 화면 하나에 파일 하나 (login · patients · ocr-review · manage · settings …)
│   ├── css/            # 화면별 + 공용(tokens · style · shell · blocks)
│   ├── js/             # 화면 코드와 순수 규칙 파일(`*-rules.js` — 검사가 부른다)
│   └── tests/          # `node --test` 계약 검사. 새 의존성 없이 돈다
├── infra/              # 운영 인프라 설정
│   ├── docker/         # docker-compose.prod.yml (프로필 없음 — 항상 전부 뜬다)
│   └── nginx/          # 리버스 프록시 (http/https)
├── scripts/            # 부트스트랩 · seed · smoke · 배포 · CI
├── docs/               # 정본 문서 (문서 지도 참고)
├── docker-compose.yml  # 로컬 개발용
└── pyproject.toml      # uv 의존성 관리 + [tool.aerich]
```

---

## 🧩 서비스 구성과 기동 순서

| 서비스 | 역할 | 포트(로컬) | 프로필 |
|---|---|---|---|
| `mysql` | 데이터 저장 (MySQL 8.0, utf8mb4) | `3306` | 기본 |
| `redis` | 세션·비동기 작업 큐 (Redis Stream) | `6379` | 기본 |
| `fastapi` | API 서버 (`app.main:app`) | `8000` | 기본 |
| `nginx` | 정적 화면 서빙 + API 프록시 | `80` | `web` |
| `ai-worker` | OCR 판독 워커 | — | `ocr` |
| `minio` | 합성 EMR 이미지 보관 (S3 호환) | `9000` API · `9001` 콘솔 | `ocr` |
| `minio-init` | 버킷 생성 + 익명 접근 차단 (1회 실행) | — | `ocr` |

**기동 순서**: `mysql`·`redis` 가 healthy → `fastapi` → `aerich upgrade`(테이블 생성) →
`seed`(합성 계정) → 필요 시 `minio` + `minio-init` + `ai-worker`. `scripts/bootstrap-local.sh`
가 이 순서를 그대로 밟는다.

- **DB 스키마가 밀려 있어도** `/api/v1/health` 는 `SELECT 1` 만 보므로 `ok` 를 준다.
  그래서 `aerich upgrade` 뒤에는 항상 `scripts/check_schema_drift.py` 로 칸 단위 대조한다.
- 운영(`infra/docker/docker-compose.prod.yml`)에는 프로필이 없다 — 거기서는 항상 전부 뜬다.

---

## ⚙️ 사전 준비 사항

| 도구 | 버전 | 용도 |
|---|---|---|
| **Python** | 3.13 이상 | 로컬 개발·스크립트 실행 |
| **UV** | 최신 | 의존성 설치·가상환경 ([설치 가이드](https://github.com/astral-sh/uv)) |
| **Docker / Docker Compose** | Compose v2 | 전체 서비스 실행 |
| **Node** | 22 이상 | 프런트엔드 계약 검사 (`node --test`) |
| `curl` · `openssl` | — | `bootstrap-local.sh` 가 사용 |

---

## 🛠️ 빠른 시작 — 한 명령

깨끗하게 clone 한 상태에서:

```bash
./scripts/bootstrap-local.sh
```

이 스크립트가 하는 일 (KEY-228):

1. 사전 도구 검사 (`docker` · `curl` · `openssl` · `python3`, Docker 실행 여부)
2. `.env` 가 없으면 `envs/example.local.env` 를 복사하고 **비밀값을 무작위 생성**
   (`SECRET_KEY` · `DB_PASSWORD` · `MINIO_*` 등). 기존 `.env` 와 볼륨은 절대 건드리지 않는다
3. 포트(3306·6379·8000) 충돌 검사
4. `mysql`·`redis`·`fastapi` 기동 후 health 대기
5. 컨테이너 안에서 `aerich upgrade`
6. 합성 직원 seed (`scripts/seed.py --mode staff`) — 비밀번호는 `.bootstrap.local.env` 에만 저장
7. `check_schema_drift.py` + `smoke.py` 로 health·auth·core 통과 확인

OCR 흐름까지 재현하려면:

```bash
./scripts/bootstrap-local.sh --with-ocr-worker   # minio·ai-worker 추가, MinIO 버킷 초기화
./scripts/bootstrap-local.sh --rebuild           # 이미지 다시 빌드
```

> 생성된 비밀값은 stdout 에 찍히지 않는다. 합성 계정 로그인 값은 `.bootstrap.local.env`
> (Git 무시)에서 확인한다. 팀 공용 시연 계정 비밀번호는 Notion 자격증명 표에 있다
> ([`docs/local-demo-accounts.md`](docs/local-demo-accounts.md)).

---

## 🧰 수동 설치 (스크립트 없이)

### 1. 의존성 설치

```bash
uv sync                                 # 전체
uv sync --group app                     # API 서버만
uv sync --group worker --group ai       # AI 워커용 (worker·ai 둘 다)
```

> **`--group ai` 만으로는 워커가 안 뜬다.** 그 그룹에는 모델 쪽 패키지만 있고
> `tortoise-orm` 이 없어서 `ModuleNotFoundError: No module named 'tortoise'` 로
> 죽는다 (KEY-198 · 도커 경로는 KEY-197).

### 2. 환경변수

```bash
cp envs/example.local.env envs/.local.env
ln -s envs/.local.env .env
```

`envs/.local.env` · `envs/.prod.env` · `.env` 는 `.gitignore` 로 제외된다. **실제 비밀값은
커밋하지 않는다.** 값의 의미는 아래 [환경변수](#-환경변수) 표를 본다.

### 3. 스택 기동

```bash
docker compose up -d --build            # redis · mysql · fastapi (기본 셋)
```

| 명령 | 더 뜨는 것 | 언제 |
|---|---|---|
| `docker compose up -d --build` | (기본 셋) | 앱 코드를 고칠 때 |
| `--profile web` | `nginx` | 브라우저로 화면을 볼 때 |
| `--profile ocr` | `ai-worker` · `minio` | OCR 을 돌려 볼 때 |

```bash
docker compose --profile web --profile ocr up -d --build   # 여섯 개 전부
```

> walking skeleton smoke 와 종단 검사는 화면과 OCR 을 모두 지나므로 **두 프로필을 다** 줘야
> 한다. 프로필 없이 돌리면 「연결 거부」로 죽는다.

### 4. 테이블 생성 + 스키마 대조

```bash
uv run aerich upgrade
uv run python scripts/check_schema_drift.py
```

> `aerich upgrade` 를 건너뛰면 API 호출 시 `OperationalError: Table 'ai_health.users' doesn't exist`.

### 5. 접속

- **FE**: <http://localhost> (`--profile web` 필요, 정적 HTML·CSS·JS)
- **API 문서**: <http://localhost/api/docs> 또는 <http://localhost:8000/api/docs> (Swagger)
- **헬스체크**: `curl -s http://localhost:8000/api/v1/health | python3 -m json.tool`

> `ai-worker` 는 현재 스텁이라 `docker compose ps` 에서 `Restarting` 으로 보일 수 있다 — 정상.

### 6. 개별 실행 (개발용)

```bash
uv run uvicorn app.main:app --reload                       # API
uv run python -m ai_worker.main                            # 워커 (먼저 uv sync --group worker --group ai)
docker compose --profile ocr up -d --build ai-worker       # 워커를 컨테이너로
```

---

## 🔑 환경변수

정본은 [`envs/example.local.env`](envs/example.local.env)(로컬) · [`envs/example.prod.env`](envs/example.prod.env)(운영).
아래는 이름·목적·설정 위치다. **실제 키·비밀번호·토큰은 문서에 적지 않는다.**

### FastAPI / 인증

| 변수 | 목적 | 예시·기본값 |
|---|---|---|
| `ENV` | 실행 환경 (`local`·`dev`·`prod`) | `local` |
| `APP_VERSION` · `AI_WORKER_VERSION` · `WEB_VERSION` | 빌드 이미지 태그 | `v1.0.0` |
| `SECRET_KEY` | JWT 서명 키 | 로컬 전용 무작위값 (bootstrap 이 생성) |
| `COOKIE_DOMAIN` | 하위 도메인 공유 쿠키. 비우면 host-only | (비움) |
| `JWT_ALGORITHM` | JWT 알고리즘 | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 액세스 토큰 수명 | `60` |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | 리프레시 토큰 수명 | `20160` (14일) |
| `TIMEZONE` | 서버 벽시계 시간대 (검사·서버 시계가 어긋나면 날짜 오류) | `Asia/Seoul` |

### DB / Redis

| 변수 | 목적 | Docker | 로컬 직접 실행 |
|---|---|---|---|
| `DB_HOST` | DB 호스트 | `mysql` | `localhost` |
| `DB_PORT` · `DB_EXPOSE_PORT` | DB 포트 / 호스트 노출 포트 | `3306` | `3306` |
| `DB_USER` · `DB_PASSWORD` · `DB_ROOT_PASSWORD` | DB 계정 | 로컬 전용값 (bootstrap 생성) | |
| `DB_NAME` | 스키마 이름 | `ai_health` | |
| `REDIS_HOST` | Redis 호스트 | `redis` | `localhost` |
| `REDIS_PORT` · `REDIS_EXPOSE_PORT` | Redis 포트 / 노출 포트 | `6379` | `6379` |
| `REDIS_DB` | 논리 DB 번호(0~15). 평소 비움. pytest-xdist 병렬 검사용 | `0` |

### 업로드 / OCR

| 변수 | 목적 | 예시·기본값 |
|---|---|---|
| `UPLOAD_DIR` | 업로드 임시 경로 | `/tmp/medical_uploads` |
| `MAX_UPLOAD_SIZE_MB` | 업로드 최대 크기 | `20` |
| `OCR_FIXTURE_FALLBACK` | 판독 워커가 없을 때 합성 결과로 흐름을 잇는 **로컬 전용 스위치**. `prod` 에서 켜면 서버가 안 뜬다 | `false` |
| `CLOVA_OCR_INVOKE_URL` · `CLOVA_OCR_SECRET_KEY` | CLOVA OCR 자격증명. 비우면 fixture fallback (KEY-56) | (비움) |
| `CLOVA_OCR_TIMEOUT_SECONDS` | CLOVA 타임아웃 | `10` |

### OpenAI (환자 챗봇)

| 변수 | 목적 | 예시·기본값 |
|---|---|---|
| `OPENAI_API_KEY` | 환자 챗봇 응답 생성 키 (`app/apis/v1/chatbot_routers.py` 가 읽는 유일한 자리). 비우면 챗봇이 고정 폴백 문구만 답한다. 안내문 생성에는 안 쓰인다 | (비움) |
| `OPENAI_MODEL` | 모델 이름 | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | API 엔드포인트 | `https://api.openai.com/v1` |
| `OPENAI_TIMEOUT_SECONDS` | 타임아웃 | `20` |

### MinIO (합성 EMR 보관)

| 변수 | 목적 | 예시·기본값 |
|---|---|---|
| `MINIO_ROOT_USER` · `MINIO_ROOT_PASSWORD` | MinIO 계정. **비우면 컨테이너가 안 뜬다.** 비밀번호 8자 이상 (KEY-191) | 로컬 전용값 (bootstrap 생성) |
| `MINIO_API_PORT` · `MINIO_CONSOLE_PORT` | 포트 | `9000` · `9001` |

### 문자 발송 (KEY-248)

| 변수 | 목적 | 예시·기본값 |
|---|---|---|
| `SMS_PROVIDER` | `mock`(기본, 자격증명 불필요) 또는 `aligo` | `mock` |
| `ALIGO_KEY` · `ALIGO_USER_ID` · `ALIGO_SENDER_NUMBER` | 알리고 자격증명 (`aligo` 일 때만) | (비움) |
| `ALIGO_BASE_URL` · `ALIGO_TIMEOUT_SECONDS` | 알리고 엔드포인트·타임아웃 | `https://apis.aligo.in` · `10` |
| `MOCK_OTP_CODE` | 로컬에서 OTP 를 고정하고 싶을 때 | (비움) |

### 만들기 중

| 변수 | 목적 | 기본값 |
|---|---|---|
| `CATALOG_DRAFT_MODE` | 대표 처방·약 이름을 고치고 지울 수 있게 함 | `true` |

---

## 🌐 외부 서비스 설정

실제 키·비밀번호는 **로컬 `.env` 에만** 넣는다. 코드·화면·로그·커밋에 남기지 않는다.

- **CLOVA OCR** — NAVER Cloud 콘솔에서 OCR 도메인을 만들고 `Invoke URL` 과 `Secret Key`
  를 받아 `CLOVA_OCR_INVOKE_URL` · `CLOVA_OCR_SECRET_KEY` 에 넣는다. 비워 두면 워커가
  fixture fallback 으로 동작한다 (KEY-56 · 계약: [`docs/decisions/KEY-163-ocr-real-contract.md`](docs/decisions/KEY-163-ocr-real-contract.md)).
- **OpenAI** — 환자 챗봇 응답 생성에 쓴다. `app/apis/v1/chatbot_routers.py` 가 이 키를 읽는
  유일한 자리다. `OPENAI_API_KEY` 를 넣고, 필요하면 `OPENAI_MODEL` · `OPENAI_BASE_URL` 로
  바꾼다. 비우면 챗봇이 고정 폴백 문구만 답하고([`docs/local-demo-accounts.md`](docs/local-demo-accounts.md) §3-7),
  나머지 흐름은 그대로 돈다. **안내문 생성은 이 키를 쓰지 않는다** — 확정 OCR + 승인 문구
  조합이고 LLM 생성은 미착수(KEY-75).
- **MinIO** — 합성 EMR 이미지를 담는다. `--profile ocr` 로 뜨며, 최초 1회
  `minio-init` 이 버킷을 만들고 **익명 접근을 차단**한다. 수동으로 돌릴 때는:

  ```bash
  export MC_HOST_team="http://<사용자>:<비밀번호>@localhost:9000"
  ./scripts/minio_init.sh
  ```

  비밀번호를 인자로 주지 않는다 — `ps` 와 셸 기록에 남는다 (KEY-191 · KEY-174).
  S3 호환이라 Sprint 6 AWS 전환 때 엔드포인트만 바꾼다.

---

## 🗃️ DB migration · seed · 초기화

```bash
uv run aerich upgrade                          # 마이그레이션 적용
uv run python scripts/check_schema_drift.py    # 모델 ↔ 실제 스키마 칸 단위 대조
```

seed 는 세 모드다. 비밀번호는 인자·파일이 아니라 환경변수로만 넘긴다.

```bash
uv run python scripts/seed.py --mode empty                         # 아무것도 안 넣음 (빈 화면 확인용)
SEED_STAFF_PASSWORD=<로컬전용PW> uv run python scripts/seed.py --mode staff   # 병원 2곳 + 직원 15개 (기본값)
SEED_STAFF_PASSWORD=<로컬전용PW> uv run python scripts/seed.py --mode full    # + 환자·진료·처방 전체
```

- `--mode full` 은 `docs/data/synthetic-patients.csv` 가 있어야 한다.
- 로그인 아이디는 `docs/data/synthetic-staff.csv` 에서 온다. `SEED_STAFF_PASSWORD` 로 넘긴
  값이 곧 모든 합성 직원의 비밀번호다. 계정 표는 [`docs/local-demo-accounts.md`](docs/local-demo-accounts.md).
- 운영(`ENV=prod`)에서는 `--mode` 를 반드시 손으로 적어야 하고 `--allow-prod-seed` 가 필요하다.

### 초기화 / 재실행

- **seed 재실행**은 안전하다 (멱등). 스키마만 밀렸으면 `aerich upgrade` 를 다시 돌린다.
- **DB 를 완전히 비우려면** — MySQL 은 볼륨이 비어 있을 때만 새 비밀번호·초기 DB 를 잡으므로:

  ```bash
  docker compose down -v      # 로컬 볼륨(mysql_data 등) 삭제 — DB 데이터가 사라진다
  docker compose up -d --build
  uv run aerich upgrade
  ```

  `bootstrap-local.sh` 는 볼륨을 절대 지우지 않는다. 위 명령은 직접 판단해서 돌린다.

---

## 📄 합성 문서로 OCR → 확정 → 안내 재현

실제 환자 문서는 한 건도 쓰지 않는다. 규격은
[`docs/synthetic-data-spec.md`](docs/synthetic-data-spec.md) · [`docs/ocr-fixtures.md`](docs/ocr-fixtures.md).

1. **OCR 흐름을 켠다** — `./scripts/bootstrap-local.sh --with-ocr-worker` 또는
   `docker compose --profile web --profile ocr up -d --build`.
2. **합성 EMR 이미지를 만든다** (누가 돌려도 같은 바이트, 컨테이너 안에서 렌더 — KEY-190):

   ```bash
   ./scripts/render_ocr_fixture.sh build/ocr-fixtures
   ```

   기대값은 `docs/data/ocr-fixtures/*.toml`, 생성기는 `scripts/make_ocr_fixture.py`.
   만들어진 그림은 커밋하지 않는다.
3. **MinIO 에 올린다** — `minio-init` 이 만든 `ocr-fixtures` 버킷에 콘솔(<http://localhost:9001>)
   또는 `mc` 로 등록한다.
4. **화면에서** 스탭으로 로그인 → 진료 건에 문서 업로드 → 판독 결과 확인(`ocr-review`) →
   환자정보 일치 확인 후 값 수정·**확정** → 안내문 생성 → 의사 승인.
5. **자동으로 확인**하려면 E2E 를 돌린다:

   ```bash
   uv run pytest -q app/tests/e2e/test_key69_real_ocr_journey.py
   ```

---

## 🧪 테스트 및 품질 관리

```bash
./scripts/ci/run_test.sh            # pytest + coverage (MySQL 컨테이너 필요)
./scripts/ci/code_fommatting.sh     # Ruff 포맷 확인
./scripts/ci/check_mypy.sh          # Mypy 타입 검사
```

**프런트엔드 검사** — 별도 도구 없이 Node 만으로 (파일 73개):

```bash
TZ=Asia/Seoul node --test frontend/tests/*.test.js
```

> `TZ` 를 고정하는 이유: 러너 기본값이 `UTC` 라 그대로 두면 「오늘 날짜는 현지 기준」을
> 재는 검사가 아무것도 확인하지 못한다. CI 도 `Asia/Seoul` 로 고정한다.
> 폴더가 아니라 **파일들**을 넘긴다 — Node 22 부터 폴더를 주면 `MODULE_NOT_FOUND` 로 죽는다.

**E2E / smoke**:

```bash
# Walking Skeleton 종단 (로컬 테스트 DB 개발용 값)
DB_PASSWORD=<로컬전용PW> ./scripts/run_key152_e2e.sh
uv run pytest -q app/tests/e2e/                       # 전체 E2E

# 살아 있는 서버 찔러 보기 (health·auth·core)
SMOKE_LOGIN_ID=staff01 SMOKE_PASSWORD=<PW> uv run python scripts/smoke.py http://localhost:8000
```

**API 계약** — DTO·라우터를 바꿨으면:

```bash
uv run --group app python scripts/generate_openapi.py --check
```

---

## 🖥 화면

**화면 정의의 정본은 와이어프레임이다** — [`docs/wireframes/`](docs/wireframes/README.md).
띄운 뒤 <http://localhost/map.html> 이 지금 실제 상태(1 완전 · 2 일부 · 3 화면 없음)와
무엇이 막고 있는지를 적어 둔다 (`frontend/js/frames.js`).

| 화면 | 파일 | 프레임 |
|---|---|---|
| 로그인 · 비밀번호 | `login.html` · `password.html` | `L-1~3` |
| 오늘 목록 · 환자 카드 · 안내문 | `patients.html` | `S1-1~5` · `S1-11~13` · `D1-1~7` |
| 판독 결과 확인 | `ocr-review.html` | `S1-6~10` |
| 관리 (환자 · 발송 예정 · 발송 이력) | `manage.html` | `S2-1~4` |
| 설정 (안내문 · 처방 · 검사 기준선 · 문자 문구) | `settings.html` | `D2-1~5` |
| 의사 승인 | `doctor.html` | `D1-*` |
| 어드민 | `admin.html` | `A1-1~7` |
| 환자 모바일 | `guide.html` · `checkin.html` | `P2~P7` |

**화면 ID 는 팀 공용 이름이다** — 티켓·PR·버그 리포트에서 `S1-6` 처럼 부른다.

### 목업으로 보기

서버 없이 화면만 보려면 주소에 `?mock=1` 을 붙인다. 그 탭에서 유지되고 `?mock=0` 으로
끈다. 목업은 서버보다 관대하지 않게 만든다 — 검사가 그 계약을 지킨다.

---

## 🚀 배포 · 장애 · 보안

README 에는 링크만 둔다. 운영 비밀값과 긴 대응 절차는 정본 문서에 있다.

| 주제 | 문서 |
|---|---|
| Pilot 배포·롤백 절차, 무엇이 준비됐고 무엇이 아닌지 | [`docs/deploy-runbook.md`](docs/deploy-runbook.md) |
| 배포 자동화 스크립트 (`deployment.sh` · `certbot.sh`) | 위 런북 §자동 배포 |
| 배포·보안 회귀 시나리오 | [`docs/qa/KEY-177-deployment-security-regression.md`](docs/qa/KEY-177-deployment-security-regression.md) |
| 롤백 리허설 | [`docs/qa/KEY-185-pilot-rollback-rehearsal.md`](docs/qa/KEY-185-pilot-rollback-rehearsal.md) |
| 민감정보 마스킹·로그 노출 검토 | [`docs/qa/KEY-48-log-masking-review.md`](docs/qa/KEY-48-log-masking-review.md) · [`docs/qa/KEY-25-sensitive-data-regression.md`](docs/qa/KEY-25-sensitive-data-regression.md) |
| 인프라 규모 판단 | [`docs/infra-scale.md`](docs/infra-scale.md) |

---

## 🩹 자주 겪는 오류와 확인 순서

| 증상 | 먼저 확인할 것 |
|---|---|
| `OperationalError: Table 'ai_health.users' doesn't exist` | `uv run aerich upgrade` 를 안 돌렸다 |
| `Unknown column '...'` 이 한참 뒤 엉뚱한 자리에서 | 스키마 드리프트 — `uv run python scripts/check_schema_drift.py` |
| `ModuleNotFoundError: No module named 'tortoise'` (워커) | `uv sync --group worker --group ai` (둘 다). `--group ai` 만으로는 안 된다 |
| OCR·픽스처 검사가 「연결 거부」로 죽음 | `--profile ocr` (또는 `web`+`ocr`) 를 안 줬다 |
| MinIO 컨테이너가 안 뜸 | `MINIO_ROOT_USER`·`MINIO_ROOT_PASSWORD` 가 비었다. 비밀번호 8자 이상 |
| pytest 가 `test` DB 없음 / 비밀번호 불일치로 실패 | 기존 mysql 볼륨이 옛 비밀번호를 잡고 있다 — `docker compose down -v` 후 재기동 (데이터 삭제됨) |
| `node --test` 가 `MODULE_NOT_FOUND` | 폴더 말고 `frontend/tests/*.test.js` 파일 글롭을 넘긴다 |
| 현지 날짜 검사가 항상 통과 | `TZ=Asia/Seoul` 을 안 붙였다 |
| `bootstrap-local.sh` 가 `ENV=local 에서만` 이라며 멈춤 | `.env` 의 `ENV` 가 `local` 이 아니다 |
| 포트 `3306`·`6379`·`8000` 사용 중 | 해당 프로그램 종료 또는 `.env` 의 노출 포트 변경 |

로컬 헬스체크 정본 절차: [`docs/local-health-check.md`](docs/local-health-check.md).

---

## 📝 개발 가이드

- **API 추가**: `app/apis/v1/` 에 라우터 파일을 만들고 `app/apis/v1/__init__.py` 에 등록.
  경로 소유권은 [`docs/router-ownership.md`](docs/router-ownership.md).
- **DB 모델 추가**: `app/models/` 에 Tortoise 모델을 정의하고 모델 목록에 등록한 뒤
  `uv run aerich migrate --name <설명>`. 배치 규칙과 등록 위치는
  [`docs/models-layout.md`](docs/models-layout.md).
- **AI 로직 추가**: `ai_worker/tasks/` 에 처리 로직을 쓰고 `ai_worker/main.py` 에서 호출.
- **화면 추가**: `frontend/` 에 HTML 하나와 `js/` 코드 하나. **셈하고 고르는 규칙은
  IIFE 밖 `*-rules.js` 로 뺀다** — 안에 두면 검사가 못 부른다. 새 화면은
  `frontend/js/frames.js` 의 수준도 함께 고친다.

---

## 📌 기능 PR 문서 동기화 체크리스트

이 README 는 **완료 시점에 몰아서 쓰지 않는다.** 설치·환경변수·migration·seed·실행·검증
절차가 달라지는 PR 은 같은 PR 에서 관련 문서를 함께 고친다 (KEY-279).

기능 PR 을 올릴 때 확인한다:

- [ ] 새 환경변수를 추가했으면 `envs/example.*.env` 와 이 README 의 [환경변수](#-환경변수) 표에 이름·목적·예시를 넣었다 (실제 값은 넣지 않는다)
- [ ] 설치·기동 순서·`docker compose` 프로필·포트가 달라졌으면 README 를 고쳤다
- [ ] migration·seed 절차나 모드가 달라졌으면 README 와 `scripts/seed.py` 도움말을 맞췄다
- [ ] 테스트·smoke·E2E 실행 명령이 달라졌으면 README 의 명령을 고쳤다
- [ ] API 계약을 바꿨으면 `docs/api/*.md` 와 `docs/api/openapi.json` 을 갱신했다
- [ ] 문서 변경이 불필요하면 PR 본문에 그 사유를 적었다
- [ ] 바꾼 문서의 내부 링크와 명령을 실제로 확인했다

> 최종 책임자: 이희진 — README 구조·필수 항목·문서 간 일관성·최종 재현 가능 여부.
> 프로젝트 종료 시 깨끗한 환경에서 1명이 재현 검증을 수행한다.
