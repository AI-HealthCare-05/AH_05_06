const { test } = require("node:test");
const assert = require("node:assert/strict");
const { load } = require("./browser-shim.js");
const held = { guide_message_id: 1, status: "HELD", hold_reason: "SOURCE_NOT_DELETED",
  source_failure_type: "DELETION_RECORD_MISMATCH", source_failure_at: "2026-09-17T12:00:00+09:00",
  source_retry_generation: 2 };

test("KEY-362 보류 원인·발생 시각과 복구 대기를 표시", () => {
  const box = load("api", "message-words");
  const text = box.messageSaying(held);
  assert.match(text, /SOURCE_NOT_DELETED/);
  assert.match(text, /DELETION_RECORD_MISMATCH/);
  assert.match(text, /2026/);
  assert.match(box.messageSaying({ ...held, source_retry_requested: true }), /처리 중/);
  assert.doesNotMatch(box.messageSaying({ ...held, source_failure_type: "secret filename" }), /secret filename/);
});

test("KEY-362 권한과 상태를 모두 만족한 경우에만 별도 삭제 재시도 버튼", () => {
  const box = load("api", "message-words");
  assert.equal(box.sourceRetryButton(held), "");
  box.sourceRetryRoles = ["admin"];
  assert.equal(box.sourceRetryButton(held), "");
  for (const role of ["doctor", "staff"]) {
    box.sourceRetryRoles = [role];
    assert.match(box.sourceRetryButton(held), /data-generation="2"/);
    assert.match(box.sourceRetryButton({ ...held, source_retry_requested: true }), /disabled/);
    assert.equal(box.sourceRetryButton({ ...held, hold_reason: "NO_CREDIT" }), "");
    assert.equal(box.sourceRetryButton({ ...held, status: "SENT" }), "");
  }
  assert.equal(box.canResend("HELD"), false);
});

test("KEY-362 요청은 세대만 전송하고 이중 클릭은 한 번만 실행", async () => {
  const box = load("api", "message-words");
  const calls = [];
  box.window.confirm = () => true;
  box.request = (url, options) => {
    calls.push({url, options});
    return Promise.resolve({status:"HELD"});
  };
  const button = {disabled:false, dataset:{sourceRetry:"1",generation:"2"}};
  let refreshed = 0;
  box.requestSourceRetry(button, () => refreshed++);
  box.requestSourceRetry(button, () => refreshed++);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/messages/1/source-retry");
  assert.equal(JSON.stringify(calls[0].options.body), '{"generation":2}');
  assert.equal(refreshed, 1);
  assert.equal(button.disabled, true);
});

test("KEY-362 409는 같은 세대 버튼을 되살리지 않고 최신 상태를 다시 읽는다", async () => {
  const box = load("api", "message-words");
  box.window.confirm = () => true;
  box.request = () => Promise.reject({status: 409, code: "SOURCE_RETRY_NOT_ALLOWED"});
  const button = {disabled:false, textContent:"", dataset:{sourceRetry:"1",generation:"2"}};
  let refreshed = 0;
  box.requestSourceRetry(button, () => refreshed++);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(refreshed, 1);
  assert.equal(button.disabled, true);
  assert.equal(button.textContent, "상태 다시 확인 중…");
});

test("KEY-362 의사 화면도 역할과 삭제 재시도 클릭을 직접 배선한다", () => {
  const { codeOnly, read } = require("./source.js");
  const code = codeOnly(read("js/doctor.js"));
  assert.match(code, /sourceRetryRoles = me\.roles \|\| \[\]/);
  assert.match(code, /closest\("\[data-source-retry\]"\)/);
  assert.match(code, /requestSourceRetry\(sourceButton/);
});
