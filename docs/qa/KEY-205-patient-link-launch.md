# KEY-205 개발용 환자 링크 발급 → 안내 화면 Pilot 절차

## 범위

기존 `POST /api/v1/visits/{visit_id}/guide/link` 응답을 병원 승인 화면에서 받아
`guide.html`로 연결하는 화면 전환만 검증한다. 실제 SMS, OTP, 링크 폐기·재발급,
D+7 제출은 이 절차의 범위가 아니다.

모든 값은 `SYN-EMS-01` 합성 시나리오만 사용한다.

## 사전 조건

1. 병원 사용자로 로그인한다.
2. `SYN-EMS-01`의 안내가 `SCHEDULED_TO_SEND`이고 `approved_at`이 존재하는지 확인한다.
3. 아직 `PatientGuideLink`가 없는 진료 건을 사용한다.
4. 브라우저 개발자 도구의 Network 기록 보존을 끄고 Console을 비운다.

## 정상 흐름

1. 병원 승인 화면에서 `SYN-EMS-01` 진료를 고른다.
2. **개발용 환자 화면 열기**를 한 번 누른다.
3. 새 탭이 `guide.html`로 열리고 주소에서 `#t=...`가 즉시 사라지는지 확인한다.
4. 환자 화면에 같은 `visit_id`의 승인 섹션만 보이는지 확인한다.
5. 챗봇 탭에서 합성 질문 `약은 언제 먹나요?`를 한 번 보낸다.
6. 승인 복약 안내를 근거로 답하거나, 모델 장애 시 안전 fallback과 한계가 표시되는지 확인한다.
7. 병원 화면으로 돌아와 Console, DOM, `localStorage`, `sessionStorage`에 링크 토큰 원문이 없는지 확인한다.
8. 서버 access log에 `/guide.html#t=...` 또는 링크 토큰 원문이 없는지 확인한다. URL fragment는 HTTP 요청에 포함되지 않아야 한다.

## 차단·오류 흐름

| 상황 | 기대 결과 |
| --- | --- |
| 미승인 안내 | `GUIDE_NOT_APPROVED`; 승인 완료 후 열 수 있다는 안내 |
| 같은 안내에서 두 번째 발급 | `LINK_ALREADY_ISSUED`; 재발급하지 않고 기존 환자 화면을 이용하라는 안내 |
| 타 병원 진료 | `GUIDE_NOT_FOUND`; 진료·안내 존재 여부를 추가 노출하지 않음 |
| 발급 권한 없음 | `FORBIDDEN`; 권한 안내만 표시 |
| 없는 링크 | 환자 화면에서 사용할 수 없는 링크 안내 |
| 만료 링크 | 환자 화면에서 링크 만료 및 병원 문의 안내 |

## 자동 검증

```bash
node --test frontend/tests/key205-patient-link-launch.test.js
uv run pytest -q app/tests/patient_links/test_key205_patient_link_launch.py
uv run pytest -q app/tests/patient_links app/tests/chatbot
uv run ruff check .
uv run ruff format . --check
uv run mypy --explicit-package-bases .
```

## 실제 구현과 demo 대체

| 구간 | 상태 |
| --- | --- |
| 승인 안내 링크 발급·digest 저장·72시간 만료 | 실제 API·DB 구현 |
| 승인 안내 조회와 챗봇 승인 컨텍스트 검증 | 실제 API 구현 |
| 병원 화면 → 환자 화면 전환 | 실제 프런트 연결 |
| SMS·OTP | 이번 시연에서는 사용하지 않는 명시적 demo 범위 |
| 외부 모델 실패 | 진단·처방 변경 권고가 없는 안전 fallback |

## 수동 결과 기록

- 실행 일시:
- 실행자:
- `visit_id`(합성 데이터):
- 정상 흐름: 통과 / 실패
- 챗봇: 승인 컨텍스트 응답 / 안전 fallback
- 토큰 원문 미노출: Console / DOM / 저장소 / access log
- 제한사항 또는 후속 일감:
