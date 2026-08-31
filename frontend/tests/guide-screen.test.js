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

/* ── 고치기 ──────────────────────────────────────────────────────────── */

test("**「수정」은 판 머리 오른쪽 끝에 있다** — 항목 블록 안이 아니다", () => {
  const { guideScreenHtml, guideSectionHtml } = box();
  const html = guideScreenHtml(SECTIONS, "medication", "guide", true, null);

  /* 「원문 · 환자 화면과 같은 차례」와 같은 줄이다 (와이어프레임 S1-11) */
  const headAt = html.indexOf("환자 화면과 같은 차례");
  const editAt = html.indexOf('data-edit="medication"');
  const bodyAt = html.indexOf("gs__paneBody");
  assert.ok(editAt !== -1, "수정 버튼이 없다");
  assert.ok(headAt < editAt && editAt < bodyAt, "수정이 판 머리 줄에 없다");

  /* **오른쪽 끝**이다 — 원문이 `margin-left:auto` 로 민다. 왼쪽에 붙으면
     제목·곁말과 뭉쳐서 무엇이 버튼인지 안 보인다. */
  const css = codeOnly(read("css/blocks.css"));
  assert.match(rule(css, ".gs__edit"), /margin-left:\s*auto/, "수정이 오른쪽 끝으로 안 밀린다");

  /* 항목 블록에는 없어야 한다 — 한 탭에 항목이 둘일 때 버튼도 둘이 된다 */
  assert.ok(
    !guideSectionHtml(SECTIONS[0], true, null).includes("data-edit="),
    "항목 블록에도 수정 버튼이 남았다",
  );
});

test("**열쇠는 항목 이름이 아니라 `key` 다** — 서버가 그것으로 받는다", () => {
  const { guideHeadEditHtml } = box();
  const html = guideHeadEditHtml(SECTIONS, "medication", true, null);

  /* 전에는 한글 제목을 담고 있어서 눌러도 보낼 데가 없었다.
     서버는 `PATCH /guide/sections/{key}` 로 받는다. */
  assert.ok(html.includes('data-edit="medication"'), "고치기 열쇠가 key 가 아니다");
  assert.ok(!html.includes("복약지도"), "한글 제목을 열쇠로 쓴다");
});

test("**한 탭에 수정 버튼은 하나다** — 주의사항 탭에는 응급이 함께 온다", () => {
  const { guideScreenHtml, guideHeadEditHtml } = box();

  const html = guideScreenHtml(SECTIONS, "caution", "guide", true, null);
  const count = (html.match(/data-edit="/g) || []).length;
  assert.equal(count, 1, `수정 버튼이 ${count}개다 — 하나는 잠긴 응급 문장이다`);

  /* 그리고 그 하나는 **탭의 주인**이어야 한다 */
  assert.ok(guideHeadEditHtml(SECTIONS, "caution", true, null).includes('data-edit="caution"'));
});

test("**못 고치는 자리에는 안 그린다** — 이유는 항목 블록이 말한다", () => {
  const { guideHeadEditHtml } = box();

  /* 응급은 식약처 기준 문장이라 잠겨 있다 */
  assert.equal(guideHeadEditHtml(SECTIONS, "emergency", true, null), "");
  /* 의사 차례가 아니면 */
  assert.equal(guideHeadEditHtml(SECTIONS, "medication", false, null), "");
  /* 이미 고치는 중이면 — 저장·취소가 아래 있다 */
  assert.equal(guideHeadEditHtml(SECTIONS, "medication", true, "medication"), "");
});

test("**제자리에서 고친다** — 창을 띄우면 미리보기가 가려진다", () => {
  const { guideSectionHtml } = box();
  const editing = guideSectionHtml(SECTIONS[0], true, "medication");

  assert.ok(editing.includes("<textarea"), "고치는 칸이 없다");
  assert.ok(editing.includes('data-edit-box="medication"'), "어느 항목인지 안 붙는다");
  assert.ok(editing.includes("복약 본문"), "지금 글이 안 채워진다 — 처음부터 다시 쓰게 된다");
  assert.ok(editing.includes("data-edit-save"), "저장할 것이 없다");
  assert.ok(editing.includes("data-edit-cancel"), "무를 길이 없다");

  /* 고치는 중에는 「수정」 버튼이 없어야 한다 — 둘이 같이 있으면 어느 것을
     눌러야 하는지 묻게 된다 */
  assert.ok(!editing.includes('data-edit="medication"'), "고치는 중에 수정 버튼이 남았다");
});

test("**잠긴 항목은 못 고친다** — 식약처 기준 문장이다", () => {
  const { guideSectionHtml } = box();
  const locked = guideSectionHtml(SECTIONS[2], true, "emergency");

  assert.ok(!locked.includes("<textarea"), "잠긴 항목에 고치는 칸이 열렸다");
  assert.ok(locked.includes("고칠 수 없습니다"), "왜 못 고치는지 안 말한다");
});

test("**두 화면이 같은 배선을 쓴다** — 두 벌이면 한쪽만 고쳐진다", () => {
  const view = codeOnly(read("js/guide-view.js"));
  assert.ok(view.includes("function wireGuideEditing"), "공용 배선이 없다");

  for (const js of ["js/visit-guide.js", "js/doctor.js"]) {
    const code = codeOnly(read(js));
    /* **줄 처음에 와야 한다.** 그냥 `includes` 로 재면 `if (false) wireGuideEditing(`
       처럼 감싸도 통과한다 — 돌연변이를 넣어 보고 알았다. */
    assert.match(
      code,
      /(^|\n)\s*wireGuideEditing\(\{/,
      `${js} 가 공용 배선을 조건 없이 부르지 않는다`,
    );
    /* 각자 처리기를 또 만들면 안 된다 */
    assert.ok(!code.includes('closest("[data-edit-save]")'), `${js} 가 저장을 따로 다룬다`);
  }

  /* 의사 화면의 옛 안내창은 사라져야 한다 — 그 API 는 이미 붙었다 */
  const doc = codeOnly(read("js/doctor.js"));
  assert.ok(!doc.includes("KEY-111"), "「승인 API 가 붙은 뒤입니다」 안내창이 남아 있다");
});

test("**빈 글로 덮지 않는다** — 환자가 받는 글이다", () => {
  const view = codeOnly(read("js/guide-view.js"));
  const at = view.indexOf("function wireGuideEditing");
  const body = view.slice(at);

  assert.ok(body.includes("if (!text)"), "빈 글도 저장한다 — 그 항목이 빈 채로 나간다");
  assert.match(body, /비울 수는 없습니다/, "왜 안 되는지 안 말한다");
});

test("**저장이 두 번 가지 않는다** — 판(version)이 두 번 오른다", () => {
  const view = codeOnly(read("js/guide-view.js"));
  const at = view.indexOf("function wireGuideEditing");
  const body = view.slice(at);

  assert.ok(body.includes("save.disabled = true"), "두 번 눌린다");
  assert.ok(body.includes("save.disabled = false"), "실패해도 잠긴 채로 남는다");
});

test("**저장하는 사이 환자를 바꾸면 버린다** — 남의 글을 고친 것이 된다", () => {
  const view = codeOnly(read("js/guide-view.js"));
  const at = view.indexOf("function wireGuideEditing");
  const body = view.slice(at);

  assert.ok(body.includes("var wantedId"), "어느 진료를 고치는지 안 붙잡는다");
  const guards = body.match(/getVisitId\(\) !== wantedId/g) || [];
  assert.equal(guards.length, 2, `답이 온 뒤 확인하는 자리가 ${guards.length}곳이다 — 성공·실패 둘 다여야 한다`);
});

/* ── 환자 화면 시뮬레이션 ────────────────────────────────────────────── */

test("**기기 화면을 흉내낸다** — 카드 몇 장이 아니다", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication");

  assert.ok(html.includes('class="ph"'), "기기 틀이 없다");
  assert.ok(html.includes("ph__tabs"), "탭 줄이 없다");
  assert.ok(html.includes("ph__bar"), "묶음 제목의 막대가 없다");
});

test("**탭 다섯이 맨 위에 있다** — 아래가 아니다 (환자 원문)", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication");

  for (const label of ["복약지도", "주의사항", "생활관리", "현황", "챗봇"]) {
    assert.ok(html.includes(label), `${label} 탭이 없다`);
  }

  /* 환자는 「생활관리」라 부른다 — 의료진 화면의 「생활지도」와 다르다 */
  assert.ok(!html.includes("생활지도"), "환자 화면에 의료진 쪽 이름을 썼다");

  /* 탭이 본문보다 위에 온다 */
  assert.ok(html.indexOf("ph__tabs") < html.indexOf("ph__body-wrap"), "탭이 본문 아래에 있다");
});

test("**보고 있는 항목이 탭에 표시된다** — 응급은 주의사항 탭이다", () => {
  const { guidePreviewHtml } = box();

  const life = guidePreviewHtml(SECTIONS, "life");
  const at = life.indexOf("생활관리");
  assert.ok(life.slice(Math.max(0, at - 60), at).includes("is-on"), "생활관리 탭이 안 켜졌다");

  /* 응급 문장을 볼 때도 환자에게는 「주의사항」 탭이다 */
  const emer = guidePreviewHtml(SECTIONS, "emergency");
  const ca = emer.indexOf("주의사항");
  assert.ok(emer.slice(Math.max(0, ca - 60), ca).includes("is-on"), "응급일 때 주의사항 탭이 안 켜졌다");
});

test("**없는 것을 그리지 않는다** — 상태바 · 노치 · 홈 인디케이터", () => {
  /* 환자 와이어프레임 두 파일 어디에도 없다. 없는 것을 그리면
     「환자가 저렇게 본다」가 거짓이 된다. */
  /* **주석을 걷어낸다.** 「노치를 그리지 않는다」고 적은 내 설명글 때문에
     이 검사가 늘 실패했다 — 같은 함정에 여섯 번째다 (`tests/source.js`). */
  const css = codeOnly(read("css/blocks.css"));
  const code = codeOnly(read("js/guide-view.js"));

  for (const word of ["notch", "노치", "상태바", "status-bar", "home-indicator"]) {
    assert.ok(!css.includes(word), `CSS 에 ${word} 를 그렸다 — 원문에 없다`);
    assert.ok(!code.includes(word), `코드에 ${word} 를 그렸다 — 원문에 없다`);
  }
});

test("**축소는 `zoom` 이다** — `scale` 로 바꾸면 줄바꿈이 달라진다", () => {
  /* 주석에 「`transform: scale` 로 바꾸면」이라 적어 두었더니 그 글자에 걸렸다 */
  const css = codeOnly(read("css/blocks.css"));
  const phone = rule(css, ".ph");

  assert.match(phone, /width:\s*375px/, "환자 화면 폭이 375 가 아니다");
  assert.match(phone, /zoom:/, "축소를 안 한다");
  assert.ok(
    !/transform:\s*scale/.test(phone),
    "scale 로 축소한다 — 안쪽 폭이 300 으로 잡혀 환자가 볼 줄 모양과 달라진다",
  );
});

/* ── 문자 설정 (S1-14) ───────────────────────────────────────────────── */

test("**「문자 설정」은 다른 화면이다** — 원문·미리보기 두 칸이 아니다", () => {
  const { guideScreenHtml } = load("api", "session", "sms-plan", "guide-view");

  const sms = guideScreenHtml(SECTIONS, "messages", "guide", true, null);
  assert.ok(sms.includes("확인 문자"), "회차가 없다");
  assert.ok(sms.includes("소진 임박"), "소진 임박이 없다");
  assert.ok(sms.includes("재진 안내"), "재진 안내가 없다");
  assert.ok(!sms.includes("환자 화면과 같은 차례"), "원문 칸이 그대로 남았다");

  /* 다른 탭에는 회차가 새면 안 된다 */
  const med = guideScreenHtml(SECTIONS, "medication", "guide", true, null);
  assert.ok(!med.includes("확인 문자"), "복약지도 탭에 회차가 샜다");
});

test("**일주일 뒤는 켜진 채로 그려진다** — 끌 수 없는 회차다", () => {
  const { smsLeftHtml } = load("api", "session", "sms-plan", "guide-view");
  const html = smsLeftHtml({ startIso: "2026-08-13", picked: "d7", on: {} });

  /* `on` 이 비어 있어도 일주일 뒤는 켜져야 한다.
     **켜짐을 `aria-pressed` 로 본다** — 글자 ☑ 를 앞뒤 몇 자로 찾으면
     마크업이 조금만 바뀌어도 헛돈다(그렇게 한 번 깨졌다). */
  const at = html.indexOf('data-sms-toggle="d7"');
  assert.notEqual(at, -1, "일주일 뒤 켜고 끄기가 없다");
  const tag = html.slice(at, html.indexOf(">", at));
  assert.ok(tag.includes('aria-pressed="true"'), "일주일 뒤가 꺼진 채로 그려졌다");
  assert.ok(tag.includes('aria-disabled="true"'), "일주일 뒤를 끌 수 있게 두었다");
  assert.ok(html.includes("(고정)"), "고정이라는 것을 안 밝힌다");
});

test("**미리보기는 치환된 실제 발송본이다**", () => {
  const { smsRightHtml } = load("api", "session", "sms-plan", "guide-view");
  const html = smsRightHtml({
    startIso: "2026-08-13",
    picked: "d7",
    text: "{환자명}님, 복약 {일차}일째 확인입니다. {링크}",
    values: { 환자명: "김서연", 일차: 7, 링크: "mg.kr/a3F9x2" },
  });

  assert.ok(html.includes("김서연님, 복약 7일째"), "치환 전 글을 보여 준다");
  assert.ok(html.includes("바이트"), "몇 바이트인지 안 말한다");
  assert.ok(html.includes("08-20 (목)"), "언제 가는지 안 말한다");
});

test("**저장할 자리가 없다는 것을 말한다** — 켤 수 있게 두면 켜 뒀다고 믿는다", () => {
  const { SMS_NOT_SAVED, smsRightHtml } = load("api", "session", "sms-plan", "guide-view");

  assert.match(SMS_NOT_SAVED, /아직 없습니다/, "되는 것처럼 말한다");
  const html = smsRightHtml({ startIso: "2026-08-13", picked: "d7", text: "{링크}" });
  assert.ok(html.includes(SMS_NOT_SAVED), "화면이 그 말을 안 한다");
});

test("**회차를 고르는 것과 켜는 것이 다른 버튼이다** — 보려고 눌렀는데 꺼지면 안 된다", () => {
  const { smsLeftHtml } = load("api", "session", "sms-plan", "guide-view");
  const html = smsLeftHtml({ startIso: "2026-08-13", picked: "d7", on: { d15: true } });

  assert.ok(html.includes('data-sms-toggle="d15"'), "켜고 끄는 버튼이 없다");
  assert.ok(html.includes('data-sms-pick="d15"'), "고르는 버튼이 없다");
});

test("**문구를 고칠 수 있다** — 읽기 전용이면 화면이 거기서 끝난다", () => {
  const { smsRightHtml } = load("api", "session", "sms-plan", "guide-view");
  const html = smsRightHtml({ startIso: "2026-08-13", picked: "d7", text: "{링크}" });

  assert.ok(html.includes("<textarea"), "문구가 읽기 전용이다");
  assert.ok(html.includes("data-sms-text"), "친 것을 받는 자리가 없다");
  assert.ok(html.includes('data-sms-put="{링크}"'), "링크를 넣는 버튼이 없다");
});

test("**「일차」는 고른 회차의 날수다** — 7일째 문자에 15가 뜨면 안 된다", () => {
  const { smsRightHtml } = load("api", "session", "sms-plan", "guide-view");

  const tpl = "복약 {일차}일째";
  assert.ok(smsRightHtml({ startIso: "2026-08-13", picked: "d7", text: tpl }).includes("복약 7일째"));
  assert.ok(smsRightHtml({ startIso: "2026-08-13", picked: "d15", text: tpl }).includes("복약 15일째"));
});

test("**두 화면이 같은 배선을 쓴다**", () => {
  for (const js of ["js/visit-guide.js", "js/doctor.js"]) {
    const code = codeOnly(read(js));
    assert.match(code, /(^|\n)\s*wireSmsSettings\(\{/, `${js} 가 문자 설정 배선을 안 쓴다`);
    /* 환자를 옮기면 지운다 — 앞 사람에게 고친 문구가 남으면 남의 문자다 */
    assert.ok(code.includes("smsForget()"), `${js} 가 앞 환자의 문구를 안 지운다`);
  }
});

test("**치는 사이 커서가 안 튄다** — 다시 그리면 innerHTML 이 통째로 바뀐다", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  assert.ok(code.includes("keepCaretAround"), "커서를 안 지킨다");
  assert.ok(code.includes("setSelectionRange"), "치던 자리를 안 되돌린다");
});

/* ── 승인 · 되돌리기 ─────────────────────────────────────────────────── */

test("**승인 버튼이 실제로 눌린다** — 그리기만 하고 받는 자리가 없었다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.ok(code.includes('closest("#final-approve")'), "승인을 누른 것을 안 받는다");
  assert.ok(code.includes('closest("#final-return")'), "되돌리기를 누른 것을 안 받는다");
  assert.ok(code.includes("doctorApi\n      .approve("), "승인을 서버에 안 보낸다");
});

test("**넘어오기 전에는 못 누른다** — 눌러서 409 를 받으면 「내가 뭘 잘못했나」로 읽힌다", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  const at = code.indexOf("function renderFinalActions");
  const body = code.slice(at, at + 1400);

  assert.ok(body.includes('guide.status === "APPROVAL_PENDING"'), "상태를 안 본다");
  assert.ok(body.includes("disabled"), "승인 전에도 눌린다");
  /* 왜 못 누르는지를 대신 말한다 */
  assert.match(body, /스탭이 확인 중입니다/, "왜 지금 안 되는지 안 말한다");
  assert.match(body, /이미 승인되어/, "이미 승인된 것을 안 가른다");
});

test("**사유 없이 되돌리지 않는다** — 그 문장이 스탭 알림에 그대로 뜬다", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  const at = code.indexOf('closest("#final-return")');
  const body = code.slice(at, at + 1200);

  assert.ok(body.includes("prompt("), "사유를 안 묻는다");
  assert.match(body, /무엇을 고쳐야 하는지/, "무엇을 적어야 하는지 안 말한다");
  assert.ok(/if \(!String\(why\)\.trim\(\)\)/.test(body), "빈 사유로 보낸다");
});

test("**승인하면 다시 불러온다** — 상태가 바뀌고 발송이 예약된다", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  const at = code.indexOf("doctorApi\n      .approve(");
  assert.notEqual(at, -1, "승인을 서버에 안 보낸다 — 검사가 헛돈다");

  /* 잠그는 것은 **부르기 앞**이라 뒤만 보면 못 찾는다 — 그렇게 한 번 헛돌았다.
     앞뒤를 함께 본다. */
  const around = code.slice(Math.max(0, at - 300), at + 700);

  assert.ok(around.includes("loadGuide("), "안내문을 다시 안 부른다");
  assert.ok(around.includes("loadTimeline("), "현황을 다시 안 부른다 — 예약된 문자가 안 뜬다");
  assert.ok(around.includes("go.disabled = true"), "두 번 눌린다");
  assert.ok(around.includes("go.disabled = false"), "실패해도 잠긴 채로 남는다");
});

test("**두 탭 모두에 알린다** — 한쪽에만 쓰면 결과가 어디에도 안 보인다", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  const at = code.indexOf("function say(");
  const body = code.slice(at, at + 300);

  assert.ok(body.includes("guide-say"), "안내문 탭에 안 쓴다");
  assert.ok(body.includes("final-say"), "최종 확인 탭에 안 쓴다");
});
