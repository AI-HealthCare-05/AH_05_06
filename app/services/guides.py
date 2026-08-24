"""안내문 검토·승인·반려 — KEY-111 (`KEY-76` 인수조건).

이 파일이 지키는 것은 넷이다.

    ① 승인·반려는 **의사만** 한다. `admin` 단독은 못 한다
    ② 승인 요청 상태가 아니면 승인할 수 없다 — 두 번 승인하거나 건너뛸 수 없다
    ③ 반려에는 **사유가 반드시** 붙는다. 그 문장이 스탭 알림에 그대로 뜬다
    ④ 상태를 바꾸는 것과 이력을 남기는 것은 **한 트랜잭션**이다

④가 특히 중요하다. 갈라 두면 상태만 바뀌고 이력이 빈 행이 생기는데,
그러면 「누가 이 글을 환자에게 내보냈나」에 답할 수 없다 — 감사가 성립하지 않는다.

권한 판정이 화면이 아니라 여기 있는 이유는 `docs/models-layout.md` 가 정한
그대로다 — 「`[승인]`은 의사 계정만」은 규칙이라 서비스가 갖는다. 화면이
버튼을 잠그는 것은 편의일 뿐이고, 잠긴 버튼을 우회한 요청도 여기서 막힌다.
"""

from datetime import datetime, timedelta

from tortoise.timezone import now
from tortoise.transactions import in_transaction

from app.core import config

# `AuthError` 는 이름이 인증처럼 보이지만 **계약이 정한 오류 봉투**다 —
# `{code, message}` 를 평평하게 내보내는 하나뿐인 길이라 여기서도 그대로 쓴다.
# `#39`(KEY-34)가 같은 모양의 일반 `ApiError` 를 들여오는 중이니, 그것이
# 병합되면 이 import 만 갈아 끼우면 된다. 지금 같은 파일을 새로 만들면
# 병합에서 부딪힌다.
from app.core.auth_errors import AuthError as ApiError
from app.models.ocr import OcrField
from app.models.visits import (
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    Visit,
)

#: 승인하면 그날 이 시각에 나간다. 와이어프레임 D1-5 의 「오늘 18:00」이다.
#: 진료가 끝난 저녁에 받아야 환자가 차분히 읽는다 — 진료 중에 오면 안 본다.
SEND_HOUR = 18

#: 반려 사유의 길이. 스탭 알림 한 줄에 들어가야 한다.
REASON_MAX = 200


def _not_found() -> ApiError:
    """없는 것과 **남의 의원 것**을 같게 답한다 — 존재 여부를 감춘다(계약 §5)."""
    return ApiError("GUIDE_NOT_FOUND", 404, "안내문을 찾을 수 없습니다.")


class GuideService:
    async def generate(self, actor, visit_id: int) -> GuideDocument:
        """확정 OCR 필드가 있어야 고정 템플릿 안내를 만들 수 있다.

        LLM·RAG 없이 출처가 고정된 합성 템플릿을 사용한다 — KEY-150 W1 범위.
        미확정 값으로 안내를 만들면 스탭이 수정한 사실이 사라지고,
        의사는 OCR 원본인지 사람이 고친 것인지 알 수 없는 글을 승인하게 된다.
        """
        self._require_staff_or_doctor(actor)
        # 진료 소유권·OCR 확정 여부는 경합 대상이 아니라 트랜잭션 밖에서 먼저 확인한다.
        visit = await Visit.filter(visit_id=visit_id, hospital_id=actor.hospital_id).first()
        if visit is None:
            raise ApiError("VISIT_NOT_FOUND", 404, "진료 건을 찾을 수 없습니다.")

        confirmed = await OcrField.filter(
            ocr_result__ocr_job__visit_id=visit_id,
            ocr_result__ocr_job__hospital_id=actor.hospital_id,
            is_confirmed=True,
        ).first()
        if confirmed is None:
            raise ApiError(
                "OCR_NOT_CONFIRMED",
                422,
                "확정된 OCR 항목이 없습니다. 먼저 OCR을 확정해 주세요.",
            )

        field_label = f"{confirmed.field_type}: {confirmed.value}" if confirmed.value else confirmed.field_type
        async with in_transaction() as connection:
            # Visit 행을 잠근 채로 중복을 확인하고 생성한다.
            # 잠금 밖에서 exists()→create() 하면 동시 요청이 둘 다 통과해
            # GuideDocument.visit 의 OneToOneField 제약에서 IntegrityError(500) 가 된다.
            # approve() 가 PR #50 에서 같은 이유로 고쳐진 패턴이다.
            if (
                await Visit.filter(visit_id=visit_id, hospital_id=actor.hospital_id)
                .select_for_update()
                .using_db(connection)
                .first()
            ) is None:
                raise ApiError("VISIT_NOT_FOUND", 404, "진료 건을 찾을 수 없습니다.")

            if await GuideDocument.filter(visit_id=visit_id).using_db(connection).exists():
                raise ApiError("GUIDE_ALREADY_EXISTS", 409, "이미 안내문이 생성되어 있습니다.")

            guide = await GuideDocument.create(
                hospital_id=actor.hospital_id,
                visit_id=visit_id,
                status=GuideStatus.APPROVAL_PENDING,
                using_db=connection,
            )
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.MEDICATION,
                generated_body=f"[합성 복약 안내]\n확정된 항목: {field_label}\n복약 지시에 따라 정해진 시간에 복용해 주세요.",
                using_db=connection,
            )
            # 주의사항은 **두 갈래로 저장한다.** 예전에는 `caution` 한 줄에 응급
            # 문장만 담고 통째로 잠갔는데, 그러면 고칠 수 있어야 할 일반 주의
            # 문구를 넣을 자리가 없다 — 넣는 순간 그것까지 잠긴다(KEY-161).
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.CAUTION,
                # 일반 주의 문구 — 원장님이 환자에 맞춰 고치는 자리다. 잠그지 않는다.
                generated_body=(
                    "[합성 주의 안내]\n복용 초기에는 가벼운 불편감이 있을 수 있고 대개 시간이 지나면서 "
                    "좋아집니다.\n평소와 다르게 느껴지는 점이 있으면 참지 마시고 진료 때 말씀해 주세요."
                ),
                using_db=connection,
            )
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.EMERGENCY,
                # 🚨 식약처 근거 응급 문장 — 사람이 고칠 수 없다(D1-2, KEY-150 이희진 코멘트).
                generated_body="처방약 복용 중 두드러기, 호흡 곤란, 심한 복통이 생기면 즉시 복용을 중단하고 응급실을 방문하세요.",
                locked=True,
                using_db=connection,
            )
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.LIFE,
                generated_body="처방 기간 중 음주는 피해 주세요. 충분한 수분 섭취와 규칙적인 수면을 유지해 주세요.",
                using_db=connection,
            )
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.MESSAGES,
                generated_body="복약 안내가 발송될 예정입니다. 궁금한 점은 진료실로 문의해 주세요.",
                using_db=connection,
            )

        return guide

    async def get(self, actor, visit_id: int) -> GuideDocument:
        """병원은 **진료를 타고** 판단한다.

        `guide_document` 에도 `hospital_id` 가 있지만 그것은 목록을 거르는
        인덱스용 사본이다. 격리를 그 사본으로 판정하면, 사본이 진료와 어긋난
        순간 남의 의원 것이 열린다 — 두 곳에 같은 값을 두면 어긋날 자리도
        함께 생긴다(`#25` 리뷰에서 나온 이야기다).

        근거를 하나로 두면 질의도 하나로 준다.
        """
        guide = (
            await GuideDocument.filter(visit_id=visit_id, visit__hospital_id=actor.hospital_id)
            .prefetch_related("sections", "visit__patient")
            .first()
        )
        if guide is None:
            raise _not_found()
        return guide

    async def _lock(self, actor, visit_id: int, connection) -> GuideDocument:
        """**트랜잭션 안에서** 이 안내문을 잠그고 읽는다.

        예전에는 `get()` 으로 읽고 상태를 확인한 **뒤에** 트랜잭션을 열었다.
        그 사이가 비어 있어서, 승인과 반려가 동시에 들어오면 **둘 다**
        `APPROVAL_PENDING` 을 읽고 둘 다 통과했다. 그러면 승인 이벤트와 반려
        이벤트가 함께 남고, 최종 상태와 기록이 어긋난다 — 의사가 승인한 것과
        실제로 나가는 것이 달라진다 (`#50` 리뷰).

        드문 일이지만 의료 안내문이라 드문 것도 막는다. 읽기·확인·쓰기를
        한 트랜잭션 안에 두고, 행을 잠근 채로 본다.

        병원 울타리도 여기서 함께 친다 — 잠글 자격이 없는 사람은 잠그지도
        못해야 한다. 다른 병원 것은 없는 것처럼 404 다(계약 §3).
        """
        guide = (
            await GuideDocument.filter(visit_id=visit_id, visit__hospital_id=actor.hospital_id)
            .select_for_update()
            .using_db(connection)
            .first()
        )
        if guide is None:
            raise _not_found()
        return guide

    async def edit_section(self, actor, visit_id: int, key: str, body: str) -> GuideSection:
        """한 갈래만 고친다. 생성 원문은 지우지 않는다."""
        self._require_doctor(actor)

        try:
            section_key = GuideSectionKey(key)
        except ValueError as err:
            raise ApiError("SECTION_NOT_FOUND", 404, "그런 항목이 없습니다.") from err

        text = (body or "").strip()
        if not text:
            raise ApiError("EMPTY_BODY", 422, "내용을 입력해 주세요.")

        async with in_transaction() as connection:
            guide = await self._lock(actor, visit_id, connection)

            section = (
                await GuideSection.filter(guide_document=guide, section_key=section_key).using_db(connection).first()
            )
            if section is None:
                raise ApiError("SECTION_NOT_FOUND", 404, "그런 항목이 없습니다.")

            if section.locked:
                # 🚨 응급 문장. 식약처 의약품정보를 근거로 미리 써 둔 것이라
                # 약이 바뀌면 문장도 함께 바뀐다 — 사람이 고칠 자리가 아니다.
                raise ApiError("SECTION_LOCKED", 409, "응급 안내 문장은 고칠 수 없습니다.")

            if guide.status is not GuideStatus.APPROVAL_PENDING:
                # 이미 승인해 발송을 기다리는 글을 조용히 바꾸면, 환자가 받는 것과
                # 승인한 것이 달라진다. 잠근 채로 보므로 승인과 겹치지 않는다.
                raise ApiError("GUIDE_NOT_PENDING", 409, "승인 요청 상태에서만 고칠 수 있습니다.")

            section.edited_body = text
            await section.save(update_fields=["edited_body", "updated_at"], using_db=connection)
            guide.version += 1
            await guide.save(update_fields=["version", "updated_at"], using_db=connection)
            await GuideEvent.create(
                guide_document=guide,
                event_type=GuideEventType.EDITED,
                section_key=section_key,
                actor_id=actor.user_id,
                using_db=connection,
            )
        return section

    async def approve(self, actor, visit_id: int) -> GuideDocument:
        """승인 — 그리고 **곧 발송 예약**이다.

        둘을 나누지 않는다. 나누면 「승인했는데 왜 안 나갔지」가 생기고,
        그 자리를 메우려고 스탭이 발송 버튼을 누르게 된다(D1-5 가 없애려던 것).
        """
        self._require_doctor(actor)

        moment = now()
        async with in_transaction() as connection:
            guide = await self._lock(actor, visit_id, connection)
            self._require_pending(guide)

            guide.status = GuideStatus.SCHEDULED_TO_SEND
            guide.approved_by = actor.user_id
            guide.approved_at = moment
            guide.scheduled_at = self._send_at(moment)
            guide.returned_reason = None  # type: ignore[assignment]
            await guide.save(
                update_fields=["status", "approved_by", "approved_at", "scheduled_at", "returned_reason", "updated_at"],
                using_db=connection,
            )
            await GuideEvent.create(
                guide_document=guide,
                event_type=GuideEventType.APPROVED,
                actor_id=actor.user_id,
                using_db=connection,
            )
        return guide

    async def return_to_staff(self, actor, visit_id: int, reason: str) -> GuideDocument:
        """스탭에 되돌린다. **사유가 없으면 되돌리지 않는다.**

        이 문장이 스탭 알림에 그대로 뜬다(D1-7 「승인 반려 — 진료기록 재업로드
        필요」). 비어 있으면 받는 사람은 무엇을 고쳐야 하는지 알 수 없고,
        그러면 되돌리는 일 자체가 왕복만 늘린다.
        """
        self._require_doctor(actor)

        text = (reason or "").strip()
        if not text:
            raise ApiError("REASON_REQUIRED", 422, "무엇을 고쳐야 하는지 적어 주세요.")
        if len(text) > REASON_MAX:
            raise ApiError("REASON_TOO_LONG", 422, f"사유는 {REASON_MAX}자까지 입력할 수 있습니다.")

        async with in_transaction() as connection:
            guide = await self._lock(actor, visit_id, connection)
            self._require_pending(guide)

            guide.status = GuideStatus.APPROVAL_RETURNED
            guide.returned_reason = text
            await guide.save(update_fields=["status", "returned_reason", "updated_at"], using_db=connection)
            await GuideEvent.create(
                guide_document=guide,
                event_type=GuideEventType.RETURNED,
                reason=text,
                actor_id=actor.user_id,
                using_db=connection,
            )
        return guide

    # ── 규칙 ────────────────────────────────────────────

    @staticmethod
    def _require_staff_or_doctor(actor) -> None:
        """`admin` 단독은 안내를 생성하지 못한다.

        `GUIDE_DRAFT` 는 staff·doctor 에게만 열려 있다(`app/tests/rbac/matrix.py`).
        `admin` 은 의원 운영 권한이지 진료 화면을 여는 역할이 아니다.
        """
        if not ({"staff", "doctor"} & set(actor.roles)):
            raise ApiError("FORBIDDEN", 403, "안내 생성은 스탭 또는 의사 계정만 할 수 있습니다.")

    @staticmethod
    def _require_doctor(actor) -> None:
        """`admin` 단독은 승인하지 못한다.

        `admin` 은 역할이 아니라 **권한**이다(`app/tests/rbac/matrix.py`) —
        의원 운영을 관리할 수 있다는 뜻이지 의료 판단을 한다는 뜻이 아니다.
        켠다고 진료 화면이 열리지 않는다.
        """
        if "doctor" not in actor.roles:
            raise ApiError("FORBIDDEN", 403, "안내문 승인은 의사 계정만 할 수 있습니다.")

    @staticmethod
    def _require_pending(guide: GuideDocument) -> None:
        if guide.status is GuideStatus.APPROVAL_PENDING:
            return
        if guide.status is GuideStatus.SCHEDULED_TO_SEND:
            # 두 번 승인은 조용히 넘기지 않는다 — 발송 예정 시각이 밀린다.
            raise ApiError("ALREADY_APPROVED", 409, "이미 승인된 안내문입니다.")
        raise ApiError("GUIDE_NOT_PENDING", 409, "아직 승인 요청된 안내문이 아닙니다.")

    @staticmethod
    def _send_at(moment: datetime) -> datetime:
        """**병원 시간으로** 오늘 18:00. 이미 지났으면 내일 같은 시각이다.

        시간대를 옮기지 않으면 18시가 아니라 **받은 값의 시간대에서** 18시가
        된다. 운영은 `databases.py` 가 `use_tz: True` 라 `now()` 가 UTC 를
        돌려주므로 UTC 18시 — 한국에서는 **다음 날 새벽 3시**다. 환자가 복약
        안내를 자다가 받는다.

        **검사에서는 안 보이던 버그다.** `conftest` 의 `generate_config(...,
        testing=True)` 가 `use_tz=False` 로 두는데, 그러면 `now()` 가 이미
        병원 시간이라 `replace(hour=18)` 이 우연히 맞는다. 두 환경이 서로 다른
        답을 주고 있었다.

        그래서 **받은 값이 어느 시간대든** 병원 시간으로 옮겨 판단한다.
        돌려주는 값도 병원 시간대를 달고 나간다 — 시각이 무슨 뜻인지가 값 안에
        남아야 저장이 어느 모드든 같은 순간을 가리킨다.

        지난 시각으로 예약하면 「예약됨」인데 영영 안 나가거나, 발송기가
        지난 것을 몰아서 한꺼번에 보낸다.
        """
        local = moment.astimezone(config.TIMEZONE)
        today = local.replace(hour=SEND_HOUR, minute=0, second=0, microsecond=0)
        return today if today > local else today + timedelta(days=1)
