## ✅ PR 요약
- 작업 요약: 어떤 작업을 했는지 간단하게 적어주세요.

## 📄 상세 내용
- [ ] 주요 변경 사항 1
- [ ] 주요 변경 사항 2
- [ ] 주요 변경 사항 3

## 📸 스크린샷 (선택)

## 👀 리뷰어
- @{github-id} <!-- Jira 리뷰어 필드와 동일 인물. 여기 적으면 PR 오픈 시 자동으로 리뷰어 요청됩니다. -->

## 🖥 수동 브라우저 확인

<!-- `frontend/tests/browser-shim.js` 는 일부러 화면을 그리지 않는다. 그래서
     호출 여부·순서·포커스·음성 안내는 자동 검사로 안 잡힌다.
     판단 기준과 기록 형식: docs/qa/frontend-manual-browser-check.md -->

- [ ] 해당 없음 (프런트 화면 동작을 바꾸지 않음)
- [ ] 필요해서 브라우저에서 직접 확인했음 — 아래에 결과를 적는다

```text
대상          
환경          
조작          
기대 결과     
실제 결과     PASS / FAIL
자동검사 한계 
```

## 📝 기타 참고 사항

## 🔌 API 계약 영향

- [ ] API 계약 변경 없음
- [ ] DTO·라우터 변경에 맞춰 `docs/api/openapi.json`을 재생성했고, `uv run --group app python scripts/generate_openapi.py --check`를 통과시켰습니다.
- [ ] 계약 결정·호환성 영향은 관련 `docs/api/*.md`와 Jira에 기록했습니다.

## 📚 문서 동기화 (KEY-279)

<!-- 설치·환경변수·migration·seed·실행·검증 절차가 달라졌으면 같은 PR에서 README/관련 docs를 고친다.
     최종 책임자: 이희진. 기준: README.md 「기능 PR 문서 동기화 체크리스트」 -->

- [ ] 문서 변경 불필요 — 사유: <!-- 여기에 적는다 -->
- [ ] 새 환경변수를 `envs/example.*.env`와 `README.md` 환경변수 표에 이름·목적·예시로 반영했습니다(실제 값 제외).
- [ ] 설치·기동 순서·compose 프로필·포트 변경을 `README.md`에 반영했습니다.
- [ ] migration·seed 절차/모드 변경을 `README.md`와 `scripts/seed.py` 도움말에 맞췄습니다.
- [ ] 테스트·smoke·E2E 실행 명령 변경을 `README.md`에 반영했습니다.
- [ ] 바꾼 문서의 내부 링크와 명령을 실제로 확인했습니다.

## 🧪 PR Checklist
- [ ] 커밋 메시지 컨벤션에 맞게 작성했습니다.
- [ ] 변경 사항에 대한 테스트를 했습니다.(버그 수정/기능에 대한 테스트).
