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

  /* 갈래가 넷이 됐다 — 복약지도·생활지도는 문구가 `guides.py` 에 박혀 있어
     **고칠 자리 자체가 없었다.** 응급만 잠긴다(KEY-150). */
  /* 값으로 견준다 — 목 안의 배열은 프로토타입이 달라 `deepStrictEqual` 이 운다. */
  assert.strictEqual(
    sections.map((s) => s.section_key).join(","),
    "medication,caution,emergency,life",
  );
  assert.strictEqual(sections.filter((s) => s.editable).length, 3, "응급만 잠겨야 한다");
  assert.strictEqual(sections.filter((s) => s.section_key === "emergency")[0].editable, false);
});

test("목업의 원본이 씨앗의 합성 문구다", async () => {
  const box = api();

  const page = await box.catalogApi.guideCopy();

  /* 승인 문구가 있는 갈래는 「[합성]」으로 시작한다 — 지어낸 의학 문장을
     목업에 넣으면 그것이 진짜처럼 읽힌다. 승인 문구가 없는 갈래는 기본
     문구가 그 자리를 채운다(서버와 같은 규칙). */
  const bySection = {};
  for (const part of page.items[0].sections) bySection[part.section_key] = part;

  assert.ok(bySection.caution.origin.indexOf("[합성]") === 0);
  assert.ok(bySection.emergency.origin.indexOf("[합성]") === 0);
  assert.strictEqual(
    bySection.medication.origin,
    box.MOCK_COPY_DEFAULT.medication,
    "승인 문구가 없는 갈래는 기본 문구가 원본이다",
  );
});

test("**목의 기본 문구가 서버 것과 같은 글이다**", async () => {
  /* 갈라지면 목에서 보던 글과 실제로 나가는 글이 달라진다. 서버는 응답에
     실어 주므로 화면이 베끼지 않지만, 목은 서버가 없어 들고 있다. */
  const box = api();
  const server = read("../app/services/guide_defaults.py");

  const page = await box.catalogApi.guideCopy();
  const got = {};
  for (const part of page.defaults) got[part.section_key] = part;

  assert.strictEqual(Object.keys(got).sort().join(","), "caution,emergency,life,medication");
  assert.strictEqual(got.emergency.editable, false, "🚨 는 고칠 수 없다");

  /* **넷을 다 본다.** 예전에는 `medication`·`life` 둘만 봤다 — 여러 줄인
     `caution` 과 `emergency` 가 빠져 있어서, 그 둘은 갈라져도 아무도 몰랐다
     (`#192` 리뷰 ⑧, 2heej).

     빠졌던 까닭은 파이썬 원본이 인접 리터럴을 여러 줄로 이어 쓰고 `\n` 을
     글자 둘로 적기 때문이다. 원본을 실행 시 문자열과 같은 꼴로 펴서 잰다. */
  const flat = server.replace(/"\s*\n\s*"/g, "").replace(/\\n/g, "\n");

  for (const key of ["medication", "caution", "emergency", "life"]) {
    assert.ok(
      flat.indexOf(got[key].body) !== -1,
      `목의 ${key} 기본 문구가 서버에 없는 글이다 — 두 곳이 갈라졌다`,
    );
  }
});

test("**그 대조가 헛돌지 않는다** — 서버 글을 바꾸면 운다", () => {
  /* 위 검사가 늘 통과하면 지키는 것이 없다. 서버 원본을 한 글자 바꾼 것으로
     흉내내어, 대조가 실제로 걸리는지 본다. */
  const server = read("../app/services/guide_defaults.py");
  const flat = server.replace(/"\s*\n\s*"/g, "").replace(/\\n/g, "\n");

  assert.ok(flat.indexOf("복약 지시에 따라 정해진 시간에 복용해 주세요.") !== -1, "펴는 것부터 안 된다");
  assert.ok(flat.indexOf("[합성 주의 안내]\n복용 중") !== -1, "여러 줄 문구가 안 펴진다");
  assert.strictEqual(flat.indexOf("복약 지시에 따라 정해진 시각에 복용해 주세요."), -1, "안 바뀐 글도 찾는다");
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

test("**네 갈래가 다 선다** — 복약지도 · 주의사항 · 응급 · 생활지도", () => {
  /* 한동안 주의사항 둘뿐이었다. 「복약지도·생활지도는 환자마다 판독값으로
     만들어지는 것이라 고칠 문구가 없다」고 화면에 적어 두었는데, **그것이
     틀렸다** — 원문 D2-2 는 넷 다 [수정] 이고, 두 갈래의 문장이 `guides.py`
     에 박혀 있었을 뿐이다.

     차례는 환자가 읽는 차례다. */
  const { COPY_SECTION_SAYING } = rules();

  assert.deepEqual(Object.keys(COPY_SECTION_SAYING), [
    "medication",
    "caution",
    "emergency",
    "life",
  ]);
});

test("**판독값이 든다는 것과 못 고친다는 것은 다르다**", () => {
  /* 옛 안내가 둘을 뭉쳐 「고칠 문구가 없습니다」라 적고 있었다. 값이 채워지는
     자리와 그 값이 들어갈 문장을 정하는 자리는 다르다. */
  const code = codeOnly(read("js/settings.js"));

  assert.ok(
    code.indexOf("여기서 고칠 문구가 없습니다") === -1,
    "이제 고칠 수 있는데 못 고친다고 적혀 있다",
  );
  assert.ok(
    code.indexOf("그 값이 들어갈 문장을 정합니다") !== -1,
    "판독값이 어디에 채워지는지 안 알려 준다",
  );
});
