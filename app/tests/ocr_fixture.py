"""판독이 **끝난 상태**를 한 곳에서 만든다 — KEY-172.

세 곳이 같은 일을 따로 하고 있었다.

    app/tests/blocking/accounts.py            make_ocr
    app/tests/guide_apis/test_guide_generate  attach_confirmed_ocr
    app/tests/e2e/test_key152_walking_skeleton  운영 코드를 직접 부름(`#114`)

앞의 둘은 `OcrJob` · `OcrResult` · `OcrField` 를 손으로 만들었다. 그래서
`OcrDocumentText` 를 안 만들고, `job.completed_at` 도 안 채우고, 모델 이름도
제각각이었다 — **운영이 실제로 만드는 모양과 조금씩 달랐다.** 스키마가 바뀌면
세 사본을 다 찾아 고쳐야 하고, 하나를 놓치면 그 검사만 옛 모양으로 남는다.

여기서는 **운영 코드를 그대로 부른다**(`app.ocr.service.seed_fixture_result`).
업로드 경로가 판독을 끝낼 때 타는 바로 그 함수다. 그래서 완료된 판독의 모양이
검사와 운영에서 어긋날 자리가 없다.

`#114`(KEY-152)가 e2e 에서 먼저 이 방향으로 갔고, 이 파일이 나머지 둘을 데려온다.
"""

from dataclasses import dataclass

from tortoise.transactions import in_transaction

from app.models.documents import MedicalDocument
from app.models.ocr import OcrDocumentType, OcrField, OcrJob, OcrJobStatus
from app.ocr.service import seed_fixture_result


@dataclass(frozen=True)
class CompletedOcr:
    """끝난 판독 하나가 남긴 식별자들."""

    job_id: str
    field_id: int
    document_id: int


async def complete_ocr(
    *,
    hospital_id: int,
    visit_id: int,
    job_id: str,
    requested_by: int,
    confirmed_by: int | None = None,
) -> CompletedOcr:
    """그 진료에 **끝난 판독** 한 건을 붙인다.

    문서 한 장을 올린 것으로 치고, 운영과 같은 완료 경로를 태운다.
    `confirmed_by` 를 주면 나온 항목을 확정까지 한다 — 안내 생성은 확정된
    항목을 요구하므로 그쪽 검사가 쓴다.

    업로드 라우트를 타지 않는 것은 이 헬퍼를 쓰는 검사들이 재는 것이 「어떻게
    올라오는가」가 아니기 때문이다. e2e 는 실제 업로드를 태우고 그 뒤에 같은
    운영 함수를 부른다 — 경계가 다르다.
    """
    document = await MedicalDocument.create(
        hospital_id=hospital_id,
        visit_id=visit_id,
        document_type=OcrDocumentType.EMR,
        file_path=f"synthetic/{job_id}.pdf",
        file_size=1024,
        mime_type="application/pdf",
        uploaded_by=requested_by,
    )
    job = await OcrJob.create(
        ocr_job_id=job_id,
        hospital_id=hospital_id,
        visit_id=visit_id,
        status=OcrJobStatus.PROCESSING,
        requested_by=requested_by,
    )
    async with in_transaction() as connection:
        await seed_fixture_result(job, [(document.document_id, OcrDocumentType.EMR)], connection)

    field = await OcrField.get(ocr_result__ocr_job=job)
    if confirmed_by is not None:
        field.is_confirmed = True
        field.confirmed_by = confirmed_by
        await field.save(update_fields=("is_confirmed", "confirmed_by"))

    return CompletedOcr(job_id=job.ocr_job_id, field_id=field.ocr_field_id, document_id=document.document_id)
