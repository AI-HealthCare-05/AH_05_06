/* 미리보기가 **환자 렌더러와 갈리지 않는다** — KEY-286.
 *
 * 「환자가 받는 그대로」라고 적어 둔 자리가 실제 환자 화면과 **완전히 다른
 * 렌더러**였다. 환자는 `.card` 레이아웃을 받는데 미리보기는 납작한
 * `.ph__block` 을 보였고, 탭도 다섯(환자는 넷)이었다.
 *
 * 이제 환자 자신의 스타일시트를 신은 iframe 이라 **모양은 갈릴 수 없다.**
 * 갈릴 수 있는 것은 **이름**이다 — 클래스가 하나 어긋나면 스타일이 안 붙고,
 * 빈 상태 문구가 어긋나면 환자와 스탭이 다른 말을 본다.
 *
 * 그래서 여기서는 미리보기가 쓰는 이름들을 **환자 렌더러 소스에 대고** 잰다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");
const { codeOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");
const patientSource = () => codeOnly(fs.readFileSync(path.join(ROOT, "patient_wireframe/js/guide.js"), "utf8"));
const patientCss = () => fs.readFileSync(path.join(ROOT, "patient_wireframe/css/guide.css"), "utf8");
const box = () => load("api", "session", "patient-guide-cards", "guide-view");

const SECTIONS = [
  { key: "medication", body: "복약 안내 본문" },
  { key: "caution", body: "주의 본문" },
  { key: "emergency", body: "응급 본문" },
  { key: "life", body: "생활 본문" },
];

test("**쓰는 클래스가 환자 렌더러에 실제로 있다** — 하나만 어긋나도 모양이 무너진다", () => {
  const { guidePreviewHtml } = box();
  const source = patientSource();
  const css = patientCss();

  const html = ["medication", "caution", "life"].map((k) => guidePreviewHtml(SECTIONS, k)).join("");
  const used = new Set([...html.matchAll(/class=&quot;([^&]+)&quot;|class="([^"]+)"/g)].flatMap((m) => (m[1] || m[2] || "").split(/\s+/)).filter(Boolean));

  /* 기기 틀(`pv`)만 뺀다 — 그것 하나가 스탭 쪽 것이고 나머지는 전부 환자 것이다.
     전에는 `guide-body` 도 함께 뺐는데, 그 예외가 바로 **환자 화면에 없는 래퍼를
     써도 검사가 안 우는** 구멍이었다 (유가은 님 `#253`). 예외를 늘리지 않는다. */
  for (const name of used) {
    if (name === "pv") continue;
    const inPatient = source.includes(`'${name}'`) || source.includes(`"${name}"`) || source.includes(`${name}'`);
    const inCss = css.includes("." + name);
    assert.ok(inPatient || inCss, `환자 화면에 없는 이름을 쓴다: ${name}`);
  }
});

test("**빈 상태 문구를 지어내지 않는다** — 환자가 보는 말 그대로다", () => {
  const { guidePreviewHtml } = box();
  const source = patientSource();

  const empty = guidePreviewHtml([], "medication") + guidePreviewHtml([], "caution") + guidePreviewHtml([], "life");
  const sayings = [
    "표시할 승인 복약 안내가 아직 없어요.",
    "표시할 승인 주의사항이 아직 없어요.",
    "표시할 승인 생활관리 안내가 아직 없어요.",
  ];

  for (const saying of sayings) {
    assert.ok(source.includes(saying), `환자 렌더러에 없는 문구다 — ${saying}`);
    assert.ok(empty.includes(saying), `빈 상태에서 그 말을 안 한다 — ${saying}`);
  }
});

test("**탭 이름이 환자 것과 같다** — 환자가 바꾸면 여기가 운다", () => {
  const { PATIENT_TAB_KEYS } = box();
  const source = patientSource();

  const found = source.match(/var TABS\s*=\s*\[([^\]]+)\]/);
  assert.ok(found, "환자 렌더러의 TABS 를 못 찾았다");
  const patientTabs = found[1].split(",").map((s) => s.trim().replace(/^'|'$/g, ""));

  assert.deepEqual(PATIENT_TAB_KEYS, patientTabs, "탭 목록이 환자 화면과 다르다");
});

test("**못 채우는 카드는 안 그린다** — 빈 카드는 「목표가 안 잡혔네」로 읽힌다", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication", "오늘 진료 요약 본문");

  /* 채울 수 있는 둘 */
  assert.ok(html.includes("오늘 진료 요약"), "요약 카드가 없다");
  assert.ok(html.includes("이 약을 왜 드시나요"), "복약 문구 카드가 없다");

  /* 파생을 안 받은 자리 — 목업이나 옛 응답이다. 모르는 것을 그리지 않는다.
     이제 스탭 종점은 이 값을 준다(KEY-294) — 받았을 때 무엇을 그리는지는
     `key294-preview-cards.test.js` 가 잰다. */
  for (const title of ["나의 목표", "처방받은 약", "약별 복용 방법", "다음 방문 계획"]) {
    assert.ok(!html.includes(title), `채울 수 없는 카드를 그렸다 — ${title}`);
  }
});

test("**빈 카드 대신 환자의 빈 상태를 쓴다** — 요약이 없을 때", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication");

  assert.ok(html.includes("오늘 진료 요약"), "요약 카드 자체는 선다");
  assert.ok(html.includes("표시할 승인 복약 안내가 아직 없어요."), "환자의 빈 상태를 안 쓴다");
});

test("🚨 응급은 주의사항 탭 안에 위험 카드로 온다 — KEY-161", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "caution");

  assert.ok(html.includes("card--danger"), "위험 카드가 없다");
  assert.ok(html.includes("바로 병원에 연락하세요"), "환자가 보는 제목이 아니다");
  assert.ok(html.includes("응급 본문"), "응급 문장이 안 실렸다");
  assert.ok(html.includes("주의 본문"), "일반 주의가 같이 안 왔다");
});

test("**토큰도 환자 식별자도 안 실린다** — 인수조건 6", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml(SECTIONS, "medication", "요약");

  /* 미리보기는 `sections` 와 `summary` 만 받는다. 그 밖의 것이 들어올 길이
     없어야 하고, 스크립트도 안 싣는다(iframe 이 도는 코드를 늘리면 안 된다). */
  assert.ok(!/#t=|\/api\/v1\/guides\//.test(html), "링크 토큰이 실렸다");
  assert.ok(!html.includes("<script"), "미리보기가 스크립트를 싣는다");
  /* 모래상자를 쓰되 `allow-scripts` 는 없다 — 그 둘이 함께 있으면 안에서
     제 모래상자를 풀 수 있다. 스타일시트를 실으려고 `allow-same-origin` 만 연다. */
  assert.ok(html.includes('sandbox="allow-same-origin"'), "iframe 을 안 가뒀다");
  assert.ok(!html.includes("allow-scripts"), "모래상자 안에서 코드가 돌 수 있다");
});

test("**따옴표가 srcdoc 을 안 깨뜨린다** — 본문에 큰따옴표가 오면", () => {
  const { guidePreviewHtml } = box();
  const html = guidePreviewHtml([{ key: "life", body: '따옴표 " 와 & 가 든 문장' }], "life");

  /* `srcdoc` 은 속성이라 큰따옴표 하나가 그 자리에서 문서를 닫는다. */
  assert.ok(!/srcdoc="[^"]*"[^>]*"/.test(html.replace(/&quot;/g, "")), "srcdoc 이 중간에 닫힌다");
  assert.ok(html.includes("&quot;"), "따옴표를 안 감쌌다");
});

/* ── 골격이 환자 것과 같은가 — 유가은 님 `#253` ────────────────────────────
 *
 * 환자 CSS 를 싣기만 해서는 모자란다. 카드 간격(`gap: 12px`)·좌우 여백·스크롤을
 * 만드는 규칙은 `<main class="body">` 에 붙어 있어서, 그 이름을 안 쓰면
 * **CSS 는 실었는데 배치만 환자와 다른** 상태가 된다.
 */

/** `srcdoc` 속성 안의 문서를 되돌린다. 실은 순서가 `&`→`&amp;`, `"`→`&quot;`
    였으므로 푸는 순서는 그 반대다. */
function srcdocOf(html) {
  const m = /srcdoc="([\s\S]*?)"><\/iframe>/.exec(html);
  assert.ok(m, "srcdoc 을 못 찾았다");
  return m[1].replace(/&quot;/g, '"').replace(/&amp;/g, "&");
}

/** 어떤 조각의 **바로 아래 자식**들의 class 목록. 태그 깊이를 세어 고른다 —
    안쪽 카드까지 세면 형제인지 아닌지를 못 가른다. */
function directChildClasses(inner) {
  const out = [];
  let depth = 0;
  const tag = /<(\/?)([a-z]+)([^>]*)>/g;
  let m;
  while ((m = tag.exec(inner))) {
    const closing = m[1] === "/";
    if (!closing) {
      if (depth === 0) {
        const cls = /class="([^"]*)"/.exec(m[3]);
        out.push(cls ? cls[1] : "");
      }
      depth += 1;
    } else {
      depth -= 1;
    }
  }
  return out;
}

test("**iframe 본문이 환자의 `.body` 다** — 없는 래퍼로 감싸면 배치가 갈린다", () => {
  const { guidePreviewHtml } = box();
  const doc = srcdocOf(guidePreviewHtml(SECTIONS, "caution", "요약"));

  assert.ok(!doc.includes("guide-body"), "환자 CSS 에 없는 래퍼로 감쌌다");
  assert.match(doc, /<main class="body">/, "카드를 담는 자리가 환자의 `.body` 가 아니다");

  /* 골격도 환자 것 그대로 — `.app` 안에 탭 줄을 인 `.header`, 그 아래 `.body`. */
  assert.match(doc, /<div class="app"><header class="header">/, "환자 골격(`.app` · `.header`)이 아니다");
  assert.match(doc, /<header class="header"><div class="tab-bar"/, "탭 줄이 머리 안에 없다");
});

test("**카드가 `.body` 의 직계 형제다** — 그래야 12px 간격이 붙는다", () => {
  const { guidePreviewHtml } = box();
  const doc = srcdocOf(guidePreviewHtml(SECTIONS, "caution", "요약"));

  const inner = /<main class="body">([\s\S]*)<\/main>/.exec(doc);
  assert.ok(inner, "`.body` 안을 못 읽었다");

  /* 주의사항 탭이 이 차이가 가장 잘 드러나는 자리다 — 제목·주의 카드·응급 카드
     셋이 이어 붙는다. 사이에 래퍼가 하나라도 끼면 `gap` 이 그 래퍼에만 걸린다. */
  const kids = directChildClasses(inner[1]);
  assert.deepEqual(kids, ["tab-title", "card", "card card--danger"], `직계 자식이 환자 화면과 다르다 — ${JSON.stringify(kids)}`);

  /* 간격을 만드는 규칙이 실제로 환자 CSS 의 `.body` 에 있는지도 함께 본다.
     여기만 맞고 저쪽 규칙이 사라지면 이 검사는 거짓으로 통과한다. */
  const rule = /\.body\s*\{([^}]*)\}/.exec(patientCss());
  assert.ok(rule, "환자 CSS 에서 `.body` 규칙을 못 찾았다");
  assert.match(rule[1], /gap:\s*12px/, "환자 화면의 카드 간격이 12px 가 아니다 — 미리보기 기대값을 고쳐야 한다");
  assert.match(rule[1], /overflow-y:\s*auto/, "환자 화면의 본문이 스크롤 영역이 아니다");
});

test("**제목 없는 카드는 제목 칸을 안 세운다** — 도려내지 않는다", () => {
  const { guidePreviewHtml } = box();
  const doc = srcdocOf(guidePreviewHtml(SECTIONS, "caution"));

  assert.ok(!doc.includes('<div class="card__section-title"></div>'), "빈 제목 칸이 남았다");
  assert.match(doc, /<div class="card card--danger"><div class="danger-title">/, "🚨 카드가 곧바로 제목으로 시작하지 않는다");
});

test("**스타일시트가 환자 화면과 같은 벌이다** — 버전이 어긋나면 옛 캐시본이 뜬다", () => {
  const { guidePreviewHtml } = box();
  const doc = srcdocOf(guidePreviewHtml(SECTIONS, "medication"));

  const hrefsIn = (text) =>
    [...text.matchAll(/<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"/g)].map((m) => m[1]);

  const page = fs.readFileSync(path.join(ROOT, "guide.html"), "utf8");
  const want = hrefsIn(page.replace(/\s*\/?>/g, ">").replace(/href="([^"]+)"\s*/g, 'href="$1" '));

  assert.ok(want.length >= 2, `환자 화면의 스타일시트를 못 읽었다 — ${JSON.stringify(want)}`);
  assert.deepEqual(
    hrefsIn(doc),
    want,
    "미리보기가 신는 스타일시트가 `frontend/guide.html` 과 다르다 — 버전 쿼리까지 같아야 한다",
  );
});
