#!/usr/bin/env python3
"""합성 데이터 seed 명령 — KEY-29

고정 데이터로 개발 DB 를 채운다. 같은 명령을 반복 실행해도 데이터가 쌓이지 않는다.

사용법:
    SEED_STAFF_PASSWORD=<pw> uv run python scripts/seed.py [--mode MODE]

옵션:
    --mode empty   아무것도 적재하지 않음 (S1-1 빈 화면 확인용)
    --mode staff   직원 계정 14개만 적재 (기본값)
    --mode full    직원 + 환자·진료 데이터 전체 적재

전제:
    - docs/data/synthetic-staff.csv 가 있어야 한다 (PR #12, KEY-10).
    - SEED_STAFF_PASSWORD 환경변수가 없으면 실행을 거부한다.
    - 운영 환경(ENV=prod)에서는 실행을 거부한다.
"""

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAFF_CSV = ROOT / "docs" / "data" / "synthetic-staff.csv"
PATIENTS_CSV = ROOT / "docs" / "data" / "synthetic-patients.csv"  # noqa: F841

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tortoise import Tortoise  # noqa: E402

from app.core.config import Config  # noqa: E402
from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.core.utils.security import hash_password  # noqa: E402
from app.models.users import Gender, User  # noqa: E402

SEED_PASSWORD_ENV = "SEED_STAFF_PASSWORD"


def _guard_environment() -> None:
    config = Config()
    if str(config.ENV).lower() == "prod":
        print("오류: 운영 환경(ENV=prod)에서는 seed 를 실행할 수 없습니다.", file=sys.stderr)
        sys.exit(1)


def _require_password() -> str:
    password = os.environ.get(SEED_PASSWORD_ENV)
    if not password:
        print(
            f"오류: {SEED_PASSWORD_ENV} 환경변수가 없습니다.\n"
            f"  SEED_STAFF_PASSWORD=<개발용 비밀번호> uv run python scripts/seed.py",
            file=sys.stderr,
        )
        sys.exit(1)
    return password


def _require_csv(path: Path, hint: str) -> None:
    if not path.exists():
        print(
            f"오류: {path} 파일이 없습니다.\n  {hint}",
            file=sys.stderr,
        )
        sys.exit(1)


async def seed_staff(password: str) -> None:
    """직원 14개 계정을 User 테이블에 적재한다.

    멱등성: email(= login_id@seed.local) 기준 upsert.

    NOTE: 현재 User 모델은 부트캠프 예시 골격(email·is_admin bool)이다.
          auth-contract.md 가 지적한 대로 login_id·roles jsonb 로 교체되면
          이 함수의 필드 매핑을 함께 업데이트해야 한다.
    """
    _require_csv(
        STAFF_CSV,
        hint="docs/data/synthetic-staff.csv 는 PR #12(KEY-10) 이 만든다. 해당 PR 을 merge 한 뒤 다시 실행하세요.",
    )

    hashed = hash_password(password)
    created = updated = 0

    with STAFF_CSV.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    for idx, row in enumerate(rows):
        login_id = row["login_id"]
        roles = frozenset(r.strip() for r in row["roles"].split("|") if r.strip())
        is_active = row["status"] == "active"
        is_admin = "admin" in roles

        # login_id → email: staff 모델로 교체되기 전 임시 매핑
        email = f"{login_id}@seed.local"

        # staff 모델에는 gender·birthday·phone_number 가 없다.
        # 현재 User 모델이 필수로 요구하므로 의미 없는 플레이스홀더를 넣는다.
        phone = f"0100000{idx + 1:04d}"  # 01000000001 ~ 01000000014, 11자리

        _, was_created = await User.get_or_create(
            email=email,
            defaults={
                "hashed_password": hashed,
                "name": row["이름"],
                "gender": Gender.FEMALE,
                "birthday": "1990-01-01",
                "phone_number": phone,
                "is_active": is_active,
                "is_admin": is_admin,
            },
        )

        if was_created:
            created += 1
        else:
            await User.filter(email=email).update(
                hashed_password=hashed,
                is_active=is_active,
                is_admin=is_admin,
            )
            updated += 1

    print(f"[staff] created={created} updated={updated} total={len(rows)}")


async def seed_patients() -> None:
    """환자·진료 데이터 적재 — patient/visit 모델 구현 후 활성화.

    TODO: KEY-1(환자·진료 모델), KEY-2(OCR·안내) 가 완성되면 구현한다.
          docs/data/synthetic-patients.csv → patient·visit·lab_result·visit_flag 테이블
          멱등성 키: patient.chart_no (자연 키)
          결정론적 UUID: uuid5(NAMESPACE_DNS, row["시나리오ID"]) 등
    """
    print("[patients] 건너뜀 — patient/visit 모델 미구현 (KEY-1, KEY-2 이후 활성화)")


async def main(mode: str) -> None:
    _guard_environment()
    await Tortoise.init(config=TORTOISE_ORM)

    match mode:
        case "empty":
            print("[seed] 빈 상태 — 아무것도 적재하지 않습니다.")
        case "staff":
            password = _require_password()
            await seed_staff(password)
        case "full":
            password = _require_password()
            await seed_staff(password)
            await seed_patients()
        case _:
            print(f"알 수 없는 mode: {mode}", file=sys.stderr)
            await Tortoise.close_connections()
            sys.exit(1)

    await Tortoise.close_connections()
    print("[seed] 완료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="합성 데이터 seed — KEY-29",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  SEED_STAFF_PASSWORD=devpass uv run python scripts/seed.py --mode=staff\n"
            "  SEED_STAFF_PASSWORD=devpass uv run python scripts/seed.py --mode=full\n"
            "  uv run python scripts/seed.py --mode=empty"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["empty", "staff", "full"],
        default="staff",
        help="empty=적재 없음 | staff=직원만(기본값) | full=전체",
    )
    args = parser.parse_args()
    asyncio.run(main(args.mode))
