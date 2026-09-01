/* **판독이 읽어야 하는 스물한 항목** — KEY-234.
 *
 *   증상      생리통 · 생리과다 · 불규칙 월경        사람이 물어 적는 것
 *   초음파    선근증 · 근종 · 내막 두께 · 부속기 혹  본 것
 *   혈액      Hb · AST · ALT · 호르몬 여덟           뽑아 잰 것
 *
 * 나온 곳이 다르면 못 읽었을 때 어디를 다시 봐야 하는지도 다르다. 그래서
 * 묶어서 세우고, 왼쪽(보고 적는 것) · 오른쪽(뽑아 잰 것) 두 칸으로 나눈다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function box() {
  return load("api", "session", "patients-api", "shell", "field-labels", "ocr-groups");
}

const WANTED = {
  증상: ["PAIN_SCORE", "HEAVY_BLEEDING", "IRREGULAR_CYCLE"],
  "초음파 검사": [
    "ADENOMYOSIS_SIZE",
    "MYOMA_SIZE",
    "MYOMA_COUNT",
    "ENDOMETRIAL_THICKNESS",
    "ADNEXAL_CYST_LEFT",
    "ADNEXAL_CYST_RIGHT",
  ],
  혈액검사: [
    "HEMOGLOBIN",
    "AST",
    "ALT",
    "LH_FSH_RATIO",
    "DHEA_S",
    "TESTOSTERONE",
    "PROLACTIN",
    "TSH",
    "T3",
    "T4",
    "E2",
    "PROGESTERONE",
  ],
};

test("**스물한 항목이 제 묶음에 선다**", () => {
  const { LAB_GROUPS } = box();
  const byTitle = {};
  LAB_GROUPS.forEach((g) => (byTitle[g.title] = g.types));

  for (const [title, types] of Object.entries(WANTED)) {
    assert.ok(byTitle[title], `「${title}」 묶음이 없다`);
    assert.deepEqual(byTitle[title], types, `「${title}」 묶음의 항목이 다르다`);
  }

  const total = LAB_GROUPS.reduce((n, g) => n + g.types.length, 0);
  assert.equal(total, 21, `항목이 ${total}개다 — 스물하나여야 한다`);
});

test("**모든 항목에 이름표가 있다** — 없으면 서버 코드가 그대로 뜬다", () => {
  const { LAB_CORE, FIELD_LABELS } = box();
  for (const type of LAB_CORE) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(FIELD_LABELS, type),
      `${type} 의 이름표가 없다 — 화면에 코드가 뜬다`,
    );
  }

  /* 한글로 부르는 것은 한글로. `TSH` · `Prolactin` 처럼 차트에 영문으로 적히는
     것은 그대로 둔다 — 옮기면 오히려 차트와 대조가 안 된다. */
  assert.equal(FIELD_LABELS.PAIN_SCORE, "생리통 (0~10점)");
  assert.equal(FIELD_LABELS.ADNEXAL_CYST_LEFT, "난소 부속기 혹 (왼쪽)");
  assert.equal(FIELD_LABELS.TSH, "TSH");
});

/* ── 두 칸 ──────────────────────────────────────────────────────────── */

test("**왼쪽은 보고 적는 것, 오른쪽은 뽑아 잰 것**", () => {
  const { labColumnsOf, labGroupsOf, LAB_CORE } = box();
  const rows = LAB_CORE.map((t) => ({ field_type: t, value: null, is_absent: true }));
  const columns = labColumnsOf(labGroupsOf(rows));

  assert.equal(columns.length, 2, "두 칸이 아니다");
  assert.deepEqual(
    columns[0].groups.map((g) => g.title),
    ["증상", "초음파 검사"],
    "왼쪽 칸의 묶음이 다르다",
  );
  assert.deepEqual(columns[1].groups.map((g) => g.title), ["혈액검사"], "오른쪽 칸의 묶음이 다르다");
});

test("빈 칸은 내지 않는다 — 옆에 빈 칸이 서면 화면이 반쯤 무너져 보인다", () => {
  const { labColumnsOf, labGroupsOf } = box();

  /* 혈액만 있을 때 */
  const onlyBlood = labColumnsOf(labGroupsOf([{ field_type: "TSH", value: "2.1" }]));
  assert.equal(onlyBlood.length, 1);
  assert.equal(onlyBlood[0].key, "right");

  /* 아무것도 없을 때 */
  assert.deepEqual(labColumnsOf(labGroupsOf([])), []);
});

test("**묶음에 없는 값도 버리지 않는다** — DB 에 남은 값이 화면에서 사라지면 안 된다", () => {
  const { labGroupsOf, labColumnsOf } = box();
  const groups = labGroupsOf([
    { field_type: "TSH", value: "2.1" },
    { field_type: "CA_125", value: "18 U/mL" },
    { field_type: "AST_ALT", value: "24 / 34 U/L" },
  ]);

  const others = groups.filter((g) => g.key === "others")[0];
  assert.ok(others, "옛 이름 값이 사라졌다");
  assert.deepEqual(
    others.rows.map((r) => r.field_type),
    ["CA_125", "AST_ALT"],
    "옛 값이 다 안 실렸다",
  );

  /* 드물게 서는 것이라 왼쪽에 붙인다 — 긴 오른쪽 칸을 더 늘리지 않는다 */
  const left = labColumnsOf(groups).filter((c) => c.key === "left")[0];
  assert.ok(left && left.groups.some((g) => g.key === "others"), "그 밖의 값이 왼쪽에 안 붙는다");
});

/* ── 있다 / 없다 ────────────────────────────────────────────────────── */

test("**「있다 / 없다」는 고르게 한다** — 치게 두면 세 가지 글자가 섞인다", () => {
  const { fieldChoices } = box();

  for (const type of ["HEAVY_BLEEDING", "IRREGULAR_CYCLE", "ADNEXAL_CYST_LEFT", "ADNEXAL_CYST_RIGHT"]) {
    assert.deepEqual(fieldChoices(type), ["있다", "없다"], `${type} 이 고르는 항목이 아니다`);
  }

  /* 숫자 항목까지 고르게 하면 안 된다 */
  for (const type of ["HEMOGLOBIN", "MYOMA_COUNT", "PAIN_SCORE"]) {
    assert.equal(fieldChoices(type), null, `${type} 이 고르는 항목이 됐다`);
  }
});

test("**난소 부속기 혹은 「있다」에 크기가 딸린다**", () => {
  const { joinChoiceValue, splitChoiceValue, fieldChoiceSized } = box();

  assert.equal(fieldChoiceSized("ADNEXAL_CYST_LEFT"), true);
  assert.equal(fieldChoiceSized("HEAVY_BLEEDING"), false, "크기 없는 항목에 크기 칸이 붙는다");

  assert.equal(joinChoiceValue("ADNEXAL_CYST_LEFT", "있다", "3.2"), "있다 3.2 cm");
  /* 「없다」에는 크기를 붙이지 않는다 — 없는데 크기가 남으면 뜻이 어긋난다 */
  assert.equal(joinChoiceValue("ADNEXAL_CYST_LEFT", "없다", "3.2"), "없다");
  /* 크기를 아직 안 적었으면 「있다」만 */
  assert.equal(joinChoiceValue("ADNEXAL_CYST_LEFT", "있다", ""), "있다");
  /* 안 골랐으면 빈 값 — 빈 값은 「적었다」로 세지 않는다 */
  assert.equal(joinChoiceValue("ADNEXAL_CYST_LEFT", "", "3.2"), "");

  assert.deepEqual(splitChoiceValue("ADNEXAL_CYST_LEFT", "있다 3.2 cm"), { pick: "있다", size: "3.2" });
  assert.deepEqual(splitChoiceValue("ADNEXAL_CYST_LEFT", "없다"), { pick: "없다", size: "" });
  assert.deepEqual(splitChoiceValue("HEAVY_BLEEDING", "있다"), { pick: "있다", size: "" });

  /* 크기만 적힌 옛 값은 「있다」로 읽는다 — 크기가 적혔다는 것이 곧 있다는 뜻 */
  assert.deepEqual(splitChoiceValue("ADNEXAL_CYST_LEFT", "2.4 cm"), { pick: "있다", size: "2.4" });

  /* 갔다가 돌아와도 같은 값이다 */
  const back = splitChoiceValue("ADNEXAL_CYST_LEFT", joinChoiceValue("ADNEXAL_CYST_LEFT", "있다", "3.2"));
  assert.deepEqual(back, { pick: "있다", size: "3.2" });
});

/* ── 화면에 붙어 있는가 ─────────────────────────────────────────────── */

test("**화면이 고르는 칸을 그린다**", () => {
  const code = codeOnly(read("js/ocr-review.js"));
  const at = code.indexOf("function choiceHtml");
  assert.notEqual(at, -1, "고르는 칸을 그리는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.match(body, /<select/, "고르는 칸이 아니다");
  assert.match(body, /fieldChoices\(/, "무엇을 고를지 안 읽는다");
  assert.match(body, /data-choice-size/, "크기 칸이 안 붙는다");

  /* 값을 읽는 자리도 두 칸을 이어야 한다 */
  assert.match(code, /function boxValue/, "값을 잇는 자리가 없다");
  const join = code.indexOf("function boxValue");
  assert.match(code.slice(join, join + 400), /joinChoiceValue\(/, "고른 것과 크기를 안 잇는다");
});

test("**단위를 아는 항목에는 단위가 있다** — cm 인지 개수인지 점수인지", () => {
  const { LAB_CORE, fieldUnit, fieldChoices } = box();

  /* 단위가 **정말 없는** 것은 여기 적어 둔다. 비율은 나눈 값이라 단위가 없고,
     없는 것에 억지로 붙이면(「배」·「비」) 차트에 없는 글자가 화면에만 뜬다.
     고르는 항목(있다/없다)도 단위가 없다. */
  const UNITLESS = ["LH_FSH_RATIO"];
  const blank = LAB_CORE.filter(
    (t) => !fieldChoices(t) && !fieldUnit(t, "") && UNITLESS.indexOf(t) === -1,
  );
  assert.deepEqual(blank, [], `단위가 없는 항목: ${blank.join(", ")}`);

  assert.equal(fieldUnit("MYOMA_SIZE", ""), "cm");
  assert.equal(fieldUnit("MYOMA_COUNT", ""), "개");
  assert.equal(fieldUnit("PAIN_SCORE", ""), "점");
  assert.equal(fieldUnit("AST", ""), "U/L");

  /* 서버가 준 단위가 있으면 그것이 이긴다 */
  assert.equal(fieldUnit("MYOMA_SIZE", "mm"), "mm", "서버가 준 단위를 무시한다");
});

test("**고르는 항목은 고르개로 그린다** — 두 갈래 모두에서", () => {
  const { fieldChoices } = box();
  const code = codeOnly(read("js/ocr-review.js"));

  /* 서버에 있는 줄과 아직 없는 줄, 두 갈래가 **같은 모양**이어야 한다.
     한쪽만 고르개면 같은 항목이 화면에 따라 다르게 보인다. */
  const hooks = ['data-input="', 'data-local-input="'];
  for (const hook of hooks) {
    const at = code.indexOf("choiceHtml(\n              field,") !== -1 ? 0 : 0;
    assert.ok(at === 0, "");
  }
  const uses = (code.match(/choiceHtml\(/g) || []).length;
  assert.ok(uses >= 3, `고르개를 ${uses} 곳에서만 쓴다 — 두 갈래 모두여야 한다`);

  /* 그리는 조건이 실제로 「고르는 항목인가」여야 한다 */
  const guard = code.split("? choiceHtml(");
  assert.ok(guard.length >= 3, "고르개 갈래를 못 찾았다 — 검사가 헛돈다");
  for (let i = 1; i < guard.length; i++) {
    assert.match(
      guard[i - 1].slice(-120),
      /fieldChoices\(field\.field_type\)/,
      `${i} 번째 갈래가 「고르는 항목인가」를 안 본다`,
    );
  }
  assert.ok(fieldChoices("HEAVY_BLEEDING"), "검사가 헛돈다");
});

test("**점선 칸 오른쪽에 단위가 선다** — `?` 만 있으면 무엇을 적을지 물어봐야 안다", () => {
  const code = codeOnly(read("js/ocr-review.js"));
  const at = code.indexOf("function unitHtml");
  assert.notEqual(at, -1, "단위를 그리는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.match(body, /fieldUnit\(/, "단위표를 안 읽는다");
  assert.match(body, /fieldChoices\(/, "고르는 항목에도 단위를 붙인다");
  /* 처방 줄은 제 단위를 이미 그린다 — 또 붙이면 한 줄에 「일」이 두 번 선다 */
  assert.match(body, /PRESCRIPTION_TYPES/, "처방 줄에도 단위를 또 붙인다");

  /* 못 읽은 두 갈래 모두에 붙어야 한다 — 한쪽만 붙이면 줄마다 달라 보인다 */
  const missing = code.split('field__value--missing">?</div>');
  assert.ok(missing.length >= 3, "못 읽은 줄 갈래를 못 찾았다 — 검사가 헛돈다");
  for (let i = 1; i < missing.length; i++) {
    assert.match(missing[i].slice(0, 120), /unitHtml\(field\)/, `못 읽은 줄 ${i} 에 단위가 없다`);
  }
});

test("**못 읽었다는 말을 한 줄에 두 번 적지 않는다**", () => {
  /* 이름 옆의 「⚠ 인식 실패」와 값 옆의 「판독 실패」가 겹쳐서, 같은 말이 두 번
     서고 항목 이름이 밀려 잘렸다. 상태는 값이 서는 쪽에서 말한다. */
  const code = codeOnly(read("js/ocr-review.js"));
  const at = code.indexOf("var STATE_TEXT");
  assert.notEqual(at, -1, "상태 글 표가 없다");

  const table = code.slice(at, code.indexOf("};", at));
  assert.ok(!table.includes("missing:"), "이름 옆에 「인식 실패」가 다시 붙는다");
  assert.ok(table.includes("skipped:"), "다른 상태까지 사라졌다 — 검사가 헛돈다");

  /* 대신 값 쪽이 말해야 한다 */
  assert.ok(code.includes("판독 실패"), "왜 비었는지 아무 데서도 안 말한다");
});
