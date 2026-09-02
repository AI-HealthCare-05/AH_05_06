"""판독이 읽어야 하는 스물한 항목 — KEY-234.

증상 · 초음파 · 혈액 세 묶음이다. 나온 곳이 다르면 못 읽었을 때 어디를 다시
봐야 하는지도 다르다 — 증상은 사람이 물어 적고, 초음파는 본 것이고, 혈액은
뽑아 잰 것이다.

**패턴이 있는 것과 실제로 읽는 것은 다르다.** 표에 이름만 올려 두고 정규식이
어긋나 있으면 화면에는 스물한 줄이 물음표로 서고, 사람이 전부 손으로 적는다.
그래서 여기서는 한 줄씩 **실제로 읽혀 나오는지**를 잰다.
"""

from ai_worker.tasks.field_extractor import _LAB_PATTERNS

# 병원 문서에 실제로 적히는 모양. 콜론과 단위 표기를 섞어 둔다.
SAMPLE = """검사일: 2026-09-01
생리통: 7점
생리 과다: 있다
불규칙 월경: 없다
선근증: 5.4 cm
근종 크기: 2.1 cm
근종 개수: 3개
내막 두께: 0.9 cm
난소 부속기 혹 (왼쪽): 있다 3.2 cm
난소 부속기 혹 (오른쪽): 없다
Hb: 10.2 g/dL
AST: 24 U/L
ALT: 34 U/L
LH/FSH 비율: 2.4
DHEA-S: 210 ug/dL
Testosterone: 45 ng/dL
Prolactin: 18.2 ng/mL
TSH: 2.1 uIU/mL
T3: 3.2 pg/mL
T4: 1.1 ng/dL
E2: 42 pg/mL
Progesterone: 1.2 ng/mL
"""

WANTED = {
    # 증상
    "PAIN_SCORE": "7",
    "HEAVY_BLEEDING": "있다",
    "IRREGULAR_CYCLE": "없다",
    # 초음파
    "ADENOMYOSIS_SIZE": "5.4 cm",
    "MYOMA_SIZE": "2.1 cm",
    "MYOMA_COUNT": "3",
    "ENDOMETRIAL_THICKNESS": "0.9 cm",
    "ADNEXAL_CYST_LEFT": "있다 3.2 cm",
    "ADNEXAL_CYST_RIGHT": "없다",
    # 혈액
    "HEMOGLOBIN": "10.2 g/dL",
    "AST": "24 U/L",
    "ALT": "34 U/L",
    "LH_FSH_RATIO": "2.4",
    "DHEA_S": "210 ug/dL",
    "TESTOSTERONE": "45 ng/dL",
    "PROLACTIN": "18.2 ng/mL",
    "TSH": "2.1 uIU/mL",
    "T3": "3.2 pg/mL",
    "T4": "1.1 ng/dL",
    "E2": "42 pg/mL",
    "PROGESTERONE": "1.2 ng/mL",
}


def test_every_wanted_field_is_actually_read() -> None:
    """스물한 항목이 **한 줄도 빠짐없이** 읽힌다."""
    missing = []
    wrong = []

    for name, want in WANTED.items():
        pattern = _LAB_PATTERNS.get(name)
        if pattern is None:
            missing.append(f"{name} — 패턴이 없다")
            continue
        found = pattern.search(SAMPLE)
        if found is None:
            missing.append(f"{name} — 패턴은 있는데 못 읽는다")
            continue
        got = found.group(1).strip()
        if got != want:
            wrong.append(f"{name} — {got!r} (원하는 것 {want!r})")

    assert not missing, "못 읽는 항목:\n  " + "\n  ".join(missing)
    assert not wrong, "다르게 읽는 항목:\n  " + "\n  ".join(wrong)


def test_ast_and_alt_are_separate() -> None:
    """**AST 와 ALT 를 따로 읽는다.**

    예전 `AST_ALT` 는 「24 / 34 U/L」처럼 한 칸에 둘을 담았다. 한쪽만 틀렸을 때
    고칠 수가 없고, 안내문이 간수치를 하나의 값으로 다루게 된다.
    """
    assert "AST" in _LAB_PATTERNS
    assert "ALT" in _LAB_PATTERNS

    # `AST / ALT: 24 / 34 U/L` 같은 옛 표기를 AST 하나로 잘못 읽지 않는다
    old_style = "AST / ALT : 24 / 34 U/L"
    assert _LAB_PATTERNS["AST"].search(old_style) is None, "옛 합친 표기를 AST 로 읽는다"
    assert _LAB_PATTERNS["AST_ALT"].search(old_style) is not None, "옛 표기를 아무도 못 읽는다"


def test_no_value_is_invented_when_the_line_is_absent() -> None:
    """**없는 줄에서 값을 지어내지 않는다.**

    「없으면 못 읽는다」가 「있는데 엉뚱한 값을 읽는다」보다 낫다 — 뒤엣것은
    스탭이 눈으로 못 잡는다.
    """
    blank = "검사일: 2026-09-01\n특이사항 없음\n"
    for name in WANTED:
        pattern = _LAB_PATTERNS.get(name)
        if pattern is None:
            continue
        assert pattern.search(blank) is None, f"{name} 이 없는 줄에서 값을 만들어 냈다"
