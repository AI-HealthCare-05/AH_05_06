/* D+7 복약 신호가 실제로 어떻게 도는가 — KEY-138.
 *
 * 문자열을 grep 하는 검사가 아니다. `checkin-api.js` 를 **실제로 불러서** 돌린다.
 * 그렇게 하지 않으면 못 잡는다는 것을 `#79` 리뷰가 보여 줬다 — 요청 도착 순서가
 * 뒤집혀 「지금 답」이 어긋나는데, 소스를 보는 검사 13개가 전부 통과했다.
 *
 * 유가은 님이 지정한 넷을 그대로 잰다.
 *
 *   ① 빠른 연속 선택 시 요청 도착 순서 역전
 *   ② 동일 답 연속 선택 · 다른 답을 거쳐 재선택
 *   ③ 마지막 신호 실패 후 저장 요청으로 최종 상태 정정
 *   ④ 새로고침·세션 변경 시 sequence 처리
 */

const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS_DIR = path.join(__dirname, "..", "js");

/* 브라우저 전역 최소 흉내. `checkin-api.js` 는 IIFE 가 아니라 최상위에 함수를
   두므로 이것만으로 통째로 불린다 — `checkin.js` 는 IIFE 라 못 부른다(KEY-158). */
function loadApi() {
  const sandbox = {
    location: { search: "?mock=1" },
    sessionStorage: (() => {
      const box = {};
      return {
        getItem: (k) => (k in box ? box[k] : null),
        setItem: (k, v) => {
          box[k] = String(v);
        },
        removeItem: (k) => delete box[k],
      };
    })(),
    URLSearchParams,
    setTimeout,
    Promise,
    Math,
    Date,
    JSON,
    crypto,
    console,
    // `api.js` 대신 최소한만 둔다 — 목업 경로만 쓰므로 실제 요청은 안 나간다.
    ApiError: class ApiError extends Error {
      constructor(code, status, detail) {
        super(code);
        this.code = code;
        this.status = status;
        this.detail = detail;
      }
    },
    MOCK: true,
    request: () => {
      throw new Error("검사에서 진짜 요청이 나갔다 — 목업이 안 걸렸다");
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "checkin-api.js"), "utf8"), sandbox);
  return sandbox;
}

/* 신호를 보내되 **닿는 데 걸리는 시간을 검사가 정한다.** 실제 망에서 첫 요청이
   느린 것(첫 연결·재시도·혼잡)을 재현하는 유일한 방법이다. */
function sendAfter(api, token, key, stamp, latency) {
  return new Promise((resolve) => setTimeout(resolve, latency)).then(() =>
    api.checkinApi.signal(token, key, stamp.session, stamp.sequence)
  );
}

test("① 빠른 연속 선택 — 요청이 뒤집혀 닿아도 마지막에 고른 답이 지금 답이다", async () => {
  const api = loadApi();
  const tracker = api.createSignalTracker();

  const first = tracker.next("stopped_side_effect");
  const second = tracker.next("taking");

  // 첫 요청이 느리다 → 나중에 고른 `taking` 이 서버에 먼저 닿는다.
  const results = await Promise.all([
    sendAfter(api, "t", "stopped_side_effect", first, 60),
    sendAfter(api, "t", "taking", second, 0),
  ]);

  const late = results[0]; // 늦게 닿은 옛 신호
  assert.equal(late.answer_key, "stopped_side_effect");
  assert.equal(late.current, false, "늦게 닿은 옛 신호가 지금 답을 덮었다");
  assert.equal(
    late.current_answer_key,
    "taking",
    "환자는 「잘 먹고 있어요」로 바꿨는데 서버의 지금 답이 중단이다 — 의원이 없는 문제를 쫓는다"
  );
});

test("② 연달아 같은 답은 안 보내고, 다른 답을 거쳐 돌아오면 새 신호다", async () => {
  const api = loadApi();
  const tracker = api.createSignalTracker();

  assert.ok(tracker.next("stopped_side_effect"), "첫 선택은 보내야 한다");
  assert.equal(tracker.next("stopped_side_effect"), null, "연달아 같은 답을 두 번 보냈다");

  const back = tracker.next("taking");
  assert.ok(back, "다른 답은 보내야 한다");
  const again = tracker.next("stopped_side_effect");
  assert.ok(again, "다른 답을 거쳐 돌아온 것은 새 신호여야 한다");
  assert.ok(
    again.sequence > back.sequence,
    "돌아온 신호의 순번이 더 커야 한다 — 아니면 마지막 신호가 실제로 고른 답과 어긋난다"
  );
});

test("③ 마지막 신호가 실패해도 저장이 최종 답으로 바로잡는다", async () => {
  const api = loadApi();
  const tracker = api.createSignalTracker();

  // 위험한 답은 닿았다.
  const danger = tracker.next("stopped_side_effect");
  await api.checkinApi.signal("t", "stopped_side_effect", danger.session, danger.sequence);

  // 마음을 바꿨지만 그 신호는 못 갔다 — 화면은 조용히 접고 표시를 되돌린다.
  const previous = tracker.lastSent();
  tracker.next("taking");
  tracker.failed("taking", previous);
  assert.equal(tracker.lastSent(), "stopped_side_effect", "실패한 신호가 보낸 것으로 남아 있다");

  // 이 시점에 서버의 「지금 답」은 여전히 중단이다.
  const saved = await api.checkinApi.save("t", { medication: "taking", notify: false });
  assert.equal(saved.saved, true);

  /* 저장 응답이 정정 결과를 말해 준다. 신호를 하나 더 보내서 확인하면 **그것이
     지금 답이 돼 버려** 정작 재려던 것을 가린다 — 처음에 그렇게 썼다가
     돌연변이가 안 잡혀서 알았다. */
  assert.equal(
    saved.signal_answer_key,
    "taking",
    "저장이 신호 상태를 맞추지 못했다 — 못 간 신호를 저장이 받쳐 준다는 계약이 서지 않는다"
  );
});

test("④ 새로고침하면 순번이 1 부터 다시 시작하고, 그래도 나중 화면이 이긴다", async () => {
  const api = loadApi();

  const before = api.createSignalTracker();
  const s1 = before.next("stopped_side_effect");
  const s2 = before.next("taking");
  assert.equal(s1.sequence, 1);
  assert.equal(s2.sequence, 2);
  await api.checkinApi.signal("t", "stopped_side_effect", s1.session, s1.sequence);
  await api.checkinApi.signal("t", "taking", s2.session, s2.sequence);

  // 새로고침 — 다른 화면이다.
  const after = api.createSignalTracker();
  assert.notEqual(after.session, before.session, "새로고침했는데 화면 식별값이 같다");

  const fresh = after.next("stopped_improved");
  assert.equal(fresh.sequence, 1, "새 화면의 순번은 1 부터다");

  const result = await api.checkinApi.signal("t", "stopped_improved", fresh.session, fresh.sequence);
  assert.equal(
    result.current_answer_key,
    "stopped_improved",
    "순번이 1 이라고 앞 화면의 2 번에 밀렸다 — 새로고침 뒤 고른 답이 무시된다"
  );
});

test("④-b 같은 화면 안에서는 순번이 도착 순서를 이긴다", async () => {
  const api = loadApi();
  const tracker = api.createSignalTracker();

  const a = tracker.next("taking");
  const b = tracker.next("stopped_side_effect");

  // 일부러 뒤집어 보낸다 — 2번을 먼저, 1번을 나중에.
  await api.checkinApi.signal("t", "stopped_side_effect", b.session, b.sequence);
  const late = await api.checkinApi.signal("t", "taking", a.session, a.sequence);

  assert.equal(late.current, false);
  assert.equal(late.current_answer_key, "stopped_side_effect", "같은 화면인데 도착 순서가 순번을 이겼다");
});
