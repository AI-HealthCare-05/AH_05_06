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

## 5. Smoke test

배포한 뒤 **기계가 세 자리를 찔러 본다** (KEY-184).

**계정은 `staff01` 을 쓴다** (KEY-192). 합성 직원 17 명 중 자격을 갖춘 것은
열이지만 아무거나 고르면 안 된다 — 아래 「고르면 안 되는 것」 참고.

```bash
export SMOKE_LOGIN_ID=staff01
export SMOKE_PASSWORD=<합성 비밀번호>      # 인자로 주지 않는다 — ps · CI 로그에 남는다
                                          # 값은 시딩할 때 넣은 것이다 (`SEED_PASSWORD`).
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
