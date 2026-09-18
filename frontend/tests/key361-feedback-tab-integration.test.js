const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

function read(relative) {
  return fs.readFileSync(path.join(__dirname, '..', relative), 'utf8');
}

test('환자 피드백은 별도 페이지 링크가 아니라 같은 쉘의 네 번째 탭이다 — 2heej 리뷰', () => {
  const html = read('manage.html');
  // 예전엔 <a href="/admin-feedback.html">였다 — 클릭하면 공용 쉘(로고·
  // 상단 네비게이션)을 벗어나고 돌아올 방법이 없었다.
  assert.doesNotMatch(html, /href="\/admin-feedback\.html"/);
  assert.match(html, /data-view="feedback"/);
  // <button>으로 바뀌었으니 .tab 클래스의 밑줄 문제도 함께 없어진다
  // (2heej가 같이 지적한 항목 — <a>에만 쓰이던 스타일이라 밑줄이
  // 남아 있었다).
  const feedbackTabButton = html.slice(
    html.lastIndexOf('<button', html.indexOf('data-view="feedback"')),
    html.indexOf('data-view="feedback"'),
  );
  assert.match(feedbackTabButton, /<button/);
});

test('manage.js가 기존 admin-feedback API를 그대로 재사용한다 — 새 API를 만들지 않는다', () => {
  const script = read('js/manage.js');
  assert.match(script, /listPatientFeedback\(\{/);
  assert.match(script, /getPatientFeedback\(feedbackId\)/);
  // 목록·상세 화면 자체(admin-feedback.js)는 손대지 않았다 — manage.js가
  // 그 파일의 함수만 새 위치에서 부른다.
  assert.doesNotMatch(script, /function listPatientFeedback/);
  assert.doesNotMatch(script, /function getPatientFeedback/);
});

test('manage.html이 admin-feedback-api.js를 불러온다', () => {
  const html = read('manage.html');
  assert.match(html, /<script src="\/js\/admin-feedback-api\.js">/);
});

test('탭을 바꾸면 피드백 페이지가 1쪽으로 돌아간다 — KEY-303과 같은 규칙', () => {
  const script = read('js/manage.js');
  const tabsHandler = script.slice(
    script.indexOf('el("tabs").addEventListener'),
    script.indexOf('el("feedback-target-filter")'),
  );
  assert.match(tabsHandler, /if \(name === "feedback"\) feedbackPage = 1;/);
});

test('상세 보기는 기존 공용 모달(#modal)을 재사용한다 — 새 페이지 이동이 아니다', () => {
  const script = read('js/manage.js');
  const detailFn = script.slice(
    script.indexOf('function openFeedbackDetail'),
    script.indexOf('function openHistory'),
  );
  assert.match(detailFn, /el\("modal"\)\.hidden = false/);
  assert.match(detailFn, /data-close/);
});

test('역할·병원 범위 검증은 서버 계약(AdminPatientFeedbackService)에 그대로 위임한다', () => {
  // 프런트가 role/hospital 필터링을 새로 하지 않는다 — 기존 계약(403
  // FORBIDDEN, hospital_id 스코프)이 이미 서버에 있고
  // app/tests/patient_feedback/test_patient_feedback_api.py의
  // TestAdminFeedbackList가 이를 검증한다. 여기서는 프런트가 그 응답을
  // 그대로 통과시키는지만 잰다 — 에러를 삼키거나 무시하지 않는다.
  const detailScreen = read('js/admin-feedback.js');
  assert.match(detailScreen, /\['staff', 'doctor', 'admin'\]/);
  assert.match(detailScreen, /location\.replace\(landingFor\(me\.roles\)\)/);
});

test('어드민 단독 계정은 걸림 없이 피드백 탭에서 시작한다 — 2heej 재리뷰', () => {
  const script = read('js/manage.js');
  assert.match(script, /if \(!doesClinicWork\(who\.roles\)\) view = "feedback";/);
});

test('403 문구가 피드백 탭에서는 어드민을 배제하는 것처럼 읽히지 않는다', () => {
  const script = read('js/manage.js');
  const loadFn = script.slice(script.indexOf('function load()'), script.indexOf('function load()') + 1400);
  assert.match(loadFn, /view === "feedback"/);
  assert.match(loadFn, /이 계정으로는 조회할 수 없습니다/);
});

test('대상·유형 드롭다운이 발송예정·발송이력과 같은 send-days 스타일을 쓴다', () => {
  const html = read('manage.html');
  assert.match(html, /<select class="send-days" id="feedback-target-filter">/);
  assert.match(html, /<select class="send-days" id="feedback-category-filter">/);
});

test('피드백 상세는 환자 이력 모달과 같은 modal__top·아이콘 닫기를 쓴다', () => {
  const script = read('js/manage.js');
  const detailFn = script.slice(
    script.indexOf('function openFeedbackDetail'),
    script.indexOf('function openHistory'),
  );
  assert.match(detailFn, /class="modal__top"/);
  assert.match(detailFn, /class="modal__title"/);
  assert.match(detailFn, /class="icon-button"/);
  assert.match(detailFn, /class="feedback-fields"/);
  // 예전엔 텍스트 "닫기" 버튼 + 클래스 없는 <dl>이었다 — 나열처럼 보였다.
  assert.doesNotMatch(detailFn, /button-ghost.*닫기</);
});
