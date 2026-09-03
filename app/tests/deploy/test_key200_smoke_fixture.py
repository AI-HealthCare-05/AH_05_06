"""**KEY-176 smoke fixture 가 지켜야 하는 것** — KEY-200.

DB 를 띄우지 않고, `scripts/seed.py` 의 소스를 읽어 계약만 잰다. 실제로 서는지는
스키마가 맞는 DB 가 있어야 해서(마이그레이션 20 · KEY-196) 여기서 못 재고,
그 확인은 PR 본문에 실측으로 남긴다.

여기서 지키는 것은 **말로 하면 잊히는 세 가지**다.

    토큰을 시드가 만들지 않는다   만들면 그 순간 로그에 환자 링크 토큰이 남는다
    의학 문구를 지어내지 않는다   승인된 카탈로그에서만 가져온다
    시연 건과 겹치지 않는다      smoke 는 제출로 fixture 를 소진한다
"""

import ast
import re
from pathlib import Path

import pytest

from app.services import guide_defaults

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "scripts" / "seed.py"


def _tree() -> ast.Module:
    return ast.parse(SEED.read_text(encoding="utf-8"))


def _func_in(source: str, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} 을 못 찾았다")


def _func(name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"seed.py 에 {name} 이 없다")


def _assigned(name: str) -> ast.expr:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    raise AssertionError(f"seed.py 에 {name} 이 없다")


class TestTheSeedNeverInventsALinkToken:
    """**토큰은 밖에서 받는다.**

    `PatientGuideLink` 는 sha256 만 저장하고 원문은 발급 응답 한 번뿐이다. 시드가
    원문을 만들면 조작자에게 알려 줄 길이 출력밖에 없고, 그러면 로그에 환자 링크
    토큰이 남는다 — `AGENTS.md` 가 금지한 자리다.
    """

    def test_the_token_comes_from_the_environment(self) -> None:
        src = ast.get_source_segment(SEED.read_text(encoding="utf-8"), _func("seed_smoke_fixture")) or ""
        assert "SMOKE_LINK_TOKEN_ENV" in src, "fixture 가 토큰을 환경변수에서 안 받는다"

    def test_the_seed_does_not_generate_one(self) -> None:
        """`secrets` 로 토큰을 만드는 순간 이 검사가 막는다."""
        fn = _func("seed_smoke_fixture")
        calls = {
            node.func.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        forbidden = {"token_urlsafe", "token_hex", "token_bytes", "uuid4"}
        assert not (calls & forbidden), (
            f"시드가 토큰을 직접 만든다 ({sorted(calls & forbidden)}) — 그러면 조작자에게 "
            "알려 줄 길이 출력뿐이고, 로그에 환자 링크 토큰이 남는다"
        )

    def test_it_stores_only_the_digest(self) -> None:
        fn = _func("seed_smoke_fixture")
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
        assert "digest_link_token" in names, "원문을 그대로 저장하려는 것으로 보인다 — sha256 을 써야 한다"

    def test_it_never_prints_the_raw_token(self) -> None:
        """출력하는 자리에 토큰 변수가 섞이면 막는다.

        문자열 검사가 아니라 **AST 로** 본다 — 주석이나 설명문에 `raw_token` 이라는
        말이 나온다고 걸리면, 검사가 재는 척만 하게 된다.
        """
        fn = _func("seed_smoke_fixture")
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"):
                continue
            printed = {n.id for a in node.args for n in ast.walk(a) if isinstance(n, ast.Name)}
            assert "raw_token" not in printed, "시드가 링크 토큰 원문을 출력한다"


class TestTheFixtureUsesApprovedKnowledgeOnly:
    """**의학 문구를 지어내지 않는다** — 이희진 님 「확정 승인 지식 외 내용 추가 금지」."""

    def test_caution_and_emergency_come_from_the_catalog(self) -> None:
        fn = _func("seed_smoke_fixture")
        names = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
        assert "get_approved_content" in names, (
            "주의·응급 문구를 승인 카탈로그에서 안 가져온다 — 지어낸 문장이 환자에게 간다"
        )

    def test_it_refuses_to_fall_back_silently(self) -> None:
        """승인 문구가 없으면 **폴백으로 서지 말고 멈춰야 한다.**

        폴백은 실서비스에서는 옳지만, smoke fixture 로는 「승인된 안내」라고
        부를 수 없다. 조용히 폴백으로 서면 아무도 모른다.
        """
        src = ast.get_source_segment(SEED.read_text(encoding="utf-8"), _func("seed_smoke_fixture")) or ""
        assert "is None or" in src or "None in" in src, "승인 문구가 없을 때를 안 가른다"
        assert "폴백" in src, "폴백으로 서면 안 된다는 것을 적어 두지 않았다"

    def test_the_emergency_section_is_locked(self) -> None:
        """🚨 응급 문장은 사람이 못 고친다 (KEY-150, KEY-165)."""
        src = ast.get_source_segment(SEED.read_text(encoding="utf-8"), _func("seed_smoke_fixture")) or ""
        emergency = next((ln for ln in src.splitlines() if "GuideSectionKey.EMERGENCY" in ln), "")
        assert emergency, "응급 섹션을 안 만든다"
        assert "True" in emergency, f"응급 섹션이 잠기지 않았다 — {emergency.strip()}"


class TestTheFixtureDoesNotCollideWithTheDemo:
    """**시연 건을 쓰면 안 된다** — smoke 는 제출로 fixture 를 소진한다."""

    #: KEY-148 정본 시나리오. 시연이 이것을 쓴다.
    DEMO_SCENARIO = "SYN-EMS-01"
    DEMO_CHART = "12401"

    def test_the_smoke_scenario_is_a_different_one(self) -> None:
        scenario = ast.literal_eval(_assigned("SMOKE_SCENARIO_ID"))
        chart = ast.literal_eval(_assigned("SMOKE_CHART_NO"))

        assert scenario != self.DEMO_SCENARIO, (
            f"smoke 가 시연 시나리오({self.DEMO_SCENARIO})를 쓴다 — 제출 한 번에 시연이 오염된다"
        )
        assert chart != self.DEMO_CHART, f"smoke 가 시연 차트({self.DEMO_CHART})를 쓴다"

    def test_the_chosen_row_is_really_in_the_csv_and_fits(self) -> None:
        """고른 행이 **실제로 그런 행인지** CSV 로 대조한다.

        상수만 보고 통과하면, 나중에 누가 시나리오를 바꿔도 검사가 모른다.
        """
        import csv

        scenario = ast.literal_eval(_assigned("SMOKE_SCENARIO_ID"))
        chart = ast.literal_eval(_assigned("SMOKE_CHART_NO"))

        with (ROOT / "docs" / "data" / "synthetic-patients.csv").open(encoding="utf-8-sig") as f:
            row = next((r for r in csv.DictReader(f) if r["시나리오ID"] == scenario), None)

        assert row is not None, f"CSV 에 {scenario} 가 없다"
        assert row["차트번호"].strip() == chart, f"차트번호가 어긋난다 — CSV {row['차트번호']} vs 상수 {chart}"
        assert row["문자수신동의"].strip() == "Y", "문자 미동의 환자는 OTP 가 409 SMS_OPT_OUT 이다"
        assert row["진료일"].strip(), "진료일이 없으면 진료가 안 만들어진다"
        assert row["처방세트"].strip(), "처방세트가 없으면 승인 문구를 못 고른다"

    def test_the_chosen_set_has_approved_wording(self) -> None:
        """고른 처방세트에 승인된 주의·응급 문구가 **둘 다** 있어야 한다."""
        import csv

        from app.models.catalog import CautionSectionKey
        from app.tests.fixtures.catalog import DRUG_CAUTION_CONTENTS

        scenario = ast.literal_eval(_assigned("SMOKE_SCENARIO_ID"))
        with (ROOT / "docs" / "data" / "synthetic-patients.csv").open(encoding="utf-8-sig") as f:
            row = next(r for r in csv.DictReader(f) if r["시나리오ID"] == scenario)
        set_name = row["처방세트"].strip()

        have = {c.section_key for c in DRUG_CAUTION_CONTENTS if c.prescription_set_name == set_name}
        for key in (CautionSectionKey.CAUTION, CautionSectionKey.EMERGENCY):
            assert key in have, f"{set_name!r} 에 승인된 {key.value} 문구가 없다 — 폴백으로 선다"


class TestItCanBeSeededAgain:
    """**일회용이라 다시 심을 수 있어야 한다.**

    `CheckIn` 은 안내문당 하나뿐이라(OneToOne) smoke 가 제출하면 두 번째는 409 다.
    """

    def test_it_clears_the_previous_submission(self) -> None:
        fn = _func("seed_smoke_fixture")
        deletes = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "delete"
        ]
        assert deletes, "이전 제출을 안 지운다 — 두 번째 smoke 가 409 로 죽는다"

        src = ast.get_source_segment(SEED.read_text(encoding="utf-8"), fn) or ""
        assert "CheckIn.filter(guide_document_id=" in src, "지우는 대상이 이 fixture 의 안내문 하나로 좁혀져 있지 않다"

    def test_it_pushes_the_expiry_back(self) -> None:
        """링크 TTL 이 72 시간이라, 안 밀면 이틀 뒤 QA 에서 410 LINK_EXPIRED 다."""
        src = ast.get_source_segment(SEED.read_text(encoding="utf-8"), _func("seed_smoke_fixture")) or ""
        assert src.count("LINK_TTL") >= 2, "재시드할 때 만료를 다시 밀지 않는다"

    def test_skipping_is_quiet_when_no_token_is_given(self) -> None:
        """토큰을 안 준 사람에게 **없던 요구를 만들지 않는다.**"""
        src = ast.get_source_segment(SEED.read_text(encoding="utf-8"), _func("seed_smoke_fixture")) or ""
        head = src.split("h1 = hospitals", 1)[0]
        assert "return" in head, "토큰이 없을 때 조용히 건너뛰지 않는다"


class TestTheFixtureLooksLikeARealApproval:
    """**손으로 흉내낸 승인이 진짜 승인과 어긋나면 안 된다** — 이희진 님 `#158`.

    처음에는 `status`·`approved_by`·`approved_at` 셋만 채웠다. 그런데 실제
    `GuideService.approve()` 는 한 트랜잭션에서 **다섯**을 쓰고 감사로그까지
    남긴다. 그래서 이 fixture 가 **실제 승인 흐름으로는 나올 수 없는 상태**를
    만들고 있었다 — 승인됐는데 예약시각이 없고, 누가 승인했는지 기록도 없다.

    `docs/api/hospital.md` 가 「승인은 `scheduled_at` 을 채우는 데까지다」라고
    적어 두었고 `test_guide_approval.py` 가 그것을 이미 단언한다. 시드만 그
    계약 밖에 있었다.
    """

    @staticmethod
    def _seed_source() -> str:
        src = ast.get_source_segment(
            (ROOT / "scripts" / "seed.py").read_text(encoding="utf-8"), _func("seed_smoke_fixture")
        )
        assert src, "seed_smoke_fixture 를 못 찾았다"
        return src

    def test_it_fills_everything_the_real_approval_fills(self) -> None:
        """**진짜 승인이 쓰는 필드를 코드에서 읽어** 하나씩 대조한다.

        목록을 여기 적어 두면 `approve()` 가 필드를 하나 더 쓰기 시작해도
        검사가 모른다. `update_fields=[...]` 를 직접 읽는다.
        """
        guides = (ROOT / "app" / "services" / "guides.py").read_text(encoding="utf-8")
        approve = ast.get_source_segment(guides, _func_in(guides, "approve")) or ""

        line = next((ln for ln in approve.splitlines() if "update_fields=[" in ln), "")
        assert line, "approve() 의 update_fields 를 못 찾았다"
        fields = re.findall(r'"([a-z_]+)"', line)
        assert {"status", "approved_by", "approved_at", "scheduled_at", "returned_reason"} <= set(fields), (
            f"approve() 가 쓰는 필드가 달라졌다 — {fields}"
        )

        fixture = self._seed_source()
        for field in fields:
            if field == "updated_at":
                continue  # auto_now — 손으로 쓰지 않는다
            assert f'"{field}"' in fixture, (
                f"실제 승인은 {field} 를 채우는데 fixture 는 안 채운다 — 실제 흐름으로는 나올 수 없는 상태가 된다"
            )

    def test_it_uses_the_same_schedule_rule(self) -> None:
        """예약시각을 **따로 계산하지 않는다.**

        시드가 제 나름대로 18시를 구하면 두 곳이 어긋나고, 어긋난 쪽이 조용히
        환자에게 나간다. `_send_at` 이 시간대 때문에 한 번 틀렸던 자리다.
        """
        fixture = self._seed_source()
        assert "GuideService.send_at" in fixture, "예약시각을 서비스와 같은 규칙으로 안 구한다"

    def test_it_leaves_an_audit_row(self) -> None:
        fixture = self._seed_source()
        assert "GuideEventType.APPROVED" in fixture, "누가 승인했는지 감사로그가 안 남는다"
        assert "exists()" in fixture, "다시 시드하면 감사로그가 쌓인다 — 하나만 두어야 한다"

    def test_it_refuses_without_an_approver(self) -> None:
        """**승인자 없이 「승인」을 만들지 않는다** — `#158` ②.

        예전에는 `doctor_id` 가 `None` 이어도 `issued_by=0` 으로 조용히 지나갔다.
        """
        fixture = self._seed_source()
        head = fixture.split("approved_moment", 1)[0]
        assert "doctor_id is None" in head, "담당의가 없을 때 멈추는 가드가 없다"
        assert "return" in head, "가드가 멈추지 않는다"

    def test_it_never_invents_an_issuer(self) -> None:
        """`issued_by=doctor_id or 0` 같은 자리를 남기지 않는다."""
        fixture = self._seed_source()
        assert "or 0" not in fixture, "승인자·발급자를 0 으로 메우는 자리가 있다 — 실제로 없는 사람이 발급한 것이 된다"


class TestTheFixtureInventsNoMedicalText:
    """**시드가 새 의학 문장을 지어내지 않는다** — 이희진 님 `#158` ⑤.

    카탈로그 밖 세 섹션(medication · life · messages)의 본문은 `guides.generate`
    가 쓰는 말이어야 한다. 주석은 「그대로 옮긴 것」이라 적혀 있었는데 실제로는
    `확정된 항목: {field_label}` 줄이 빠져 있었다 — **지어낸 말은 없었지만 같지도
    않았다.**

    주석은 다시 어긋날 수 있으므로, 여기서는 말이 아니라 **문장 단위로** 잰다.
    시드가 쓰는 모든 줄이 `guides.py` 의 그 자리에 실제로 있는지 본다.
    """

    #: (시드 상수 이름, `guides.py` 의 섹션 키)
    BODIES = (
        ("_SMOKE_MEDICATION_BODY", "MEDICATION"),
        ("_SMOKE_LIFE_BODY", "LIFE"),
        ("_SMOKE_MESSAGES_BODY", "MESSAGES"),
    )

    @staticmethod
    def _generated_body(section: str) -> str:
        """`guides.generate` 가 그 섹션에 넣는 글.

        **두 곳을 함께 본다.** 문장이 `guides.py` 에 박혀 있던 때는 그 파일만
        긁으면 됐는데, 지금은 기본 문구가 `guide_defaults` 에 있고 `guides.py`
        는 그것을 부른다 — 설정 화면이 「원본」으로 보이는 글과 실제로 나가는
        글을 하나로 묶느라 그렇게 됐다. 한쪽만 보면 시드가 지어낸 문장을
        「진짜」로 착각한다.
        """
        guides = (ROOT / "app" / "services" / "guides.py").read_text(encoding="utf-8")
        lines = guides.splitlines()
        at = next(
            (i for i, ln in enumerate(lines) if f"GuideSectionKey.{section}" in ln),
            None,
        )
        assert at is not None, f"guides.py 에 {section} 섹션이 없다"
        block = "\n".join(lines[at : at + 12])
        assert "generated_body=" in block, f"{section} 의 generated_body 를 못 찾았다"

        # 그 자리가 부르는 기본 문구까지 합쳐야 「지어낸 문장」을 가릴 수 있다.
        # **그 갈래 것만 합친다.** 넷을 다 넣으면 생활지도 문장이 복약지도에서도
        # 통과해 검사가 헐거워진다 — 갈래를 섞어 적은 시드를 못 잡는다.
        key = next((k for k in guide_defaults.BY_SECTION if k.value.upper() == section), None)
        default = guide_defaults.BY_SECTION[key] if key else ""
        return block + "\n" + default

    @pytest.mark.parametrize(("const", "section"), BODIES)
    def test_every_line_it_writes_exists_in_the_real_one(self, const: str, section: str) -> None:
        seed = (ROOT / "scripts" / "seed.py").read_text(encoding="utf-8")
        line = next((ln for ln in seed.splitlines() if ln.startswith(f"{const} = ")), "")
        assert line, f"seed.py 에 {const} 가 없다"

        value = ast.literal_eval(line.split("=", 1)[1].strip())
        real = self._generated_body(section)

        for sentence in [s for s in value.split("\n") if s.strip()]:
            assert sentence in real, (
                f"{const} 의 「{sentence}」 가 guides.py 의 {section} 본문에 없다 — 시드가 새 문장을 지어냈다"
            )

    def test_the_comment_says_what_was_left_out(self) -> None:
        """**무엇을 왜 뺐는지 적혀 있어야 한다.**

        앞의 두 검사가 「지어낸 문장이 없다」를 이미 재므로, 여기서는 다음 사람이
        대조를 건너뛰지 않도록 **빠진 줄이 무엇인지** 적혀 있는지만 본다.

        「그대로 옮겼다고 말하지 않는가」도 재려 했는데 접었다. 지금 주석은 과거
        오류를 설명하느라 그 표현을 **인용**하는데, 글자만 훑는 검사는 주장과
        회고를 못 가른다 — 제 설명에 제가 걸려 빨간불이 났다. 실질은 위 두
        검사가 잡으니 여기서 산문을 더 재지 않는다.
        """
        seed = (ROOT / "scripts" / "seed.py").read_text(encoding="utf-8")
        head = seed.split("_SMOKE_MEDICATION_BODY = ", 1)[0]
        note = head[head.rindex("SMOKE_CHART_NO") :]

        assert "확정된 항목" in note, "무엇을 왜 뺐는지 적혀 있지 않다"
        assert "field_label" in note, "그 값이 어디서 오는지 적혀 있지 않다"

    def test_it_does_not_write_an_empty_confirmed_line(self) -> None:
        """빈 「확정된 항목: 」이 환자 화면에 나가면 안 된다."""
        seed = (ROOT / "scripts" / "seed.py").read_text(encoding="utf-8")
        line = next((ln for ln in seed.splitlines() if ln.startswith("_SMOKE_MEDICATION_BODY = ")), "")
        value = ast.literal_eval(line.split("=", 1)[1].strip())

        assert "확정된 항목" not in value, (
            "확정된 OCR 항목이 없는 fixture 인데 그 줄을 넣었다 — 빈 값이 환자에게 나간다"
        )
