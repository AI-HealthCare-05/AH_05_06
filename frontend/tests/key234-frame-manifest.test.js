/* **화면 목록표가 와이어프레임과 어긋나면 운다** — KEY-234.
 *
 * 인수조건 ③ 「설정 누락·중복을 검증할 수 있다」가 이 파일이다.
 *
 * 표(`js/frames.js`)는 손으로 고칠 수 있으므로, 정본인 와이어프레임
 * (`docs/wireframes/*.html` 의 `data-screen-label`)과 매번 대조한다.
 * 프레임을 빠뜨리거나, 없는 번호를 넣거나, 같은 번호를 두 번 적으면 잡힌다.
 *
 * **인수조건 ④ 「핵심 데모 화면에는 적용하지 않는다」도 여기서 잰다.**
 * 이번 주에 올라갈 프레임(`target < 3`)에 안내 화면을 씌우면 같은 주에 두 번
 * 만들게 되고, 9/3 시연 대본이 안내 화면을 지나간다.
 *
 * 화면 IIFE 는 `browser-shim.js` 의 `getElementById` 가 `null` 이라 통째로
 * 건너뛰어진다. 그래서 이 검사는 **IIFE 밖에 있는 표와 함수만** 잰다 —
 * 잴 수 있는 것만 재고, 못 재는 것을 잰 척하지 않는다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..");
const WIREFRAMES = path.join(ROOT, "..", "docs", "wireframes");

/* frames.js 는 브라우저용 전역 스크립트라 `require` 로는 안 읽힌다.
   브라우저와 같은 방식(전역 평가)으로 읽어야 실제 화면과 같은 것을 잰다. */
function loadManifest() {
  const context = { console };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "js", "frames.js"), "utf8"), context);
  return context;
}

function wireframeIds() {
  const ids = [];
  for (const file of fs.readdirSync(WIREFRAMES)) {
    if (!file.endsWith(".html")) continue;
    const html = fs.readFileSync(path.join(WIREFRAMES, file), "utf8");
    for (const found of html.matchAll(/data-screen-label="([A-Z0-9-]+)"/g)) ids.push(found[1]);
  }
  return ids;
}

const { FRAMES, FRAME_AREAS, FRAME_LEVELS, frameById, needsGuideScreen } = loadManifest();

/* 목록을 견줄 때 배열이 아니라 **문자열**로 견준다. vm 컨텍스트에서 만든 배열은
   프로토타입이 이쪽과 달라 `deepStrictEqual` 이 빈 배열끼리도 실패한다. */

/* ── ③ 설정 누락·중복 ─────────────────────────────────────────────────── */

test("와이어프레임의 프레임이 표에 다 있다", () => {
  const missing = wireframeIds().filter((id) => !FRAMES.some((f) => f.id === id));
  assert.strictEqual(missing.join(", "), "", "표에서 빠진 프레임");
});

test("표에 와이어프레임에 없는 번호가 없다", () => {
  const ids = wireframeIds();
  const extra = FRAMES.filter((f) => !ids.includes(f.id)).map((f) => f.id);
  assert.strictEqual(extra.join(", "), "", "와이어프레임에 없는 번호");
});

test("같은 번호가 두 번 적혀 있지 않다", () => {
  const seen = FRAMES.map((f) => f.id);
  const twice = seen.filter((id, at) => seen.indexOf(id) !== at);
  assert.strictEqual(twice.join(", "), "", "두 번 적힌 번호");
});

test("모든 줄이 구분과 수준을 갖는다", () => {
  for (const frame of FRAMES) {
    assert.ok(FRAME_AREAS[frame.area], frame.id + " 의 구분이 낯설다: " + frame.area);
    assert.ok(FRAME_LEVELS[frame.level], frame.id + " 의 수준이 낯설다: " + frame.level);
    assert.ok(FRAME_LEVELS[frame.target], frame.id + " 의 목표가 낯설다: " + frame.target);
  }
});

test("목표가 지금보다 뒤로 가지 않는다", () => {
  /* target 은 「이번 주에 어디까지」다. 지금보다 낮은 수준을 목표로 두면
     표를 잘못 적은 것이다 (수준은 1 이 가장 완성된 상태다). */
  const backwards = FRAMES.filter((f) => f.target > f.level).map((f) => f.id);
  assert.strictEqual(backwards.join(", "), "", "목표가 지금보다 뒤에 있는 프레임");
});

/* ── 1·2단계는 갈 곳이, 3단계는 설명이 있어야 한다 ─────────────────────── */

test("1·2단계는 실제 화면 주소를 갖는다", () => {
  const noUrl = FRAMES.filter((f) => f.level !== 3 && !f.url).map((f) => f.id);
  assert.strictEqual(noUrl.join(", "), "", "갈 곳이 없는 프레임");
});

test("3단계는 무슨 화면인지와 무엇이 필요한지를 말한다", () => {
  /* 인수조건 ② — 안내 화면이 기능 완료를 오인시키지 않으려면, 화면이
     스스로 「무엇을 할 자리이고 무엇이 없어서 아직인가」를 말해야 한다. */
  const silent = FRAMES.filter((f) => f.level === 3 && !(f.role && f.blocker)).map((f) => f.id);
  assert.strictEqual(silent.join(", "), "", "설명이 빈 프레임");
});

/* ── ④ 핵심 데모 화면에는 안 씌운다 ──────────────────────────────────── */

/* **대상을 여기에 적어 둔다.** 「needsGuideScreen 으로 거른 것이
   needsGuideScreen 을 만족하는가」로 재면 조건을 어떻게 바꾸든 늘 통과한다 —
   자기 자신을 재는 검사다(돌연변이로 확인했다). 그래서 **밖에서 정한 목록**과
   견준다. 어떤 프레임이 안내 화면 대상에 들어오거나 빠지면 이 검사가 울고,
   목록을 함께 고치게 되므로 그 변화가 리뷰에 보인다.

   지금 23개다. 팀 계획 문서(`docs/work-packages.md`)는 20으로 적혀 있는데,
   그 숫자는 구조 진단 §6.2 의 **목표치**(완전 36 · 조회 8 · 안내 20)에서 왔고
   현재 상태로 다시 세면 23다. 문서 쪽을 고쳐야 한다.

   D2-3(처방 설정)과 S2-3(발송 예정)이 여기서 빠졌다 — 화면이 생겨 안내할
   자리가 아니라 쓰는 자리가 됐다. 이렇게 하나씩 줄어드는 것이 맞다. */
const GUIDE_SCREEN_FRAMES = [
  "A1-2", "A1-3", "A1-5", "A1-6", "A1-7",
  "D1-4", "D1-6", "D1-7",
  "D2-1", "D2-2", "D2-4", "D2-5",
  "P1-3", "P1-5", "P5-1", "P5-2", "P8-1", "P8-2", "P9",
  "S1-10", "S1-14", "S2-2", "S2-4",
];

test("안내 화면 대상이 정해 둔 목록과 같다", () => {
  const derived = FRAMES.filter(needsGuideScreen)
    .map((f) => f.id)
    .sort()
    .join(", ");
  assert.strictEqual(derived, GUIDE_SCREEN_FRAMES.slice().sort().join(", "));
});

test("이번 주에 올라갈 프레임은 안내 화면 대상이 아니다", () => {
  /* level 3 인데 target 이 3 보다 작은 것 — 이번 주에 화면이 생긴다.
     여기에 안내 화면을 씌우면 같은 주에 두 번 만들게 되고, 9/3 시연 대본이
     안내 화면을 지나간다. 목록에 들어 있으면 안 된다. */
  const climbing = FRAMES.filter((f) => f.level === 3 && f.target < 3).map((f) => f.id);
  const wrong = climbing.filter((id) => GUIDE_SCREEN_FRAMES.indexOf(id) !== -1);
  assert.strictEqual(wrong.join(", "), "", "이번 주에 올라가는데 안내 화면 대상인 프레임");
});

test("안내 화면 대상은 지금 화면이 없는 것뿐이다", () => {
  for (const id of GUIDE_SCREEN_FRAMES) {
    const frame = frameById(id);
    assert.ok(frame, "목록에 있는데 표에 없는 번호: " + id);
    assert.strictEqual(frame.level, 3, id + " 은 화면이 있는데 안내 화면 대상이다");
  }
});

/* ── 조회 함수 ────────────────────────────────────────────────────────── */

test("번호로 찾을 수 있고, 없는 번호는 null 이다", () => {
  assert.strictEqual(frameById("S1-6").id, "S1-6");
  assert.strictEqual(frameById("없는번호"), null);
  assert.strictEqual(frameById(""), null);
});
