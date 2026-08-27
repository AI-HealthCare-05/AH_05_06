"""`docker-compose` 가 요구하는 것과 예시 파일이 어긋나지 않는가 — KEY-191.

compose 는 `${VAR}` 를 **조용히 빈 문자열로 바꾼다.** 그래서 예시에 이름조차
없는 변수가 생기면, 그 파일을 베껴 쓴 사람은 컨테이너가 뜨지 않는 것을 보고
나서야 안다 — 그때는 이미 서버 앞이다.

`Config.model_fields` 를 훑는 검사(`test_pilot_deploy_contract.py`)가 이미
있지만 **여기까지는 못 온다.** MinIO 는 앱이 안 쓰는 인프라라 `Config` 에
없다. 앱 설정과 compose 설정은 서로 다른 목록이고, 지금까지 뒤엣것은
아무도 안 봤다.

**YAML 로 읽는다.** 첫 판은 문자열을 잘라 봤는데, 그러면 주석 한 줄이나 키
순서 하나에 엉뚱한 곳을 보게 되고 검사가 「지키려던 것」이 아니라 다른 이유로
통과하거나 실패한다 (이희진 님 `#149`). 읽는 도구는 `conftest.py` 하나뿐이다.

값은 안 읽는다 — **이름과 구조만** 센다.
"""

import ast
import re

import pytest

from app.tests.deploy.conftest import (
    COMPOSE_VAR,
    ROOT,
    compose,
    compose_vars,
    declared_names,
    host_side,
    read,
    service,
    service_ports,
)

#: compose 파일과 **그 짝인 예시**. 둘을 싸잡아 보면 안 된다 — 로컬 compose 는
#: `WEB_VERSION` 을 안 쓰고, 운영 compose 는 빌드 컨텍스트를 안 쓴다.
#:
#: `deployment.sh` 가 `envs/.prod.env` → 원격 `.env`,
#: `infra/docker/docker-compose.prod.yml` → 원격 `docker-compose.yml` 로 올린다.
PAIRS = (
    ("docker-compose.yml", "envs/example.local.env"),
    ("infra/docker/docker-compose.prod.yml", "envs/example.prod.env"),
)
COMPOSES = tuple(c for c, _ in PAIRS)
PROD = "infra/docker/docker-compose.prod.yml"

#: `${NAME}` · `${NAME:-기본값}` 둘 다.


@pytest.mark.parametrize("rel", COMPOSES)
def test_the_compose_file_actually_asks_for_things(rel: str) -> None:
    """**아래 검사가 조용히 통과하지 않게 한다.**"""
    found = set(COMPOSE_VAR.findall(read(rel)))

    assert len(found) > 5, f"{rel} 에서 변수를 거의 못 찾았다 — 검사가 헛돈다: {sorted(found)}"


@pytest.mark.parametrize(("rel", "example"), PAIRS)
def test_every_compose_variable_is_named_in_its_example(rel: str, example: str) -> None:
    """compose 가 부르는데 예시엔 없는 이름이 있으면 여기서 운다."""
    missing = sorted(set(COMPOSE_VAR.findall(read(rel))) - declared_names(example))

    assert not missing, f"{rel} 이 부르는데 {example} 에 이름조차 없다: {missing}"


@pytest.mark.parametrize("example", tuple(e for _, e in PAIRS))
def test_the_name_reader_does_not_invent_names(example: str) -> None:
    """**산문을 선언으로 읽으면 위 검사가 헛돈다.**

    예전 판은 `"=" in line` 만 봐서 `# db (Docker 실행: DB_HOST=mysql …)` 을
    `db (Docker 실행: DB_HOST` 로 읽었다. 가짜 이름이 목록에 섞이면 「빠진
    이름」 집합이 줄어들어, 정작 없는 변수를 있다고 본다.
    """
    invented = sorted(n for n in declared_names(example) if not re.fullmatch(r"[A-Z][A-Z0-9_]*", n))

    assert not invented, f"{example} 에서 산문을 이름으로 읽었다: {invented}"


@pytest.mark.parametrize("example", tuple(e for _, e in PAIRS))
def test_the_examples_carry_no_minio_value(example: str) -> None:
    """이름은 보여 주되 **값은 저장소에 없다** — KEY-191 범위 첫 줄."""
    filled = [
        line
        for line in read(example).splitlines()
        if line.startswith("MINIO_") and "=" in line and line.split("=", 1)[1].strip()
    ]

    assert not filled, f"{example} 에 MinIO 실값이 적혀 있다: {filled}"


class TestMinioIsInBothPlaces:
    """**팀 서버는 운영 compose 로 돈다.**

    처음 판은 루트 `docker-compose.yml` 에만 넣고 이 검사도 거기만 봤다.
    그러면 로컬에서만 돌고 정작 「팀이 나눠 갖는 자리」는 안 생긴다 —
    KEY-191 목적 첫 줄이 「팀 서버에 … 추가」다.
    """

    @pytest.mark.parametrize("rel", COMPOSES)
    def test_it_is_pinned_by_digest(self, rel: str) -> None:
        """같은 바이트를 나눠 갖는 자리라 판이 흔들리면 안 된다 (KEY-190 방식)."""
        image = service(rel, "minio").get("image", "")

        assert "minio/minio" in image, f"{rel}: minio 이미지가 아니다 — {image!r}"
        assert "@sha256:" in image, f"{rel}: digest 가 없다 — 같은 태그가 다른 것을 가리킬 수 있다"

    @pytest.mark.parametrize("rel", COMPOSES)
    def test_the_data_survives_a_restart(self, rel: str) -> None:
        """이름 붙은 볼륨이 없으면 `docker compose down` 에 올린 것이 사라진다."""
        doc = compose(rel)
        mounts = service(rel, "minio").get("volumes", [])

        assert any(str(m).endswith(":/data") and str(m).startswith("minio_data") for m in mounts), (
            f"{rel}: MinIO 가 이름 붙은 볼륨 없이 돈다 — {mounts}"
        )
        assert "minio_data" in (doc.get("volumes") or {}), f"{rel}: minio_data 볼륨이 선언돼 있지 않다"

    def test_production_does_not_open_it_to_the_internet(self) -> None:
        """**「팀 6인만」이 자격증명 하나에만 걸려 있으면 안 된다.**

        9000(S3 API)·9001(콘솔)이 공개로 붙으면 보안 그룹 한 번 잘못 열린
        것으로 끝난다. `127.0.0.1` 에 묶어 두면 SSH 터널을 지나야 한다.
        """
        published = [str(p) for p in service(PROD, "minio").get("ports", [])]

        assert published, "운영 MinIO 의 포트 줄을 못 찾았다 — 검사가 헛돈다"
        wide_open = [p for p in published if not p.startswith("127.0.0.1:")]
        assert not wide_open, f"운영 MinIO 포트가 밖으로 열려 있다: {wide_open}"


class TestProductionPublishesOnlyTheWebPorts:
    """**보안 그룹 하나에 환자 표가 걸려 있으면 안 된다** — KEY-192 배포 준비.

    MinIO 를 `127.0.0.1` 에 묶고 나서 같은 파일을 다시 보니, MySQL · Redis ·
    FastAPI 가 여전히 호스트로 열려 있었다. 앱은 도커 네트워크로 지나간다 —
    `DB_HOST=mysql` · `REDIS_HOST=redis` · `upstream fastapi { server
    fastapi:8000; }`. 그 포트들은 **사람이 들여다볼 때만** 쓴다.

    그런데 EC2 보안 그룹을 한 번 잘못 열면 그대로 인터넷에 붙는다.
    같은 규칙을 셋에 마저 걸었다.

    **묶고 나서 실제로 띄워 봤다** — 운영 compose 로 스택을 올리니
    `/` 200, `/api/v1/health` 가 api·db·redis 전부 ok 였다.
    """

    #: 밖에서 닿아야 하는 것은 웹 둘뿐이다.
    PUBLIC = {"80", "443"}

    def test_only_the_web_ports_face_the_world(self) -> None:
        exposed: dict[str, list[str]] = {}
        for name, svc in (compose(PROD).get("services") or {}).items():
            for spec in svc.get("ports") or []:
                if not str(spec).startswith("127.0.0.1:"):
                    exposed.setdefault(name, []).append(str(spec))

        assert exposed, "운영 compose 에서 열린 포트를 하나도 못 찾았다 — 검사가 헛돈다"

        wrong = {n: p for n, p in exposed.items() if n != "nginx"}
        assert not wrong, f"nginx 말고 밖으로 열린 것이 있다: {wrong}"

        ports = {p.split(":")[0] for p in exposed["nginx"]}
        assert ports <= self.PUBLIC, f"nginx 가 웹 포트 말고 다른 것도 연다: {sorted(ports - self.PUBLIC)}"

    @pytest.mark.parametrize("name", ["mysql", "redis", "fastapi", "minio"])
    def test_the_internal_services_stay_on_localhost(self, name: str) -> None:
        """이름을 박아 둔다 — 하나가 조용히 빠지면 위 검사만으로는 안 보인다."""
        published = service_ports(PROD, name)

        assert published, f"{name} 의 포트 줄을 못 찾았다 — 검사가 헛돈다"
        wide = [p for p in published if not p.startswith("127.0.0.1:")]
        assert not wide, f"{name} 가 밖으로 열려 있다: {wide}"


class TestTheWorkerCanReadWhatTheAppWrote:
    """**업로드한 파일을 워커가 열 수 있는가** — KEY-197 후속.

    워커는 `document.file_path` 를 그대로 열어 CLOVA 에 보낸다. 그런데
    `ai-worker` 에 업로드 볼륨이 아예 없어서 **OCR 이 전부
    `FileNotFoundError` 로 죽었다** — 로컬·운영 양쪽 다.

    로컬 `fastapi` 쪽 주석이 「Worker(로컬)와 업로드 파일 공유 (KEY-56)」
    라고 적어 두었는데 정작 워커에는 그 줄이 없었다. 의도는 있었고
    한쪽만 들어갔다.

    운영에는 하나가 더 있었다 — `UPLOAD_DIR` 이 `/vol/web/media` 인데
    `fastapi` 볼륨은 `/app/media` 였다. 업로드가 **볼륨 밖**에 떨어져
    재시작하면 사라지고 nginx 도 못 봤다.
    """

    #: (compose, 짝인 예시 env)
    UPLOADS = (
        ("docker-compose.yml", "envs/example.local.env"),
        ("infra/docker/docker-compose.prod.yml", "envs/example.prod.env"),
    )

    @staticmethod
    def _mounts(rel: str, name: str) -> list[str]:
        return [str(v) for v in service(rel, name).get("volumes") or []]

    @staticmethod
    def _split(mount: str) -> tuple[str, str]:
        """마운트 문자열을 **(왼쪽, 컨테이너 안 경로)** 로 쪼갠다.

        `host:container` 만 있는 것이 아니다. `host:container:ro` 처럼 **세 토막**이
        오는 형식이 같은 파일에 이미 쓰이고 있다.

            ./infra/docker/initdb.d:/docker-entrypoint-initdb.d:ro
            ./frontend:/vol/web/frontend:ro

        처음에는 `endswith(f":{upload_dir}")` 와 `rsplit(":", 1)` 로 두 토막만
        가정했다. 그러면 나중에 누가 워커의 media 볼륨에 `:ro` 를 붙이는 순간
        — 워커는 읽기만 하므로 **자연스러운 강화 조치다** — 검사가 그 마운트를
        아예 못 찾아 「볼륨이 없다」는 **거짓 실패**를 낸다. 볼륨은 있는데.
        이희진 님이 `#157` ① 로 짚어 주셨고, 실제로 붙여 재현했다.

        마지막 토막이 옵션(`ro` · `rw` · `z` · `Z` · `delegated` …)이면 떼어 낸다.
        컨테이너 안 경로는 반드시 `/` 로 시작하므로 그것으로 가른다 — 옵션 이름을
        일일이 나열하면 새 옵션이 생길 때 또 같은 함정에 빠진다.
        """
        parts = mount.split(":")
        if len(parts) >= 3 and not parts[-1].startswith("/"):
            parts = parts[:-1]
        left, container = ":".join(parts[:-1]), parts[-1]
        return left, container

    @staticmethod
    def _upload_dir(example: str) -> str:
        """**앱이 실제로 쓰는 자리.** 예시 env 가 정해 두었으면 그 값, 비워
        두었으면 `Settings` 의 기본값 — 앱이 고르는 순서 그대로다.

        기본값은 `config.py` 를 AST 로 읽는다. 글자로 훑으면 주석에 적힌
        경로를 잡아 검사가 재는 척만 하게 된다.
        """
        declared = [
            line.split("=", 1)[1].strip() for line in read(example).splitlines() if line.startswith("UPLOAD_DIR=")
        ]
        if declared and declared[0]:
            return declared[0]

        tree = ast.parse(read("app/core/config.py"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "UPLOAD_DIR"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                return node.value.value
        raise AssertionError("config.py 에서 UPLOAD_DIR 기본값을 못 찾았다")

    @pytest.mark.parametrize(("rel", "example"), UPLOADS)
    def test_the_worker_shares_the_upload_dir(self, rel: str, example: str) -> None:
        upload_dir = self._upload_dir(example)
        api = [m for m in self._mounts(rel, "fastapi") if self._split(m)[1] == upload_dir]
        worker = [m for m in self._mounts(rel, "ai-worker") if self._split(m)[1] == upload_dir]

        assert api, f"{rel}: fastapi 가 {upload_dir} 에 볼륨을 안 붙였다"
        assert worker, (
            f"{rel}: ai-worker 에 {upload_dir} 볼륨이 없다 — 워커가 업로드 파일을 못 열어 "
            "OCR 이 FileNotFoundError 로 전부 죽는다"
        )
        assert {self._split(m)[0] for m in api} == {self._split(m)[0] for m in worker}, (
            f"{rel}: fastapi 와 ai-worker 가 서로 다른 곳을 본다 — {api} vs {worker}"
        )

    @pytest.mark.parametrize(("rel", "example"), UPLOADS)
    def test_the_volume_is_where_the_app_actually_writes(self, rel: str, example: str) -> None:
        """**볼륨이 앱이 쓰는 자리에 붙어 있어야 한다.**

        운영에서 `UPLOAD_DIR=/vol/web/media` 인데 볼륨은 `/app/media` 였다.
        컨테이너는 뜨고 업로드도 성공하지만, 파일이 볼륨 밖에 떨어져
        **재시작하면 사라진다.**
        """
        expected = self._upload_dir(example)

        mounted = [self._split(m)[1] for m in self._mounts(rel, "fastapi")]
        assert expected in mounted, (
            f"{rel}: 앱은 {expected} 에 쓰는데 볼륨은 {mounted} 에 붙었다 — "
            "업로드가 볼륨 밖에 떨어져 재시작하면 사라진다"
        )

    def test_nginx_serves_the_same_place_in_production(self) -> None:
        """nginx 가 다른 곳을 보면 올린 파일을 못 준다."""
        prod = "infra/docker/docker-compose.prod.yml"
        api = {self._split(m)[0] for m in self._mounts(prod, "fastapi") if "media" in m}
        web = {self._split(m)[0] for m in self._mounts(prod, "nginx") if "media" in m}

        assert api and web, f"media 볼륨을 못 찾았다 — fastapi {api} · nginx {web}"
        assert api == web, f"fastapi 와 nginx 가 다른 볼륨을 본다 — {api} vs {web}"


class TestHostPortsAreNotAlsoAppPorts:
    """**밖에서 보이는 번호와 앱이 붙는 번호는 다른 값이어야 한다** — KEY-193.

    `redis` 는 `REDIS_PORT` 하나가 두 자리를 겸했다. 그런데 그 값은 앱이
    붙을 때도 쓰는 값이라(`config.REDIS_PORT`), 호스트 포트를 바꾸면 앱이
    `redis:<그 값>` 으로 붙으려다 실패한다. 배포 리허설에서 `16379` 로 두니
    health 가 `redis: connection_failed` 였다.

    `mysql` 은 처음부터 `DB_EXPOSE_PORT`(호스트) 와 `DB_PORT`(내부)로 갈려
    있었다. 같은 규칙을 전체에 건다.
    """

    #: 앱이 붙을 때 쓰는 설정 이름 → 그 값을 실제로 듣는 컨테이너의 자리.
    #: 이름을 박아 두지만, 아래 제네릭 검사가 새 서비스도 함께 본다.
    APP_SIDE = (("redis", "REDIS_PORT"), ("mysql", "DB_PORT"))

    def test_no_service_publishes_with_its_own_app_port(self) -> None:
        """**서비스를 다 돈다** — 이름 박은 목록에 없는 것도 잡는다.

        앞으로 세 번째 서비스가 같은 겸용 버그를 가져도, 누가 `APP_SIDE` 에
        추가하는 걸 기억하지 않아도 여기서 걸린다 (이희진 님 `#155` ⑤).

        규칙: 어떤 포트 줄의 **컨테이너 쪽**에 쓰인 변수는 **호스트 쪽**에
        나오면 안 된다.
        """
        offenders = []
        for name, svc in (compose(PROD).get("services") or {}).items():
            for spec in (str(port) for port in svc.get("ports") or []):
                host = host_side(spec)
                inside = spec[len(host) :].lstrip(":")
                shared = compose_vars(host) & compose_vars(inside)
                if shared:
                    offenders.append(f"{name}: {sorted(shared)} — {spec}")

        assert not offenders, f"호스트 쪽과 컨테이너 쪽이 같은 변수를 쓴다: {offenders}"

    @pytest.mark.parametrize(("service_name", "app_var"), APP_SIDE)
    def test_the_app_port_is_not_used_for_the_host_side(self, service_name: str, app_var: str) -> None:
        """이름을 박아 둔다 — 위 검사가 무슨 이유로 조용해져도 이건 운다."""
        published = service_ports(PROD, service_name)

        assert published, f"{service_name} 의 포트 줄을 못 찾았다 — 검사가 헛돈다"
        for spec in published:
            assert app_var not in compose_vars(host_side(spec)), (
                f"{service_name}: 호스트 쪽에 앱 접속 포트({app_var})를 썼다 — "
                f"밖을 바꾸면 앱이 안쪽에서 길을 잃는다: {spec}"
            )

    @pytest.mark.parametrize(("service_name", "app_var"), APP_SIDE)
    def test_the_container_actually_listens_on_it(self, service_name: str, app_var: str) -> None:
        """**앱만 아는 값이 되면 안 된다.**

        예전 판은 파일 전체 텍스트에서 `${REDIS_PORT}` 를 찾았다. 그런데 그
        이름은 `ports:` 줄에도 있어서, `command` 를 지우고 `--port 6379` 로
        되돌려도(= KEY-193 버그를 그대로 재현해도) **통과했다**
        (이희진 님 `#155` ①).

        그래서 컨테이너를 띄우는 자리(`command` · `healthcheck`)만 떼어 본다.
        """
        svc = service(PROD, service_name)
        runs = " ".join(
            [str(svc.get("command") or "")] + [str(part) for part in (svc.get("healthcheck") or {}).get("test") or []]
        )

        assert runs.strip(), f"{service_name} 에 command·healthcheck 가 없다 — 검사가 헛돈다"
        assert app_var in compose_vars(runs), (
            f"{service_name}: 컨테이너가 {app_var} 를 안 듣는다 — 그 값은 앱만 아는 값이 되고, "
            f"바꾸는 순간 앱이 없는 포트로 붙는다: {runs[:120]}"
        )

    @pytest.mark.parametrize(("service_name", "app_var"), APP_SIDE)
    def test_the_app_port_has_a_default(self, service_name: str, app_var: str) -> None:
        """**비면 컨테이너가 아예 안 뜬다** — 갈라 놓으면서 넓어진 실패 범위.

        예전에는 컨테이너 쪽이 고정 숫자라 이 값이 비어도 떴다. 이제
        `ports` · `command` · `healthcheck` 셋이 걸려 있다 (이희진 님 `#155` ②).
        """
        # **주석은 뺀다.** 설명에 적힌 `${DB_PORT}` 같은 낱말이 걸린다 —
        # 이 저장소에서 여러 번 밟은 함정이다.
        code = "\n".join(line.split("#", 1)[0] for line in read(PROD).splitlines())
        used = re.findall(r"\$\{" + app_var + r"(:-[^}]*)?\}", code)

        assert used, f"{app_var} 가 운영 compose 에 안 쓰인다"
        assert all(used), f"{service_name}: {app_var} 에 기본값이 없다 — 비면 컨테이너가 안 뜬다"

    def test_both_names_are_shown_in_the_examples(self) -> None:
        """예시가 이름을 안 보여 주면 베낀 사람이 갈린 줄 모른다."""
        for example in ("envs/example.prod.env", "envs/example.local.env"):
            named = declared_names(example)
            missing = sorted({"REDIS_PORT", "REDIS_EXPOSE_PORT", "DB_PORT", "DB_EXPOSE_PORT"} - named)
            assert not missing, f"{example} 에 이름이 없다: {missing}"


class TestTheBucketIsNotPublic:
    """**정책이 문서에만 있으면 아무도 안 지킨다** — 이희진 님 `#149` ④.

    첫 판은 「익명 GET 403」을 손으로 한 번 확인하고 문서에 적었다. 그런데
    버킷이 다른 서버에서 다시 만들어지거나 누가 `mc anonymous set public` 을
    한 번 돌리면, 이 저장소의 어떤 것도 그걸 못 잡는다.
    """

    INIT = "scripts/minio_init.sh"

    def test_there_is_an_init_that_creates_the_bucket(self) -> None:
        assert (ROOT / self.INIT).exists(), f"{self.INIT} 이 없다 — 버킷을 손으로 만들고 있다"
        assert (ROOT / self.INIT).stat().st_mode & 0o111, f"{self.INIT} 이 실행 가능하지 않다"

    @staticmethod
    def _commands(rel: str) -> list[str]:
        """**주석을 빼고 실행되는 줄만.**

        낱말로 훑으면 「누가 `mc anonymous set public` 을 한 번 돌리면」 같은
        **설명 문장**이 걸린다. 이 저장소에서 네 번째 밟는 함정이라, 여기서는
        주석을 떼고 본다.
        """
        out = []
        for line in read(rel).splitlines():
            code = line.split("#", 1)[0].strip()
            if code:
                out.append(code)
        return out

    def test_it_closes_anonymous_access_explicitly(self) -> None:
        """MinIO 기본값이 private 이지만 **기대지 않는다.**"""
        commands = self._commands(self.INIT)

        assert any("anonymous set none" in c for c in commands), "익명 접근을 명시적으로 닫지 않는다"

        opens = [c for c in commands if re.search(r"anonymous\s+set\s+(public|download|upload)", c)]
        assert not opens, f"익명 접근을 여는 명령이 있다: {opens}"

    def test_it_does_not_take_the_password_on_the_command_line(self) -> None:
        """`ps` 에 남는다 — `deployment.sh` 가 같은 이유로 고쳐졌다 (KEY-174)."""
        commands = self._commands(self.INIT)

        assert any("MC_HOST_" in c for c in commands), "자격증명을 환경변수로 안 받는다"
        leaks = [c for c in commands if re.search(r"mc\s+alias\s+set", c)]
        assert not leaks, f"별칭을 명령줄에서 만든다 — 비밀번호가 ps 에 남는다: {leaks}"


class TestTheDocsSayWhereItLives:
    """KEY-163 §8 이 「미확인」으로 열어 두었던 자리가 채워졌는가."""

    def test_the_decision_row_is_filled(self) -> None:
        row = [
            ln
            for ln in read("docs/decisions/KEY-163-ocr-real-contract.md").splitlines()
            if "합성 EMR 이미지 보관 위치" in ln and ln.startswith("|")
        ]

        assert row, "§8 에서 보관 위치 행을 못 찾았다"
        assert "(확정 후 기입)" not in row[0], "보관 위치가 아직 미확정으로 남아 있다"
        assert "MinIO" in row[0], f"결정이 MinIO 를 안 가리킨다: {row[0]}"

    def test_the_fixture_doc_names_the_same_bucket(self) -> None:
        """문서 둘이 다른 자리를 가리키면 둘 중 하나를 믿고 헤맨다."""
        body = read("docs/ocr-fixtures.md")

        assert "아직 정해지지 않았다" not in body, "§5 가 아직 미정이라고 말한다"
        assert "ocr-fixtures" in body and "MinIO" in body
        assert "폐기" in body, "폐기 정책이 없다 — KEY-191 인수조건 5"
