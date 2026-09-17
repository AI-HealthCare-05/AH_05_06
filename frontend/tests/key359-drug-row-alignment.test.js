/* 처방일수 칸이 약품명 칸과 같은 층에 선다 — KEY-359.
 *
 * S1-6 「① 진단 · 처방」의 둘째 약부터(`extraDrugRowsHtml`)와 「+ 약 추가」로
 * 만든 줄(`manualDrugRowsHtml`)에서 **처방일수 칸이 23px 내려앉아 있었다.**
 *
 * `.top` 은 칸을 위로 맞춘다 — KEY-293 때 `flex-end` 에서 `flex-start` 로
 * 바꾼 자리다. 그래서 칸의 **첫 요소가 라벨이어야** 값칸끼리 높이가 맞는다.
 * CSS 가 이미 그렇게 적어 뒀다 — 「라벨 높이를 고정한다 — 한 줄짜리와 두
 * 줄짜리가 섞이면 아래 값칸이 어긋난다」.
 *
 * 맨 윗줄(`topRowHtml`)은 모든 칸에 라벨을 세우는데 뒤에 붙은 두 곳이
 * 약품명 칸의 라벨을 빠뜨렸다. 그래서 **그 둘만** 어긋났다.
 *
 * 🚩 **원문을 정규식으로 훑지 않고 함수를 실제로 돌린다.** 「소스에 낱말이
 * 있는가」로 재면 주석이나 다른 줄의 라벨이 걸려 조용히 통과한다 — 이
 * 저장소에서 여러 번 밟은 함정이다(`tests/source.js` 머리말).
 *
 * 그린 높이는 브라우저에서 쟀다(PR 에 측정값을 적었다). 여기서 재는 것은
 * **라벨 자리가 빠지지 않는가**와 **그것이 필요한 이유(CSS)가 그대로인가**다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, rule } = require("./source.js");

const JS = () => read("js/ocr-review.js");

/** IIFE 안에 갇힌 함수를 **꺼내 와 실제로 부른다.**
 *
 * 🚩 **틀리면 조용히 넘어가지 않는다** — `2heej` `#347` 리뷰 4번을 재 봤다.
 * 자르는 자리가 어긋나는 경우는 셋이고, 셋 다 크게 운다.
 *
 * - 이름이 바뀌어 못 찾음 → 아래 `assert.notEqual(start, -1)`
 * - 끝을 못 찾음(들여쓰기가 통째로 바뀜) → `assert.notEqual(end, -1)`
 * - 몸통 안에 2칸 들여쓴 `function ` 줄이 끼어 **덜 잘림** → `new Function` 이
 *   문법 오류를 던진다. 몸통이 닫히지 않은 채 잘리기 때문이다.
 *
 * 사이에 새 최상위 함수가 끼어드는 것은 문제가 아니다 — 끝이 그 앞에서 멈출
 * 뿐 우리 함수는 온전히 잘린다.
 *
 * `ocr-review.js` 는 통째로 즉시실행 함수 안이라 shim 으로 못 집는다. 선언
 * 자리부터 다음 선언 직전까지를 잘라 필요한 것만 주입해 돌린다. 잘라 낸 자리에
 * 남는 꼬리 주석은 문장 목록으로 그대로 성립하므로 건드리지 않는다.
 */
function lift(name, deps) {
  const src = JS();
  const start = src.indexOf(`  function ${name}(`);
  assert.notEqual(start, -1, `${name} 이 없다 — 검사가 헛돈다`);
  const end = src.indexOf("\n  function ", start + 1);
  assert.notEqual(end, -1, `${name} 의 끝을 못 찾았다 — 검사가 헛돈다`);

  const names = Object.keys(deps);
  const make = new Function(...names, `${src.slice(start, end)}\nreturn ${name};`);
  return make(...names.map((k) => deps[k]));
}

const escapeHtml = (v) => String(v == null ? "" : v).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
);

/* 실제 `field-labels.js` 를 그대로 쓴다 — 지어낸 이름으로 재면 3번 인수조건을
   못 지킨다. */
function realFieldLabel() {
  const { fieldLabel } = load("field-labels");
  assert.equal(typeof fieldLabel, "function", "field-labels.js 가 fieldLabel 을 안 낸다");
  return fieldLabel;
}

/** `.top` 한 줄을 칸 단위로 쪼갠다. 만들어 낸 마크업이라 모양이 단순하다. */
function cellsOf(rowHtml) {
  const marks = [];
  const needle = '<div class="top__cell';
  for (let i = rowHtml.indexOf(needle); i !== -1; i = rowHtml.indexOf(needle, i + 1)) marks.push(i);
  assert.ok(marks.length, `칸을 못 찾았다:\n${rowHtml}`);
  return marks.map((at, i) => rowHtml.slice(at, i + 1 < marks.length ? marks[i + 1] : rowHtml.length));
}

/** 값이 보이는 칸은 **전부** 라벨을 갖는다. 빈 자리만 예외다. */
function assertEveryVisibleCellHasALabel(rowHtml, where) {
  for (const cell of cellsOf(rowHtml)) {
    if (cell.includes('aria-hidden="true"')) {
      assert.ok(
        !cell.includes('class="top__label"'),
        `${where}: 읽히지 않는 빈 자리에 라벨을 세웠다 — 폭만 차지해야 한다:\n${cell}`,
      );
      continue;
    }
    assert.ok(
      cell.includes('class="top__label"'),
      `${where}: 라벨 없는 칸이 있다 — 이 칸의 값칸만 23px 위로 올라붙는다:\n${cell}`,
    );
  }
}

/* ── 추가 약품 행 ──────────────────────────────────────────────────── */

function extraRows() {
  return lift("extraDrugRowsHtml", {
    escapeHtml,
    fieldLabel: realFieldLabel(),
    fieldBody: () => ({ clash: false, state: "ok", body: '<input class="field__input" />' }),
  });
}

const field = (type, value) => ({ field_type: type, value });

test("**추가 약품 행의 모든 칸이 라벨을 갖는다** — 없는 칸만 23px 올라붙던 자리", () => {
  const html = extraRows()([
    field("MEDICATION_NAME_2", "바이독시정(독시사이클린수화물)"),
    field("DURATION_DAYS_2", "7"),
  ]);

  assert.ok(html.includes('<div class="top">'), "행을 안 만들었다");
  assertEveryVisibleCellHasALabel(html, "추가 약품 행");
});

test("두 줄 이상이어도 줄마다 그렇다 — 한 줄만 고치고 끝내지 않게", () => {
  const html = extraRows()([
    field("MEDICATION_NAME_2", "바이독시정"),
    field("DURATION_DAYS_2", "7"),
    field("MEDICATION_NAME_3", "레바미피드정"),
    field("DURATION_DAYS_3", "7"),
  ]);

  const rows = html.split('<div class="top">').slice(1);
  assert.equal(rows.length, 2, "줄 수가 틀렸다");
  rows.forEach((row, i) => assertEveryVisibleCellHasALabel(row, `추가 약품 ${i + 1}번째 줄`));
});

test("약품명 칸만 있어도 라벨이 선다 — 처방일수를 못 읽은 문서", () => {
  const html = extraRows()([field("MEDICATION_NAME_2", "바이독시정")]);
  assertEveryVisibleCellHasALabel(html, "처방일수 없는 추가 약품 행");
});

/* ── 수동 추가 행 ──────────────────────────────────────────────────── */

test("**「+ 약 추가」로 만든 줄도 그렇다** — 같은 결함이 여기 그대로 있었다", () => {
  const html = lift("manualDrugRowsHtml", {
    escapeHtml,
    fieldLabel: realFieldLabel(),
    manualDrugs: [{ name: "레바미피드정", days: 7 }],
  })();

  assert.ok(html.includes('<div class="top">'), "행을 안 만들었다");
  assertEveryVisibleCellHasALabel(html, "수동 추가 행");
});

/* ── 낱말은 한 곳에서 온다 ─────────────────────────────────────────── */

/* 🚩 **두 함수를 합쳐 놓고 재면 안 된다.** 처음에 그렇게 짰다가 걸렸다 —
   `extraDrugRowsHtml` 이 「복용일수」로 지어내도 `manualDrugRowsHtml` 이 내놓은
   「처방일수」가 합친 글자열에 있어서 **그대로 통과했다.** 낱말을 재는 검사는
   내놓는 자리마다 따로 봐야 한다. */
test("라벨 문구를 지어내지 않는다 — `field-labels.js` 것을 쓴다 (인수조건 3)", () => {
  const fieldLabel = realFieldLabel();
  const made = {
    "추가 약품 행": extraRows()([field("MEDICATION_NAME_2", "가"), field("DURATION_DAYS_2", "7")]),
    "수동 추가 행": lift("manualDrugRowsHtml", {
      escapeHtml,
      fieldLabel,
      manualDrugs: [{ name: "나", days: 7 }],
    })(),
  };

  for (const [where, html] of Object.entries(made)) {
    const said = [...html.matchAll(/<span class="top__label">([^<]*)<\/span>/g)].map((m) => m[1]);
    assert.deepEqual(
      said,
      [fieldLabel("MEDICATION_NAME"), fieldLabel("DURATION_DAYS")],
      `${where} 의 라벨이 field-labels.js 것과 다르다 — 같은 항목이 화면마다 다른 이름으로 불린다`,
    );
  }
});

/* 🚩 **위 검사는 자기 자신과 견준다** — `2heej` `#347` 리뷰 3번.
   `fieldLabel()` 끼리 맞는지만 보므로, `field-labels.js` 의 낱말 자체가 오타로
   바뀌어도 그대로 통과한다. `MEDICATION_NAME` 은 `field-labels.test.js` 가
   「약품명」으로 고정해 두었지만 **`DURATION_DAYS` 는 어디서도 고정되지 않았다.**
   그래서 화면에 실제로 찍히는 글자를 여기서 못 박는다. */
test("화면에 찍히는 낱말을 글자 그대로 못 박는다 — 원천이 바뀌어도 여기서 걸린다", () => {
  const fieldLabel = realFieldLabel();
  const made = {
    "추가 약품 행": extraRows()([field("MEDICATION_NAME_2", "가"), field("DURATION_DAYS_2", "7")]),
    "수동 추가 행": lift("manualDrugRowsHtml", {
      escapeHtml,
      fieldLabel,
      manualDrugs: [{ name: "나", days: 7 }],
    })(),
  };

  for (const [where, html] of Object.entries(made)) {
    const said = [...html.matchAll(/<span class="top__label">([^<]*)<\/span>/g)].map((m) => m[1]);
    assert.deepEqual(said, ["약품명", "처방일수"], `${where} 의 라벨 글자가 바뀌었다: ${JSON.stringify(said)}`);
  }
});

/* ── 라벨이 필요한 **이유** ────────────────────────────────────────── */

test("🚩 라벨 규칙이 서 있는 까닭을 함께 못 박는다 — CSS 가 바뀌면 여기서 걸린다", () => {
  const css = codeOnly(read("css/ocr-review.css"));

  /* 위로 맞추기 때문에 첫 요소의 높이가 아래를 통째로 민다. KEY-293 에서
     `flex-end` 였던 것을 일부러 바꾼 자리라 되돌아갈 수 있다. */
  assert.match(
    rule(css, ".top"),
    /align-items:\s*flex-start/,
    "`.top` 이 더 이상 위로 안 맞춘다 — 라벨 자리를 요구하는 위 검사들의 근거가 사라졌다",
  );

  /* 어긋나던 23px 의 정체 — 라벨 높이 18 + 칸 간격 5. */
  const label = rule(css, ".top__label");
  const cell = rule(css, ".top__cell");
  const min = /min-height:\s*(\d+)px/.exec(label);
  const gap = /gap:\s*(\d+)px/.exec(cell);
  assert.ok(min, "`.top__label` 의 min-height 를 못 읽었다");
  assert.ok(gap, "`.top__cell` 의 gap 을 못 읽었다");
  assert.equal(
    Number(min[1]) + Number(gap[1]),
    23,
    "라벨 높이+간격이 브라우저에서 잰 어긋남(23px)과 안 맞는다 — 한쪽만 바뀌었다",
  );
});
