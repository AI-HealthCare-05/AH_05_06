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

배포가 살아 있는지 보는 최소 확인이다.

```bash
# ① 서버가 떴는가
curl -fsS https://<도메인>/api/v1/health | jq .

# ② 로그인이 되는가 (합성 계정)
curl -fsS -X POST https://<도메인>/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"login_id":"staff01","password":"<합성 비밀번호>"}' | jq .must_change_password
```

전 구간 여정은 이미 정리돼 있다 — `docs/qa/KEY-152-e2e-evidence.md` 가
`SYN-EMS-01` 고정 시나리오로 로그인→업로드→판독→승인→환자링크→D+7 을 적었고
`scripts/run_key152_e2e.sh` 가 로컬에서 그것을 돌린다. **원격 대상으로 돌리는
판은 아직 없다** — 아래 참조.

## 6. 🔴 아직 못 하는 것

`KEY-174` 인수조건 중 **「공유 가능한 Pilot URL 또는 동등한 실행 환경 제공」**
은 지금 구성으로 만들면 **빈 화면이 나온다.**

```text
infra/nginx/prod_http.conf:25-27    location / { return 404; }
infra/nginx/prod_https.conf:46-48   location / { return 404; }
infra/docker/docker-compose.prod.yml   nginx 에 frontend 볼륨이 없다
app/main.py                         StaticFiles 마운트가 없다
```

로컬은 `infra/nginx/default.conf:25-29` 가 `/vol/web/frontend` 를 서빙하고
`docker-compose.yml:102` 가 `./frontend` 를 거기 마운트한다. **운영에는 그 둘이
다 없다.** 게다가 운영에서는 `/api/docs`·`/redoc`·`/openapi.json` 도 꺼져 있어
API 문서로 대신 보여 줄 수도 없다.

즉 **URL 을 공유해도 볼 것이 없다.** 고치려면 결정이 하나 필요하다.

| 길 | 무엇을 해야 하나 |
|---|---|
| ① 이미지에 프런트를 굽는다 | `Dockerfile` 에 `frontend/` 를 COPY, nginx 가 그 볼륨을 본다 |
| ② 볼륨으로 마운트한다 | 배포 때 `frontend/` 를 EC2 로 `scp`, compose 에 마운트 추가 |
| ③ 프런트를 따로 띄운다 | 정적 호스팅(S3·Netlify 등)에 올리고 API 만 EC2 |

**어느 쪽인지는 배포·비용 결정이라 이 문서가 정하지 않는다.** 셋 다 nginx
설정과 compose 를 함께 고쳐야 하고, ③은 CORS·쿠키 도메인까지 걸린다.

그 밖에 남은 것:

- **원격 대상 smoke 자동화** — `scripts/run_key152_e2e.sh` 는 로컬 전용이다
- **CI 배포** — 지금은 사람이 로컬에서 스크립트를 돌린다
- **EC2 인스턴스·도메인·Docker Hub 계정** — 실제로 확보돼 있는지 저장소만으로는
  알 수 없다

## 관련

- 부모: [KEY-144](https://leehee.atlassian.net/browse/KEY-144)
- 형제: KEY-175(한금준) · KEY-176(김고은) · KEY-177(유가은) — 이 환경 위에서 검증
- 로컬 확인: `docs/local-health-check.md`
- 규모 설계 비교: `docs/infra-scale.md`
- E2E 증적: `docs/qa/KEY-152-e2e-evidence.md`
