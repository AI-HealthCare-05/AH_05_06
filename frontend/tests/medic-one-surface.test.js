/* **의사와 스탭이 같은 화면을 본다** — 역할은 버튼만 가른다.
 *
 * 1차 시연에서 의사와 스탭이 서로의 화면을 못 봐서 막혔다. 원인은 화면을
 * 역할로 나눈 것이었는데, **와이어프레임은 그렇게 그린 적이 없다.**
 *
 *     D1-1 골격   「좌 320 목록 / 우 960 본문 → 5단계 탭 → 카드 1장」
 *     D1-5 골격   「5단계 탭은 여전히 최종 확인 ●」
 *     D1-6 골격   「5단계 탭에서 현황 ●」
 *
 * 21프레임(S1-1~14 · D1-1~7)이 환자 카드 한 화면의 다섯 탭이다.
 *
 * 서버도 처음부터 그렇게 되어 있었다 — `app/core/rbac.py` 에서 조회·업로드·
 * 안내문 작성은 staff·doctor 둘 다이고 승인·반려만 doctor 다. 화면만 어긋나
 * 있었다.
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

/* ── 다섯 탭이 다 열려 있는가 ─────────────────────────────────────────── */

test("**환자 카드의 다섯 탭이 하나도 잠겨 있지 않다**", () => {
  const { VISIT_STEPS, stepsHtml } = load("api", "step-nav");
  const tabs = VISIT_STEPS;
  assert.strictEqual(tabs.length, 5, `탭이 다섯이 아니다: ${tabs.length}`);

  /* 공용 모듈이 실제로 그리는 결과를 본다. patients.html의 정적 복사본을 세면
     공용 정의와 HTML이 어긋나도 검사하지 못한다. */
  const rendered = stepsHtml("basic", "/patients.html", 12);
  assert.strictEqual((rendered.match(/role="tab"/g) || []).length, 5);
  assert.ok(!rendered.includes("tab--later") && !rendered.includes('aria-disabled="true"'));
});

test("탭에 붙일 패널이 실제로 있다 — 없으면 눌러도 빈 화면이다", () => {
  const html = read("patients.html");
  for (const name of ["basic", "guide", "final", "status"]) {
    assert.ok(html.includes(`id="panel-${name}"`), `panel-${name} 이 없다`);
  }

  /* 「진료기록」만 판이 없다 — 그 칸은 판독 화면(`/ocr-review.html`)이다.
     전에는 여기에도 업로드 판이 있어서 같은 칸에 두 화면이었다. */
  assert.ok(!html.includes('id="panel-record"'), "진료기록 판이 두 화면에 다 있다");
});

test("**다섯 칸을 다 안다 — 넷은 판으로, 하나는 다른 화면으로**", () => {
  const source = read("js/detail.js");
  assert.match(source, /VISIT_STEPS\.filter\(/, "환자 화면의 탭 목록이 공용 단계 정의에서 나오지 않는다");

  /* 화면에 그려진 다섯 칸이 모두 어딘가로 이어져야 한다 — 하나라도 빠지면
     눌러도 아무 일이 없다. */
  const { VISIT_STEPS, stepsHtml } = load("api", "step-nav");
  const samePage = VISIT_STEPS.filter((step) => step.page === "/patients.html").map((step) => step.key);
  assert.deepEqual(Array.from(samePage), ["basic", "guide", "final", "status"]);
  assert.match(stepsHtml("basic", "/patients.html", 12), /data-tab="record"[^>]*data-href=/, "진료기록의 이동 주소가 없다");
});

/* ── 역할은 버튼만 가른다 ─────────────────────────────────────────────── */

test("**승인·반려는 의사만** — 스탭에게는 이유를 말한다", () => {
  const { finalActionsFor } = load("api", "guide-view", "visit-guide");

  const doctor = finalActionsFor(["doctor"]);
  assert.strictEqual(doctor.canApprove, true);
  assert.strictEqual(doctor.canReturn, true);
  assert.strictEqual(doctor.why, "", "의사에게는 막는 이유가 없다");

  const staff = finalActionsFor(["staff"]);
  assert.strictEqual(staff.canApprove, false, "스탭이 승인할 수 있으면 서버가 403 을 준다");
  assert.strictEqual(staff.canReturn, false);
  assert.match(staff.why, /의사 계정/, "왜 못 누르는지 말하지 않는다");
});

test("두 역할을 다 가지면 의사 쪽이 이긴다 — rbac 의 OR 규칙과 같다", () => {
  const { finalActionsFor } = load("api", "guide-view", "visit-guide");
  assert.strictEqual(finalActionsFor(["staff", "doctor"]).canApprove, true);
});

test("역할이 비어 있거나 없어도 죽지 않는다", () => {
  const { finalActionsFor } = load("api", "guide-view", "visit-guide");
  assert.strictEqual(finalActionsFor([]).canApprove, false);
  assert.strictEqual(finalActionsFor(null).canApprove, false);
  assert.strictEqual(finalActionsFor(undefined).canApprove, false);
});

/* ── 안내문이 없을 때 ────────────────────────────────────────────────── */

test("안내문이 없으면 다음에 할 일을 말한다 — 서버 문구는 흘리지 않는다", () => {
  const { guideMissingSaying } = load("api", "guide-view", "visit-guide");

  const none = guideMissingSaying({ code: "GUIDE_NOT_FOUND", message: "환자 윤지아 · 비잔정" });
  assert.match(none, /진료기록/, "어디로 가야 하는지 말하지 않는다");
  assert.ok(!none.includes("윤지아"), `서버 문구가 새어 나왔다: ${none}`);

  assert.match(guideMissingSaying({ code: "FORBIDDEN" }), /권한/);
  assert.match(guideMissingSaying({}), /다시 열어/);
});

/* ── 같은 안내문을 두 번 구현하지 않았는가 ────────────────────────────── */

test("**안내문 그리는 규칙이 한 곳에만 있다** — 두 벌이면 화면마다 다른 말이 나온다", () => {
  const shared = read("js/guide-view.js");
  assert.match(shared, /function guideSectionHtml\(/, "공용 모듈에 규칙이 없다");

  /* 의사 화면이 자기 것을 따로 갖고 있으면 안 된다. 옮기기 전에는 여기에
     `sectionHtml` · `SECTION_LABEL` · `TUCKED_UNDER` 가 다 있었다. */
  const doctor = read("js/doctor.js");
  assert.ok(!doctor.includes("function sectionHtml("), "의사 화면이 규칙을 또 갖고 있다");
  assert.ok(!doctor.includes("var SECTION_LABEL"), "섹션 이름표가 두 벌이다");
  assert.ok(!doctor.includes("var TUCKED_UNDER"), "응급 접기 규칙이 두 벌이다");

  /* 두 화면 모두 공용 모듈을 싣고 있어야 한다 — 안 실으면 그리다 죽는다. */
  assert.ok(read("doctor.html").includes("/js/guide-view.js"), "의사 화면이 공용 모듈을 안 싣는다");
  assert.ok(read("patients.html").includes("/js/guide-view.js"), "환자 카드가 공용 모듈을 안 싣는다");
});
