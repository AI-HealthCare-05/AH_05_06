/* **로그인이 의원 코드를 함께 받는다** — KEY-324.
 *
 * 아이디가 의원 안에서만 유일해져서, 어느 의원인지를 먼저 말해야 한다. 칸 하나,
 * 인자 하나, 본문 열쇠 하나가 새로 늘었고 **셋이 어긋나면 아무도 못 들어온다.**
 *
 * `login.js` 는 IIFE 라 shim 아래서 안 돈다. 그래서 화면과 스크립트가 맞는지는
 * 원문으로 재고, 목업이 코드를 실제로 보는지는 **돌려서** 잰다.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim");
const { read, bareCode, markupOnly } = require("./source");

/** 로그인 화면의 폼이 받는 칸 이름들 — `name=` 이 그대로 서버로 갈 이름이다. */
function formFieldNames() {
  const html = markupOnly(read("login.html"));
  return [...html.matchAll(/<input\b[^>]*\bname="([\w-]+)"/g)].map((m) => m[1]);
}

/** `api.login` 이 실제로 보내는 본문 열쇠들. */
function loginBodyKeys() {
  const code = bareCode(read("js/api.js"));
  const found = code.match(/login:\s*function\s*\([^)]*\)\s*\{[\s\S]*?body:\s*\{([^}]*)\}/);
  assert.ok(found, "api.login 이 본문을 만드는 자리를 못 찾았다 — 검사가 헛돈다");
  return found[1]
    .split(",")
    .map((pair) => pair.split(":")[0].trim())
    .filter(Boolean);
}

test("로그인 화면이 받는 칸과 api.login 이 보내는 열쇠가 같다", () => {
  /* 한쪽만 고치면 조용히 401 이 된다 — 화면은 멀쩡해 보이고 아무도 못 들어온다. */
  assert.deepEqual(formFieldNames().sort(), loginBodyKeys().sort());
  assert.ok(formFieldNames().includes("clinic_code"), "의원 코드 칸이 없다");
});

test("api.login 을 부르는 자리는 모두 인자 셋을 준다", () => {
  /* 인자가 앞에 하나 늘었다. 두 개로 부르던 자리가 남아 있으면 **아이디가
     의원 코드 자리로 들어간다** — 401 만 나오고 이유는 화면에 안 보인다. */
  /* 이름을 적어 두지 않는다 — 내일 새로 생긴 화면이 두 인자로 부르면 그것도
     잡혀야 한다. `js/` 를 통째로 훑는다. */
  const scripts = fs.readdirSync(path.join(__dirname, "..", "js")).filter((name) => name.endsWith(".js"));

  let seen = 0;
  for (const name of scripts) {
    const file = "js/" + name;
    for (const [, args] of bareCode(read(file)).matchAll(/\bapi\.login\(([^)]*)\)/g)) {
      seen += 1;
      assert.equal(args.split(",").length, 3, `${file}: api.login 인자가 셋이 아니다 — ${args}`);
    }
  }
  assert.ok(seen > 0, "api.login 을 부르는 자리를 하나도 못 찾았다 — 검사가 헛돈다");
});

test("커서는 첫 칸인 의원 코드에 있다", () => {
  /* `autofocus` 가 둘이면 브라우저는 앞엣것을 고른다. 아이디 칸에 남아 있으면
     접수대는 매번 Shift+Tab 으로 되돌아와야 한다 — 하루에 수십 번 여는 화면이다. */
  const html = markupOnly(read("login.html"));
  const fields = [...html.matchAll(/<input\b([^>]*)>/g)].map((m) => m[1]);
  const focused = fields.filter((attrs) => /\bautofocus\b/.test(attrs));

  assert.equal(focused.length, 1, "autofocus 가 하나가 아니다");
  assert.match(focused[0], /name="clinic_code"/);
});

test("login.js 는 코드를 소문자로 접고, 비면 안 보낸다", () => {
  const code = bareCode(read("js/login.js"));

  assert.match(code, /clinicInput\.value\.trim\(\)\.toLowerCase\(\)/, "대문자로 친 코드가 그대로 나간다");
  /* 비었는데 보내면 서버가 **422** 를 준다 — 화면의 「입력해 주세요」와 다른 말이다. */
  const guard = code.match(/if\s*\(([^)]*\bloginId\b[^)]*)\)\s*\{/);
  assert.ok(guard, "빈 칸을 막는 자리를 못 찾았다");
  assert.match(guard[1], /!clinicCode/, "의원 코드가 비어도 그냥 보낸다");
});

test("목업도 모르는 의원 코드를 막는다", async () => {
  /* 목업이 아무 코드나 받아 주면 「목업에서는 되는데 실서버에서는 안 되는」
     거리가 생긴다. 그 거리는 늘 배포 뒤에 발견된다. */
  const box = load("api");

  const signed = await box.api.login("clinic0001", "staff01", "local-only-password");
  assert.ok(signed.access_token);

  await assert.rejects(
    box.api.login("clinic9999", "staff01", "local-only-password"),
    (error) => error.status === 401 && error.code === "invalid_credentials",
  );
});

test("목업도 대소문자를 접는다 — 서버와 같은 규칙", async () => {
  const box = load("api");

  const signed = await box.api.login("CLINIC0001", "staff01", "local-only-password");

  assert.ok(signed.access_token, "대문자로 친 코드를 목업만 거절한다 — 서버는 접는다");
});
