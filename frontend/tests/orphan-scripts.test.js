/* **아무 화면도 안 싣는 파일을 재지 않는다** — KEY-281 이 남긴 처분.
 *
 * `frontend/js/guide.js` 는 어떤 HTML 도 안 싣는 고아였다. 그런데 검사 넷이
 * 그것을 재고 있었고, 그동안 **초록불이 지키던 것은 사용자에게 가지 않는
 * 코드**였다. 옮겨 보니 실제 화면에서는 계약 하나가 이미 깨져 있었다 —
 * 「다시 시도」가 치던 글자를 지웠다 (KEY-281).
 *
 * 이름을 적어 막지 않는다. 늘 같은 물음으로 잰다:
 *
 *   ① 저장소의 스크립트를 **어느 화면이든 싣는가**
 *   ② 검사가 읽는 스크립트가 **실리는 것인가**
 *
 * ②가 이 파일의 요점이다. ①만 재면 고아를 지우기만 하고, 그것을 붙잡고 있던
 * 검사는 남아 다음 고아를 다시 만든다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { codeOnly } = require("./source.js");

const FRONTEND = path.join(__dirname, "..");

/** 화면이 `<script src>` 로 싣는 것 전부 — 버전 꼬리(`?v=12`)는 뗀다. */
function loadedScripts() {
  const pages = [
    ...fs.readdirSync(FRONTEND).filter((n) => n.endsWith(".html")).map((n) => n),
    ...fs
      .readdirSync(path.join(FRONTEND, "patient_wireframe", "html"))
      .filter((n) => n.endsWith(".html"))
      .map((n) => path.join("patient_wireframe", "html", n)),
  ];
  const loaded = new Set();
  for (const page of pages) {
    const html = fs.readFileSync(path.join(FRONTEND, page), "utf8");
    for (const match of html.matchAll(/<script src="([^"]+)"/g)) {
      loaded.add(match[1].split("?")[0].replace(/^\//, ""));
    }
  }
  return loaded;
}

function repoScripts() {
  const found = [];
  (function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const rel = path.relative(FRONTEND, full);
      if (entry.isDirectory()) {
        if (entry.name === "tests" || entry.name === "node_modules") continue;
        walk(full);
      } else if (entry.name.endsWith(".js")) {
        found.push(rel);
      }
    }
  })(FRONTEND);
  return found.sort();
}

test("**저장소의 스크립트는 모두 어느 화면인가 싣는다** — 안 실리면 아무도 안 쓰는 코드다", () => {
  const loaded = loadedScripts();
  const orphans = repoScripts().filter((rel) => !loaded.has(rel));

  assert.deepEqual(
    orphans,
    [],
    `아무 화면도 안 싣는 스크립트가 있다 — ${orphans.join(" · ")}. ` +
      "지우거나, 싣는 화면을 만들거나, 왜 남기는지 여기에 적는다",
  );
});

test("**검사가 읽는 스크립트도 실리는 것이어야 한다** — 초록불이 헛것을 지킨다", () => {
  const loaded = loadedScripts();
  const here = fs.readdirSync(__dirname).filter((n) => n.endsWith(".test.js"));

  const wrong = [];
  for (const name of here) {
    /* **주석은 뺀다.** 이 파일의 설명글이 예로 든 경로가 제 검사에 걸렸다 —
       재려는 것은 검사가 실제로 읽는 파일이지, 설명에 적힌 이름이 아니다. */
    const code = codeOnly(fs.readFileSync(path.join(__dirname, name), "utf8"));
    for (const match of code.matchAll(/read\(\s*"((?:\.\.\/)?[\w./-]+\.js)"\s*\)/g)) {
      const rel = match[1].replace(/^\.\.\//, "");
      if (rel.startsWith("docs/") || rel.startsWith("scripts/")) continue;
      if (!loaded.has(rel) && fs.existsSync(path.join(FRONTEND, rel))) {
        wrong.push(`${name} → ${rel}`);
      }
    }
  }

  assert.deepEqual(
    wrong,
    [],
    `검사가 아무 화면도 안 싣는 파일을 잰다 — ${wrong.join(" · ")}. ` +
      "지키려는 계약을 실제로 실리는 파일로 옮긴다",
  );
});
