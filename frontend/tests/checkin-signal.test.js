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

/* 새로고침을 넘겨 살아남는 저장소. 같은 것을 넘기면 같은 탭, 새로 만들면 새 탭이다. */
function memoryBox() {
  const box = {};
  return {
    getItem: (k) => (k in box ? box[k] : null),
    setItem: (k, v) => {
      box[k] = String(v);
    },
    removeItem: (k) => delete box[k],
  };
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
  const tracker = api.createSignalTracker(undefined, memoryBox());

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
  const tracker = api.createSignalTracker(undefined, memoryBox());

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
  const tracker = api.createSignalTracker(undefined, memoryBox());

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

test("④ 새로고침해도 순번이 이어진다 — 1 로 되돌아가지 않는다", async () => {
  const api = loadApi();
  const box = memoryBox(); // 기기에 남는 저장소. 새로고침·새 탭을 넘어 산다.

  const before = api.createSignalTracker(undefined, box);
  assert.equal(before.next("stopped_side_effect").sequence, 1);
  assert.equal(before.next("taking").sequence, 2);

  // 새로고침.
  const after = api.createSignalTracker(undefined, box);
  const fresh = after.next("stopped_improved");
  assert.equal(
    fresh.sequence,
    3,
    "순번이 1 로 되돌아갔다 — 새로고침 직전에 떠난 요청과 견줄 수 없다"
  );

  const result = await api.checkinApi.signal("t", "stopped_improved", fresh.session, fresh.sequence);
  assert.equal(result.current_answer_key, "stopped_improved");
});

/* 유가은 님이 `#79` 재검토에서 재현해 주신 것.
 *
 *   session-A  위험 답변 요청 출발 → 망에서 지연
 *   새로고침
 *   session-B  정상 답변 도착 → 지금 답 taking
 *   session-A  지연된 위험 답변 도착        ← 이것이 덮으면 안 된다
 *
 * 「새로고침은 사람 손 속도라 겹치지 않는다」로는 **이미 떠난 요청**을 막을 수
 * 없다. 도착 순서를 쓰던 앞 판정이 여기서 깨졌다. */
test("④-c 새로고침 전에 출발한 지연 요청이 새 화면의 답을 덮지 않는다", async () => {
  const api = loadApi();
  const box = memoryBox();

  const before = api.createSignalTracker(undefined, box);
  const danger = before.next("stopped_side_effect");

  // 위험 답변은 출발만 했다 — 아래에서 늦게 닿는다.
  const inFlight = sendAfter(api, "t", "stopped_side_effect", danger, 80);

  // 새로고침. 순번은 이어지므로 이 답이 더 큰 번호를 받는다.
  const after = api.createSignalTracker(undefined, box);
  const fresh = after.next("taking");
  assert.ok(fresh.sequence > danger.sequence, "새 화면의 순번이 앞 요청보다 커야 한다");

  const settled = await api.checkinApi.signal("t", "taking", fresh.session, fresh.sequence);
  assert.equal(settled.current_answer_key, "taking");

  // 이제 지연됐던 옛 요청이 닿는다.
  const late = await inFlight;
  assert.equal(late.current, false, "이전 화면의 지연 요청이 새 화면의 최종 답을 덮었다");
  assert.equal(late.current_answer_key, "taking", "환자가 마지막에 고른 답이 아니다");
});

test("④-d 탭을 새로 열어도 같은 순번을 이어 간다", async () => {
  const api = loadApi();
  const box = memoryBox(); // 같은 기기 = 같은 저장소

  const tab1 = api.createSignalTracker(undefined, box);
  const a = tab1.next("stopped_side_effect");

  const tab2 = api.createSignalTracker(undefined, box);
  const b = tab2.next("taking");
  assert.ok(b.sequence > a.sequence, "다른 탭이 앞 탭의 순번을 이어받지 않았다");

  // 두 탭의 요청이 뒤집혀 닿아도 나중에 고른 것이 이긴다.
  await api.checkinApi.signal("t", "taking", b.session, b.sequence);
  const late = await api.checkinApi.signal("t", "stopped_side_effect", a.session, a.sequence);
  assert.equal(late.current, false);
  assert.equal(late.current_answer_key, "taking");
});

test("④-b 같은 화면 안에서는 순번이 도착 순서를 이긴다", async () => {
  const api = loadApi();
  const tracker = api.createSignalTracker(undefined, memoryBox());

  const a = tracker.next("taking");
  const b = tracker.next("stopped_side_effect");

  // 일부러 뒤집어 보낸다 — 2번을 먼저, 1번을 나중에.
  await api.checkinApi.signal("t", "stopped_side_effect", b.session, b.sequence);
  const late = await api.checkinApi.signal("t", "taking", a.session, a.sequence);

  assert.equal(late.current, false);
  assert.equal(late.current_answer_key, "stopped_side_effect", "같은 화면인데 도착 순서가 순번을 이겼다");
});
