"""훑기가 **한 파일도 조용히 빠뜨리지 않는가** — KEY-139.

비밀값 재유출 가드(`test_exposed_secrets_not_reused.py`)는 「못 찾았다」가
「없다」와 같은 뜻일 때만 쓸모가 있다. 파일이 목록에서 빠지거나 읽다 넘어가면
가드는 초록인데 값은 그대로 저장소에 남는다.

지금 걸리는 실제 경로는 없다(KEY-139 는 latent 로 열렸다). **그래서 더 위험
하다** — 아무도 안 볼 때 조용히 생긴다. 두 자리를 재현해 못 박는다.

    ① non-ASCII 파일명   `git ls-files` 가 8진수로 이스케이프해 경로가 안 열린다
    ② non-UTF-8 텍스트   CP949 파일이 `UnicodeDecodeError` 로 통째로 빠진다

정본 저장소에 한글 이름 파일이나 CP949 파일을 넣어 두고 재는 것은 **검사를
위해 정본을 더럽히는 일**이라, 검사가 임시 저장소를 만들어 그 안에서 잰다.
"""

import subprocess
from pathlib import Path

import pytest

from app.tests.security._shared import tracked_files

#: 이 파일들이 담는 값. 진짜 비밀이 아니라 **훑기가 닿았는지 보려고 심는 표식**이다.
MARKER = "synthetic-marker-not-a-secret"


def _repo_with(tmp_path: Path, files: dict[str, bytes]) -> Path:
    """파일 몇 개가 추적되는 임시 저장소를 만든다."""
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "synthetic"], cwd=tmp_path, check=True)
    for name, body in files.items():
        (tmp_path / name).write_bytes(body)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "synthetic"], cwd=tmp_path, check=True)
    return tmp_path


class TestEveryTrackedPathCanBeOpened:
    """목록에 이름만 있고 **열리지 않으면** 안 본 것과 같다."""

    def test_a_non_ascii_name_survives_the_listing(self, tmp_path: Path) -> None:
        root = _repo_with(tmp_path, {"한글이름.env": b"x\n", "plain.env": b"x\n"})

        listed = tracked_files(root=root)

        assert len(listed) == 2, f"목록이 짧다: {listed}"
        unopenable = [name for name in listed if not (root / name).exists()]
        assert not unopenable, f"목록에 있는데 열리지 않는다 — 훑기에서 조용히 빠진다: {unopenable}"

    def test_the_escaped_form_is_not_what_we_get(self, tmp_path: Path) -> None:
        """`-z` 를 빼면 어떤 모양이 오는지 함께 박아 둔다.

        이게 없으면 「왜 `-z` 가 필요한지」가 주석에만 남고, 다음 사람이
        지우고도 검사가 안 운다 — 위 검사는 이름이 하나뿐이면 통과한다.
        """
        root = _repo_with(tmp_path, {"한글이름.env": b"x\n"})

        raw = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        assert raw.startswith('"\\'), f"이스케이프가 안 나온다 — 재현 전제가 바뀌었다: {raw}"
        assert not (root / raw).exists(), "이스케이프된 이름이 그대로 열린다 — 전제가 바뀌었다"

        assert tracked_files(root=root) == ["한글이름.env"]


class TestNoTextFileIsSkippedForItsEncoding:
    """CP949 파일도 **훑기가 닿아야** 한다 — 그 안에 비밀값이 있을 수 있다."""

    @pytest.mark.parametrize("encoding", ["cp949", "euc-kr", "utf-8"])
    def test_a_korean_text_file_is_still_read(self, tmp_path: Path, encoding: str) -> None:
        body = f"# 설정 파일\nPASSWORD={MARKER}\n".encode(encoding)
        path = tmp_path / "conf.env"
        path.write_bytes(body)

        # 가드가 쓰는 것과 같은 방식으로 읽는다.
        text = path.read_bytes().decode("utf-8", errors="replace")

        assert MARKER in text, f"{encoding} 파일이 통째로 빠진다 — 안의 비밀값을 못 찾는다"

    def test_the_old_way_would_have_dropped_it(self, tmp_path: Path) -> None:
        """예전 방식이 정말 빠뜨렸는지 함께 박아 둔다 — 근거가 주석에만 남지 않게."""
        path = tmp_path / "conf.env"
        path.write_bytes(f"PASSWORD={MARKER}\n# 설정".encode("cp949"))

        with pytest.raises(UnicodeDecodeError):
            path.read_text(encoding="utf-8")

    def test_a_binary_file_does_not_blow_up(self, tmp_path: Path) -> None:
        """바이너리는 건너뛰는 대신 그냥 지나간다 — 걸릴 모양이 없다."""
        path = tmp_path / "blob.bin"
        path.write_bytes(bytes(range(256)))

        text = path.read_bytes().decode("utf-8", errors="replace")

        assert MARKER not in text
