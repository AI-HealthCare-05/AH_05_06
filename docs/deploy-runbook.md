# Pilot 배포·롤백 런북 (`KEY-174`)

> 2026-08-25 작성 · 부모 `KEY-144` [9/17] 배포·보안·운영 Pilot 검증
>
> **이 문서는 「지금 저장소로 무엇을 할 수 있는가」를 적는다.** 아직 못 하는
> 것은 마지막 절에 그대로 적어 두었다 — 형제 일감(`KEY-175`·`176`·`177`)이
> 이 환경 위에서 검증하겠다고 했으므로, 무엇이 준비됐고 무엇이 아닌지가
> 그쪽 계획에 바로 걸린다.

## 1. 무엇이 준비돼 있나

```text
infra/docker/docker-compose.prod.yml   fastapi · mysql · redis · nginx · certbot
infra/nginx/prod_http.conf             HTTP 전용 (인증서 받기 전)
infra/nginx/prod_https.conf            HTTPS (인증서 받은 뒤)
scripts/lib.sh                         두 스크립트가 함께 쓰는 조각
scripts/deployment.sh                  이미지 빌드·푸시 → EC2 배포
scripts/certbot.sh                     Let's Encrypt 인증서 발급
envs/example.prod.env                  운영 환경변수 이름표
```

배포는 **로컬에서 스크립트를 돌려 EC2 로 미는** 모양이다. CI 가 배포하지
않는다 — `.github/workflows/` 에는 `checks.yml`(lint·test)과
`pr-reviewer-from-body.yml` 뿐이다.

## 2. 비밀값 경계

**저장소에 들어가는 것은 이름뿐이다.** 값은 `envs/.prod.env` 에 두고 그 파일은
`.gitignore` 에 있다.

| 어디 | 무엇 | 어떻게 |
|---|---|---|
| `envs/.prod.env` | DB·JWT·쿠키 설정 | 저장소 밖. 배포 때 `scp` 로 EC2 의 `~/project/.env` 로 간다 |
| Docker Hub PAT | 이미지 푸시·풀 | **파일에 안 쓴다.** `DOCKER_PAT` 환경변수 또는 가려진 입력 |
| SSH 키 | EC2 접속 | `~/.ssh/` — 저장소 밖 |
| Let's Encrypt | 인증서·개인키 | EC2 안 `certbot-conf` 볼륨 |

### PAT 이 화면·로그에 안 남는 이유

`scripts/deployment.sh` 가 세 가지를 지킨다 (`KEY-174` 에서 고쳤다).

```bash
read -r -s -p "password (PAT, 화면에 안 보입니다): " DOCKER_PAT   # 안 찍힌다
printf '%s' "${docker_pw}" | docker login --password-stdin        # ps 에 안 남는다
remote_deploy_payload "$pat" | ssh … bash -s                      # 원격 ps 에 안 남는다
```

예전 판은 `read -p`(그대로 찍힘) · `docker login -p`(경고 + `ps` 노출) ·
`ssh "DOCKER_PAT=… bash -s"`(원격 `ps` 노출) 셋 다 걸렸다.

**한 번 더 고쳤다.** 그 사이 판은 PAT 를 스크립트보다 **먼저** 한 줄로 얹었는데,
`bash -s` 는 stdin 을 스크립트로 읽으므로 그 줄을 명령으로 실행하려다
`command not found` 로 **stderr 에 그대로 흘렸고**, 뒤의 `read` 는 PAT 대신 다음
스크립트 줄을 삼켰다 — 막으려던 노출을 만들면서 **배포는 100% 실패했다.**
지금은 PAT 를 스크립트 본문 안 heredoc 으로 넘긴다 (`scripts/lib.sh`).

**환경변수로 미리 주면 묻지 않는다** — CI 에서 비대화형으로 돌릴 수 있다.

```bash
DOCKER_USERNAME=... DOCKER_PAT=... ./scripts/deployment.sh
```

### 서버가 조용히 뜨지 않게

`app/core/config.py` 가 둘을 이름 대며 막는다.

```text
DB_PASSWORD    비어 있으면 멈춘다 (KEY-110)
SECRET_KEY     운영에서 기본값·자리표시자면 멈춘다 (KEY-174)
```

`SECRET_KEY` 기본값은 **프로세스마다 다르다.** 안 채우고 뜨면 재배포할 때마다
발급한 토큰이 전부 죽어 「갑자기 로그아웃됐다」가 된다.

예시 파일에 적힌 자리표시자(`change-me-…`)도 같이 막는다. `DB_PASSWORD` 와 달리
**값이 있어 보여서 안 채우고 넘어가기 쉽고**, 그렇게 뜨면 서버는 조용히 살아나
공개 저장소에 적힌 값으로 JWT 를 서명한다.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 서버에 올라간 `.env`

`scp` 는 로컬 파일의 권한을 그대로 안 옮긴다. 그래서 **올린 직후에 잠근다.**

```bash
scp … envs/.prod.env ubuntu@<ip>:~/project/.env
ssh … "chmod 600 ~/project/.env"      # 이 순서다. 나중에 잠그면 그 사이가 열려 있다
```

`scripts/deployment.sh` 가 이 둘을 붙여서 한다. 손으로 올릴 때도 같이 한다 —
이 파일에는 `DB_PASSWORD` 와 `SECRET_KEY` 가 들어 있다.

## 3. 배포 절차

```bash
# 0. 환경변수 준비 — 이름표를 베껴 값을 채운다
cp envs/example.prod.env envs/.prod.env
$EDITOR envs/.prod.env          # SECRET_KEY·DB_PASSWORD 는 반드시

# 1. 배포
./scripts/deployment.sh
#    묻는 것: 빌드할 서비스 · EC2 IP · SSH 키 파일 · HTTP/HTTPS · (도메인)
#    PAT 은 가려진 입력으로 받는다

# 2. 처음 한 번만 — 인증서
./scripts/certbot.sh
```

스크립트가 하는 일은 이렇다.

1. 고른 서비스의 이미지를 빌드해 Docker Hub 로 민다
2. `envs/.prod.env` → EC2 `~/project/.env`
3. `infra/docker/docker-compose.prod.yml` → EC2 `~/project/docker-compose.yml`
4. nginx 설정의 `server_name` 을 IP/도메인으로 바꿔 EC2 로
5. EC2 에서 `docker compose up -d --pull always` 후 옛 이미지 정리

## 4. 롤백

`docker compose up -d --pull always` 는 **태그가 가리키는 이미지**를 받는다.
그래서 되돌리는 길은 **태그를 되돌리는 것**이다.

```bash
# EC2 에서
cd ~/project
docker compose down

# 이전 버전 태그로 되돌린다 — .env 의 APP_VERSION 을 고친다
sed -i "s/^APP_VERSION=.*/APP_VERSION=<직전 버전>/" .env
docker compose up -d --pull always
```

**전제: 직전 버전 이미지가 Docker Hub 에 남아 있어야 한다.** 배포 스크립트가
EC2 에서 `docker image prune -af` 를 돌리므로 **로컬 캐시로는 못 되돌린다.**
Hub 의 태그가 유일한 되돌림 지점이다.

`APP_VERSION` 을 매 배포마다 올리지 않고 `latest` 로만 밀면 되돌릴 자리가
없어진다 — **버전을 붙여 미는 것이 롤백 계획의 전부다.**

DB 는 별개다. 마이그레이션을 되돌리려면 `aerich downgrade` 이고, 그건
`docs/migrations/` 를 따른다. **`--delete` 를 쓰지 않는다** — 마이그레이션
파일 자체가 지워진다.

## 4-2. 보안 그룹은 웹 둘만 연다 (KEY-192)

운영 compose 가 밖으로 여는 것은 **nginx 의 80·443 뿐**이다. MySQL · Redis ·
FastAPI · MinIO 는 `127.0.0.1` 에 묶여 있다.

| 열 것 | 왜 |
|---|---|
| `22` | SSH — 배포와 터널에 쓴다. 가능하면 팀 IP 만 |
| `80` | 지금은 http 로 먼저 띄운다 |
| `443` | 인증서를 붙인 뒤 |

**`3306` · `6379` · `8000` · `9000` · `9001` 은 열지 않는다.** 열어도 컨테이너가
`127.0.0.1` 에만 붙어 있어 안 닿지만, 두 겹으로 막는다 — 한쪽을 고치는 사람이
다른 쪽을 모를 수 있다. 안을 들여다볼 때는 SSH 터널을 쓴다.

```bash
ssh -N -L 13306:127.0.0.1:3306 -L 19000:127.0.0.1:9000 ubuntu@<서버>
```

### 포트 변수는 안쪽과 바깥이 갈려 있다

```text
DB_PORT           앱이 붙는 포트 · 컨테이너가 실제로 듣는다 (--port=…)
DB_EXPOSE_PORT    호스트에 붙일 번호

REDIS_PORT        같은 뜻 (redis-server --port …)
REDIS_EXPOSE_PORT 같은 뜻 · 안 적으면 6379
```

**바깥 번호를 바꾼다고 안쪽이 바뀌지 않는다.** 예전에는 redis 만 `REDIS_PORT`
하나가 두 자리를 겸해서, 호스트 번호를 6379 아닌 값으로 두면 앱이
`redis:<그 값>` 으로 붙으려다 실패했다 — health 가 `redis: connection_failed`
였다 (KEY-193). 지금은 갈려 있다.

### 확인은 `/api/v1/health` 로 한다

팀 노션의 배포 가이드 7단계는 `http://<IP>/api/docs` 로 확인하라고 하는데,
**운영에서는 Swagger 가 꺼져 있다**(`app/main.py:24-26` — `docs_url=None`).
그대로 따라가면 404 를 보고 배포가 실패한 줄 안다.

```bash
curl -fsS http://<IP>/api/v1/health | jq .     # api·db·redis 가 다 ok 인가
curl -sI  http://<IP>/                         # 프런트 화면 (KEY-189)
```

## 4-3. 합성 데이터를 붓는다 (KEY-200)

**배포는 데이터를 넣지 않는다.** `deployment.sh` 는 `seed` 를 부르지 않고, 앞으로도
부르지 않는다 — 배포가 곧 시딩이 되면 언젠가 진짜 운영 DB 에 합성 환자가 들어간다.
그래서 이 절은 **사람이 손으로 한 번 돌리는 자리**로 남겨 둔다.

`scripts/seed.py` 는 `ENV=prod` 에서 스스로 멈춘다. Pilot 은 「운영처럼 뜨지만
합성 데이터로 도는 환경」이라 그 가드와 정면으로 부딪힌다. 문을 없애지 않고
**좁은 문 하나**를 냈다.

### 🔴 `scripts/seed.py` 는 앱 이미지 안에 없다

`app/Dockerfile` 이 복사하는 것은 셋뿐이다 — `pyproject.toml` · `uv.lock` · `./app`.
그래서 `docker compose exec fastapi … scripts/seed.py` 는 **서버에서 못 돈다.**
실제로 돌고 있는 컨테이너에 물어 확인했다.

```text
$ docker exec fastapi ls /app/scripts/seed.py
ls: cannot access '/app/scripts/seed.py': No such file or directory
```

`docs/data/*.csv`(합성 환자·직원)도 없다. 이미지가 가벼운 것은 의도된 것이라
(운영 이미지에 시딩 도구를 두지 않는다) **넣지 말고 그때만 밀어 넣는다.**

```bash
# 서버에서. 스키마가 먼저 올라가 있어야 한다 (4. 롤백 아래 「마이그레이션」 참고).

# ① 시딩에 필요한 것만 컨테이너로 밀어 넣는다
#    `docker cp` 는 대상 디렉터리를 안 만든다 — 없으면
#    「Could not find the file /app/scripts」로 죽는다. 먼저 만든다.
docker compose exec -T fastapi mkdir -p /app/scripts /app/docs
docker cp scripts/seed.py fastapi:/app/scripts/seed.py
docker cp docs/data      fastapi:/app/docs/

# ② 돌린다 — 플래그와 비밀번호는 **이 줄에만** 적는다
SEED_ALLOW_PROD=1 SEED_STAFF_PASSWORD='<합성 비밀번호>' \
  docker compose exec -T \
    -e SEED_ALLOW_PROD -e SEED_STAFF_PASSWORD \
    fastapi uv run --no-sync python scripts/seed.py --mode full

# ③ 끝나면 도로 치운다 — 운영 이미지에 시딩 도구를 남기지 않는다
docker compose exec -T fastapi rm -rf /app/scripts /app/docs
```

두 가지가 안 하면 죽는 자리다. 셋 다 로컬에서 그대로 밟아 확인했다.

```text
docker compose exec 는 호스트 환경변수를 자동으로 안 넘긴다
  -e 없이  →  컨테이너가 본 값: 없음   (seed 가 「SEED_STAFF_PASSWORD 환경변수가 없습니다」로 종료)
  -e 주면  →  컨테이너가 본 값: 있음

그냥 `python` 은 시스템 파이썬이라 의존성이 없다
  python scripts/seed.py            →  ModuleNotFoundError: No module named 'tortoise'
  uv run --no-sync python …         →  [seed] 완료
```

`--no-sync` 는 이미지 `CMD` 와 같은 꼴이다 — 컨테이너 안에서 다시 설치하지 않는다.

```text
⚠ ENV=prod 시딩 허용됨 (SEED_ALLOW_PROD) — Pilot/합성 전용
```

이 배너가 stderr 에 뜨면 문이 열린 것이다. 안 뜨면 안 열린 것이니 아래를 본다.

### 🔴 플래그를 `.env` 에 적지 않는다

**명령줄에 그때그때 붙인다.** 파일에 적으면 두 가지가 한꺼번에 어긋난다.

```text
envs/.prod.env 에 적으면   deployment.sh 가 그 파일을 ~/project/.env 로 올린다
                          → 배포할 때마다 따라 올라가 서버에 영구히 켜져 있다
~/project/.env 에 적으면   다음 배포가 덮어쓰기 전까지 남아 있다
```

#### 🔴 파일에 적으면 **서버에서는 켜진다** — 가드가 못 막는다

앞 판의 이 문서는 「`.env` 에 적어도 안 켜진다」고 적어 두었다. **그건 틀렸다.**
한금준 님이 `#158` 에서 짚었고, 재현해서 확인했다.

```text
docker-compose.prod.yml:55  fastapi     env_file: .env
docker-compose.prod.yml:81  ai-worker   env_file: .env

  .env 에 SEED_ALLOW_PROD=1 을 적고 컨테이너를 다시 만들면
  → os.environ.get("SEED_ALLOW_PROD") == "1"      ← 문이 열린다
```

`env_file` 은 **도커가 진짜 환경변수로 실어 준다.** 파이썬이 시작하기 전 일이라
`os.environ` 만 보는 가드로는 구별할 수가 없다.

호스트에서 `python scripts/seed.py` 를 그냥 돌릴 때는 여전히 안 열린다 — 그때는
`Config` 가 `.env` 를 흡수할 뿐 `os.environ` 에는 안 들어간다. 검사가 못박은 것은
**그 경우뿐**이다 (`test_a_flag_only_in_the_env_file_does_not_open_it`).

그러니 서버에서는 규칙으로 지킨다.

* `envs/.prod.env` 와 서버 `~/project/.env` 에 `SEED_ALLOW_PROD` 를 **적지 않는다**
* 시딩할 때만 명령줄에 붙인다 (`docker compose exec -e SEED_ALLOW_PROD …`)
* 시딩이 끝나면 그 셸을 닫는다 — 변수는 그 명령에만 산다

명령줄이어야만 열리게 코드를 고치는 길(예: `--allow-prod` 를 argv 로 요구)도 있다.
`env_file` 은 argv 를 못 만들기 때문이다. 다만 한금준 님이 「해결 방식을 바로
정하기보다 재현 결과를 공유하고 가드레일 변경 여부를 합의하자」고 했으므로 **팀
합의 뒤에** 손댄다. 지금은 사실만 정확히 적어 둔다.

### 운영에서는 `--mode` 를 적어야 한다

로컬에서는 `--mode` 를 빼면 `staff` 로 간다. **`ENV=prod` 에서는 안 된다** — 무엇을
부을지 사람이 한 번 더 적게 한다. 안 적으면 나중에 무엇이 들어갔는지 아무도 모른다.

| `--mode` | 무엇이 들어가나 |
|---|---|
| `empty` | 아무것도 안 넣는다 (연결만 확인) |
| `staff` | 병원 2 · 직원 17 · 처방세트 8 · 주의문구 13 |
| `full` | 거기에 합성 환자 100 · 진료 · 처방 |

Pilot 로그인만 필요하면 `staff` 로 충분하다. 시연·QA 까지 보려면 `full` 이다.

### 값을 정확히 쓴다

`1` 과 `true` 만 문을 연다 (앞뒤 공백은 털고 대소문자는 안 가린다).
`yes` · `Y` · `2` 는 **안 열린다** — 오타가 운영 DB 를 여는 열쇠가 되면 안 된다.

### KEY-176 smoke 용 fixture 를 함께 심는다

`--mode full` 은 KEY-176 smoke 가 쓸 **승인 완료 안내 1건 + 미제출 D+7 상태**를
같이 만든다. 단 링크 토큰을 넘겨야 선다.

```bash
# 위 4-3 의 ①(mkdir + docker cp)을 먼저 한 상태에서.
SEED_ALLOW_PROD=1 \
SEED_STAFF_PASSWORD='<합성 비밀번호>' \
SEED_SMOKE_LINK_TOKEN='<직접 정한 토큰>' \
  docker compose exec -T \
    -e SEED_ALLOW_PROD -e SEED_STAFF_PASSWORD -e SEED_SMOKE_LINK_TOKEN \
    fastapi uv run --no-sync python scripts/seed.py --mode full
```

```text
[smoke] 시나리오=SYN-BULK-020 차트=08424 visit_id=50 안내문=1 제출초기화=0 …
[smoke] PATIENT_SMOKE_VISIT_ID=50 로 쓰세요 (토큰은 넣어 주신 값 그대로).
```

**토큰은 시드가 만들지 않는다.** DB 에는 sha256 만 남고 원문은 발급 응답 한 번뿐이라,
시드가 만들면 알려 줄 길이 출력밖에 없고 그러면 **로그에 환자 링크 토큰이 남는다**.
직접 정해 넘기고, 같은 값을 smoke 의 `PATIENT_SMOKE_LINK_TOKEN` 에 넣는다.

시연이 쓰는 `SYN-EMS-01`(차트 12401) 과 **일부러 다른 건**이다 — smoke 는 제출로
fixture 를 소진하므로 같은 건을 쓰면 시연 시나리오가 오염된다.

### fixture 를 다시 심는다 (소진된 뒤)

smoke 가 ⑤ 에서 제출하면 fixture 가 **소진된다** — 제출 기록은 안내문당 하나뿐이라
두 번째 제출은 409 다. 같은 명령을 다시 돌리면 된다.

```text
[smoke] … 제출초기화=1 …      ← 이 숫자가 1 이면 지난 제출을 지우고 다시 세운 것이다
```

링크 만료(72 시간)도 함께 다시 밀린다. 이틀 넘게 두었다가 돌리면 밀지 않는 한
`410 LINK_EXPIRED` 가 난다.

### 다시 돌려도 안전하다

`seed.py` 는 전부 `get_or_create` 라 같은 명령을 여러 번 돌려도 쌓이지 않는다.
비밀번호를 바꾸고 다시 돌리면 직원 계정의 비밀번호가 갱신된다.

## 5. Smoke test

배포한 뒤 **기계가 세 자리를 찔러 본다** (KEY-184).

**계정은 `staff01` 을 쓴다** (KEY-192). 합성 직원 17 명 중 자격을 갖춘 것은
열이지만 아무거나 고르면 안 된다 — 아래 「고르면 안 되는 것」 참고.

```bash
export SMOKE_LOGIN_ID=staff01
export SMOKE_PASSWORD=<합성 비밀번호>      # 인자로 주지 않는다 — ps · CI 로그에 남는다
                                          # 값은 시딩할 때 넣은 것이다 (`SEED_STAFF_PASSWORD`).
                                          # 저장소·Jira·채팅 어디에도 안 적는다.

uv run python scripts/smoke.py https://<도메인>
echo $?        # 0 이면 통과, 1 이면 어느 자리가 왜 어긋났는지 위에 찍힌다
```

| 자리 | 무엇을 보나 |
|---|---|
| `health` | `GET /api/v1/health` — api·db·redis 가 **다** ok 인가 |
| `auth` | 합성 계정으로 `access_token` 을 받나 |
| `core` | 그 토큰으로 `GET /api/v1/front-desk/visits` 가 200 인가 |

### 고르면 안 되는 계정

**의원은 `H1` 이다.** 합성 환자 100 명이 전부 여기 있고, 시연이 보는 것도
여기다. 다른 의원 계정을 쓰면 smoke 는 **통과하는데 아무것도 증명하지
못한다** — H2 스탭이 H2 진료를 읽으니 초록이 뜬다.

같은 CSV 에 **눈으로는 통과하는데 쓰면 안 되는** 계정이 여섯 있다. 셋은
합성 직원 CSV 가 `★` 로 「전용」이라고 표시해 둔 것이다.

| 계정 | 왜 안 되나 |
|---|---|
| `lock01` | `★` 5 회 실패 잠금 전용. smoke 가 비밀번호를 한 번 틀리면 그 시험이 못 돈다 |
| `adminstaff01` | `★` 의료 승인 차단 검사 전용 |
| `newbie01` | `★` 첫 로그인 검사 전용. 게다가 비밀번호를 바꿔야 해 **auth 가 막힌다** |
| `newdoc01` | 비밀번호를 바꿔야 한다 — 같은 이유로 auth 가 막힌다 |
| `staff21` | 다른 의원(H2) |
| `doctor21` | `★` 동명이인 검사 전용 · 다른 의원(H2) |

반대로 `staff01` · `doctor01` · `doctor02` · `both01` · `admindoc01` ·
`allthree01` 은 조건을 다 갖췄다. 그중 **`staff01`** 을 쓴다 — CSV 가 스스로
「기준 스탭 — L-1 로그인의 표준 계정. 다른 시험의 기본값으로 쓴다」고 적어
둔 계정이다.

이 목록은 `app/tests/deploy/test_pilot_deploy_contract.py` 가 CSV 에서 다시
계산해 대조한다. 계정이 늘거나 `★` 가 붙으면 여기가 먼저 운다.

### smoke 계정이 갖춰야 하는 것

**로그인만 되면 되는 것이 아니다.** `core` 는 `require_patient_read` 를 지나므로
계정에 아래 둘이 다 있어야 한다 (`app/dependencies/patient_access.py`).

```text
hospital_id   배정돼 있어야 한다. 없으면 403
역할          PATIENT_READ 를 가진 역할(STAFF·DOCTOR)
```

둘 중 하나가 빠지면 `core` 가 **「로그인은 됐는데 권한이 없다」**로 끝난다 —
배포가 아니라 계정 설정 문제라는 뜻이다. 401(토큰 문제)과 사유가 갈려 있으니
어느 쪽인지 보고 고친다.

앞이 어긋나면 뒤는 안 부른다 — 로그인 실패가 「DB 가 죽었다」를 덮지 않게 한다.

**진단은 정해진 어휘로만 나간다.** 응답 본문·토큰·비밀번호는 어떤 경로로도 안
찍힌다. `health` 는 로컬에서 예외 문자열을 `detail` 에 실어 주므로
(`app/apis/v1/health_routers.py:27`), 그대로 옮기면 접속 문자열이 배포 로그에
남는다. `scripts/smoke.py` 의 `Reason` 이 밖으로 나갈 수 있는 말의 전부다.

```text
대상 주소가 http/https URL 이 아니다      대상에 닿지 못했다
제한 시간 안에 답이 없다                   서버가 5xx 로 답했다
health 가 degraded 다 (db·redis)           합성 계정 로그인이 거절됐다
```

`SMOKE_TIMEOUT_SECONDS` 로 제한 시간을 바꾼다(기본 10초). 숫자가 아니면 그
자리에서 이름을 대며 멈춘다.

**닿지 못한 경우에만 다시 건다** (기본 3회, 5초 간격). 배포 직후에는 컨테이너가
아직 뜨는 중일 수 있어서다. `degraded`·`401`·`5xx` 처럼 **판정이 끝난 실패는 다시
묻지 않는다** — 여러 번 묻는 동안 진짜 고장이 「간헐적」으로 보인다.

**실패 게이트로 쓸 때**는 종료 코드만 보면 된다. 배포 스크립트 끝이나 GitHub
Actions 에서 같은 명령을 그대로 쓴다.

```bash
uv run python scripts/smoke.py "$TARGET" || { echo "smoke 실패 — 롤백한다"; exit 1; }
```

### 손으로 볼 때

```bash
curl -fsS https://<도메인>/api/v1/health | jq .
```

로그인까지 손으로 확인할 때는 **비밀번호를 명령줄에 적지 않는다.** 위 실행기를
쓰는 편이 낫다.

### 아직 원격에서 못 도는 것

전 구간 여정은 정리돼 있다 — `docs/qa/KEY-152-e2e-evidence.md` 가 `SYN-EMS-01`
고정 시나리오로 로그인→업로드→판독→승인→환자링크→D+7 을 적었고
`scripts/run_key152_e2e.sh` 가 그것을 돌린다. **그 스크립트는 아직 로컬 전용**
이다. 위 smoke 는 「API 가 최소한 살아 있는가」까지만 본다.

## 6. 🔴 아직 못 하는 것

**프런트가 안 뜨던 것은 해결됐다** — 아래 7절 참고 (KEY-189).

남은 것:

- **원격 대상 전 구간 E2E** — 5절의 smoke 는 「API 가 살아 있는가」까지다(KEY-184).
  `scripts/run_key152_e2e.sh` 가 도는 전 구간 여정은 여전히 로컬 전용이다
- **CI 배포** — 지금은 사람이 로컬에서 스크립트를 돌린다
- **EC2 인스턴스·도메인·Docker Hub 계정** — 실제로 확보돼 있는지 저장소만으로는
  알 수 없다

## 7. 프런트는 이미지에 구워서 나간다

`KEY-174` 때는 운영 nginx 가 `/` 를 404 로 막고 있어 URL 을 공유해도 볼 것이
없었다. 셋 중 **①이미지에 굽기**로 정했다(한금준 님) — **이미지 태그로 어떤
화면이 떴는지 고정**되기 때문이다. QA 가 「그때 그 화면」을 다시 띄울 수 있어야
한다.

```text
infra/nginx/Dockerfile        FROM nginx:latest + COPY frontend/ /vol/web/frontend/
docker-compose.prod.yml       nginx 이미지를 web-${WEB_VERSION} 으로
prod_http · prod_https        location / 이 /vol/web/frontend 를 준다
```

배포 때 메뉴에서 **3) frontend(nginx)** 를 고르면 굽고 올린다. 되돌리는 것도
`APP_VERSION` 과 같다 — `.env` 의 `WEB_VERSION` 을 직전 값으로 내린다.

프런트는 빌드 단계가 없다(npm·번들러 없는 ES5). `frontend/` 를 그대로 굽는다.

**nginx 설정은 안 굽는다.** `deployment.sh` 가 http/https 중 고른 것을 올리고,
certbot 이 갱신하면서 바꾸기도 한다 — 이미지에 넣으면 그때마다 다시 구워야 한다.

**https 판의 80 포트는 아무것도 안 준다.** 전부 https 로 넘긴다 — 거기서
프런트를 주면 환자가 평문으로 안내를 본다.

## 관련

- 부모: [KEY-144](https://leehee.atlassian.net/browse/KEY-144)
- 형제: KEY-175(한금준) · KEY-176(김고은) · KEY-177(유가은) — 이 환경 위에서 검증
- 후속: [KEY-184](https://leehee.atlassian.net/browse/KEY-184) 원격 smoke·실패 게이트(5절) · [KEY-185](https://leehee.atlassian.net/browse/KEY-185) 롤백 리허설
- 로컬 확인: `docs/local-health-check.md`
- 규모 설계 비교: `docs/infra-scale.md`
- E2E 증적: `docs/qa/KEY-152-e2e-evidence.md`
