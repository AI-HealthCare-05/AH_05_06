const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

function read(relative) {
  return fs.readFileSync(path.join(__dirname, '..', relative), 'utf8');
}

test('관리자 피드백 목록 화면은 실제 목록 API와 빈 상태·실패 상태를 구분한다', () => {
  const api = read('js/admin-feedback-api.js');
  const screen = read('js/admin-feedback.js');
  assert.match(api, /request\('\/admin\/patient-feedback\?'/);
  assert.match(screen, /접수된 피드백이 없습니다/);
  assert.match(screen, /피드백을 불러오지 못했습니다/);
  assert.match(screen, /indexOf\('admin'\) === -1/);
});

test('목록 화면은 자유 입력 원문을 행에 렌더링하지 않는다', () => {
  const screen = read('js/admin-feedback.js');
  assert.doesNotMatch(screen, /item\.details/);
  assert.match(screen, /item\.has_details/);
});
