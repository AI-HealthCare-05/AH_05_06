"""검사 기준선 — 와이어프레임 D2-4.

원문 주석: 「기준선 → D1 「나의 목표」의 남은 거리 계산에 쓰인다」.

**두 가지를 담는다.**

  · **기준선** — 목표까지 얼마 남았나를 셈할 값. 비워 둘 수 있다.
  · **판독 키워드** — EMR 마다 표기가 다르다(DHEA-S / DHEAS / 황체호르몬).
    판독이 진료기록에서 그 항목을 찾도록 의원이 쓰는 표기를 넣어 둔다.

**기본 목록은 코드가 갖는다.** 의원이 이 화면을 처음 열 때 그 의원 몫으로 한
번 깔린다. 문자 문구(D2-5)처럼 「고친 것만 담는다」로 두지 않는 이유는, 여기서는
**지우고 더할 수 있어야** 하기 때문이다 — 안 쓰는 항목을 지운 것과 아직 안
고친 것을 구별할 수 없다.

기본값은 **원문 D2-4 에 적힌 그대로**다. 의료 판단이 아니라 화면에 이미 적혀
있는 것을 표로 옮긴 것이고, 화면이 그 옆에 「기준선은 검사기관 · 연령에 따라
다릅니다」를 함께 띄운다. 의원이 확인해 고칠 자리다.
"""

from dataclasses import dataclass
from decimal import Decimal

from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor
from app.models.catalog import BaselineDirection, LabBaseline, SetDisease
from app.models.staffs import Staff
from app.services.patient_visit_scope import hospital_id_of


@dataclass(frozen=True, slots=True)
class Seed:
    disease: SetDisease
    name: str
    direction: BaselineDirection
    low: str | None
    high: str | None
    by_age: bool
    keywords: str
    unit: str
    always_shown: bool


#: 원문 D2-4 의 열세 줄. **차례도 원문대로다** — 의사가 보던 순서가 바뀌면
#: 같은 화면이 아니게 된다.
DEFAULT_BASELINES: tuple[Seed, ...] = (
    Seed(SetDisease.PCOS, "월경 주기", BaselineDirection.KEEP, "21", "35", False, "LMP, 월경, 주기", "일", True),
    Seed(
        SetDisease.PCOS,
        "총 테스토스테론",
        BaselineDirection.LOWER,
        None,
        None,
        False,
        "Testosterone, 테스토스테론",
        "ng/dL",
        True,
    ),
    Seed(SetDisease.PCOS, "DHEA-S", BaselineDirection.LOWER, None, None, False, "DHEA-S, DHEAS", "µg/dL", True),
    Seed(SetDisease.PCOS, "AMH", BaselineDirection.KEEP, None, None, True, "AMH, 항뮬러관", "ng/mL", True),
    Seed(SetDisease.PCOS, "LH / FSH", BaselineDirection.REFERENCE, None, None, False, "LH, FSH", "비율", True),
    Seed(SetDisease.PCOS, "HbA1c", BaselineDirection.LOWER, None, None, False, "HbA1c, 당화혈색소", "%", False),
    Seed(SetDisease.PCOS, "BMI", BaselineDirection.LOWER, None, None, False, "BMI, 체질량", "", False),
    Seed(
        SetDisease.ENDOMETRIOSIS,
        "혈색소 Hb",
        BaselineDirection.KEEP,
        "12.0",
        None,
        False,
        "Hb, 혈색소, Hemoglobin",
        "g/dL",
        True,
    ),
    Seed(
        SetDisease.ENDOMETRIOSIS,
        "자궁내막종 크기",
        BaselineDirection.LOWER,
        None,
        None,
        False,
        "LO, RO, cyst, 내막종",
        "cm",
        True,
    ),
    Seed(
        SetDisease.ENDOMETRIOSIS, "내막 두께 EM", BaselineDirection.KEEP, None, None, False, "EM, 내막두께", "cm", True
    ),
    Seed(SetDisease.ENDOMETRIOSIS, "AMH", BaselineDirection.KEEP, None, None, True, "AMH, 항뮬러관", "ng/mL", True),
    Seed(
        SetDisease.ENDOMETRIOSIS,
        "간수치 AST/ALT",
        BaselineDirection.KEEP,
        None,
        "40",
        False,
        "AST, ALT, SGOT",
        "U/L",
        True,
    ),
    Seed(
        SetDisease.ENDOMETRIOSIS, "CA-125", BaselineDirection.LOWER, None, "35", False, "CA-125, CA125", "U/mL", False
    ),
)


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError) as error:
        raise ApiError(422, "INVALID_BASELINE", "기준선은 숫자로 적어 주세요.") from error


class LabBaselineService:
    async def list(
        self,
        actor: ClinicalActor,
        *,
        doctor_id: int | None,
    ) -> tuple[list[LabBaseline], list[Staff]]:
        hospital_id = hospital_id_of(actor)
        await self._ensure_seeded(hospital_id)
        # **차례는 `position` 만 본다.** 질환으로 먼저 정렬하면 알파벳순이 되어
        # 원문(다낭성 → 자궁내막증)이 뒤집힌다 — 화면이 보여 준 차례가 곧
        # 저장되는 차례다.
        rows = await LabBaseline.filter(hospital_id=hospital_id, doctor_id=doctor_id).order_by(
            "position", "lab_baseline_id"
        )
        if not rows and doctor_id is not None:
            # 그 의사만의 기준을 아직 안 만들었다. **의원 공통을 보여 준다** —
            # 빈 화면을 띄우면 「이 의사에게는 기준이 없다」로 읽히는데, 실제로는
            # 의원 공통이 쓰인다.
            rows = await LabBaseline.filter(hospital_id=hospital_id, doctor_id=None).order_by(
                "position", "lab_baseline_id"
            )
        return list(rows), await self._doctors(hospital_id)

    @staticmethod
    async def _doctors(hospital_id: int) -> list[Staff]:
        """**역할은 JSON 칸이라 SQL 로 못 거른다.** 의원 직원이 수십이라
        읽어 와서 고르는 편이 낫고, 억지로 `roles__contains` 를 쓰면 Tortoise
        가 그 값을 JSON 으로 파싱하려다 터진다."""
        everyone = await Staff.filter(hospital_id=hospital_id).order_by("staff_id")
        return [staff for staff in everyone if "doctor" in (staff.roles or [])]

    async def save(
        self,
        actor: ClinicalActor,
        *,
        doctor_id: int | None,
        items: list[dict],
    ) -> None:
        """**한 판 통째로 저장한다.**

        줄마다 번호를 주고받으면 화면이 그 번호를 들고 다녀야 하고, 지운 줄을
        놓치면 유령이 남는다 — 처방 설정(D2-3)의 약·확인 항목과 같은 판단이다.
        """
        self._require_doctor(actor)
        hospital_id = hospital_id_of(actor)
        rows = [self._checked(item, index) for index, item in enumerate(items)]

        seen = {(row["disease"], row["name"]) for row in rows}
        if len(seen) != len(rows):
            raise ApiError(422, "DUPLICATE_BASELINE", "같은 질환에 같은 검사 항목이 둘일 수 없습니다.")

        async with in_transaction() as connection:
            await LabBaseline.filter(hospital_id=hospital_id, doctor_id=doctor_id).using_db(connection).delete()
            for row in rows:
                await LabBaseline.create(hospital_id=hospital_id, doctor_id=doctor_id, using_db=connection, **row)

    async def _ensure_seeded(self, hospital_id: int) -> None:
        """**의원이 이 화면을 처음 열 때 한 번 깔린다.**

        읽는 자리에서 쓰는 것이 낯설지만, 대안이 더 나쁘다 — 마이그레이션에서
        깔면 나중에 생기는 의원에는 안 깔리고(의원을 만드는 화면이 아직 없다),
        빈 화면을 보이면 의사가 열세 줄을 손으로 적어야 한다.

        비어 있을 때만 넣으므로 여러 번 불러도 같다.
        """
        if await LabBaseline.filter(hospital_id=hospital_id, doctor_id=None).exists():
            return
        for index, seed in enumerate(DEFAULT_BASELINES):
            await LabBaseline.get_or_create(
                hospital_id=hospital_id,
                doctor_id=None,
                disease=seed.disease,
                name=seed.name,
                defaults={
                    "direction": seed.direction,
                    "low": _decimal(seed.low),
                    "high": _decimal(seed.high),
                    "by_age": seed.by_age,
                    "keywords": seed.keywords,
                    "unit": seed.unit,
                    "always_shown": seed.always_shown,
                    "position": index,
                },
            )

    @staticmethod
    def _require_doctor(actor: ClinicalActor) -> None:
        """원문 D2-2 와 같은 규칙이다 — 설정에서 의료 판단이 걸리는 값은
        의사만 고친다. 기준선은 환자가 보는 「목표까지 얼마」를 정한다."""
        if "doctor" not in actor.roles:
            raise ApiError(403, "DOCTOR_ONLY", "검사 기준선은 의사 계정만 수정할 수 있습니다.")

    @staticmethod
    def _checked(item: dict, index: int) -> dict:
        name = str(item.get("name") or "").strip()
        if not name:
            raise ApiError(422, "EMPTY_NAME", "검사 항목 이름을 적어 주세요.")

        low = _decimal(item.get("low"))
        high = _decimal(item.get("high"))
        if low is not None and high is not None and low > high:
            raise ApiError(422, "INVALID_RANGE", "기준선의 아래가 위보다 클 수 없습니다.")

        by_age = bool(item.get("by_age"))
        if by_age:
            # 나이별이면 숫자 하나로 못 적는다. 남겨 두면 어느 쪽으로 셈할지
            # 알 수 없으므로 여기서 지운다.
            low = high = None

        return {
            "disease": SetDisease(item["disease"]),
            "name": name[:100],
            "direction": BaselineDirection(item.get("direction") or BaselineDirection.KEEP),
            "low": low,
            "high": high,
            "by_age": by_age,
            "keywords": str(item.get("keywords") or "").strip()[:200],
            "unit": str(item.get("unit") or "").strip()[:20],
            "always_shown": bool(item.get("always_shown", True)),
            "position": index,
        }
