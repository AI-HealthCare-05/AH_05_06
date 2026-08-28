/* 의사 화면의 진행 단계가 **눌러서 갈 수 있는가** — KEY-204.
 *
 * 다섯 칸(기본정보 · 진료기록 · 안내문 · 최종 확인 · 현황)이 `<li>` 로만 적혀
 * 있어서 눌러도 아무 일이 없었다. 앞 두 칸은 스탭 화면(`patients.html`)에 있고,
 * 뒤 셋은 이 화면이거나(안내문 · 최종 확인) 아직 없다(현황 — D1-6·D1-7).
 *
 * ## 무엇을 재는가
 *
 * 「버튼처럼 생겼는가」가 아니라 **갈 수 있는가**를 잰다. `<li>` 를 `<button>`
 * 으로 바꿔 놓고 클릭을 안 받으면 겉만 바뀐 것이고, 키보드로는 여전히 못 닿는다.
 */

const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/* 진행 단계 다섯. 앞 둘만 다른 화면으로 간다. */
const STEPS = [
  ["basic", "기본정보", true],
  ["record", "진료기록", true],
  ["guide", "안내문", false],
  ["final", "최종 확인", false],
  ["status", "현황", false],
];

/* ── 생김새 ─────────────────────────────────────────────── */

test("다섯 칸이 **버튼**이다 — `<li>` 로는 키보드가 못 닿는다", () => {
  const html = read("doctor.html");
  const box = html.slice(html.indexOf('<div class="steps"'), html.indexOf("</div>", html.indexOf('<div class="steps"')));

  assert.ok(!/<li class="step/.test(html), "아직 `<li class=\"step\">` 이 남아 있다");
  for (const [key, label] of STEPS) {
    const line = box.split("\n").find((l) => l.includes(`data-step="${key}"`));
    assert.ok(line, `${label} 칸에 data-step="${key}" 가 없다`);
    assert.match(line, /<button /, `${label} 이 버튼이 아니다 — 눌러도 키보드로 못 닿는다`);
  }
});

test("갈 수 있는 칸과 아닌 칸이 갈려 있다", () => {
  const html = read("doctor.html");
  const box = html.slice(html.indexOf('<div class="steps"'), html.indexOf("</div>", html.indexOf('<div class="steps"')));

  for (const [key, label, goes] of STEPS) {
    const line = box.split("\n").find((l) => l.includes(`data-step="${key}"`));
    const blocked = /aria-disabled="true"/.test(line);
    assert.equal(
      blocked,
      !goes,
      goes
        ? `${label} 은 스탭 화면으로 가야 하는데 aria-disabled 다`
        : `${label} 은 갈 곳이 없는데 눌리게 열려 있다 — 눌러도 아무 일이 없으면 고장으로 읽힌다`,
    );
  }
});

/* ── 이동 ───────────────────────────────────────────────── */

test("**어느 진료인지 실어 보낸다** — 목록만 열면 사람을 다시 찾아야 한다", () => {
  const source = read("js/doctor.js");
  const at = source.indexOf('closest("[data-step]")');
  assert.ok(at !== -1, "진행 단계 분기가 없다 — 눌러도 아무 일이 없다");

  const branch = source.slice(at, source.indexOf("data-section", at));
  assert.match(branch, /patients\.html\?visit=/, "어느 진료인지 안 싣는다");
  assert.match(branch, /visit\.visit_id/, "지금 열어 둔 진료의 번호를 안 쓴다");
  assert.match(branch, /open=/, "어느 탭을 열지 안 싣는다");
  assert.match(branch, /encodeURIComponent/, "값을 그대로 주소에 끼운다");
});

test("잠긴 칸은 걸러내고, 아무것도 안 열렸으면 안 간다", () => {
  const source = read("js/doctor.js");
  const at = source.indexOf('closest("[data-step]")');
  const branch = source.slice(at, source.indexOf("data-section", at));

  assert.match(branch, /aria-disabled/, "잠긴 칸을 안 거른다 — 안내문·현황을 눌러도 나간다");
  assert.match(branch, /if \(!visit\)/, "진료가 안 열린 채로 눌리면 undefined 를 주소에 싣는다");
});

/* ── 받는 쪽 ────────────────────────────────────────────── */

function shell(search) {
  return load("api", "session", "patients-api", "shell", { search });
}

test("**스탭 화면이 그 값을 읽는다** — 안 읽으면 보내 봐야 소용없다", () => {
  const box = shell("?visit=42&open=record");

  assert.deepEqual(box.entry, { visit_id: 42, open_tab: "record" });
});

test("평소에 들어오면 아무것도 안 바뀐다", () => {
  assert.equal(shell("?mock=1").entry, null, "지목이 없는데 뭔가를 골라 두려 한다");
});

test("진료만 있고 탭이 없으면 기본정보로 연다", () => {
  const box = shell("?visit=7");

  assert.equal(box.entry.visit_id, 7);
  assert.equal(box.entry.open_tab, null, "탭을 안 줬는데 임의로 정한다");
});

test("**한 번 쓰고 버린다** — 목록을 못 쓰게 되면 안 된다", () => {
  const source = read("js/shell.js");
  const at = source.indexOf("function loadDay");
  const body = source.slice(at, source.indexOf("\nfunction ", at + 10));

  assert.match(body, /entry = null/, "쓰고 나서 안 버린다 — 날짜를 옮길 때마다 그 사람으로 끌려간다");
  assert.ok(
    body.indexOf("entry = null") > body.indexOf("syncPane()"),
    "쓰기 전에 버린다 — 지목한 줄이 안 골라진다",
  );
});

test("주소에서 지운다 — 화면을 공유할 때 진료 번호가 따라가지 않게", () => {
  /* shim 에 `history` 가 없어 실제 호출은 못 잰다. 부르려 한다는 것까지만 본다 —
     `typeof history !== "undefined"` 가드가 있어 검사에서는 그냥 건너뛴다. */
  const source = read("js/shell.js");
  const at = source.indexOf("var entry = (function");
  const body = source.slice(at, source.indexOf("})();", at));

  assert.match(body, /q\.delete\("visit"\)/, "주소에서 진료 번호를 안 지운다");
  assert.match(body, /q\.delete\("open"\)/, "주소에서 탭 이름을 안 지운다");
  assert.match(body, /replaceState/, "지운 주소로 바꿔치지 않는다");
});
