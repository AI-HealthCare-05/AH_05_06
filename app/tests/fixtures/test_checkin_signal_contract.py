"""어느 답이 의료진에게 「봐 주세요」를 보내는가 — KEY-138.

세 곳이 같은 말을 해야 한다. 하나라도 갈리면 **환자가 「원장님께 전해
드릴게요」를 읽었는데 의원은 모르는 상태**가 되거나, 반대로 「가끔 놓쳐요」에
연락이 가서 다음 회차부터 솔직한 답을 못 받게 된다.

    docs/api/patient.md                     계약 3절 — 규칙과 판단표
    docs/wireframes/wireframe-patient-...   화면이 환자에게 약속하는 문장
    frontend/js/checkin-api.js              목업의 notify 값

계약이 「어느 답이 알림인지는 **서버가** 정한다」로 두었기 때문에, 화면은
`answers[key].notify` 를 읽기만 한다. 그 값이 세 곳에서 어긋나지 않는지가
여기서 재는 전부다.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "docs" / "api" / "patient.md"
WIREFRAME = ROOT / "docs" / "wireframes" / "wireframe-patient-2.3.1.html"
CHECKIN_API_JS = ROOT / "frontend" / "js" / "checkin-api.js"
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"

#: 계약 §4 의 판단. 이 값을 바꾸려면 세 곳을 함께 바꿔야 한다.
NOTIFIES = {
    "taking": False,
    "uncomfortable": True,
    "missing": False,
    "stopped_side_effect": True,
    "stopped_improved": True,
}

#: 알림을 만들지 않는 답. 「가끔 놓쳐요」가 여기 있는 것이 이 파일의 요점이다.
QUIET = sorted(k for k, v in NOTIFIES.items() if not v)


def _mock_notify_flags() -> dict[str, bool]:
    """목업의 `answers` 블록에서 답별 `notify` 를 읽는다.

    JS 를 파싱하지 않고 답 키 뒤에 처음 나오는 `notify` 를 본다 — 목업이
    답마다 한 블록이라 이것으로 충분하고, 구조가 바뀌면 아래 검사가 죽는다.
    """
    source = CHECKIN_API_JS.read_text(encoding="utf-8")
    flags: dict[str, bool] = {}
    for key in NOTIFIES:
        # `taking: null,` 처럼 블록이 없는 답은 알림도 없다.
        block = re.search(rf"\b{key}:\s*\{{(.*?)\n      \}}", source, re.S)
        if block is None:
            flags[key] = False
            continue
        found = re.search(r"notify:\s*(true|false)", block.group(1))
        flags[key] = bool(found and found.group(1) == "true")
    return flags


def _send_signal_body() -> str:
    """`sendSignal` 함수 본문만 잘라 낸다."""
    source = CHECKIN_JS.read_text(encoding="utf-8")
    body = source[source.index("function sendSignal") :]
    return body[: body.index("\n  }")]


class TestTheThreePlacesAgree:
    def test_the_contract_document_exists(self) -> None:
        assert CONTRACT.exists(), "계약 문서가 없으면 아래 검사가 전부 헛돈다"

    def test_the_contract_says_missing_is_not_a_notification(self) -> None:
        """계약 §4 의 1번이 이 파일의 근거다. 그 문장이 사라지면 아래가 잔소리가 된다."""
        text = CONTRACT.read_text(encoding="utf-8")
        assert "missing" in text and "notify: false" in text

    def test_the_mock_matches_the_contract_table(self) -> None:
        assert _mock_notify_flags() == NOTIFIES


class TestMissingStaysQuiet:
    """「가끔 놓쳐요」에 연락이 가면 다음 회차부터 「잘 먹고 있어요」를 고른다.

    그러면 우리가 보는 숫자가 거짓이 된다 — 와이어프레임 P7-3 노트.
    """

    def test_missing_is_in_the_quiet_set(self) -> None:
        assert "missing" in QUIET

    def test_the_mock_does_not_notify_for_missing(self) -> None:
        assert _mock_notify_flags()["missing"] is False

    def test_the_p7_3_caption_no_longer_promises_a_notification(self) -> None:
        """P7-3 카드 안에서 세 줄이 서로 다르게 말하던 것을 고쳤다.

        헤더는 「🔔 알림을 만들지 않는다」, 노트는 「기록만 남는다」인데
        공통 캡션만 「선택 즉시 알림이 전송된다」로 남아 있었다. **계약 §4 의
        1번이 근거로 삼는 것이 바로 그 헤더**라, 캡션을 그대로 두면 계약이
        자기 근거와 어긋난 문서를 가리키게 된다.
        """
        lines = WIREFRAME.read_text(encoding="utf-8").splitlines()
        # P7-3 카드 = 헤더 줄부터 다음 P7 헤더 전까지
        starts = [i for i, ln in enumerate(lines) if re.search(r"P7-\d\s*·", ln)]
        header = next(i for i in starts if "P7-3" in lines[i])
        end = next((i for i in starts if i > header), len(lines))
        card = "\n".join(lines[header:end])

        assert "알림을 만들지 않는다" in card, "P7-3 헤더의 「알림을 만들지 않는다」가 사라졌다"
        assert "선택 즉시 의료진 화면에 알림이 전송된다" not in card, (
            "P7-3 에 「선택 즉시 알림」 캡션이 다시 들어왔다 — 같은 카드의 헤더·노트와 어긋난다"
        )

    def test_the_other_cards_still_promise_it(self) -> None:
        """P7-2·P7-4 에서는 그 문장이 맞다. 지우면 안 된다."""
        text = WIREFRAME.read_text(encoding="utf-8")
        assert text.count("선택 즉시 의료진 화면에 알림이 전송된다") >= 2


class TestTheScreenActuallySignals:
    def test_the_api_layer_has_a_signal_call(self) -> None:
        source = CHECKIN_API_JS.read_text(encoding="utf-8")
        assert "signal:" in source
        assert "/signals" in source

    def test_the_screen_signals_on_selection_not_only_on_save(self) -> None:
        """저장할 때만 보내면 고르고 창을 닫은 환자를 놓친다.

        임의 중단은 치료가 잘 듣는 2~3개월 차에 가장 많고(P7-5 노트),
        **끊은 환자가 곧 폼을 끝까지 채울 가능성이 가장 낮은 환자**다.
        """
        source = CHECKIN_JS.read_text(encoding="utf-8")
        picked_at = source.index('picked = med.getAttribute("data-med")')
        signal_at = source.index("sendSignal(picked)")
        save_at = source.index('event.target.id === "save"')
        assert picked_at < signal_at < save_at, "신호가 선택 처리 안에 있지 않다"

    def test_a_failed_signal_does_not_block_the_patient(self) -> None:
        """알림은 의원 쪽 편의다. 못 보냈다고 환자 제출을 막으면 답을 잃는다.

        「전송 실패」는 환자에게 **자기 답이 안 갔다**는 뜻으로 읽힌다.
        """
        assert ".catch(" in _send_signal_body(), "신호 실패를 삼키지 않으면 화면이 깨진다"

    def test_the_screen_sends_every_pick_so_a_change_can_supersede(self) -> None:
        """계약 §4 의 1번 — 화면이 알림 대상만 걸러 보내면 **철회가 안 된다.**

        「불편해서 중단했어요」를 골랐다가 「잘 먹고 있어요」로 바꿔도 뒤엣것을
        안 보내면 서버에는 중단 신호가 남는다. 저장하지 않고 창을 닫으면 의원이
        없는 문제를 쫓는다 — **저장을 안 했으니 옆에 놓고 볼 답도 없다.**
        저장하지 않는 환자가 이 계약이 존재하는 이유다.
        """
        assert "notifyFor(" not in _send_signal_body(), (
            "화면이 알림 대상을 스스로 걸러 낸다 — 답을 바꿔도 앞 신호가 안 덮인다"
        )

    def test_the_quiet_answer_is_silenced_by_the_server_not_the_screen(self) -> None:
        """조용한 답도 서버까지는 간다. **기록은 남고 연락만 안 간다.**

        목업이 `notify` 를 내려주는 것이 그 판단 자리다. 화면이 아니라
        여기서 갈려야 「가끔 놓쳐요」로 바꾼 것도 앞 신호를 덮을 수 있다.
        """
        source = CHECKIN_API_JS.read_text(encoding="utf-8")
        block = source[source.index("/\\/signals$/") :]
        block = block[: block.index("\n      }")]
        assert "notify:" in block, "목업이 알림 여부를 내려주지 않는다 — 판단이 화면에 남는다"
        assert "NOT_A_SIGNAL" not in block, "목업이 조용한 답을 거부한다 — 그러면 답을 바꿔도 안 덮인다"

    def test_pressing_the_same_answer_twice_signals_once(self) -> None:
        """계약 §4 의 2번 — 연달아 같은 답을 다시 눌러도 보내지 않는다.

        `P7-2`~`P7-5` 는 펼침 화면이라 환자가 설명을 **읽어 보려고** 눌렀다
        되돌릴 수 있다. 누를 때마다 알리면 의료진 화면이 같은 환자로 찬다.

        **다만 「연달아」다.** 다른 답을 거쳐 돌아온 것은 새 신호여야 한다 —
        그러지 않으면 마지막 신호가 실제로 고른 답과 어긋난다.
        """
        body = _send_signal_body()
        assert "key === lastSignal" in body, "같은 답을 연달아 눌러도 두 번 알린다"
        assert "signalled[key]" not in body, (
            "답마다 한 번씩만 보낸다 — 중단→복용중→중단 이면 마지막 신호가 「복용중」으로 남는다"
        )
