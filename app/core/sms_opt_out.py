"""문자 수신 거부 판정 — 발송 게이트·문서 업로드·안내 생성이 공유한다.

세 곳 모두 「이 진료의 환자가 수신을 거부했는가」를 거의 같은 모양으로
물었다(2heej 리뷰, KEY-355) — `Visit.filter(...).select_related("patient")
.first()` 후 `sms_opted_out_at` 확인. 이 판정 자체가 「기준이 여러 곳에
흩어지면 갈린다」는 이 PR이 고치려던 문제와 같은 종류라, 한 곳으로 모았다.
나중에 조건이 바뀌면(예: 거부 후 유예 기간을 둔다) 여기 한 곳만 고치면
된다.
"""

from app.models.visits import Visit


def is_opted_out(visit: Visit) -> bool:
    """`visit.patient`가 이미 `select_related`로 로드돼 있어야 한다.

    호출부가 각자 다른 방식으로 반응한다 — 발송 게이트는 HELD로 붙들고,
    업로드·생성은 명시적 오류로 거절한다. 그래서 예외를 던지는 대신
    판정만 돌려주고 처리는 호출부에 맡긴다.
    """
    return visit.patient.sms_opted_out_at is not None
