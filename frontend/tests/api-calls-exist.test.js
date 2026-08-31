/* **부르는 함수가 실제로 있는가.**
 *
 * `doctorApi.timeline(...)` 을 화면이 부르는데 `doctor-api.js` 에 그 함수가
 * 없던 적이 있다. 검사는 전부 통과했다 — 화면을 그리는 코드는 shim 아래서
 * 안 돌기 때문에, 없는 함수를 부르는 줄에 아무도 닿지 않았다.
 *
 * 브라우저에서만 `undefined is not a function` 으로 터진다. 그 부류를
 * 원문으로 막는다.
 *
 * 완벽하지는 않다 — 변수에 담아 부르거나 이름을 만들어 부르는 것은 못 본다.
 * 그래도 `xxxApi.yyy(` 라고 곧이곧대로 적은 것은 전부 잡는다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { codeOnly } = require("./source.js");

const JS = path.join(__dirname, "..", "js");

/** 어느 파일이 어느 이름의 묶음을 정의하는가 — `var xxxApi = {` */
function apiBundles() {
  const out = {};
  for (const name of fs.readdirSync(JS).filter((n) => n.endsWith(".js"))) {
    const code = codeOnly(fs.readFileSync(path.join(JS, name), "utf8"));
    for (const m of code.matchAll(/(?:^|\n)var\s+([a-zA-Z_$][\w$]*Api)\s*=\s*\{/g)) {
      /* 그 묶음이 가진 이름들 — `이름: function` 꼴만 센다 */
      const at = m.index + m[0].length;
      const body = code.slice(at, code.indexOf("\n};", at));
      const keys = new Set();
      for (const k of body.matchAll(/(?:^|\n)\s{2}([a-zA-Z_$][\w$]*):\s*function/g)) keys.add(k[1]);
      out[m[1]] = { file: name, keys: keys };
    }
  }
  return out;
}

test("**부르는 API 함수가 실제로 있다**", () => {
  const bundles = apiBundles();
  assert.ok(Object.keys(bundles).length >= 2, "API 묶음을 못 찾았다 — 검사가 헛돈다");

  const missing = [];
  for (const name of fs.readdirSync(JS).filter((n) => n.endsWith(".js"))) {
    const code = codeOnly(fs.readFileSync(path.join(JS, name), "utf8"));
    for (const m of code.matchAll(/\b([a-zA-Z_$][\w$]*Api)\s*\.\s*([a-zA-Z_$][\w$]*)\s*\(/g)) {
      const bundle = bundles[m[1]];
      if (!bundle) continue; // 이 저장소가 정의한 묶음이 아니면 넘어간다
      if (!bundle.keys.has(m[2])) missing.push(`${name}: ${m[1]}.${m[2]}() — ${bundle.file} 에 없다`);
    }
  }

  assert.deepEqual(
    [...new Set(missing)],
    [],
    "없는 API 함수를 부른다 — 브라우저에서만 터진다:\n  " + [...new Set(missing)].join("\n  "),
  );
});
