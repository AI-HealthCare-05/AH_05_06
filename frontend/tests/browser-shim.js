/* 브라우저가 주는 것 중 **화면 파일이 불리는 데 꼭 필요한 만큼만** 흉내낸다.
 *
 * 프런트 코드는 빌드가 없다. `<script src>` 로 그냥 실려서 전역에 함수를 얹는
 * 구조라, Node 에서 부르려면 `document` 같은 것이 있어야 한다.
 *
 * **여기서 흉내내는 것을 늘리지 않는다.** 껍데기가 커질수록 「검사에서는 되는데
 * 브라우저에서는 안 되는」 거리가 벌어진다. 지금 담은 것은 **파일이 로드만
 * 되게** 하는 최소한이고, 검사는 그 뒤에 꺼낸 **순수 함수**만 부른다.
 * 화면을 그리는 함수(`renderRows` 등)는 여기서 검사하지 않는다 — 그건 브라우저가
 * 할 일이고, 껍데기로 흉내내면 거짓 초록불이 된다.
 */

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS_DIR = path.join(__dirname, "..", "js");

function stubElement() {
  const el = { addEventListener() {}, appendChild() {}, remove() {}, style: {}, dataset: {}, hidden: false };
  for (const key of ["innerHTML", "textContent", "value"]) {
    Object.defineProperty(el, key, {
      get: () => "",
      set() {
        throw new Error(
          `검사에서 화면을 그리려 했습니다 (${key}). 이 껍데기는 순수 함수만 위한 것이고, ` +
            "그리는 것은 브라우저에서 눈으로 확인합니다.",
        );
      },
    });
  }
  return el;
}

/** 화면 파일들을 한 상자에 실어서 그 상자를 돌려준다. */
/* 마지막 인자가 문자열이 아니면 **설정**으로 본다 — `{ search: "?mock=1&case=forbidden" }`.
   목업의 갈래(`MOCK_CASE`)는 파일이 불릴 때 한 번 읽히므로, 검사가 그 뒤에
   `sessionStorage` 를 만져도 늦다. 갈래별 검사를 쓰려면 여기서 정해야 한다. */
function load(...files) {
  const options = typeof files[files.length - 1] === "object" ? files.pop() : {};
  const store = new Map();
  const persistent = new Map();

  const box = {
    console,
    URLSearchParams,
    Date,
    Math,
    JSON,
    Promise,
    /* 목업 API 가 호출마다 실제로 180ms 를 기다린다. 검사가 늘수록 CI 시간이
       그만큼 선형으로 는다 — 지금 재는 것은 **계약 규칙이지 타이밍이 아니다.**
       (이희진 님 `#64` 리뷰)

       기다림만 없앤다. **동기로 바꾸지는 않는다** — 즉시 실행으로 만들면
       `setTimeout` 으로 다음 순번을 잡는 코드(`ocr-review.js` 의 폴링 같은)가
       그 자리에서 무한히 돈다. 0ms 로 미루면 비동기 차례는 그대로 지킨다. */
    setTimeout: (fn, _ms, ...rest) => setTimeout(fn, 0, ...rest),
    clearTimeout,
    setInterval,
    clearInterval,
    isNaN,
    Number,
    String,
    Object,
    Array,

    /* `?mock=1` 로 목업을 켠다. 검사는 서버 없이 도는 것이 목적이라 늘 켠 채로
       불린다 — 실제 요청이 나가면 그건 목업 분기가 깨졌다는 뜻이고, `fetch` 가
       없어 바로 터진다. 조용히 통과하는 것보다 낫다. */
    location: {
      search: options.search || "?mock=1",
      href: "http://test/patients.html" + (options.search || "?mock=1"),
      pathname: "/patients.html",
      hostname: options.hostname || "localhost",
      protocol: options.protocol || "http:",

      /* `session.js` 의 `bounce()` 가 부른다. 없으면 `TypeError` 가 나는데,
         `requireSession().catch(function(){})` 가 조용히 삼켜서 **검사는 그냥
         통과한다**. 나중에 로그아웃·세션만료 경로를 검사로 덮을 때 뜬금없는
         오류로 죽거나 또 삼켜져 거짓 통과가 된다 — 이희진 님이 `#64` 리뷰에서
         짚어 주신 자리다.

         던지지 않고 **어디로 보내려 했는지 적어 둔다.** 검사가 「만료되면
         /login.html 로 보낸다」를 확인할 수 있게. */
      replace: (url) => box.location.replaced.push(String(url)),
      replaced: [],
    },

    sessionStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
      clear: () => store.clear(),
    },

    /* `session.js` 의 `clear()` 가 「예전 판이 남겨 둔 것」을 걷어내려고
       부른다(`localStorage.removeItem`). **`sessionStorage` 와 다른 저장소라
       같은 `store` 를 쓰면 안 된다** — 하나를 지웠는데 다른 쪽도 지워지면
       「토큰을 세션에만 둔다」는 규칙을 검사가 확인할 수 없게 된다. */
    localStorage: {
      getItem: (k) => (persistent.has(k) ? persistent.get(k) : null),
      setItem: (k, v) => persistent.set(k, String(v)),
      removeItem: (k) => persistent.delete(k),
      clear: () => persistent.clear(),
    },

    /* 리스너는 걸리되 **그리기는 터지는** 문서.
     *
     * `shell.js` 는 최상위에서 `getElementById(...).addEventListener(...)` 를
     * 여섯 번 부른다. 그걸 막으면 파일 자체가 안 불려서 `stateClass` 같은
     * 순수 함수도 못 꺼낸다.
     *
     * 그래서 **리스너 등록만** 통과시키고, `innerHTML` · `textContent` 에
     * 값을 넣으려 하면 던진다. 화면을 그리는 함수를 검사에서 부르면 조용히
     * 통과하는 대신 그 자리에서 죽는다 — 「검사가 화면까지 본다」는 착각이
     * 제일 비싸다. 화면은 브라우저에서 눈으로 본다. */
    /* `upload.js` 가 최상위에서 `window.addEventListener` 를 부른다 — 끌어다
       놓기를 창 전체에서 막는 자리다. 없으면 파일이 아예 안 실려서 순수
       규칙도 못 꺼낸다. **등록만 받고 아무것도 하지 않는다** — 여기서 이벤트를
       흉내내기 시작하면 껍데기가 브라우저 흉내로 자라난다. */
    window: {
      addEventListener: () => {},
      removeEventListener: () => {},
    },

    document: {
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener: () => {},
      createElement: () => stubElement(),
      body: { appendChild() {}, removeChild() {} },
    },
  };

  const ctx = vm.createContext(box);
  for (const name of files) {
    const file = path.join(JS_DIR, `${name}.js`);
    vm.runInContext(fs.readFileSync(file, "utf8"), ctx, { filename: file });
  }
  return ctx;
}

module.exports = { load };
