/* 「■ 소제목」 카드와 「오늘 진료 요약」 — KEY-365.
 *
 * 카드를 나누는 일은 서버가 한다(`app/services/patient_guide_view.py`). 여기서
 * 재는 것은 두 화면이 **받은 카드를 그대로, 같은 차례로** 그리는가다.
 *
 *   · 환자 화면: `guide-api.js` 가 `guide.blocks` 를 받아 넘기고, 요약이 없으면
 *     본문으로 채우지 않는다. 서버가 현황을 줬으면 본문을 현황에 또 싣지 않는다.
 *   · 스탭·의사 미리보기: `preview` 가 있으면 `sections` 가 아니라 그것으로 그린다.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const { load } = require("./browser-shim.js");
const { codeOnly, read } = require("./source.js");

const HEADED_MEDICATION = "■ 이 약을 복용하는 이유\n합성 이유\n\n■ 복용 안내\n합성 안내";
const SECTIONS = [
  { key: "medication", body: HEADED_MEDICATION },
  { key: "caution", body: "■ 진료 시 알려주세요\n합성 알릴 것" },
  { key: "emergency", body: "합성 응급" },
  { key: "life", body: "■ 수면\n합성 수면\n\n■ 운동\n합성 운동" },
];

/** 서버가 위 `SECTIONS` 로 짓는 파생 — `GuidePreview` 와 환자 응답의 같은 칸들. */
const DERIVED = {
  guide: {
    summary: "자궁내막증으로 진료받으셨고, 비잔정을 처방받으셨어요.",
    goals: [],
    drug: { n: "비잔정 2mg", s: "성분 · 디에노게스트", d: "1일 1회 · 84일분" },
    why: ["합성 이유"],
    how: "1일 1회 · 84일분",
    blocks: [{ t: "복용 안내", p: ["합성 안내"] }],
    next: "합성 다음 방문",
  },
  stat: { drugName: "비잔정 2mg", prescribed: 84 },
  care: { blocks: [{ t: "진료 시 알려주세요", p: ["합성 알릴 것"] }], danger: ["합성 응급"] },
  life: {
    sub: "자궁내막증 · 비잔정 복용 중",
    challenges: [],
    axes: { 수면: { title: "수면", p: ["합성 수면"] }, 운동: { title: "운동", p: ["합성 운동"] } },
  },
};

function preview(overrides = {}) {
  return { visit: "2026.09.17", clinic: "합성여성의원", ...DERIVED, ...overrides };
}

const cards = () => load("api", "session", "patient-guide-cards", "guide-view");

function patientApi() {
  const context = vm.createContext({
    URLSearchParams,
    Date,
    Intl,
    Promise,
    setTimeout,
    sessionStorage: { getItem: () => null, setItem() {} },
    location: { protocol: "https:", hostname: "care-on.test" },
    window: { location: { search: "", hostname: "care-on.test", protocol: "https:" } },
  });
  vm.runInContext(read("patient_wireframe/js/guide-api.js"), context);
  return context;
}

function patientPayload(overrides = {}) {
  return {
    version: 1,
    approved_at: "2026-09-17T09:00:00+09:00",
    expires_at: "2026-09-20T09:00:00+09:00",
    demo_only: true,
    sections: SECTIONS,
    ...DERIVED,
    ...overrides,
  };
}

const plain = (value) => JSON.parse(JSON.stringify(value));

/* 미리보기 HTML 에서 **카드 제목**만 차례대로 뽑는다. */
function titlesOf(html) {
  return [...html.matchAll(/class="card__section-title">([^<]*)</g)].map((match) => match[1]);
}

/* ── 환자 화면이 받는 모델 ──────────────────────────────────────────── */

test("환자 모델이 소제목 카드(`guide.blocks`)를 그대로 넘긴다", () => {
  const model = plain(patientApi().adaptGuideResponse(patientPayload()));

  assert.deepEqual(model.guide.blocks, [{ t: "복용 안내", p: ["합성 안내"] }]);
  assert.deepEqual(model.guide.why, ["합성 이유"]);
});

test("소제목 카드 모양이 어긋나면 계약 오류다 — 모르는 키를 그리지 않는다", () => {
  const api = patientApi();
  const broken = patientPayload({ guide: { ...DERIVED.guide, blocks: [{ t: "가", p: ["나"], html: "<b>" }] } });

  assert.throws(() => api.adaptGuideResponse(broken), (error) => error.code === "GUIDE_CONTRACT_MISMATCH");
});

test("서버가 요약을 안 줬으면 본문으로 채우지 않는다 — 처방 세트 없는 진료", () => {
  const { summary, ...withoutSummary } = DERIVED.guide;
  const model = plain(patientApi().adaptGuideResponse(patientPayload({ guide: withoutSummary })));

  assert.equal(summary.length > 0, true);
  assert.equal(model.guide.summary, "");
});

test("현황이 복약지도 본문을 또 싣지 않는다 — 현황이 있든 없든 서버 파생이 있으면", () => {
  const api = patientApi();

  assert.equal(plain(api.adaptGuideResponse(patientPayload())).stat.body, "");
  const noStat = plain(api.adaptGuideResponse(patientPayload({ stat: null })));
  assert.equal(noStat.stat.body, "");
  assert.equal(noStat.stat.drugName, "");
});

test("옛 sections-only 응답은 예전처럼 본문으로 요약·현황을 채운다(회귀)", () => {
  const model = plain(
    patientApi().adaptGuideResponse({
      version: 1,
      approved_at: "2026-09-17T09:00:00+09:00",
      expires_at: "2026-09-20T09:00:00+09:00",
      demo_only: true,
      sections: [{ key: "medication", body: "합성 옛 본문" }],
    }),
  );

  assert.equal(model.guide.summary, "합성 옛 본문");
  assert.equal(model.stat.body, "합성 옛 본문");
  assert.deepEqual(model.guide.blocks, []);
});

test("환자 렌더러: 요약 카드는 문장이 있을 때만, 소제목 카드는 복용 방법 다음·다음 방문 앞", () => {
  const source = codeOnly(read("patient_wireframe/js/guide.js"));
  const render = source.slice(source.indexOf("function renderGuide"), source.indexOf("function renderCare"));

  assert.match(render, /if \(g\.summary\) \{\s*var sumCard/, "요약이 없어도 요약 카드를 세운다");
  const how = render.indexOf("'약별 복용 방법'");
  const blocks = render.indexOf("g.blocks");
  const next = render.indexOf("'다음 방문 계획'");
  assert.ok(how > 0 && blocks > how && next > blocks, "소제목 카드의 자리가 미리보기와 다르다");
});

/* ── 스탭·의사 미리보기 ──────────────────────────────────────────────── */

test("미리보기 복약지도가 서버 카드를 환자와 같은 차례로 그린다", () => {
  const html = cards().patientMedicationHtml("스탭 요약은 안 쓴다", HEADED_MEDICATION, preview());

  assert.deepEqual(titlesOf(html), [
    "오늘 진료 요약",
    "처방받은 약",
    "이 약을 왜 드시나요",
    "약별 복용 방법",
    "복용 안내",
    "다음 방문 계획",
  ]);
  assert.ok(html.includes(DERIVED.guide.summary), "서버 요약 문장이 안 나온다");
  assert.ok(!html.includes("스탭 요약은 안 쓴다"), "서버 파생이 있는데 스탭 요약을 그렸다");
  assert.ok(!html.includes("■"), "소제목 줄이 본문으로 새었다");
});

test("미리보기: 요약이 없으면 요약 카드도, 여닫기 단추도 없이 펼쳐 둔다", () => {
  const { summary, ...withoutSummary } = DERIVED.guide;
  const html = cards().patientMedicationHtml("스탭 요약", HEADED_MEDICATION, preview({ guide: withoutSummary }));

  assert.equal(summary.length > 0, true);
  assert.ok(!titlesOf(html).includes("오늘 진료 요약"));
  assert.ok(!html.includes("expand-btn"), "위에 접을 카드가 없는데 단추를 세웠다");
  assert.ok(html.includes("expand-body expand-body--open"));
});

test("미리보기 주의사항이 소제목 카드와 🚨 카드를 서버 값으로 그린다", () => {
  const html = cards().patientCautionHtml("■ 진료 시 알려주세요\n합성 알릴 것", "합성 응급", preview());

  assert.deepEqual(titlesOf(html), ["진료 시 알려주세요"]);
  assert.ok(html.includes('class="tab-title__main">복약 중 주의사항<'), "환자 화면과 탭 제목이 다르다");
  assert.ok(html.includes('<div class="danger-item">합성 응급</div>'), "응급 카드가 바뀌었다");
  assert.ok(!html.includes("■"));
});

test("미리보기 생활관리가 칩으로 카드를 고른다 — 환자 renderLife 와 같다", () => {
  const { patientLifeHtml } = cards();

  const first = patientLifeHtml("", preview(), null);
  assert.ok(first.includes('class="tab-title__sub">자궁내막증 · 비잔정 복용 중<'), "부제가 환자와 다르다");
  assert.match(first, /axis-tab--active[^>]*data-preview-axis="수면"/);
  assert.match(first, /axis-tab--inactive[^>]*data-preview-axis="운동"/);
  assert.deepEqual(titlesOf(first), ["수면"]);

  const second = patientLifeHtml("", preview(), "운동");
  assert.deepEqual(titlesOf(second), ["운동"]);
  assert.ok(second.includes("합성 운동") && !second.includes("합성 수면"));
});

test("미리보기 현황이 복약지도 본문을 또 싣지 않는다", () => {
  const { patientStatusHtml } = cards();

  assert.ok(!patientStatusHtml(preview(), HEADED_MEDICATION).includes("합성 이유"));
  assert.ok(!patientStatusHtml(preview({ stat: null }), HEADED_MEDICATION).includes("합성 이유"));
  /* 파생이 없는 옛 응답만 예전처럼 본문을 보인다 */
  assert.ok(patientStatusHtml(null, "합성 옛 본문").includes("합성 옛 본문"));
});

test("미리보기 여닫기 처리기가 생활관리 칩을 받는다", () => {
  const source = codeOnly(read("js/patient-guide-cards.js"));

  assert.match(source, /closest\("\[data-preview-tab\], \[data-preview-expand\], \[data-preview-axis\]"\)/);
});
