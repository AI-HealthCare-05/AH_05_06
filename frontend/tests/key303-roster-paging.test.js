/* 환자 관리 표를 25명씩 끊어 넘긴다 — KEY-303.
 *
 * **전에는 조용히 잘렸다.** `manage.js` 가 `roster(keyword, chosen, null, 50)` (그때의 모양) 을
 * 한 번 부르고 `next_cursor` 를 아무도 안 봤다. 전체가 101명이어도 50명에서
 * 끝났고, 배지는 서버가 세어 준 101 을 그대로 보여 줘서 **잘린 줄도 몰랐다.**
 *
 * 커서가 아니라 자리(offset)로 센다 — 커서는 앞으로만 가서 「이전」이 안 된다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

function box() {
  return load("roster-paging");
}

test("**101명을 40씩 세 쪽으로 나눈다** — 마지막 쪽은 21명", () => {
  const { rosterPaging } = box();

  const first = rosterPaging(101, 0, 40);
  assert.deepStrictEqual(
    { page: first.page, pages: first.pages, from: first.from, to: first.to },
    { page: 1, pages: 3, from: 1, to: 40 },
  );
  assert.equal(first.hasPrev, false, "첫 쪽에서 뒤로 갈 데가 없다");
  assert.equal(first.hasNext, true);

  const last = rosterPaging(101, 80, 40);
  assert.deepStrictEqual(
    { page: last.page, pages: last.pages, from: last.from, to: last.to },
    { page: 3, pages: 3, from: 81, to: 101 },
  );
  assert.equal(last.hasNext, false, "마지막 쪽에서 앞으로 갈 데가 없다");
  assert.equal(last.hasPrev, true);
});

test("자리를 앞뒤로 옮긴다 — 첫 쪽 아래로 안 내려간다", () => {
  const { rosterPaging } = box();

  assert.equal(rosterPaging(101, 40, 40).prevOffset, 0);
  assert.equal(rosterPaging(101, 40, 40).nextOffset, 80);
  assert.equal(rosterPaging(101, 0, 40).prevOffset, 0, "첫 쪽에서 뒤로 가도 음수가 안 된다");
});

test("한 쪽에 다 들어가면 쪽 이야기를 안 한다", () => {
  const { rosterPaging, rosterPagingSaying } = box();

  const one = rosterPaging(25, 0, 40);
  assert.equal(one.pages, 1);
  assert.equal(one.hasNext, false);
  assert.equal(rosterPagingSaying(one), "25명 중 1–25", "쪽 수를 말하면 넘길 데가 있는 줄 안다");
  assert.match(rosterPagingSaying(rosterPaging(101, 0, 40)), /101명 중 1–40 · 1\/3쪽/);
});

test("0명이어도 무너지지 않는다", () => {
  const { rosterPaging, rosterPagingSaying } = box();

  const none = rosterPaging(0, 0, 40);
  assert.deepStrictEqual({ page: none.page, pages: none.pages, from: none.from, to: none.to }, { page: 1, pages: 1, from: 0, to: 0 });
  assert.equal(none.hasNext, false);
  assert.equal(none.hasPrev, false);
  assert.equal(rosterPagingSaying(none), "", "0명일 때 「0명 중 0–0」은 말이 아니다");
});

test("자리가 총수를 넘어도 마지막 쪽으로 본다 — 3쪽에서 조각을 좁혔을 때", () => {
  const { rosterPaging } = box();

  /* 3쪽(자리 80)에서 「수신 거부 5명」을 누르면 총수가 확 준다. */
  const over = rosterPaging(5, 80, 40);
  assert.equal(over.pages, 1);
  assert.equal(over.page, 1, "있지도 않은 3쪽을 가리키면 안 된다");
});

test("**화면이 자리를 실제로 보낸다** — 안 보내면 언제나 첫 25명만 온다", () => {
  const code = codeOnly(read("js/manage.js"));

  assert.match(code, /var ROSTER_PAGE = 25;/, "한 쪽에 25명이다");
  assert.match(
    code,
    /* **인자 수를 못 박지 않는다.** 여기에 차례(`sort`)가 하나 더 붙었는데
       (KEY-327) 이 줄이 먼저 빨개졌다 — 「자리를 안 보낸다」가 아니라
       「인자가 하나 늘었다」인데, 고칠 곳을 잘못 가리킨다. 재려던 것은
       **`rosterOffset` 이 실제로 실리는가** 하나다. */
    /patientsApi\.roster\([^)]*rosterOffset[^)]*\)/,
    "자리를 안 보내면 다음 쪽이 첫 쪽과 같다",
  );

  /* **`cursor` 를 받지 않는다.** 서버가 `cursor` 와 `offset` 을 함께 받으면
     400 이다 — 부를 수 있는 모양을 아예 하나로 둔다. */
  const api = codeOnly(read("js/patients-api.js"));
  assert.match(api, /roster: function \([^)]*offset[^)]*\)/);
  assert.match(api, /offset: offset,/, "질의에 자리가 안 실린다");
  const at = api.indexOf("roster: function");
  assert.doesNotMatch(api.slice(at, at + 320), /cursor/, "쪽 넘김 자리가 커서까지 보낼 수 있다 — 서버가 400 을 낸다");
});

test("**조각·검색어·갈래가 바뀌면 첫 쪽으로 돌아간다**", () => {
  const code = codeOnly(read("js/manage.js"));

  /* 3쪽을 보다가 「수신 거부」를 누르면, 자리를 안 되돌릴 때 빈 표가 뜬다. */
  for (const spot of [/view = name;\s*\n\s*rosterOffset = 0;/, /chosen = key;\s*\n\s*rosterOffset = 0;/, /keyword = typed\.trim\(\);\s*\n\s*rosterOffset = 0;/]) {
    assert.match(code, spot, "자리를 안 되돌리면 빈 표가 뜬다");
  }
});

test("쪽 넘김 줄이 화면에 있고, 한 쪽뿐이면 감춘다", () => {
  const markup = markupOnly(read("manage.html"));

  assert.match(markup, /id="roster-page"[^>]*hidden/, "처음에는 감춰 두고 그릴 때 켠다");
  assert.match(markup, /data-page="prev"/);
  assert.match(markup, /data-page="next"/);

  const code = codeOnly(read("js/manage.js"));
  assert.match(code, /pager\.hidden = !paging \|\| paging\.pages <= 1;/, "누를 데 없는 단추를 남기지 않는다");
  assert.match(code, /disabled = !paging\.hasPrev/, "끝에 닿으면 눌리지 않아야 한다");
  assert.match(code, /disabled = !paging\.hasNext/);
});

test("목업도 서버와 같은 것을 돌려준다 — 쪽 넘김이 목업에서만 돌면 안 된다", () => {
  const api = codeOnly(read("js/patients-api.js"));

  assert.match(api, /items: shown\.slice\(offset, offset \+ limit\)/, "목업이 자리를 무시하면 다음 쪽이 첫 쪽과 같다");
  assert.match(api, /roster: \{ offset: offset, limit: limit, total: shown\.length/);
});

/* ── 서버가 「더 없다」고 하면 따른다 (이희진 님 #270 리뷰 ②) ────────────
 *
 * 진료에서 나오는 조각(진행 중 · 챙겨주세요)의 셈은 의원의 최근 진료를 훑어
 * 내므로 검색어를 몰랐다. 표는 걸러지는데 배지는 안 걸러져 **배지가 표보다
 * 커졌고**, 그 값으로 쪽을 세면 「다음」에 빈 표가 떴다. 셈은 서버에서 고쳤고,
 * 여기서는 그래도 어긋났을 때 앞으로 안 가게 막는다.
 */
test("**총수가 부풀어도 서버가 아니라면 다음으로 안 간다**", () => {
  const { rosterPaging } = box();

  /* 총수는 101 이라는데 서버는 「이게 끝」이라고 한다 */
  const lying = rosterPaging(101, 0, 40, false);
  assert.equal(lying.hasNext, false, "총수만 믿으면 빈 표를 준다");

  /* 서버가 더 있다고 하면 총수와 함께 본다 */
  assert.equal(rosterPaging(101, 0, 40, true).hasNext, true);
  /* 서버가 더 있다 해도 총수가 다 찼으면 안 간다 — 둘 다 그럴 때만 */
  assert.equal(rosterPaging(40, 0, 40, true).hasNext, false);
});

test("서버가 말을 안 해도 예전처럼 총수로 센다", () => {
  const { rosterPaging } = box();

  /* 넷째 인자를 안 주는 예전 호출도 그대로 돌아야 한다 */
  assert.equal(rosterPaging(101, 0, 40).hasNext, true);
  assert.equal(rosterPaging(101, 80, 40).hasNext, false);
});

test("화면이 서버의 `has_next` 를 실제로 넘긴다", () => {
  const code = codeOnly(read("js/manage.js"));

  const calls = code.match(/rosterPaging\(page\.roster\.total, page\.roster\.offset, page\.roster\.limit, page\.roster\.has_next\)/g) || [];
  assert.strictEqual(calls.length, 2, "그리는 자리와 누르는 자리 둘 다 넘겨야 한다");
});
