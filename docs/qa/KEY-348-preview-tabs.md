# KEY-348 내부 안내문 미리보기 검증

검증일: 2026-09-15. 기준: develop `7654419`에서 분리한 `codex/KEY-348-preview-tabs`.

PR 생성 전 develop `689c61f`를 fast-forward로 반영했다. KEY-348 변경과 겹치지 않는 migration 검사 파일 한 개가 갱신되었으며 충돌은 없었다.
최신화 후 미리보기 응답·migration 계약 검사를 다시 실행해 76건 통과했다.

## 구현 범위

- 기존 `GET /visits/{visit_id}/guide`의 `preview`에 `stat`/`clinic` 추가.
- `medication_stat_of(data)`와 `data.clinic_name` 재사용. 처방이 없으면 `stat: null`.
- 공용 `patient-guide-cards.js`에서 현황/복약지도/주의사항/생활관리 전환.
- 현황 카드, 소진 안내, 복약지도 보기, 접기/펼치기 지원.
- 관리·환자 카드 현황의 미리보기 모두 하단 닫기 하나. 바깥 클릭·ESC 지원.
- iframe은 `allow-same-origin`만 사용. 내부 스크립트 실행·환자 읽음 기록·실제 링크 발급 없음.
- 실제 환자 페이지, DB 모델, migration, 챗봇은 변경하지 않음.

## 자동 검증

- 백엔드 `app/tests/guide_apis app/tests/patient_links`: **308 passed**.
- `test_key294_preview_payload.py`: 기존 환자 API와 `guide`/`stat`/진료일/병원명 값 일치, 처방 없는 `stat: null`, 조회 외 응답 미포함, 환자 이름·연락처·토큰 미포함 확인.
- 프런트 `node --test frontend/tests/*.test.js`: **1,306 passed**.
- 신규 `key348-preview-tabs.test.js`: 실제 환자 renderStatus의 클래스·문구 대조, null/0일/시작일 없음, 0%/100%, 텍스트 이스케이프, 네 탭 순서·초기 선택, 공용 렌더러·단일 닫기 확인.
- Ruff check/format, mypy(470파일), OpenAPI 생성물 일치, `git diff --check` 통과.
- DB는 전용 로컬 MySQL(18377) 테스트 슬롯 3 사용. 운영 DB·외부 발송/API 호출 없음.

## 실제 브라우저 확인

| 항목 | 기록 |
|---|---|
| 대상 | 관리 → 발송 예정 → 안내문 미리보기 / 환자 카드 → 현황 → 안내문 미리보기 |
| 환경 | Chrome 152.0.7977.83, 1440×1000, 로컬 정적 서버 18382, 기존 실제 HTML/JS와 합성 API 응답 |
| 조작 | 각 진입점에서 네 탭 클릭 → 현황의 복약지도 보기 → 접기/펼치기 → 하단 닫기 → 재열기 → iframe 포커스에서 ESC → 재열기 → 바깥 클릭 |
| 기대 | 선택 탭 클래스·aria-selected·본문이 일치. 처방일/병원명, 약 카드, 진행률, 핑크 카드 표시. 닫기 한 개와 모든 종료 경로 작동 |
| 실제 | **PASS** — 두 진입점 모두 확인. JavaScript pageerror 없음. 현황 모달에 빠져 있던 ESC 처리를 발견해 보완한 뒤 재검증 |
| 자동검사 한계 | 기존 browser-shim은 DOM을 그리지 않음. 위 실제 브라우저 조작으로 iframe 이벤트·포커스·카드 표시를 별도 확인. 서버 API 응답은 별도 통합 테스트로 검증 |

현황 합성 데이터: 처방 28일, 7일째, 21일 남음, 진행률 25%, 합성 병원명과 소진 안내.
실제 환자 데이터는 사용하지 않았다. 기존 iframe `zoom: 0.8`을 유지하고, 브라우저 자동 조작의 클릭 좌표에 그 배율을 반영했다. 강제 클릭이나 DOM 이벤트 직접 발사는 사용하지 않았다.

재현 시 같은 로컬 페이지에서 합성 스탭 계정으로 로그인하고 두 진입점을 각각 연다. 환자 카드 쪽은 목업 `case=approved`를 사용한다. 관리 쪽은 API 응답의 `preview`를, 환자 카드 쪽은 공용 렌더러의 `preview` 입력만 위 합성 데이터로 공급했다. 기존 원본 렌더링 함수·이벤트 처리를 실행했다. 실제 백엔드·운영 배포 환경에서의 종단간 검증 완료를 의미하지는 않는다.
