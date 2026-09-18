"""KEY-343: ERD 산출물의 모델·migration 동기화 계약.

DB 초기화를 하는 app/tests 아래에 두지 않는다 — generate_erd.py 자체가
DB에 안 붙는다(모델 메타데이터만 읽는다). CI가 별도로 현재 모델·migration과
산출물 일치를 검사한다(iljun-sys 리뷰 — 이 검사를 부르는 곳이 문서 안내
문구 하나뿐이라 아무도 안 돌리고 있었다).
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import generate_erd  # noqa: E402


def test_upgrade_sql_literals_ignores_comments() -> None:
    """주석 속 CREATE/DROP TABLE 언급이 안 걸린다 — iljun-sys 리뷰로 재현된 버그.

    이 저장소는 migration에 한국어 산문 주석을 길게 다는 관례가 있다.
    "예전엔 이 표를 만들었다" 같은 주석 한 줄만으로 있지도 않은 표가
    잡히면 안 된다.
    """
    source = '''
async def upgrade(db) -> str:
    # 예전에는 CREATE TABLE `old_scratch_table` 을 여기서 만들었다 — 지금은 안 만든다.
    return """
        CREATE TABLE `real_table` (id BIGINT);
    """


async def downgrade(db) -> str:
    return "DROP TABLE `real_table`;"
'''
    literals = generate_erd._upgrade_sql_literals(source)
    assert "real_table" in literals
    assert "old_scratch_table" not in literals


def test_upgrade_sql_literals_does_not_read_downgrade() -> None:
    """downgrade()의 DROP TABLE이 upgrade 쪽 판정에 안 섞인다."""
    source = """
async def upgrade(db) -> str:
    return "CREATE TABLE `kept_table` (id BIGINT);"


async def downgrade(db) -> str:
    return "DROP TABLE `kept_table`;"
"""
    literals = generate_erd._upgrade_sql_literals(source)
    assert "kept_table" in literals
    # downgrade 쪽 DROP TABLE 문자열 자체가 안 들어가야, upgrade만 본다는
    # 것이 실제로 지켜진다.
    tree = ast.parse(source)
    downgrade_literal = next(
        inner.value
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "downgrade"
        for inner in ast.walk(node)
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str)
    )
    assert downgrade_literal not in literals.split("\n")


def test_check_reports_stale_artifacts() -> None:
    original = generate_erd.SOURCE_PATH.read_text(encoding="utf-8")
    generate_erd.SOURCE_PATH.write_text(original + "// tampered\n", encoding="utf-8")
    try:
        assert generate_erd.main(["--check"]) == 1
    finally:
        generate_erd.SOURCE_PATH.write_text(original, encoding="utf-8")


def test_generate_then_check_round_trips(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(generate_erd, "SOURCE_PATH", tmp_path / "current-erd.mmd")
    monkeypatch.setattr(generate_erd, "SVG_PATH", tmp_path / "current-erd.svg")
    monkeypatch.setattr(generate_erd, "DBML_PATH", tmp_path / "current-erd.dbml")

    assert generate_erd.main([]) == 0
    assert generate_erd.main(["--check"]) == 0
