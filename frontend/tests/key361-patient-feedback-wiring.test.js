const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const guideSource = fs.readFileSync(
  path.join(__dirname, '..', 'patient_wireframe', 'js', 'guide.js'),
  'utf8',
);
const footerSource = fs.readFileSync(
  path.join(__dirname, '..', 'patient_wireframe', 'component', 'guide-footer.js'),
  'utf8',
);

test('오류 신고 진입점이 GUIDE_MOCK 뒤에 숨어 있지 않다 — KEY-361 핵심 결함', () => {
  // 저장 흐름(submitPatientFeedback)은 이미 실제 API를 부르고 있었는데,
  // 진입점 자체가 GUIDE_MOCK일 때만 만들어져서 실 환경에서는 아무것도
  // 안 보였다. 이 게이팅이 되살아나지 않게 잡아 둔다.
  assert.doesNotMatch(guideSource, /onReport:\s*GUIDE_MOCK/);
  assert.doesNotMatch(guideSource, /if\s*\(GUIDE_MOCK\)\s*\{\s*\n?\s*var report = document\.createElement/);
});

test('onHelpful·onUnhelpful·onReport가 항상(mock 여부와 무관하게) 연결된다', () => {
  assert.match(guideSource, /onHelpful:\s*submitHelpful/);
  assert.match(guideSource, /onUnhelpful:\s*function\s*\(\)\s*\{\s*openReport\('UNHELPFUL'\);\s*\}/);
  assert.match(guideSource, /onReport:\s*function\s*\(\)\s*\{\s*openReport\(\);\s*\}/);
});

test('👍는 오버레이 없이 즉시 HELPFUL로 제출한다', () => {
  assert.match(guideSource, /function submitHelpful\(/);
  assert.match(guideSource, /category:\s*'HELPFUL'/);
  // 중복 클릭 방지 — 진행 중이면 다시 안 부른다.
  assert.match(guideSource, /if\s*\(helpfulSubmitting\)\s*return;/);
});

test('👎는 오류 신고 오버레이를 열되 UNHELPFUL을 미리 고른다', () => {
  assert.match(guideSource, /function buildReportOverlay\(presetCategory\)/);
  assert.match(guideSource, /if\s*\(presetCategory && reason\.category === presetCategory\)/);
});

test('GuideFooter가 도움말 영역(👍·👎)과 오류 신고를 모두 옵션으로 받는다', () => {
  assert.match(footerSource, /opts\.onHelpful/);
  assert.match(footerSource, /opts\.onUnhelpful/);
  assert.match(footerSource, /이 안내가 도움이 되었나요/);
  assert.match(footerSource, /guide-footer__thumb/);
});

test('시연 범위 — 승인 완료 모달에 D+7 자동발송 약속 문구가 없다', () => {
  const guideViewSource = fs.readFileSync(
    path.join(__dirname, '..', 'js', 'guide-view.js'),
    'utf8',
  );
  assert.doesNotMatch(guideViewSource, /확인 문자\(일주일 뒤 · 보름 뒤\)/);
});
