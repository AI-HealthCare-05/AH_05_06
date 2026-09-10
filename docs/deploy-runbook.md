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

### 🚩 배포 전에 되돌릴 것

만드는 동안 편하려고 풀어 둔 값들이다. **`.prod.env` 에서 반드시 확인한다.**

| 값 | 만드는 중 | 배포 |
| --- | --- | --- |
| `CATALOG_DRAFT_MODE` | `true` — 대표 처방·약 이름을 고치고 지울 수 있다 | **`false`** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` — 하루에 한 번만 로그인 | **`60`** |

`CATALOG_DRAFT_MODE` 를 켠 채로 배포하면 **이름을 바꾸거나 지울 수 있는 상태로
나간다.** 그 이름은 진료기록에 **문자열로** 박혀 나가므로(스냅샷, KEY-137),
바꾸거나 지우면 지난 기록이 가리키던 것이 사라지고 **화면엔 아무 말도 안 뜬다.**
의료 데이터라 삭제도 금지다.

끈 뒤에는 잘못 등록한 것을 **감춘다** — 지우는 대신.

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
5. EC2 에서 `docker compose up -d --pull always --no-deps <고른 서비스>` 후 옛 이미지 정리
   (`scripts/lib.sh:51`. **고른 것만 뜬다** — `--no-deps` 라 mysql·redis 는 딸려 오지 않는다)

## 3-2. 배포가 DB 를 따라오게 한다 (KEY-206)

`scripts/deployment.sh` 를 돌리면 아래 순서가 **원격에서** 돈다. 손으로 할 일은
없고, 여기 적는 것은 **무엇이 언제 도는지**와 **틀어졌을 때 어디를 보는지**다.

```text
docker login
docker compose pull   <고른 서비스>
docker compose run --rm -T --no-deps fastapi uv run --no-sync aerich upgrade   ← 여기
docker compose up -d  --no-deps <고른 서비스>
docker image prune -af
```

### 왜 `up -d` 앞인가

**뒤에 걸면 실패해도 새 코드는 이미 돌고 있다.** 멈출 것이 남아 있지 않다.
그래서 이미지만 받아 두고, 그 이미지로 마이그레이션을 한 번 돌리고, 통과하면
그때 앱을 바꾼다. `set -e` 가 걸려 있으므로 실패하면 **앱은 옛 버전 그대로**
남는다 — 이게 이 순서의 전부다.

`fastapi` 를 고른 배포에서만 돈다. nginx 만 올리는 배포는 DB 를 안 건드린다.

### 여태 이 단계가 없었다

`KEY-197` 을 하다가 Pilot 에서 `guide_section.drug_caution_content_id` 가 통째로
없는 것을 발견했다. **사고가 아니라 이 구조의 당연한 결과였다** — 이미지를 새로
올려도 DB 는 있던 자리에 그대로 있었다.

### 도는 자리에 도구가 있는지 확인했다

시드 스크립트에서 「런북에 적힌 명령이 서버에서는 그런 파일 없음으로 죽는」
자리를 한 번 밟았다. 그래서 이번에는 **이미지를 지어서** 봤다 (2026-08-28).

```text
app/Dockerfile 로 지은 이미지 안 (마운트 없음)

  aerich          0.9.2
  마이그레이션      21 개
  pyproject.toml  [tool.aerich] 있음

  빈 DB 에 걸었을 때   21 개 적용 · 25 표
  한 번 더 걸었을 때   No upgrade items found
```

### 틀어졌을 때

| 화면에 뜨는 것 | 뜻 | 할 일 |
|---|---|---|
| `Old format of migration file detected` | 마이그레이션 파일에 `MODELS_STATE` 가 없다 | `aerich fix-migrations`. 검사가 미리 잡게 돼 있다 (`test_migration_file_format.py`) |
| `No upgrade items found` | **정상이다.** 이미 다 적용돼 있다 | 그대로 진행 |
| 연결 오류 (`Can't connect`) | DB 가 안 떠 있거나 `.env` 의 DB 값이 틀렸다 | `docker compose ps mysql` · `.env` 확인 |
| SQL 오류로 중간에 멈춤 | 마이그레이션이 지금 데이터와 안 맞는다 | **앱은 안 바뀐 상태다.** 아래 「되돌릴 때」 |
| **`✅ Deployment finished` 는 떴는데 컨테이너가 안 바뀜** | **stdin 을 삼켰다** | 아래 「조용히 성공한 것처럼 끝날 때」 |

### 조용히 성공한 것처럼 끝날 때 — stdin (KEY-263)

원격 배포 본문 **전체가 `bash -s` 의 stdin 으로** 흘러 들어간다. 그 안에서
stdin 을 읽는 명령은 **아직 안 읽은 스크립트 나머지를 먹는다.**

```bash
docker compose run --rm -T … aerich upgrade < /dev/null   # ← 이 리다이렉션이 필수다
```

2026-09-03 에 이것을 빼먹어서 이렇게 됐다.

| 돈 것 | 사라진 것 |
|---|---|
| `docker compose pull` | `echo "Deploying services"` |
| `aerich upgrade` (16 개 적용) | **`docker compose up -d`** ← 컨테이너가 안 바뀐 이유 |
| | `docker image prune -af` |

`aerich` 가 0 으로 끝나므로 **`set -e` 에도 안 걸리고 `✅ Deployment finished` 가
찍힌다.** 실패했다는 사실 자체가 안 보인다.

🚩 **원격 스크립트에 stdin 을 쓰는 명령을 더할 때는 반드시 막는다** —
`docker compose run/exec` · `read` · `ssh` 전부 해당한다. `read` 는 예전에
같은 함정에 걸려 heredoc 으로 바꿨다(`#133` 리뷰, `scripts/lib.sh` 주석).

**한 번에 닫는 `exec < /dev/null` 은 못 쓴다.** 구조적으로 안전해 보여
`#202` 리뷰에서 제안을 받아 넣어 봤는데, **스크립트 자신이 stdin 에 실려
있어서**(`bash -s`) 닫는 순간 뒤가 통째로 안 읽힌다.

```bash
printf 'echo A\nexec < /dev/null\necho B\n' | bash -s   # → A 만 나온다
printf 'echo A\ncat  < /dev/null\necho B\n' | bash -s   # → A B 둘 다
```

그래서 **명령마다** 막는다. 빠뜨리기 쉬운 것이 이 방식의 약점이라,
`test_key263_deploy_actually_ships.py` 가 stdin 을 쓰는 명령을 전부 훑어
리다이렉션이 없으면 운다.

**확인은 로그가 아니라 상태로 한다.** 배포 전에 찍어 두고 뒤와 맞댄다.

```bash
ssh -i ~/.ssh/<키>.pem ubuntu@<IP> 'cd ~/project && docker compose ps'
```

`Up 2 hours` 처럼 **오래 떠 있으면 안 바뀐 것**이다.

### 도는 것이 어느 커밋인가 (KEY-315)

`docker compose ps` 는 **태그**를 보여 준다(`app-v1.0.5`). 그 태그는 사람이
손으로 올리는 값이라 **어느 커밋인지 말해 주지 않는다.** 서버에는 저장소가
없어서 되짚을 길도 없었다 — 배포 사고를 의심할 때 출처를 못 밝히면 조사가
시작을 못 한다.

이제 이미지가 스스로 답한다.

```bash
ssh -i ~/.ssh/<키>.pem ubuntu@<IP> "cd ~/project && \
  for s in fastapi ai-worker nginx; do
    printf '%-10s ' \$s
    docker inspect --format '{{index .Config.Labels \"org.opencontainers.image.revision\"}} ({{index .Config.Labels \"org.opencontainers.image.ref.name\"}})' \$s
  done"
```

**`\"` 와 `\$` 를 지운 채로 옮겨 적지 않는다.** 라벨 이름은 Go 템플릿에서
글자열이라 따옴표가 있어야 하고(없으면 `function "org" not defined`), 그 따옴표는
바깥 `"` 안에서 escape 돼야 원격까지 간다. `$s` 도 마찬가지로 **원격에서** 풀려야
할 값이다. 아래 검사가 이 명령을 실제로 돌려 본다.

```text
fastapi    7c7ab7dc5cc27f4ec7185ab2265cc9b070bfcbdd (develop)
ai-worker  7c7ab7dc5cc27f4ec7185ab2265cc9b070bfcbdd (develop)
nginx      7c7ab7dc5cc27f4ec7185ab2265cc9b070bfcbdd (develop)
```

**`-dirty` 가 붙어 있으면 그 SHA 를 믿지 않는다.** 커밋 안 된 변경으로 구운
이미지라 그 커밋을 받아 봐도 같은 판이 안 나온다 — 빌드할 때도 한 번 경고한다.

셋의 커밋이 서로 다르면 **부분 배포**다(프런트만 다시 구운 경우 등). 그 자체는
정상이지만, 무엇이 옛것인지 여기서 드러난다.

라벨은 `scripts/deployment.sh` 의 `build_and_push` 가 붙인다. **9/4 이전에 구운
이미지에는 없다** — 그때 것은 태그로만 되짚는다.

### 되돌릴 때

앱은 `4. 롤백` 을 따른다. **DB 는 별개다.**

```bash
# 어디까지 왔는지 먼저 본다
docker compose run --rm -T --no-deps fastapi uv run --no-sync aerich history
```

되돌리려면 `aerich downgrade` 이고 `docs/migrations/` 를 따른다.
**`--delete` 를 쓰지 않는다** — 마이그레이션 파일 자체가 지워진다.

> 실제로 한 번 지워 봤다. `aerich downgrade -v 1 -d` 로 파일 20 개가 사라졌고
> `git checkout --` 으로 되살렸다. `-d` 는 「delete」다.

### 증적을 남긴다

배포 로그의 이 세 줄이 증적이다. 시연·QA 전에 남겨 둔다.

```text
Pulling images: …
Applying migrations
Success upgrading to 20_20260826000000_key165_drug_caution.py    ← 또는 No upgrade items found
```

아무것도 안 뜨면 **그 배포는 `fastapi` 를 안 고른 것**이다.

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
# ⓪ **저장소가 있는 기계에서.** 서버에는 `scripts/` 도 `docs/` 도 없다 —
#    `deployment.sh` 가 올리는 것은 `.env` · `docker-compose.yml` ·
#    `nginx/default.conf` 셋뿐이다(133-142 줄). 이 줄이 없으면 아래 ① 이
#    「lstat /home/ubuntu/project/scripts: no such file or directory」로 죽는다.
ssh -i ~/.ssh/<키> ubuntu@<IP> 'mkdir -p ~/project/docs'
scp -i ~/.ssh/<키> -r scripts   ubuntu@<IP>:~/project/
scp -i ~/.ssh/<키> -r docs/data ubuntu@<IP>:~/project/docs/

# 아래부터 서버에서. 스키마가 먼저 올라가 있어야 한다 (4. 롤백 아래 「마이그레이션」 참고).

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
    fastapi uv run --no-sync python scripts/seed.py --mode full --allow-prod-seed

# ③ 끝나면 도로 치운다 — **컨테이너 안과 호스트 양쪽.**
#    ⓪ 이 올린 것이 서버에 남으면 시딩 도구를 안 남긴다는 뜻이 반만 지켜진다.
docker compose exec -T fastapi rm -rf /app/scripts /app/docs
rm -rf ~/project/scripts ~/project/docs
```

세 가지가 안 하면 죽는 자리다. 셋 다 그대로 밟아 확인했다 — ⓪ 은 실제 Pilot EC2 에서.

```text
서버에는 저장소 사본이 없다
  ⓪ 없이  →  lstat /home/ubuntu/project/scripts: no such file or directory
  ⓪ 하면  →  docker cp 가 지난다

docker compose exec 는 호스트 환경변수를 자동으로 안 넘긴다
  -e 없이  →  컨테이너가 본 값: 없음   (seed 가 「SEED_STAFF_PASSWORD 환경변수가 없습니다」로 종료)
  -e 주면  →  컨테이너가 본 값: 있음

그냥 `python` 은 시스템 파이썬이라 의존성이 없다
  python scripts/seed.py            →  ModuleNotFoundError: No module named 'tortoise'
  uv run --no-sync python …         →  [seed] 완료
```

`--no-sync` 는 이미지 `CMD` 와 같은 꼴이다 — 컨테이너 안에서 다시 설치하지 않는다.

```text
⚠ ENV=prod 시딩 허용됨 (SEED_ALLOW_PROD + --allow-prod-seed) — Pilot/합성 전용
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

그래서 **환경변수 하나로는 안 열리게 고쳤다** (가드레일 ① 개정, 이희진 님
2026-08-28 결정 · 한금준 님 제안).

```text
SEED_ALLOW_PROD=1        환경변수      「이 서버는 Pilot 이다」
--allow-prod-seed        명령줄 인자   「이번 실행을 사람이 뜻했다」

둘 다 있을 때만 열린다.
```

`env_file` 은 **argv 를 만들 수 없다.** 서버 `.env` 에 값이 남아 있어도, 실행할
때 명령줄에 다시 적지 않으면 문이 안 열린다. 하나만 있을 때 어떻게 막히는지는
계약 검사 다섯이 붙들고 있다 (`test_key200_seed_prod_gate.py`).

그래도 서버 `.env` 에는 안 적는 것이 낫다 — 두 문턱 중 하나를 미리 열어 두는
셈이다.

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
    fastapi uv run --no-sync python scripts/seed.py --mode full --allow-prod-seed
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

`seed.py` 는 같은 명령을 여러 번 돌려도 쌓이지 않는다. 병원·직원·환자·진료·처방은
`get_or_create` 다. 비밀번호를 바꾸고 다시 돌리면 직원 계정의 비밀번호가 갱신된다.

**안내 문구(`drug_caution_content`)만 다르다.** 「쌓지 않는다」가 아니라 **도장을
옮긴다** — `content_version` 이 오르면 옛 승인본을 `DEPRECATED` 로 내리고 새 판을
승인한다(KEY-180 §3). 지우지 않는 것은 이미 나간 안내문이
`GuideSection.drug_caution_content_id` 로 옛 행을 가리키기 때문이다.

그래서 재시드 뒤 그 표에는 **행이 는다.** 「안 쌓인다」만 보고 디버깅하면 헷갈리는
자리라 적어 둔다 (이희진 님 `#214` ⑧). 검증은
`app/tests/catalog/test_seed_is_rerunnable.py` 가 한다.

## 4-3-1. Pilot 고정 OTP 좁은문 (KEY-264)

Pilot은 `ENV=prod`로 뜨기 때문에 KEY-219 가드가 기본적으로 `MOCK_OTP_CODE`를
막는다. 아래 둘 다 있어야 Pilot에서 고정 OTP(`000000`)를 쓸 수 있다.

```text
PILOT_ALLOW_MOCK_OTP=1     환경변수
--pilot-confirm-mock-otp   실행 플래그
```

하나만 있으면 예전과 동일하게 부팅이 막힌다 — `SEED_ALLOW_PROD`(4-3절)와 같은
이유다.

```bash
PILOT_ALLOW_MOCK_OTP=1 docker compose \
  -f infra/docker/docker-compose.prod.yml \
  -f infra/docker/docker-compose.pilot.yml \
  up -d --build fastapi
```

좁은문이 열렸는지는 fastapi 컨테이너 로그에서 확인한다.

```text
MOCK_OTP_CODE 좁은문 열림 (ENV=prod, PILOT_ALLOW_MOCK_OTP + --pilot-confirm-mock-otp) — Pilot 전용 (KEY-264)
```

일반 운영 배포에는 `docker-compose.pilot.yml`을 절대 함께 주지 않는다.

솔라피 어댑터(KEY-248)를 `OtpDelivery`에 실배선하는 작업은 KEY-284가 한다 —
아래 4-3-2절을 본다.

## 4-3-2. Pilot 고정 OTP → 실제 솔라피 OTP 전환 (KEY-284)

**KEY-219의 난수 OTP·검증·잠금 로직은 이미 있다.** 이 절이 하는 일은 그
로직을 실제 발송 경로(솔라피)와 잇고, 검증된 뒤에만 4-3-1절의 고정 OTP
좁은문을 끄는 순서를 정하는 것이다.

### 전환 순서 — 단계마다 앞 단계가 끝나야 다음으로 간다

1. **mock 자동 테스트 통과.** `SMS_PROVIDER=mock`(기본값)로 CI가 그대로
   통과하는지 먼저 확인한다 — 여기까지는 자격증명이 전혀 없어도 된다.
2. **Pilot/staging에서 승인된 테스트 번호로 실제 문자 1건 수신.**
   ```text
   ENV=prod (Pilot)
   SMS_PROVIDER=solapi
   SOLAPI_API_KEY / SOLAPI_API_SECRET / SOLAPI_SENDER_NUMBER  실제 값
   OTP_APPROVED_TEST_PHONES=010XXXXXXXX   (승인된 팀 내 번호만, 쉼표 구분)
   ```
   **이 단계에서는 `MOCK_OTP_CODE`를 빼고 띄운다.** `_otp_service()`는
   `MOCK_OTP_CODE`가 있으면(그리고 4-3-1 좁은문이 열려 있으면) 그걸
   최우선으로 보고 고정 OTP로 응답해 버린다 — 4-3-1 좁은문이 여전히
   켜진 채로 이 단계를 밟으면 솔라피 경로에 도달하지도 않는다
   (iljun-sys 리뷰로 재현됨).

   Pilot(ENV=prod)에서는 `_otp_service()`가 `OTP_SOLAPI_PROD_ENABLED` 환경변수
   **와** `--otp-confirm-solapi-prod` 실행 플래그를 **둘 다** 요구한다(4-3-1의
   `PILOT_ALLOW_MOCK_OTP`와 같은 이중 게이트 원칙). 이 둘이 갖춰지면 실제
   솔라피로 나가되, `OTP_APPROVED_TEST_PHONES`에 없는 번호는 발송 자체가
   막힌다 — 이 단계에서 실수로 임의의 번호에 문자가 나가지 않게 하는
   안전장치다. **이 목록을 비워 두지 않는다** — 비면 승인 여부와 무관하게
   전부 막혀서(deny-all), 공급자 장애와 구분 안 되는 503만 받는다.
3. **수신한 OTP로 검증·환자 세션·보호 API 접근까지 E2E 확인.**
4. **장애·재발송·만료·잠금 회귀를 다시 돌려서 실제 경로에서도 그대로
   지켜지는지 확인.**
5. **위 네 가지가 전부 확인되고 팀 승인을 받은 뒤에만** 4-3-1절의
   `PILOT_ALLOW_MOCK_OTP` 좁은문을 끈다(env·플래그를 배포에서 뺀다).
6. **운영(실제 환자) 발송 활성화는 여기서 하지 않는다** — KEY-6 배포 승인과
   비밀값 설정 절차를 별도로 따른다. Pilot 검증이 끝났다고 운영에 자동으로
   반영되지 않는다.

### Rollback — 실제 경로에서 문제가 생기면

`SMS_PROVIDER=solapi`로 전환한 뒤 실발송에 문제가 생기면, 아래로 즉시
되돌릴 수 있다 — 코드 롤백이 필요 없다.

- **표준 롤백**: `OTP_SOLAPI_PROD_ENABLED`를 지우거나
  `--otp-confirm-solapi-prod` 플래그를 빼고 재기동한다.
  `UnavailableOtpDelivery`로 떨어져 발급 자체가 503으로 안전하게
  막힌다(발송이 성공한 것처럼 보이는 상태로 남지 않는다). `SMS_PROVIDER`는
  건드릴 필요가 없다.
- **`SMS_PROVIDER=mock`으로는 롤백하지 않는다.** KEY-248의 검증기가
  `SMS_PROVIDER=mock`과 `ENV=prod`의 조합 자체를 거부한다 — 그 조합으로
  재기동하면 `Config` 생성 시점에 `ValidationError`가 나서 **앱이 아예
  뜨지 않는다**(iljun-sys 리뷰로 재현됨). 사고 중에 이 줄을 따르면
  롤백이 아니라 서비스 전체가 내려간다.
- 어느 쪽으로 되돌리든 `PatientOtpChallenge`의 기존 계약(3분 만료·5회
  잠금·일회 사용)은 그대로다 — 이 표를 건드리는 롤백이 아니다.

## 4-4. 시연 전 재프로비저닝 — 한 번에 따라가는 순서 (KEY-203)

**시연 당일에 읽는 절이다.** 위의 3·4·4-2·4-3 은 각각 「무엇을 할 수 있는가」를
적은 배경이고, 이 절은 **어느 순서로 누가 무엇을 하는가**만 적는다.

### 누가 무엇을 하나

같은 서버를 두 사람이 동시에 만지면 무엇이 깨졌는지 알 수 없게 된다.

| 단계 | 하는 사람 |
|---|---|
| ①②  EC2 · compose · env (프로비저닝) | 권일준 |
| ②③④ 배포 · 마이그레이션 · seed 실행 | 한금준 |
| ⑥   smoke 검증 | 유가은 |

**시연 창 동안 Pilot 의 DB·컨테이너를 만지는 사람은 권일준·한금준 둘뿐이다**
(유가은은 ⑥ 검증만 하고 쓰지 않는다). SSH 키를 가진
사람이 더 있어도 마찬가지다 — 이 문단이 사실상 유일한 잠금이다.

### 시작 전 — 선행 셋이 `develop` 에 있는가

```text
KEY-196  마이그레이션 형식     없으면 ③ 이 「Old format of migration file」로 멈춘다
KEY-197  업로드 볼륨          없으면 OCR 이 FileNotFoundError 로 전부 실패한다
KEY-200  seed 운영 가드       없으면 ④ 가 「운영 환경(ENV=prod)에서는…」으로 멈춘다
```

셋 중 하나라도 빠져 있으면 **그 단계에서 반드시 멈춘다.** 시작 전에 확인한다.

### 비밀값 — 값은 이 문서에 없다

| 이름 | 누가 정하나 | 어떻게 나누나 |
|---|---|---|
| `SEED_STAFF_PASSWORD` | 시딩 담당자 | 팀 비밀번호 매니저 또는 1:1 DM |
| `SMOKE_PASSWORD` | 위와 **같은 값** | 유가은에게 같은 방법으로 |

커밋·이슈·Jira 본문·로그·`~/project/.env` 어디에도 남기지 않는다. 「채팅에 안 적는다」와
「1:1 DM」이 어긋나 보이지만 뜻은 하나다 — **여러 사람이 보는 자리에 안 적는다.**

시연 계정은 표준 `staff01` · 승인 `doctor01` 이다. H2 · 잠금 · 첫 로그인 계정은
쓰지 않는다 (「고르면 안 되는 계정」 참고).

### ① 이미지를 굽고 민다

```bash
# 이 스크립트가 `scripts/lib.sh` 를 source 한다 — 아래 ② 가 가리키는 `lib.sh:51`
# 이 실제로 `docker compose up` 을 부르는 자리다.
./scripts/deployment.sh    # 대화형 — 무엇을 구울지 고른다
```

**버전 세 개를 다 챙긴다.** 롤백은 태그를 되돌리는 것이라(4절) 지금 무엇을
올렸는지가 곧 되돌릴 지점이다.

```text
APP_VERSION         fastapi
AI_WORKER_VERSION   ai-worker      ← 예전 런북이 이것을 안 적었다
WEB_VERSION         nginx (프런트를 구워서 담는다 — 7절)
```

**재프로비저닝 때는 태그를 올린다.** 같은 태그로 다시 밀면 `--pull always` 가
새것을 받기는 하지만 `docker ps` 로는 어제 것과 오늘 것이 같아 보인다. 8/28 에
「이미지가 낡았나」를 이미지 안 마이그레이션 파일을 뒤져서야 알았다.

```bash
docker image inspect <user>/<repo>:app-<태그> --format '{{.Created}}'
```

태그를 올려 두면 이 명령을 찾을 일이 없다.

### ② 전체를 띄운다

**배포 스크립트만으로는 전체가 안 뜬다.** `scripts/lib.sh:51` 이
`--no-deps` 로 **고른 서비스만** 올린다 — mysql·redis 는 딸려 오지 않는다.

```bash
# EC2 에서. 서비스 이름을 주지 않으면 compose 가 전부 띄운다.
cd ~/project && docker compose up -d
docker compose ps      # 일곱이 다 떴는가
```

이 저장소의 운영 compose 에는 `profiles:` 가 없다 — 줄 옵션을 찾지 않아도 된다.

> **RDS 로 옮긴 서버는 다르다.** 그 서버에는 `~/project/docker-compose.override.yml` 이
> 얹혀 있고, 거기서 `mysql` 이 프로필 뒤로 간다 — 맨 `up -d` 로는 안 뜬다(의도된 것이다).
> 옮긴 뒤에 이 절을 읽는다면 4-5 절을 함께 본다.

### ③ 스키마를 올린다

```bash
docker compose exec -T fastapi uv run --no-sync aerich upgrade
```

올린 뒤 **표가 실제로 생겼는지 본다.** `/api/v1/health` 로는 알 수 없다 —
`SELECT 1` 만 보기 때문에 **DB 가 비어 있어도 `ok`** 를 준다.

```bash
# 변수는 **컨테이너 안에서** 풀게 한다. 밖에서 풀면 호스트 셸에 그 이름이
# 없을 때 조용히 빈 값이 들어가 `Access denied for user '-p'` 로 죽는다.
docker compose exec -T mysql sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e \
   "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"$MYSQL_DATABASE\";"'
```

**25 가 나와야 한다.** <!-- 마이그레이션이 표를 더하면 이 숫자를 갱신한다 -->
0 이면 마이그레이션이 안 돈 것이고, 그 상태로 ④ 를 하면
「Unknown column …」 같은 엉뚱한 자리에서 죽는다.

표 개수만으로는 부족한 경우가 있다 — **표는 다 있는데 칸이 빠진** 상태가 실제로
있었다(`guide_section.drug_caution_content_id` 하나가 빠진 채 표는 25 개였다).
칸 단위로 대조하는 스크립트는 KEY-198 이 붙인다. 그것이 들어오기 전에는, 위 개수
확인이 통과해도 **④ 에서 「Unknown column …」이 나면 이 자리를 의심한다.**

### ④ 합성 데이터를 붓는다

**4-3 절을 그대로 따른다.** 명령이 네 군데 함정을 지나므로 요약하지 말고
그 절을 편다 — `scp` → `mkdir` → `docker cp` → `-e` 로 값 전달 → `uv run --no-sync`.

**⓪ 만 다른 기계에서 돈다.** 서버에는 `scripts/` 도 `docs/` 도 없어서(①②는
`.env`·compose·nginx 만 올린다) 저장소가 있는 기계에서 먼저 올려야 한다. 그
줄을 건너뛰면 `docker cp` 가 「no such file or directory」로 멈춘다.

### ⑤ 로그인이 되는가

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://<IP>/login.html      # 화면 200
curl -sS -X POST http://<IP>/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"login_id":"staff01","password":"<합성 비밀번호>"}' | head -c 80
```

`access_token` 이 나오면 통과다. **화면 `/login` 은 404 다** — nginx 가
`try_files $uri $uri/ =404` 라 확장자 없는 경로를 못 찾는다. `/login.html` 로 본다.

### ⑥ 한 바퀴 돌려 보고 넘긴다

`docs/qa/KEY-148-walking-skeleton.md` 의 시나리오(`SYN-EMS-01` · 차트 12401 ·
`staff01` · `doctor01`)를 **손으로 한 번** 밟는다. 그 뒤 5절 smoke 를 유가은에게
넘긴다 — `SMOKE_LOGIN_ID=staff01` 과 `SMOKE_PASSWORD`(④ 에서 쓴 값과 같다).

### 볼륨을 비우는 경우

재프로비저닝은 **상태를 예측 가능하게** 두려고 볼륨을 비우고 다시 심는다.

```bash
cd ~/project && docker compose down -v     # 🔴 mysql_data 가 사라진다
```

`mysql_data` · `media_volume` · `minio_data` 가 함께 지워진다. **보존이 필요하면
실행 전에 KEY-203 코멘트에 사유를 남기고 결정한다.** 지운 뒤에는 ②③④ 를 다시 밟는다.

### 중간에 깨지면

| 어디서 | 어떻게 되돌리나 |
|---|---|
| ① 이미지 | 4절 — Hub 태그를 되돌린다 |
| ② 기동 | `docker compose ps` 로 무엇이 안 떴는지 보고 그것만 다시 |
| ③ 마이그레이션 | `aerich downgrade` (`docs/migrations/`). **먼저 어디까지 올랐는지 확인한다** |
| ④ 시딩 | `down -v` 로 비우고 ②부터 다시 — seed 는 `get_or_create` 라 다시 돌려도 안 쌓인다 |

## 4-5. 컨테이너 MySQL → RDS MySQL (KEY-201)

`mysql_data` 볼륨은 컨테이너 재시작은 견디지만 **EC2 인스턴스가 사라지면 함께
사라진다.** 담긴 것이 진료 기록·안내문이고 명세가 「삭제하지 않는다」이므로,
지금 구조에는 되살릴 수단이 하나도 없다. `docs/infra-scale.md` 가 목표를 RDS
MySQL 로 적어 두었다.

> **아직 안 옮겼다.** 이 절은 옮길 때 따라갈 절차이고, AWS 자원을 실제로 만든
> 기록이 아니다. 만든 뒤에는 엔드포인트·검증 결과를 여기 이어 적는다.

### ① 무엇을 만드나

| | 값 | 왜 |
|---|---|---|
| 엔진 | MySQL 8.0 | 컨테이너와 같은 판이라 스키마를 그대로 옮긴다 |
| 퍼블릭 액세스 | **끈다** | 켜면 환자 표가 인터넷에 붙는다 — 보안그룹 하나에 기대지 않는다 |
| 보안그룹 | EC2 의 그룹에서 3306 만 | 4-2 절이 웹 둘만 여는 것과 같은 태도다 |
| 문자셋 | `utf8mb4` · `utf8mb4_unicode_ci` | 컨테이너 `command` 가 주던 값이다 — RDS 는 **파라미터 그룹**으로 준다 |
| 시간대 | `Asia/Seoul` | 컨테이너는 `TZ` 로 줬다. RDS 는 파라미터 그룹의 `time_zone` 이다 |

**문자셋·시간대를 기본값으로 두면 안 된다.** 컨테이너 쪽은 `command` 와 `TZ`
로 주고 있어서, 그 두 줄을 안 옮기면 RDS 에서 한글이 `????` 로 들어가거나
날짜 경계가 UTC 로 밀린다. 같은 스키마인데 값이 달라지는 자리다.

**지금 서버에서 잰 값이다** (2026-09-09, `ai-health-05-06`). 새로 만든 RDS 를
이것과 대 본다.

```text
판          8.0.46
문자셋       utf8mb4          정렬  utf8mb4_unicode_ci
time_zone   SYSTEM           ← 컨테이너의 TZ=Asia/Seoul 을 따라간 값이다
크기         6.1 MB           환자 103 · 진료 107 · 안내문 6
```

🚩 **`time_zone` 이 `SYSTEM` 인 것이 함정이다.** RDS 에는 그 컨테이너가 없어
`SYSTEM` 이 **UTC** 를 가리킨다. 파라미터 그룹에 `Asia/Seoul` 을 **명시**하지
않으면 옮긴 뒤 날짜 경계가 아홉 시간 밀린다 — 접수대 목록과 D+7 이 하루씩
어긋나는 모양으로 드러난다(같은 축의 전례 KEY-181).

### ② 옮긴다

앱을 세우고 옮긴다 — 도는 중에 뜨면 그 사이 쓰인 것이 사라진다.

**먼저 compose 판을 본다.** 오버레이가 쓰는 `!override` 는 **v2.24.4 이상**의
문법이다. 낮으면 그 줄을 모르는 값으로 읽어 `mysql` 이 그대로 뜬다 — 옮기고도
컨테이너 DB 가 도는, 이 절이 막으려던 그 자리다.

```bash
docker compose version    # Docker Compose version v2.24.4 이상
```

**서버에는 저장소가 없다.** 배포가 올리는 것은 `.env` · `docker-compose.yml` ·
nginx 설정 셋뿐이다(3절 3번). `-f infra/docker/...` 로 부르면 그런 파일이 없다 —
`~/project` 로 가서 이름 없이 부른다.

```bash
# EC2 에서. 비밀번호는 이 줄에만 적고 셸 기록에 안 남긴다 (2절).
cd ~/project

docker compose stop fastapi ai-worker

# **root 로 뜬다.** 앱 계정은 제 스키마에만 권한이 있어 `--routines`
# `--triggers` 가 환경에 따라 막힌다. 옮기는 일은 한 번뿐이라 여기서만 쓴다.
#
# **자격을 명령줄에 안 싣는다.** `-p` 로 주면 컨테이너 안 `ps` 에 그대로
# 뜬다 — 2절이 셸 기록을 두고 정한 것과 같은 까닭이다. 아래 형태는 그 자리에
# 안 남는다.
docker compose exec -T mysql \
  sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --single-transaction \
    --routines --triggers -uroot "$MYSQL_DATABASE"' > /tmp/care-on.sql

# 받는 쪽. 호스트에 mysql 클라이언트가 없으면 컨테이너를 빌린다.
docker run --rm -i -e MYSQL_PWD="<채워 넣는다>" mysql:8.0 \
  mysql -h <RDS 엔드포인트> -u <사용자> <DB 이름> < /tmp/care-on.sql

shred -u /tmp/care-on.sql   # 덤프에는 환자 표가 통째로 들어 있다
```

`--single-transaction` 이 있어야 InnoDB 를 잠그지 않고 한 시점으로 뜬다.

### ③ 바꿔 붙인다 — **두 곳이다**

```bash
# ⓐ DB_HOST 를 RDS 엔드포인트로 — **두 곳이다**
#    1) 서버의 ~/project/.env
#    2) 배포 원본 envs/.prod.env      ← 이것을 빠뜨리면 다음 배포에서 되돌아간다

# ⓑ 컨테이너 MySQL 을 끈다 — 오버레이를 **이 이름으로** 서버에 둔다
scp -i ~/.ssh/<키> infra/docker/docker-compose.rds.yml \
    ubuntu@<ip>:~/project/docker-compose.override.yml
```

**ⓐ 가 두 곳인 까닭.** 배포 스크립트는 `envs/.prod.env` 를 서버의 `~/project/.env`
로 **매번 덮어쓴다**(`scripts/deployment.sh:210`). 서버 쪽만 고치면 다음 배포에서
`DB_HOST` 가 `mysql` 로 돌아가는데, 오버레이는 파일 이름이 달라 그대로 남는다 —
**앱이 프로필 뒤로 숨은 컨테이너를 찾다가 못 붙는다.** 한쪽만 되돌아가는 이
어긋남이 가장 나쁘다: 배포는 성공하고 앱만 죽는다 (한금준 님 리뷰).

`envs/.prod.env` 는 저장소에 없는 파일이라(`.gitignore`) 배포하는 사람의 손에만
있다. 옮길 때 그 손이 두 곳을 함께 고쳐야 한다.

**`-f` 로 주는 것이 아니다.** 배포 스크립트가 `docker compose` 를 `-f` 없이
부르고(`scripts/lib.sh:65·110`), `~/project/docker-compose.yml` 을 매번
덮어쓴다(`scripts/deployment.sh:215`). 넘길 자리가 없으므로 **이름으로** 얹는다
— compose 는 `docker-compose.override.yml` 을 자동으로 합친다. 배포는 그 이름을
안 건드리므로 **다음 배포에도 그대로 이어진다.**

**ⓒ 앱을 다시 세운다.** `.env` 를 고친 것만으로는 도는 컨테이너가 안 바뀐다 —
환경변수는 컨테이너를 만들 때 박힌다.

```bash
cd ~/project
docker compose up -d --force-recreate --no-deps fastapi ai-worker
```

얹혔는지·붙었는지는 서버에서 이렇게 본다. **앞의 둘은 설정을 볼 뿐이고, 실제로
붙었는지는 셋째가 답한다.**

```bash
cd ~/project
docker compose config --services                  # mysql 이 없어야 한다
docker compose exec fastapi env | grep DB_HOST    # RDS 엔드포인트여야 한다

# 진짜 붙었는가 — 앱이 쓰는 그 자격으로 RDS 에 묻는다
docker compose exec fastapi python -c "
import asyncio, os
from tortoise import Tortoise
from app.core.db.databases import TORTOISE_ORM
async def main():
    await Tortoise.init(config=TORTOISE_ORM)
    rows = await Tortoise.get_connection('default').execute_query_dict(
        'SELECT DATABASE() AS db, @@hostname AS host, @@time_zone AS tz')
    print(rows, os.environ['DB_HOST'])
    print(await Tortoise.get_connection('default').execute_query_dict(
        'SELECT COUNT(*) AS visits FROM visit'))
    await Tortoise.close_connections()
asyncio.run(main())
"
```

`@@hostname` 이 컨테이너 이름이 아니라 RDS 것으로 나오고 진료 건수가 옮기기 전과
같으면 붙은 것이다. 5 절 smoke test 도 한 번 돌린다.

**ⓑ 를 빼먹으면 아무도 안 쓰는 MySQL 이 계속 돌면서 옮기기 전의 진료 기록을
들고 있다.** 백업 대상도 아니고 지우는 절차도 없는 자리라, 환자 데이터 사본이
소리 없이 남는다. 오버레이가 그 서비스를 `profiles` 뒤로 감추고 앱의 기다림도
`redis` 만 남긴다.

**ⓓ 컨테이너만 치운다 — 볼륨은 남긴다.**

```bash
cd ~/project

# 오버레이가 얹힌 뒤라 `mysql` 은 프로필 뒤에 있다 — 프로필을 켜야 이름이 잡힌다.
docker compose --profile container-db rm -sf mysql
```

**여기서 볼륨을 지우지 않는다.** 그 볼륨이 되돌아갈 자리다 — 치우는 것은 ⑦ 이고,
백업·복원을 실제로 검증하고 롤백 기간이 끝난 뒤다 (한금준 님 리뷰). 아래
`--profile` 주의는 그때도 그대로 쓴다.

`--profile container-db` 없이 `docker compose down mysql` 을 부르면 compose 가
그 이름을 못 찾고 **판을 통째로 내린다** — `fastapi` · `nginx` 까지 멈춘다.
옮기는 중에 서비스가 끊기는 것이고, 「mysql 만 지웠다」고 읽은 사람은 그것을
모른다. 같은 모양을 만들어 확인했다(2026-09-09).

```text
--profile container-db rm -sf db   db 만 사라지고 app 은 산다
down db (프로필 없이)               app 까지 사라진다
```

볼륨 이름에 접두어가 없는 것은 compose 파일이 **이름을 못 박아** 두어서다
(`docker-compose.prod.yml` 의 `volumes.mysql_data.name: mysql_data`). 프로젝트
이름이 앞에 안 붙으므로 `docker_mysql_data` 같은 이름은 없다 — 그렇게 부르면
`no such volume` 으로 실패하고, 절차를 따라간 사람은 **옮기기 전 진료 기록을
지웠다고 믿고 넘어간다.**

### ④ 마이그레이션은 그대로 돈다

3-2 절의 `aerich upgrade` 는 `DB_HOST` 를 볼 뿐이라 대상만 바뀐다. 배포
스크립트를 고칠 것이 없다. 다만 `--no-deps` 가 붙어 있어 mysql 컨테이너를
안 띄운다는 점이 오히려 여기서 맞는다.

### ⑤ 되돌리기 — **RDS 에 쓴 것이 있느냐로 갈린다**

되돌릴 것은 늘 셋이다: 서버 `.env` 의 `DB_HOST`, **배포 원본 `envs/.prod.env`**,
그리고 `~/project/docker-compose.override.yml`. **셋을 함께** 되돌리고 ③ⓒ 처럼
`--force-recreate` 로 다시 세운다. 하나만 되돌리면 앱이 없는 곳을 찾는다.

문제는 그 다음이다.

#### ⓐ 아직 아무것도 안 썼다면 — 주소를 되돌리고 **MySQL 을 다시 띄운다**

전환 직후 붙는 것만 확인하고 되돌리는 경우다. 컨테이너 볼륨이 그대로라 그
시점 데이터가 그대로 산다.

**그런데 주소만 되돌리면 안 붙는다.** ③ⓓ 에서 컨테이너를 지웠기 때문이다 —
볼륨은 남아 있어도 컨테이너는 없다. 그리고 ③ⓒ 의 명령은 `--no-deps` 라
`fastapi` · `ai-worker` 만 다시 만든다. **MySQL 은 저절로 안 돌아온다**
(한금준 님 리뷰).

순서가 있다. **앱보다 DB 가 먼저다.**

```bash
cd ~/project

# 1) 주소를 두 곳 다 되돌린다 — 서버 `.env` 와 배포 원본 `envs/.prod.env`.
#    ③ⓐ 와 같은 두 곳이다. 한쪽만 되돌리면 다음 배포가 다시 RDS 로 간다.

# 2) 오버레이를 걷는다. 남아 있으면 mysql 이 프로필 뒤에 계속 숨는다
rm ~/project/docker-compose.override.yml

# 3) 컨테이너 MySQL 을 **먼저** 띄운다 — 남겨 둔 볼륨을 그대로 문다.
#    `--wait` 가 healthy 까지 기다린다. 앱을 먼저 세우면 없는 곳을 찾는다.
docker compose up -d --wait mysql

# 4) 그 다음에 앱을 다시 세운다
docker compose up -d --force-recreate --no-deps fastapi ai-worker

# 5) 붙었는지 · 옛 기록이 보이는지 본다 — ③ⓒ 의 연결 확인을 그대로 쓴다.
#    `@@hostname` 이 컨테이너 것이고 진료 건수가 옮기기 전과 같아야 한다.
```

**3) 을 빼면 배포는 성공하고 앱만 죽는다.** 같은 판을 세워 밟아 봤다.

```text
주소만 되돌리고 ③ⓒ 명령         fastapi 는 running · docker compose ps 도 정상
앱이 DB 에 물으면                ERROR 2005 (HY000): Unknown MySQL server host 'mysql' (-2)
3) 을 넣고 다시                  mysql healthy → 앱 재생성 → 옮기기 전 두 건 그대로 읽힘
```

`docker compose ps` 가 `running` 이라 **되돌리기가 성공한 것처럼 보인다.** ③ⓐ
가 두 곳인 까닭과 같은 종류의 함정이다.

#### ⓑ RDS 에 새 기록이 생겼다면 — **역이전 없이 되돌리면 그것이 사라진다**

전환 뒤 만들어지거나 고쳐진 진료·안내문은 컨테이너 MySQL 에 없다. 주소만
되돌리면 **앱은 옮기기 전 상태를 최신으로 보여 준다.** 지운 것이 아니라 안
보이는 것이라 더 나쁘다 — 사람이 다시 입력하면 그때부터 두 판이 갈린다.

```bash
# 1) 쓰기를 멈춘다 — 뜨는 동안 들어온 것이 사라진다
cd ~/project && docker compose stop fastapi ai-worker

# 2) RDS 에서 뜬다
docker run --rm mysql:8.0 mysqldump -h <RDS 엔드포인트> -u <사용자> -p<비밀번호> \
  --single-transaction --routines --triggers <DB 이름> > /tmp/rollback.sql

# 3) 컨테이너 MySQL 로 되돌린다 — 오버레이를 걷어 다시 띄운 뒤
rm ~/project/docker-compose.override.yml
docker compose up -d mysql
docker compose exec -T mysql sh -c 'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < /tmp/rollback.sql

# 4) 정합성 — 양쪽 건수가 같아야 한다
#    visit · guide_document · patient 셋은 반드시 센다

# 5) 주소 셋을 되돌리고 앱을 다시 세운다 (③ⓒ 와 같다)

shred -u /tmp/rollback.sql   # 덤프에는 환자 표가 통째로 들어 있다
```

**되돌린 뒤에도 시간대는 안 고쳐진다.** RDS 에서 `time_zone` 을 안 주고 쓴
기간의 기록은 UTC 로 박혀 있고, 컨테이너로 되돌아와도 그 값 그대로다 —
아래 리허설이 그것을 보인다.

### ⑥ 아직 팀이 안 정한 것 — 백업 방식

`docs/infra-scale.md` §7 의 미결 4번이다. 정하는 자리는 팀이고, 여기서는
고르는 데 필요한 것만 적는다.

| | RDS 자동 백업 | EBS 스냅샷 |
|---|---|---|
| 되살리는 단위 | **특정 시점**(초 단위) | 스냅샷 찍은 시점 |
| 되살리는 대상 | 새 DB 인스턴스 | 볼륨 → 인스턴스 |
| 앱이 할 일 | `DB_HOST` 교체 | 인스턴스 교체 |
| 켜는 법 | 인스턴스 설정 하나 | 별도 일정 |
| 컨테이너 MySQL 에도 되나 | 아니오 | 예 |

**RDS 로 옮기는 것 자체가 이 선택을 좁힌다** — 옮기고 나면 EBS 스냅샷은
DB 를 안 담는다. 그래서 「RDS 로 간다」와 「EBS 스냅샷으로 백업한다」는 같이
설 수 없다. 옮기기로 정한 이상 자동 백업이 딸려 오는 쪽이 자연스럽다.

인수조건이 **복원 1회 실검증**을 요구한다 — 실제로 되살려 보고 그 결과를
이 절에 이어 적는다. 「켜 두었다」는 검증이 아니다.

### ⑦ 옛 볼륨 치우기 — **맨 마지막이다**

`mysql_data` 는 되돌아갈 자리다. 지우는 순간 ⑤ⓑ 가 불가능해진다. 그래서 아래
셋이 **모두** 끝난 뒤에만 지운다.

1. ⑥ 이 요구하는 **백업·복원 1회 실검증**을 마쳤다 — RDS 자동 백업으로 실제로
   되살려 보고 그 결과를 ⑥ 에 적었다
2. 정한 **롤백 기간**이 지났다 (기간은 팀이 정한다 — 적어도 한 번의 정상 진료일)
3. 그 기간 동안 RDS 로 도는 앱에서 5 절 smoke test 가 통과했다

**순서가 중요하다 — 뜨고, 뜬 것을 확인하고, 그 다음에 지운다.**

```bash
cd ~/project

# ⓐ 한 벌 뜬다
docker run --rm -v mysql_data:/from -v "$PWD":/to alpine \
  tar czf /to/mysql_data-$(date +%Y%m%d).tar.gz -C /from .

# ⓑ 뜬 것을 **확인한다** — 크기와 안에 든 것을 본다
ls -lh mysql_data-$(date +%Y%m%d).tar.gz
tar tzf mysql_data-$(date +%Y%m%d).tar.gz | head        # 데이터 파일이 보여야 한다
tar tzf mysql_data-$(date +%Y%m%d).tar.gz | grep -c ibdata1   # 1 이어야 한다

# ⓒ 확인이 끝난 **뒤에만** 지운다
docker volume rm mysql_data
```

**ⓑ 가 실패하면 ⓒ 를 하지 않는다.** `tar` 가 조용히 빈 묶음을 만들 수 있다
(볼륨 이름을 틀리면 빈 디렉터리를 묶는다). 그 상태로 지우면 백업이 있다고
믿으면서 실제로는 아무것도 없다 — 이 절이 막으려는 바로 그 자리다.

볼륨 이름에 접두어가 없는 것은 compose 파일이 **이름을 못 박아** 두어서다
(`docker-compose.prod.yml` 의 `volumes.mysql_data.name: mysql_data`). 프로젝트
이름이 앞에 안 붙으므로 `docker_mysql_data` 같은 이름은 없다 — 그렇게 부르면
`no such volume` 으로 실패하고, 절차를 따라간 사람은 **옮기기 전 진료 기록을
지웠다고 믿고 넘어간다.**

### ⑧ 전환·롤백을 실제로 밟아 본 결과 (2026-09-09)

한금준 님이 요청한 「전환 → 데이터 생성·수정 → 롤백 → 보존 확인」을 같은 판을
세워 밟았다. **운영 서버가 아니라 리허설이다** — MySQL 8.0 컨테이너 둘을
컨테이너 MySQL(`TZ=Asia/Seoul`, `utf8mb4_unicode_ci`)과 RDS 대역(기본값)으로 세웠다.

**옮기기 전부터 두 판이 다르다.**

```text
컨테이너   utf8mb4 / utf8mb4_unicode_ci / tz=SYSTEM → NOW() 17:05:13
RDS 대역   utf8mb4 / utf8mb4_0900_ai_ci / tz=SYSTEM → NOW() 08:05:13   ← 9시간 뒤
```

`tz=SYSTEM` 이 같은 값인데 결과가 다르다 — 컨테이너는 `TZ=Asia/Seoul` 을 받아
그 시스템 시계를 따르고, RDS 에는 그 컨테이너가 없어 UTC 다. **파라미터 그룹에
`time_zone` 을 명시하지 않으면 여기서 갈린다.**

| 단계 | 결과 |
|---|---|
| 한글·덤프 | `--single-transaction` 덤프로 옮긴 뒤 한글 그대로. collation 은 덤프의 `CREATE TABLE` 이 들고 가 표별로는 지켜진다 |
| 전환 뒤 새 기록 | `visited_at` 이 **08:05 (UTC)** 로 박힌다 — 옮겨 온 행은 17:05 (KST) |
| 주소만 되돌림 | 컨테이너 판은 2행, RDS 는 3행 + 수정 1건 → **전환 뒤 기록이 통째로 안 보인다** |
| 역이전 뒤 되돌림 | 양쪽 3행 일치, 새 진료와 수정 **보존됨** |
| `time_zone` 을 준 뒤 | 그 뒤 쓴 행만 KST. **이미 UTC 로 박힌 행은 안 고쳐진다** |

두 가지가 이 절차의 근거다 — **역이전 없는 롤백은 데이터를 잃고**, **시간대는
옮기기 전에 정해야 한다.**

**「아직 아무것도 안 썼다면」 갈래도 밟았다 (2026-09-10).** 한금준 님이
「③ⓓ 로 컨테이너를 지운 뒤 볼륨만 남은 상태에서 되돌리면 정말 붙느냐」를
물어 같은 판을 다시 세웠다 — 컨테이너 MySQL · RDS 대역 · 앱 셋과 오버레이까지
서버와 같은 모양으로.

| 단계 | 결과 |
|---|---|
| 전환 뒤 | `docker compose config --services` 가 `redis fastapi` — mysql 이 사라진다. 앱은 RDS 대역에서 2행을 읽는다 |
| ③ⓓ 뒤 | mysql **컨테이너 0 개** · 볼륨 `mysql_data` 그대로 |
| 주소만 되돌림 (옛 ⓐ) | `fastapi` 는 `running` 인데 **`ERROR 2005 (HY000): Unknown MySQL server host 'mysql' (-2)`** |
| `up -d --wait mysql` 넣고 다시 | `healthy` → 앱 재생성 → **옮기기 전 두 건 그대로 읽힘** (`visited_at` 도 KST 그대로) |
| 볼륨 확인 | 되살아난 컨테이너가 `mysql_data` 를 그대로 문다 |

**셋째 줄이 이 갈래의 전부다** — 되돌리기가 성공한 것처럼 보이는데 앱만 죽어
있다. `docker compose ps` 로는 안 보이므로 ⓐ 5) 의 연결 확인을 꼭 한다.

운영 RDS 에서 다시 밟을 때는 이 표에 실제 값을 이어 적는다. 리허설은 절차가
성립한다는 것까지만 말한다.

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

반대로 `staff01` · `doctor01` · `doctor02` · `admindoc01` 은 조건을 다 갖췄다. 그중 **`staff01`** 을 쓴다 — CSV 가 스스로
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
- **RDS 로의 이전** — 절차와 오버레이는 4-5 절에 있고 compose 가 그대로 도는
  것까지 확인했지만, **인스턴스를 만들고 옮기고 복원해 본 것은 아직 없다**
  (KEY-201). 그 셋은 AWS 계정을 쥔 사람이 한다

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

🚩 **`.dockerignore` 에 `frontend/` 를 넣으면 이 이미지가 안 구워진다** (KEY-263).
`fastapi`·`ai_worker` 는 정말로 `frontend/` 를 안 쓰기 때문에 「이미지가 안 쓰는
것」으로 보이지만, **이 이미지는 그게 전부다.** 2026-08-31 `fba3c95` 가 넣었고,
그 뒤로 web 이미지가 한 번도 안 구워져 **서버 화면이 8/28 에 멈춰 있었다.**
드러나는 데 사흘 걸린 까닭은 그 사이 web 을 구운 사람이 없어서다.

무게로도 뺄 이유가 없다 — `frontend/` 는 2.9MB 인데 그 커밋이 실제로 막으려던
`.venv`·`.mypy_cache` 는 249MB 다.

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
