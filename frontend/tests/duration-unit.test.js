/* 처방일수의 단위를 사람이 고친다 — KEY-285.
 *
 * 「3」이 3일이면 3일이고 3통이면 84일이다. 그 차이가 소진 예정일을 81일
 * 움직이고 확인 문자가 엉뚱한 날 나간다. 여태 화면은 서버가 준 글자를
 * **보여주기만** 해서, 잘못 심긴 단위는 DB 를 직접 만져야 풀렸다.
 *
 * 여기서 재는 것은 **목업 라우터**다 — 그리는 것은 브라우저에서 본다.
 * 목업이 서버보다 좁으면 `?mock=1` 로 검수할 수 없고, 넓으면 목업에서만
 * 되는 화면이 된다. 두 문(값의 모양 · 붙일 자리)을 서버와 같이 세운다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");
const { codeOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");
const read = (f) => codeOnly(fs.readFileSync(path.join(ROOT, f), "utf8"));

/** 목업 저장소에 처방일수 줄을 심는다 — 기본 픽스처는 검사값뿐이다. */
function withDurationRow(box, overrides) {
  const row = Object.assign(
    {
      ocr_field_id: 9500,
      field_type: "DURATION_DAYS",
      extracted_value: "3",
      corrected_value: null,
      value: "3",
      unit: null,
      confidence: 0.9,
      is_low_confidence: false,
      version: 1,
      is_confirmed: false,
      is_pending_report: false,
      candidates: [],
    },
    overrides || {},
  );
  box.mockState().fields.push(row);
  return row;
}

test("단위만 보내도 저장된다 — 숫자를 다시 안 적는다", async () => {
  const box = load("api", "field-labels", "ocr-api");
  const row = withDurationRow(box);

  const saved = await box.ocrApi.updateField(row.ocr_field_id, { base_version: 1, unit: "통" });

  assert.equal(saved.unit, "통");
  assert.equal(saved.value, "3", "숫자를 건드렸다");
  assert.equal(saved.version, 2, "판올림이 없으면 다음 저장이 옛 판을 덮는다");
  assert.ok(saved.modified_at, "누가 언제 고쳤는지가 안 남았다");
});

test("모르는 단위는 목업도 거절한다 — 서버가 422 로 막는 자리", async () => {
  const box = load("api", "field-labels", "ocr-api");
  const row = withDurationRow(box, { ocr_field_id: 9501 });

  for (const bogus of ["박스", "days", "정"]) {
    await assert.rejects(
      box.ocrApi.updateField(row.ocr_field_id, { base_version: 1, unit: bogus }),
      (e) => e.status === 422,
      `목업이 ${bogus} 를 통과시켰다 — 진짜 서버는 거절한다`,
    );
  }
  assert.equal(box.mockState().fields.find((f) => f.ocr_field_id === 9501).unit, null);
});

test("검사값 줄에는 단위를 못 붙인다 — 그 글자가 그대로 화면에 뜬다", async () => {
  const box = load("api", "field-labels", "ocr-api");
  const lab = box.mockState().fields[0];

  await assert.rejects(
    box.ocrApi.updateField(lab.ocr_field_id, { base_version: lab.version, unit: "통" }),
    (e) => e.code === "UNIT_NOT_ALLOWED" && e.status === 400,
  );
});

test("둘째 약의 총투도 받는다 — 접미사가 붙을 뿐 같은 칸이다", async () => {
  const box = load("api", "field-labels", "ocr-api");
  const row = withDurationRow(box, { ocr_field_id: 9502, field_type: "DURATION_DAYS_2" });

  const saved = await box.ocrApi.updateField(row.ocr_field_id, { base_version: 1, unit: "통" });

  assert.equal(saved.unit, "통");
});

test("빈 요청은 여전히 거절한다 — 단위를 원천으로 인정하면서 문이 열리면 안 된다", async () => {
  const box = load("api", "field-labels", "ocr-api");
  const row = withDurationRow(box, { ocr_field_id: 9503 });

  await assert.rejects(
    box.ocrApi.updateField(row.ocr_field_id, { base_version: 1 }),
    (e) => e.code === "INVALID_REQUEST",
  );
});

test("**확정된 줄도 고칠 수 있다** — 목업이 서버보다 좁았던 자리", async () => {
  /* 서버는 KEY-273 에서 확정 뒤 수정을 열었는데(`app/ocr/service.py` 의
     「확정돼도 고칠 수 있다」) 목업만 409 로 남아 있었다.

     이 티켓의 한복판이 바로 그 갈래다 — **확정하고 나서** 단위가 틀린 것을
     알아차리는 것. 목업이 막으면 `?mock=1` 로 그 자리를 볼 수 없다. */
  const box = load("api", "field-labels", "ocr-api");
  const row = withDurationRow(box, { ocr_field_id: 9504, is_confirmed: true });

  const saved = await box.ocrApi.updateField(row.ocr_field_id, { base_version: 1, unit: "통" });

  assert.equal(saved.unit, "통");
});

test("화면이 단위를 보내는 길이 있고, 처방일수에만 있다", () => {
  const src = read("js/ocr-review.js");

  /* 그리는 것은 브라우저에서 보지만, **어느 줄에 다는가**는 순수 규칙이라
     여기서 잰다 — 검사값 줄에 달면 서버가 400 을 주고 화면은 고장으로 읽힌다. */
  /* `isDurationField` 는 `field-labels.js` 로 옮겼다 — 규칙이라 그 자리다. */
  assert.match(read("js/field-labels.js"), /function isDurationField\(fieldType\)/);
  assert.match(read("js/field-labels.js"), /\^DURATION_DAYS\(_\\d\+\)\?\$/);
  assert.ok(src.includes("data-field-unit"), "단위를 고르는 자리가 없다");
  assert.match(src, /saveField\(unitId, \{ unit: chosen \}\)/, "고른 값을 서버로 안 보낸다");

  /* 빈 값으로 되돌리는 것은 안 보낸다 — 서버가 그 길을 안 열었다. */
  assert.match(src, /if \(!isNaN\(unitId\) && chosen\)/, "빈 값도 보내면 422 만 받는다");
});

/** 그 함수의 몸통만. **파일 전체를 뒤지면 남의 `<option>` 까지 걸린다** —
    처음에 그렇게 썼다가 처방세트 고르는 칸의 조각을 「모르는 단위」로 세었다. */
function bodyOf(src, name) {
  const at = src.indexOf(`function ${name}(`);
  assert.notEqual(at, -1, `${name} 을 못 찾았다`);
  const end = src.indexOf("\n  }", at);
  assert.notEqual(end, -1, `${name} 의 끝을 못 찾았다`);
  const body = src.slice(at, end);
  assert.ok(body.length > 100, "빈 조각을 검사하고 있다");
  return body;
}

test("고를 수 있는 값이 서버가 아는 값과 같다", () => {
  const { DURATION_UNITS } = load("api", "field-labels");

  /* `DurationUnit` 은 일 · 통 둘뿐이다. 화면이 그 밖의 값을 내면 고른 순간
     422 다 — 고를 수 있게 해 놓고 거절하는 것이 가장 나쁜 짝이다. */
  assert.deepEqual(DURATION_UNITS, ["일", "통"]);

  /* 그 목록이 실제로 칸을 만드는지도 본다 — 상수만 맞고 화면이 제 손으로
     다른 것을 적으면 소용이 없다. */
  const body = bodyOf(read("js/ocr-review.js"), "durationUnitHtml");
  assert.ok(body.includes("DURATION_UNITS.map"), "화면이 그 목록으로 칸을 안 만든다");
});

test("**모르면 모르는 채로 둔다** — 「일」을 미리 골라 두면 3통이 3일로 넘어간다", () => {
  const { durationUnitChoice } = load("api", "field-labels");

  /* 판독이 단위를 못 정한 것은 **실제 상태**다. 화면이 그것을 「일」로 보이면
     스탭은 확인 없이 넘어간다 — 합성 100행 중 33행이 통수다. */
  assert.equal(durationUnitChoice(null), "", "빈 단위를 골라진 것처럼 보였다");
  assert.equal(durationUnitChoice(undefined), "");
  assert.equal(durationUnitChoice(""), "");
  assert.equal(durationUnitChoice("일"), "일");
  assert.equal(durationUnitChoice("통"), "통");

  /* 서버가 모르는 글자가 들어와도 골라진 채 서면 안 된다 — 스탭은 이미
     정해진 것으로 읽는다. */
  assert.equal(durationUnitChoice("박스"), "");
  assert.equal(durationUnitChoice("days"), "");
});

/* ── 판독이 줄 자체를 못 만든 자리 — 이희진 님 `#251` 리뷰 ① ────────────────
 *
 * 위 검사들은 **줄이 있는** 경우만 쟀다. 그런데 이 티켓이 막으려던 상황은
 * 판독이 처방일수를 **통째로 못 읽어** 스탭이 손으로 「3」을 치는 자리다.
 * 그때는 `ocr_field_id` 가 없어 단위 칸이 아예 안 그려졌고, 저장도
 * `writeField` 로 나가는데 그 함수에 단위를 실을 인자가 없었다.
 * 서버는 문을 열어 두었는데(`WriteOcrFieldRequest.unit`) 화면이 안 보냈다.
 */

test("직접입력도 단위를 실어 보낸다 — 서버가 연 문을 화면이 쓴다", async () => {
  const box = load("api", "ocr-api", { search: "?mock=1" });
  const sent = [];
  const real = box.request;
  box.request = function (path, options) {
    sent.push({ path, body: options && options.body });
    return Promise.resolve({});
  };
  box.MOCK = false;
  try {
    await box.ocrApi.writeField(77, "DURATION_DAYS", "3", "통");
  } finally {
    box.request = real;
  }

  assert.equal(sent.length, 1, "요청이 안 나갔다");
  assert.equal(sent[0].body.value, "3");
  assert.equal(sent[0].body.unit, "통", "손으로 적은 줄의 단위가 안 실렸다");
});

test("단위를 안 고르면 아예 안 싣는다 — 빈 값은 서버가 「모른다로 되돌려라」로 읽는다", async () => {
  const box = load("api", "ocr-api", { search: "?mock=1" });
  const sent = [];
  const real = box.request;
  box.request = function (path, options) {
    sent.push(options && options.body);
    return Promise.resolve({});
  };
  box.MOCK = false;
  try {
    await box.ocrApi.writeField(77, "DURATION_DAYS", "3");
  } finally {
    box.request = real;
  }

  assert.ok(!("unit" in sent[0]), `안 고른 단위를 실어 보냈다 — ${JSON.stringify(sent[0])}`);
});

test("직접입력의 단위도 목업이 보정과 같은 규칙으로 막는다", async () => {
  const box = load("api", "ocr-api", { search: "?mock=1" });

  await assert.rejects(
    box.ocrApi.writeField(77, "DURATION_DAYS", "3", "박스"),
    (e) => e.status === 422,
    "서버가 아는 값이 아닌데 목업이 통과시켰다",
  );
  await assert.rejects(
    box.ocrApi.writeField(77, "HEMOGLOBIN", "10.2", "통"),
    (e) => e.code === "UNIT_NOT_ALLOWED" && e.status === 400,
    "검사값 줄에 단위를 붙였는데 목업이 통과시켰다",
  );
});

test("줄이 없어도 단위 칸이 선다 — 그리고 담는 길이 갈린다", () => {
  const src = read("js/ocr-review.js");

  /* `&& field.ocr_field_id` 가 붙어 있으면 판독이 못 읽은 줄에는 칸이 안 선다.
     이 티켓이 막으려던 바로 그 줄이다. */
  assert.doesNotMatch(
    src,
    /isDurationField\(field\.field_type\) && field\.ocr_field_id/,
    "줄이 있을 때만 단위 칸을 세운다 — 손으로 적는 자리에 칸이 없다",
  );
  assert.match(src, /if \(isDurationField\(field\.field_type\)\) return durationUnitHtml\(field\)/);

  /* 담는 길이 둘이라야 한다 — 줄이 있으면 번호로 즉시, 없으면 [저장] 때 함께. */
  assert.ok(src.includes("data-field-unit-new"), "줄 없는 칸을 짚는 표시가 없다");
  assert.match(src, /function pickedUnitFor\(fieldType\)/, "저장할 때 고른 단위를 읽는 자리가 없다");
  assert.match(
    src,
    /writeField\(wanted, job\.type, job\.value, pickedUnitFor\(job\.type\)\)/,
    "직접입력 저장이 단위를 같이 안 보낸다",
  );
});

test("잘못된 단위 + 낡은 판이 같이 오면 422 다 — 실서버가 그렇다", async () => {
  /* 이희진 님 `#251` 리뷰 ②. 실서버는 pydantic 이 **DB 를 건드리기 전에**
     요청 전체를 검증하므로 늘 422 다. 목업이 409 를 먼저 내면 `?mock=1` 로
     이 조합을 검수한 사람이 실서버와 다른 코드를 본다. */
  const box = load("api", "ocr-api", { search: "?mock=1" });
  withDurationRow(box, { version: 7 });

  await assert.rejects(
    box.ocrApi.updateField(9500, { base_version: 1, unit: "박스" }),
    (e) => e.status === 422,
    "낡은 판이 먼저 걸려 409 가 났다 — 실서버는 422 를 준다",
  );

  /* 반대쪽도 잰다 — 단위가 멀쩡하면 낡은 판은 여전히 409 다. */
  await assert.rejects(
    box.ocrApi.updateField(9500, { base_version: 1, unit: "통" }),
    (e) => e.status === 409,
    "멀쩡한 단위인데 판 충돌을 안 막았다",
  );
});

/* ── 고른 단위가 다시 그려도 남는가 — 이희진 님 `#251` 리뷰(둘째 판) ────────
 *
 * 앞 검사는 「[저장]이 `pickedUnitFor(job.type)` 를 부르는가」를 **글자로만**
 * 재고 그것이 **무엇을 내놓는지**는 안 봤다. 그 사이에 [저장] 핸들러가
 * `say(); redraw();` 를 먼저 부르고, `pickedUnitFor` 는 그 자리의 `select` 를
 * DOM 에서 읽었다 — 다시 그려진 칸은 미선택이라 늘 `undefined` 였다.
 * 스탭이 「통」을 골라도 서버에는 한 번도 안 갔다.
 *
 * 그래서 값을 들고 있는 규칙을 IIFE 밖(`field-labels.js`)에 두고 여기서 잰다.
 */

test("고른 단위는 화면이 들고 있는다 — 다시 그려도 남아야 [저장]이 싣는다", () => {
  const { holdDurationUnit, heldDurationUnit } = load("api", "field-labels");
  const held = {};

  holdDurationUnit(held, "DURATION_DAYS", "통");
  assert.equal(heldDurationUnit(held, "DURATION_DAYS"), "통", "고른 단위가 남지 않았다");

  /* 다시 그리는 것은 이 자리를 건드리지 않는다 — DOM 이 아니라 상태다. */
  assert.equal(heldDurationUnit(held, "DURATION_DAYS"), "통", "두 번 읽으면 사라졌다");

  /* 둘째 약도 같은 자리에 각각 담긴다 — 접미사가 붙을 뿐이다. */
  holdDurationUnit(held, "DURATION_DAYS_2", "일");
  assert.equal(heldDurationUnit(held, "DURATION_DAYS"), "통", "둘째 약이 첫째를 덮었다");
  assert.equal(heldDurationUnit(held, "DURATION_DAYS_2"), "일");
});

test("「단위?」로 되돌리면 안 싣는다 — 빈 글자를 보내라는 뜻이 아니다", () => {
  const { holdDurationUnit, heldDurationUnit } = load("api", "field-labels");
  const held = {};

  holdDurationUnit(held, "DURATION_DAYS", "통");
  holdDurationUnit(held, "DURATION_DAYS", "");

  assert.equal(heldDurationUnit(held, "DURATION_DAYS"), undefined, "빈 값을 고른 것으로 들고 있었다");
  assert.ok(!("DURATION_DAYS" in held), "지우지 않고 빈 글자로 남겨 뒀다 — 그대로 실려 422 가 난다");
});

test("담을 수 없는 것은 담지 않는다 — 서버가 막는 자리를 화면이 먼저 안다", () => {
  const { holdDurationUnit, heldDurationUnit } = load("api", "field-labels");
  const held = {};

  /* 서버가 모르는 글자. 담아 두면 [저장] 때 실려 나가 422 를 받는다. */
  holdDurationUnit(held, "DURATION_DAYS", "박스");
  assert.equal(heldDurationUnit(held, "DURATION_DAYS"), undefined, "모르는 단위를 들고 있었다");

  /* 처방일수가 아닌 자리. 서버는 400(`UNIT_NOT_ALLOWED`)으로 막는다. */
  holdDurationUnit(held, "HEMOGLOBIN", "통");
  assert.equal(heldDurationUnit(held, "HEMOGLOBIN"), undefined, "검사값에 단위를 들고 있었다");
  assert.ok(!("HEMOGLOBIN" in held), "검사값 자리에 단위를 담아 뒀다");

  /* **읽는 쪽도 따로 막는다.** 담는 쪽만 막으면, 어쩌다 들어간 값이 그대로
     실려 나간다 — 문이 둘이면 둘 다 잠가야 한다. */
  const poisoned = { HEMOGLOBIN: "통", MEDICATION_NAME: "일" };
  assert.equal(heldDurationUnit(poisoned, "HEMOGLOBIN"), undefined, "담긴 값을 그대로 내줬다");
  assert.equal(heldDurationUnit(poisoned, "MEDICATION_NAME"), undefined, "약품명에 단위를 실어 줬다");
});

test("[저장]이 읽는 자리가 DOM 이 아니다 — 다시 그리기와 순서를 다투지 않는다", () => {
  const src = read("js/ocr-review.js");

  /* 이 한 줄이 버그였다. 되돌아오면 `redraw()` 뒤에 읽혀 늘 빈 값이 나간다. */
  assert.doesNotMatch(
    src,
    /querySelector\('\[data-field-unit-new=/,
    "고른 단위를 다시 DOM 에서 읽는다 — [저장]이 먼저 다시 그리므로 늘 미선택이다",
  );
  assert.match(
    src,
    /function pickedUnitFor\(fieldType\) \{\s*return heldDurationUnit\(localUnit, fieldType\);/,
    "[저장]이 화면 상태에서 단위를 읽지 않는다",
  );

  /* 고른 순간 상태에 담는 자리가 있어야 한다. */
  assert.match(src, /holdDurationUnit\(localUnit, newUnitFor, event\.target\.value\)/, "고른 단위를 담는 자리가 없다");

  /* 다시 그릴 때 그 값을 되살려야 스탭 눈에도 남는다. */
  assert.match(
    src,
    /field\.ocr_field_id \? field\.unit : heldDurationUnit\(localUnit, field\.field_type\)/,
    "다시 그릴 때 고른 단위를 안 되살린다 — 골라도 화면에서 사라진다",
  );

  /* 적어 둔 값 옆의 단위도 **고르개**여야 한다.
   *
   * 여기는 `fieldUnit(field.field_type, "")` 로 글자를 박아 두고 있었고,
   * 처방일수에서 그 글자는 「일」이다 — 스탭이 「3」을 적고 [확인]을 누르는
   * 순간 고르개가 사라지고 화면이 「3 일」이라고 단언했다. 3통짜리가 조용히
   * 3일이 되는, 이 티켓이 막으려던 바로 그 자리다. */
  assert.doesNotMatch(
    src,
    /fieldUnit\(field\.field_type, ""\)/,
    "적어 둔 값 옆의 단위를 글자로 박아 뒀다 — 처방일수는 「일」로 굳는다",
  );
  assert.match(
    src,
    /field__value--local[\s\S]{0,200}?unitHtml\(field\)/,
    "적어 둔 값 옆에 단위 고르개가 안 선다 — 값을 적기 전에만 고를 수 있다",
  );

  /* 담긴 줄은 **셋 다** 놓는다. 하나만 남으면 다음에 그 자리에 다시 값을
     적을 때 앞 선택이 되살아난다 — 위 둘과 짝이 맞아야 한다. */
  assert.match(
    src,
    /delete local\[r\.type\];\s*delete localDraft\[r\.type\];[\s\S]{0,200}?delete localUnit\[r\.type\];/,
    "저장에 성공한 뒤에도 고른 단위를 계속 들고 있는다",
  );

  /* 환자를 바꾸면 버린다 — 남으면 새 환자의 「3」이 앞 사람의 「통」으로 나간다. */
  const reset = src.slice(src.indexOf("function resetState()"));
  assert.match(reset.slice(0, reset.indexOf("\n  }")), /localUnit = \{\};/, "환자를 바꿔도 고른 단위가 남는다");
});
