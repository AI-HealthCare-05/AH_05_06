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
const manageMarkup = fs.readFileSync(path.join(__dirname, '..', 'manage.html'), 'utf8');
const adminFeedbackSource = fs.readFileSync(
  path.join(__dirname, '..', 'js', 'admin-feedback.js'),
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
  // 응답 유실 뒤 재시도해도 서버 멱등키가 바뀌면 중복 저장된다.
  assert.match(
    guideSource,
    /helpfulSubmissionId\s*=\s*helpfulSubmissionId\s*\|\|\s*createFeedbackSubmissionId\(\)/,
  );
  assert.match(guideSource, /submission_id:\s*helpfulSubmissionId/);
});

test('👍 전송 실패는 접근 가능한 재시도 안내를 표시하고 입력 상태를 유지한다', () => {
  assert.match(footerSource, /aria-live',\s*'polite'/);
  assert.match(footerSource, /data-feedback-status/);
  assert.match(guideSource, /전송하지 못했어요\. 다시 눌러 주세요\./);
  assert.strictEqual(
    (guideSource.match(/helpfulSubmissionId\s*=\s*null/g) || []).length,
    1,
    '실패 뒤 멱등키를 비우면 재시도가 중복 저장될 수 있다',
  );
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

test('관리 보조 탭은 발송 이력 바로 뒤에서 기존 환자 피드백 화면으로 이동한다', () => {
  const historyAt = manageMarkup.indexOf('발송 이력');
  const feedbackAt = manageMarkup.indexOf('환자 피드백', historyAt);
  assert.ok(historyAt !== -1 && feedbackAt > historyAt);
  assert.match(manageMarkup.slice(historyAt, feedbackAt + 20), /href="\/admin-feedback\.html"/);
});

test('기존 피드백 화면은 staff·doctor·admin 모두 진입할 수 있다', () => {
  assert.match(adminFeedbackSource, /\['staff', 'doctor', 'admin'\]/);
  assert.doesNotMatch(adminFeedbackSource, /indexOf\('admin'\)\s*===\s*-1/);
});

test('시연 범위 — 승인 완료 모달에 D+7 자동발송 약속 문구가 없다', () => {
  const guideViewSource = fs.readFileSync(
    path.join(__dirname, '..', 'js', 'guide-view.js'),
    'utf8',
  );
  assert.doesNotMatch(guideViewSource, /확인 문자\(일주일 뒤 · 보름 뒤\)/);
});
