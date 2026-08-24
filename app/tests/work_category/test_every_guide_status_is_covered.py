"""안내문 상태가 늘면 **누가 잡는가** — 이희진 님 `#93` 리뷰 ②.

> 제가 앞서 `ARCHIVED` 를 임의로 하나 더해 재 봤을 때 KEY-120 검사 40개가
> 전부 통과했습니다 — 아무도 안 잡습니다.

예전 `_candidates()` 는 `if/elif` 사슬이었다. 멤버가 하나 늘면 어느 가지에도
안 걸려 후보가 비고, `derive()` 가 `AssertionError` 를 던진다. 그 자리는 환자
목록 **한 줄**이라 목록 전체가 raw 500 이 된다 — `ContractRoute` 는 `ApiError`
와 `RequestValidationError` 만 다룬다.

지금은 표이고, 빠지면 **임포트할 때** 죽는다. 여기서는 그 가드가 실제로
무는지를 잰다 — 가드를 믿지 않고 재는 것이 이 저장소의 방식이다.
"""

import pytest

from app.models.visits import GuideStatus
from app.services.work_category import (
    DETAIL_OF_GUIDE_STATUS,
    CATEGORY_OF,
    VisitSignals,
    _require_every_guide_status_is_mapped,
    derive,
)


def test_every_guide_status_has_a_derivation() -> None:
    assert set(DETAIL_OF_GUIDE_STATUS) == set(GuideStatus)


def test_the_guard_actually_fires_when_one_is_missing() -> None:
    """**가드를 믿지 않고 잰다.**

    표만 확인하면 가드가 `pass` 로 비어 있어도 위 검사는 통과한다.
    하나를 빼 두고 불러서, 이름을 대고 죽는지 본다.
    """
    dropped = GuideStatus.APPROVAL_RETURNED
    kept = DETAIL_OF_GUIDE_STATUS.pop(dropped)
    try:
        with pytest.raises(RuntimeError, match=dropped.value):
            _require_every_guide_status_is_mapped()
    finally:
        DETAIL_OF_GUIDE_STATUS[dropped] = kept

    assert set(DETAIL_OF_GUIDE_STATUS) == set(GuideStatus), "되돌리지 못했다"


@pytest.mark.parametrize("status", list(GuideStatus))
def test_derive_never_runs_out_of_candidates(status: GuideStatus) -> None:
    """어떤 안내문 상태로도 `derive()` 가 빈손으로 끝나지 않는다.

    `#96`(KEY-51)의 `front_desk.py` 는 페이지의 진료를 돌며 `derive()` 를
    예외처리 없이 부른다. 여기서 하나라도 터지면 **목록 한 줄이 아니라
    페이지 전체**가 사라진다.
    """
    category, detail = derive(
        VisitSignals(
            has_document=True,
            ocr_status=None,
            guide_status=status,
            phone="01044524085",
            sms_opted_out_at=None,
        )
    )
    assert CATEGORY_OF[detail] is category
