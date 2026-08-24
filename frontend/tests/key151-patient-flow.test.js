/* KEY-151 실제 환자 화면이 개발 링크 토큰 계약을 사용하는가. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const JS_DIR = path.join(__dirname, "..", "js");

function storage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
  };
}

test("승인 안내 화면은 visit_id가 아니라 개발 링크 토큰으로 조회한다", async () => {
  let requested = null;
  const box = storage();
  const context = vm.createContext({
    URLSearchParams,
    sessionStorage: box,
    window: { location: { search: "" } },
    fetch(url) {
      requested = url;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ sections: [{ key: "medication", body: "합성 승인 문구" }] }),
      });
    },
    setTimeout,
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "guide-api.js"), "utf8"), context);

  const result = await context.fetchGuide("synthetic token");

  assert.equal(requested, "/api/v1/guides/synthetic%20token");
  assert.deepEqual(JSON.parse(JSON.stringify(result.sections)), [{ key: "medication", body: "합성 승인 문구" }]);
});

test("D+7 실제 저장은 확정 범위인 복약·통증만 서버에 보낸다", async () => {
  let call = null;
  const context = vm.createContext({
    MOCK: false,
    URLSearchParams,
    location: { search: "" },
    localStorage: storage(),
    sessionStorage: storage(),
    request(url, options) {
      call = { url, options };
      return Promise.resolve({ saved: true });
    },
    crypto: { randomUUID: () => "synthetic-id" },
    setTimeout,
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "checkin-api.js"), "utf8"), context);

  await context.checkinApi.save("synthetic token", {
    medication: "taking",
    pain: { had: false, score: null, types: [] },
    note: "KEY-151 범위 밖",
    client_id: "ignored",
  });

  assert.equal(call.url, "/checkins/synthetic%20token");
  assert.deepEqual(JSON.parse(JSON.stringify(call.options.body)), {
    medication: "taking",
    pain: { had: false, score: null, types: [] },
  });
});

test("실제 승인 안내의 응급 섹션은 기존 위험 강조 블록을 재사용한다", () => {
  function node(tag) {
    return {
      tag,
      children: [],
      appendChild(child) {
        this.children.push(child);
        return child;
      },
      addEventListener() {},
    };
  }
  const context = vm.createContext({
    document: {
      addEventListener() {},
      createElement: node,
      createDocumentFragment: () => node("fragment"),
    },
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "guide.js"), "utf8"), context);

  const danger = context.renderEmergency(["합성 응급 문구"]);

  assert.equal(danger.className, "card card--danger");
  assert.equal(danger.children[0].textContent, "⚠");
  assert.equal(danger.children[1].textContent, "🚨 바로 병원에 연락하세요");
  assert.equal(danger.children[2].children[0].textContent, "합성 응급 문구");
  assert.equal(danger.children[3].textContent, "💬 문의하기");
});

test("D+7 결과에 다음 진료 값이 없으면 빈 항목을 만들지 않는다", () => {
  const source = fs.readFileSync(path.join(JS_DIR, "checkin.js"), "utf8");

  assert.match(
    source,
    /result\.next_visit\s*\?\s*"<dt>다음 진료<\/dt><dd>"[\s\S]*?:\s*""/,
    "next_visit null 가드가 없어 빈 다음 진료 행이 노출된다",
  );
});
