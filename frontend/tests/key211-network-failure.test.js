/* KEY-211 — `fetch` 가 거절한 것을 화면이 알아볼 수 있게 한다.
 *
 * HTTP 응답이 온 오류는 서버가 `status` 와 `code` 를 준다. 그런데 오프라인 ·
 * DNS 실패 · 연결 끊김은 `fetch` **자체**가 거절하고, 브라우저가 주는 것은
 * `.status` 도 `.code` 도 없는 날것 `TypeError` 다. 그래서 화면은 「서버가 거절했다」와
 * 「서버에 닿지도 못했다」를 구별할 수 없었다.
 *
 * **여기서는 흉내내지 않고 실제로 거절시킨다.** 「문구 표에 `status: 0` 규칙이
 * 있는가」를 재는 검사는 #162 가 이미 겪었다 — 규칙은 있는데 한 번도 안 걸렸고,
 * 그 검사는 그 사실을 못 봤다. 그래서 여기서는 `fetch` 를 거절시켜 **끝까지
 * 흘려 보고** 화면이 무슨 말을 하는지까지 본다.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "js");

/* `api.js` 만 세운다 — 목업 배너·세션 저장소가 없어도 뜨게 하는 최소한. */
function apiWith(fetchImpl, extras) {
  const context = {
    Promise,
    String,
    Number,
    Object,
    JSON,
    Error,
    TypeError,
    console,
    fetch: fetchImpl,
    location: { search: "", hostname: "localhost", protocol: "http:", pathname: "/" },
    document: {
      getElementById: () => null,
      addEventListener() {},
      createElement: () => ({ style: {}, classList: { add() {} }, appendChild() {}, setAttribute() {} }),
      body: { appendChild() {} },
    },
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  };
  Object.assign(context, extras || {});
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(JS, "api.js"), "utf8"), context);
  return context;
}

/** 서버가 답한 오류를 흉내낸다 — 본문과 상태를 그대로 준다. */
function answering(status, body) {
  return async () => ({
    ok: false,
    status,
    headers: { get: () => null },
    json: async () => body,
  });
}

test("① fetch 가 거절하면 화면은 ApiError 를 받는다 — 날것 TypeError 가 아니라", async () => {
  const api = apiWith(async () => {
    throw new TypeError("Failed to fetch");
  });

  const error = await api.request("/anything").then(
    () => null,
    (e) => e,
  );

  assert.ok(error, "거절하지 않았다");
  assert.equal(error.name, "ApiError", `날것이 올라온다 — ${error && error.constructor && error.constructor.name}`);
  assert.equal(error.status, 0, "status 가 0 이 아니라 화면의 status 규칙에 안 걸린다");
  assert.equal(error.code, api.NETWORK_ERROR_CODE, "code 가 정해진 값이 아니다");
});

test("② 브라우저가 뭐라고 하든 그 문장을 싣지 않는다", () => {
  /* 브라우저마다 말이 다르고(`Failed to fetch` · `NetworkError when attempting…`),
     무엇보다 그 문장이 **주소를 담을 수 있다.** 화면에 올리지 않는다. */
  const code = fs.readFileSync(path.join(JS, "api.js"), "utf8");
  const at = code.indexOf("NETWORK_ERROR_CODE, 0");
  assert.notEqual(at, -1, "네트워크 실패를 정규화하는 자리가 없다");

  const around = code.slice(Math.max(0, at - 400), at + 100);
  assert.doesNotMatch(around, /error\.message/, "브라우저 원문을 실어 보낸다");
});

test("③ 서버가 답한 오류는 그대로 남는다 — 정규화가 삼키지 않는다", async () => {
  const api = apiWith(answering(422, { code: "OCR_NOT_CONFIRMED" }));

  const error = await api.request("/guides").then(
    () => null,
    (e) => e,
  );

  assert.equal(error.status, 422, "서버가 준 status 를 잃었다");
  assert.equal(error.code, "OCR_NOT_CONFIRMED", "서버가 준 code 를 잃었다");
});

test("④ 성공은 그대로 성공이다", async () => {
  const api = apiWith(async () => ({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => ({ hello: "there" }),
  }));

  assert.deepEqual(await api.request("/ok"), { hello: "there" });
});

test("⑤ session.js 를 안 싣는 화면에서도 동기로 터지지 않는다", async () => {
  /* **환자 체크인(`checkin.html`)이 그 조합이다** — 의료진 세션 없이 링크 토큰으로
     들어오므로 `session.js` 를 안 싣는다. 그런데 `request()` 가 `session.token()` 을
     곧장 부르면 `ReferenceError` 가 나고, 그건 프라미스 거절이 아니라 **동기 예외**라
     부르는 쪽의 `.catch` 가 아예 안 걸린다. 환자는 내용이 빈 반쪽 화면을 보고,
     왜 안 되는지는 콘솔에만 남는다. */
  const api = apiWith(async () => {
    throw new TypeError("Failed to fetch");
  });
  assert.equal(typeof api.session, "undefined", "이 검사가 세우려던 상황이 아니다");

  let thrown = null;
  let rejected = null;
  try {
    rejected = await api.request("/checkins/token").then(
      () => null,
      (e) => e,
    );
  } catch (error) {
    thrown = error;
  }

  assert.equal(thrown, null, `동기로 터진다 — ${thrown && thrown.message}. 화면의 .catch 가 안 걸린다`);
  assert.equal(rejected && rejected.status, 0, "거절은 했는데 화면이 알아볼 모양이 아니다");
});

test("⑥ 세 화면이 「닿지 못했다」와 「거절당했다」를 다르게 말한다", () => {
  /* 문구 표에 규칙이 있는지가 아니라 **무슨 말이 나오는지**를 본다. */
  const { load } = require("./browser-shim.js");

  const cases = [
    ["안내문 생성", load("api", "ocr-review").generateFailureSaying],
    ["안내문 불러오기", load("api", "session", "patients-api", "shell", "doctor-api", "doctor").guideLoadSaying],
  ];

  for (const [what, saying] of cases) {
    const offline = saying({ code: "NETWORK_UNREACHABLE", status: 0 });
    const refused = saying({ code: "FORBIDDEN", status: 403 });
    const unknown = saying({ code: "something-else", status: 500 });

    assert.match(offline, /닿지 못했습니다/, `${what} 가 네트워크 실패를 안 알아본다 — ${offline}`);
    assert.notEqual(offline, refused, `${what} 가 거절과 단절을 같은 말로 한다`);
    assert.notEqual(offline, unknown, `${what} 가 단절을 기본 문구로 뭉갠다`);
  }
});

test("⑦ 그 문장을 화면마다 따로 적지 않는다", () => {
  /* 같은 말을 네 곳에 두면 한쪽만 고쳐지고, 그 어긋남은 사람이 오류를 만났을 때
     드러난다 — 가장 나쁜 때다. */
  const said = [];
  for (const name of fs.readdirSync(JS).filter((f) => f.endsWith(".js") && f !== "api.js")) {
    if (/["'][^"']*닿지 못했습니다/.test(fs.readFileSync(path.join(JS, name), "utf8"))) said.push(name);
  }
  assert.deepEqual(said, [], `문장을 손으로 옮겨 적은 파일이 있다 — ${said.join(", ")}`);
});
