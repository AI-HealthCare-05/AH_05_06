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
const { read, codeOnly, markupOnly } = require("./source.js");

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

test("**현황이 읽는 이력을 목업이 준다** — 없으면 `?mock=1` 로 그 화면을 못 본다", () => {
  /* 이 분기가 없어서 현황 탭(D1-6)이 `?mock=1` 에서 늘 「불러오지 못했습니다」였다.
     서버(`app/timeline/api.py`)에는 있는데 목업만 없었다 — **목업이 서버보다
     좁으면 화면을 목업으로 검수할 수 없다.** 2heej 님이 `#162` 에서 같은 부류를
     짚었다(`generateGuide` 에 목업 분기가 없던 것). */
  const code = codeOnly(read("js/doctor-api.js"));

  /* **정의만 보지 않는다.** 규칙을 만들어 두고 안 쓰면 아무 일도 안 일어난다 —
     받는 주소 목록에 실제로 들어 있어야 하고, 걸렸을 때 부르는 자리도 있어야 한다. */
  const union = code.match(/var m = [^;]+;/);
  assert.ok(union, "받는 주소를 모으는 자리가 없다");
  assert.match(union[0], /\btl\b/, "timeline 을 받는 주소 목록에 안 넣었다");
  assert.match(code, /if \(tl\) return resolve\(mockTimeline\(/, "걸려도 부르지 않는다");

  /* 화면이 읽는 세 칸을 다 준다 */
  const at = code.indexOf("function mockTimeline(visitId)");
  assert.notEqual(at, -1, "이력을 만드는 자리가 없다");
  const body = code.slice(at, code.indexOf("\n}", at));
  for (const key of ["visit_id", "entries", "messages"]) {
    assert.ok(body.includes(key), `${key} 를 안 준다`);
  }

  /* **예약은 승인이 만든다** — 승인 전에 채워 두면 「승인 안 했는데 나갈 문자가
     있다」로 읽힌다. 서버 주석이 그렇게 못박았다. */
  const msgs = body.slice(body.indexOf("var messages"));
  assert.match(msgs, /guide\.status === "SCHEDULED_TO_SEND"/, "승인 여부와 무관하게 예약을 준다");

  /* 안내문이 없는 진료는 빈 이력이다 — 오류가 아니다 */
  assert.match(body, /if \(!guide\) return \{[^}]*entries: \[\]/, "안내문이 없으면 오류를 낸다");
});
