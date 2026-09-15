const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

test("KEY-238 안내 복귀는 현재 토큰을 fragment로만 전달한다", () => {
  const { checkinGuideReturnUrl } = load("api", "checkin-api", "checkin");
  const token = "synthetic-only_238-&=token";
  const url = new URL(checkinGuideReturnUrl(token), "https://example.test");
  assert.equal(url.pathname, "/guide.html");
  assert.equal(url.search, "");
  assert.equal(new URLSearchParams(url.hash.slice(1)).get("t"), token);
  assert.equal(checkinGuideReturnUrl(""), "");
});

test("KEY-238 완료 화면은 서버 guide_url 대신 현재 브라우저 토큰을 사용한다", () => {
  const source = fs.readFileSync(path.join(__dirname, "../js/checkin.js"), "utf8");
  assert.match(source, /esc\(checkinGuideReturnUrl\(token\)\)/);
  assert.doesNotMatch(source, /result\.guide_url/);
});

test("KEY-238 의료진 확인은 안전 해소와 구분하고 확인 정보는 이스케이프한다", () => {
  const { checkinSignalsHtml } = load("api", "clinic-clock", "session", "message-words", "checkin-words", "patients-api", "history-modal");
  const signal = {state_id: 1, signal_id: 2, answer_key: "stopped_side_effect", status: "OPEN", updated_at: '"<script>'};
  const html = checkinSignalsHtml({visit_id: 3, checkin_signals: [signal]});
  assert.match(html, /확인 필요/);
  assert.match(html, /진료 완료나 안전 해소가 아닙니다/);
  assert.match(html, /data-checkin-ack="1"/);
  assert.doesNotMatch(html, /<script>/);
  signal.status = "ACKNOWLEDGED";
  assert.doesNotMatch(checkinSignalsHtml({visit_id: 3, checkin_signals: [signal]}), /data-checkin-ack/);
});
