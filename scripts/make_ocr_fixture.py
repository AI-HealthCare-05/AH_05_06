#!/usr/bin/env python3
"""합성 EMR 판독 샘플을 만든다 — KEY-68.

**만든 것을 커밋하지 않는다.** KEY-68 범위 밖 첫 줄이 「합성 이미지의 Git 저장소
커밋」이다. 그래서 저장소에는 **만드는 법**만 둔다 — 이 스크립트와 기대값
YAML 이다. 그림은 부를 때마다 새로 나온다.

값은 어디서 오는가
    환자·처방      docs/data/synthetic-patients.csv   ← 정본
    ICD·표 위치    docs/data/ocr-fixtures/*.toml       ← EMR 에만 있는 것

두 곳을 합쳐 SVG 한 장과 기대값 JSON 한 장을 낸다. SVG 로 내는 이유는 글자가
그대로 남아 **사람이 열어 확인할 수 있고**, 저장소가 이미 가진 것 말고 아무
의존성도 안 늘리기 때문이다. 판독기에 넣을 래스터/PDF 로 바꾸는 절차는
`docs/ocr-fixtures.md` 에 적었다.

사용법
    uv run python scripts/make_ocr_fixture.py                    # 전부
    uv run python scripts/make_ocr_fixture.py --spec SYN-EMS-01.emr.v1.toml
    uv run python scripts/make_ocr_fixture.py --out /tmp/내폴더
"""

import argparse
import csv
import hashlib
import json
import sys
import tomllib
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / "docs" / "data" / "ocr-fixtures"
PATIENTS_CSV = ROOT / "docs" / "data" / "synthetic-patients.csv"
#: 기본 출력 자리. `.gitignore` 가 막고 있다 — 실수로 커밋되지 않게.
DEFAULT_OUT = ROOT / "build" / "ocr-fixtures"


def load_patient(scenario: str) -> dict[str, str]:
    """정본 CSV 에서 그 시나리오 행을 읽는다."""
    with PATIENTS_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("시나리오ID") == scenario:
                return row
    raise SystemExit(f"{PATIENTS_CSV.name} 에 {scenario} 행이 없다 — 시나리오 ID 를 확인해라")


def resolve(spec: dict, patient: dict[str, str]) -> dict[str, dict[str, object]]:
    """YAML 이 가리키는 열을 실제 값으로 바꾼다.

    값을 YAML 에 안 박는 이유가 여기 있다 — CSV 가 바뀌면 여기서 따라온다.
    """
    out: dict[str, dict[str, object]] = {}
    for name, rule in spec["fields"].items():
        raw = patient.get(rule["csv_column"], "")
        if "csv_part" in rule:
            # 총투원문 `1/1/84` 처럼 한 열에 여럿이 든 경우
            parts = raw.split("/")
            index = int(rule["csv_part"])
            raw = parts[index] if index < len(parts) else ""
        value = raw.strip()
        if not value and rule.get("required"):
            raise SystemExit(f"{name} 이 비었다 — CSV 의 `{rule['csv_column']}` 열을 확인해라")
        entry: dict[str, object] = {"value": value, "required": bool(rule.get("required"))}
        if "icd_code" in rule:
            entry["icd_code"] = rule["icd_code"]
        out[name] = entry
    return out


def cell(x: int, y: int, text: str, *, bold: bool = False, size: int = 13) -> str:
    weight = ' font-weight="600"' if bold else ""
    return (
        f'<text x="{x}" y="{y}" font-family="AppleSDGothicNeo, AppleGothic, '
        f'NanumGothic, sans-serif" font-size="{size}"{weight}>{escape(text)}</text>'
    )


def render_svg(spec: dict, patient: dict[str, str], fields: dict[str, dict[str, object]]) -> str:
    """KEY-163 §2 가 적은 표 구조를 따른다.

    실제 병원 EMR 화면 레이아웃은 아직 미확정이다(KEY-163 §8 「대상 병원 EMR
    시스템 이름·버전 — 미기입」). 그래서 **화면을 흉내 내지 않고** 문서가 못 박은
    표 구조만 그린다. 확정되면 이 함수만 갈아 끼우고 기대값은 그대로 쓴다.
    """
    p = patient
    rows: list[str] = ['<rect width="900" height="520" fill="#ffffff"/>']
    rows.append(cell(40, 46, "진료기록 (합성 · 실제 환자 아님)", bold=True, size=17))
    rows.append(cell(40, 74, f"차트번호 {p['차트번호']}    이름 {p['이름']}    생년월일 {p['생년월일']}"))
    rows.append(cell(40, 98, f"진료일 {p['진료일']}    담당의 {p['담당의']}"))

    rows.append(cell(40, 146, "[진단]", bold=True))
    rows.append('<line x1="40" y1="158" x2="860" y2="158" stroke="#333"/>')
    rows.append(cell(40, 180, "ICD코드", bold=True))
    rows.append(cell(140, 180, "상병명", bold=True))
    rows.append(cell(420, 180, "주/부상병", bold=True))
    diagnosis = fields["DIAGNOSIS"]
    rows.append(cell(40, 208, str(diagnosis["icd_code"])))
    rows.append(cell(140, 208, str(diagnosis["value"])))
    rows.append(cell(420, 208, "주상병"))

    rows.append(cell(40, 268, "[처방]", bold=True))
    rows.append('<line x1="40" y1="280" x2="860" y2="280" stroke="#333"/>')
    for x, head in ((40, "약품명"), (300, "1회량"), (400, "일일횟수"), (520, "처방일수")):
        rows.append(cell(x, 302, head, bold=True))
    rows.append(cell(40, 330, str(fields["MEDICATION_NAME"]["value"])))
    rows.append(cell(300, 330, str(fields["DOSAGE"]["value"])))
    rows.append(cell(400, 330, str(fields["FREQUENCY"]["value"])))
    rows.append(cell(520, 330, str(fields["DURATION_DAYS"]["value"])))

    rows.append(cell(40, 470, f"합성 자료 · {spec['scenario']} · {spec['version']} · 실제 환자정보 없음", size=11))
    body = "\n  ".join(rows)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="520" viewBox="0 0 900 520">\n  {body}\n</svg>\n'
    )


def build(spec_path: Path, out_dir: Path) -> None:
    spec = tomllib.loads(spec_path.read_text(encoding="utf-8"))
    patient = load_patient(spec["patient"]["csv_scenario"])
    fields = resolve(spec, patient)

    stem = f"{spec['scenario']}.{spec['document_type'].lower()}.{spec['version']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    svg = render_svg(spec, patient, fields)
    (out_dir / f"{stem}.svg").write_text(svg, encoding="utf-8")

    expected = {
        "scenario": spec["scenario"],
        "document_type": spec["document_type"],
        "version": spec["version"],
        "patient": {k: patient[v] for k, v in spec["patient"]["columns"].items()},
        "fields": fields,
        "success_requires": spec["success_requires"],
        "source": {
            "values": "docs/data/synthetic-patients.csv",
            "layout": f"docs/data/ocr-fixtures/{spec_path.name}",
        },
    }
    text = json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (out_dir / f"{stem}.expected.json").write_text(text, encoding="utf-8")

    digest = hashlib.sha256(svg.encode("utf-8")).hexdigest()
    print(f"  {stem}.svg            {len(svg):>6}자  sha256 {digest[:16]}…")
    print(f"  {stem}.expected.json  {len(text):>6}자")


def main() -> int:
    ap = argparse.ArgumentParser(description="합성 EMR 판독 샘플 생성 (KEY-68)")
    ap.add_argument("--spec", help="파일명 하나만 지정. 없으면 전부")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"출력 폴더 (기본 {DEFAULT_OUT})")
    args = ap.parse_args()

    specs = sorted(SPEC_DIR.glob(args.spec or "*.toml"))
    if not specs:
        raise SystemExit(f"{SPEC_DIR} 에서 기대값 파일을 못 찾았다")

    print(f"기대값 {len(specs)}건 · 값 정본 {PATIENTS_CSV.name}\n출력 {args.out}\n")
    for path in specs:
        build(path, args.out)
    print("\n이 산출물은 커밋하지 않는다 (KEY-68 범위 밖). `.gitignore` 가 막고 있다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
