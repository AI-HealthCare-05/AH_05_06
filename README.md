# 케어온 — 복약 안내 도우미

다낭성난소증후군·자궁내막증 환자에게 **약을 어떻게 드시는지**를 진료 뒤에도 이어서
안내하는 서비스다. 의원이 종이로 주던 복약 안내를 자동으로 만들고, 환자 휴대폰으로
보내고, 복약 도중 확인 문자를 회차대로 보낸다.

한 진료가 지나가는 길:

```
진료기록 사진 올림 → OCR 판독 → 스탭 확인 → 의사 승인 → 환자에게 문자
                                                          ↓
                                              D+7 · D+15 확인 문자 · 소진 예정 알림
```

**의료 안전이 이 저장소의 첫 규칙이다.** 안내문에 들어가는 의학 문장은 지어내지
않고, 판독이 못 읽은 값은 비워 두며(0 이나 「-」로 채우지 않는다), 의사 승인 없이는
환자에게 아무것도 나가지 않는다.

---

## 🚀 무엇으로 만들었나

- **FastAPI + Tortoise ORM** — 비동기 API 서버와 DB 모델
- **AI Worker** — OCR 판독을 API 서버와 분리해 처리
- **프런트엔드 — 빌드가 없다.** HTML·CSS·ES5 JavaScript 를 `<script src>` 로 그대로
  싣는다. 번들러도 `node_modules` 도 잠금파일도 없다. 그래서 파일을 고치고 새로고침하면
  끝이고, 대신 전역 이름이 곧 주소라 **이름이 겹치면 서로를 덮는다**(검사가 막는다)
- **UV Package Manager** — 의존성 설치와 가상환경
- **Docker-Compose** — MySQL · Redis · Nginx 를 포함한 스택을 한 번에
- **CI/CD Scripts** — Ruff · Mypy · Pytest 자동화

---

## 📂 프로젝트 구조

```text
.
├── ai_worker/          # AI 모델 추론 및 학습 관련 코드 (Worker)
│   ├── core/           # 워커 설정 및 로거
│   ├── models/         # AI 모델 파일 보관 (PyTorch 등)
│   ├── tasks/          # 실제 처리할 작업 정의
│   └── main.py         # 워커 진입점
├── app/                # FastAPI 서버 코드
│   ├── apis/           # API 라우터 (v1 버전 관리)
│   ├── core/           # 서버 설정 (pydantic-settings), DB 설정, JWT, Validator 등 핵심 기능
│   ├── dtos/           # 데이터 전송 객체 (Pydantic models)
│   ├── models/         # DB 테이블 정의
│   ├── services/       # 비즈니스 로직
│   └── main.py         # FastAPI 애플리케이션 진입점
├── envs/               # 환경 변수 파일 관리
│   ├── example.local.env   # 로컬 환경변수 예시 (버전 관리됨)
│   └── example.prod.env    # 운영 환경변수 예시 (버전 관리됨)
├── frontend/           # 화면 — 빌드 없는 HTML·CSS·ES5 JS
│   ├── *.html          # 화면 하나에 파일 하나 (login · patients · ocr-review · manage · settings …)
│   ├── css/            # 화면별 + 공용(tokens · style · shell · blocks)
│   ├── js/             # 화면 코드와 **순수 규칙 파일**(`*-rules.js` — 검사가 부른다)
│   └── tests/          # `node --test` 계약 검사. 새 의존성 없이 돈다
├── infra/              # 인프라 설정 관련 디렉터리
│   ├── docker/         # Docker Compose 설정 (운영용)
│   └── nginx/          # Nginx 설정 파일 (리버스 프록시)
├── scripts/            # 배포 및 CI용 쉘 스크립트
├── docker-compose.yml  # 로컬 개발용 서비스 실행 설정
└── pyproject.toml      # uv 기반 의존성 관리 설정
```

---

## ⚙️ 사전 준비 사항

- **Python**: 3.13 이상 (로컬 개발 환경용)
- **UV**: Python 패키지 매니저 ([설치 가이드](https://github.com/astral-sh/uv))
- **Docker & Docker-Compose**: 전체 서비스 실행용

---

## 🛠️ 설치 및 설정

### 1. 가상환경 구축 및 의존성 설치

`uv`를 사용하여 프로젝트에 필요한 패키지를 설치합니다.

```bash
# 의존성 설치 (가상환경 자동 생성)
uv sync

# 특정 그룹의 의존성만 설치하려는 경우
uv sync --group app                    # API 서버용
uv sync --group worker --group ai      # AI 워커용
```

> **`--group ai` 만으로는 워커가 안 뜬다.** 그 그룹에는 모델 쪽 패키지만 있고
> `tortoise-orm` 이 없어서 `ModuleNotFoundError: No module named 'tortoise'` 로
> 죽는다. 예전 안내가 그렇게 적혀 있어 그대로 따라 하면 막혔다 (KEY-198).
> 도커 경로는 KEY-197 에서 같은 이유로 고쳤다.

### 2. 환경 변수 설정

`envs/` 디렉토리의 예시 파일을 복사한 뒤 루트의 `.env`에 심볼릭 링크로 연결합니다.

- 로컬용
    ```bash
    cp envs/example.local.env envs/.local.env
    ln -s envs/.local.env .env
    ```
- 배포용
    ```bash
    cp envs/example.prod.env envs/.prod.env
    ln -s envs/.prod.env .env
    ```

> `envs/.local.env`, `envs/.prod.env`, `.env`는 `.gitignore`에 의해 버전 관리에서 제외됩니다. 실제 비밀값은 절대 커밋하지 마세요.

복사된 파일의 환경변수를 프로젝트 상황에 맞게 수정하세요.

| 변수 | 설명 | Docker 실행 | 로컬 직접 실행 |
|---|---|---|---|
| `DB_HOST` | DB 접속 호스트 | `mysql` | `localhost` |
| `REDIS_HOST` | Redis 접속 호스트 | `redis` | `localhost` |

---

## 🏃 실행 방법

### 1. 로컬 및 개발 환경

#### Docker Compose로 전체 스택 실행

모든 서비스(API, Worker, DB, Redis, Nginx)를 한 번에 실행합니다.

> **⚠️ 기존 팀원 주의**: `.env`의 DB 비밀번호가 변경되었거나 `test` DB가 없어 pytest가 실패하는 경우, MySQL은 볼륨이 비어 있을 때만 새 비밀번호와 초기 DB 설정이 적용됩니다. 기존 볼륨이 있으면 아래 명령으로 먼저 제거하세요.
> ```bash
> docker compose down -v   # 기존 볼륨 삭제 (DB 데이터 초기화됨)
> ```

```bash
docker-compose up -d --build
```

컨테이너가 뜬 후 최초 1회(또는 마이그레이션 파일이 추가된 경우) 테이블을 생성합니다.

```bash
uv run aerich upgrade
```

> **참고**: 이 단계를 건너뛰면 API 호출 시 `OperationalError: Table 'ai_health.users' doesn't exist` 오류가 발생합니다.

올린 뒤 **모델과 맞는지 확인**합니다.

```bash
uv run python scripts/check_schema_drift.py
```

`/api/v1/health` 는 `SELECT 1` 만 보기 때문에 **스키마가 밀려 있어도 `ok`** 를 줍니다.
그래서 조용히 밀린 채로 검증을 돌리게 되고, 한참 뒤에 엉뚱한 자리에서
`Unknown column '...'` 로 터집니다. 이 명령은 표뿐 아니라 **칸 단위로** 대조합니다 —
표 개수는 맞는데 칸이 비어 있는 경우가 실제로 있었습니다 (KEY-198).

실행 후 다음 주소로 접속 가능합니다:
- **FE**: [http://localhost](http://localhost) (정적 HTML·CSS·JS)
- **API 서버**: [http://localhost/api/docs](http://localhost/api/docs) (Swagger UI)
- **Nginx**: 80 포트를 통해 FE 정적 파일 서빙 및 API 서버 프록시를 처리합니다.

> **참고**: `ai-worker`는 현재 스텁 상태(실행 후 즉시 종료)입니다. `restart: always` 설정으로 인해 `docker compose ps`에서 `Restarting`으로 표시될 수 있으나 정상입니다.

#### 로컬에서 개별 실행 (개발용)

**FastAPI 서버 실행:**
```bash
uv run uvicorn app.main:app --reload
# or
docker compose up -d --build app
```

**AI Worker 실행:** (먼저 `uv sync --group worker --group ai`)
```bash
uv run python -m ai_worker.main
# or
docker compose up -d --build ai_worker
```

### 2. EC2 배포 환경 (Production)

제공된 쉘 스크립트를 사용하여 AWS EC2 환경에 이미지를 빌드, 푸시 및 배포할 수 있습니다.

#### 사전 준비
- EC2 인스턴스 (Ubuntu 권장)
- SSH 키 페어 (`~/.ssh/` 경로에 위치)
- 도커 허브(Docker Hub) 계정 및 Personal Access Token
- 배포용 환경 변수 설정 (`envs/.prod.env`)
- 도메인 구매 (Gabia, GoDaddy, AWS Route53 등)

#### 자동 배포 스크립트 실행
`scripts/deployment.sh`는 도커 이미지 빌드, 레포지토리 푸시, EC2 접속 및 컨테이너 실행 과정을 자동화합니다.

```bash
chmod +x scripts/deployment.sh
./scripts/deployment.sh
```
스크립트 실행 시 다음 정보를 입력해야 합니다:
1. 도커 허브 계정 정보 (Username, PAT)
2. 이미지를 업로드할 레포지토리 이름
3. 배포할 서비스 선택 (FastAPI, AI-Worker) 및 버전(Tag)
4. SSH 키 파일명 및 EC2 IP 주소
5. https 사용여부
   - 5-1. https인 경우 도메인 추가 입력  

#### SSL(HTTPS) 설정 (Certbot)
도메인을 연결하고 HTTPS를 적용하려면 `scripts/certbot.sh`를 사용합니다.

```bash
chmod +x scripts/certbot.sh
./scripts/certbot.sh
```
1. 도메인 주소 및 이메일 입력
2. SSH 키 파일명 및 EC2 IP 주소 입력
3. Let's Encrypt를 통한 인증서 발급 및 Nginx 설정 자동 갱신 적용

---

## 🧪 테스트 및 품질 관리

제공된 스크립트를 사용하여 코드의 품질을 검증할 수 있습니다.

```bash
# 서버 테스트
./scripts/ci/run_test.sh

# 코드 포맷팅 확인 (Ruff)
./scripts/ci/code_fommatting.sh

# 정적 타입 검사 (Mypy)
./scripts/ci/check_mypy.sh
```

**프런트엔드 검사**는 별도 도구 없이 Node 만으로 돈다.

```bash
TZ=Asia/Seoul node --test frontend/tests/*.test.js
```

> `TZ` 를 고정하는 이유: 러너 기본값이 `UTC` 라 그대로 두면 현지 시각 getter 와 UTC
> getter 가 같은 값을 내서 **「오늘 날짜는 현지 기준이다」를 재는 검사가 아무것도
> 확인하지 못한다.** CI 도 `Asia/Seoul` 로 고정한다.

> 폴더가 아니라 **파일들**을 넘긴다. Node 22 부터 `--test` 의 위치 인자를 훑을 폴더가
> 아니라 불러올 모듈로 보기 때문에, 폴더를 주면 `MODULE_NOT_FOUND` 로 죽는다.

---

## 🖥 화면

**화면 정의의 정본은 와이어프레임이다** — [`docs/wireframes/`](docs/wireframes/README.md).
화면 질문이 생기면 코드가 아니라 거기를 먼저 본다. 프레임마다 「왜 이렇게 생겼는가」가
화면 옆에 적혀 있다.

**지금 어디까지 됐는지는 화면 지도가 안다** — 띄운 뒤 <http://localhost/map.html>.
64프레임을 수준(1 완전 · 2 일부 · 3 화면 없음)과 **무엇이 막고 있는지**로 적어 둔
표다(`frontend/js/frames.js`). 이 표는 **지금 실제 상태**만 적는다 — 목표를 여기
적지 않는다.

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

**화면 ID 는 팀 공용 이름이다.** 티켓·PR·버그 리포트에서 `S1-6` 처럼 부른다.

### 목업으로 보기

서버 없이 화면만 보려면 주소에 `?mock=1` 을 붙인다. 그 탭에서 유지되고, `?mock=0` 으로
끈다. **목업은 서버보다 관대하지 않게 만든다** — 목업에서만 되는 화면은 붙이는 날
조용히 빈다. 검사가 그 계약을 지킨다.

---

## 📝 개발 가이드

- **API 추가**: `app/apis/v1/` 아래에 새로운 라우터 파일을 생성하고 `app/apis/v1/__init__.py`에 등록하세요.
- **DB 모델 추가**: `app/models/`에 Tortoise 모델을 정의하고 `app/db/databases.py`의 `MODELS` 리스트에 추가하세요.
- **AI 로직 추가**: `ai_worker/tasks/`에 새로운 처리 로직을 작성하고 `ai_worker/main.py`에서 호출하도록 구성하세요.
- **화면 추가**: `frontend/` 에 HTML 하나와 `js/` 코드 하나. **셈하고 고르는 규칙은
  IIFE 밖 `*-rules.js` 로 뺀다** — 안에 두면 검사가 못 부르고, 그 규칙이 틀렸을 때
  브라우저에서 눈으로만 발견된다. 새 화면은 `frontend/js/frames.js` 의 수준도 함께 고친다.
