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

import re

import pytest

from app.tests.deploy.conftest import ROOT, compose, declared_names, read, service

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
COMPOSE_VAR = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)")


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
        published = [str(p) for p in service(PROD, name).get("ports") or []]

        assert published, f"{name} 의 포트 줄을 못 찾았다 — 검사가 헛돈다"
        wide = [p for p in published if not p.startswith("127.0.0.1:")]
        assert not wide, f"{name} 가 밖으로 열려 있다: {wide}"


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
