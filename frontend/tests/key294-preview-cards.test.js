/* 미리보기가 **환자 화면의 카드 목록까지** 같다 — KEY-294 (KEY-286 후속).
 *
 * KEY-286 은 미리보기를 환자 렌더러와 같은 스타일·같은 골격으로 바꿨지만,
 * **나의 목표 · 처방받은 약 · 약별 복용 방법** 세 카드는 못 그렸다. 스탭
 * 종점이 그 값을 안 줬기 때문이다. 「환자가 받는 그대로」라고 적어 놓고
 * 부분만 보이던 자리가 그것이다.
 *
 * 이제 `GET /visits/{id}/guide` 가 `preview` 를 준다. 여기서 재는 것은
 * **받은 것을 환자와 같은 차례·같은 조건으로 그리는가**다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");
const { codeOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");
const patientSource = () => codeOnly(fs.readFileSync(path.join(ROOT, "patient_wireframe/js/guide.js"), "utf8"));
const box = () => load("api", "session", "patient-guide-cards", "guide-view");

const SECTIONS = [{ key: "medication", body: "이 약은 배란을 돕습니다" }];

/** 서버가 주는 모양 그대로 — `GuidePreview` (`app/dtos/guides.py`). */
function preview(detail) {
  return { visit: "2026.09.09", guide: detail };
}

const FULL = {
  summary: "이 약은 배란을 돕습니다",
  goals: [
    { n: "AMH", now: "7.2", t: "5.0", hasChart: true, rangeLabel: "정상 1.0–5.0" },
    { n: "공복 인슐린", now: null, t: null, hasChart: false, rangeLabel: null },
  ],
  drug: { n: "메트포르민", s: "메트포르민염산염 500mg", d: "1일 2회 식후" },
  why: ["이 약은 배란을 돕습니다"],
  how: "아침·저녁 식후 30분",
  next: null,
};

/* ── 받은 것을 그린다 ──────────────────────────────────────────────── */

test("**세 카드가 다 선다** — 이 티켓이 채우려던 자리다", () => {
  const { guidePreviewHtml } = box();

  const html = guidePreviewHtml(SECTIONS, "medication", "오늘 진료 요약 본문", preview(FULL));

  for (const title of ["오늘 진료 요약", "나의 목표", "처방받은 약", "이 약을 왜 드시나요", "약별 복용 방법"]) {
    assert.ok(html.includes(title), `${title} 카드가 없다`);
  }
  assert.ok(html.includes("메트포르민염산염 500mg"), "성분명이 안 나온다");
  assert.ok(html.includes("아침·저녁 식후 30분"), "복용 방법이 안 나온다");
  assert.ok(html.includes("2026.09.09"), "목표 카드 머리의 진료일이 없다");
});

test("**차례가 환자 화면과 같다** — 요약 · 목표 · 처방약 · 왜 · 복용 방법", () => {
  /* 환자 렌더러의 `renderGuide` 가 세우는 차례다. 카드를 더하다 순서가
     어긋나면 스탭이 승인한 화면과 환자가 받는 화면이 달라 보인다. */
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication", "오늘 진료 요약 본문", preview(FULL));

  const order = ["오늘 진료 요약", "나의 목표", "처방받은 약", "이 약을 왜 드시나요", "약별 복용 방법"];
  const at = order.map((title) => html.indexOf(title));
  assert.deepEqual(
    at.slice().sort((a, b) => a - b),
    at,
    `카드 차례가 환자 화면과 다르다 — ${JSON.stringify(order.map((t, i) => [t, at[i]]))}`,
  );
});

test("**접힌 자리를 펼쳐 둔다** — 승인 전에 읽는 자리라 감추면 안 본 것을 승인한다", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication", "요약", preview(FULL));

  assert.ok(html.includes("expand-body--open"), "접힌 채로 두면 처방약·복용 방법을 못 본다");
  assert.ok(html.includes("expand-btn--open"), "단추가 펼친 모양이 아니다");
  /* 탭 바와 같은 규칙 — 읽는 자리라 움직이지 않는다 */
  assert.match(html, /class=&quot;expand-btn expand-btn--open&quot;[^>]*disabled/, "단추가 눌린다");
});

/* ── 없는 것은 그리지 않는다 ────────────────────────────────────────── */

test("**목표가 없어도 카드는 서고, 환자의 빈 상태를 쓴다**", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication", "요약", preview({ goals: [], why: [] }));

  assert.ok(html.includes("나의 목표"), "환자 화면은 목표가 없어도 이 카드를 세운다");
  assert.ok(
    html.includes("등록된 검사 목표가 없어 차트를 표시하지 않아요."),
    "환자가 보는 빈 상태 문구를 안 쓴다",
  );
  assert.ok(patientSource().includes("등록된 검사 목표가 없어 차트를 표시하지 않아요."), "환자에 없는 말을 지어냈다");
});

test("**처방이 없으면 처방약·복용 방법 카드가 안 선다** — 환자 렌더러의 `if (g.drug)`", () => {
  const { guidePreviewHtml } = box();
  const bare = preview({ goals: [], why: [], drug: null, how: null });
  const html = guidePreviewHtml(SECTIONS, "medication", "요약", bare);

  for (const title of ["처방받은 약", "약별 복용 방법", "다음 방문 계획"]) {
    assert.ok(!html.includes(title), `빈 카드를 세웠다 — ${title}`);
  }
  /* 절 본문이 있으니 「왜 드시나요」 하나는 접힘 자리에 남는다 */
  assert.ok(html.includes("이 약을 왜 드시나요"), "절에서 오는 카드까지 지웠다");

  /* 접힘 자리에 들 것이 하나도 없으면 단추도 안 세운다 — 눌러도 빈 칸이다 */
  const empty = guidePreviewHtml([], "medication", "요약", bare);
  assert.ok(!empty.includes("expand-body"), "속이 빈 접힘 자리를 세웠다");
  assert.ok(!empty.includes("expand-btn"), "열 것이 없는데 단추를 세웠다");
});

test("**파생이 `null` 이어도 무너지지 않는다** — 아직 아무것도 없는 진료", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication", "요약", preview(null));

  assert.ok(html.includes("나의 목표"), "봉투는 왔으므로 목표 카드는 선다");
  assert.ok(html.includes("2026.09.09"), "진료일은 봉투에 있다");
  assert.ok(!html.includes("처방받은 약"), "없는 처방을 그렸다");
});

/* ── 목표 막대 ─────────────────────────────────────────────────────── */

test("**막대의 셈을 환자 원본에서 읽어 대조한다** — 삼각형이 다른 자리에 서면 안 된다", () => {
  /* 🚩 **식을 여기 다시 적지 않는다.**
   *
   * 처음에는 환자의 식을 검사 안에 리터럴로 옮겨 적고 비교했다. 그러면 같은
   * 셈이 **세 벌**이 된다 — 환자 렌더러 · 미리보기 렌더러 · 검사. 환자 쪽을
   * 고쳐도 검사는 조용히 통과한다 (돌연변이로 확인: `pctNum` 을 바꿔도 10개
   * 전부 통과했다).
   *
   * 미리보기 iframe 에는 스크립트가 없어(`sandbox` 에 `allow-scripts` 가 없다)
   * 렌더러 자체를 나눠 쓸 수는 없다. 그러니 **식만이라도 원본에서 읽어** 온다.
   * 옆의 문구 검사들이 이미 그 방식이다.
   */
  const source = patientSource();
  const at = source.indexOf("var center");
  assert.notEqual(at, -1, "환자 원본에서 막대 셈을 못 찾았다 — 검사가 헛돈다");
  const rule = source.slice(at, source.indexOf("function pct(", at));
  assert.match(rule, /function pctNum/, "잘라 온 자리에 셈이 없다 — 검사가 헛돈다");

  /* 환자 원본의 셈을 그대로 돌린다. 이 검사가 아는 것은 **인자 이름뿐**이다. */
  const patientPct = new Function(
    "nowNum",
    "startNum",
    "targetNum",
    "hasStart",
    "hasTarget",
    rule + "\nreturn pctNum(nowNum);",
  );

  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication", "요약", preview(FULL));

  const want = patientPct(7.2, NaN, 5.0, false, true);
  assert.ok(html.includes("left:" + want + "%"), `삼각형 자리가 환자 화면과 다르다 — ${want}% 를 못 찾았다`);
  assert.ok(html.includes("목표 5.0"), "눈금에 목표값이 없다");
  assert.ok(html.includes("지금 7.2"), "값 요약이 없다");
});

test("**값이 없는 목표는 숨기지 않고 그대로 말한다** — 환자 문장 그대로", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication", "요약", preview(FULL));

  assert.ok(html.includes("공복 인슐린"), "값 없는 목표를 지웠다");
  assert.ok(html.includes("결과가 나오면 채워드릴게요"), "환자가 보는 문장을 안 쓴다");
  assert.ok(patientSource().includes("결과가 나오면 채워드릴게요"), "환자에 없는 말을 지어냈다");
});

/* ── 새는 것이 없다 ────────────────────────────────────────────────── */

test("**미리보기가 환자 링크로 가는 길을 그리지 않는다**", () => {
  /* 이 화면은 안내문을 **보여 주기만** 한다. 환자 링크는 발송이 만들고
     (KEY-297), 그 토큰은 화면·로그·커밋 어디에도 안 남긴다 (`AGENTS.md`). */
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication", "요약", preview(FULL));

  assert.ok(!/href=&quot;\/p\//.test(html), "환자 링크 주소를 그렸다");
  assert.ok(!/#t=/.test(html), "링크 조각을 그렸다");
  assert.ok(!/\b01[016-9][-\s]?\d{3,4}[-\s]?\d{4}\b/.test(html), "연락처가 실렸다");
});

/* ── 목업 ───────────────────────────────────────────────────────────── */

test("**목업도 서버와 같은 모양을 준다** — 목업만 옛 미리보기를 보면 안 된다", async () => {
  const { doctorApi } = load("api", "session", "doctor-api");
  const guide = await doctorApi.guide(8801);

  assert.ok(guide.preview, "목업에 `preview` 가 없다 — 목업으로 보면 세 카드가 사라진다");
  assert.ok(guide.preview.visit, "진료일이 없다");
  assert.ok(guide.preview.guide.drug, "처방받은 약을 채울 값이 없다");
  assert.ok(guide.preview.guide.goals.length, "나의 목표를 채울 값이 없다");
  assert.ok(guide.preview.guide.how, "약별 복용 방법을 채울 값이 없다");
});
