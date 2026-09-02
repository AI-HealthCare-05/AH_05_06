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
  return load("api", "session", "field-labels", "settings-rail", "drug-lines");
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

test("**처방 설정은 아직 아무도 못 고친다** — 표가 전 의원 공용이다", () => {
  /* `prescription_set` 에는 `hospital_id` 가 없다 — 여덟 처방 유형을 모든
     의원이 함께 쓴다. 역할(의사)만 보고 쓰기를 열었더니 어느 의원 의사든
     다른 의원의 질환 분류 · 총투 해석 · 소진 예정일 셈법을 바꿀 수 있었다.
     2heej 님이 `#183` 리뷰에서 찾아 주셨다.

     **표를 가르기 전까지는 닫아 둔다.** 고칠 수 있는 것처럼 보이는 화면이
     조용히 남의 의원 것을 바꾸는 것보다, 못 고치는 편이 낫다. */
  const code = codeOnly(read("js/settings.js"));

  /* 다른 설정(D2-4·D2-5)과 **다른 깃발**을 쓴다 — `canEdit` 을 같이 내리면
     기준선과 문자 문구까지 못 고치게 된다 */
  assert.match(code, /var canEditSet = false;/, "처방 전용 깃발이 없다");
  assert.ok(
    !/canEditSet = /.test(code.replace("var canEditSet = false;", "")),
    "어딘가에서 다시 켠다 — 그러면 닫은 것이 아니다",
  );

  /* 저장 단추가 잠긴다 */
  const at = code.indexOf('id="set-save"');
  assert.notEqual(at, -1, "저장 단추 자리가 없다");
  assert.match(code.slice(at, at + 160), /canEditSet \? "" : " disabled"/, "단추가 눌린다");

  /* 왜 못 고치는지 말한다 — 잠긴 단추만 두면 고장으로 읽힌다.
     「의사 계정만」이라 적으면 의사가 눌러 보고 안 되는 것으로 읽는다. */
  assert.ok(
    code.includes("모든 의원이 함께 쓰는 값이라 아직 고칠 수 없습니다"),
    "왜 잠겼는지 안 말하거나, 의사면 된다고 잘못 말한다",
  );

  /* **부를 길이 아예 없어야 한다.** 단추만 잠그면 화면 하나가 바뀔 때 뚫린다 */
  assert.ok(!code.includes("catalogApi.saveSet"), "아직 저장 API 를 부른다");
  assert.ok(!/function save\(\)/.test(code), "저장 함수가 남아 있다");

  /* 서버에도 길이 없어야 한다 */
  const api = read("../app/catalog/api.py");
  assert.ok(
    !/@catalog_router\.put\("\/prescription-sets/.test(api),
    "서버가 아직 쓰기를 연다 — 화면만 막으면 요청 하나로 뚫린다",
  );
  assert.match(api, /@catalog_router\.get\("\/prescription-sets/, "읽기까지 걷으면 판독 화면이 못 고른다");
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
