/* 검사 기준선 (D2-4) — KEY-234.
 *
 * 원문 주석: 「기준선 → D1 「나의 목표」의 남은 거리 계산에 쓰인다」.
 *
 * **가장 크게 재는 것은 「비워 둘 수 있는가」다.** 원문: 「비워 두면 값과
 * 추이만 표시하고 목표 대비 수치는 계산하지 않습니다」. 기준선은 검사기관과
 * 나이에 따라 다르고, 모르는 채로 셈해 「목표까지 3 남았습니다」라고 말하는
 * 것이 제일 나쁘다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function rules() {
  return load("api", "settings-rail", "baseline-rules");
}

function a_row(over) {
  return Object.assign(
    {
      disease: "PCOS",
      name: "월경 주기",
      direction: "KEEP",
      low: "21.00",
      high: "35.00",
      by_age: false,
      keywords: "LMP, 월경, 주기",
      unit: "일",
      always_shown: true,
    },
    over || {},
  );
}

/* ── 기준선을 사람 말로 ─────────────────────────────────────────────── */

test("원문의 여섯 모양을 그대로 적는다", () => {
  const { baselineSaying } = rules();

  assert.strictEqual(baselineSaying(a_row()), "21~35");
  assert.strictEqual(baselineSaying(a_row({ low: "12.00", high: null })), "12 이상");
  assert.strictEqual(baselineSaying(a_row({ low: null, high: "40.00" })), "40 미만");
  assert.strictEqual(baselineSaying(a_row({ low: null, high: null, by_age: true })), "나이별");
  assert.strictEqual(baselineSaying(a_row({ low: null, high: null })), "—");
  assert.strictEqual(baselineSaying(null), "—");
});

test("소수 꼬리를 떼어 원문과 같게 적는다", () => {
  const { trimNumber } = rules();

  assert.strictEqual(trimNumber("21.00"), "21", "「21.00~35.00」이면 원문과 다르다");
  assert.strictEqual(trimNumber("12.50"), "12.5", "뜻이 있는 소수는 남긴다");
  assert.strictEqual(trimNumber(null), "");
  assert.strictEqual(trimNumber(""), "");
});

test("나이별이면 숫자를 보지 않는다", () => {
  const { baselineSaying } = rules();

  assert.strictEqual(
    baselineSaying(a_row({ by_age: true })),
    "나이별",
    "숫자 하나로 못 적는 값이라, 남은 숫자를 보이면 그것으로 셈하는 줄 안다",
  );
});

/* ── 방향 ───────────────────────────────────────────────────────────── */

test("방향 셋이 원문대로다", () => {
  const { BASELINE_DIRECTIONS, directionSaying } = rules();

  assert.strictEqual(BASELINE_DIRECTIONS.map((d) => d.say).join(" "), "유지 ↓ 낮춤 참고");
  assert.strictEqual(directionSaying("REFERENCE"), "참고", "올리고 내릴 값이 아닌 것도 있다");
  assert.strictEqual(directionSaying("무언가새로운"), "무언가새로운");
});

/* ── 막는 자리 ──────────────────────────────────────────────────────── */

test("이름 없는 줄을 막는다", () => {
  const { baselineProblem } = rules();

  assert.ok(baselineProblem(a_row({ name: "   " })));
  assert.strictEqual(baselineProblem(a_row()), "", "멀쩡한 줄은 막지 않는다");
});

test("숫자가 아닌 기준선을 막는다", () => {
  const { baselineProblem } = rules();

  assert.ok(baselineProblem(a_row({ low: "스물하나" })));
  assert.strictEqual(baselineProblem(a_row({ low: "", high: "" })), "", "비워 두는 것은 막지 않는다");
});

test("아래가 위보다 크면 막는다", () => {
  const { baselineProblem } = rules();

  assert.ok(baselineProblem(a_row({ low: "35", high: "21" })));
});

test("같은 질환에 같은 이름이 둘이면 잡는다", () => {
  const { duplicateBaselines } = rules();

  assert.deepStrictEqual(duplicateBaselines([a_row(), a_row()]).join(), "월경 주기");
  assert.deepStrictEqual(
    duplicateBaselines([a_row({ name: "AMH" }), a_row({ name: "AMH", disease: "ENDOMETRIOSIS" })]).join(),
    "",
    "AMH 는 두 질환에 다 있다 — 원문이 그렇게 그린다",
  );
});

/* ── 묶기 ───────────────────────────────────────────────────────────── */

test("질환으로 묶되 받은 차례를 지킨다", () => {
  const { baselinesByDisease } = rules();

  const blocks = baselinesByDisease([
    a_row({ name: "월경 주기" }),
    a_row({ name: "혈색소 Hb", disease: "ENDOMETRIOSIS" }),
    a_row({ name: "AMH" }),
  ]);

  assert.strictEqual(blocks.length, 2);
  assert.strictEqual(blocks[0].title, "다낭성난소증후군", "설정 레일과 같은 이름을 쓴다");
  assert.deepStrictEqual(blocks[0].rows.map((r) => r.name).join(), "월경 주기,AMH");
  assert.strictEqual(blocks[1].title, "자궁내막증");
});

test("차례를 여기서 다시 세우지 않는다", () => {
  const { baselinesByDisease } = rules();

  const blocks = baselinesByDisease([
    a_row({ name: "혈색소 Hb", disease: "ENDOMETRIOSIS" }),
    a_row({ name: "월경 주기" }),
  ]);

  assert.strictEqual(
    blocks[0].disease,
    "ENDOMETRIOSIS",
    "화면이 보여 준 차례가 곧 저장되는 차례다 — 다시 세우면 저장할 때마다 순서가 바뀐다",
  );
});

/* ── 누구 기준 ──────────────────────────────────────────────────────── */

test("의사가 둘 이상일 때만 「누구 기준」이 뜬다", () => {
  const { showsWhosePicker } = rules();

  assert.strictEqual(showsWhosePicker([{ doctor_id: 1 }, { doctor_id: 2 }]), true);
  assert.strictEqual(showsWhosePicker([{ doctor_id: 1 }]), false, "고를 것이 하나뿐인 칸은 자리만 찬다");
  assert.strictEqual(showsWhosePicker([]), false);
  assert.strictEqual(showsWhosePicker(null), false);
});

/* ── 목업이 서버와 같은가 ───────────────────────────────────────────── */

function api() {
  const box = load("api", "settings-rail", "baseline-rules", "field-labels", "message-words", "sms-template-rules", "catalog-api");
  box.MOCK = true;
  return box;
}

test("목업 기본값이 원문 열세 줄이다", async () => {
  const box = api();

  const page = await box.catalogApi.baselines(null);

  assert.strictEqual(page.items.length, 13);
  assert.strictEqual(page.items[0].name, "월경 주기", "차례도 원문대로다");
  const rows = {};
  page.items.forEach((row) => {
    rows[row.disease + "|" + row.name] = row;
  });
  assert.strictEqual(box.baselineSaying(rows["PCOS|월경 주기"]), "21~35");
  assert.strictEqual(box.baselineSaying(rows["ENDOMETRIOSIS|혈색소 Hb"]), "12 이상");
  assert.strictEqual(box.baselineSaying(rows["ENDOMETRIOSIS|간수치 AST/ALT"]), "40 미만");
  assert.strictEqual(box.baselineSaying(rows["PCOS|AMH"]), "나이별");
  assert.strictEqual(rows["PCOS|HbA1c"].always_shown, false, "「＋ 항목 추가」에서 고른다");
});

test("의사가 둘이라 목업에서 「누구 기준」이 보인다", async () => {
  const box = api();

  const page = await box.catalogApi.baselines(null);

  assert.strictEqual(box.showsWhosePicker(page.doctors), true, "그 자리를 눈으로 보려면 둘이어야 한다");
});

test("의사 판을 안 만들었으면 의원 공통을 보인다", async () => {
  const box = api();

  const mine = await box.catalogApi.baselines(2);

  assert.strictEqual(mine.items.length, 13, "빈 화면은 「이 의사에게는 기준이 없다」로 읽힌다");
});

test("의사 판을 저장해도 의원 공통은 그대로다", async () => {
  const box = api();

  await box.catalogApi.saveBaselines(2, [a_row({ name: "나만의 항목" })]);

  assert.strictEqual((await box.catalogApi.baselines(2)).items.length, 1);
  assert.strictEqual((await box.catalogApi.baselines(null)).items.length, 13);
});

test("나이별을 켜면 저장할 때 숫자가 지워진다", async () => {
  const box = api();

  const page = await box.catalogApi.saveBaselines(null, [a_row({ by_age: true })]);

  assert.strictEqual(page.items[0].low, null, "서버도 같은 이유로 지운다");
  assert.strictEqual(page.items[0].high, null);
});

/* ── 화면이 그 규칙을 쓰는가 ────────────────────────────────────────── */

test("저장 전에 화면이 먼저 잰다", () => {
  const code = codeOnly(read("js/settings.js"));
  const save = code.slice(code.indexOf("function saveBaselines"), code.indexOf("/* ── 손짓"));

  assert.ok(save.indexOf("baselineProblem(") !== -1);
  assert.ok(save.indexOf("duplicateBaselines(") !== -1);
  const checkAt = save.indexOf("baselineProblem(");
  const sendAt = save.indexOf("catalogApi");
  assert.ok(checkAt < sendAt, "반만 저장되면 어느 것이 들어갔는지 모른다");
});

test("다시 그리기 전에 친 값을 거둔다", () => {
  const code = codeOnly(read("js/settings.js"));

  assert.ok(code.indexOf("function baselinesNow") !== -1);
  /* **손을 잘라 본다.** `data-drop-baseline` 의 첫 등장은 그리는 쪽이라,
     거기서 자르면 손이 아니라 마크업을 재게 된다. */
  const at = code.indexOf("var dropBaseline");
  assert.notStrictEqual(at, -1, "지우는 손이 없다 — 검사가 헛돈다");
  const drop = code.slice(at, code.indexOf("}", code.indexOf("render()", at)));
  assert.ok(drop.indexOf("baselinesNow()") !== -1, "지우기 전에 거두지 않으면 치던 값이 날아간다");
});

test("줄이 제 질환을 들고 있다", () => {
  const code = codeOnly(read("js/settings.js"));
  const collect = code.slice(code.indexOf("function baselinesNow"), code.indexOf("function saveBaselines"));

  assert.ok(
    collect.indexOf('tr.getAttribute("data-disease")') !== -1,
    "그린 차례와 배열 차례가 어긋난다 — 새로 더한 줄이 질환으로 묶이면서 자리가 바뀐다",
  );
  assert.ok(collect.indexOf("baselines.items[") === -1, "배열을 되짚으면 그 어긋남을 다시 만든다");
});

test("서버가 돌려준 것을 화면으로 삼는다", () => {
  const code = codeOnly(read("js/settings.js"));
  const save = code.slice(code.indexOf("function saveBaselines"), code.indexOf("/* ── 손짓"));

  assert.ok(save.indexOf("baselines = data") !== -1, "나이별을 켜면 서버가 숫자를 비운다 — 그것이 보여야 한다");
});

test("판독 키워드가 왜 필요한지 화면이 말한다", () => {
  const code = codeOnly(read("js/settings.js"));

  assert.ok(code.indexOf("EMR 표기를 그대로") !== -1, "왜 적어야 하는지 없으면 빈칸으로 둔다");
  assert.ok(code.indexOf("검사기관 · 연령에 따라 다릅니다") !== -1, "원문의 ⚠ 줄이다");
});
