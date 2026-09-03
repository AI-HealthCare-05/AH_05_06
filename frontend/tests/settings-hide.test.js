/* **지우지 않는다. 감춘다.** — KEY-255
 *
 * 의료 데이터라 삭제가 금지된다(2026-09-02 팀 결정). 여기서는 이유가 하나 더
 * 있다: 지난 진료기록이 이 세트를 **이름 문자열로** 가리키므로, 행이 사라지면
 * 그 진료들의 안내문 문구가 조용히 떨어진다.
 *
 * **감춤은 「없다」가 아니라 「새로 못 고른다」다.**
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { read, codeOnly } = require("./source.js");

test("**지우는 길이 어디에도 없다**", () => {
  /* 단추 하나만 있어도 눌린다. 「지운다」는 말이 화면에도 API 에도 없어야 한다. */
  /* DELETE 자체는 다른 데도 쓴다 — 문구 되돌리기가 덮어쓴 값을 지운다.
     막아야 하는 것은 **처방 세트를 지우는 길**이다. */
  for (const file of ["js/settings.js", "js/catalog-api.js"]) {
    const code = codeOnly(read(file));
    assert.ok(
      !/prescription-sets[^;]{0,200}?method:\s*"DELETE"/s.test(code),
      `${file} 이 처방 세트를 DELETE 한다 — 지난 진료기록이 이 이름을 가리킨다`,
    );
    assert.ok(
      !/deleteSet|removeSet|id="set-delete"/.test(code),
      `${file} 에 처방을 지우는 길이 있다`,
    );
  }
});

test("**감춘 처방도 목록에 남아야 되살릴 수 있다**", () => {
  /* 레일에서 거르면 되살릴 화면 자체가 없어진다. 표시만 하고 남긴다. */
  const code = codeOnly(read("js/settings.js"));

  assert.ok(
    !/sets\s*\.filter\([^)]*hidden/.test(code),
    "설정 레일이 감춘 것을 걸러 낸다 — 되살릴 길이 없어진다",
  );
  assert.match(code, /row\.hidden \? " \(숨김\)" : ""/, "레일이 감춤을 표시하지 않는다");
  assert.match(code, /id="set-hide"/, "숨기기 단추가 없다");
  assert.match(code, /picked\.hidden \? "되살리기" : "숨기기"/, "되살리기로 안 바뀐다");
});

test("**거르는 곳은 새로 고르는 칸 하나뿐이다**", () => {
  /* 서버 조회를 거르면 지난 환자들의 안내문 문구가 조용히 범용으로 바뀐다.
     화면에서 거를 자리는 판독 확인의 처방 고르는 칸뿐이다. */
  const code = codeOnly(read("js/ocr-review.js"));

  assert.match(code, /!set\.hidden \|\|/, "고르는 칸이 감춘 처방을 거르지 않는다");
  assert.match(
    code,
    /pickedSet && pickedSet\.prescription_set_id === set\.prescription_set_id/,
    "이미 고른 것이 감춰지면 고른 값이 풀린다",
  );
});

test("**새 처방은 이름과 진단을 한 판에서 받는다**", () => {
  /* 이름은 만들고 나면 **못 바꾼다** — 지난 진료기록이 그 이름으로 이 처방을
     가리키기 때문이다. 그래서 못 바꾼다는 것을 만들기 **전에** 말해야 한다.
     만들고 나서 알면 남는 수는 숨기고 다시 만드는 것뿐인데, 지우는 것은
     금지라 잘못 지은 이름이 표에 영구히 남는다. */
  const settings = codeOnly(read("js/settings.js"));
  const api = codeOnly(read("js/catalog-api.js"));

  /* **더하는 자리는 묶음 머리다.** 목록 아래 한 줄로 두었더니 여덟 줄과
     접힌 묶음을 지나야 보였고, 거기서는 목록의 마지막 항목처럼 읽혔다. */
  assert.match(settings, /sectionHtml\("처방",[^)]*"set-new"\)/, "처방 머리에 더하기가 없다");
  assert.match(settings, /class="rail__plus"/, "더하기 단추 꼴이 없다");
  /* **본문이 상세와 같다.** 만들기 전용 판을 따로 두면 두 곳이 갈라지고,
     새로 더한 절이 한쪽에만 생긴다. `picked` 에 초안을 넣어 같은 본문을 쓴다. */
  assert.match(settings, /function draftSet\(\)/, "초안 틀이 없다");
  assert.match(settings, /picked = draft \|\| draftSet\(\)/, "초안을 picked 에 안 넣는다");
  assert.ok(
    !/function makeHtml/.test(settings),
    "만들기 전용 판이 남아 있다 — 절을 더하면 한쪽에만 생긴다",
  );
  assert.match(settings, /making \? "만들기" : "저장"/, "단추 글이 안 갈린다");
  assert.match(settings, /id="make-cancel"/, "취소가 없다 — 잘못 열면 빠져나갈 길이 없다");
  assert.match(settings, /나중에 바꿀 수 없습니다/, "못 바꾼다는 것을 안 말한다");

  /* 브라우저 기본 대화상자를 쓰지 않는다 — 이 화면 어디에도 없는 꼴이고,
     한 줄만 받으니 진단을 같이 고를 자리가 없다. */
  assert.ok(
    !/window\.prompt|window\.confirm|window\.alert/.test(settings),
    "브라우저 기본 대화상자를 쓴다",
  );

  assert.match(settings, /PRESCRIPTION_SET_EXISTS/, "겹친 이름을 사람 말로 안 알린다");
  assert.match(settings, /숨긴 것도 포함/, "감춘 이름도 못 쓴다는 것을 안 말한다");

  /* 목도 서버와 같이 다듬어야 한다 — 앞뒤 공백은 unique 가 안 막는다 */
  assert.match(api, /split\(\/\\s\+\/\)/, "목이 이름을 안 다듬는다 — 눈에 같은 쌍둥이가 생긴다");
});

test("**만들기 판은 다른 곳으로 옮기면 닫힌다**", () => {
  /* 안 닫으면 오른쪽은 만들기 판인데 왼쪽은 다른 처방이 골라진 채로 어긋난다. */
  const code = codeOnly(read("js/settings.js"));

  assert.match(
    code,
    /data-set\]"\);[\s\S]{0,200}?closeMaking\(\);/,
    "다른 처방을 골라도 만들기 판이 남는다",
  );
  assert.match(
    code,
    /chosenGroup = target\.closest[\s\S]{0,200}?closeMaking\(\);/,
    "기타 묶음으로 옮겨도 만들기 판이 남는다",
  );
});

test("**초안일 때는 이름도 거둔다** — 안 그러면 다시 그릴 때 지워진다", () => {
  /* `planNow()` 는 이름을 안 담는다 — 저장 계약이 안 받기 때문이다. 그런데
     `textHtml` 은 값을 **모델에서만** 그리므로, 거두지 않으면 다시 그릴 때마다
     친 이름이 빈칸이 된다. 「+ 약 추가」 한 번에 이름이 사라진다. */
  const code = codeOnly(read("js/settings.js"));

  assert.match(
    code,
    /if \(making\) kept\.name = el\("f-name"\)\.value;/,
    "초안에서 이름을 안 거둔다 — 약을 추가하면 이름이 날아간다",
  );
});

test("**만들다 만 판을 버리는 길은 「취소」뿐이다**", () => {
  /* 잘못 눌러 나갔다가 돌아왔을 때 다시 치게 하면 안 된다.
     두 번 누르는 것도 막아야 한다 — 단추가 만드는 중에도 레일에 서 있다. */
  const code = codeOnly(read("js/settings.js"));

  assert.match(code, /function closeMaking\(\)/, "닫으면서 들고 가는 자리가 없다");
  assert.match(code, /draft = picked;/, "떠날 때 친 것을 안 들고 간다");
  assert.match(code, /if \(making\) return;/, "「+ 새 처방」을 두 번 누르면 친 것이 전멸한다");
  assert.match(code, /make-cancel[\s\S]{0,200}?draft = null;/, "취소가 초안을 안 버린다");
});

test("**보내는 중에는 다시 못 누른다**", () => {
  /* DOM 의 `disabled` 는 `render()` 가 판을 갈아치우면서 지워진다.
     상태로 들고 있어야 다시 그려도 살아남는다. */
  const code = codeOnly(read("js/settings.js"));

  assert.match(code, /var busy = false;/, "보내는 중 상태가 없다");
  assert.match(code, /if \(!picked \|\| !canEdit \|\| busy\) return;/, "두 번 눌리면 두 번 보낸다");
  assert.match(code, /canEdit && !busy \? "" : " disabled"/, "보내는 중에 단추가 열려 있다");
});

test("**만든 뒤 문구 판을 다시 받는다**", () => {
  /* 문구 목록은 로그인 때 한 번 받는다. 새 번호가 그 목록에 없으므로
     다시 안 받으면 **새로 만든 처방은 안내문 절이 통째로 안 보인다.** */
  const code = codeOnly(read("js/settings.js"));

  assert.match(code, /Promise\.all\(\[loadSets\(\), loadCopy\(\)\]\)/, "저장 뒤 문구를 다시 안 받는다");
});

test("**새로 지은 클래스에는 꼴이 있어야 한다**", () => {
  /* 클래스 이름만 짓고 CSS 를 안 만들면 단추가 **그려지는데 안 보인다.**
     실제로 그랬다 — `rail__add` 를 지어 놓고 스타일을 빠뜨려, 꼴 없는 맨
     버튼이 레일 배경에 묻혔다. DOM 에 있는 것만 보고 넘어가면 못 잡는다. */
  const js = codeOnly(read("js/settings.js"));
  const css = read("css/settings.css") + read("css/shell.css");

  const used = new Set();
  for (const m of js.matchAll(/class="(rail__[a-z0-9_-]+)/g)) used.add(m[1]);

  const naked = [...used].filter((c) => !css.includes("." + c));
  assert.deepStrictEqual(naked, [], `꼴 없는 클래스: ${naked.join(", ")}`);
});

test("**CSS 변수는 정의된 것만 쓴다**", () => {
  /* `--ink-soft` 를 지어 썼다가 잡았다. 없는 변수는 조용히 무시되어
     글자색이 상속값으로 남는다 — 안 보이거나 잘못 보인다. */
  const css = ["css/settings.css", "css/shell.css", "css/tokens.css"]
    .map((f) => read(f))
    .join("\n");

  const defined = new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
  const used = new Set([...css.matchAll(/var\((--[a-z0-9-]+)/g)].map((m) => m[1]));

  const missing = [...used].filter((v) => !defined.has(v));
  assert.deepStrictEqual(missing, [], `정의 없는 변수: ${missing.join(", ")}`);
});
