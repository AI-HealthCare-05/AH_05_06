"""배포가 스키마를 따라오게 한다 — KEY-206.

**여태 배포 경로에 마이그레이션 단계가 없었다.** `deployment.sh` 는 이미지를
짓고 밀고, `.env`·compose·nginx 설정을 올리고, `docker compose up` 을 한다.
그게 전부다. DB 는 아무도 안 건드린다.

그래서 KEY-197 을 하다가 Pilot 에서 `guide_section.drug_caution_content_id` 가
통째로 없는 것을 발견했다. **사고가 아니라 이 구조의 당연한 결과였다** — 새
이미지를 올려도 DB 는 있던 자리에 그대로 있다.

여기서 재는 것은 「명령이 어딘가에 적혀 있는가」가 아니라 **그 명령이 배포를
멈출 수 있는 자리에 있는가**다. 순서가 틀리면 있으나 마나다.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "scripts" / "lib.sh"


def commands() -> list[str]:
    """**주석을 떼고 실행되는 줄만.**

    낱말로 훑으면 바로 위에 적어 둔 「`up -d` 뒤에 걸면」 같은 **설명 문장**이
    걸린다. 그러면 순서를 재는 검사가 산문을 재게 된다 — 이 저장소에서 여러 번
    밟은 자리라 여기서는 처음부터 떼고 본다.
    """
    out = []
    for line in LIB.read_text(encoding="utf-8").splitlines():
        code = line.split("#", 1)[0].strip()
        if code:
            out.append(code)
    return out


def _first(pattern: str) -> int:
    """그 명령이 처음 나오는 줄 번호(실행되는 줄만 센 것). 없으면 -1."""
    for i, line in enumerate(commands()):
        if re.search(pattern, line):
            return i
    return -1


def test_the_deploy_applies_migrations() -> None:
    """**배포가 DB 를 안 따라오면 스키마가 갈린다.**"""
    assert _first(r"\baerich\s+upgrade\b") >= 0, (
        "배포 경로에 `aerich upgrade` 가 없다 — 새 이미지를 올려도 DB 는 그대로 남는다. "
        "Pilot 에서 실제로 칸 하나가 통째로 없었다 (KEY-197)"
    )


def test_it_runs_before_the_app_is_swapped() -> None:
    """**순서가 틀리면 「실패하면 배포가 멈춘다」가 거짓이 된다.**

    `up -d` 뒤에 걸면, 마이그레이션이 죽어도 새 코드는 이미 돌고 있다.
    멈출 것이 남아 있지 않다.
    """
    migrate = _first(r"\baerich\s+upgrade\b")
    swap = _first(r"docker compose up\b")

    assert migrate >= 0 and swap >= 0, f"둘 중 하나를 못 찾았다 — 마이그레이션 {migrate} · 교체 {swap}"
    assert migrate < swap, (
        f"마이그레이션({migrate})이 `up -d`({swap}) 뒤에 있다 — 실패해도 새 코드는 "
        "이미 돌고 있어 배포를 멈춰 봐야 소용이 없다"
    )


def test_a_failure_stops_the_deploy() -> None:
    """`set -e` 가 없으면 마이그레이션이 죽어도 그냥 다음 줄로 간다."""
    assert _first(r"^set -e") >= 0, "원격 스크립트에 `set -e` 가 없다 — 실패가 배포를 못 멈춘다"


def test_it_only_migrates_when_the_app_is_deployed() -> None:
    """nginx 만 올리는 배포까지 DB 를 건드릴 이유는 없다."""
    joined = "\n".join(commands())

    assert "grep -qx fastapi" in joined, "무엇을 올리든 마이그레이션을 돈다 — nginx 만 올리는 배포도 DB 를 건드린다"


def test_the_image_it_runs_in_carries_aerich() -> None:
    """**명령이 도는 이미지에 도구와 마이그레이션이 없으면 그 단계는 못 돈다.**

    시드 스크립트에서 똑같은 자리를 밟았다 — 런북에 적힌 명령이 서버에서는
    「그런 파일 없음」으로 죽었다. 그래서 여기서는 `app/Dockerfile` 이 실제로
    무엇을 담는지 본다.

    2026-08-28 에 이미지를 지어 확인했다: aerich 0.9.2 · 마이그레이션 21 개 ·
    `[tool.aerich]` 설정. 빈 DB 에 걸어 25 표가 섰고 두 번째는 「No upgrade
    items found」였다.
    """
    dockerfile = (ROOT / "app" / "Dockerfile").read_text(encoding="utf-8")
    lines = [ln.split("#", 1)[0].strip() for ln in dockerfile.splitlines()]
    code = [ln for ln in lines if ln]

    assert any(re.search(r"COPY\s+.*pyproject\.toml", ln) for ln in code), (
        "이미지에 `pyproject.toml` 이 없다 — aerich 가 `[tool.aerich]` 설정을 못 읽는다"
    )
    assert any(re.search(r"COPY\s+\./app\b", ln) for ln in code), (
        "이미지에 `app/` 을 안 넣는다 — 마이그레이션 파일이 통째로 빠진다"
    )
    assert any("--group app" in ln for ln in code), "`app` 그룹을 안 설치한다 — 이 그룹에 aerich 가 들어 있다"


RUNBOOK = ROOT / "docs" / "deploy-runbook.md"
SECTION = "## 3-2. 배포가 DB 를 따라오게 한다"

#: 배포가 하는 일의 뼈대. 런북과 스크립트가 **같은 순서로** 말해야 한다.
STEPS = [
    ("이미지 받기", r"docker compose pull\b"),
    ("마이그레이션", r"\baerich\s+upgrade\b"),
    ("앱 교체", r"docker compose up\b"),
]


def _runbook_section() -> str:
    """그 절만. **문서 전체를 훑으면 다른 절의 같은 낱말을 잡는다.**

    이 런북에는 `docker compose up` 이 롤백 절에도 나온다. 통째로 훑으면
    그 줄을 순서 근거로 삼아, 실제로는 어긋났는데도 조용히 통과한다.
    """
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index(SECTION)
    rest = text[start + len(SECTION) :]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def _order(haystack: str, patterns: list[tuple[str, str]]) -> list[str]:
    """나오는 차례대로 이름을 늘어놓는다. 못 찾은 것은 뺀다."""
    found = [(m.start(), name) for name, pat in patterns if (m := re.search(pat, haystack))]
    return [name for _, name in sorted(found)]


def test_the_runbook_describes_this_step() -> None:
    """**있는 단계를 아무도 모르면 없는 것과 같다.**"""
    assert SECTION in RUNBOOK.read_text(encoding="utf-8"), (
        f"런북에 「{SECTION}」 절이 없다 — 배포가 무엇을 하는지 적힌 곳이 없다"
    )


def test_the_runbook_and_the_script_tell_the_same_order() -> None:
    """**적어 둔 순서와 실제 순서가 갈리면, 틀어졌을 때 아무도 못 고친다.**

    특히 마이그레이션이 앞이라는 것 — 그게 「실패하면 배포가 멈춘다」의
    근거인데, 문서가 뒤로 적어 두면 사람은 문서를 믿는다.
    """
    in_script = _order("\n".join(commands()), STEPS)
    in_runbook = _order(_runbook_section(), STEPS)

    assert len(in_script) == len(STEPS), f"스크립트에서 못 찾은 단계가 있다 — {in_script}"
    assert in_runbook == in_script, f"런북과 스크립트의 순서가 다르다\n  런북    {in_runbook}\n  스크립트 {in_script}"


def test_the_runbook_says_what_to_do_when_it_breaks() -> None:
    """**멈췄을 때 볼 곳이 없으면 런북이 아니다.**"""
    section = _runbook_section()

    for phrase in ("No upgrade items found", "aerich history", "--delete"):
        assert phrase in section, f"런북 3-2 절에 「{phrase}」 안내가 없다"
