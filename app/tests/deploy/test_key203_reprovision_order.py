"""**시연 당일에 읽는 절이 실제로 따라갈 수 있는가** — KEY-203.

런북의 나머지 절은 「무엇을 할 수 있는가」를 적은 배경이고, `4-4` 는 **어느 순서로
누가 무엇을 하는가**만 적는다. 그 절이 여섯 단계를 다 덮는지, 그리고 적어 둔 것이
코드와 어긋나지 않는지를 잰다.

## 절 안만 본다

이 파일은 런북 **전체**를 훑지 않는다. 오늘 같은 함정을 네 번 밟았다 — 절을
통째로 지워도 문서 다른 곳의 같은 글자를 보고 통과하는 자리다. `#155` 에서
이희진 님이 짚어 주신 것과 같은 종류라, 여기서는 처음부터 절 단위로 자른다.
"""

import re
from pathlib import Path

import pytest

from app.tests.deploy.conftest import read

ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = "docs/deploy-runbook.md"
SECTION = "## 4-4. 시연 전 재프로비저닝 — 한 번에 따라가는 순서 (KEY-203)"


def section() -> str:
    prose = read(RUNBOOK)
    assert SECTION in prose, f"런북에 「{SECTION}」 절이 없다 — 아래 검사가 전부 헛돈다"
    body = prose.split(SECTION, 1)[1]
    cut = body.find("\n## ")
    return body[:cut] if cut != -1 else body


class TestAllSixStepsAreThere:
    """여섯 단계 중 하나라도 빠지면 그 자리에서 막힌다."""

    #: (번호, 그 단계가 반드시 말해야 하는 것)
    STEPS = (
        ("①", "이미지"),
        ("②", "띄"),
        ("③", "스키마"),
        ("④", "합성 데이터"),
        ("⑤", "로그인"),
        ("⑥", "넘긴다"),
    )

    @pytest.mark.parametrize(("mark", "must_say"), STEPS)
    def test_the_step_has_its_own_heading(self, mark: str, must_say: str) -> None:
        headings = [ln for ln in section().splitlines() if ln.startswith("### ") and mark in ln]

        assert headings, f"{mark} 단계 제목이 없다"
        assert any(must_say in h for h in headings), f"{mark} 제목이 무엇을 하는 단계인지 안 알려 준다 — {headings}"

    def test_the_steps_are_in_order(self) -> None:
        """번호가 뒤섞이면 따라가다 되돌아가야 한다."""
        found = [
            mark for line in section().splitlines() if line.startswith("### ") for mark, _ in self.STEPS if mark in line
        ]
        assert found == [m for m, _ in self.STEPS], f"단계가 빠졌거나 순서가 어긋난다 — 문서에 나온 차례: {found}"


class TestItSaysWhoAndWhatIsLocked:
    """같은 서버를 두 사람이 동시에 만지면 무엇이 깨졌는지 알 수 없게 된다."""

    def test_it_names_the_people_per_step(self) -> None:
        body = section()
        for who in ("권일준", "한금준", "유가은"):
            assert who in body, f"{who} 이 어느 단계를 맡는지 안 적혀 있다"

    def test_it_freezes_the_demo_window(self) -> None:
        body = section()
        assert "시연 창" in body, "시연 창 동안의 변경 통제가 없다"
        assert "둘" in body or "두 명" in body, "만질 수 있는 사람이 몇인지 안 적혀 있다"


class TestSecretsNeverLandInTheDocument:
    """값이 문서에 들어가면 그 순간 공개 저장소에 남는다."""

    def test_it_names_the_variables_but_not_the_values(self) -> None:
        body = section()
        for name in ("SEED_STAFF_PASSWORD", "SMOKE_PASSWORD"):
            assert name in body, f"{name} 를 어떻게 나누는지 안 적혀 있다"

        assert "비밀번호 매니저" in body, "전달 수단이 안 적혀 있다"

    def test_no_value_looks_like_a_real_password(self) -> None:
        """`<합성 비밀번호>` 같은 자리표시자만 있어야 한다."""
        for line in section().splitlines():
            for match in re.finditer(r"(SEED_STAFF_PASSWORD|SMOKE_PASSWORD)=(\S+)", line):
                value = match.group(2)
                assert value.startswith(("'<", "<", "$", '"')), (
                    f"문서에 값처럼 보이는 것이 적혀 있다 — 「{line.strip()}」"
                )


class TestItWarnsWhereTheCommandsBite:
    """**적어 두지 않으면 시연 당일에 그 자리에서 멈춘다.**

    아래 셋은 전부 준비하다 실제로 밟은 것이다.
    """

    def test_it_says_the_deploy_script_does_not_start_everything(self) -> None:
        """`scripts/lib.sh` 가 `--no-deps` 로 고른 것만 띄운다."""
        assert "--no-deps" in read("scripts/lib.sh"), "lib.sh 가 바뀌었다 — 이 경고가 낡았다"

        body = section()
        assert "--no-deps" in body, (
            "배포 스크립트만으로는 전체가 안 뜬다는 것을 안 적었다 — mysql·redis 가 없는 채로 ③④ 를 시작하게 된다"
        )

    def test_it_says_health_is_not_enough(self) -> None:
        """`/api/v1/health` 는 `SELECT 1` 만 본다 — DB 가 비어도 `ok` 다."""
        body = section()
        assert "SELECT 1" in body, "health 만 보고 「배포 성공」이라 읽는 것을 안 막았다"

    def test_it_says_the_screen_path_is_not_slash_login(self) -> None:
        """nginx 가 `try_files … =404` 라 확장자 없는 `/login` 은 404 다."""
        assert "try_files" in read("infra/nginx/prod_http.conf"), "nginx 설정이 바뀌었다"

        body = section()
        assert "/login.html" in body, "화면을 어느 경로로 여는지 안 적었다"


class TestTheVolumeWipeIsSpelledOut:
    """`down -v` 는 되돌릴 수 없다 — 무엇이 사라지는지 적혀 있어야 한다."""

    def test_it_names_what_disappears(self) -> None:
        body = section()
        assert "down -v" in body, "볼륨 초기화 절차가 없다"

        declared = re.findall(r"^\s{2}([a-z_]+):$", read("infra/docker/docker-compose.prod.yml"), re.M)
        assert "mysql_data" in declared, "운영 compose 에 mysql_data 가 없다 — 이 경고가 낡았다"
        assert "mysql_data" in body, "무엇이 지워지는지 이름을 안 적었다"

    def test_it_says_how_to_keep_it(self) -> None:
        body = section()
        assert "보존" in body, "지우면 안 되는 경우에 어떻게 하는지 안 적혀 있다"


class TestItListsThePrerequisites:
    """선행이 빠진 채 시작하면 그 단계에서 반드시 멈춘다."""

    @pytest.mark.parametrize("key", ["KEY-196", "KEY-197", "KEY-200"])
    def test_each_prerequisite_is_named_with_its_symptom(self, key: str) -> None:
        body = section()
        assert key in body, f"선행 {key} 가 안 적혀 있다"

        line = next((ln for ln in body.splitlines() if key in ln), "")
        assert "멈춘다" in line or "실패" in line, (
            f"{key} 가 없으면 **무슨 일이 생기는지**를 안 적었다 — 「{line.strip()}」"
        )
