"""**로컬은 평소에 셋만 뜬다** — KEY-194.

프로필이 없던 때는 `docker compose up` 이 여섯을 통째로 띄웠다. OCR 픽스처와
무관한 사람도 MinIO 컨테이너와 헬스체크를 매번 함께 띄웠다 (이희진 님 `#149` ⑧).

여기서 재는 것 셋이다.

    무엇이 기본으로 뜨는가        redis · mysql · fastapi
    무엇이 프로필 뒤에 있는가      nginx → web · ai-worker · minio → ocr
    운영은 그대로인가             prod.yml 에 profiles 키가 없다

**세 번째가 가장 중요하다.** 운영에 프로필이 들어가면, 프로필을 안 준 배포가
조용히 절반만 띄운다 — 그리고 `docker compose up` 은 성공으로 끝난다.
"""

from typing import Any

import pytest

from app.tests.deploy.conftest import compose, read, service

LOCAL = "docker-compose.yml"
PROD = "infra/docker/docker-compose.prod.yml"

#: 프로필을 안 줘도 떠야 하는 것 — 앱을 고치는 데 필요한 최소.
DEFAULT_SERVICES = frozenset({"redis", "mysql", "fastapi"})

#: 프로필 뒤로 뺀 것.
GATED = {"nginx": "web", "ai-worker": "ocr", "minio": "ocr", "minio-init": "ocr"}

# minio-init은 bootstrap이 필요할 때 한 번 실행하고 사라지는 내부 도구다. README의
# 사용자용 프로필 표에는 계속 떠 있는 서비스만 설명한다(KEY-228; README 개편은
# KEY-229 범위).
DOCUMENTED_GATED = frozenset({"nginx", "ai-worker", "minio"})


def _profiles(rel: str, name: str) -> list[str]:
    return [str(p) for p in service(rel, name).get("profiles") or []]


class TestTheLocalStackIsLightByDefault:
    def test_the_default_three_have_no_profile(self) -> None:
        """프로필이 붙으면 기본에서 사라진다 — 앱이 안 뜨게 된다."""
        for name in sorted(DEFAULT_SERVICES):
            assert not _profiles(LOCAL, name), f"{name} 에 프로필이 붙었다 — `docker compose up` 만으로는 안 뜬다"

    @pytest.mark.parametrize(("name", "profile"), sorted(GATED.items()))
    def test_the_rest_are_opt_in(self, name: str, profile: str) -> None:
        assert _profiles(LOCAL, name) == [profile], (
            f"{name} 이 `{profile}` 프로필 뒤에 있지 않다 — {_profiles(LOCAL, name)}"
        )

    def test_every_service_is_accounted_for(self) -> None:
        """**새 서비스가 조용히 기본에 끼는 것**을 막는다.

        이것이 없으면 나중에 누가 무거운 서비스를 하나 더 넣어도 위 검사들은
        아무 말을 안 한다 — 이 일감이 처음 생긴 이유가 바로 그것이다.
        """
        services: dict[str, Any] = compose(LOCAL)["services"]
        known = DEFAULT_SERVICES | set(GATED)

        assert set(services) == known, (
            f"로컬 compose 의 서비스 목록이 바뀌었다 — 새것 {sorted(set(services) - known)} · "
            f"사라진 것 {sorted(known - set(services))}. 기본으로 둘지 프로필 뒤로 뺄지 정하고 "
            "이 검사를 함께 고쳐라."
        )


class TestProductionAlwaysStartsEverything:
    """**운영에는 프로필을 넣지 않는다.**

    넣는 순간, 프로필을 안 준 배포가 절반만 띄우고도 성공으로 끝난다.
    """

    def test_no_service_in_prod_is_gated(self) -> None:
        services: dict[str, Any] = compose(PROD)["services"]

        gated = {name: body.get("profiles") for name, body in services.items() if body.get("profiles")}
        assert not gated, f"운영 compose 에 프로필이 붙었다 — {gated}"

    def test_the_prod_file_does_not_even_mention_it(self) -> None:
        """YAML 로도 보고 글자로도 본다 — 주석은 뺀다."""
        live = "\n".join(line.split("#", 1)[0] for line in read(PROD).splitlines())

        assert "profiles:" not in live, "운영 compose 에 profiles 키가 적혀 있다"


class TestTheReadmeTellsYouHowToGetTheRest:
    """**문서에 없으면 아무도 못 찾는다.**

    기본이 셋으로 줄었다는 것을 모르면, 화면이 안 뜨는 것을 고장으로 읽는다.
    """

    @staticmethod
    def _table() -> str:
        """**표만 떼어 본다.**

        처음에는 README 전체에서 `--profile ocr` 를 찾았다. 그런데 그 글자는
        문서 다른 곳(워커 개별 실행 안내)에도 있어서, **표를 통째로 지워도**
        검사가 그것을 보고 통과했다. 재는 척만 하는 자리였다 — 이희진 님이
        `#155` 에서 짚어 주신 것과 같은 종류다.

        이제 프로필 표의 줄만 본다.
        """
        rows = [ln for ln in read("README.md").splitlines() if ln.startswith("| `--profile")]
        assert rows, "README 에 프로필 표가 없다"
        return "\n".join(rows)

    def test_the_readme_names_both_profiles(self) -> None:
        table = self._table()

        for profile in sorted(set(GATED.values())):
            assert f"--profile {profile}" in table, f"README 프로필 표에 `--profile {profile}` 가 없다"

    def test_the_table_says_what_each_one_adds(self) -> None:
        """이름만 있고 무엇이 뜨는지 안 적으면 표가 소용없다."""
        table = self._table()

        for name in sorted(DOCUMENTED_GATED):
            assert name in table, f"프로필 표가 `{name}` 이 뜬다는 것을 안 적었다"

    def test_the_readme_says_how_to_get_all_six_back(self) -> None:
        prose = read("README.md")
        both = [ln for ln in prose.splitlines() if "--profile web" in ln and "--profile ocr" in ln]

        assert both, "README 에 예전처럼 전부 띄우는 법이 없다"

    def test_the_readme_warns_the_test_suites_need_them(self) -> None:
        """smoke·종단 검사를 프로필 없이 돌리면 「연결 거부」로 죽는다."""
        prose = read("README.md")

        assert "walking skeleton" in prose, "README 가 smoke 실행에 프로필이 필요하다는 것을 안 적었다"
