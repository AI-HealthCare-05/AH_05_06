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
  { prescription_set_id: 4, name: "PCOS · 야즈 (처음)", disease: "PCOS" },
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

test("**설정은 스탭도 고친다** — 이름부터 일수까지", () => {
  /* 한동안 아무도 못 고쳤다. 여러 의원이 한 표를 나눠 쓰는 모양이라 남의
     의원 것까지 바뀌었기 때문이다(`#183` 리뷰). **의원 하나를 보는
     프로그램**이라는 것이 정해지면서(2026-09-02 회의) 그 걱정이 범위 밖으로
     갔고, 같은 회의에서 설정 수정을 스탭에게도 열었다. */
  const code = codeOnly(read("js/settings.js"));

  assert.doesNotMatch(code, /canEditSet/, "처방 전용 잠금이 남아 있다");
  assert.match(code, /canEdit = \(me\.roles \|\| \[\]\)/, "역할에서 정하지 않는다");

  const at = code.indexOf('id="set-save"');
  assert.notEqual(at, -1, "저장 단추가 없다");
  /* 보내는 중에만 잠긴다(`busy`) — 역할로는 안 잠근다. */
  assert.match(
    code.slice(at, at + 160),
    /canEdit && !busy \? "" : " disabled"/,
    "단추가 늘 잠겨 있거나, 보내는 중에도 열려 있다",
  );

  assert.match(code, /catalogApi\s*\.saveSet/, "저장 API 를 안 부른다");

  const api = read("../app/catalog/api.py");
  assert.match(api, /@catalog_router\.put\("\/prescription-sets/, "서버에 쓰기 경로가 없다");
});

test("**「의사 계정만」이라 적지 않는다** — 이제 사실이 아니다", () => {
  const code = codeOnly(read("js/settings.js"));

  assert.ok(
    code.indexOf("의사 계정만 수정할 수 있습니다") === -1,
    "스탭도 고치는데 못 고친다고 적혀 있다",
  );
  assert.ok(
    code.indexOf("모든 의원이 함께 쓰는 값이라") === -1,
    "의원 하나를 보는 프로그램인데 여러 의원 얘기가 남아 있다",
  );
});

test("**다시 그리기 전에 화면에 적힌 것을 거둔다**", () => {
  /* `render()` 는 판을 `picked` 로 되돌려 그린다. 그래서 아직 저장 안 한 값은
     거두지 않으면 **소리 없이 사라진다.** 약을 한 줄 적고 「+ 약 추가」를
     누르면 적은 것이 날아갔다 — 삭제에만 방어가 있었고 나머지에는 없었다.
     사라지는 것이 가장 나쁘다: 저장이 성공했다고 뜨는데 값만 없다. */
  const code = codeOnly(read("js/settings.js"));

  assert.match(code, /function keepScreen\(\)/, "거두는 자리가 없다");

  /* 다시 그리기 전에 거두어야 하는 네 자리 */
  const beforeRender = [
    ["#drug-add", /#drug-add"\)\) \{\s*keepScreen\(\);/],
    ["data-drop", /data-drop\]"\);[\s\S]{0,80}?keepScreen\(\);/],
    ["data-edit-copy", /editCopyAt\) \{\s*keepScreen\(\);/],
    ["data-cancel-copy", /data-cancel-copy\]"\)\)[\s\S]{0,400}?keepScreen\(\);/],
  ];
  for (const [what, re] of beforeRender) {
    assert.match(code, re, `${what} 가 화면 값을 안 거두고 다시 그린다`);
  }

  /* 거두는 것은 처방 판이 떠 있을 때뿐 — 기준선·문자 문구 화면에는 그 칸이
     없어 그냥 부르면 null 을 읽는다. */
  assert.match(code, /!picked \|\| !canEdit \|\| !el\("f-name"\)/, "거두기 전에 판이 떠 있는지 안 본다");
});

test("**화면이 부르는 이름으로 적는다** — 진단 · 대표 처방", () => {
  /* 「이름」·「질환」이라 적혀 있었다. 「이름」은 무엇의 이름인지 안 말하고,
     「질환」은 진료기록·판독 화면이 쓰는 말(「진단」)과 갈린다 — 같은 것을 두
     말로 부르면 화면마다 다른 것으로 읽힌다. */
  const code = codeOnly(read("js/settings.js"));

  /* **8가지 세트는 「대표 처방」이고, 그 안의 약이 「처방」이다.**
     진료기록에서 원외 처방된 약을 아래에 덧붙이는데, 그것들이 곧 처방이다.
     세트는 그 처방들의 대표 꼴이라 이름이 갈려야 한다. */
  assert.match(code, /"f-name",\s*"대표 처방"/, "이름 칸을 「대표 처방」이라 안 부른다");
  assert.match(code, /fld__label">처방</, "약 목록을 「처방」이라 안 부른다");
  assert.match(code, /"f-disease",\s*"진단"/, "진단 칸을 「질환」이라 부른다");

  /* **절 이름도 현황·진료기록과 같아야 한다** — 거기서 이 한 쌍을
     「진단 · 처방」이라 부른다. 화면마다 다른 말이면 같은 것을 두 가지로 배운다. */
  assert.match(code, /box__title">진단 · 대표 처방</, "절 이름이 진료기록과 다르다");

  /* **진단이 앞이다.** 진단이 처방을 고르는 기준이지 그 반대가 아니다. */
  assert.ok(
    code.indexOf('"f-disease"') < code.indexOf('"f-name"'),
    "처방이 진단보다 앞에 그려진다 — 고르는 차례가 뒤집혔다",
  );
});

test("**처방 이름은 잠근다** — 지난 진료기록이 그 이름으로 가리킨다", () => {
  /* `Prescription.prescription_set` 은 스냅샷 문자열이고 서버가 그 문자열로
     세트를 찾아 안내문 문구를 붙인다. 이름을 바꾸면 **기존 진료기록의 문구가
     통째로 떨어져 나가고** 화면엔 아무 말도 안 뜬다. */
  const code = codeOnly(read("js/settings.js"));

  /* 보내지 않는다 — 서버는 `name` 을 아예 안 받아 400 으로 튕긴다.
     담아 보내면 저장 전체가 죽는다. */
  assert.ok(
    !/name:\s*el\("f-name"\)/.test(code),
    "아직 이름을 보낸다 — 저장이 통째로 400 이 된다",
  );

  /* 칸은 남긴다. 무엇을 고치는 중인지 보여야 하고, keepScreen() 이 이 칸을
     탐침으로 쓴다 — 없애면 값 유실 버그가 되살아난다. */
  assert.match(code, /"f-name",\s*"대표 처방"/, "이름 칸이 통째로 사라졌다");
  assert.match(code, /locked \? " readonly"/, "잠금이 readonly 가 아니다");
  assert.ok(
    !/textHtml\(\s*"f-name"[\s\S]{0,300}?disabled/.test(code),
    "disabled 로 잠갔다 — 이 화면에서 그것은 「권한이 없다」는 뜻이라 갈린다",
  );

  /* 까닭을 말한다. 힌트 없이 잠그면 「고장」으로 읽힌다. */
  assert.match(code, /지난 진료기록이 이 이름으로 이 대표 처방을/, "왜 못 바꾸는지 화면이 말하지 않는다");
});

test("**목이 저장하면서 이름을 잃지 않는다**", () => {
  /* 서버가 이름을 안 받으므로 보내는 판에 `name` 이 없다. 그대로 덮으면
     목에서 이름 키가 사라져 상세 머리와 레일이 빈칸이 된다 — 목이라 CI 가
     못 잡고 사람이 눌러 봐야 보인다. */
  const code = codeOnly(read("js/catalog-api.js"));

  assert.match(code, /var keptName = store\[i\]\.name;/, "덮기 전에 이름을 안 뜬다");
  assert.match(code, /store\[i\]\.name = keptName;/, "덮은 뒤 이름을 안 되살린다");
});

test("**적용 시점 칸은 없애되 값은 잃지 않는다**", () => {
  /* 「초회 처방 · 계속 복용 · 휴약기」는 처방 이름이 이미 담고 있다
     (「비잔 (처음)」·「(계속)」). 칸을 없앴는데 저장할 때 안 보내면 서버가
     막고, 기본값을 보내면 **저장할 때마다 조용히 되돌아간다.** */
  const code = codeOnly(read("js/settings.js"));

  assert.ok(code.indexOf('"f-phase"') === -1, "적용 시점 칸이 아직 그려진다");
  assert.match(code, /phase: picked\.phase/, "있던 값을 안 싣는다 — 저장하면 사라진다");
});

test("**읽는 데 없는 칸은 화면에 두지 않는다** — 그 밖에", () => {
  /* 「EMR 표시 코드」·「재진 안내」는 저장되고 되읽힐 뿐 **읽어서 쓰는 데가
     한 곳도 없었다.** 그런데 도움말은 「이 코드가 기록된 진료를 안내 대상으로
     인식합니다」라며 아직 없는 기능을 설명했다 — 적어 넣으면 무언가 달라질
     줄 안다. 값과 컬럼은 남겼으니 되살릴 때 잃은 것이 없어야 한다. */
  const code = codeOnly(read("js/settings.js"));

  for (const gone of ['"f-emr"', '"f-revisit"', "그 밖에</h2>"]) {
    assert.ok(code.indexOf(gone) === -1, `${gone} 가 아직 화면에 있다`);
  }
  assert.match(code, /emr_code: picked\.emr_code/, "있던 값을 안 싣는다 — 저장하면 지워진다");
  assert.match(code, /revisit_note: picked\.revisit_note/, "있던 값을 안 싣는다 — 저장하면 지워진다");
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
    /* `note` 는 **원문 프레임 번호**다. 원문에 없던 판(약 목록)은 비어 있고,
       그 사실 자체가 「이건 우리가 더한 것」이라는 표시다. */
    if (group.key !== "drugs") {
      assert.ok(group.note, `${group.key} 에 어느 프레임인지 안 적혀 있다`);
    }
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

/* ── `#192` 리뷰 반영 ────────────────────────────────────────────────── */

test("**목도 스탭의 저장을 받는다** — 서버는 여는데 목만 막으면 목이 거짓말한다", async () => {
  const box = load("api", "settings-rail", "field-labels", "catalog-api");
  box.MOCK = true;
  box.sessionStorage.setItem("mockUser", "staff01");

  const sets = await box.catalogApi.sets();
  const id = sets[0].prescription_set_id;

  /* 2026-09-02 회의에서 설정 수정을 스탭에게 열었고 서버는
     `require_patient_read` 로 바뀌었는데, 목만 의사를 요구한 채 남아 있었다
     (`#192` 리뷰 ④). 목으로 보면 스탭이 403 을 맞았다. */
  const saved = await box.catalogApi.saveSet(id, { days_mode: "DAYS", days: 30 });

  assert.strictEqual(saved.prescription_set_id, id, "스탭이 저장했는데 안 돌아왔다");
});

test("**저장이 매번 전체를 다시 받지 않는다** — 새로 만들 때만 받는다", () => {
  /* `save()` 는 IIFE 안이라 밖에서 못 부른다 — 원본을 본다.

     예전에는 저장할 때마다 세트 전체와 문구 전체를 무조건 다시 받았다.
     칸 하나 고칠 때마다 두 번의 왕복이 더 있었다 (`#192` 리뷰 ⑥). */
  const code = codeOnly(read("js/settings.js"));
  const at = code.indexOf("function save()");
  assert.ok(at >= 0, "save() 를 못 찾았다 — 검사가 헛돈다");

  const next = code.slice(at + 10).search(/\n {2}function \w/);
  const body = next < 0 ? code.slice(at) : code.slice(at, at + 10 + next);

  const reload = body.indexOf("Promise.all([loadSets(), loadCopy()])");
  assert.ok(reload >= 0, "다시 받는 줄이 아예 없다 — 새로 만들면 목록에 안 뜬다");

  const guard = body.indexOf("if (!createdNew) return;");
  assert.ok(guard >= 0, "무조건 다시 받는다 — 새로 만들 때만 받아야 한다");
  assert.ok(guard < reload, "가드가 다시 받는 줄보다 뒤에 있다 — 소용이 없다");
});
