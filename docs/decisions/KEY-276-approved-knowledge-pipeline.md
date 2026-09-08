# KEY-276 승인 의료지식 적재·검색 파이프라인

## 목적과 안전 경계

이 작업은 승인 의료지식을 private MinIO에 보관하고 MySQL 8에 버전·청크·임베딩을
저장한 뒤 Python cosine으로 검색하는 경계까지만 만든다. 안내문 생성, 챗봇,
환자 화면에는 연결하지 않는다. 생성 연결은 KEY-277의 별도 범위다.

선행 정본인 `KEY-82-rag-search-poc.md`는 Pilot에서 로컬 임베딩만 허용한다.
따라서 Jira 본문의 “OpenAI Embeddings” 표현보다 선행 안전 결정을 우선하여
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`의 고정 revision과
384차원을 사용한다. 외부 임베딩 전송은 보안·의료 검토가 별도로 승인되기 전까지
구현하거나 활성화하지 않는다.

## 저장 구조

- `knowledge_document`: 제목, 기관, 원문 URL, 병원 범위, 입력 유형의 고정 식별자
- `knowledge_version`: 원문 hash, private object key, 라이선스, 검증일, 승인 상태
- `knowledge_chunk`: 800자 이하 정규화 텍스트, 위치·페이지·OCR 좌표, 로컬 임베딩
- `knowledge_ingestion_attempt`: 원문 없는 실행 상태, 안전한 오류 코드, 재시도 시각

문서 버전은 `DRAFT → APPROVED → DEPRECATED`로 이동한다. 현재 승인본에만
`current_approved_key=document_id`를 채우고 unique 제약을 걸어 문서당 현행 승인본이
두 개 생기지 않게 한다. 같은 문서·버전에 다른 바이트를 덮어쓰는 요청은
`VERSION_CONTENT_MISMATCH`로 막는다. 같은 바이트 재처리는 청크를 중복 생성하지 않는다.

## 입력 계약

세 입력은 `KnowledgeIngestionService.ingest()` 하나로 들어간다.

1. 텍스트 PDF: `pypdf`로 페이지별 텍스트와 페이지 번호를 보존한다.
2. 스캔/이미지: Worker의 CLOVA 어댑터가 텍스트, 좌표, 평균 신뢰도를 넘긴다.
3. 구조화 API: 원본 JSON snapshot을 MinIO에 보관하고 정렬된 `경로 = 값` 행으로 정규화한다.

원문/snapshot은 `approved-knowledge` 버킷의
`knowledge/{scope}/{source_key}/{version}/{sha256}.source`에 둔다. object key는 URL이
아니며 presigned/public URL을 반환하는 기능도 두지 않는다. `minio_init.sh`는 버킷을
만들 때마다 익명 정책을 `none`으로 재설정한다.

## 승인과 검색 규칙

승인은 다음을 모두 만족해야 한다.

- A등급 출처이며 기관과 원문 URL이 있다.
- 라이선스 확인이 끝났다.
- 적재 실행이 `READY`이고 청크가 있다.
- 검토 만료일을 이미 지난 자료가 아니다.

검색은 승인 상태, 현행 버전, A등급, 라이선스, 검증일, 병원 범위, section, 검토
유효기간, 고정 임베딩 모델·revision·차원을 모두 검사한다. 결과에는 문서/청크 ID,
기관, URL, 버전, 검증일, 병원 범위, score와 `approved_current` 검증 상태를 담는다.
한 건도 없으면 텍스트를 만들지 않고 `NO_VERIFIED_CONTEXT`만 반환한다.

## 실행과 검증

### 실제 자료 적재

노션 「RAG 전환 위한 서치」 하단에서 지정한 실제 입력은 다음 다섯 건이다.

| 입력 | 출처 | 적재 방식 |
|---|---|---|
| 2023 PCOS 국제 가이드라인 | Monash University·International PCOS Network | 텍스트 PDF |
| ESHRE guideline: endometriosis 공개 논문 | Human Reproduction Open | 텍스트 PDF |
| 의약품 제품 허가정보 | 식품의약품안전처 OpenAPI | JSON snapshot |
| DUR 성분정보 | 식품의약품안전처 OpenAPI | JSON snapshot |
| DUR 품목정보 | 식품의약품안전처 OpenAPI | JSON snapshot |

원문 PDF와 실제 JSON snapshot은 저장소에 넣지 않는다. 로컬 manifest는
`key276-ingestion-manifest.local.json` 이름으로 만들며 `.gitignore`가 이를 막는다.
형식은 `docs/data/key276-ingestion-manifest.example.json`을 복사해 사용한다. 식약처
인증키는 manifest·argv·문서에 적지 않고 실행 프로세스 환경변수로만 넘긴다. 세 API의
키가 같으면 `MFDS_SERVICE_KEY` 하나를 쓰고, 다르면 아래 데이터셋별 변수를 사용한다.

```bash
cp docs/data/key276-ingestion-manifest.example.json key276-ingestion-manifest.local.json

# PDF만 검토 대기 상태로 적재
DB_HOST=127.0.0.1 \
KNOWLEDGE_MINIO_ENDPOINT=http://127.0.0.1:9000 \
uv run python scripts/ingest_approved_knowledge.py \
  key276-ingestion-manifest.local.json --only=text_pdf

# 식약처 3종 snapshot만 검토 대기 상태로 적재
MFDS_DRUG_PRODUCT_APPROVAL_SERVICE_KEY='실행할 때만 주입' \
MFDS_DUR_INGREDIENT_SERVICE_KEY='실행할 때만 주입' \
MFDS_DUR_PRODUCT_SERVICE_KEY='실행할 때만 주입' \
DB_HOST=127.0.0.1 \
KNOWLEDGE_MINIO_ENDPOINT=http://127.0.0.1:9000 \
uv run python scripts/ingest_approved_knowledge.py \
  key276-ingestion-manifest.local.json --only=mfds_api
```

기본 실행 결과는 `ready_for_review`다. `approve: true`인 A등급 자료라도
`--approved-by`를 명시한 경우에만 현재 승인본으로 전환된다. 즉 자료 적재와 의료
검수 승인을 같은 행위로 취급하지 않는다.

2026-09-08 로컬 실제 적재 확인에서는 두 공개 PDF가 private MinIO에 저장됐고,
MySQL에 문서 2건·버전 2건·검색 청크 1,351건·READY 실행 2건이 생성됐다. 원문,
로컬 경로, 자격증명은 실행 출력과 이 문서에 기록하지 않았다. 식약처 snapshot은
인증키를 로컬 프로세스에 주입한 뒤 같은 명령으로 별도 적재한다.

```bash
uv sync --group app --group dev
DB_HOST=127.0.0.1 uv run aerich upgrade
DB_HOST=127.0.0.1 uv run pytest -q \
  app/tests/rag/test_key82_knowledge_search.py \
  app/tests/rag/test_key276_approved_knowledge_pipeline.py \
  app/tests/rag/test_key276_real_sources.py
```

환경변수 `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `KNOWLEDGE_MINIO_ENDPOINT`,
`KNOWLEDGE_MINIO_BUCKET`은 `.env`/배포 secret에서만 주입한다. 로그·오류 코드·커밋에는
자격증명이나 원문을 남기지 않는다.
