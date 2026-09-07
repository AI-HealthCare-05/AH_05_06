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
const { read, codeOnly, rule } = require("./source.js");

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

test("**펼친 묶음은 여럿일 수 있다** — 누른 것만 뒤집는다", () => {
  /* 한동안 하나만 열리게 두었다. 원문 D2-3 주석이 「9개가 늘 다 펼쳐져 있으면
     왼쪽이 길어져 「그 밖에」가 화면 밖으로 밀린다」고 적었고, 실측도 넷 다
     937px vs 보이는 높이 689px 이었다.

     **그 셈의 전제가 바뀌었다.** 안내문 묶음을 처방 안으로 넣으면서 묶음이
     넷에서 둘로 줄었다. 둘 다 펴도 「기타」가 안 밀린다.

     그리고 하나만 열리는 것이 걸리적거렸다 — 다낭성을 펴면 자궁내막증이 닫혀
     두 묶음을 견주려면 접었다 폈다를 되풀이해야 했다. */
  const src = codeOnly(read("js/settings.js"));

  assert.match(src, /var opened = \{\};/, "펼친 것을 하나만 담는다");
  assert.match(src, /if \(opened\[key\]\) delete opened\[key\];/, "누른 것을 못 닫는다");
  assert.ok(
    !/opened = opened === key/.test(src),
    "아직 아코디언이다 — 다른 묶음이 같이 닫힌다",
  );

  /* 처방을 고르면 그 묶음이 펴지되 **다른 묶음은 그대로**여야 한다. */
  assert.match(
    src,
    /opened\[railFoldKey\("sets", chose\)\] = true;/,
    "처방을 고르면 다른 묶음이 닫힌다",
  );
});

test("**레일은 처방 하나로 선다** — 안내문 묶음을 따로 두지 않는다", () => {
  /* 같은 처방을 두 번 오가야 했다 — 「비잔 (계속)」의 약을 보다가 그 문구를
     고치려면 위쪽 안내문 묶음에서 「비잔 (계속)」을 다시 찾아야 했다.

     **둘의 열쇠가 같은 처방 세트다.** 안내문은 처방과 처방일수로 만들어지므로
     문구는 그 처방의 한 속성이고, 나무를 둘로 세우면 같은 것을 두 번 세운
     셈이 된다. */
  const src = codeOnly(read("js/settings.js"));

  assert.match(src, /railFoldKey\("sets"/, "처방 쪽이 갈래를 안 담는다");
  assert.doesNotMatch(src, /railFoldKey\("guide"/, "안내문 묶음이 아직 남아 있다");
  assert.doesNotMatch(src, /data-copy-set/, "안내문 줄을 아직 그린다");
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

test("**고르는 자리가 하나다** — 두 곳이 동시에 굵을 수 없다", () => {
  /* `copyPick` 과 `pickedId` 두 상태가 있었다. 갈래가 하나가 되면서 고름도
     하나다 — 상태를 남겨 두면 언젠가 둘이 어긋난다. */
  const src = codeOnly(read("js/settings.js"));

  assert.doesNotMatch(src, /copyPick/, "안내문 전용 고름 상태가 남아 있다");
  assert.match(src, /pickedId = id/, "처방 고름이 없다");
});

test("**처방을 고르면 그 문구도 함께 받는다** — 자리가 비어 있으면 안 된다", () => {
  /* 문구는 처방과 **다른 API** 로 온다(`guide-copy`). 처방만 받아 오면
     상세 맨 아래 문구 자리가 계속 「불러오는 중」이다. */
  const src = codeOnly(read("js/settings.js"));
  /* `loadSets`(목록)가 아니라 `loadSet(`(한 장)이다 — 앞엣것이 먼저 잡혀
     엉뚱한 자리를 보고 있었다. */
  const at = src.indexOf("function loadSet(id)");
  assert.notEqual(at, -1, "처방 한 장을 여는 자리가 없다");
  const body = src.slice(at, src.indexOf("catalogApi", at));

  assert.match(body, /if \(!copy\) loadCopy\(\)/, "문구를 안 받아 온다");
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
     아니라 질환 **코드**다. 이름으로만 자르면 그 묶음이 통째로 남는다. */
  const block = { key: "PCOS", title: "다낭성난소증후군" };
  assert.equal(railSetName(block, "PCOS · 야즈 (계속)"), "야즈 (계속)");
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
  assert.equal(railSetName(null, "PCOS · 야즈 (처음)"), "PCOS · 야즈 (처음)");
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

test("**안 본 장이 다 본 장보다 눈에 띈다** — 원문이 노린 것", () => {
  /* 원문 D2-1 레일은 「확인 전」 줄에 굵기와 왼쪽 막대를 주고 「✓」 줄에는
     아무것도 안 준다 — 이 화면의 일이 「여덟 장을 다 보는 것」이라 남은 것이
     소리쳐야 한다. 구현은 그것을 뒤집어 두고 있었다: 끝난 것이 초록으로 굵고
     할 일이 회색이었다. */
  const css = read("css/settings.css");

  const todo = rule(css, ".rail__note--todo");
  assert.ok(todo, "안 본 장 표시가 없다");
  assert.match(todo, /font-weight:\s*700/, "안 본 장이 굵지 않다");

  /* `rule()` 은 못 찾으면 던진다 — 없으면 그 자리에서 빨개진다 */
  const done = rule(css, ".rail__note--done");
  assert.doesNotMatch(done, /font-weight:\s*700/, "끝난 것이 남은 것만큼 굵다");
});

test("**화면이 안 본 장에 그 표시를 붙인다**", () => {
  const code = codeOnly(read("js/settings.js"));
  assert.match(code, /rail__note--todo/, "안 본 장 표시를 안 쓴다");
  /* 아직 목록을 못 받아 왔을 때(`say` 가 빈 문자열)는 아무 표시도 안 붙인다 —
     「모른다」를 「안 봤다」로 적으면 안 된다 */
  assert.match(code, /mark\.done \? " rail__note--done" : mark\.say \?/);
});
