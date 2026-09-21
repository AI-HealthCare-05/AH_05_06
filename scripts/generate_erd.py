"""현재 Tortoise 모델에서 KEY-343 ERD 원본과 SVG를 생성한다.

DB에는 접속하지 않는다. ``TORTOISE_APP_MODELS``에 등록된 모델 메타데이터만
읽으므로 실제 스키마 변경도 일어나지 않는다.
"""

from __future__ import annotations

import argparse
import ast
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tortoise import Tortoise  # noqa: E402
from tortoise.fields.base import Field  # noqa: E402
from tortoise.fields.relational import (  # noqa: E402
    ForeignKeyFieldInstance,
    OneToOneFieldInstance,
)

from app.core.db.databases import TORTOISE_APP_MODELS  # noqa: E402

OUTPUT = ROOT / "docs" / "assets" / "erd"
SOURCE_PATH = OUTPUT / "current-erd.mmd"
SVG_PATH = OUTPUT / "current-erd.svg"
DBML_PATH = OUTPUT / "current-erd.dbml"
MIGRATIONS = ROOT / "app" / "core" / "db" / "migrations" / "models"


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    nullable: bool
    pk: bool
    unique: bool
    target: str | None
    target_column: str | None


@dataclass(frozen=True)
class Table:
    name: str
    module: str
    columns: tuple[Column, ...]
    unique_together: tuple[tuple[str, ...], ...]


def _kind(field: object) -> str:
    return field.__class__.__name__.removesuffix("FieldInstance").removesuffix("Field").upper()


def load_tables() -> list[Table]:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    tables: list[Table] = []
    for model in Tortoise.apps["models"].values():
        meta = model._meta
        columns: list[Column] = []
        physical_fields: dict[str, Field[Any]] = {}
        for field_name, field in meta.fields_map.items():
            db_name = field.source_field or field_name
            if db_name not in meta.db_fields:
                continue
            # Tortoise는 FK마다 내부 스칼라 필드도 만든다. 관계 필드를 우선해야
            # 대상 테이블과 카디널리티가 ERD에서 사라지지 않는다.
            if db_name not in physical_fields or isinstance(field, (ForeignKeyFieldInstance, OneToOneFieldInstance)):
                physical_fields[db_name] = field
        for field_name in sorted(meta.db_fields):
            field = physical_fields[field_name]
            target = None
            target_column = None
            selected_field = field
            if isinstance(selected_field, (ForeignKeyFieldInstance, OneToOneFieldInstance)):
                target = selected_field.related_model._meta.db_table
                target_column = selected_field.to_field
            columns.append(
                Column(
                    name=field.source_field or field_name,
                    kind=_kind(field),
                    nullable=bool(field.null),
                    pk=bool(field.pk),
                    unique=bool(field.unique),
                    target=target,
                    target_column=target_column,
                )
            )
        tables.append(
            Table(
                name=meta.db_table,
                module=model.__module__.removeprefix("app.models."),
                columns=tuple(columns),
                unique_together=tuple(
                    tuple(meta.fields_map[name].source_field or name for name in group)
                    for group in (meta.unique_together or ())
                ),
            )
        )
    return sorted(tables, key=lambda table: (table.module, table.name))


def _upgrade_sql_literals(source: str) -> str:
    """``upgrade()`` 함수 안의 문자열 리터럴만 이어 붙인다.

    예전에는 파일 텍스트 전체(주석 포함)에 정규식을 걸었다 — 이 저장소는
    마이그레이션에 한국어 산문 주석을 길게 다는 관례가 있어서, "예전엔
    이 표를 만들었다"류의 주석 한 줄만으로도 있지도 않은 CREATE/DROP TABLE
    이 잡혀 거짓 경보가 났다(iljun-sys 리뷰, KEY-343 — 실제로 재현해서
    확인됨). AST로 upgrade 함수 안의 문자열 리터럴만 모으면 주석은
    원천적으로 안 걸린다 — migration의 SQL은 전부 문자열 리터럴이라 오히려
    더 정확하다.
    """
    tree = ast.parse(source)
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "upgrade":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    literals.append(inner.value)
    return "\n".join(literals)


def migration_tables() -> set[str]:
    """전체 upgrade SQL을 순서대로 적용했을 때 남는 테이블 이름을 구한다.

    RENAME TABLE은 아직 못 본다 — 지금 마이그레이션엔 하나도 없어 당장은
    무해하지만, 표 이름을 바꾸는 마이그레이션이 생기면 옛 이름이 집합에
    남아 "Only in migrations"로 잘못 운다(iljun-sys 리뷰, 지금 고칠
    필요는 없다는 판단까지 포함).
    """
    tables = {"aerich"}
    migrations = sorted(MIGRATIONS.glob("*.py"), key=lambda path: int(path.name.split("_", 1)[0]))
    for path in migrations:
        upgrade = _upgrade_sql_literals(path.read_text(encoding="utf-8"))
        tables.update(re.findall(r"CREATE TABLE(?: IF NOT EXISTS)? [`\"]?([a-zA-Z0-9_]+)", upgrade, re.I))
        tables.difference_update(re.findall(r"DROP TABLE(?: IF EXISTS)? [`\"]?([a-zA-Z0-9_]+)", upgrade, re.I))
    return tables


def mermaid(tables: list[Table]) -> str:
    lines = ["%% KEY-343 — generated from current Tortoise model metadata", "erDiagram"]
    for table in tables:
        lines.append(f"    {table.name} {{")
        for column in table.columns:
            marks = []
            if column.pk:
                marks.append("PK")
            if column.target:
                marks.append("FK")
            if column.unique:
                marks.append("UK")
            marker = f" {','.join(marks)}" if marks else ""
            comment = ' "nullable"' if column.nullable else ""
            lines.append(f"        {column.kind} {column.name}{marker}{comment}")
        lines.append("    }")
    for child in tables:
        for column in child.columns:
            if not column.target:
                continue
            child_side = "o|" if column.unique else "o{"
            parent_side = "o|" if column.nullable else "||"
            lines.append(f"    {column.target} {parent_side}--{child_side} {child.name} : {column.name}")
    return "\n".join(lines) + "\n"


def dbml_type(column: Column, tables: list[Table]) -> str:
    kind = column.kind
    if column.target and column.target_column:
        target = next(table for table in tables if table.name == column.target)
        kind = next(field.kind for field in target.columns if field.name == column.target_column)
    return {
        "BIGINT": "bigint",
        "BOOLEAN": "boolean",
        "CHAR": "varchar",
        "CHARENUM": "varchar",
        "DATE": "date",
        "DATETIME": "datetime",
        "DECIMAL": "decimal",
        "FLOAT": "float",
        "INT": "int",
        "JSON": "json",
        "SMALLINT": "smallint",
        "TEXT": "text",
        "UUID": "uuid",
    }.get(kind, "varchar")


def dbml_column(column: Column, tables: list[Table]) -> str:
    settings = []
    if column.pk:
        settings.append("pk")
    if not column.nullable:
        settings.append("not null")
    if column.unique and not column.pk:
        settings.append("unique")
    suffix = f" [{', '.join(settings)}]" if settings else ""
    return f"  {column.name} {dbml_type(column, tables)}{suffix}"


def dbml(tables: list[Table]) -> str:
    lines = [
        "// KEY-343 - generated from current Tortoise model metadata",
        "// Import this file into dbdiagram.io to edit or export the ERD.",
        "",
    ]
    for table in tables:
        lines.append(f"Table {table.name} {{")
        for column in table.columns:
            lines.append(dbml_column(column, tables))
        if table.unique_together:
            lines.append("")
            lines.append("  Indexes {")
            for unique_columns in table.unique_together:
                lines.append(f"    ({', '.join(unique_columns)}) [unique]")
            lines.append("  }")
        lines.extend(["}", ""])
    for child in tables:
        for column in child.columns:
            if not column.target or not column.target_column:
                continue
            relation = "-" if column.unique else ">"
            lines.append(f"Ref: {child.name}.{column.name} {relation} {column.target}.{column.target_column}")
    return "\n".join(lines) + "\n"


def svg(tables: list[Table]) -> str:
    box_width, gap_x, gap_y, margin = 940, 70, 50, 70
    header_height, row_height, footer_height = 58, 30, 34
    columns_count = 5
    column_heights = [150] * columns_count
    placed: list[tuple[Table, int, int, int]] = []
    for table in tables:
        height = header_height + row_height * len(table.columns) + footer_height
        slot = min(range(columns_count), key=column_heights.__getitem__)
        x = margin + slot * (box_width + gap_x)
        y = column_heights[slot]
        placed.append((table, x, y, height))
        column_heights[slot] += height + gap_y

    relations = [
        (column.target, child.name, column.name, column.nullable, column.unique)
        for child in tables
        for column in child.columns
        if column.target
    ]
    relation_y = max(column_heights) + 80
    relation_columns = 3
    relation_rows = (len(relations) + relation_columns - 1) // relation_columns
    width = margin * 2 + columns_count * box_width + (columns_count - 1) * gap_x
    height = relation_y + 120 + relation_rows * 34 + 100

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text{font-family:'Malgun Gothic','Segoe UI',sans-serif;fill:#172033}",
        ".title{font-size:42px;font-weight:700}.sub{font-size:21px;fill:#516075}",
        ".box{fill:#fff;stroke:#9aa8ba;stroke-width:2}.head{fill:#172033}",
        ".table{font-size:24px;font-weight:700;fill:#fff}.module{font-size:17px;fill:#718096}",
        ".field{font-size:18px}.muted{fill:#6b778c}.tag{font-size:15px;font-weight:700}",
        ".rel{font-size:18px}.section{font-size:30px;font-weight:700}.rule{stroke:#d5dce5;stroke-width:1}",
        "</style>",
        '<rect width="100%" height="100%" fill="#f4f7fb"/>',
        '<text x="70" y="68" class="title">AH_05_06 — Current ERD</text>',
        f'<text x="70" y="105" class="sub">develop model metadata · {len(tables)} tables · PK / FK / UK and composite unique constraints</text>',
    ]
    for table, x, y, box_height in placed:
        out.append(f'<rect x="{x}" y="{y}" width="{box_width}" height="{box_height}" rx="12" class="box"/>')
        out.append(f'<rect x="{x}" y="{y}" width="{box_width}" height="{header_height}" rx="12" class="head"/>')
        out.append(f'<text x="{x + 20}" y="{y + 37}" class="table">{html.escape(table.name)}</text>')
        out.append(
            f'<text x="{x + box_width - 20}" y="{y + 35}" text-anchor="end" class="module">{html.escape(table.module)}</text>'
        )
        for index, column in enumerate(table.columns):
            row_y = y + header_height + (index + 1) * row_height
            if index:
                out.append(
                    f'<line x1="{x + 14}" y1="{row_y - row_height + 4}" x2="{x + box_width - 14}" y2="{row_y - row_height + 4}" class="rule"/>'
                )
            marks = " ".join(
                mark
                for mark, enabled in (("PK", column.pk), ("FK", bool(column.target)), ("UK", column.unique))
                if enabled
            )
            out.append(f'<text x="{x + 20}" y="{row_y}" class="field">{html.escape(column.name)}</text>')
            out.append(
                f'<text x="{x + 430}" y="{row_y}" class="field muted">{html.escape(column.kind)}{" ?" if column.nullable else ""}</text>'
            )
            if marks:
                out.append(f'<text x="{x + box_width - 20}" y="{row_y}" text-anchor="end" class="tag">{marks}</text>')
        unique_constraint_text = "; ".join("(" + ", ".join(group) + ")" for group in table.unique_together)
        out.append(
            f'<text x="{x + 20}" y="{y + box_height - 12}" class="module">UNIQUE: {html.escape(unique_constraint_text or "—")}</text>'
        )

    out.append(f'<text x="{margin}" y="{relation_y}" class="section">FK relationships and cardinality</text>')
    out.append(
        f'<text x="{margin}" y="{relation_y + 34}" class="sub">parent ||—o{{ child: many · parent ||—o| child: unique child · nullable FK uses o| on parent side</text>'
    )
    relation_width = (width - margin * 2) // relation_columns
    for index, (parent, child, field, nullable, relation_unique) in enumerate(relations):
        column_index, row_index = divmod(index, relation_rows)
        x = margin + column_index * relation_width
        y = relation_y + 88 + row_index * 34
        left = "o|" if nullable else "||"
        right = "o|" if relation_unique else "o{"
        out.append(
            f'<text x="{x}" y="{y}" class="rel">{html.escape(parent or "")} {left}—{right} {html.escape(child)} · {html.escape(field)}</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write_or_check(path: Path, content: str, check: bool) -> bool:
    if check:
        return path.exists() and path.read_text(encoding="utf-8") == content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    tables = load_tables()
    model_names = {table.name for table in tables}
    migrated_names = migration_tables()
    if model_names != migrated_names:
        print(f"Only in models: {sorted(model_names - migrated_names)}")
        print(f"Only in migrations: {sorted(migrated_names - model_names)}")
        return 1
    results = {
        SOURCE_PATH: write_or_check(SOURCE_PATH, mermaid(tables), args.check),
        SVG_PATH: write_or_check(SVG_PATH, svg(tables), args.check),
        DBML_PATH: write_or_check(DBML_PATH, dbml(tables), args.check),
    }
    stale = [str(path.relative_to(ROOT)) for path, current in results.items() if not current]
    if stale:
        print("ERD output is stale: " + ", ".join(stale))
        return 1
    print(f"ERD {'checked' if args.check else 'generated'}: {len(tables)} tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
