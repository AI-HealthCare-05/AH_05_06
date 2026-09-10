/* KEY-151 실제 환자 화면이 개발 링크 토큰 계약을 사용하는가. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { read } = require("./source.js");

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

/* 「승인 안내 화면이 토큰으로 조회한다」는 실리는 파일에서 잰다 —
   `key241-patient-guide-api.test.js` 가 같은 주소(`encodeURIComponent`)를
   확인한다. 여기 있던 판은 아무 화면도 안 싣는 `js/guide-api.js` 를
   돌리고 있었다 (KEY-281 이 남긴 처분). */


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
  /* **실리는 파일에서 잰다.** 전에는 `js/guide.js` 의 `renderEmergency` 를
     vm 으로 돌렸는데, 그 파일은 아무 화면도 안 싣는 고아였다 (KEY-281).
     지금 실리는 렌더러는 IIFE 안이라 함수만 떼어 돌릴 수 없어 원문으로 본다 —
     응급 문구가 **위험 강조 카드**로 뜨는가, 그 문장이 환자가 보는 것과 같은가.

     그때 함께 재던 「⚠」와 「💬 문의하기」는 지금 화면에 없다. 문의는 창구
     계약이 없어 KEY-259 가 걷었고, 여기서 되살리면 없는 것을 지키게 된다. */
  const js = read("patient_wireframe/js/guide.js");
  const at = js.indexOf("if (c.danger.length)");
  assert.notStrictEqual(at, -1, "응급 블록을 못 찾았다 — 검사가 헛돈다");

  const block = js.slice(at, at + 500);
  assert.match(block, /'card card--danger'/, "응급 문구가 위험 강조 카드로 안 뜬다");
  assert.match(block, /🚨 바로 병원에 연락하세요/, "환자가 보는 문장이 다르다");
});

test("D+7 결과에 다음 진료 값이 없으면 빈 항목을 만들지 않는다", () => {
  const source = fs.readFileSync(path.join(JS_DIR, "checkin.js"), "utf8");

  assert.match(
    source,
    /result\.next_visit\s*\?\s*"<dt>다음 진료<\/dt><dd>"[\s\S]*?:\s*""/,
    "next_visit null 가드가 없어 빈 다음 진료 행이 노출된다",
  );
});
