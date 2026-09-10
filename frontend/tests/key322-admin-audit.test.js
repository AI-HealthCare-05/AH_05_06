/* 어드민 감사 로그 화면 — A1-6 · A1-7 (KEY-322). */

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

function loadAuditScreen() {
  const context = {
    console,
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    location: { search: "" },
    document: { body: null, getElementById: () => null },
    fetch: () => Promise.reject(new Error("검사에서 네트워크를 쓰지 않는다")),
    URLSearchParams,
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(read("js/api.js"), context);
  vm.runInContext(read("js/admin-audit.js"), context);
  return context;
}

const ROW = {
  event_id: "guide:12",
  occurred_at: "2026-09-10T08:58:00+09:00",
  source: "guide",
  event_type: "APPROVED",
  actor_staff_id: 900,
  actor_name: "박연",
  visit_id: 1204,
  summary: "안내문을 승인했습니다",
};

test("화면이 아는 유형이 서버가 주는 유형과 같다", () => {
  /* 서버가 유형을 늘렸는데 화면이 모르면 그 줄은 영문 그대로 뜬다. 반대로
     화면에만 있는 유형은 거르개에서 고를 수 있는데 결과가 늘 비어 있다. */
  const { AUDIT_SOURCE_LABEL } = loadAuditScreen();
  const dto = fs.readFileSync(path.join(REPO, "app", "dtos", "admin_audit.py"), "utf8");
  const block = dto.slice(dto.indexOf("class AuditSource"), dto.indexOf("class AuditLogEntry"));
  const server = [...block.matchAll(/^\s+[A-Z_]+ = "([a-z_]+)"$/gm)].map((m) => m[1]).sort();

  assert.strictEqual(server.length, 5, `서버 유형을 ${server.length}개 읽었다 — 검사가 헛돈다`);
  assert.deepEqual(Object.keys(AUDIT_SOURCE_LABEL).sort(), server);
});

test("유형을 사람 말로 적는다", () => {
  const { auditSourceLabel } = loadAuditScreen();
  assert.strictEqual(auditSourceLabel("guide"), "안내문");
  assert.strictEqual(auditSourceLabel("staff_account"), "직원 계정");
  /* 서버가 새 유형을 더해도 빈칸을 그리지 않는다. */
  assert.strictEqual(auditSourceLabel("brand_new"), "brand_new");
});

test("행위자가 없는 줄도 누가 한 일인지 말한다", () => {
  /* 빈칸으로 두면 「이름을 못 불러왔다」로 읽힌다. */
  const { auditActorLabel } = loadAuditScreen();
  assert.strictEqual(auditActorLabel({ source: "guide", actor_name: "박연" }), "박연");
  assert.strictEqual(auditActorLabel({ source: "patient_usage", actor_name: null }), "환자");
  assert.strictEqual(auditActorLabel({ source: "otp", actor_name: null }), "환자");
  assert.strictEqual(auditActorLabel({ source: "message", actor_name: null }), "발송기");
  assert.strictEqual(auditActorLabel({ source: "staff_account", actor_name: null }), "—");
});

test("목록이 다섯 칸을 그리고 진료가 없는 줄도 빈칸으로 선다", () => {
  const { auditListHtml } = loadAuditScreen();
  const html = auditListHtml([ROW, { ...ROW, event_id: "staff_account:3", source: "staff_account", visit_id: null }]);

  assert.match(html, /2026-09-10 08:58/);
  assert.match(html, /안내문/);
  assert.match(html, /박연/);
  assert.match(html, /1204/);
  assert.match(html, /안내문을 승인했습니다/);
  /* 머리글도 `<tr>` 이라 그것으로 세면 하나 더 나온다 — 줄마다 하나뿐인
     칸으로 센다. */
  assert.strictEqual((html.match(/class="audit__when"/g) || []).length, 2);
});

test("빈 결과와 못 불러온 것은 다른 말이다", () => {
  const { auditListHtml, auditLoadSaying } = loadAuditScreen();
  assert.match(auditListHtml([]), /그 조건에 맞는 기록이 없습니다/);
  assert.doesNotMatch(auditListHtml([]), /불러오지 못했습니다/);
  assert.match(auditLoadSaying({ status: 500 }), /불러오지 못했습니다/);
  assert.match(auditLoadSaying({ status: 403 }), /권한이 없습니다/);
});

test("요약에 든 HTML 이 그대로 그려지지 않는다", () => {
  const { auditListHtml } = loadAuditScreen();
  const html = auditListHtml([{ ...ROW, summary: '<img src=x onerror="alert(1)">' }]);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
});

test("빈 거르개는 아예 안 보낸다", () => {
  /* 빈 문자열을 보내면 서버가 그것을 값으로 읽고 아무것도 안 맞는 목록을 준다. */
  const { auditQueryFrom } = loadAuditScreen();
  assert.deepEqual(auditQueryFrom({ source: "", actor: "", visit: "", from: "", to: "" }), {});
  assert.deepEqual(auditQueryFrom({ source: "guide", actor: "900", visit: "1204", from: "", to: "" }), {
    source: "guide",
    actor_staff_id: "900",
    visit_id: "1204",
  });
});

test("「이 날까지」가 그날을 포함한다", () => {
  /* 날짜만 고르면 0시다. 그대로 보내면 그날 기록이 통째로 빠지고, 고른 사람은
     그날 아무 일도 없었다고 읽는다. */
  const { auditQueryFrom } = loadAuditScreen();
  const query = auditQueryFrom({ from: "2026-09-01", to: "2026-09-10" });
  assert.strictEqual(query.occurred_from, "2026-09-01T00:00:00");
  assert.strictEqual(query.occurred_to, "2026-09-10T23:59:59");
});

test("질의 문자열에 빈 값이 안 실린다", () => {
  const screen = read("js/admin-audit.js");
  assert.match(screen, /query\[key\] !== ""/, "빈 값을 거르는 자리가 없다");
  assert.match(screen, /request\("\/admin\/audit-logs"/);
});

test("화면이 부르는 경로를 서버가 연다", () => {
  const routers = fs.readFileSync(path.join(REPO, "app", "apis", "v1", "admin_audit_routers.py"), "utf8");
  assert.match(routers, /prefix="\/admin\/audit-logs"/);
});

test("이 화면이 붙이는 클래스가 이 화면이 싣는 CSS 의 바탕 규칙에 있다", () => {
  /* `css-reaches-page.test.js` 는 화면 파일에 적힌 클래스만 본다 — 여기 것은
     자바스크립트가 붙인다. 자손 규칙으로는 안 세는 것이 요점이다: KEY-321 에서
     `.staff-add__foot .button-primary` 가 부분 문자열 검사를 만족시켜, 바탕
     규칙이 없는데도 초록불이었다(브라우저 기본 회색 버튼이 떴다). */
  const page = read("admin.html");
  const files = [...page.matchAll(/href="\/(css\/[a-z-]+\.css)"/g)].map((m) => m[1]);
  const css = files.map((rel) => read(rel)).join("\n");

  const defined = new Set();
  for (const line of css.split("\n")) {
    const match = line.match(/^(\.[a-zA-Z][\w-]*) \{$/);
    if (match) defined.add(match[1].slice(1));
  }
  assert.ok(defined.has("audit"), "바탕 규칙을 못 긁고 있다");

  const screen = read("js/admin-audit.js") + read("js/admin.js");
  const used = new Set();
  for (const match of screen.matchAll(/class="([^"'\\]+)"/g)) {
    for (const name of match[1].split(/\s+/)) if (name) used.add(name);
  }

  const missing = [...used].filter((name) => !defined.has(name)).sort();
  assert.deepEqual(missing, [], `모양 없이 뜰 클래스: ${missing.join(", ")}`);
});
