/* **안내문 화면** — 와이어프레임 S1-11 · D1-1.
 *
 * 두 프레임은 같은 화면이다. 다른 것은 제목과 아래 버튼뿐이다:
 *
 *   S1-11  「환자가 받게 될 안내문 · 스탭 확인」  [진료기록 재업로드] [의사 승인 요청]
 *   D1-1   「환자가 받게 될 안내문 · 미리보기」    [스탭에 되돌리기]   [승인]
 *
 * 두 벌로 그리면 한쪽만 고쳐지고, 스탭이 본 것과 의사가 보는 것이 달라진다 —
 * 「의사가 보지 않은 글이 환자에게 간다」와 같은 종류의 사고다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly, rule } = require("./source.js");

function box() {
  return load("api", "session", "guide-view");
}

const SECTIONS = [
  { key: "medication", body: "복약 본문", warn: null, locked: false },
  { key: "caution", body: "주의 본문", warn: "확인 부탁", locked: false },
  { key: "emergency", body: "응급 본문", warn: null, locked: true },
  { key: "life", body: "생활 본문", warn: null, locked: false },
  { key: "messages", body: "문자 본문", warn: null, locked: false },
];

/* ── 한 화면, 두 모드 ────────────────────────────────────────────────── */

test("**제목만 다르다** — 나머지는 같은 화면이다", () => {
  const { guideScreenHtml } = box();

  const staff = guideScreenHtml(SECTIONS, "medication", "guide", true);
  const doctor = guideScreenHtml(SECTIONS, "medication", "final", true);

  /* **제목 자리를 짚어서 본다.** 그냥 `includes("미리보기")` 로 재면 오른쪽
     칸 제목(「환자 화면 미리보기」)에 걸려 늘 통과한다 — 그렇게 새어 나갔다. */
  const titleOf = (html) => /<span class="gs__title">([^<]*)<\/span>/.exec(html)[1];

  assert.match(titleOf(staff), /스탭 확인/, "S1-11 제목이 아니다");
  assert.match(titleOf(doctor), /미리보기/, "D1-1 제목이 아니다");
  assert.notEqual(titleOf(staff), titleOf(doctor), "두 모드 제목이 같다");

  /* 제목 줄만 빼면 같아야 한다 — 두 벌이 되면 한쪽만 고쳐진다 */
  const strip = (html) => html.replace(/<span class="gs__title">[^<]*<\/span>/, "");
  assert.equal(strip(staff), strip(doctor), "제목 말고도 다르다 — 두 화면이 갈라졌다");
});

test("**네 항목이 가로로 한눈에 든다** — 세로 목록이 아니다", () => {
  const { guideSegmentsHtml } = box();
  const html = guideSegmentsHtml(SECTIONS, "medication");

  /* 응급은 주의사항 아래로 접힌다 — 따로 탭을 만들면 그 탭을 안 열고 넘긴다 */
  for (const label of ["복약지도", "주의사항", "생활지도", "문자 설정"]) {
    assert.ok(html.includes(label), `${label} 탭이 없다`);
  }
  assert.ok(!html.includes(">응급"), "응급이 따로 탭이 됐다 — 넘겨도 되는 문장이 아니다");

  const tabs = (html.match(/<button class="seg__one/g) || []).length;
  assert.equal(tabs, 4, `탭이 ${tabs}개다 — 넷이어야 한다`);
});

test("고른 탭만 채워진다", () => {
  const { guideSegmentsHtml } = box();
  const html = guideSegmentsHtml(SECTIONS, "life");

  const on = (html.match(/aria-selected="true"/g) || []).length;
  assert.equal(on, 1, `고른 탭이 ${on}개다`);
  assert.match(html, /data-section="life"[^>]*\n?/, "고른 것이 표시되지 않았다");
});

test("**확인 부탁(⚠)이 탭에 보인다** — 원장님은 그것만 보면 된다", () => {
  const { guideSegmentsHtml } = box();
  const html = guideSegmentsHtml(SECTIONS, "medication");
  assert.ok(html.includes("seg__warn"), "확인 부탁 표시가 없다");

  /* 환자에게 나가는 응급 안내(🚨)와 기호를 나눠 쓴다 —
     같은 기호를 쓰면 「누구에게 하는 경고인가」가 섞인다 */
  assert.ok(!html.includes("🚨"), "환자용 기호를 원장님 화면에 썼다");
});

/* ── 원문과 미리보기 ─────────────────────────────────────────────────── */

test("**원문과 환자 화면을 나란히 둔다** — 이 화면의 전부다", () => {
  const { guideScreenHtml } = box();
  const html = guideScreenHtml(SECTIONS, "medication", "guide", true);

  /* `gs__paneHead` · `gs__paneTitle` 까지 걸리지 않게 **낱말 끝**을 본다 —
     처음에 `class="gs__pane` 로 세었더니 10개가 나왔다. */
  const panes = (html.match(/class="gs__pane[ "]/g) || []).length;
  assert.equal(panes, 2, `칸이 ${panes}개다 — 원문과 미리보기 둘이어야 한다`);
  assert.ok(html.includes("원문"), "원문 칸이 없다");
  assert.ok(html.includes("환자 화면 미리보기"), "미리보기 칸이 없다");
});

test("**같은 글이 두 칸에 있다** — 다르면 무엇이 나갈지 모른 채 고친다", () => {
  const { guideScreenHtml, guidePreviewHtml } = box();

  const preview = guidePreviewHtml(SECTIONS, "caution");
  /* 주의사항 탭에는 응급이 함께 온다 */
  assert.ok(preview.includes("주의 본문"), "미리보기에 본문이 없다");
  assert.ok(preview.includes("응급 본문"), "미리보기에 응급 문장이 빠졌다 — 환자는 받는다");

  /* **칸을 갈라서 본다.** 통째로 `includes` 하면 왼쪽 원문에 걸려, 미리보기가
     비어도 통과한다 — 그렇게 새어 나갔다. */
  const html = guideScreenHtml(SECTIONS, "caution", "guide", true);
  const at = html.indexOf('gs__pane--pv');
  assert.notEqual(at, -1, "미리보기 칸이 없다");

  const left = html.slice(0, at);
  const right = html.slice(at);
  assert.ok(left.includes("주의 본문"), "원문 칸에 본문이 없다");
  assert.ok(right.includes("주의 본문"), "미리보기 칸이 비었다 — 무엇이 나갈지 모른 채 고친다");
  assert.ok(right.includes("응급 본문"), "미리보기에 응급 문장이 빠졌다 — 환자는 받는다");
});

test("병원에서만 보는 메모가 있다 — 환자 화면에 안 나간다는 것을 밝힌다", () => {
  const { guideScreenHtml } = box();
  const html = guideScreenHtml(SECTIONS, "medication", "guide", true);
  assert.ok(html.includes("병원에서만 보는 메모"), "메모 줄이 없다");
  assert.match(html, /환자 화면에 안 나갑니다/, "환자에게 안 나간다는 것을 안 밝힌다");
});

/* ── 하단 버튼 ───────────────────────────────────────────────────────── */

test("**스탭 확인 중일 때만 넘길 수 있다**", () => {
  const { guideActionsFor } = box();

  assert.equal(guideActionsFor("STAFF_REVIEW", ["staff"]).canSubmit, true);
  assert.equal(guideActionsFor("APPROVAL_RETURNED", ["staff"]).canSubmit, true, "반려된 것은 다시 스탭 차례다");

  /* 넘긴 뒤에는 버튼을 지운다 — 눌러도 409 로 떨어지는 버튼은
     「내가 뭘 잘못했나」로 읽힌다 */
  assert.equal(guideActionsFor("APPROVAL_PENDING", ["staff"]).canSubmit, false);
  assert.equal(guideActionsFor("SCHEDULED_TO_SEND", ["staff"]).canSubmit, false);
});

test("**어디까지 왔는지 말한다** — 버튼이 사라진 이유가 보여야 한다", () => {
  const { guideActionsFor } = box();

  assert.match(guideActionsFor("STAFF_REVIEW", ["staff"]).say, /의사에게 전달/);
  assert.match(guideActionsFor("APPROVAL_PENDING", ["staff"]).say, /기다리는 중/);
  assert.match(guideActionsFor("SCHEDULED_TO_SEND", ["staff"]).say, /발송/);

  /* 의사에게는 어디서 승인하는지 알려 준다 */
  assert.match(guideActionsFor("APPROVAL_PENDING", ["doctor"]).say, /최종 확인/);
});

/* ── 화면이 실제로 쓴다 ──────────────────────────────────────────────── */

test("**두 탭이 같은 것을 그린다** — 두 벌이면 한쪽만 고쳐진다", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  assert.ok(code.includes("guideScreenHtml("), "안내문 탭이 한 판을 안 그린다");

  /* 옛 세로 탭 자리에 그리면 안 된다 */
  assert.ok(!code.includes("guideTabsHtml("), "옛 세로 탭이 남아 있다");
});

test("**탭을 누르면 바뀐다** — 탭이 본문 안으로 들어갔다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  /* **듣는 자리**를 본다. `el(prefix + "-panel")` 은 그리는 쪽에도 있어서
     그냥 `indexOf` 하면 엉뚱한 데를 잰다 — 처음에 그렇게 헛돌았다. */
  const at = code.indexOf('["guide", "final"].forEach');
  assert.notEqual(at, -1, "탭을 듣는 자리가 없다 — 검사가 헛돈다");

  const body = code.slice(at, at + 600);
  assert.ok(
    body.includes('el(prefix + "-panel")'),
    "본문이 아니라 빈 칸에 붙었다 — 아무것도 안 눌린다",
  );
  assert.ok(body.includes("[data-section]"), "탭을 못 알아본다");
});

test("**고칠 수 있는지를 서버와 같은 규칙으로 정한다**", () => {
  /* 화면이 다른 규칙을 쓰면 눌리는데 저장이 403 으로 떨어져,
     스탭은 「내가 뭘 잘못했나」로 읽는다. */
  const code = codeOnly(read("js/visit-guide.js"));
  const at = code.indexOf("function canEditNow");
  assert.notEqual(at, -1, "규칙이 한 곳에 없다");

  const body = code.slice(at, at + 400);
  assert.ok(body.includes("STAFF_REVIEW"), "스탭 차례를 안 본다");
  assert.ok(body.includes("doctor"), "의사 차례를 안 본다");
});

test("**모양이 두 화면 모두에 닿는다** — 한쪽 파일에 두면 다른 쪽이 민얼굴이다", () => {
  for (const page of ["patients.html", "doctor.html"]) {
    const html = read(page);
    assert.ok(html.includes("/css/blocks.css"), `${page} 가 blocks.css 를 안 싣는다`);
  }
  const css = read("css/blocks.css");
  for (const sel of [".gs", ".seg", ".gs__pane"]) {
    assert.ok(rule(css, sel), `${sel} 규칙이 없다`);
  }
});
