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

import asyncio
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
from app.models.catalog import CautionSectionKey, DoctorGuideCopy, PrescriptionSet
from app.models.ocr import OcrField, OcrJob, OcrJobStatus, OcrResult
from app.models.prescriptions import Prescription, PrescriptionItem, ordered_prescription_items
from app.models.visits import (
    GuideDocument,
    GuideEvent,
    GuideEventType,
    GuideMessage,
    GuideMessageKind,
    GuideMessageSetting,
    GuideMessageStatus,
    GuideSection,
    GuideSectionKey,
    GuideStatus,
    Visit,
)
from app.services import guide_defaults
from app.services.drug_caution import DrugCautionService

#: 승인하면 그날 이 시각에 나간다. 와이어프레임 D1-5 의 「오늘 18:00」이다.
#: 진료가 끝난 저녁에 받아야 환자가 차분히 읽는다 — 진료 중에 오면 안 본다.
SEND_HOUR = 18

#: 확인 · 소진 문자가 나가는 시각. 안내문(18:00)과 다르다 —
#: 와이어프레임 S1-14 가 「확인 문자 시각 오전 10:00」이라 적는다.
#: 안내문은 진료 당일 저녁에 받아야 하고, 확인 문자는 며칠 뒤 낮이 낫다.
CHECK_HOUR = 10

#: 소진 임박은 며칠 전에 보내나. D2-3 에서 처방별로 정할 값인데 그 자리가
#: 아직 없어 기본값을 쓴다 (S1-14 의 「소진 3일 전」).
RUN_OUT_BEFORE_DAYS = 3

#: 확인 회차와 그 날수 — **있는 것 전부**다. 무엇이 켜져 있는지는 `_DEFAULT_ON`
#: 과 저장된 설정이 정한다. 한 달 뒤는 기본이 꺼짐이지만 스탭이 켤 수 있다(S1-14).
#: 진료일로부터 세는 이유는, 승인일 기준이면 승인이 하루 늦어질 때 「복약 7일째」
#: 가 8일째에 가기 때문이다 — 환자에게 적는 숫자다.
CHECK_DAYS: dict[GuideMessageKind, int] = {
    GuideMessageKind.CHECK_D7: 7,
    GuideMessageKind.CHECK_D15: 15,
    GuideMessageKind.CHECK_D30: 30,
}

#: 아무도 안 만졌을 때 켜져 있는 회차. 와이어프레임 S1-14 의 체크 상태다 —
#: 「☑ 일주일 뒤(고정) · ☑ 보름 뒤 · ☐ 한 달 뒤」, 소진 임박은 켜짐.
_DEFAULT_ON: dict[GuideMessageKind, bool] = {
    GuideMessageKind.CHECK_D7: True,
    GuideMessageKind.CHECK_D15: True,
    GuideMessageKind.CHECK_D30: False,
    GuideMessageKind.RUN_OUT: True,
}

#: **일주일 뒤는 끌 수 없다.** 원문이 「(고정)」이라 적고 주석도 「일주일 뒤는
#: 여기서도 끌 수 없다」고 못박는다 — 복약 첫 주가 가장 잘 끊기는 구간이다.
#: 화면이 체크박스를 잠그지만, 서버도 막는다. 화면만 막으면 요청 하나로 꺼진다.
FIXED_ON: frozenset[GuideMessageKind] = frozenset({GuideMessageKind.CHECK_D7})

#: 확인 문자를 몇 시에 보낼지 — 화면이 고르게 하는 값들(S1-14 의 시각 목록).
#: 아무 시각이나 받으면 새벽 3시에 문자가 갈 수 있다.
CHECK_HOURS: tuple[int, ...] = (9, 10, 11, 14, 18)

#: 소진 며칠 전. 0이면 소진 당일이라 임박이 아니고, 너무 크면 처방 시작 전이 된다.
RUN_OUT_BEFORE_MIN = 1
RUN_OUT_BEFORE_MAX = 30

#: 문구 한 통의 길이. 장문(LMS)도 담아야 해서 넉넉히 두되, 무한은 아니다.
MESSAGE_BODY_MAX = 2000

#: 반려 사유의 길이. 스탭 알림 한 줄에 들어가야 한다.
REASON_MAX = 200

# KEY-165: DrugCautionContent 승인 문구가 없을 때 사용하는 범용 폴백.
# caution 은 어떤 약물·증상도 특정하지 않는 안전한 문장이다(PR #100 이희진 검수).
# emergency 폴백은 약물 비특이적 일반 응급 지시다. 세트별 승인 문구가 없을 때만 쓴다.
# 기본 문구는 `guide_defaults` 하나에서만 온다. 여기에 따로 들고 있었더니
# 설정 화면이 「원본」이라며 보이는 글과 **실제로 나가는 글이 달랐다** —
# 셋은 우연히 같았고 복약지도만 어긋나 있었다.


def _not_found() -> ApiError:
    """없는 것과 **남의 의원 것**을 같게 답한다 — 존재 여부를 감춘다(계약 §5)."""
    return ApiError("GUIDE_NOT_FOUND", 404, "안내문을 찾을 수 없습니다.")


def _medication_body(items: list[PrescriptionItem], guidance: str) -> str:
    """구조화 처방 항목을 환자가 읽는 복약 안내로 옮긴다.

    약명·복용 빈도·기간은 ``PrescriptionItem`` 에 실제로 저장된 값만 쓴다.
    기간이 없는 필요시 약에 다른 약의 기간을 붙이지 않고, 처방 항목 자체가
    없으면 승인된 기본 지도 문장만 내보낸다 — 없는 값을 OCR 원문이나 임의
    문장으로 대신 만들지 않는다(KEY-224).
    """
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        facts = [item.name.strip(), item.frequency.strip()]
        if item.duration_days is not None:
            facts.append(f"{item.duration_days}일분")
        lines.append(f"{index}. {' · '.join(fact for fact in facts if fact)}")

    if not lines:
        return guidance
    return "\n".join(("처방된 복약 정보", *lines, guidance))


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

        # 가장 최근 비제외 completed job을 기준으로 확정 여부를 판정한다.
        # 새 문서를 추가 업로드했을 때 이전 확정값으로 게이트가 통과되는 것을 막는다.
        latest_job = (
            await OcrJob.filter(
                visit_id=visit_id,
                hospital_id=actor.hospital_id,
                excluded_from_guide=False,
                status=OcrJobStatus.COMPLETED,
            )
            .order_by("-created_at")
            .first()
        )

        if latest_job is None:
            raise ApiError(
                "OCR_NOT_CONFIRMED",
                422,
                "확정된 OCR 항목이 없습니다. 먼저 OCR을 확정해 주세요.",
            )

        latest_result = await OcrResult.filter(ocr_job=latest_job).first()
        if latest_result is None:
            raise ApiError(
                "OCR_NOT_CONFIRMED",
                422,
                "확정된 OCR 항목이 없습니다. 먼저 OCR을 확정해 주세요.",
            )

        unconfirmed = await OcrField.filter(
            ocr_result=latest_result,
            is_confirmed=False,
        ).first()
        if unconfirmed is not None:
            raise ApiError(
                "OCR_NOT_CONFIRMED",
                422,
                "가장 최근 판독에 확정되지 않은 항목이 있습니다. 모든 항목을 확정해 주세요.",
            )

        confirmed = await OcrField.filter(
            ocr_result=latest_result,
            is_confirmed=True,
        ).first()

        # 미확정 필드가 없더라도 확정된 필드가 하나도 없으면(필드 0개) 안내 생성을 막는다.
        if confirmed is None:
            raise ApiError(
                "OCR_NOT_CONFIRMED",
                422,
                "확정된 OCR 항목이 없습니다. 먼저 OCR을 확정해 주세요.",
            )

        # KEY-165: 처방 세트의 승인된 caution/emergency 문구를 미리 조회한다.
        # 트랜잭션 밖에서 실행해 락 보유 시간을 줄인다.
        # 미등록·미승인이면 None → 트랜잭션 안에서 폴백 문구를 사용한다(KEY-180 §4).
        #
        # **세트는 한 번만 찾는다.** 갈래마다·의사마다 이름으로 다시 찾으면
        # 같은 `SELECT` 가 **네 번** 돈다 — 주의·응급·담당 문구·의원 공통 문구가
        # 전부 같은 세트를 본다 (`#191` 리뷰, 2heej).
        prescription = await Prescription.filter(visit_id=visit_id).prefetch_related("items").first()
        prescription_items = ordered_prescription_items(prescription)
        set_name = prescription.prescription_set if prescription else None
        prescription_set = await PrescriptionSet.filter(name=set_name).first() if set_name else None

        # KEY-243: **의사가 고친 문구가 있으면 그것이 이긴다.**
        #
        # D2-2 「안내문 고치기」가 `DoctorGuideCopy` 에 저장하는데, 여기서 읽지
        # 않고 있었다 — 의사가 고쳐도 환자에게는 원본이 나갔다. 고칠 수 있게
        # 해 놓고 반영하지 않는 것이 제일 나쁘다: 의사는 고쳤다고 믿는다.
        #
        # **담당 의사 것 → 의원 공통 → 기본 문구.** 갈래마다 따로 내려간다 —
        # 담당이 주의사항만 고치고 의원 공통이 복약지도만 가졌으면 둘 다
        # 나가야 한다. 통째로 한 벌만 고르면 한쪽이 통째로 묻힌다.
        #
        # 의원 공통이 뒤인 것은 개인 문구가 더 좁은 뜻이기 때문이다 —
        # 좁은 것이 넓은 것을 덮는다(2026-09-02 회의: 「기본 설정은 모두
        # 공통으로 두자. 원장별 설정은 나중에」).
        #
        # **누구 것을 읽는지는 `_doctor_copies` 의 설명에 적혀 있다.** 여기에
        # 두 벌로 적혀 있었는데, 규칙은 지켜지는 자리에 한 벌만 있어야 고칠 때
        # 같이 읽힌다.
        #
        # **넷을 나란히 돌린다.** 서로를 안 기다린다. 트랜잭션 밖이라 락 보유
        # 시간과는 무관하고, 지연만 줄어든다.
        caution_content, emergency_content, own_copies, common_copies = await asyncio.gather(
            DrugCautionService.approved_content_of(prescription_set, CautionSectionKey.CAUTION),
            DrugCautionService.approved_content_of(prescription_set, CautionSectionKey.EMERGENCY),
            self._doctor_copies(actor.hospital_id, visit.doctor_id, prescription_set),
            self._doctor_copies(actor.hospital_id, None, prescription_set),
        )
        # **담당 것이 의원 공통을 덮는다** — 뒤에 오는 쪽이 이긴다.
        copies = {**common_copies, **own_copies}

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
                # **스탭 확인부터다** (와이어프레임 S1-11).
                #
                # 전에는 여기서 바로 APPROVAL_PENDING 으로 보냈다 — 만들자마자
                # 원장님 목록에 떴다는 뜻이다. 그런데 와이어프레임은
                # 「스탭이 넘기지 않으면 원장님 목록에 뜨지 않는다」고 못 박는다.
                # 스탭이 먼저 보는 이유는 원장님 시간을 아끼기 위해서다 —
                # 진료기록이 잘못 올라갔거나 다른 환자 것이 섞인 것은 스탭이 잡는다.
                #
                # `GuideDocument.status` 의 기본값이 이미 STAFF_REVIEW 다.
                # 그것을 덮어쓰던 한 줄이 흐름을 건너뛰고 있었다.
                status=GuideStatus.STAFF_REVIEW,
                using_db=connection,
            )
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.MEDICATION,
                # KEY-224: 첫 OCR 필드 하나가 아니라 KEY-66이 만든 구조화 처방을
                # 전부 싣는다. 복수 약제의 빈도·기간을 서로 섞지 않고, 없는 값은
                # 지어내지 않는다. 의사/의원별 지도 문구 우선순위는 그대로다.
                generated_body=_medication_body(
                    prescription_items,
                    copies.get(CautionSectionKey.MEDICATION, guide_defaults.MEDICATION),
                ),
                using_db=connection,
            )
            # 주의사항은 **두 갈래로 저장한다.** 예전에는 `caution` 한 줄에 응급
            # 문장만 담고 통째로 잠갔는데, 그러면 고칠 수 있어야 할 일반 주의
            # 문구를 넣을 자리가 없다 — 넣는 순간 그것까지 잠긴다(KEY-161).
            #
            # KEY-165: 처방 세트별 승인 문구가 있으면 그것을 쓴다. 없으면 폴백.
            # caution 은 의사가 고칠 수 있어 locked=False, emergency 는 locked=True.
            # 이기는 차례: 의사가 고친 문구 → 세트별 승인 문구 → 범용 폴백.
            #
            # `drug_caution_content_id` 는 **원본을 가리킨 채로 둔다.** 의사가
            # 고쳤어도 그 글이 어느 승인 문구에서 나왔는지는 남아야 한다 —
            # 나중에 원본이 개정되면 무엇을 다시 봐야 하는지 알 수 있다.
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.CAUTION,
                generated_body=copies.get(
                    CautionSectionKey.CAUTION,
                    caution_content.body if caution_content else guide_defaults.CAUTION,
                ),
                drug_caution_content_id=(caution_content.drug_caution_content_id if caution_content else None),
                using_db=connection,
            )
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.EMERGENCY,
                # 🚨 승인된 세트별 응급 문장 또는 범용 폴백 — 사람이 고칠 수 없다(KEY-150, KEY-165).
                # `copies` 를 보지 않는다 — 고칠 수 없는 글이다(KEY-150).
                generated_body=emergency_content.body if emergency_content else guide_defaults.EMERGENCY,
                drug_caution_content_id=(emergency_content.drug_caution_content_id if emergency_content else None),
                locked=True,
                using_db=connection,
            )
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.LIFE,
                generated_body=copies.get(CautionSectionKey.LIFE, guide_defaults.LIFE),
                using_db=connection,
            )
            await GuideSection.create(
                guide_document=guide,
                section_key=GuideSectionKey.MESSAGES,
                generated_body="복약 안내가 발송될 예정입니다. 궁금한 점은 진료실로 문의해 주세요.",
                using_db=connection,
            )
            # 안내문과 다섯 섹션이 생겼는데 이 행만 빠지면 「누가 생성했나」에
            # 답할 수 없다. 같은 트랜잭션에 둬서 감사 기록 저장이 실패하면
            # 안내문·섹션도 함께 되돌린다 — 생성 성공과 감사 성공은 한 사건이다.
            await GuideEvent.create(
                guide_document=guide,
                event_type=GuideEventType.GENERATED,
                actor_id=actor.user_id,
                using_db=connection,
            )

        return guide

    async def get(self, actor, visit_id: int) -> GuideDocument:
        """병원은 **진료를 타고** 판단한다.

        역할을 **먼저** 본다. 병원 범위만 보고 역할을 안 보면 `admin` 단독
        계정이 남의 진료가 아닌 **자기 의원 환자의** 이름·차트번호·생년월일과
        안내문 전문을 읽는다. 같은 계정이 `GET /patients` 에서는 403 인데
        여기만 열려 있었다 — KEY-111 때부터 있던 구멍이고 KEY-90 QA 에서
        드러났다 (KEY-168).

        찾기 전에 보는 것도 중요하다. 먼저 찾고 나중에 역할을 보면, 권한 없는
        사람에게 404 를 주면서 「그 의원에 그런 진료가 없다」를 알려 준다.

        `guide_document` 에도 `hospital_id` 가 있지만 그것은 목록을 거르는
        인덱스용 사본이다. 격리를 그 사본으로 판정하면, 사본이 진료와 어긋난
        순간 남의 의원 것이 열린다 — 두 곳에 같은 값을 두면 어긋날 자리도
        함께 생긴다(`#25` 리뷰에서 나온 이야기다).

        근거를 하나로 두면 질의도 하나로 준다.
        """
        self._require_staff_or_doctor(actor, "안내문 조회는")

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
        # **스탭도 고친다** (와이어프레임 S1-11 — 「스탭은 내용을 고칠 수
        # 있지만 승인은 못 한다」). RBAC 도 이미 그렇게 적혀 있다:
        # GUIDE_DRAFT = {staff, doctor}. 여기만 의사로 좁혀 두어서, 스탭이
        # 확인 화면에서 고칠 수가 없었다.
        #
        # **누가 고치느냐가 아니라 언제 고치느냐로 가른다** — 아래 상태 검사가
        # 그 몫이다. 스탭 확인 중이면 스탭이, 승인 요청 중이면 의사가 고친다.
        self._require_staff_or_doctor(actor, "안내문 수정은")

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

            # 이미 승인해 발송을 기다리는 글을 조용히 바꾸면, 환자가 받는 것과
            # 승인한 것이 달라진다. 잠근 채로 보므로 승인과 겹치지 않는다.
            #
            # **반려된 것도 고칠 수 있다.** 아래 주석이 「스탭이 고치려면 반려를
            # 거쳐 자기 차례로 돌아와야 한다」고 적어 두었는데, 정작 돌아온
            # 자리가 막혀 있었다 — 화면은 「고친 뒤 다시 넘겨 주세요」라고
            # 안내하면서 고치려 들면 409 를 냈다. 반려는 **고치라고** 하는
            # 것이므로 고칠 수 없으면 뜻이 없다 (Gomin-art 님 `#176` 리뷰).
            if guide.status not in (
                GuideStatus.STAFF_REVIEW,
                GuideStatus.APPROVAL_PENDING,
                GuideStatus.APPROVAL_RETURNED,
            ):
                raise ApiError("GUIDE_NOT_PENDING", 409, "확인·승인 요청 상태에서만 고칠 수 있습니다.")

            # **승인 요청 중에는 의사만 고친다.** 원장님이 보고 있는 글을 스탭이
            # 바꾸면, 승인한 것과 읽은 것이 달라진다. 스탭이 고치려면 반려를
            # 거쳐 자기 차례로 돌아와야 한다.
            if guide.status is GuideStatus.APPROVAL_PENDING and not self._is_doctor(actor):
                # **403 이다, 409 가 아니다.** 「지금은 때가 아니다」가 아니라
                # 「당신은 못 한다」이기 때문이다 — 스탭은 기다린다고 이 글을
                # 고칠 수 있게 되지 않는다. 고치려면 의사가 반려해서 자기
                # 차례로 돌아와야 한다.
                raise ApiError(
                    "FORBIDDEN",
                    403,
                    "의사에게 넘긴 뒤에는 의사 계정에서만 고칠 수 있습니다.",
                )

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

    async def submit(self, actor, visit_id: int) -> GuideDocument:
        """스탭이 확인을 마치고 **의사에게 넘긴다** (와이어프레임 S1-11).

        이 자리가 없어서 안내문이 만들어지자마자 원장님 목록에 떴다. 스탭이
        먼저 보는 이유는 원장님 시간을 아끼기 위해서다 — 진료기록이 잘못
        올라갔거나 다른 환자 것이 섞인 것은 스탭이 잡는다.

        의사도 부를 수 있다. 의사가 직접 만들고 바로 승인으로 넘어가는 길을
        막을 이유가 없다 — 승인 자체는 여전히 의사만 한다.
        """
        self._require_staff_or_doctor(actor, "의사 승인 요청은")

        async with in_transaction() as connection:
            guide = await self._lock(actor, visit_id, connection)

            # **이미 넘긴 것을 또 넘기지 않는다.** 두 사람이 같이 눌렀거나
            # 새로고침 뒤 다시 누른 것이고, 원하던 것은 이미 그 상태다.
            # 조용히 통과시키면 승인 이벤트가 두 번 쌓여 누가 언제 넘겼는지가
            # 흐려진다.
            #
            # **반려된 것은 다시 넘길 수 있다.** 그것이 반려의 목적이다 —
            # 고쳐서 다시 올리라는 뜻이니, 재제출을 막으면 반려된 안내문은
            # 영영 그 자리에 갇힌다 (Gomin-art 님 `#176` 리뷰).
            if guide.status not in (GuideStatus.STAFF_REVIEW, GuideStatus.APPROVAL_RETURNED):
                raise ApiError(
                    "GUIDE_NOT_IN_REVIEW",
                    409,
                    "이미 의사에게 넘겼거나 승인된 안내문입니다.",
                )

            # **지난 반려 사유를 지운다.** 스탭 알림에 그대로 뜨는 문장이라,
            # 고쳐서 다시 올렸는데도 남아 있으면 「아직 반려 상태」로 읽힌다.
            # **이력은 지우지 않는다** — 무엇을 왜 고쳤는지는 `GuideEvent` 의
            # RETURNED 줄에 그대로 남아 있다. 지우는 것은 「지금 상태」뿐이다.
            #
            # Tortoise 의 `CharField` 는 `null=True` 오버로드가 없어(`**kwargs: Any`)
            # 비울 수 있다는 것을 타입으로 말할 길이 없다 — 칸은 실제로 nullable 이다.
            guide.status = GuideStatus.APPROVAL_PENDING
            guide.returned_reason = None  # type: ignore[assignment]
            await guide.save(update_fields=["status", "returned_reason", "updated_at"], using_db=connection)
            await GuideEvent.create(
                guide_document=guide,
                event_type=GuideEventType.SUBMITTED,
                actor_id=actor.user_id,
                using_db=connection,
            )
        return guide

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
            guide.scheduled_at = self.send_at(moment)
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
            # **예약도 같은 트랜잭션이다.** 갈라 두면 승인은 됐는데 예약이
            # 빈 건이 생기고, 그 환자만 조용히 아무 문자도 못 받는다.
            await self._schedule_messages(guide, moment, connection)
        return guide

    async def _schedule_messages(self, guide: GuideDocument, moment: datetime, connection) -> None:
        """승인 순간에 **나갈 문자를 전부 세워 둔다** — 와이어프레임 D1-6.

        전에는 `guide.scheduled_at` 하나뿐이라 진료 안내문 한 통만 예약됐다.
        확인 회차와 소진 임박은 담길 데가 없어서, 화면이 「예정」이라 적어도
        실제로는 아무것도 예약돼 있지 않았다.

        **다시 승인해도 두 번 만들지 않는다.** 반려됐다가 다시 올라오는 길이
        있어서(`return_to_staff` → 다시 `approve`), 그때마다 새로 만들면
        환자가 같은 문자를 두 번 받는다. 표의 유니크가 마지막으로 막지만,
        여기서 먼저 본다 — 예외로 막으면 승인 자체가 실패한다.

        **거뒀다가 다시 승인하면 껐던 줄을 되살린다.** 유니크 때문에 새로
        만들 수 없기도 하고, 껐던 것도 기록이라 지우지 않기 때문이다.
        """
        live = await GuideMessage.filter(guide_document_id=guide.guide_document_id).using_db(connection).all()

        # **껐던 줄은 「이미 있다」가 아니다.** 승인을 거두면 예약을 CANCELED 로
        # 꺼 두는데, 그 줄까지 있는 것으로 세면 다시 승인해도 꺼진 채 남는다 —
        # 화면은 「발송 예정」이라 적고 실제로는 아무것도 안 나간다. 유니크가
        # (안내문, 종류) 라 새로 만들 수도 없어서, 여기서 되살린다.
        already = {m.kind for m in live if m.status != GuideMessageStatus.CANCELED}
        revive = {m.kind: m for m in live if m.status == GuideMessageStatus.CANCELED}

        # **시각이 비어 있을 수 있다.** 아래 고리가 `at is None` 이면 건너뛴다 —
        # 진료일을 모르면 확인 회차를 셈할 수 없고, 그때 없는 날짜를 지어내
        # 예약하면 엉뚱한 날 문자가 간다. 주석이 그 사실을 말해야 한다.
        rows: list[tuple[GuideMessageKind, datetime | None]] = []
        if GuideMessageKind.GUIDE not in already:
            rows.append((GuideMessageKind.GUIDE, guide.scheduled_at))

        # 확인 회차는 **진료일** 기준이다. 승인일 기준으로 세면 승인이 하루
        # 늦어질 때 「복약 7일째」가 8일째에 간다 — 환자에게 적는 숫자다.
        visit = await Visit.filter(visit_id=guide.visit_id).using_db(connection).first()
        started = visit.visited_at if visit else moment

        # **스탭이 고른 것을 그대로 예약한다** (와이어프레임 S1-14).
        #
        # 예전에는 회차도 시각도 코드에 박힌 값(`_CHECK_ROUNDS` · `CHECK_HOUR`)
        # 이었다. 화면에서 「한 달 뒤」를 켜도 예약은 안 생겼고, 시각을 오후
        # 2시로 바꿔도 10시에 잡혔다 — **고른 것과 나가는 것이 갈렸다.**
        #
        # 설정 행이 없는 회차는 기본값이다(`_DEFAULT_ON`).
        plan = {
            r.kind: r
            for r in await GuideMessageSetting.filter(guide_document_id=guide.guide_document_id)
            .using_db(connection)
            .all()
        }

        def wanted(kind: GuideMessageKind) -> bool:
            if kind in FIXED_ON:
                return True  # 일주일 뒤는 끌 수 없다
            row = plan.get(kind)
            return _DEFAULT_ON[kind] if row is None else row.enabled

        hour = guide.check_hour

        for kind, days in CHECK_DAYS.items():
            if kind in already or not wanted(kind):
                continue
            rows.append((kind, self.check_at(started, days, hour)))

        # 소진 임박은 **처방일수를 알아야** 셈할 수 있다. 판독이 못 읽었으면
        # 만들지 않는다 — 지어낸 날짜로 예약하면 엉뚱한 날 문자가 간다.
        course = await self._course_days(guide.visit_id, connection)
        if course and GuideMessageKind.RUN_OUT not in already and wanted(GuideMessageKind.RUN_OUT):
            run_out = plan.get(GuideMessageKind.RUN_OUT)
            before = RUN_OUT_BEFORE_DAYS if run_out is None or run_out.days_before is None else run_out.days_before
            rows.append((GuideMessageKind.RUN_OUT, self.check_at(started, course - before, hour)))

        for kind, at in rows:
            if at is None:
                continue
            back = revive.get(kind)
            if back is not None:
                back.status = GuideMessageStatus.SCHEDULED
                back.scheduled_at = at
                back.failure_code = None
                await back.save(
                    update_fields=["status", "scheduled_at", "failure_code", "updated_at"],
                    using_db=connection,
                )
                continue
            await GuideMessage.create(
                guide_document=guide,
                kind=kind,
                scheduled_at=at,
                using_db=connection,
            )

    @staticmethod
    async def _course_days(visit_id: int, connection) -> int | None:
        """처방일수 — 판독이 확정한 값에서 읽는다.

        **확정된 것만 본다.** 스탭이 아직 확인하지 않은 값으로 발송일을 잡으면,
        고친 뒤에도 옛 날짜로 예약된 채 남는다.
        """
        row = (
            await OcrField.filter(
                ocr_result__ocr_job__visit_id=visit_id,
                field_type="DURATION_DAYS",
                is_confirmed=True,
            )
            .using_db(connection)
            .first()
        )
        if row is None or not row.value:
            return None
        try:
            days = int(str(row.value).strip())
        except ValueError:
            # 「84일」처럼 단위가 붙어 오면 숫자만 뗀다. 그래도 안 되면 포기한다 —
            # 지어낸 값으로 예약하는 것보다 안 만드는 편이 낫다.
            digits = "".join(ch for ch in str(row.value) if ch.isdigit())
            if not digits:
                return None
            days = int(digits)
        return days if days > 0 else None

    @staticmethod
    def check_at(started: datetime, days: int, hour: int | None = None) -> datetime:
        """확인 · 소진 문자가 나갈 시각 — **병원 시간으로** 그날 그 시각.

        안내문(18:00)과 다르다. 안내문은 진료 당일 저녁에 받아야 차분히 읽고,
        확인 문자는 며칠 뒤 낮에 오는 편이 낫다 (S1-14 「오전 10:00」).
        시각은 스탭이 고른다 — 안 주면 기본값(10시)이다.

        `send_at` 과 같은 이유로 **시간대를 옮겨 판단한다** — 안 옮기면 받은
        값의 시간대에서 10시가 되고, 운영(UTC)에서는 한국 저녁 7시가 된다.
        """
        local = started.astimezone(config.TIMEZONE)
        at = CHECK_HOUR if hour is None else hour
        return (local + timedelta(days=days)).replace(hour=at, minute=0, second=0, microsecond=0)

    # ── 문자 설정 (와이어프레임 S1-14) ────────────────────────────────

    async def message_plan(self, actor, visit_id: int) -> dict:
        """이 진료의 문자 회차 설정.

        **행이 없는 회차는 기본값이다.** 화면을 한 번도 안 만진 진료까지 미리
        다섯 줄을 채우지 않는다 — 안 만졌다는 것과 기본값으로 정했다는 것은
        여기서 같은 뜻이다.
        """
        guide = await self.get(actor, visit_id)
        rows = {r.kind: r for r in await GuideMessageSetting.filter(guide_document_id=guide.guide_document_id)}

        rounds = []
        for kind in (
            GuideMessageKind.CHECK_D7,
            GuideMessageKind.CHECK_D15,
            GuideMessageKind.CHECK_D30,
            GuideMessageKind.RUN_OUT,
        ):
            row = rows.get(kind)
            rounds.append(
                {
                    "kind": kind.value,
                    "enabled": _DEFAULT_ON[kind] if row is None else row.enabled,
                    "body": None if row is None else row.body,
                    "days_before": (
                        RUN_OUT_BEFORE_DAYS
                        if kind is GuideMessageKind.RUN_OUT and (row is None or row.days_before is None)
                        else (None if row is None else row.days_before)
                    ),
                    "fixed": kind in FIXED_ON,
                }
            )
        return {"check_hour": guide.check_hour, "rounds": rounds}

    async def save_message_plan(self, actor, visit_id: int, plan) -> dict:
        """문자 설정을 저장한다 — 「이 환자만 적용」.

        스탭도 저장한다. 원문의 「저장은 의사 계정만」은 **의원 템플릿**(D2-5)
        이야기고, 스탭은 「이 환자만 적용」까지 할 수 있다고 같은 줄이 적는다.

        고칠 수 있는 때는 안내문 본문과 **같은 규칙**이다 — 스탭 확인 중이면
        스탭이, 의사에게 넘어간 뒤로는 의사가. 두 규칙이 갈리면 「문구는
        고쳐지는데 본문은 403」 같은 화면이 나온다.

        승인 뒤(`SCHEDULED_TO_SEND`)에는 막는다. 그때 고치면 **이미 잡힌 예약과
        어긋난다** — 화면에는 새 문구가, 예약에는 옛 문구가 남는다. 고치려면
        승인을 거두고(`unapprove`) 고친 뒤 다시 승인한다.
        """
        self._require_staff_or_doctor(actor, "문자 설정은")

        async with in_transaction() as connection:
            guide = await self._lock(actor, visit_id, connection)

            # **반려된 것도 스탭 차례다.** 본문 수정과 같은 규칙이어야 한다 —
            # 반려 사유가 「문자 회차를 고쳐 주세요」인 순간 여기서만 막히면,
            # 스탭은 본문은 고쳐지는데 문자 설정은 409 를 보는 화면을 만난다.
            # 본문 쪽만 열었다가 이 자리를 빠뜨렸다.
            if guide.status in (GuideStatus.STAFF_REVIEW, GuideStatus.APPROVAL_RETURNED):
                self._require_staff_or_doctor(actor, "문자 설정은")
            elif guide.status is GuideStatus.APPROVAL_PENDING:
                self._require_doctor(actor)
            else:
                raise ApiError(
                    "GUIDE_NOT_PENDING",
                    409,
                    "확인·승인 요청 상태에서만 문자 설정을 고칠 수 있습니다.",
                )

            hour = int(getattr(plan, "check_hour", CHECK_HOUR))
            if hour not in CHECK_HOURS:
                raise ApiError("BAD_CHECK_HOUR", 422, "고를 수 없는 시각입니다.")
            guide.check_hour = hour
            await guide.save(update_fields=["check_hour", "updated_at"], using_db=connection)

            for item in getattr(plan, "rounds", []) or []:
                kind = GuideMessageKind(item.kind)
                await GuideMessageSetting.update_or_create(
                    guide_document_id=guide.guide_document_id,
                    kind=kind,
                    defaults=self._round_values(kind, item),
                    using_db=connection,
                )

        return await self.message_plan(actor, visit_id)

    @staticmethod
    def _round_values(kind: GuideMessageKind, item) -> dict:
        """회차 한 줄이 담길 모양. **한 줄을 재는 규칙을 여기 모은다** —
        저장 함수 안에 두었더니 트랜잭션·권한·검사가 한 덩이가 됐다.
        """
        # **일주일 뒤는 끌 수 없다** — 화면이 잠그지만 요청은 그냥 온다.
        enabled = True if kind in FIXED_ON else bool(item.enabled)

        body = item.body
        if body is not None:
            body = body.strip()
            if not body:
                # 비운 것은 「기본 문구로 되돌린다」는 뜻이다.
                body = None
            elif len(body) > MESSAGE_BODY_MAX:
                raise ApiError("BODY_TOO_LONG", 422, "문구가 너무 깁니다.")

        days_before = None
        if kind is GuideMessageKind.RUN_OUT:
            days_before = RUN_OUT_BEFORE_DAYS if item.days_before is None else int(item.days_before)
            if not RUN_OUT_BEFORE_MIN <= days_before <= RUN_OUT_BEFORE_MAX:
                raise ApiError("BAD_DAYS_BEFORE", 422, "소진 며칠 전인지가 범위를 벗어났습니다.")

        return {"enabled": enabled, "body": body, "days_before": days_before}

    async def unapprove(self, actor, visit_id: int) -> GuideDocument:
        """승인을 **거둔다** — 승인했는데 잘못된 것을 발견했을 때.

        의사만 한다. 승인한 사람이 거두는 것이라 같은 권한이다.

        **이미 나간 문자가 있으면 거두지 않는다.** 환자가 이미 받았는데
        「승인 안 한 것」으로 되돌리면, 화면에 안 보이는 글이 환자 손에 있는
        상태가 된다 — 그때 할 일은 철회가 아니라 새 안내를 보내는 것이다.

        거두면 **예약된 문자를 끈다.** 줄을 지우지 않고 `CANCELED` 로 둔다 —
        껐다는 것도 기록이다. 나중에 「왜 안 갔지」를 물을 때 답이 있어야 한다.

        상태는 `APPROVAL_PENDING` 으로 돌아간다. 스탭까지 되돌리지 않는 이유는,
        **잘못을 본 사람이 의사이기 때문**이다 — 스탭에게 넘기려면 사유를 적어
        `return_to_staff` 로 보낸다.
        """
        self._require_doctor(actor)

        async with in_transaction() as connection:
            guide = await self._lock(actor, visit_id, connection)

            if guide.status is not GuideStatus.SCHEDULED_TO_SEND:
                raise ApiError("GUIDE_NOT_SCHEDULED", 409, "승인된 안내문만 철회할 수 있습니다.")

            sent = (
                await GuideMessage.filter(
                    guide_document_id=guide.guide_document_id,
                    status=GuideMessageStatus.SENT,
                )
                .using_db(connection)
                .exists()
            )
            if sent:
                raise ApiError(
                    "GUIDE_ALREADY_SENT",
                    409,
                    "이미 환자에게 나간 문자가 있어 철회할 수 없습니다. 새 안내를 보내 주세요.",
                )

            guide.status = GuideStatus.APPROVAL_PENDING
            guide.approved_by = None
            guide.approved_at = None
            guide.scheduled_at = None
            await guide.save(
                update_fields=["status", "approved_by", "approved_at", "scheduled_at", "updated_at"],
                using_db=connection,
            )

            # 예약을 끈다. **지우지 않는다** — 껐다는 것도 기록이다.
            await (
                GuideMessage.filter(
                    guide_document_id=guide.guide_document_id,
                    status=GuideMessageStatus.SCHEDULED,
                )
                .using_db(connection)
                .update(status=GuideMessageStatus.CANCELED)
            )

            await GuideEvent.create(
                guide_document=guide,
                event_type=GuideEventType.UNAPPROVED,
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
    async def _doctor_copies(
        hospital_id: int, doctor_id: int | None, prescription_set: PrescriptionSet | None
    ) -> dict[CautionSectionKey, str]:
        """이 의사가 이 처방에 대해 고쳐 둔 문구를 **갈래별로.**

        빈 사전이면 부르는 쪽이 세트별 승인 문구로, 그것도 없으면 기본 문구로
        내려간다. 갈래마다 따로 내려간다 — 담당이 주의사항만 고치고 스탭이
        복약지도만 고쳤으면 **둘 다 나가야 한다.**

        **고칠 수 있는 갈래만 읽는다**(`guide_defaults.EDITABLE_SECTIONS`).
        `emergency` 는 `locked=True` 로 사람이 못 고치는 글이라(KEY-150)
        여기서 읽어 버리면 그 표에 행이 생기는 날 **응급 문장이 조용히
        바뀐다.** 목록을 잎 모듈에 둔 까닭이 이것이다 — 설정이 넓힌 갈래를
        생성이 안 따라가면 「고칠 수 있는데 안 나가는」 갈래가 생긴다.

        **세트는 부르는 쪽이 찾아 넘긴다.** `Prescription.prescription_set` 은
        스냅샷 문자열이라(KEY-137) 이름으로 찾아야 하는데, 한 진료에서 이것을
        담당·의원 공통으로 두 번 부르므로 안에서 찾으면 같은 `SELECT` 가
        되풀이된다 (`#191` 리뷰, 2heej).

        🚨 **`doctor_id` 에 `visit.doctor_id` 말고 다른 번호를 넣지 마라.**

        여기서 읽은 글은 **담당 의사 이름으로 환자에게 나간다.** 한동안
        「만든 사람」으로 내려가는 층이 있었다가 리뷰(2heej)에서 잡혔다 —
        `generate()` 는 담당이 아니어도 같은 의원의 아무 의사·스탭이나 부를
        수 있다. `_require_staff_or_doctor` 는 역할만 보고, 진료 조회도
        `hospital_id` 로만 범위를 잡는다.

            의사 B 가 세트 S 문구를 고쳐 둔다
            담당 의사 A 는 S 를 고친 적이 없다
            B 가 (담당이 아닌데) A 의 진료로 generate 를 부른다
            → **B 가 쓴 글이 A 이름으로 환자에게 나간다**

        `doctor_id=None` 은 그것과 다르다 — **의원 공통**을 뜻하고, 없다는
        뜻이 아니다.

        트랜잭션 밖에서 읽는다. 락 보유 시간을 늘릴 이유가 없다.
        """
        if prescription_set is None:
            return {}

        rows = await DoctorGuideCopy.filter(
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            prescription_set_id=prescription_set.prescription_set_id,
            section_key__in=list(guide_defaults.EDITABLE_SECTIONS),
        )
        return {row.section_key: row.body for row in rows}

    @staticmethod
    def _require_staff_or_doctor(actor, subject: str = "안내 생성은") -> None:
        """`admin` 단독은 진료 자료에 손대지 못한다.

        `GUIDE_DRAFT` · `PATIENT_READ` 모두 staff·doctor 에게만 열려 있다
        (`app/tests/rbac/matrix.py`). `admin` 은 의원 운영 권한이지 진료 화면을
        여는 역할이 아니다.

        **읽기에도 건다.** 안내문 응답에는 환자 이름·차트번호·생년월일과 네
        갈래 전문이 실린다 — 「보기만 하는 것」이 아니다 (KEY-168).
        """
        if not ({"staff", "doctor"} & set(actor.roles)):
            raise ApiError("FORBIDDEN", 403, f"{subject} 스탭 또는 의사 계정만 할 수 있습니다.")

    @staticmethod
    def _is_doctor(actor) -> bool:
        """`_require_doctor` 와 같은 판정을 **막지 않고 묻기만** 한다.

        고칠 수 있는지를 상태와 함께 봐야 하는 자리가 있어서다 — 스탭 확인
        중이면 스탭이, 승인 요청 중이면 의사가 고친다. 두 곳이 서로 다른
        기준을 쓰면 한쪽만 고쳐진다.
        """
        return "doctor" in actor.roles

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
    def send_at(moment: datetime) -> datetime:
        """**병원 시간으로** 오늘 18:00. 이미 지났으면 내일 같은 시각이다.

        이름이 열려 있는 것은 `scripts/seed.py` 가 같은 규칙을 써야 하기 때문이다.
        시드가 예약시각을 따로 계산하면 두 곳이 어긋나고, 어긋난 쪽이 조용히
        환자에게 나간다 (이희진 님 `#158` ①).

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
