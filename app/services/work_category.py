"""환자 목록의 업무 카테고리를 **이벤트에서 파생한다** — KEY-120.

계약(`docs/api/hospital.md` §3 S1-1)이 이렇게 정했다.

    업무 카테고리는 서버가 OCR·안내·승인·발송의 최신 이벤트를 읽어 파생한다.

**저장하지 않는다.** `visit` 에 칸을 하나 더 두고 싶어지지만, 그러면 같은 사실이
두 곳에 있게 되고 어긋나는 순간 화면이 거짓을 말한다 — 이 저장소가 `hospital_id`
사본을 두지 않기로 한 것과 같은 이유다. 읽을 때마다 이벤트에서 다시 센다.

## 왜 순수 함수와 적재를 갈랐나

`derive()` 는 DB 를 모른다. 조합이 열둘이고 우선순위가 다섯 단계라, **표를 채우듯
검사**해야 규칙이 지켜지는지 알 수 있다. DB 를 태우면 그 검사가 느려지고, 느려지면
조합을 다 안 채우게 된다.

`load_signals()` 는 **진료 목록 하나에 질의 넷**이다. 환자 수만큼 질의가 늘면
`limit=100` 에서 목록이 무너진다 — KEY-51 이 같은 이유로 회귀 검사를 요구한다.

## 지금 파생할 수 없는 것

계약의 `detail_status` 열둘 중 **넷은 그 기능 자체가 아직 없다.**

    GUIDE_GENERATING   안내 생성 경로가 없다        KEY-150
    GENERATION_FAILED  같음                        KEY-150
    SENT               발송기·SMS 연동이 없다        S1-14 후속
    VIEWED             환자 링크 조회가 없다         KEY-90

**없는 것을 있는 척 파생하지 않는다.** 그 자리가 생기면 `derive()` 에 가지를
더하면 되고, 그때 이 목록을 지운다.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.models.documents import MedicalDocument
from app.models.ocr import OcrJob, OcrJobStatus
from app.models.visits import GuideDocument, GuideStatus, Visit


class WorkCategory(StrEnum):
    """화면 탭. 계약 §3 의 다섯 값 그대로다."""

    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    SEND_PENDING = "SEND_PENDING"
    COMPLETED = "COMPLETED"


class DetailStatus(StrEnum):
    """줄에 뜨는 글자. 카테고리 안에서 「무엇 때문에」를 말한다."""

    NO_DOCUMENT = "NO_DOCUMENT"
    OCR_REVIEW = "OCR_REVIEW"
    GUIDE_GENERATING = "GUIDE_GENERATING"
    STAFF_REVIEW = "STAFF_REVIEW"

    GENERATION_FAILED = "GENERATION_FAILED"
    INVALID_PHONE = "INVALID_PHONE"
    SMS_OPT_OUT = "SMS_OPT_OUT"
    APPROVAL_RETURNED = "APPROVAL_RETURNED"

    APPROVAL_PENDING = "APPROVAL_PENDING"
    SCHEDULED_TO_SEND = "SCHEDULED_TO_SEND"
    SENT = "SENT"
    VIEWED = "VIEWED"


#: 여러 이벤트가 동시에 있으면 이 순서로 하나를 고른다 (계약 §3).
#:
#: **보완이 맨 앞이다.** 승인 요청이 걸려 있어도 전화번호가 틀렸으면 스탭이 먼저
#: 볼 것은 전화번호다 — 승인해 봐야 나갈 곳이 없다.
CATEGORY_PRIORITY: tuple[WorkCategory, ...] = (
    WorkCategory.NEEDS_ATTENTION,
    WorkCategory.APPROVAL_REQUESTED,
    WorkCategory.SEND_PENDING,
    WorkCategory.IN_PROGRESS,
    WorkCategory.COMPLETED,
)

#: 어느 `detail_status` 가 어느 탭에 속하는가 (계약 §3 의 표).
CATEGORY_OF: dict[DetailStatus, WorkCategory] = {
    DetailStatus.NO_DOCUMENT: WorkCategory.IN_PROGRESS,
    DetailStatus.OCR_REVIEW: WorkCategory.IN_PROGRESS,
    DetailStatus.GUIDE_GENERATING: WorkCategory.IN_PROGRESS,
    DetailStatus.STAFF_REVIEW: WorkCategory.IN_PROGRESS,
    DetailStatus.GENERATION_FAILED: WorkCategory.NEEDS_ATTENTION,
    DetailStatus.INVALID_PHONE: WorkCategory.NEEDS_ATTENTION,
    DetailStatus.SMS_OPT_OUT: WorkCategory.NEEDS_ATTENTION,
    DetailStatus.APPROVAL_RETURNED: WorkCategory.NEEDS_ATTENTION,
    DetailStatus.APPROVAL_PENDING: WorkCategory.APPROVAL_REQUESTED,
    DetailStatus.SCHEDULED_TO_SEND: WorkCategory.SEND_PENDING,
    DetailStatus.SENT: WorkCategory.COMPLETED,
    DetailStatus.VIEWED: WorkCategory.COMPLETED,
}

#: 아직 파생할 수 없는 상태. 모듈 주석 참고.
#:
#: 검사가 이 목록을 읽어 **「없는데 파생됐다」와 「생겼는데 목록에 남았다」를
#: 양쪽으로** 잡는다. 목록만 적어 두면 다음 사람이 지우는 것을 잊는다.
NOT_YET_DERIVABLE: frozenset[DetailStatus] = frozenset(
    {
        DetailStatus.GUIDE_GENERATING,
        DetailStatus.GENERATION_FAILED,
        DetailStatus.SENT,
        DetailStatus.VIEWED,
    }
)

#: 문자를 **보낼 수 있는** 번호. 환자 전화번호는 10~11 자리면 저장되므로
#: `02-` 로 시작하는 유선번호도 들어온다 — 저장은 되지만 문자는 못 간다.
#: 그 자리를 `INVALID_PHONE` 이 잡는다.
_SMS_REACHABLE = re.compile(r"^(?:\+?82)?0?1[016-9]\d{7,8}$")


def sms_reachable(phone: str | None) -> bool:
    """이 번호로 문자를 보낼 수 있는가."""
    if not phone:
        return False
    return _SMS_REACHABLE.fullmatch(re.sub(r"[^\d+]", "", phone)) is not None


@dataclass(frozen=True, slots=True)
class VisitSignals:
    """한 진료에서 읽은 이벤트. **`derive()` 가 보는 전부다.**

    DB 를 모르는 값 묶음이라 검사가 조합을 표처럼 채울 수 있다.
    """

    has_document: bool
    ocr_status: OcrJobStatus | None
    guide_status: GuideStatus | None
    phone: str | None
    sms_opted_out_at: datetime | None

    #: 안내문 상태가 **마지막으로 움직인** 시각(`guide_document.updated_at`).
    #:
    #: 승인·반려·수정이 모두 이 값을 밀어 올린다. 반려된 안내문은 그 뒤로
    #: 고칠 수 없으므로(`edit_section` 이 `APPROVAL_PENDING` 만 받는다),
    #: `APPROVAL_RETURNED` 인 진료에서는 **되돌린 시각**과 같다.
    #:
    #: `GuideEvent` 를 뒤지면 더 정확하지만 질의가 하나 는다. 목록은 한 번에
    #: 백 건을 그리는 자리라 질의 수가 곧 화면 속도다 — 이미 읽는 열로 푼다.
    guide_changed_at: datetime | None = None

    #: 환자 정보가 마지막으로 바뀐 시각(`patient.updated_at`).
    #:
    #: `INVALID_PHONE` 은 「사건」이 아니라 **상태**라 자기 시각이 없다. 번호가
    #: 틀리게 된 순간은 번호를 마지막으로 고친 때이므로 이것을 쓴다.
    patient_changed_at: datetime | None = None


#: 안내문 상태 하나에 상세 상태 하나. **`if/elif` 사슬이 아니라 표다.**
#:
#: 사슬이었을 때는 `GuideStatus` 에 멤버가 하나 늘면 어느 가지에도 안 걸려
#: 후보가 비고, `derive()` 가 `AssertionError` 를 던졌다. 그 자리는 환자 목록
#: 한 줄이라, **목록 전체가 raw 500** 이 된다 — `ContractRoute` 는 `ApiError` 와
#: `RequestValidationError` 만 다룬다.
#:
#: 표로 두면 아래 `_require_every_guide_status_is_mapped()` 가 **임포트할 때**
#: 빠진 것을 잡는다. 요청이 들어오기 전에, 검사를 한 번이라도 돌리면 죽는다.
#: (이희진 님 `#93` 리뷰 — 「`ARCHIVED` 를 임의로 하나 더해 재 봤을 때 KEY-120
#: 검사 40개가 전부 통과했습니다」)
DETAIL_OF_GUIDE_STATUS: dict[GuideStatus, DetailStatus] = {
    GuideStatus.STAFF_REVIEW: DetailStatus.STAFF_REVIEW,
    GuideStatus.APPROVAL_PENDING: DetailStatus.APPROVAL_PENDING,
    GuideStatus.SCHEDULED_TO_SEND: DetailStatus.SCHEDULED_TO_SEND,
    GuideStatus.APPROVAL_RETURNED: DetailStatus.APPROVAL_RETURNED,
}


def _require_every_guide_status_is_mapped() -> None:
    """`GuideStatus` 멤버가 늘면 **여기서 죽는다.**

    늦게 죽을수록 비싸다. 요청 시점에 죽으면 환자 목록이 통째로 500 이고,
    화면은 「불러오지 못했습니다」만 말한다 — 무엇이 빠졌는지는 로그를 파야
    안다. 임포트 시점에 죽으면 이름을 대고 죽는다.
    """
    missing = set(GuideStatus) - set(DETAIL_OF_GUIDE_STATUS)
    if missing:
        raise RuntimeError(
            "GuideStatus 에 새 멤버가 생겼는데 파생 규칙이 없다: "
            + ", ".join(sorted(m.value for m in missing))
            + " — app/services/work_category.py 의 DETAIL_OF_GUIDE_STATUS 와 "
            "docs/api/hospital.md S1-1 표를 함께 채워야 한다."
        )


_require_every_guide_status_is_mapped()


#: 시각을 모르는 후보를 줄 세울 때 쓰는 바닥값. **비교에만 쓰고 저장하지 않는다.**
_OLDEST = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Candidate:
    """참인 상태 하나와 **그것이 참이 된 시각**.

    시각을 함께 나르는 까닭은 같은 탭 안에서 무엇을 보여 줄지 고르기 위해서다.
    시각을 모르는 상태(`NO_DOCUMENT` 같은)는 `None` 이다 — 그런 상태는 자기
    탭에 혼자 있어 고를 일이 없다.
    """

    detail: DetailStatus
    at: datetime | None


def _candidates(signals: VisitSignals) -> list[Candidate]:
    """지금 이 진료에 **동시에 참인** 상태를 전부 모은다.

    하나만 고르지 않는다. 전화번호가 틀렸는데 승인 요청도 걸려 있는 진료는
    실제로 둘 다 참이고, 계약은 그중 무엇을 **보여 줄지**를 따로 정한다.
    둘을 한 함수에서 섞으면 우선순위가 규칙 안에 숨는다.
    """
    found: list[Candidate] = []

    # ── 안내문이 말하는 것 ────────────────────────────────
    if signals.guide_status is not None:
        found.append(Candidate(DETAIL_OF_GUIDE_STATUS[signals.guide_status], signals.guide_changed_at))

    # ── 환자에게 닿을 수 있는가 ───────────────────────────
    #
    # 안내문 상태와 **무관하게** 참이다. 승인까지 끝났어도 보낼 곳이 없으면
    # 스탭이 먼저 볼 것은 그쪽이다.
    if signals.sms_opted_out_at is not None:
        found.append(Candidate(DetailStatus.SMS_OPT_OUT, signals.sms_opted_out_at))
    elif not sms_reachable(signals.phone):
        found.append(Candidate(DetailStatus.INVALID_PHONE, signals.patient_changed_at))

    # ── 판독이 어디까지 왔나 ──────────────────────────────
    #
    # 안내문이 이미 있으면 판독은 지난 단계라 말하지 않는다.
    if signals.guide_status is None:
        if signals.ocr_status is not None:
            # 판독이 시작됐으면 확정 전까지 스탭이 보고 있는 중이다.
            # `FAILED` 도 여기다 — 실패는 재업로드로 풀고 그 자리가 판독 화면이다.
            found.append(Candidate(DetailStatus.OCR_REVIEW, None))
        elif signals.has_document:
            # 문서는 올라왔는데 작업이 아직 없다. 업로드가 작업을 함께 만들므로
            # 흔치 않지만 그 사이 순간이 있다.
            found.append(Candidate(DetailStatus.OCR_REVIEW, None))
        else:
            found.append(Candidate(DetailStatus.NO_DOCUMENT, None))

    return found


def _latest(candidates: list[Candidate]) -> Candidate:
    """같은 탭 안에서 **가장 최근에 참이 된 것**을 고른다.

    예전에는 `_candidates()` 가 담은 차례대로 첫 번째를 골랐다. 그러면 2주 전
    반려와 어제 수신거부가 함께 걸린 진료에서 **2주 전 반려**가 떴다 — 둘 다
    「보완」 탭이지만 스탭이 먼저 볼 것은 어제 것이다 (이희진 님 `#93` 리뷰).

    시각을 모르는 후보(`None`)는 **가장 오래된 것**으로 둔다. 지금은 그런
    후보가 자기 탭에 혼자 있어 실제로 겨루지 않지만, 나중에 겹치는 날
    「시각을 모른다」가 「최신이다」로 읽히면 안 된다.

    같은 시각이면 `_candidates()` 의 차례를 그대로 둔다 — `max` 가 첫 번째를
    남긴다. 무엇이 이길지 정해 두지 않으면 같은 데이터에 화면이 흔들린다.
    """
    return max(candidates, key=lambda c: (c.at is not None, c.at or _OLDEST))


def derive(signals: VisitSignals) -> tuple[WorkCategory, DetailStatus]:
    """이벤트에서 탭과 상세 상태를 파생한다.

    **우선순위를 `CATEGORY_PRIORITY` 한 곳에서만 읽는다.** 규칙을 두 곳에 두면
    「보완 탭에 있는데 상세는 승인 요청」 같은 줄이 생긴다.

    같은 탭에 여럿이 걸리면 `_latest()` 가 고른다 — 계약이 「가장 최근에 발생한
    미해결 상태」다.

    DB 를 타지 않는다 — 검사가 조합을 표처럼 채울 수 있게 하려는 것이다.
    """
    found = _candidates(signals)
    for category in CATEGORY_PRIORITY:
        same_tab = [c for c in found if CATEGORY_OF.get(c.detail) is category]
        if same_tab:
            return category, _latest(same_tab).detail

    # 아무것도 안 걸리는 조합은 없다 — 판독 가지가 늘 하나를 넣는다.
    # 그래도 조용히 틀린 값을 주지 않는다.
    raise ApiError(500, "WORK_CATEGORY_DATA_INVALID", "업무 상태 데이터를 처리할 수 없습니다.")


async def load_signals(visit_ids: list[int], hospital_id: int) -> dict[int, VisitSignals]:
    """진료 여럿의 이벤트를 **질의 넷으로** 읽는다.

    진료마다 한 번씩 물으면 `limit=100` 에서 질의가 백 번 넘게 난다.

    `hospital_id` 로 한 번 더 거른다. 호출부가 이미 병원 범위로 걸러 준 목록을
    받지만, **집계가 그 범위를 벗어나면 남의 의원 건수가 화면에 뜬다** —
    거르는 자리를 하나로 믿지 않는다.
    """
    if not visit_ids:
        return {}

    async with in_transaction() as connection:
        documented = set(
            await MedicalDocument.filter(visit_id__in=visit_ids, hospital_id=hospital_id)
            .using_db(connection)
            .distinct()
            .values_list("visit_id", flat=True)
        )
        ocr_rows = (
            await OcrJob.filter(visit_id__in=visit_ids, hospital_id=hospital_id)
            .using_db(connection)
            .order_by("visit_id", "-created_at")
            .values_list("visit_id", "status")
        )
        guide_rows = (
            await GuideDocument.filter(visit_id__in=visit_ids, hospital_id=hospital_id)
            .using_db(connection)
            .values_list("visit_id", "status", "updated_at")
        )
        patient_rows = (
            await Visit.filter(visit_id__in=visit_ids, hospital_id=hospital_id)
            .using_db(connection)
            .values_list(
                "visit_id",
                "patient__phone",
                "patient__sms_opted_out_at",
                "patient__updated_at",
            )
        )

    # 같은 진료에 판독이 여러 번 돌 수 있다. **가장 최근 것만** 본다 —
    # 위 `order_by` 가 최신을 먼저 주므로 처음 만난 것을 쓴다.
    try:
        latest_ocr: dict[int, OcrJobStatus] = {}
        for visit_id, status in ocr_rows:
            latest_ocr.setdefault(visit_id, OcrJobStatus(status))
        # **질의를 늘리지 않는다.** 시각은 이미 읽던 행에서 열 하나씩 더 가져온다 —
        # 목록은 한 번에 백 건을 그리는 자리라 질의 수가 곧 화면 속도다 (KEY-166).
        guides = {visit_id: (GuideStatus(status), changed_at) for visit_id, status, changed_at in guide_rows}
    except ValueError as error:
        # 원문 status를 오류나 로그에 싣지 않는다. 레거시 값이 있어도 공통 오류
        # 봉투를 유지해 내부 enum/데이터를 응답으로 노출하지 않는다.
        raise ApiError(500, "WORK_CATEGORY_DATA_INVALID", "업무 상태 데이터를 처리할 수 없습니다.") from error
    patients = {visit_id: (phone, opted_out, changed_at) for visit_id, phone, opted_out, changed_at in patient_rows}

    # **이 병원에서 읽을 수 있는 진료만 돌려준다.**
    #
    # 입력 목록을 그대로 되풀이하면 타 병원 진료도 「아무것도 안 붙은 진료」로
    # 결과에 들어가고, 호출부는 그것을 파생해 `NO_DOCUMENT` 로 화면에 올린다 —
    # 남의 의원 진료가 목록과 건수에 뜨는 자리다. `patients` 는 위에서 병원
    # 범위로 걸러 읽은 것이라 그것이 곧 「볼 수 있는 것」이다.
    signals: dict[int, VisitSignals] = {}
    for visit_id in visit_ids:
        if visit_id not in patients:
            continue
        phone, opted_out, patient_changed_at = patients[visit_id]
        guide_status, guide_changed_at = guides.get(visit_id, (None, None))
        signals[visit_id] = VisitSignals(
            has_document=visit_id in documented,
            ocr_status=latest_ocr.get(visit_id),
            guide_status=guide_status,
            phone=phone,
            sms_opted_out_at=opted_out,
            guide_changed_at=guide_changed_at,
            patient_changed_at=patient_changed_at,
        )
    return signals


def count_by_category(derived: dict[int, tuple[WorkCategory, DetailStatus]]) -> dict[str, int]:
    """탭별 건수.

    **다섯 칸을 늘 채운다.** 0 인 탭을 빼면 화면이 그 탭을 안 그리거나 `undefined`
    를 센다 — 「없다」와 「0 이다」는 다르다.
    """
    counts = {category.value: 0 for category in WorkCategory}
    for category, _ in derived.values():
        counts[category.value] += 1
    return counts
