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
  const listRenderer = screen.slice(screen.indexOf('function renderRows'), screen.indexOf('function detailRow'));
  assert.doesNotMatch(listRenderer, /item\.details/);
  assert.match(listRenderer, /item\.has_details/);
});

test('목록 행은 관리자 상세 API를 호출하고 상세 실패를 별도로 표시한다', () => {
  const api = read('js/admin-feedback-api.js');
  const screen = read('js/admin-feedback.js');
  assert.match(api, /request\('\/admin\/patient-feedback\/'/);
  assert.match(screen, /getPatientFeedback\(feedbackId\)/);
  assert.match(screen, /상세 내용을 불러오지 못했습니다/);
  assert.match(screen, /event\.key !== 'Enter' && event\.key !== ' '/);
});

test('범위를 벗어난 페이지는 마지막 유효 페이지로 다시 조회한다', () => {
  const screen = read('js/admin-feedback.js');

  assert.match(screen, /state\.page > lastPage/);
  assert.match(screen, /state\.page = lastPage/);
  assert.match(screen, /return loadFeedback\(\)/);
});
