"""`docker-compose.yml` 이 요구하는 것과 예시 파일이 어긋나지 않는가 — KEY-191.

compose 는 `${VAR}` 를 **조용히 빈 문자열로 바꾼다.** 그래서 예시에 이름조차
없는 변수가 생기면, 그 파일을 베껴 쓴 사람은 컨테이너가 뜨지 않는 것을 보고
나서야 안다 — 그때는 이미 서버 앞이다.

`Config.model_fields` 를 훑는 검사(`test_pilot_deploy_contract.py`)가 이미
있지만 **여기까지는 못 온다.** MinIO 는 앱이 안 쓰는 인프라라 `Config` 에
없다. 앱 설정과 compose 설정은 서로 다른 목록이고, 지금까지 뒤엣것은
아무도 안 봤다.

값은 안 읽는다 — **이름만** 센다.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "docker-compose.yml"
EXAMPLES = ("envs/example.local.env", "envs/example.prod.env")

#: `${NAME}` · `${NAME:-기본값}` 둘 다.
COMPOSE_VAR = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)")


def compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


def names_in(rel: str) -> set[str]:
    """예시 파일이 **이름을 보여 주는** 것들.

    주석 처리된 줄도 센다 — 값을 비워 두는 편이 맞는 설정이라도 이름은
    보여야 베낀 사람이 그런 것이 있다는 걸 안다 (`test_pilot_deploy_contract`
    의 같은 판단).
    """
    return {
        line.lstrip("# ").split("=", 1)[0].strip()
        for line in (ROOT / rel).read_text(encoding="utf-8").splitlines()
        if "=" in line
    }


def test_the_compose_file_actually_asks_for_things() -> None:
    """**아래 검사가 조용히 통과하지 않게 한다.**"""
    found = set(COMPOSE_VAR.findall(compose_text()))

    assert len(found) > 5, f"compose 에서 변수를 거의 못 찾았다 — 검사가 헛돈다: {sorted(found)}"


@pytest.mark.parametrize("example", EXAMPLES)
def test_every_compose_variable_is_named_in_the_example(example: str) -> None:
    """compose 가 부르는데 예시엔 없는 이름이 있으면 여기서 운다."""
    missing = sorted(set(COMPOSE_VAR.findall(compose_text())) - names_in(example))

    assert not missing, f"{example} 에 이름조차 없다 — 베껴 쓰면 빈 값으로 뜬다: {missing}"


@pytest.mark.parametrize("example", EXAMPLES)
def test_the_examples_carry_no_minio_value(example: str) -> None:
    """이름은 보여 주되 **값은 저장소에 없다** — KEY-191 범위 첫 줄."""
    filled = [
        line
        for line in (ROOT / example).read_text(encoding="utf-8").splitlines()
        if line.startswith("MINIO_") and line.split("=", 1)[1].strip()
    ]

    assert not filled, f"{example} 에 MinIO 실값이 적혀 있다: {filled}"


class TestTheImageIsPinned:
    """**같은 바이트를 나눠 갖는 자리**라 판이 흔들리면 안 된다 (KEY-190 방식)."""

    def test_minio_is_pinned_by_digest(self) -> None:
        line = [ln.strip() for ln in compose_text().splitlines() if "minio/minio" in ln]

        assert line, "minio 이미지 줄을 못 찾았다"
        assert "@sha256:" in line[0], f"digest 가 없다 — 같은 태그가 다른 것을 가리킬 수 있다: {line[0]}"

    def test_the_data_survives_a_restart(self) -> None:
        """이름 붙은 볼륨이 없으면 `docker compose down` 에 올린 것이 사라진다."""
        body = compose_text()

        assert "minio_data:/data" in body, "MinIO 가 볼륨 없이 돈다 — 재시작하면 다 날아간다"
        assert re.search(r"^volumes:$.*^  minio_data:$", body, re.MULTILINE | re.DOTALL), (
            "minio_data 볼륨이 선언돼 있지 않다"
        )


class TestTheDocsSayWhereItLives:
    """KEY-163 §8 이 「미확인」으로 열어 두었던 자리가 채워졌는가."""

    def test_the_decision_row_is_filled(self) -> None:
        row = [
            ln
            for ln in (ROOT / "docs/decisions/KEY-163-ocr-real-contract.md").read_text(encoding="utf-8").splitlines()
            if "합성 EMR 이미지 보관 위치" in ln and ln.startswith("|")
        ]

        assert row, "§8 에서 보관 위치 행을 못 찾았다"
        assert "(확정 후 기입)" not in row[0], "보관 위치가 아직 미확정으로 남아 있다"
        assert "MinIO" in row[0], f"결정이 MinIO 를 안 가리킨다: {row[0]}"

    def test_the_fixture_doc_names_the_same_bucket(self) -> None:
        """문서 둘이 다른 자리를 가리키면 둘 중 하나를 믿고 헤맨다."""
        body = (ROOT / "docs/ocr-fixtures.md").read_text(encoding="utf-8")

        assert "아직 정해지지 않았다" not in body, "§5 가 아직 미정이라고 말한다"
        assert "ocr-fixtures" in body and "MinIO" in body
        assert "폐기" in body, "폐기 정책이 없다 — KEY-191 인수조건 5"
