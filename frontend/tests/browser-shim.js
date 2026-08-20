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
function load(...files) {
  const store = new Map();

  const box = {
    console,
    URLSearchParams,
    Date,
    Math,
    JSON,
    Promise,
    setTimeout,
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
      search: "?mock=1",
      href: "http://test/patients.html?mock=1",
      pathname: "/patients.html",
    },

    sessionStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
      clear: () => store.clear(),
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
    document: {
      getElementById: () => stubElement(),
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
