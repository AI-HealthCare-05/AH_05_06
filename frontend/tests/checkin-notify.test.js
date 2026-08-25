/* 어떤 답이 병원 알림을 만드는가 — KEY-158 로 꺼낸 규칙.
 *
 * 계약이 답마다 `notify` 를 정하고 화면은 **받은 그대로 되돌린다.** 화면이
 * 「원장님께 전해 드릴게요」라고 말해 놓고 서버는 모르는 상태를 막는 자리다
 * (`#55` 리뷰).
 *
 * 꺼내면서 인자가 하나 늘었다(`data` 를 닫아 읽던 것을 받는다). **호출부를
 * 같이 안 고치면 늘 `false` 가 되는데 아무 검사도 안 죽었다** — 그래서 여기에
 * 원문 검사까지 함께 둔다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const CHECKIN_JS = path.join(__dirname, "..", "js", "checkin.js");

function box() {
  return load("api", "checkin-api", "checkin");
}

const ANSWERS = {
  taking: { notify: false },
  stopped_side_effect: { notify: true },
  uncomfortable: { notify: true },
};

test("계약이 알리라고 한 답만 알린다", () => {
  const { notifyFor } = box();
  assert.strictEqual(notifyFor(ANSWERS, "stopped_side_effect"), true);
  assert.strictEqual(notifyFor(ANSWERS, "uncomfortable"), true);
  assert.strictEqual(notifyFor(ANSWERS, "taking"), false);
});

test("모르는 답은 알리지 않는다", () => {
  /* 알림은 사람을 부르는 일이다. 모를 때 부르면 부르지 않는 것보다 나쁘다 —
     매번 헛걸음하면 다음 알림도 안 본다. */
  const { notifyFor } = box();
  assert.strictEqual(notifyFor(ANSWERS, "그런답없음"), false);
  assert.strictEqual(notifyFor(null, "taking"), false);
  assert.strictEqual(notifyFor(undefined, undefined), false);
});

test("화면이 이 규칙을 실제로 부른다 — 인자를 둘 다 넘긴다", () => {
  /* 꺼내면서 인자가 하나 늘었다. 호출부가 옛 모양(`notifyFor(picked)`)으로
     남으면 `answers` 자리에 답 키가 들어가고 `key` 는 `undefined` 라
     **늘 `false`** 가 된다 — 알림이 통째로 죽는데 아무 검사도 안 죽는다. */
  const source = fs.readFileSync(CHECKIN_JS, "utf8");
  assert.match(source, /notify: notifyFor\([^)]+,\s*picked\)/, "저장이 규칙을 인자 둘로 부르지 않는다");
  assert.doesNotMatch(source, /notifyFor\(picked\)/, "옛 한 인자 호출이 남아 있다");
});
