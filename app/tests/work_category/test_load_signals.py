"""이벤트를 **질의 몇 번으로** 읽는가, 그리고 남의 의원 것이 섞이지 않는가 — KEY-120.

파생 규칙은 `test_derive_rules.py` 가 DB 없이 잰다. 여기서 재는 것은 **읽어 오는
쪽**이다. 둘이 다른 종류의 실패를 하기 때문이다.

    규칙   조합을 잘못 고른다        → 화면에 틀린 탭이 뜬다
    적재   질의가 환자 수만큼 늘거나  → 목록이 느려지거나
           범위를 벗어난다            → 남의 의원 건수가 화면에 뜬다

여기 값은 전부 합성이다.
"""

from datetime import UTC, datetime

from tortoise import connections
from tortoise.contrib.test import TestCase

from app.models.documents import MedicalDocument
from app.models.ocr import OcrJob, OcrJobStatus
from app.models.patients import Patient
from app.models.visits import GuideDocument, GuideStatus, Visit
from app.services.work_category import DetailStatus, WorkCategory, derive, load_signals

HOSPITAL_ID = 1
OTHER_HOSPITAL_ID = 2


class CountingQueries:
    """이 블록 안에서 DB 에 나간 질의를 센다.

    `limit=100` 에서 질의가 백 번 넘게 나는 것을 막으려면 **수를 재야** 한다.
    「빠른가」가 아니라 「진료 수에 비례해 느는가」가 문제다.

    **연결 별칭을 박지 않는다.** 운영은 `default`, 검사는 `models` 라
    하나를 박으면 다른 쪽에서 조용히 아무것도 안 센다.

    **인스턴스가 아니라 클래스에 건다.** 예전에는 `connections.all()` 이 준
    객체마다 메서드를 갈아 끼웠는데, `in_transaction()` 은 그 목록에 없는
    **새 `TransactionWrapper`** 를 만든다. `load_signals()` 는 질의 넷을 전부
    트랜잭션 안에서 하므로 **한 건도 세지 못했다** — N+1 검사가 0 과 0 을
    견주며 늘 통과하고 있었다 (KEY-166 작업 중 발견).

    클래스에 걸면 그 뒤에 생기는 연결도 함께 세인다.
    """

    def __init__(self) -> None:
        self.count = 0
        self._restore: list[tuple[type, str, object]] = []

    def __enter__(self) -> "CountingQueries":
        targets: set[tuple[type, str]] = set()
        for connection in connections.all():
            for name in ("execute_query", "execute_query_dict"):
                # 실제로 그 메서드를 **가진** 클래스를 찾는다. 하위 클래스에
                # 걸면 상위 구현을 부르는 경로가 새어 나간다.
                owner = next(k for k in type(connection).__mro__ if name in k.__dict__)
                targets.add((owner, name))
        for owner, name in sorted(targets, key=lambda t: (t[0].__name__, t[1])):
            original = owner.__dict__[name]
            self._restore.append((owner, name, original))
            setattr(owner, name, self._counted(original))
        assert self._restore, "셀 연결이 하나도 없다 — 이 도구가 헛돈다"
        return self

    def _counted(self, original: object):  # type: ignore[no-untyped-def]
        async def wrapper(conn: object, *args: object, **kwargs: object) -> object:
            self.count += 1
            return await original(conn, *args, **kwargs)  # type: ignore[operator]

        return wrapper

    def __exit__(self, *exc: object) -> None:
        for owner, name, original in self._restore:
            setattr(owner, name, original)
        self._restore.clear()


async def make_visit(
    chart: str,
    *,
    hospital_id: int = HOSPITAL_ID,
    phone: str = "01039457702",
    opted_out: datetime | None = None,
) -> Visit:
    patient = await Patient.create(
        hospital_id=hospital_id,
        hospital_patient_no=chart,
        name="합성환자",
        birth_date="1994-07-22",
        phone=phone,
        sms_consent=opted_out is None,
        sms_opted_out_at=opted_out,
    )
    return await Visit.create(
        hospital_id=hospital_id,
        patient=patient,
        visited_at=datetime(2026, 8, 19, 1, 30, tzinfo=UTC),
    )


async def attach_document(visit: Visit) -> None:
    await MedicalDocument.create(
        hospital_id=visit.hospital_id,
        visit=visit,
        file_path=f"/synthetic/{visit.visit_id}.jpg",
        file_size=1024,
        mime_type="image/jpeg",
        uploaded_by=1,
    )


async def attach_ocr(visit: Visit, status: OcrJobStatus, suffix: str = "a") -> None:
    await OcrJob.create(
        ocr_job_id=f"syn-wc-{visit.visit_id}-{suffix}",
        hospital_id=visit.hospital_id,
        visit=visit,
        status=status,
        requested_by=1,
    )


async def attach_guide(visit: Visit, status: GuideStatus) -> None:
    await GuideDocument.create(hospital_id=visit.hospital_id, visit=visit, status=status)


class TestItReadsWhatIsThere(TestCase):
    async def test_no_visits_asks_nothing(self) -> None:
        with CountingQueries() as counter:
            assert await load_signals([], HOSPITAL_ID) == {}
        assert counter.count == 0, "빈 목록인데 DB 를 물었다"

    async def test_reads_every_signal(self) -> None:
        visit = await make_visit("SYN-WC-01", opted_out=datetime(2026, 8, 20, tzinfo=UTC))
        await attach_document(visit)
        await attach_ocr(visit, OcrJobStatus.COMPLETED)
        await attach_guide(visit, GuideStatus.APPROVAL_PENDING)

        signals = (await load_signals([visit.visit_id], HOSPITAL_ID))[visit.visit_id]

        assert signals.has_document is True
        assert signals.ocr_status is OcrJobStatus.COMPLETED
        assert signals.guide_status is GuideStatus.APPROVAL_PENDING
        assert signals.phone == "01039457702"
        assert signals.sms_opted_out_at is not None

    async def test_a_bare_visit_reads_as_nothing_attached(self) -> None:
        visit = await make_visit("SYN-WC-02")

        signals = (await load_signals([visit.visit_id], HOSPITAL_ID))[visit.visit_id]

        assert signals.has_document is False
        assert signals.ocr_status is None
        assert signals.guide_status is None
        assert derive(signals) == (WorkCategory.IN_PROGRESS, DetailStatus.NO_DOCUMENT)

    async def test_only_the_latest_ocr_job_counts(self) -> None:
        """같은 진료에 판독이 여러 번 돌 수 있다. 지금 상태는 **마지막 것**이다."""
        visit = await make_visit("SYN-WC-03")
        await attach_document(visit)
        await attach_ocr(visit, OcrJobStatus.FAILED, suffix="old")
        await attach_ocr(visit, OcrJobStatus.COMPLETED, suffix="new")

        signals = (await load_signals([visit.visit_id], HOSPITAL_ID))[visit.visit_id]

        assert signals.ocr_status is OcrJobStatus.COMPLETED, "옛 판독 상태를 읽었다"


class TestOtherHospitalsDoNotLeak(TestCase):
    """건수가 범위를 벗어나면 **남의 의원 것이 화면에 뜬다.**"""

    async def test_another_hospitals_visit_is_not_read(self) -> None:
        mine = await make_visit("SYN-WC-10")
        theirs = await make_visit("SYN-WC-11", hospital_id=OTHER_HOSPITAL_ID)
        await attach_guide(theirs, GuideStatus.APPROVAL_PENDING)

        signals = await load_signals([mine.visit_id, theirs.visit_id], HOSPITAL_ID)

        assert theirs.visit_id not in signals, "타 병원 진료가 읽혔다"
        assert mine.visit_id in signals

    async def test_another_hospitals_events_do_not_attach_to_my_visit(self) -> None:
        """진료 번호를 알아도 그 병원 범위 밖 이벤트는 안 붙는다."""
        mine = await make_visit("SYN-WC-12")
        await MedicalDocument.create(
            hospital_id=OTHER_HOSPITAL_ID,  # 같은 진료를 가리키지만 병원이 다르다
            visit=mine,
            file_path="/synthetic/leak.jpg",
            file_size=1,
            mime_type="image/jpeg",
            uploaded_by=1,
        )

        signals = (await load_signals([mine.visit_id], HOSPITAL_ID))[mine.visit_id]

        assert signals.has_document is False, "타 병원 문서가 내 진료에 붙었다"


class TestItDoesNotAskOncePerVisit(TestCase):
    """진료가 늘어도 질의 수가 늘면 `limit=100` 에서 목록이 무너진다."""

    async def test_query_count_does_not_grow_with_the_list(self) -> None:
        few = [await make_visit(f"SYN-WC-N{i}") for i in range(2)]
        for visit in few:
            await attach_document(visit)
            await attach_ocr(visit, OcrJobStatus.COMPLETED)

        with CountingQueries() as small:
            await load_signals([v.visit_id for v in few], HOSPITAL_ID)

        many = few + [await make_visit(f"SYN-WC-M{i}") for i in range(12)]
        for visit in many[2:]:
            await attach_document(visit)
            await attach_ocr(visit, OcrJobStatus.COMPLETED)
            await attach_guide(visit, GuideStatus.STAFF_REVIEW)

        with CountingQueries() as large:
            signals = await load_signals([v.visit_id for v in many], HOSPITAL_ID)

        assert len(signals) == len(many)
        assert large.count == small.count, (
            f"진료가 {len(few)} → {len(many)} 로 늘자 질의가 "
            f"{small.count} → {large.count} 로 늘었다 — 진료마다 묻고 있다"
        )

    async def test_the_counter_actually_counts(self) -> None:
        """**이 검사가 위 검사의 전제다.** 세는 것이 0 이면 위가 늘 통과한다."""
        with CountingQueries() as counter:
            await Visit.all().count()
        assert counter.count > 0, "질의를 세지 못하고 있다 — 위 N+1 검사가 헛돈다"


class TestItReadsTheTimesTooWithoutAskingMore(TestCase):
    """같은 탭 안에서 최신을 고르려면 **시각**이 있어야 한다 — KEY-166.

    시각을 따로 물으면 목록 한 번에 질의가 둘 더 는다. 이미 읽던 행에서
    열만 늘렸는지 여기서 붙잡는다.
    """

    async def test_it_reads_when_the_guide_and_the_patient_last_moved(self) -> None:
        visit = await make_visit("SYN-WC-T1", opted_out=datetime(2026, 8, 20, tzinfo=UTC))
        await attach_guide(visit, GuideStatus.APPROVAL_RETURNED)

        signals = (await load_signals([visit.visit_id], HOSPITAL_ID))[visit.visit_id]

        guide = await GuideDocument.get(visit_id=visit.visit_id)
        patient = await Patient.get(patient_id=visit.patient_id)
        assert signals.guide_changed_at == guide.updated_at
        assert signals.patient_changed_at == patient.updated_at

    async def test_a_visit_without_a_guide_has_no_guide_time(self) -> None:
        """안내문이 없으면 시각도 없다 — 없는 사건에 시각을 지어내지 않는다."""
        visit = await make_visit("SYN-WC-T2")

        signals = (await load_signals([visit.visit_id], HOSPITAL_ID))[visit.visit_id]

        assert signals.guide_status is None
        assert signals.guide_changed_at is None
        assert signals.patient_changed_at is not None, "환자는 늘 있으므로 시각도 있어야 한다"

    async def test_reading_the_times_did_not_add_a_query(self) -> None:
        """**질의 수를 못 박는다.**

        위 「진료가 늘어도 안 는다」 검사는 *증가*만 본다. 시각을 따로 묻는
        질의를 두 개 더해도 두 쪽이 똑같이 늘어 통과한다 — 절대값을 박아야
        그 회귀가 죽는다.
        """
        visit = await make_visit("SYN-WC-T3")
        await attach_document(visit)
        await attach_ocr(visit, OcrJobStatus.COMPLETED)
        await attach_guide(visit, GuideStatus.STAFF_REVIEW)

        with CountingQueries() as counter:
            await load_signals([visit.visit_id], HOSPITAL_ID)

        assert counter.count == 4, (
            f"질의가 {counter.count} 개다 — 문서·판독·안내문·환자 넷이어야 한다. "
            "시각을 따로 묻는 질의가 붙었는지 확인할 것"
        )
