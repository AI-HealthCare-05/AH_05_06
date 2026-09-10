/* 어드민 직원 목록·추가 화면 — A1-1 · A1-2 (KEY-321).
 *
 * 그리는 것은 브라우저가 하고(`tests/browser-shim.js` 가 일부러 막는다),
 * 여기서는 **값을 받아 문자열을 돌려주는 순수 함수**만 부른다.
 */

const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..");
const REPO = path.join(ROOT, "..");

function read(relative) {
  return fs.readFileSync(path.join(ROOT, relative), "utf8");
}

/** `admin-staff.js` 를 한 상자에 실어 그 상자를 돌려준다. */
function loadStaffScreen() {
  const context = {
    /* `esc` · `errorMessage` 는 `api.js` 가 준다. 화면에서 함께 실리는 것과
       같은 것을 쓰려고 그 파일에서 꺼낸다 — 흉내내면 이스케이프 규칙이 갈린다. */
    console,
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    location: { search: "" },
    document: { body: null, getElementById: () => null },
    fetch: () => Promise.reject(new Error("검사에서 네트워크를 쓰지 않는다")),
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(read("js/api.js"), context);
  vm.runInContext(read("js/admin-staff.js"), context);
  return context;
}

/** 서버가 인정하는 조합 다섯을 `app/core/rbac.py` 에서 그대로 읽는다. */
function serverCombinations() {
  const source = fs.readFileSync(path.join(REPO, "app", "core", "rbac.py"), "utf8");
  const block = source.slice(
    source.indexOf("VALID_ROLE_COMBINATIONS"),
    source.indexOf(")", source.indexOf("frozenset({Role.DOCTOR, Role.ADMIN})")),
  );
  return block
    .split("\n")
    .filter((line) => line.includes("frozenset({"))
    .map((line) =>
      [...line.matchAll(/Role\.([A-Z]+)/g)]
        .map((match) => match[1].toLowerCase())
        .sort()
        .join("|"),
    )
    .sort();
}

test("화면이 고르게 하는 조합이 서버가 받는 조합과 정확히 같다", () => {
  /* **여기가 이 화면에서 제일 중요한 자리다.**
   *
   * 체크상자 셋을 두고 마음대로 조합하게 하면 화면은 `의사+스탭` 을 만들 수
   * 있는 것처럼 보이는데 서버가 400 을 준다 — 누를 수 있는데 안 되는 것이다.
   * 반대로 화면이 덜 주면 만들 수 있는 계정을 못 만든다.
   *
   * 서버 표를 여기서 읽어 견준다. 한쪽만 늘리면 이 검사가 운다.
   */
  const { STAFF_ROLE_CHOICES } = loadStaffScreen();
  const offered = STAFF_ROLE_CHOICES.map((choice) => choice.roles.slice().sort().join("|")).sort();

  assert.deepEqual(offered, serverCombinations());
});

test("서버 표를 실제로 읽었는지부터 본다 — 못 읽으면 위 검사가 헛돈다", () => {
  const combos = serverCombinations();
  assert.strictEqual(combos.length, 5, `서버 조합을 ${combos.length}개 읽었다`);
  assert.ok(combos.includes("admin|staff"), `admin|staff 를 못 읽었다: ${combos}`);
  assert.ok(!combos.includes("doctor|staff"), "의사+스탭이 서버 표에 있다");
});

test("고른 값이 서버로 보낼 역할 배열이 된다", () => {
  const { staffRolesFor } = loadStaffScreen();
  assert.deepEqual(staffRolesFor("doctor+admin"), ["doctor", "admin"]);
  assert.deepEqual(staffRolesFor("staff"), ["staff"]);
  assert.deepEqual(staffRolesFor("없는키"), [], "모르는 값이 역할이 되면 안 된다");
});

test("역할을 사람 말로 적는다 — 화면에 doctor 가 그대로 뜨지 않게", () => {
  const { staffRolesLabel } = loadStaffScreen();
  assert.strictEqual(staffRolesLabel(["doctor"]), "의사");
  assert.strictEqual(staffRolesLabel(["staff", "admin"]), "스탭 · 어드민");
  assert.strictEqual(staffRolesLabel([]), "");
  /* 서버가 새 역할을 더해도 화면이 빈칸을 그리지 않는다 — 모르면 그대로 적는다. */
  assert.strictEqual(staffRolesLabel(["nurse"]), "nurse");
});

test("퇴사자를 목록에서 지우지 않고 상태로 말한다", () => {
  const { staffStateLabel } = loadStaffScreen();
  assert.strictEqual(staffStateLabel({ status: "left" }), "퇴사");
  assert.strictEqual(staffStateLabel({ status: "active", must_change_password: true }), "첫 로그인 전");
  assert.strictEqual(staffStateLabel({ status: "active", must_change_password: false }), "");
});

test("목록이 이름·아이디·역할·상태를 한 줄로 그린다", () => {
  const { staffListHtml } = loadStaffScreen();
  const html = staffListHtml([
    { staff_id: 1, login_id: "doctor01", name: "박연", roles: ["doctor"], status: "active", must_change_password: false },
    { staff_id: 2, login_id: "left01", name: "문가람", roles: ["staff"], status: "left", must_change_password: false },
  ]);

  assert.match(html, /박연/);
  assert.match(html, /doctor01/);
  assert.match(html, /의사/);
  assert.match(html, /문가람/);
  assert.match(html, /퇴사/);
  assert.match(html, /staffs__row--left/, "퇴사자 줄이 따로 표시되지 않는다");
});

test("빈 목록과 못 불러온 것은 다른 말이다", () => {
  const { staffListHtml } = loadStaffScreen();
  assert.match(staffListHtml([]), /등록된 직원이 없습니다/);
  assert.doesNotMatch(staffListHtml([]), /불러오지 못했습니다/);

  const screen = read("js/admin.js");
  assert.match(screen, /직원 목록을 불러오지 못했습니다/, "실패를 「비어 있다」로 그리고 있다");
});

test("이름에 든 HTML 이 그대로 그려지지 않는다", () => {
  const { staffListHtml } = loadStaffScreen();
  const html = staffListHtml([
    {
      staff_id: 1,
      login_id: "evil0001",
      name: '<img src=x onerror="alert(1)">',
      roles: ["staff"],
      status: "active",
      must_change_password: false,
    },
  ]);
  assert.doesNotMatch(html, /<img/, "이름의 태그가 그대로 나갔다");
  assert.match(html, /&lt;img/);
});

test("추가 폼이 네 칸을 갖고 규칙을 미리 말한다", () => {
  const { staffFormHtml } = loadStaffScreen();
  const html = staffFormHtml();

  for (const id of ["staff-name", "staff-login-id", "staff-password", "staff-roles"]) {
    assert.match(html, new RegExp(`id="${id}"`), `${id} 칸이 없다`);
  }
  /* 규칙을 눌러 보고 알게 하지 않는다 — 서버가 400 을 주기 전에 화면이 말한다. */
  assert.match(html, /네 자 이상/);
  assert.match(html, /8자 이상/);
  assert.match(html, /첫 로그인에서 본인이 바꿉니다/);
  assert.match(html, /type="password"/, "초기 비밀번호가 화면에 그대로 보인다");
});

test("이 화면이 붙이는 클래스가 이 화면이 싣는 CSS 에 있다", () => {
  /* `css-reaches-page.test.js` 는 **화면 파일에 적힌** 클래스만 본다. 여기
     것들은 자바스크립트가 붙이므로 그 검사가 못 잡는다 — 실제로 `.field` 계열을
     썼다가 입력칸이 브라우저 기본 모양으로 떴다. 그 자리를 여기서 막는다.

     `admin.html` 이 싣는 CSS 안에 규칙이 있는지만 본다(어느 파일인지는 안 본다).
  */
  const page = read("admin.html");
  const files = [...page.matchAll(/href="\/(css\/[a-z-]+\.css)"/g)].map((m) => m[1]);
  assert.ok(files.length >= 3, `admin.html 이 싣는 CSS 를 ${files.length}개밖에 못 찾았다`);
  const css = files.map((rel) => read(rel)).join("\n");

  const screen = read("js/admin-staff.js") + read("js/admin.js");
  const used = new Set();
  for (const match of screen.matchAll(/class="([^"'\\]+)"/g)) {
    for (const name of match[1].split(/\s+/)) if (name) used.add(name);
  }
  assert.ok(used.has("staffs"), "검사가 클래스를 못 긁고 있다");

  const missing = [...used].filter((name) => !css.includes("." + name)).sort();
  assert.deepEqual(missing, [], `모양 없이 뜰 클래스: ${missing.join(", ")}`);
});

test("서버 오류를 사람 말 한 줄로 옮긴다", () => {
  const { staffCreateSaying } = loadStaffScreen();
  assert.match(staffCreateSaying({ code: "LOGIN_ID_TAKEN", status: 409 }), /이미 쓰고 있는 아이디/);
  assert.match(staffCreateSaying({ code: "INVALID_ROLE_COMBINATION", status: 400 }), /고를 수 없는 역할/);
  assert.match(staffCreateSaying({ code: "unknown", status: 500 }), /추가하지 못했습니다/);
  assert.match(staffCreateSaying(null), /추가하지 못했습니다/);
});

test("화면이 부르는 경로가 서버가 여는 경로와 같다", () => {
  const screen = read("js/admin-staff.js");
  const routers = fs.readFileSync(path.join(REPO, "app", "apis", "v1", "admin_staff_routers.py"), "utf8");

  assert.match(screen, /request\("\/admin\/staffs"\)/, "목록을 부르는 자리가 없다");
  assert.match(screen, /method: "POST"/, "추가를 부르는 자리가 없다");
  assert.match(routers, /prefix="\/admin\/staffs"/, "서버가 그 경로를 안 연다");
});
