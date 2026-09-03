/* **약 목록** — 설정의 「처방」 묶음.
 *
 * 대표 처방에 약을 적을 때 손으로 치지 않고 고르라고 둔다. 약 넷이 여덟
 * 세트에 열세 번 되풀이되고, 손으로 치면 표기가 갈린다 — 이미 갈려 있다
 * (검사·주석은 「비잔정 2mg」, 판독·CSV 는 「비잔정(디에노게스트) 2mg」).
 *
 * **이 목록을 읽는 것은 아직 설정 화면뿐이다.** 안내문·환자 화면·챗봇은 안
 * 읽는다. 그것들이 읽으려면 판독 확정이 진료에 처방을 붙이는 다리(KEY-66)가
 * 먼저 서야 한다. 그러니 지금 성과는 **「설정 입력이 편해졌다」**까지다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { read, codeOnly } = require("./source.js");

test("**약 목록은 대표 처방 바로 아래다** — 「기타」가 아니라", () => {
  /* 대표 처방에 약을 적을 때 여기서 고르므로 둘이 붙어 있어야 눈이 오가지
     않는다. 검사 기준선·문자 문구는 처방과 상관없는 참조표라 「기타」에 남는다. */
  const rail = codeOnly(read("js/settings-rail.js"));
  const code = codeOnly(read("js/settings.js"));

  assert.match(rail, /key: "drugs",\s*section: "drugs"/, "약 목록이 제 갈래가 아니다");
  assert.match(rail, /RAIL_GROUP_READY = \{[^}]*drugs: true/, "눌리지 않는다");

  /* 레일에서 대표 처방 → 처방 → 기타 차례로 선다. */
  const at = {
    sets: code.indexOf('sectionHtml("대표 처방"'),
    drugs: code.indexOf('sectionHtml("처방"'),
    rest: code.indexOf('sectionHtml("기타")'),
  };
  assert.ok(at.sets !== -1 && at.drugs !== -1 && at.rest !== -1, "묶음 셋이 다 안 선다");
  assert.ok(at.sets < at.drugs && at.drugs < at.rest, "차례가 다르다 — 처방이 대표 처방 아래여야 한다");

  /* `RAIL_SECTIONS` 는 **죽은 상수다.** 거기 넣으면 화면이 안 바뀐다. */
  assert.ok(
    !/RAIL_SECTIONS/.test(code),
    "settings.js 가 죽은 상수를 쓴다 — railHtml 이 갈래를 직접 잇는다",
  );
});

test("**지우는 길이 없다 — 감춘다**", () => {
  /* 이미 그 이름으로 저장된 대표 처방이 있다. 지우면 그것이 가리키던 것이
     사라지는데 화면엔 아무 말도 안 뜬다. */
  const code = codeOnly(read("js/settings.js"));

  assert.match(code, /data-drug-hide=/, "감추는 단추가 없다");
  assert.ok(!/data-drug-drop|deleteDrug/.test(code), "지우는 길이 있다");
  assert.match(code, /지우지 않고 감춥니다/, "왜 안 지우는지 화면이 말하지 않는다");
});

test("**제작 중인지는 서버가 알려 준다** — 화면이 정하지 않는다", () => {
  /* 화면이 상수로 들고 있으면 서버와 갈린다 — 열어 둔 화면이 잠긴 서버에
     이름을 보내면 409 가 나고 사용자는 까닭을 모른다.
     받기 전에는 **잠근 쪽**이 기본값이다. */
  const code = codeOnly(read("js/settings.js"));

  assert.match(code, /var DRAFT = false;/, "받기 전 기본값이 열려 있다");
  assert.match(code, /DRAFT = !!\(page && page\.draft\)/, "서버가 준 값을 안 쓴다");
  assert.match(code, /textCell\("dg-name", i, "약 이름", row\.name, !DRAFT\)/, "이름 칸이 안 잠긴다");
});

test("**저장 결과를 지우지 않는다**", () => {
  /* `goGroup()` 이 `saying` 을 비운다. 저장 뒤에 판 여는 함수를 부르면
     「이미 등록돼 있습니다」가 그 자리에서 사라져, **막혔는데 화면이 아무
     말도 안 하게 된다.** 받아 오기만 부르고 말을 되살린다. */
  const code = codeOnly(read("js/settings.js"));

  assert.match(code, /function loadDrugs\(\)/, "받아 오기가 판 열기와 안 갈렸다");
  assert.match(code, /var told = saying;[\s\S]{0,160}?saying = told;/, "저장 결과가 지워진다");
  assert.ok(
    !/return openDrugs\(\)\.then/.test(code),
    "저장 뒤에 판 여는 함수를 부른다 — saying 이 지워진다",
  );
});

test("**대표 처방의 약 칸이 이 목록에서 고른다** — 다만 막지는 않는다", () => {
  /* `<datalist>` 는 목록 밖 값을 막지 않는다. `<select>` 로 막으면 이미
     저장된 「비잔정 2mg」이 목록에 없어서, 다른 칸만 고치고 저장해도 약
     이름이 빈칸으로 떨어진다.
     그리고 `planNow()` 가 읽는 클래스(`.drug__name`)는 **그대로 둔다** —
     숨은 칸을 더하면 그것을 안 읽어 값이 소리 없이 떨어진다. */
  const code = codeOnly(read("js/settings.js"));

  assert.match(code, /<datalist id="drug-names">/, "고를 목록이 없다");
  assert.match(code, /list="drug-names"/, "약 이름 칸이 그 목록을 안 본다");
  assert.match(code, /class="fld__input drug__name"/, "planNow 가 읽는 클래스가 바뀌었다");
  assert.match(code, /return !row\.hidden && row\.name;/, "감춘 약·빈 줄이 목록에 섞인다");
});

test("**목이 서버와 같은 봉투를 준다**", () => {
  /* 갈라지면 목에서만 되는 화면이 된다 — CI 가 못 잡고 눌러 봐야 보인다. */
  const api = codeOnly(read("js/catalog-api.js"));

  assert.match(api, /draft: true,\s*items:/, "목이 봉투를 안 준다");
  assert.match(api, /DRUG_EXISTS/, "목이 겹친 이름을 안 막는다");
  assert.match(api, /split\(\/\\s\+\/\)/, "목이 이름을 안 다듬는다 — 눈에 같은 쌍둥이가 생긴다");
});
