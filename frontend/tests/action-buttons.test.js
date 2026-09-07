/* KEY-233 — 눌리는 모양인데 아무 일도 하지 않는 정적 버튼을 찾는다.
 *
 * 동적 렌더 버튼은 생성 직후 핸들러를 붙이는 기존 화면 테스트가 맡고, 여기서는
 * HTML에 박힌 버튼과 그 페이지가 실제로 싣는 스크립트를 대조한다. 미구현 버튼은
 * 숨겨서 통과시키지 않고 `data-unimplemented-action`으로 드러낸 뒤 분류표에
 * 정확히 한 번 올린다. */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { read, codeOnly, markupOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");
const INVENTORY = JSON.parse(fs.readFileSync(path.join(__dirname, "key233-unimplemented-actions.json"), "utf8"));
const SCRIPT_CACHE = new Map();

function attr(tag, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = tag.match(new RegExp("(?:^|\\s)" + escaped + "\\s*=\\s*[\\\"']([^\\\"']+)[\\\"']"));
  return match ? match[1] : "";
}

function scriptCode(src) {
  const rel = src.split("?")[0].replace(/^\/?frontend\//, "").replace(/^\//, "");
  if (!SCRIPT_CACHE.has(rel)) SCRIPT_CACHE.set(rel, codeOnly(read(rel)));
  return SCRIPT_CACHE.get(rel);
}

function loadedCode(html) {
  const markup = markupOnly(html);
  const chunks = [];
  for (const match of markup.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    const src = attr(match[1], "src");
    if (src) {
      const rel = src.split("?")[0].replace(/^\/?frontend\//, "").replace(/^\//, "");
      if (fs.existsSync(path.join(ROOT, rel))) chunks.push(scriptCode(src));
    } else {
      chunks.push(codeOnly(match[2]));
    }
  }
  return chunks.join("\n");
}

function variableForId(code, id) {
  const escaped = id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const patterns = [
    new RegExp("(?:var|let|const)\\s+([A-Za-z_$][\\w$]*)\\s*=\\s*document\\.getElementById\\([\\\"']" + escaped + "[\\\"']\\)"),
    new RegExp("(?:var|let|const)\\s+([A-Za-z_$][\\w$]*)\\s*=\\s*el\\([\\\"']" + escaped + "[\\\"']\\)"),
  ];
  for (const pattern of patterns) {
    const match = code.match(pattern);
    if (match) return match[1];
  }
  return "";
}

function hasHandler(tag, code) {
  if (/\baria-current=["']page["']/.test(tag)) return true; // 현재 위치 표시, 동작 버튼 아님
  if (/\btype=["']submit["']/.test(tag)) return /addEventListener\s*\(\s*["']submit["']|\.onsubmit\s*=/.test(code);

  const id = attr(tag, "id");
  if (id) {
    const escaped = id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp("getElementById\\([\\\"']" + escaped + "[\\\"']\\)\\.addEventListener").test(code)) return true;
    if (new RegExp("el\\([\\\"']" + escaped + "[\\\"']\\)\\.addEventListener").test(code)) return true;
    const variable = variableForId(code, id);
    if (variable && new RegExp("\\b" + variable + "\\.addEventListener\\s*\\(").test(code)) return true;
    if (new RegExp("[#]" + escaped + "(?:[\\\"'])").test(code) && /addEventListener\s*\(/.test(code)) return true;
    /* 페이지 전체에 건 위임 리스너는 대상의 id를 비교한다. 단순히 id 문자열이
       있다는 것만 보지 않고, 클릭 대상을 실제로 판별하는 식까지 확인한다. */
    const delegatedId = new RegExp(
      "(?:\\.id\\s*===?\\s*[\\\"']" + escaped + "[\\\"']|closest\\(\\s*[\\\"']#" + escaped + "(?:[^A-Za-z0-9_-]|$))",
    );
    if (delegatedId.test(code) && /addEventListener\s*\(\s*["']click["']/.test(code)) return true;
  }

  const dataAttrs = [...tag.matchAll(/\b(data-[\w-]+)=/g)].map((match) => match[1]);
  for (const name of dataAttrs) {
    if (name === "data-unimplemented-action") continue;
    const camel = name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    if ((code.includes("[" + name) || code.includes("dataset." + camel)) && /addEventListener\s*\(/.test(code)) return true;
  }

  for (const className of attr(tag, "class").split(/\s+/).filter(Boolean)) {
    const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const selector = new RegExp(
      "(?:querySelector(?:All)?\\(\\s*[\\\"'][^\\\"']*\\." +
        escaped +
        "(?:[^A-Za-z0-9_-]|$)|closest\\(\\s*[\\\"'][^\\\"']*\\." +
        escaped +
        "(?:[^A-Za-z0-9_-]|$)|getElementsByClassName\\(\\s*[\\\"']" +
        escaped +
        "[\\\"'])",
    );
    if (selector.test(code) && /addEventListener\s*\(/.test(code)) return true;
  }
  return false;
}

function auditPage(page) {
  const html = fs.readFileSync(path.join(ROOT, page), "utf8");
  const code = loadedCode(html);
  const findings = [];
  for (const match of html.matchAll(/<button\b[^>]*>/g)) {
    const tag = match[0];
    const declared = attr(tag, "data-unimplemented-action");
    if (declared) findings.push({ page, action: declared });
    else if (!hasHandler(tag, code)) findings.push({ page, action: attr(tag, "id") || attr(tag, "class") || "anonymous" });
  }
  return findings;
}

test("핸들러 없는 정적 동작 버튼은 모두 근거와 함께 분류된다", () => {
  const pages = fs.readdirSync(ROOT).filter((name) => name.endsWith(".html") && name !== "_make-wireframe.html");
  const found = pages.flatMap(auditPage).sort((a, b) => (a.page + a.action).localeCompare(b.page + b.action));
  const expected = INVENTORY.map(({ page, action }) => ({ page, action }))
    .sort((a, b) => (a.page + a.action).localeCompare(b.page + b.action));

  assert.deepEqual(found, expected, "새 핸들러 없는 버튼이 생겼거나 분류표가 실제 화면과 다르다");
  for (const item of INVENTORY) {
    assert.ok(["delete_candidate", "wp_f_handoff", "follow_up"].includes(item.disposition), `${item.page}/${item.action} 분류가 없다`);
    assert.ok(item.evidence, `${item.page}/${item.action} 근거가 없다`);
  }
});

/* KEY-236 — 분류만으로는 화면이 안 바뀐다. **적어 둔 처리가 마크업에 실제로
   있는지** 잰다.

   `parked`  아직 만들지 않은 자리. 무엇이 있을 자리인지는 보이되 눌리는 척은
             안 한다 — `aria-disabled="true"` 와 까닭을 담은 `title`.
             `disabled` 속성은 쓰지 않는다. 초점에서 통째로 빠져 낭독기가 그런
             자리가 있다는 것조차 못 알린다 (`css/shell.css` 의 같은 주석).
   `hidden`  없는 자리. 만들 계획이 아니라서 자리를 보여 줄 까닭이 없다. */
function tagFor(page, action) {
  const html = fs.readFileSync(path.join(ROOT, page), "utf8");
  for (const match of html.matchAll(/<button\b[^>]*>/g)) {
    if (attr(match[0], "data-unimplemented-action") === action) return match[0];
  }
  return "";
}

test("적어 둔 처리가 마크업에 실제로 있다", () => {
  for (const item of INVENTORY) {
    const tag = tagFor(item.page, item.action);
    assert.ok(tag, `${item.page}/${item.action} 를 마크업에서 못 찾았다`);
    assert.ok(item.treatment, `${item.page}/${item.action} 에 처리가 없다`);
    assert.ok(item.treatment_why, `${item.page}/${item.action} 에 그 처리를 고른 까닭이 없다`);

    if (item.treatment === "parked") {
      assert.match(tag, /aria-disabled="true"/, `${item.page}/${item.action} 가 눌리는 모양 그대로다`);
      assert.match(tag, /\btitle="[^"]{10,}"/, `${item.page}/${item.action} 에 왜 못 쓰는지가 없다`);
      assert.doesNotMatch(tag, /\bhidden\b/, `${item.page}/${item.action} 는 자리를 보여 주기로 한 것이다`);
      assert.doesNotMatch(
        tag,
        /(?<![-\w])disabled(?![-\w])/,
        `${item.page}/${item.action} 에 disabled 를 썼다 — 초점에서 빠져 낭독기가 그 자리를 못 알린다`,
      );
    } else if (item.treatment === "hidden") {
      assert.match(tag, /\bhidden\b/, `${item.page}/${item.action} 가 아직 보인다`);
    } else {
      assert.fail(`${item.page}/${item.action} 의 처리 ${item.treatment} 를 모른다`);
    }
  }
});

test("잠근 자리는 보이는 것과 들리는 것이 한 값으로 정해진다", () => {
  /* 클래스로 회색만 칠하면 화면은 잠긴 것처럼 보이는데 낭독기는 멀쩡한 단추라고
     말한다. 그 반대도 생긴다. 그래서 `aria-disabled` 하나가 둘을 정하게 했다 —
     인수조건 「접근성 상태와 안내 문구가 일관된다」가 막으려던 것이다. */
  const css = fs.readFileSync(path.join(ROOT, "css/shell.css"), "utf8");
  assert.match(css, /\[aria-disabled="true"\]\s*\{[^}]*cursor:\s*default/, "잠근 자리에 손 모양이 그대로다");
  assert.match(css, /\[aria-disabled="true"\]\s*\{[^}]*color:\s*var\(--disabled\)/, "잠근 자리가 멀쩡한 색이다");
});

test("설정 화면의 로그아웃은 이제 이어져 있다", () => {
  /* KEY-236 — 기능이 없어서가 아니라 연결이 빠져 안 눌리던 것이다.
     `shell.js` 의 `bindShell()` 이 `#logout` 을 잇는데 설정 화면은 그 파일을
     안 싣는다(`#quick-search` 가 없어 그 줄에서 죽는다). 그래서 여기서 잇는다.
     잠글 자리가 아니라 이을 자리였다. */
  const code = codeOnly(read("js/settings.js"));
  assert.match(code, /el\("logout"\)\.addEventListener/, "설정 화면 로그아웃이 다시 죽었다");
  assert.match(code, /session\.logout\(\)/, "로그아웃이 세션을 안 끊는다");
  assert.ok(
    !INVENTORY.some((item) => item.page === "settings.html" && item.action === "logout"),
    "고친 것이 미구현 분류표에 그대로 남아 있다",
  );
});

test("검사기는 새 핸들러 없는 버튼을 실제로 탐지한다", () => {
  assert.equal(hasHandler('<button id="new-action" type="button">실행</button>', ""), false);
  assert.equal(
    hasHandler('<button id="new-action" type="button">실행</button>', 'document.getElementById("new-action").addEventListener("click", run);'),
    true,
  );
  assert.equal(
    hasHandler('<button class="new-action" type="button">실행</button>', 'document.addEventListener("click", run);'),
    false,
    "페이지에 다른 리스너가 있다는 이유만으로 클래스 버튼을 처리됐다고 보면 안 된다",
  );
  assert.equal(
    hasHandler(
      '<button class="new-action" type="button">실행</button>',
      'document.querySelector(".new-action").addEventListener("click", run);',
    ),
    true,
  );
  assert.equal(attr('<button data-id="wrong" class="x">', "id"), "", "data-id를 id로 읽으면 안 된다");
});

test("주석에 적힌 핸들러는 구현으로 세지 않는다", () => {
  const code = codeOnly('// document.querySelector(".new-action").addEventListener("click", run);');
  assert.equal(hasHandler('<button class="new-action" type="button">실행</button>', code), false);
});

test("체크인 뒤로 버튼처럼 실제 핸들러 없는 버튼을 놓치지 않는다", () => {
  assert.ok(
    auditPage("checkin.html").some((item) => item.action === "sheet__back"),
    "checkin.html의 뒤로 버튼이 미구현 목록에서 빠졌다",
  );
});
