/* **처방 설정** — 와이어프레임 D2-3.
 *
 * 처방 세트가 이름 하나뿐이었다. 의사가 정할 것들이 어디에도 없어서 「어느
 * 처방에 무엇을 여쭐지」도 「소진 예정일을 어떻게 셈할지」도 코드에 박혀 있었다.
 *
 * 왼쪽 레일은 다른 화면의 환자 목록 자리다 — 골격이 같아야 화면을 옮길 때
 * 눈이 새로 자리를 찾지 않는다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly, rule } = require("./source.js");

function box() {
  return load("api", "session", "field-labels", "settings-rail");
}

const SETS = [
  { prescription_set_id: 1, name: "자궁내막증 · 비잔 (처음)", disease: "ENDOMETRIOSIS" },
  { prescription_set_id: 2, name: "자궁내막증 · 비잔 (계속)", disease: "ENDOMETRIOSIS" },
  { prescription_set_id: 4, name: "PCOS · 초진", disease: "PCOS" },
];

/* ── 왼쪽 레일 ──────────────────────────────────────────────────────── */

test("**질환으로 묶는다** — 아홉이 한 줄기로 늘어지면 「그 밖에」가 화면 밖으로 밀린다", () => {
  const { setsByDisease } = box();
  const groups = setsByDisease(SETS);

  assert.deepEqual(
    groups.map((g) => [g.title, g.sets.length]),
    [["자궁내막증", 2], ["다낭성난소증후군", 1]],
    "묶음이나 차례가 다르다",
  );
});

test("빈 묶음은 내지 않는다 — 개수 0 이 서 있으면 눌러 볼 것이 없다", () => {
  const { setsByDisease } = box();
  const only = setsByDisease([SETS[2]]);
  assert.deepEqual(only.map((g) => g.title), ["다낭성난소증후군"]);
  assert.deepEqual(setsByDisease([]), []);
});

test("**모르는 질환도 버리지 않는다** — 사라진 것과 없는 것은 다르다", () => {
  /* 서버가 값을 늘렸는데 화면이 모르면 그 처방이 목록에서 통째로 사라진다.
     의사는 「내가 만든 처방이 없어졌다」로 읽는다. */
  const { setsByDisease } = box();
  const groups = setsByDisease(SETS.concat([{ name: "새 병", disease: "SOMETHING_NEW" }]));

  const rest = groups.filter((g) => g.key === "other")[0];
  assert.ok(rest, "모르는 질환이 사라졌다");
  assert.deepEqual(rest.sets.map((s) => s.name), ["새 병"]);
});

/* 처방 검색은 **없앴다.** 처방이 아홉이라 한 화면에 다 서고, 검색칸이 있으면
   「검색해야 보이나」로 읽힌다 — 환자 목록과는 다른 자리다. 규칙(`filterSets`)
   도 함께 지웠다: 안 쓰는 코드를 남겨 두면 다음 사람이 살아 있는 줄 안다. */
test("설정 레일에 검색칸이 없다", () => {
  const markup = markupOnly(read("settings.html"));
  const code = codeOnly(read("js/settings.js")) + codeOnly(read("js/settings-rail.js"));

  assert.ok(markup.indexOf("set-search") === -1);
  assert.ok(code.indexOf("filterSets") === -1, "쓰지 않는 규칙이 남아 있다");
});

/* ── 처방일수 셈 ────────────────────────────────────────────────────── */

test("**「총투」의 뜻이 소진 예정일을 정한다**", () => {
  /* 「3」이 3통일 수도 3일일 수도 있고 의원마다 다르다 — 틀리면 소진 임박
     문자가 엉뚱한 날 간다. */
  const { courseDaysOf } = box();

  assert.equal(courseDaysOf({ days_mode: "DAYS" }, 84), 84);
  assert.equal(courseDaysOf({ days_mode: "PACK", days_per_pack: 28 }, 3), 84);
});

test("**모르면 셈하지 않는다** — 지어낸 날짜로 예약하면 엉뚱한 날 문자가 간다", () => {
  const { courseDaysOf } = box();

  /* 통으로 세는데 한 통이 며칠인지 모른다 */
  assert.equal(courseDaysOf({ days_mode: "PACK" }, 3), null);
  assert.equal(courseDaysOf({ days_mode: "PACK", days_per_pack: 0 }, 3), null);

  /* 적힌 값이 숫자가 아니거나 0 이하다 */
  assert.equal(courseDaysOf({ days_mode: "DAYS" }, ""), null);
  assert.equal(courseDaysOf({ days_mode: "DAYS" }, "며칠"), null);
  assert.equal(courseDaysOf({ days_mode: "DAYS" }, 0), null);
  assert.equal(courseDaysOf(null, 84), 84, "설정을 못 읽어도 적힌 일수는 쓴다");
});

/* ── 화면 ───────────────────────────────────────────────────────────── */

test("**고치는 것은 의사만** — 스탭은 볼 수만 있다", () => {
  /* 와이어프레임 D2-2 가 못박는다. 이 값이 안내문과 문자 발송일을 정하므로
     의료 판단에 걸린다. 화면에서 잠그는 것은 편의일 뿐 실제 차단은 서버다. */
  const code = codeOnly(read("js/settings.js"));

  /* 선언(`var canEdit = false`)이 아니라 **정하는 자리**를 본다 — 선언만 찾으면
     역할을 안 봐도 통과한다. */
  assert.match(code, /canEdit = \(who\.roles \|\| \[\]\)\.indexOf\("doctor"\)/, "역할을 안 본다");

  /* 잠긴 화면이면 저장 단추도 잠긴다 */
  const save = code.indexOf('id="set-save"');
  assert.match(code.slice(save, save + 160), /canEdit \? "" : " disabled"/, "스탭에게도 눌린다");

  /* 왜 못 고치는지 말한다 — 잠긴 단추만 두면 고장으로 읽힌다 */
  assert.ok(code.includes("의사 계정만 수정할 수 있습니다"), "왜 잠겼는지 안 말한다");

  /* 서버도 막는지 — 화면만 막으면 요청 하나로 뚫린다 */
  const api = read("../app/catalog/api.py");
  assert.match(api, /StaffRole\.DOCTOR/, "서버가 역할을 안 본다");
});

test("**저장이 막혀도 친 값이 남는다** — 고치라는데 고칠 것이 사라지면 안 된다", () => {
  const code = codeOnly(read("js/settings.js"));
  const at = code.indexOf("function save()");
  assert.notEqual(at, -1, "저장하는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));
  /* 다시 그리기 **전에** 화면에 적힌 것을 거둔다 */
  assert.match(body, /var plan = planNow\(\);/, "화면 값을 안 거둔다");
  assert.ok(
    body.indexOf("planNow()") < body.indexOf("render()"),
    "다시 그린 뒤에 거둔다 — 이미 날아간 값을 거두는 셈이다",
  );
  assert.match(body, /picked = Object\.assign\(\{\}, picked, plan\)/, "거둔 것을 안 붙든다");

  /* **서버가 돌려준 것으로 갈아 끼운다.** 서버가 고쳐 준 값(일수로 바꾸면 통
     크기를 비운다)이 화면에 안 보이면, 화면과 서버가 다른 값을 들고 있게 된다.
     성공한 길 안에서 찾아야 한다 — 실패 길의 `picked` 대입에 걸리면 헛돈다. */
  const ok = body.slice(body.indexOf(".then("), body.indexOf(".catch("));
  assert.match(ok, /picked = data;/, "저장 뒤 서버 값을 안 쓴다");
  assert.ok(ok.includes('saying = "저장되었습니다"'), "저장했다고 말은 하는데 값을 안 갈아 끼운다");
  assert.match(ok, /pickedId !== wanted/, "다른 처방 화면에 붙는다");
});

test("**한 판을 통째로 보낸다** — 조각으로 보내면 반쪽이 남는다", () => {
  const code = codeOnly(read("js/settings.js"));
  const at = code.indexOf("function planNow");
  assert.notEqual(at, -1, "보낼 것을 모으는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));
  for (const key of ["drugs", "check_items", "days_mode", "run_out_before_days", "emr_code"]) {
    assert.ok(body.includes(key), `${key} 를 안 보낸다`);
  }

  /* 일수로 세면 통 크기를 안 보낸다 — 서버도 비우지만 화면부터 맞춘다 */
  assert.match(body, /mode === "PACK" && per/, "일수로 세는데 통 크기를 보낸다");
});

test("아직 없는 묶음은 **없다고 적는다** — 빈 자리는 무엇을 만들지 안 보인다", () => {
  const { RAIL_GROUPS } = box();
  assert.ok(RAIL_GROUPS.length >= 3, "그 밖의 묶음이 없다");
  for (const group of RAIL_GROUPS) {
    assert.ok(group.title, `${group.key} 에 이름이 없다`);
    assert.ok(group.note, `${group.key} 에 어느 프레임인지 안 적혀 있다`);
    assert.ok(group.saying, `${group.key} 에 무엇이 없는지 안 적혀 있다`);
  }
});

test("설정 화면이 골격을 그대로 쓴다 — 옮길 때 눈이 자리를 새로 찾지 않는다", () => {
  const html = markupOnly(read("settings.html"));

  /* 왼쪽 레일은 다른 화면의 환자 목록 자리다. **검색칸은 뺐다** — 처방이
     아홉이라 한 화면에 다 서고, 검색칸이 있으면 「검색해야 보이나」로 읽힌다. */
  for (const part of ['class="list"', 'class="list__head"', 'class="pane"']) {
    assert.ok(html.includes(part), `골격이 다르다: ${part}`);
  }

  /* 담는 모양은 공용이다 — 여기서 상자를 새로 그리지 않는다 */
  const css = read("css/settings.css");
  assert.ok(!/^\.box\s*\{/m.test(css), "설정 화면이 제 상자를 따로 그린다");

  /* 이 화면만의 것은 여기 있어야 한다 */
  rule(css, ".rail__row");
  rule(css, ".drug");
});

test("고른 처방을 실제로 불러온다 — 안 넣으면 늘 빈 화면이다", () => {
  const code = codeOnly(read("js/settings.js"));
  /* **괄호까지 짚는다.** `loadSet` 으로 찾으면 `loadSets`(목록)가 먼저 걸려
     엉뚱한 함수를 재게 된다 — 실제로 그렇게 헛돌았다. */
  const at = code.indexOf("function loadSet(id)");
  assert.notEqual(at, -1, "불러오는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.match(body, /catalogApi\s*\.?\s*set\(/, "서버에 안 묻는다");
  assert.match(body, /picked = data;/, "받아서 화면에 안 넣는다");
  /* 늦게 온 답이 다른 처방 화면에 붙으면 안 된다 */
  assert.match(body, /mine !== loadSeq/, "차례를 안 본다");
});
