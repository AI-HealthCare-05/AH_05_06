"""합성 CSV 한 행 → 처방 항목들 — KEY-137.

`scripts/seed.py` 가 이것을 쓴다. 규칙을 시드 안에 두지 않고 여기로 꺼낸 이유는
**검사가 닿아야 하기 때문**이다. 시드 함수 안에 두면 DB 를 띄우고 스크립트를
통째로 돌려야만 확인할 수 있고, 그러면 아무도 확인하지 않는다.

`app/tests/fixtures/staff.py` 를 시드가 가져다 쓰는 것과 같은 모양이다.
"""

from dataclasses import dataclass

from app.models.prescriptions import AS_NEEDED

#: CSV 가 한 칸에 약 여럿을 눌러 담을 때 쓰는 구분자.
SEPARATOR = "+"


class PrescriptionRowError(ValueError):
    """약과 용법의 개수가 어긋난다 — 짝지을 수 없다."""


@dataclass(frozen=True)
class ItemRow:
    name: str
    frequency: str
    duration_days: int | None


def items_from_row(names: str, frequencies: str, duration: str) -> list[ItemRow]:
    """`"비잔정 2mg + 진통제"` 와 `"1일 1회 + 필요시"` 를 두 줄로 가른다.

    **`처방일수` 는 행에 하나뿐이다.** 합성 데이터 100행 전부에서 `+` 가 없다.
    그런데 약은 둘일 수 있다. 그 하나뿐인 기간을 두 줄에 다 붙이면

        진통제 · 필요시 · 84일

    이 되고, 안내문이 **「진통제를 84일간 드세요」** 라고 말하게 된다. 복약지도
    프로그램에서 그건 틀린 문장이고 소진예정일도 하나 더 생긴다.

    그래서 `필요시` 인 줄에는 기간을 넣지 않는다. 없는 값을 지어내는 대신
    비워 둔다.
    """
    parsed_names = [n.strip() for n in names.split(SEPARATOR) if n.strip()]
    parsed_frequencies = [f.strip() for f in frequencies.split(SEPARATOR) if f.strip()]

    if not parsed_names:
        return []
    if len(parsed_names) != len(parsed_frequencies):
        raise PrescriptionRowError(
            f"약 {len(parsed_names)}개와 용법 {len(parsed_frequencies)}개가 어긋난다: {names!r} / {frequencies!r}"
        )

    days = int(duration.strip()) if duration.strip().isdigit() else None
    return [
        ItemRow(name=name, frequency=frequency, duration_days=None if frequency == AS_NEEDED else days)
        for name, frequency in zip(parsed_names, parsed_frequencies, strict=True)
    ]
