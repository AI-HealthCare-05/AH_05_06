/* **숫자만 쳐도 하이픈이 붙는다** — 환자 등록의 생년월일 · 휴대폰.
 *
 * 스탭은 EMR 을 보며 옮겨 적는다. 거기 적힌 것은 `19940722` · `01047851256`
 * 같은 숫자열이라, 하이픈을 손으로 넣게 하면 자리를 세어 가며 친다. 게다가
 * 안 넣으면 「생년월일은 1994-07-22 처럼 적어 주세요」로 막혀 다시 고친다.
 *
 * 자리 셈은 눈으로 확인하기 어렵다 — 그래서 규칙을 화면 밖에 두고 여기서 잰다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function box() {
  return load("api", "session", "patients-api");
}

/* ── 생년월일 ───────────────────────────────────────────────────────── */

test("**다 치면 제 모양이 된다**", () => {
  const { birthMask } = box();
  assert.equal(birthMask("19940722"), "1994-07-22");
  assert.equal(birthMask("1994-07-22"), "1994-07-22", "이미 붙은 것을 또 붙인다");
});

test("**치는 도중에도 자연스럽다** — 다 친 뒤에만 모양을 잡으면 화면이 튄다", () => {
  const { birthMask } = box();
  assert.equal(birthMask("1"), "1");
  assert.equal(birthMask("1994"), "1994", "네 자리에서 벌써 하이픈이 붙는다");
  assert.equal(birthMask("19940"), "1994-0");
  assert.equal(birthMask("199407"), "1994-07");
  assert.equal(birthMask("1994072"), "1994-07-2");
});

test("여덟 자리를 넘기지 않는다 — 넘치면 뒤가 잘려 보인다", () => {
  const { birthMask } = box();
  assert.equal(birthMask("1994072299"), "1994-07-22");
});

test("숫자가 아닌 것은 버린다 — 붙여넣기가 흔하다", () => {
  const { birthMask } = box();
  assert.equal(birthMask("1994.07.22"), "1994-07-22");
  assert.equal(birthMask("1994년 7월 22일"), "1994-72-2", "숫자만 남긴 결과가 아니다");
  assert.equal(birthMask(""), "");
  assert.equal(birthMask(null), "");
});

/* ── 휴대폰 ─────────────────────────────────────────────────────────── */

test("**열한 자리는 3-4-4, 열 자리는 3-3-4**", () => {
  const { phoneMask } = box();
  assert.equal(phoneMask("01047851256"), "010-4785-1256");

  /* 010 만 보고 가운데를 4로 박으면 옛 번호가 `011-2345-678` 로 어긋난다 */
  assert.equal(phoneMask("0112345678"), "011-234-5678");
});

test("치는 도중에도 자연스럽다", () => {
  const { phoneMask } = box();
  assert.equal(phoneMask("010"), "010");
  assert.equal(phoneMask("0104"), "010-4");
  assert.equal(phoneMask("010478"), "010-478");
  assert.equal(phoneMask("0104785125"), "010-478-5125");
  assert.equal(phoneMask("01047851256"), "010-4785-1256", "열한 번째에서 가운데가 다시 묶인다");
});

test("열한 자리를 넘기지 않는다", () => {
  const { phoneMask } = box();
  assert.equal(phoneMask("010478512569"), "010-4785-1256");
});

test("**담아 둔 번호도 같은 규칙으로 보인다** — 두 벌이면 화면마다 다르다", () => {
  const { phoneMask, formatPhone } = box();
  assert.equal(formatPhone("01047851256"), phoneMask("01047851256"));
  assert.equal(formatPhone("0112345678"), phoneMask("0112345678"));

  /* 규칙이 한 곳에만 있어야 한다 — 복사본이 생기면 한쪽만 고쳐진다 */
  const src = codeOnly(read("js/patients-api.js"));
  assert.equal(
    (src.match(/function formatPhone/g) || []).length,
    1,
    "formatPhone 이 여럿이다",
  );
  assert.ok(
    !/d\.length === 11\) return d\.slice\(0, 3\)/.test(codeOnly(read("js/detail.js"))),
    "detail.js 에 번호 모양 규칙 복사본이 남아 있다",
  );
});

/* ── 커서 ───────────────────────────────────────────────────────────── */

test("**커서가 끝으로 튀지 않는다** — 가운데를 고치던 손이 자리를 잃는다", () => {
  const { maskCaret } = box();

  /* 「숫자 넷을 지난 자리」는 하이픈이 붙어도 그 숫자 뒤다 */
  assert.equal(maskCaret("1994-07-22", 4), 4);
  assert.equal(maskCaret("1994-07-22", 5), 6, "하이픈만큼 밀리지 않았다");
  assert.equal(maskCaret("1994-07-22", 8), 10);
  assert.equal(maskCaret("1994-07-22", 0), 0);

  /* 숫자보다 많이 세면 끝이다 — 넘어가서 던지면 안 된다 */
  assert.equal(maskCaret("1994", 9), 4);
});

test("**하이픈을 지우면 그 앞 숫자가 지워진다** — 안 그러면 두 번 눌러야 한다", () => {
  const { maskAfterDelete } = box();

  /* `1994-07-22` 에서 하이픈을 지우면 숫자는 그대로다(`19940722`).
     그대로 두면 하이픈이 곧바로 다시 붙어 지운 것이 없어 보인다. */
  assert.deepEqual(maskAfterDelete("19940722", 4), { digits: "1990722", at: 3 });

  /* 맨 앞에서는 지울 것이 없다 */
  assert.deepEqual(maskAfterDelete("19940722", 0), { digits: "19940722", at: 0 });
});

/* ── 화면에 붙어 있는가 ─────────────────────────────────────────────── */

test("**두 칸이 실제로 그 규칙을 쓴다**", () => {
  const code = codeOnly(read("js/patients.js"));

  const at = code.indexOf("var MASKS");
  assert.notEqual(at, -1, "어느 칸에 붙일지 정하는 자리가 없다");
  const table = code.slice(at, at + 200);
  assert.match(table, /"f-birth":\s*birthMask/, "생년월일에 안 붙는다");
  assert.match(table, /"f-phone":\s*phoneMask/, "휴대폰에 안 붙는다");

  const use = code.indexOf("function applyMask");
  assert.notEqual(use, -1, "붙이는 자리가 없다");
  const body = code.slice(use, code.indexOf("\n  }", use));
  /* **부르는 자리**를 본다. 그냥 `setSelectionRange` 를 찾으면 있는지 없는지
     묻는 줄(`typeof ... === "function"`)에 걸려 늘 통과한다. */
  assert.match(body, /\.setSelectionRange\(\s*\w+\s*,/, "커서를 안 옮긴다 — 끝으로 튄다");
  assert.match(body, /maskCaret\(/, "커서 자리를 셈하지 않는다");
  assert.match(body, /deleteContentBackward/, "하이픈을 지울 때 두 번 눌러야 한다");

  /* 손잡이가 실제로 부르는가 — 만들어만 두면 화면은 옛길로 간다 */
  assert.match(code, /applyMask\(this, id, event\)/, "입력을 받을 때 안 부른다");
});

test("고른 환자를 채울 때도 같은 모양이다 — 친 것과 다르면 잘못 친 것처럼 보인다", () => {
  const code = codeOnly(read("js/patients.js"));
  const at = code.indexOf('el("f-birth").value');
  assert.notEqual(at, -1, "고른 환자를 안 채운다");

  const around = code.slice(at, at + 200);
  assert.match(around, /birthMask\(/, "생년월일을 날것으로 채운다");
  assert.match(around, /phoneMask\(/, "번호를 다른 규칙으로 채운다");
});

test("숫자판이 먼저 뜬다 — 손가락이 문자판에서 숫자를 찾지 않는다", () => {
  const html = read("patients.html");
  for (const id of ["f-birth", "f-phone"]) {
    const tag = new RegExp(`<input[^>]*id="${id}"[^>]*>`).exec(html);
    assert.ok(tag, `${id} 칸이 없다`);
    assert.match(tag[0], /inputmode="numeric"/, `${id} 에 숫자판이 안 뜬다`);
  }
});
