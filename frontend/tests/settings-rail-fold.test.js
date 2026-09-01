/* 설정 왼쪽 레일 — 안내문 목록과 접기 (D2-3) — KEY-234.
 *
 * 원문 주석: 「9개가 늘 다 펼쳐져 있으면 왼쪽이 길어져 「그 밖에」가 화면 밖으로
 * 밀린다」. 처방이 그랬듯 안내문도 여덟 장이라 같은 규칙을 받는다.
 *
 * **여기서 제일 크게 재는 것은 「고른 것이 보이는가」다.** 접었다 펴는 화면은
 * 고른 줄이 접힌 묶음 안에 숨으면 아무 일도 안 일어난 것처럼 보인다. 묶는
 * 규칙과 되찾는 규칙이 갈라지면 바로 그 일이 난다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function rules() {
  return load("api", "settings-rail");
}

function a_set(over) {
  return Object.assign(
    { prescription_set_id: 1, disease: "PCOS", name: "메트포르민" },
    over || {},
  );
}

test("**고른 처방이 든 묶음을 되찾는다** — 열어 줄 곳을 알아야 한다", () => {
  const { railGroupKey } = rules();
  const sets = [
    a_set({ prescription_set_id: 1, disease: "PCOS" }),
    a_set({ prescription_set_id: 2, disease: "ENDOMETRIOSIS" }),
  ];
  assert.equal(railGroupKey(sets, 1), "PCOS");
  assert.equal(railGroupKey(sets, 2), "ENDOMETRIOSIS");
});

test("**모르는 질환은 「그 밖의 질환」 묶음으로 되찾는다** — 질환 코드로 열면 안 열린다", () => {
  const { railGroupKey, setsByDisease } = rules();
  const sets = [a_set({ prescription_set_id: 7, disease: "ADENOMYOSIS" })];

  /* 나누는 쪽이 실제로 쓰는 열쇠 */
  assert.equal(setsByDisease(sets)[0].key, "other");
  /* 되찾는 쪽도 같은 열쇠여야 한다 — 「ADENOMYOSIS」 를 돌려주면 그 묶음은
     없어서 조용히 접힌 채 남는다 */
  assert.equal(railGroupKey(sets, 7), "other");
});

test("**없는 처방은 없다고 한다** — 아무 묶음이나 열지 않는다", () => {
  const { railGroupKey } = rules();
  assert.equal(railGroupKey([a_set({ prescription_set_id: 1 })], 99), null);
  assert.equal(railGroupKey([], 1), null);
  assert.equal(railGroupKey(null, 1), null);
});

test("**안내문 표시는 확인 여부를 그대로 옮긴다**", () => {
  const { copyRailMark } = rules();
  const copy = {
    items: [
      { prescription_set_id: 1, reviewed: true },
      { prescription_set_id: 2, reviewed: false },
    ],
  };
  assert.deepEqual(copyRailMark(copy, 1), { say: "✓", done: true });
  assert.deepEqual(copyRailMark(copy, 2), { say: "확인 전", done: false });
});

test("**아직 안 받아온 목록은 「확인 전」이라 하지 않는다** — 모르는 것과 안 본 것은 다르다", () => {
  const { copyRailMark } = rules();
  assert.deepEqual(copyRailMark(null, 1), { say: "", done: false });
  assert.deepEqual(copyRailMark({}, 1), { say: "", done: false });
  /* 목록에 없는 처방도 마찬가지 — 안내문이 아직 안 만들어진 것뿐이다 */
  assert.deepEqual(copyRailMark({ items: [] }, 1), { say: "", done: false });
});

test("**묶음 머리는 접힘을 화면 낭독기에도 알린다**", () => {
  const src = codeOnly(read("js/settings.js"));
  assert.match(src, /aria-expanded="/, "aria-expanded 가 없으면 낭독기는 늘 펼쳐진 줄로 읽는다");
});

test("**펼친 묶음은 하나다** — 넷 다 펼치면 「기타」가 화면 밖으로 밀린다", () => {
  /* 원문 D2-3 주석: 「9개가 늘 다 펼쳐져 있으면 왼쪽이 길어져 「그 밖에」가
     화면 밖으로 밀린다」. 실측으로도 넷 다 937px vs 보이는 높이 689px 이다. */
  const src = codeOnly(read("js/settings.js"));
  assert.match(src, /var opened = null;/, "펼친 것을 여럿 담고 있다");
  assert.match(src, /opened = opened === key \? null : key/, "아코디언이 아니다");
});

test("**갈래가 열쇠에 들어 있다** — 두 갈래에 같은 질환이 있다", () => {
  const src = codeOnly(read("js/settings.js"));
  assert.match(src, /railFoldKey\("guide"/, "안내문 쪽이 갈래를 안 담는다");
  assert.match(src, /railFoldKey\("sets"/, "처방 쪽이 갈래를 안 담는다");
});

test("**여닫을 때 레일을 다시 안 그린다** — 화살표 회전과 키보드 초점이 사라진다", () => {
  const src = codeOnly(read("js/settings.js"));
  const at = src.indexOf('target.closest("[data-fold]")');
  const body = src.slice(at, at + 260);
  assert.match(body, /return showOpen\(\)/, "통째로 다시 그린다");
  assert.doesNotMatch(body, /return render\(\)/);
});

test("**접힌 자식을 지우지 않고 감춘다** — 가리킬 것이 없으면 `aria-controls` 가 헛돈다", () => {
  const src = codeOnly(read("js/settings.js"));
  const at = src.indexOf("function railGroupHtml");
  const body = src.slice(at, src.indexOf("function copyRailRow"));
  assert.match(body, /aria-controls=/, "낭독기에 무엇이 열리는지 안 알린다");
  assert.match(body, /open \? "" : " hidden"/, "접힐 때 노드를 지운다");
});

test("**처방을 고르면 안내문 고름을 놓는다** — 두 곳이 동시에 굵으면 안 된다", () => {
  const src = codeOnly(read("js/settings.js"));
  const pick = src.slice(src.indexOf('target.closest("[data-set]")'));
  const body = pick.slice(0, pick.indexOf("return loadSet"));
  assert.match(body, /copyPick = null/, "처방으로 옮기면서 안내문 고름을 안 놓는다");
});

test("**갈래를 옮겨도 안내문 목록은 안 버린다** — 레일의 진도와 ✓ 가 거기서 나온다", () => {
  const src = codeOnly(read("js/settings.js"));
  assert.doesNotMatch(
    src,
    /^\s*copy = null;/m,
    "화면을 옮기며 `copy` 를 비우면 왼쪽의 「1/8」과 ✓ 가 통째로 사라진다",
  );
  /* 시작할 때 한 번 받아 둔다 — 안내문 갈래를 열지 않아도 진도가 서야 한다 */
  assert.match(src, /loadSets\(\),\s*loadCopy\(\)/);
});

test("**받아 온 안내문은 어느 갈래를 보고 있든 붙인다**", () => {
  const src = codeOnly(read("js/settings.js"));
  const load = src.slice(src.indexOf("function loadCopy()"));
  const then = load.slice(0, load.indexOf(".catch("));
  assert.doesNotMatch(
    then,
    /group !== "guide"/,
    "붙이는 자리를 갈래로 막으면 처방을 보는 동안 레일 표시가 사라진다",
  );
  /* 실패를 오른쪽에 적는 것은 안내문을 보고 있을 때만 — 남의 자리다 */
  assert.match(load.slice(load.indexOf(".catch(")), /group !== "guide"/);
});

/* ── 보이는 이름 ──────────────────────────────────────────────────── */

test("**묶음 안에서는 되풀이되는 앞머리를 뗀다** — 「자궁내막증」 밑에 「자궁내막증 · 」이 셋", () => {
  const { railSetName } = rules();
  const block = { key: "ENDOMETRIOSIS", title: "자궁내막증" };
  assert.equal(railSetName(block, "자궁내막증 · 비잔 (처음)"), "비잔 (처음)");
});

test("**앞머리가 코드로 붙은 것도 뗀다** — 실제 DB 가 그렇다", () => {
  const { railSetName } = rules();
  /* 다낭성난소증후군 묶음의 이름은 「PCOS · 」로 시작한다 — 묶음 이름이
     아니라 질환 **코드**다. 이름으로만 자르면 다섯 줄이 그대로 남는다. */
  const block = { key: "PCOS", title: "다낭성난소증후군" };
  assert.equal(railSetName(block, "PCOS · 야즈 + 메트포르민"), "야즈 + 메트포르민");
  assert.equal(railSetName(block, "다낭성난소증후군 · 야즈"), "야즈");
});

test("**이름의 일부인 가운뎃점은 안 자른다** — 「`·` 앞을 자른다」로 하면 병명이 없어진다", () => {
  const { railSetName } = rules();
  const block = { key: "ENDOMETRIOSIS", title: "자궁내막증" };
  assert.equal(railSetName(block, "선근증 · 생리과다"), "선근증 · 생리과다");
});

test("**「그 밖의 질환」에서는 아무것도 안 뗀다** — 거기선 질환 이름이 알아야 할 정보다", () => {
  const { railSetName } = rules();
  const block = { key: "other", title: "그 밖의 질환" };
  assert.equal(railSetName(block, "ADENOMYOSIS · 생리과다"), "ADENOMYOSIS · 생리과다");
});

test("**벗기면 빈 줄이 되는 이름은 그대로 둔다** — 이름 없는 줄은 못 고른다", () => {
  const { railSetName } = rules();
  const block = { key: "PCOS", title: "다낭성난소증후군" };
  assert.equal(railSetName(block, "PCOS · "), "PCOS · ");
  /* 사이 공백이 없으면 앞머리가 아니다 */
  assert.equal(railSetName(block, "PCOS·초진"), "PCOS·초진");
  assert.equal(railSetName(null, "PCOS · 초진"), "PCOS · 초진");
});

/* ── 묶음 열쇠 ────────────────────────────────────────────────────── */

test("**갈래를 열쇠에 담는다** — 두 갈래에 같은 질환이 있다", () => {
  const { railFoldKey } = rules();
  assert.notEqual(railFoldKey("guide", "PCOS"), railFoldKey("sets", "PCOS"));
  assert.equal(railFoldKey("guide", "PCOS"), "guide|PCOS");
});

/* ── 묶음의 진도 ──────────────────────────────────────────────────── */

test("**안내문 묶음은 진도를 단다** — 처방은 개수, 안내문은 「1/3」", () => {
  const { copyBlockMark } = rules();
  const sets = [{ prescription_set_id: 1 }, { prescription_set_id: 2 }, { prescription_set_id: 3 }];
  const copy = {
    items: [
      { prescription_set_id: 1, reviewed: true },
      { prescription_set_id: 2, reviewed: false },
      { prescription_set_id: 3, reviewed: false },
    ],
  };
  assert.deepEqual(copyBlockMark(copy, sets), { say: "1/3", done: false });
});

test("**다 봤으면 그렇다고 한다**", () => {
  const { copyBlockMark } = rules();
  const sets = [{ prescription_set_id: 1 }, { prescription_set_id: 2 }];
  const copy = {
    items: [
      { prescription_set_id: 1, reviewed: true },
      { prescription_set_id: 2, reviewed: true },
    ],
  };
  assert.deepEqual(copyBlockMark(copy, sets), { say: "2/2", done: true });
});

test("**아직 못 받아 온 것을 「0/3」이라 하지 않는다** — 「다 안 봤다」와 「모른다」는 다르다", () => {
  const { copyBlockMark } = rules();
  const sets = [{ prescription_set_id: 1 }, { prescription_set_id: 2 }, { prescription_set_id: 3 }];
  assert.deepEqual(copyBlockMark(null, sets), { say: "3", done: false });
  assert.deepEqual(copyBlockMark({}, sets), { say: "3", done: false });
});

test("**빈 묶음은 「다 봤다」가 아니다** — 0/0 을 끝난 것으로 세면 안 된다", () => {
  const { copyBlockMark } = rules();
  assert.deepEqual(copyBlockMark({ items: [] }, []), { say: "0/0", done: false });
});
