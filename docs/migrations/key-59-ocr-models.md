# KEY-59 OCR 모델 마이그레이션

## 범위

- `ocr_job`: 병원·진료 범위, 처리 상태와 진행률
- `ocr_job_document`: 한 OCR 작업에 포함된 업로드 문서 식별자와 유형
- `ocr_result`: 모델/버전 및 수정·확정 감사 메타데이터
- `ocr_document_text`: 문서별 전체 OCR 텍스트와 파기 시각
- `ocr_field`: 추출값, 수정값, 신뢰도, 필드 버전과 검수 메타데이터
- `ocr_field_candidate`: 복수 판독 후보, 순위, 신뢰도, 검사일과 선택 여부

원문은 S1-6~S1-9 검수 중에만 사용합니다. 승인 처리에서는 `raw_text=NULL`과
`raw_text_purged_at`을 같은 트랜잭션에 기록해야 하며, 구조화 필드와 감사
메타데이터만 보존합니다.

OCR이 필수 항목을 읽지 못해도 해당 `field_type`의 `ocr_field` 행은 만들고
`extracted_value=NULL`로 저장합니다. 화면과 API는 행이 없는 경우가 아니라 이
명시적 누락 값을 사용해 S1-7의 점선·물음표 상태를 표시합니다. 저신뢰 임계값은
모델에 고정하지 않으며 KEY-60 서비스/API의 서버 설정이 판정 결과를 제공합니다.

`ocr_job_id`는 환자·진료·안내 리소스 ID가 아니라 AI 워커가 발급하는 불투명 작업
식별자이므로 문자열을 유지합니다. 클라이언트는 값을 해석하거나 조립하지 않습니다.
`created_at`은 큐 등록 시각이고, nullable `started_at`은 워커가 실제 처리를 시작할
때 기록합니다.

`ocr_job.hospital_id == visit.hospital_id`는 KEY-60 서비스가 인증 컨텍스트와 함께
검증합니다. Hospital·Staff FK가 생기는 KEY-73 이후 모델 관계로 먼저 정의하고
Aerich가 복합 FK를 생성하기 전까지 마이그레이션 SQL을 손으로 수정하지 않습니다.

## 의존성과 적용

마이그레이션은 외래키 의존 순서에 맞춰 작업 → 결과·작업 문서 → 문서 원문 →
필드 → 후보의 다섯 단계로 Aerich가 생성합니다. KEY-31의 `visit` 테이블을
참조하므로 KEY-31을 먼저 적용한 뒤:

```bash
uv run aerich upgrade
```

적용 후 `ocr_job.visit_id` 외래키, 병원/상태 인덱스와 필드/후보 관계를
확인합니다. 신뢰도·진행률·버전·후보 순위의 범위는 DTO와 모델 검증을 함께
적용하며, 생성 마이그레이션 SQL에 지원되지 않는 CHECK를 손으로 추가하지 않습니다.
합성 데이터만 사용하고 원문·필드값을 운영 로그에 출력하지 않습니다.

## 롤백

KEY-60 API가 참조하지 않는 상태에서만 다음을 실행합니다.

```bash
uv run python -m aerich.cli downgrade --version 6 --yes
uv run python -m aerich.cli downgrade --version 5 --yes
uv run python -m aerich.cli downgrade --version 4 --yes
uv run python -m aerich.cli downgrade --version 3 --yes
uv run python -m aerich.cli downgrade --version 2 --yes
```

후보 → 필드 → 문서 원문 → 결과 → 작업 순으로 삭제됩니다. 운영 데이터가 있는
경우 롤백 전에 암호화 백업과 보존 정책 승인이 필요합니다.
