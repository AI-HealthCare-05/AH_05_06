# 안내문 RAG 하이브리드 평가

안내문 생성에 사용할 검색 후보의 회수·순위를 비교하는 합성 실험이다. 서비스 검색 구현을 교체하거나 생성 근거를 승인하지 않는다. 별도 Jira 없이 진행한 로컬 실험을 사용자 요청으로 공유한다.

## 평가 대상과 정답표

| 파일 | 내용 | 상태 |
|---|---|---|
| `hybrid-fixture.json` | 합성 문서 16개·질의 12개 | `relevant`에 정답 문서 ID 기록 |
| `alternative-fixture-queries.json` | 표현 차이·근거 없는 질의 8개 | `relevant=[]`는 허용 코퍼스에 정답 없음 |
| `real-cases.json` | PCOS·자궁내막증 안내 항목별 8개 평가 틀 | 모두 의료 검토 대기, 문서 버전·정답 청크·검토자 미입력 |
| `model-comparison/results.json` | 질의별 후보·점수·모델 버전·코드 해시 | 합성 데이터 실측 결과 |
| `model-comparison/report.md` | 사람이 읽는 비교표 | 위 결과의 요약 |

기존 `docs/data/key82-rag-poc-evaluation.json`의 6건도 합성 청크 기반 정답표다. 이 실험은 실제 승인 문서 정답표를 완성했다고 주장하지 않는다. `real-cases.json`은 실행기에 연결하지 않았으며, 빈 정답을 근거 없음으로 취급해서는 안 된다.

## 비교 방식

- 고정 MiniLM Dense + 단순 BM25 / Kiwi 한국어 BM25, 각각에 BGE reranker를 추가한 네 조합을 비교한다. BM25 단독은 형태소 분석 효과를 분리하는 보조 비교다.
- 기존 제품의 승인·현재 버전·A등급·이용조건·병원·섹션 필터와 충돌 검사를 호출한다. 미승인 등 금지 후보를 생성 모델에 전달하지 않는다.
- Hybrid 공통 설정: Dense 후보 임계값 0, BM25 양수 점수, RRF 상수 60, 검색별 후보 최대 10, 융합 후 재순위 후보 최대 10, 최종 최대 3.
- 임계값 0은 후보 회수 실험값이다. 기존 운영 유사도 0.72를 바꾸자는 제안이 아니며 RRF 점수는 cosine이나 근거 채택 확률이 아니다.
- Kiwi는 NFKC·소문자 정규화 후 명사·동사·형용사 및 MAG/SL/SN/XR을 사용한다. 정답 기반 동의어 사전을 추가하지 않았다.
- BGE reranker는 동일한 질의·문서 쌍의 점수를 두 조합에 재사용한다. 순위만 변경하고 거절 임계값은 적용하지 않는다.
- `hybrid_search.py`의 가중합은 앞선 탐색을 재현할 수 있는 보조 함수이며 이번 모델 비교는 RRF만 사용한다.

## 재실행

저장소 루트에서 실행한다. Python과 앱 의존성은 저장소의 `uv.lock`을 사용한다. Kiwi는 평가 전용 추가 의존성이며 서비스 의존성은 변경하지 않는다.

```bash
uv sync --frozen --group app --group ai --group dev

# DB·모델·Kiwi 없이 검색/융합 경계 17개 검사
PYTHONPATH=. uv run --no-sync python experiments/guide_rag/test_hybrid.py

# 최초 1회만 네트워크 사용: 고정 revision의 공개 모델(수 GB)을 받는다.
uv run --no-sync python experiments/guide_rag/model-comparison/prepare_models.py \
  --reranker-path /tmp/guide-rag-models/reranker

# 모델 로딩/질의 실행은 로컬 전용. uv의 의존성 준비에는 네트워크가 필요할 수 있다.
uv run --no-sync --with kiwipiepy==0.23.2 --with kiwipiepy-model==0.23.0 \
  python experiments/guide_rag/model-comparison/run.py \
  --reranker-path /tmp/guide-rag-models/reranker \
  --output-dir /tmp/guide-rag-results
```

`--repo` 기본값은 현재 저장소다. 다른 커밋의 체크아웃을 명시하면 해당 제품 검색 함수를 평가한다. 결과에 제품 커밋과 검색 함수·실험 코드·데이터 해시를 기록한다. 개인 경로는 결과에 저장하지 않는다. 모델 준비 도구가 생성한 manifest를 비교 시 확인한다.

비교 실행기는 제품 모듈을 import하기 전에 임시 디렉터리로 이동하고 합성 환경값을 사용한다. DB·환자 데이터·외부 생성 API는 호출하지 않는다. 모델 가중치·캐시·실제 문서 원문은 커밋 대상이 아니다. 실제 실행 패키지 버전은 결과 JSON에서 확인한다.

## 결과의 의미와 다음 검증

초기 로컬 실험에서는 한국어 분석 추가로 BM25의 정답 Top3 회수가 11/15에서 15/15로 증가했다. 네 Hybrid 조합은 모두 정답 15/15를 1위에 놓았지만, 근거 없는 질문 5건에도 모두 후보를 반환했다. 따라서 재순위 모델 추가의 이득이나 근거 거절 능력을 입증하지 않았다. 이번 PR의 재실행 결과는 `model-comparison/report.md`를 기준으로 확인한다.

작고 쉬운 합성셋이며 같은 데이터로 반복 탐색했다. 독립 검증·임상 정확도·운영 지연시간으로 해석하지 않는다. `seconds`는 모델 로딩·Dense 인코딩을 제외한 단일 CPU 실행 측정이며 조합별 전체 서비스 응답시간이 아니다. BGE-M3 자체 Dense+Sparse는 미측정이다.

실제 평가에서는 승인 문서 버전과 사용 가능/금지 청크 ID를 검토자가 먼저 확정한다. 정답 존재·표현 차이·유사하지만 근거 없음·적용 대상 불일치·부분 근거·충돌을 포함하고, 기준 조정용과 최종 평가용을 문서/질문 계열 단위로 분리한다. 근거 회수율, 오채택률, 과잉 거절률, 금지 근거 채택, 생성 문장의 근거 충족을 따로 기록한다. 고정 템플릿 항목은 검색 회수율의 정답 사례로 섞지 않고 기대 동작을 별도로 평가한다.
