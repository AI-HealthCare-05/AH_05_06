"""저장소에 비밀값이 들어와 있지 않은가 — KEY-11.

인수조건: 「실제 비밀값 파일이 Git 추적 대상에서 제외됨」

**점검을 문서로 두지 않는다.** 「PR 올리기 전에 확인하세요」는 바쁠 때 건너뛴다.
CI 가 매번 돌게 해서, 빠뜨리면 병합 전에 걸린다.

한 번 커밋된 비밀값은 지워도 히스토리에 남는다. 되돌릴 수 없으니 **들어오기 전에**
막아야 한다.
"""

import re
import subprocess

import pytest

from app.tests.security._shared import REPO_ROOT as REPO
from app.tests.security._shared import tracked_files

#: 실제 값이 들어 있는 파일들. 예시(`example.*.env`)는 추적해도 된다.
MUST_BE_IGNORED = (".env", "envs/.local.env", "envs/.prod.env")

#: 예시 파일에 남아 있으면 안 되는 것. 자리표시자는 통과시킨다.
PLACEHOLDER = re.compile(r"^(your[-_]|<|changeme|xxx|\.\.\.|$)", re.IGNORECASE)

SECRET_ASSIGNMENTS = re.compile(
    r"^(?P<key>[A-Z_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|CREDENTIAL)[A-Z_]*)\s*=\s*(?P<value>.*)$"
)

#: 이름에 TOKEN 이 들어가도 비밀이 아닌 것들 — 수명 · 알고리즘 같은 설정값이다.
#: ACCESS_TOKEN_EXPIRE_MINUTES=60 을 비밀로 보면 검사가 늘 빨간불이라 아무도 안 본다.
NOT_A_SECRET = re.compile(r"(_EXPIRE|_MINUTES|_SECONDS|_DAYS|_ALGORITHM|_PORT|_HOST|_NAME|_USER)$")


def is_secret_value(key: str, value: str) -> bool:
    """이 줄이 실제 비밀값을 담고 있는가."""
    if NOT_A_SECRET.search(key):
        return False
    stripped = value.strip().strip("\"'")
    if not stripped or stripped.isdigit():  # 숫자만이면 설정값이다
        return False
    return not PLACEHOLDER.match(stripped)


class TestRealSecretFilesAreNotTracked:
    @pytest.mark.parametrize("path", MUST_BE_IGNORED)
    def test_not_tracked(self, path: str) -> None:
        """한 번 커밋되면 지워도 히스토리에 남는다."""
        assert path not in tracked_files(), f"{path} 가 Git 에 추적되고 있다 — 실제 비밀값 파일이다"

    @pytest.mark.parametrize("path", MUST_BE_IGNORED)
    def test_gitignore_covers_it(self, path: str) -> None:
        """추적만 안 되는 것으로는 부족하다. `git add .` 한 번에 들어올 수 있다."""
        result = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO, capture_output=True, text=True)
        assert result.returncode == 0, f"{path} 가 .gitignore 에 안 걸린다 — git add . 로 들어온다"


class TestExampleFilesCarryNoRealValues:
    """예시 파일은 추적한다. 그래서 **거기 실제 값이 있으면 그게 유출**이다."""

    EXAMPLES = tuple(p for p in (REPO / "envs").glob("example.*.env"))

    def test_examples_exist(self) -> None:
        assert self.EXAMPLES, "envs/example.*.env 가 없다 — 신규 팀원이 실행할 수 없다"

    def test_no_real_secret_values(self) -> None:
        leaked: list[str] = []
        for path in self.EXAMPLES:
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = SECRET_ASSIGNMENTS.match(line.strip())
                if not match:
                    continue
                if is_secret_value(match.group("key"), match.group("value")):
                    leaked.append(f"{path.name}:{lineno} {match.group('key')}")
        assert not leaked, f"예시 파일에 실제 값으로 보이는 것이 있다 — 자리표시자로 바꿔라(your-... 꼴): {leaked}"

    def test_local_and_prod_examples_differ(self) -> None:
        """같은 서명 키를 로컬과 운영이 나눠 쓰면, 노트북에서 운영 토큰을 만들 수 있다.

        자리표시자라면 같아도 되지만, 실제 값이 들어가는 순간 갈려야 한다.
        이 검사는 「둘 다 자리표시자인가」를 보는 것으로 그 상태를 지킨다.
        """
        values: dict[str, set[str]] = {}
        for path in self.EXAMPLES:
            for line in path.read_text(encoding="utf-8").splitlines():
                match = SECRET_ASSIGNMENTS.match(line.strip())
                if match:
                    values.setdefault(match.group("key"), set()).add(match.group("value").strip())

        shared_real = [key for key, seen in values.items() if len(seen) == 1 and is_secret_value(key, next(iter(seen)))]
        assert not shared_real, f"로컬과 운영이 같은 실제 값을 쓴다: {shared_real}"


class TestNoSecretsInSource:
    """소스에 박힌 비밀값은 마스킹이 못 막는다.

    트레이스백이 소스 줄을 그대로 읽어 오기 때문이다(`test_masking.py` 참고).
    그러니 소스에 들어오는 것을 여기서 막는다.
    """

    def test_no_private_key_blocks(self) -> None:
        marker = "-----BEGIN" + " PRIVATE KEY-----"  # 이 파일 자신이 걸리지 않게 나눠 쓴다
        offenders = []
        for name in tracked_files():
            path = REPO / name
            if not path.is_file() or path.suffix not in (".py", ".js", ".yml", ".yaml", ".env", ".md"):
                continue
            try:
                if marker in path.read_text(encoding="utf-8"):
                    offenders.append(name)
            except UnicodeDecodeError:
                continue
        assert not offenders, f"개인키가 저장소에 있다: {offenders}"
