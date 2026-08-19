# KEY-60 OCR API 계약 구현 기록

## 엔드포인트

| Method | Path | 용도 |
| --- | --- | --- |
| `POST` | `/api/v1/documents/{document_id}/ocr` | 문서 OCR 작업 생성 |
| `GET` | `/api/v1/ocr/jobs/{ocr_job_id}` | 처리 상태·진행률 조회 |
| `GET` | `/api/v1/ocr/jobs/{ocr_job_id}/result` | 전체 텍스트와 구조화 결과 조회 |
| `GET` | `/api/v1/ocr/jobs/{ocr_job_id}/fields` | 구조화 필드·신뢰도·후보 조회 |
| `PATCH` | `/api/v1/ocr/fields/{ocr_field_id}` | 수정값 또는 후보 선택과 확정 |

수정 API는 `base_version`을 요구하고 버전이 달라지면 `409 VERSION_CONFLICT`를
반환합니다. 이미 확정된 필드는 다시 수정하지 않습니다. 타 병원 식별자는 존재
여부를 숨기기 위해 `404 NOT_FOUND`로 통일합니다.

## 권한·개인정보

- `staff` 또는 `doctor` 역할만 접근할 수 있습니다. `admin` 단독 사용자는 차단합니다.
- 모든 ORM 조회에 인증 사용자의 `hospital_id` 범위를 적용합니다.
- 문서 소유권은 문서·진료·병원이 모두 일치하는 권위 있는 업로드 저장소에서
  검증합니다. 해당 저장소가 연결되기 전에는 작업 생성을 기본 차단합니다.
- 작업 생성은 진료 행을 잠근 트랜잭션 안에서 소유권과 기존 `PROCESSING` 작업을
  확인해 동시 요청의 중복 생성을 막습니다.
- 원문과 필드값을 로그에 기록하지 않습니다.
- 테스트 데이터는 `합성 추출값`, `합성 수정값`만 사용합니다.
- 승인 이후 원문 파기는 KEY-59의 `purge_raw_text`와 승인 트랜잭션을 연결해야 합니다.

## 현재 통합 제한

현재 `develop`의 `User` 모델에는 KEY-9/KEY-21의 `hospital_id`와 `roles`가 아직
병합되지 않았습니다. 이 값이 없으면 서버는 기본 차단합니다. 직원 모델이 병합될
때 `get_ocr_actor`를 실제 직원 컨텍스트에 연결해야 합니다. KEY-73의 직원 PK인
`staff_id`와 기존 `User.id`를 모두 인식하되 최종 통합 후 직원 컨텍스트 하나로
고정합니다.

KEY-53의 권위 있는 문서 모델·저장소가 아직 없으므로 기본 소유권 검증기는 작업
생성을 `404`로 차단합니다. KEY-53 통합 시 문서의 `document_id`, `visit_id`,
`hospital_id`를 같은 트랜잭션에서 검증하고 잠그는 구현을 주입해야 합니다.

OCR 엔진 실행은 AI worker가 `ocr_job`의 `PROCESSING` 작업을 가져가 결과를 쓰는
경계입니다. 본 API는 작업 생성과 결과 검수 계약을 담당하며 OCR 추론 구현이나
문서 업로드 저장소는 포함하지 않습니다.

최신 Notion에서 삭제 상태인 재판독 API와 일괄 결과 수정 API는 구현하지 않았습니다.
KEY-60에 명시된 필드 단위 조회·수정 계약만 유지했습니다.
