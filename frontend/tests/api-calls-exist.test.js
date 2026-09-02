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
const { codeOnly, markupOnly } = require("./source.js");

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

/* **화면이 그 파일을 싣기는 하는가.**
 *
 * 함수가 어딘가에 있어도, 그 파일을 `<script>` 로 안 실으면 브라우저에서
 * `ocrApi is not defined` 로 터진다. `patients.html` 이 `js/upload.js` 는 싣고
 * `js/ocr-api.js` 는 안 실어서, 진료기록 블록의 「판독 결과 확인」 경로가 환자를
 * 고를 때마다 조용히 죽어 있었다 — 검사는 전부 초록이었다.
 */
function pageScripts(html) {
  return [...markupOnly(html).matchAll(/<script\s+src="\/js\/([\w-]+\.js)"/g)].map((m) => m[1]);
}

test("**화면이 부르는 API 파일을 실제로 싣는다**", () => {
  const bundles = apiBundles();
  const ROOT = path.join(__dirname, "..");
  const pages = fs.readdirSync(ROOT).filter((n) => n.endsWith(".html"));
  assert.ok(pages.length >= 3, "화면 파일을 못 찾았다 — 검사가 헛돈다");

  const missing = [];
  for (const page of pages) {
    const loaded = pageScripts(fs.readFileSync(path.join(ROOT, page), "utf8"));
    if (!loaded.length) continue;

    for (const script of loaded) {
      const full = path.join(JS, script);
      if (!fs.existsSync(full)) {
        missing.push(`${page}: /js/${script} 를 싣는데 그런 파일이 없다`);
        continue;
      }
      const code = codeOnly(fs.readFileSync(full, "utf8"));
      for (const m of code.matchAll(/\b([a-zA-Z_$][\w$]*Api)\s*\.\s*[a-zA-Z_$][\w$]*\s*\(/g)) {
        const bundle = bundles[m[1]];
        if (!bundle) continue;
        if (loaded.indexOf(bundle.file) === -1) {
          missing.push(`${page}: ${script} 가 ${m[1]} 를 쓰는데 ${bundle.file} 을 안 싣는다`);
        }
      }
    }
  }

  assert.deepEqual(
    [...new Set(missing)],
    [],
    "안 실은 파일의 API 를 부른다 — 브라우저에서만 터진다:\n  " + [...new Set(missing)].join("\n  "),
  );
});
