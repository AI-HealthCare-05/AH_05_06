const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'patient_wireframe', 'js', 'guide.js'),
  'utf8',
);

test('P9 오류 신고는 선택한 안내 섹션을 구조화해 전송한다', () => {
  assert.match(source, /target: 'GUIDE_SECTION'/);
  assert.match(source, /source_screen: 'P9'/);
  assert.match(source, /section_key: selectedScreen\.sectionKey/);
  assert.match(source, /content_key: selectedScreen\.contentKey/);
  assert.match(source, /detected_tab: state\.tab/);
});

test('자유 입력은 1000자로 제한하고 실패 시 입력 화면을 유지한다', () => {
  assert.match(source, /textarea\.maxLength = 1000/);
  assert.match(source, /submitBtn\.textContent = '다시 시도'/);
  assert.doesNotMatch(source, /\[\uBBF8\uAD6C\uD604\] 오류 신고/);
});

test('네트워크 재시도는 같은 submission_id를 사용한다', () => {
  assert.match(source, /submissionId = submissionId \|\| createFeedbackSubmissionId\(\)/);
  assert.match(source, /submission_id: submissionId/);
});
