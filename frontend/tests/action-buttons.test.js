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

const ROOT = path.join(__dirname, "..");
const INVENTORY = JSON.parse(fs.readFileSync(path.join(__dirname, "key233-unimplemented-actions.json"), "utf8"));

function attr(tag, name) {
  const match = tag.match(new RegExp("\\b" + name + "=[\\\"']([^\\\"']+)[\\\"']"));
  return match ? match[1] : "";
}

function loadedCode(html) {
  let code = html;
  for (const match of html.matchAll(/<script\s+[^>]*src=["']([^"']+)["'][^>]*>/g)) {
    const src = match[1].split("?")[0];
    const full = path.join(ROOT, src.replace(/^\//, ""));
    if (fs.existsSync(full)) code += "\n" + fs.readFileSync(full, "utf8");
  }
  return code;
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
  }

  const dataAttrs = [...tag.matchAll(/\b(data-[\w-]+)=/g)].map((match) => match[1]);
  for (const name of dataAttrs) {
    if (name === "data-unimplemented-action") continue;
    const camel = name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    if ((code.includes("[" + name) || code.includes("dataset." + camel)) && /addEventListener\s*\(/.test(code)) return true;
  }

  for (const className of attr(tag, "class").split(/\s+/).filter(Boolean)) {
    if ((code.includes("." + className) || code.includes(className)) && /addEventListener\s*\(/.test(code)) return true;
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

test("검사기는 새 핸들러 없는 버튼을 실제로 탐지한다", () => {
  assert.equal(hasHandler('<button id="new-action" type="button">실행</button>', ""), false);
  assert.equal(
    hasHandler('<button id="new-action" type="button">실행</button>', 'document.getElementById("new-action").addEventListener("click", run);'),
    true,
  );
});
