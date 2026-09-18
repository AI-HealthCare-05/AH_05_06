/* 숨긴 대표 처방은 **설정 동선에서 아예 안 보인다** — KEY-369.
 *
 * KEY-357 이 옛 이름 아홉을 한꺼번에 감추자 설정 화면이 「(숨김)」 아홉 줄로
 * 덮였다. 새로 고를 수 있는 넷이 그 사이에 묻혀, 목록이 「고를 것을 보여 주는
 * 자리」가 아니라 「지난 이름을 늘어놓는 자리」가 됐다.
 *
 * 거르는 것은 **상태 하나**다 — 옛 이름을 코드에 적으면 이름이 늘 때마다 또
 * 뒤처진다. 되살리는 화면은 이번 범위 밖이라 만들지 않는다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

const box = () => load("api", "session", "field-labels", "settings-rail", "drug-lines");

const SETS = [
  { prescription_set_id: 10, name: "자궁내막증 · 비잔 O", disease: "ENDOMETRIOSIS", hidden: false },
  { prescription_set_id: 11, name: "자궁내막증 · 비잔 X", disease: "ENDOMETRIOSIS", hidden: false },
  { prescription_set_id: 1, name: "자궁내막증 · 비잔 (처음)", disease: "ENDOMETRIOSIS", hidden: true },
  { prescription_set_id: 12, name: "PCOS · 야즈 O", disease: "PCOS", hidden: false },
  { prescription_set_id: 8, name: "PCOS · 대사관리", disease: "PCOS", hidden: true },
];

test("보이는 목록에서 감춘 것을 뺀다", () => {
  const { visibleSets } = box();

  assert.deepEqual(
    visibleSets(SETS).map((row) => row.prescription_set_id),
    [10, 11, 12],
  );
  /* 서버가 칸을 안 줬을 때도 지우지 않는다 — 모르면 보이는 것으로 본다 */
  assert.deepEqual(visibleSets([{ prescription_set_id: 3, name: "옛 화면" }]).length, 1);
  assert.deepEqual(visibleSets(null), []);
});

test("질환 묶음도 감춘 것을 안 담는다 — 레일·접힘 열쇠가 같은 함수를 쓴다", () => {
  const { setsByDisease, railGroupKey } = box();
  const blocks = setsByDisease(SETS);

  assert.deepEqual(
    blocks.map((block) => [block.key, block.sets.map((row) => row.prescription_set_id)]),
    [
      ["ENDOMETRIOSIS", [10, 11]],
      ["PCOS", [12]],
    ],
  );
  /* 숨긴 세트를 누를 길이 없으니 접힘 열쇠도 안 나온다 */
  assert.equal(railGroupKey(SETS, 12), "PCOS");
  assert.equal(railGroupKey(SETS, 1), null);
});

test("한 질환이 통째로 감춰지면 그 묶음 자체가 사라진다", () => {
  const { setsByDisease } = box();
  const onlyHidden = SETS.filter((row) => row.disease === "PCOS").map((row) => ({ ...row, hidden: true }));

  assert.deepEqual(setsByDisease(onlyHidden), []);
});

test("셋을 다 감추면 빈 상태가 선다 — 「대표 처방이 없습니다」", () => {
  const { setsByDisease } = box();
  const code = codeOnly(read("js/settings.js"));

  assert.deepEqual(setsByDisease(SETS.map((row) => ({ ...row, hidden: true }))), []);
  assert.match(code, /rail__none">대표 처방이 없습니다/, "빈 상태 문구가 없다");
  assert.match(code, /대표 처방을 선택하면 상세 설정이 표시됩니다/, "상세 빈 상태가 없다");
});

test("고른 것이 감춰지면 첫 활성 세트로 옮기고, 남은 것이 없으면 상세를 비운다", () => {
  /* 화면을 그리는 자리라 원문으로 잰다 — shim 은 그리지 않는다. */
  const code = codeOnly(read("js/settings.js"));
  const at = code.indexOf("function settleSelection(");
  assert.notEqual(at, -1, "옮기는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.match(body, /visibleSets\(sets\)/, "보이는 목록을 안 본다");
  assert.match(body, /if \(making\) return/, "만들기 중인 판까지 건드린다");
  assert.match(body, /pickedId = null;\s*picked = null;/, "남은 것이 없을 때 상세를 안 비운다");
  assert.match(body, /loadSet\(shown\[0\]\.prescription_set_id\)/, "첫 활성 세트로 안 옮긴다");

  /* 목록을 다시 받을 때마다 정리한다 — 다른 사람이 감춘 경우도 같은 자리다 */
  const loadAt = code.indexOf("function loadSets()");
  const loadBody = code.slice(loadAt, code.indexOf("\n  }", loadAt));
  assert.match(loadBody, /settleSelection\(\)/, "목록을 새로 받아도 고른 것을 안 다시 본다");
});
