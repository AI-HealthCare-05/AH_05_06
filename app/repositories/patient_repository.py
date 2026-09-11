from collections.abc import Sequence
from datetime import datetime
from typing import Any

from tortoise import BaseDBAsyncClient
from tortoise.expressions import Q
from tortoise.functions import Length, Max
from tortoise.queryset import QuerySet

from app.core.utils.common import normalize_phone_number
from app.dtos.patients import PatientSort
from app.models.patients import Patient
from app.models.visits import Visit

#: 차트 번호는 **글자열**이다 — `CharField(50)` 이고 형식 규칙이 없다.
#: 글자로만 세우면 `10` 이 `7` 보다 앞에 선다. **길이를 먼저 보고** 그다음
#: 글자를 보면 숫자처럼 늘어선다. 숫자가 아닌 코드가 섞여도 답이 하나로 정해진다.
_CHART_LENGTH = "chart_length"


def _ordered(query: QuerySet[Patient], sort: PatientSort) -> QuerySet[Patient]:
    """그 기준으로 세운 질의. **둘째 열쇠는 언제나 `patient_id`** 다.

    첫째 열쇠가 같은 줄이 있으면(같은 자리수·같은 차트번호) 차례가 매번
    달라지고, 그러면 쪽을 넘길 때 같은 환자가 두 번 나오거나 한 번도 안 나온다.

    `registered_*` 는 **표에 보이는 그 날짜**(`created_at`)로 센다 — 보여 주는
    값과 세우는 열쇠가 같아야 「등록 ▼」이 말이 된다.

    `ID_ASC` 만 번호로 센다. **이어 보기 전용**이다 — 커서가 `patient_id >` 로
    거르므로 세우는 열쇠도 번호여야 거름과 갈리지 않는다.
    """
    if sort is PatientSort.ID_ASC:
        return query.order_by("patient_id")
    if sort is PatientSort.REGISTERED_ASC:
        return query.order_by("created_at", "patient_id")
    if sort is PatientSort.CHART_ASC:
        return query.annotate(**{_CHART_LENGTH: Length("hospital_patient_no")}).order_by(
            _CHART_LENGTH, "hospital_patient_no", "patient_id"
        )
    if sort is PatientSort.CHART_DESC:
        return query.annotate(**{_CHART_LENGTH: Length("hospital_patient_no")}).order_by(
            f"-{_CHART_LENGTH}", "-hospital_patient_no", "-patient_id"
        )
    return query.order_by("-created_at", "-patient_id")


class PatientRepository:
    async def create(self, data: dict[str, Any]) -> Patient:
        return await Patient.create(**data)

    async def get_scoped(self, patient_id: int, hospital_id: int) -> Patient | None:
        return await Patient.get_or_none(patient_id=patient_id, hospital_id=hospital_id)

    async def get_by_number(self, hospital_id: int, hospital_patient_no: str) -> Patient | None:
        return await Patient.get_or_none(
            hospital_id=hospital_id,
            hospital_patient_no=hospital_patient_no,
        )

    async def list_scoped(
        self,
        hospital_id: int,
        *,
        keyword: str | None,
        after_id: int | None,
        limit: int,
        offset: int = 0,
        sms_opt_out_only: bool = False,
        patient_ids: list[int] | None = None,
        sort: PatientSort = PatientSort.REGISTERED_DESC,
    ) -> list[Patient]:
        query = self._scoped_query(hospital_id, keyword)
        if sms_opt_out_only:
            query = query.filter(sms_opted_out_at__isnull=False)
        if patient_ids is not None:
            if not patient_ids:
                return []
            query = query.filter(patient_id__in=patient_ids)
        if after_id is not None:
            #: **커서는 `id_asc` 하나만 탄다** — 라우터가 다른 차례를 400 으로
            #: 막는다 (KEY-327). 거르는 열쇠와 세우는 열쇠가 둘 다 `patient_id` 라
            #: 「이 뒤로 더」가 건너뛰거나 겹치지 않는다.
            query = query.filter(patient_id__gt=after_id)
        query = _ordered(query, sort)
        #: 쪽 번호로 건너뛴다 — 커서는 앞으로만 가서 「이전」이 안 된다 (KEY-303).
        if offset:
            query = query.offset(offset)
        return await query.limit(limit)

    async def ids_scoped(self, hospital_id: int, *, keyword: str | None) -> list[int]:
        """검색어에 걸리는 환자 번호 **전부** — 쪽 크기와 무관하게.

        진료에서 나오는 조각(진행 중 · 챙겨주세요)은 표를 걸러 셀 수 없어 의원의
        최근 진료를 훑어 낸다. 그 셈이 검색어를 모르면 **표는 걸러졌는데 배지는
        안 걸러진다** — 배지가 표보다 커지고, 그 값으로 쪽을 세면 있지도 않은
        쪽이 생겨 「다음」을 눌렀을 때 빈 표가 뜬다 (KEY-303).
        """
        if not keyword:
            return []
        return await self._scoped_query(hospital_id, keyword).values_list("patient_id", flat=True)

    async def category_counts(
        self,
        hospital_id: int,
        *,
        keyword: str | None,
        inactive_patient_ids: list[int],
        patient_ids: list[int] | None = None,
    ) -> tuple[int, int, int]:
        query = self._scoped_query(hospital_id, keyword)
        #: 날짜로 좁힌 검색이면 셈도 같이 좁아져야 한다 — 배지가 표와 어긋나면
        #: 안 보이는 사람이 있다고 읽힌다 (KEY-303).
        if patient_ids is not None:
            if not patient_ids:
                return 0, 0, 0
            query = query.filter(patient_id__in=patient_ids)
        all_count = await query.count()
        sms_opt_out_count = await query.filter(sms_opted_out_at__isnull=False).count()
        inactive_count = await query.filter(patient_id__in=inactive_patient_ids).count() if inactive_patient_ids else 0
        return all_count, sms_opt_out_count, inactive_count

    @staticmethod
    async def latest_visit_times(hospital_id: int) -> dict[int, datetime]:
        """환자별 최신 진료 시각만 한 번의 집계 질의로 읽는다."""
        rows = await (
            Visit.filter(hospital_id=hospital_id)
            .annotate(latest_visited_at=Max("visited_at"))
            .group_by("patient_id")
            .values("patient_id", "latest_visited_at")
        )
        return {int(row["patient_id"]): row["latest_visited_at"] for row in rows}

    @staticmethod
    def _scoped_query(hospital_id: int, keyword: str | None):  # type: ignore[no-untyped-def]
        query = Patient.filter(hospital_id=hospital_id)
        if keyword:
            # 저장은 숫자만 남긴다(normalize_phone_number). 검색어도 같은 모양으로
            # 맞춰야 차트에 적힌 대로 "010-3945-7702" 를 쳤을 때 찾힌다 — 계약 §6 의
            # 「정규화된 휴대폰에서 검색한다」가 이 자리다.
            # 못 찾으면 오류가 아니라 「결과 없음」이라, 직원은 미등록 환자로 알고
            # 새로 등록한다. 그러면 차트번호 중복까지 이어진다.
            conditions = Q(name__startswith=keyword) | Q(hospital_patient_no__contains=keyword)
            digits = normalize_phone_number(keyword)
            if digits:
                conditions |= Q(phone__contains=digits)
            query = query.filter(conditions)
        return query

    async def latest_visits(self, patient_ids: list[int], hospital_id: int) -> dict[int, Visit]:
        """환자 수와 무관하게 한 번의 질의로 최신 진료를 모은다."""
        if not patient_ids:
            return {}
        rows = await Visit.filter(patient_id__in=patient_ids, hospital_id=hospital_id).order_by(
            "patient_id", "-visited_at", "-visit_id"
        )
        latest: dict[int, Visit] = {}
        for visit in rows:
            latest.setdefault(visit.patient_id, visit)
        return latest

    async def has_visits(self, patient_id: int, hospital_id: int) -> bool:
        return await Visit.filter(patient_id=patient_id, hospital_id=hospital_id).exists()

    async def save(
        self,
        patient: Patient,
        fields: Sequence[str],
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        # `using_db` 를 받는 이유는 환자번호 정정 때문이다 — 번호를 바꾸는 것과
        # 감사 기록을 남기는 것이 **한 트랜잭션**이어야 한다(KEY-121). 갈라 두면
        # 번호만 바뀌고 「왜 바꿨나」가 비는 행이 생기고, 그러면 의무기록 정정을
        # 되짚을 수 없다.
        await patient.save(update_fields=fields, using_db=using_db)
