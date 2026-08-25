/* HTML 로 나가는 글자를 막는 규칙 — KEY-158 로 한 곳에 모았다.
 *
 * 예전에는 `shell.js` · `checkin.js` · `doctor.js` 셋에 같은 이름이 각각 있었고
 * **구현이 달랐다** — `shell.js` 만 홑따옴표까지 막았다. KEY-158 이
 * `checkin.js` 것을 전역으로 꺼내면서 이름이 부딪히게 됐고, 함께 실리면
 * 나중 선언이 조용히 이긴다 (이희진 님 `#103` 리뷰).
 *
 * 가장 엄한 것을 `api.js` 에 남겼다. 여기서 **그 엄함을 못 박는다** — 덜 엄한
 * 판으로 되돌리면 이 검사가 죽는다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const JS_DIR = path.join(__dirname, "..", "js");

test("다섯 글자를 모두 막는다 — 홑따옴표까지", () => {
  const { esc } = load("api");

  assert.strictEqual(esc("<script>"), "&lt;script&gt;");
  assert.strictEqual(esc("a & b"), "a &amp; b");
  assert.strictEqual(esc('그는 "예"라 했다'), "그는 &quot;예&quot;라 했다");
  assert.strictEqual(
    esc("it's"),
    "it&#39;s",
    "홑따옴표를 안 막는다 — 홑따옴표 속성에 쓰는 날 그대로 뚫린다",
  );
});

test("빈 값은 빈 문자열이다 — null 이 화면에 뜨지 않는다", () => {
  const { esc } = load("api");
  assert.strictEqual(esc(null), "");
  assert.strictEqual(esc(undefined), "");
  assert.strictEqual(esc(0), "0", "0 은 빈 값이 아니다");
});

test("같은 이름이 두 번 선언되지 않는다", () => {
  /* 한 곳에 모은 것이 요점이다. 어느 파일이든 `function esc(` 를 다시 선언하면
     함께 실릴 때 나중 것이 이기고, 어느 판이 도는지 알 수 없게 된다. */
  const declaring = fs
    .readdirSync(JS_DIR)
    .filter((name) => name.endsWith(".js"))
    .filter((name) => /(^|\n)\s*function esc\(/.test(fs.readFileSync(path.join(JS_DIR, name), "utf8")));

  assert.deepStrictEqual(declaring, ["api.js"], `esc() 를 선언하는 파일이 여럿이다: ${declaring.join(", ")}`);
});
