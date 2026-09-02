/* **어드민 화면이 일곱 프레임을 다 품는가** — KEY-234.
 *
 * 와이어프레임의 `A1-1`~`A1-7` 은 별도 화면이 아니라 좌측 목록 네 줄로 묶인다.
 * 묶다가 하나를 빠뜨리면 그 프레임은 **화면에서 아예 사라진다** — 목록에 없으니
 * 갈 길이 없고, 없다는 사실조차 안 보인다.
 *
 * 그리는 코드는 shim 아래서 안 돌기 때문에, 묶는 표와 그 표를 읽는 함수만 잰다.
 * 그래서 `ADMIN_MENU` 와 `adminFramesFor` 를 IIFE 밖에 뒀다.
 *
 * 이 화면이 생긴 이유도 함께 잰다 — `js/session.js:54` 가 admin 계정을
 * `/admin.html` 로 보내는데 그 파일이 없어 **로그인하면 404 가 떴다.**
 * 시드에 admin 단독 계정이 셋 있다(`admin01` · `lastadmin01` · `admin21`).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..");

/* frames.js 와 admin.js 는 브라우저용 전역 스크립트다. 브라우저와 같은 방식으로
   전역에 올려야 실제 화면과 같은 것을 잰다. `document` 가 없으면 admin.js 의
   IIFE 가 첫 줄에서 죽으므로, 화면 요소를 못 찾는 shim 만 얹어 준다. */
function loadAdmin() {
  const context = {
    console,
    document: { getElementById: () => null, addEventListener: () => {} },
    location: { replace: () => {} },
  };
  vm.createContext(context);
  for (const file of ["js/frames.js", "js/admin.js"]) {
    vm.runInContext(fs.readFileSync(path.join(ROOT, file), "utf8"), context);
  }
  return context;
}

const { FRAMES, ADMIN_MENU, adminFramesFor, adminMenuCovers } = loadAdmin();

const ADMIN_FRAMES = FRAMES.filter((f) => f.area === "admin");

/* ── 일곱을 다 품는가 ──────────────────────────────────────────────────── */

test("**어드민 프레임 일곱이 하나도 안 빠진다** — 빠지면 화면에서 사라진다", () => {
  assert.strictEqual(
    ADMIN_FRAMES.length,
    7,
    "와이어프레임의 어드민은 일곱 프레임이다",
  );
  assert.strictEqual(
    adminMenuCovers(ADMIN_FRAMES).join(", "),
    "",
    "메뉴 어디에도 안 묶인 프레임이 있다",
  );
});

test("메뉴가 없는 번호를 가리키지 않는다", () => {
  for (const item of ADMIN_MENU) {
    for (const id of item.frames) {
      const found = FRAMES.filter((f) => f.id === id);
      assert.strictEqual(
        found.length,
        1,
        `${item.label} 이 없는 번호를 가리킨다: ${id}`,
      );
      assert.strictEqual(
        found[0].area,
        "admin",
        `${id} 는 어드민 프레임이 아니다`,
      );
    }
  }
});

test("같은 프레임이 두 메뉴에 걸리지 않는다", () => {
  const seen = [];
  for (const item of ADMIN_MENU) for (const id of item.frames) seen.push(id);
  const twice = seen.filter((id, at) => seen.indexOf(id) !== at);
  assert.strictEqual(twice.join(", "), "", "두 곳에 걸린 프레임");
});

/* ── 메뉴 → 프레임 ────────────────────────────────────────────────────── */

test("메뉴를 고르면 그 화면들이 나온다", () => {
  assert.deepEqual(
    adminFramesFor("staff").map((f) => f.id),
    ["A1-1", "A1-2", "A1-3"],
    "직원 메뉴는 목록·추가·수정 셋이다",
  );
  assert.deepEqual(
    adminFramesFor("clinic").map((f) => f.id),
    ["A1-4"],
  );
  assert.deepEqual(
    adminFramesFor("sms").map((f) => f.id),
    ["A1-5"],
  );
  assert.deepEqual(
    adminFramesFor("log").map((f) => f.id),
    ["A1-6", "A1-7"],
  );
});

test("없는 메뉴를 물으면 빈 목록이다 — 죽지 않는다", () => {
  assert.deepEqual(adminFramesFor("없음"), []);
  assert.deepEqual(adminFramesFor(""), []);
});

/* ── 아직 아니라고 말하는가 ────────────────────────────────────────────── */

test("**일곱 다 「화면 없음」이고 무엇이 있어야 되는지 말한다**", () => {
  /* 어드민에 데이터를 줄 API 가 하나도 없다 — GET /staffs 도 GET /hospital 도.
     그런데 화면이 그럴듯한 값을 그리면 지금 다른 화면들이 겪는 어긋남이
     여기서 다시 생긴다. 값을 지어내지 않았는지를 잰다. */
  for (const frame of ADMIN_FRAMES) {
    assert.strictEqual(frame.level, 3, `${frame.id} 이 화면 없음이 아니다`);
    assert.ok(frame.role, `${frame.id} 이 무슨 화면인지 말하지 않는다`);
    assert.ok(
      frame.blocker,
      `${frame.id} 이 무엇이 있어야 되는지 말하지 않는다`,
    );
  }
});

/* ── 동작하지 않는 버튼을 두지 않았는가 ────────────────────────────────── */

test("**본문에 동작하는 척하는 버튼이 없다** — 눌러도 아무 일 없는 버튼은 「된다」고 말한다", () => {
  const html = fs.readFileSync(path.join(ROOT, "admin.html"), "utf8");
  const js = fs.readFileSync(path.join(ROOT, "js", "admin.js"), "utf8");

  /* 상단바는 이제 넷 다 갈 곳이 있다 — 관리(S2)는 `manage.html`, 설정(D2)은
     `settings.html`. 어느 탭이 어느 쪽인지는 `topbar-tabs-go.test.js` 가 화면
     전부에 대고 잰다. 여기서는 **어드민 화면에 잠긴 탭이 남아 있지 않은
     것**만 본다 — 화면이 생겼는데 잠가 두면 없는 줄 안다. */
  /* **주석이 아니라 요소만 본다.** 위 설명 문단에도 `tab--later` 가 적혀 있어서,
     그냥 글자로 찾으면 검사가 제 주석을 물고 통과한다. */
  const later = html
    .split("\n")
    .filter((line) => line.includes("tab--later") && line.includes("<button"));
  assert.deepStrictEqual(later, [], "화면이 있는데 아직 잠가 두었다");

  /* 본문이 그리는 것은 카드뿐이어야 한다. 카드 안에 버튼을 넣으면
     서버가 없는데 누를 것이 생긴다. */
  const bodyStart = js.indexOf("function renderBody");
  assert.notEqual(bodyStart, -1, "renderBody 가 없다 — 검사가 헛돈다");
  const body = js.slice(bodyStart, js.indexOf("function menuLabel"));
  assert.ok(
    !body.includes("<button"),
    "본문 카드에 버튼을 그린다 — 누를 데가 없는데 눌린다",
  );
});

test("좌측 메뉴는 진짜로 동작한다 — 그건 죽은 버튼이 아니다", () => {
  const js = fs.readFileSync(path.join(ROOT, "js", "admin.js"), "utf8");
  assert.ok(js.includes('data-menu="'), "메뉴 줄에 고를 표시가 없다");
  assert.ok(
    js.includes('closest("[data-menu]")'),
    "메뉴 클릭을 받는 자리가 없다",
  );
});
