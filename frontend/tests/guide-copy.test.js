/* 안내문 고치기 (D2-1 · D2-2) — KEY-234.
 *
 * 원문 주석: 「의사마다 말하는 방식이 다르고 같은 의사도 일정하지 않다. 문구를
 * 하나로 강제하면 원장님이 안 쓰신다. 대신 **원본을 위에 두어 무엇이 사실이고
 * 무엇이 표현인지 보이게 한다.** 원본은 지워지지 않으므로 언제든 되돌아간다.」
 *
 * **와이어프레임은 「약 하나에 한 장」인데 우리는 처방 세트 한 장이다** —
 * 원본이 처방 세트에 붙어 있고 약 목록이 아직 비어 있다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function rules() {
  return load("api", "settings-rail", "guide-copy-rules");
}

function a_section(over) {
  return Object.assign(
    { section_key: "caution", origin: "[합성] 원본 문구입니다.", body: null, editable: true },
    over || {},
  );
}

function a_set(over) {
  return Object.assign(
    {
      prescription_set_id: 1,
      name: "자궁내막증 · 비잔 (계속)",
      disease: "ENDOMETRIOSIS",
      reviewed: false,
      sections: [a_section(), a_section({ section_key: "emergency", editable: false })],
    },
    over || {},
  );
}

/* ── 무엇이 나가는가 ────────────────────────────────────────────────── */

test("고치기 전에는 원본이 그대로 나간다", () => {
  const { copyShown, copyIsMine } = rules();

  assert.strictEqual(copyShown(a_section()), "[합성] 원본 문구입니다.");
  assert.strictEqual(copyIsMine(a_section()), false);
});

test("고친 뒤에는 원장님 문구가 나간다", () => {
  const { copyShown, copyIsMine } = rules();
  const mine = a_section({ body: "처음 두세 달은 피가 조금씩 비칠 수 있어요." });

  assert.strictEqual(copyShown(mine), "처음 두세 달은 피가 조금씩 비칠 수 있어요.");
  assert.strictEqual(copyIsMine(mine), true);
});

test("빈 문구는 고친 것으로 치지 않는다", () => {
  const { copyIsMine, copyShown } = rules();

  assert.strictEqual(copyIsMine(a_section({ body: "" })), false);
  assert.strictEqual(copyShown(a_section({ body: "" })), "[합성] 원본 문구입니다.", "원본으로 돌아간다");
});

test("승인된 원본이 없으면 빈 채로 둔다", () => {
  const { copyShown } = rules();

  assert.strictEqual(copyShown(a_section({ origin: null })), "", "없는 문구를 지어내지 않는다");
});

/* ── 진도 ───────────────────────────────────────────────────────────── */

test("확인 진도는 장을 센다 — 구역이 아니다", () => {
  const { copyProgress } = rules();

  const said = copyProgress([a_set({ reviewed: true }), a_set({ prescription_set_id: 2 })]);

  assert.strictEqual(said.say, "1/2");
  assert.strictEqual(
    said.total,
    2,
    "원문: 「조각을 하나씩 승인하게 하면 확인할 것이 54개가 되지만 약 단위로 묶으면 5장이면 끝난다」",
  );
});

test("한 장도 안 봤으면 0이다", () => {
  const { copyProgress } = rules();

  assert.strictEqual(copyProgress([a_set()]).say, "0/1");
  assert.strictEqual(copyProgress([]).say, "0/0");
  assert.strictEqual(copyProgress(null).say, "0/0");
});

test("확인 표시가 원문대로다", () => {
  const { copyMark } = rules();

  assert.strictEqual(copyMark(a_set({ reviewed: true })), "✓");
  assert.strictEqual(copyMark(a_set()), "확인 전");
});

/* ── 묶기 ───────────────────────────────────────────────────────────── */

test("질환으로 묶되 받은 차례를 지킨다", () => {
  const { copyByDisease } = rules();

  const blocks = copyByDisease([
    a_set({ prescription_set_id: 4, disease: "PCOS", name: "PCOS · 초진" }),
    a_set({ prescription_set_id: 1 }),
  ]);

  assert.strictEqual(blocks[0].title, "다낭성난소증후군", "설정 레일과 같은 이름을 쓴다");
  assert.strictEqual(blocks[1].title, "자궁내막증");
});

/* ── 막는 자리 ──────────────────────────────────────────────────────── */

test("🚨 응급 문구는 열리지 않는다", () => {
  const { copyProblem } = rules();

  const said = copyProblem(a_section({ section_key: "emergency", editable: false }), "고친 응급 문구");

  assert.ok(said.indexOf("안전을 위해") !== -1, "원문: 「🚨 문구는 이 화면이 열리지 않는다」");
});

test("빈 문구를 막는다", () => {
  const { copyProblem } = rules();

  assert.ok(copyProblem(a_section(), "   "));
  assert.strictEqual(copyProblem(a_section(), "고친 문구"), "", "멀쩡한 문구는 막지 않는다");
});

test("구역 이름이 원문대로다", () => {
  const { copySectionSaying } = rules();

  assert.strictEqual(copySectionSaying("caution"), "주의할 점");
  assert.strictEqual(copySectionSaying("emergency"), "🚨 바로 병원에 오셔야 하는 경우");
});

/* ── 목업이 서버와 같은 규칙인가 ────────────────────────────────────── */

function api() {
  const box = load(
    "api", "settings-rail", "guide-copy-rules", "baseline-rules",
    "field-labels", "message-words", "sms-template-rules", "catalog-api",
  );
  box.MOCK = true;
  return box;
}

test("목업이 여덟 장을 세운다", async () => {
  const box = api();

  const page = await box.catalogApi.guideCopy();

  assert.strictEqual(page.items.length, 8, "처방 세트 여덟이 곧 여덟 장이다");
  assert.strictEqual(box.copyProgress(page.items).say, "0/8");
});

test("목업도 🚨 를 잠근다", async () => {
  const box = api();

  const page = await box.catalogApi.guideCopy();
  const sections = page.items[0].sections;

  assert.strictEqual(sections.filter((s) => s.editable).length, 1, "고칠 수 있는 것은 주의할 점 하나다");
  assert.strictEqual(sections.filter((s) => s.section_key === "emergency")[0].editable, false);
});

test("목업의 원본이 씨앗의 합성 문구다", async () => {
  const box = api();

  const page = await box.catalogApi.guideCopy();

  assert.ok(
    page.items[0].sections[0].origin.indexOf("[합성]") === 0,
    "지어낸 의학 문장을 목업에 넣으면 그것이 진짜처럼 읽힌다",
  );
});

test("고치면 확인이 풀린다", async () => {
  const box = api();

  await box.catalogApi.reviewCopy(1);
  const reviewed = (await box.catalogApi.guideCopy()).items.filter((r) => r.prescription_set_id === 1)[0];
  const after = (await box.catalogApi.saveCopy(1, "caution", "고친 문구")).items.filter(
    (r) => r.prescription_set_id === 1,
  )[0];

  assert.strictEqual(reviewed.reviewed, true);
  assert.strictEqual(
    after.reviewed,
    false,
    "「확인 완료」가 붙은 채로 바뀐 글이 나가면 그 표시가 거짓말이 된다",
  );
});

test("되돌리면 원본으로 간다", async () => {
  const box = api();

  await box.catalogApi.saveCopy(2, "caution", "고친 문구");
  const back = (await box.catalogApi.revertCopy(2, "caution")).items.filter(
    (r) => r.prescription_set_id === 2,
  )[0];

  assert.strictEqual(back.sections[0].body, null, "원본을 베껴 넣지 않는다");
  assert.ok(back.sections[0].origin, "원본은 지워지지 않는다");
});

/* ── 화면이 그 규칙을 쓰는가 ────────────────────────────────────────── */

test("원본이 위에 있다", () => {
  const code = codeOnly(read("js/settings.js"));
  const part = code.slice(code.indexOf("function copySectionHtml"), code.indexOf("function whoseName"));

  assert.ok(part.indexOf("cp__origin") < part.indexOf("cp__body"), "무엇이 사실이고 무엇이 표현인지 보인다");
  assert.ok(part.indexOf("표현만 수정해 주세요") !== -1, "원문의 ⓘ 줄이다");
});

test("원본을 읽는 자리로 그린다", () => {
  const css = read("css/settings.css");

  assert.ok(/\.cp__origin\s*\{/.test(css), "입력칸처럼 보이면 고쳐도 되는 줄 안다");
});

test("저장 전에 화면이 먼저 잰다", () => {
  const code = codeOnly(read("js/settings.js"));
  const save = code.slice(code.indexOf("function saveCopy"), code.indexOf("function revertCopy"));

  assert.ok(save.indexOf("copyProblem(") !== -1);
  assert.ok(save.indexOf("copyProblem(") < save.indexOf("catalogApi"), "막혔으면 보내지 않는다");
});

test("서버가 돌려준 것을 화면으로 삼는다", () => {
  const code = codeOnly(read("js/settings.js"));
  const save = code.slice(code.indexOf("function saveCopy"), code.indexOf("function revertCopy"));

  assert.ok(save.indexOf("copy = data") !== -1, "고치면 확인이 풀리는데 그것이 보여야 한다");
});

test("왜 약이 아니라 처방인지 화면이 말한다", () => {
  const code = codeOnly(read("js/settings.js"));

  assert.ok(
    code.indexOf("판독값으로 만들어집니다") !== -1,
    "「왜 드시나요」·「먹는 방법」이 없는 까닭을 적지 않으면 빠뜨린 것으로 읽힌다",
  );
});
