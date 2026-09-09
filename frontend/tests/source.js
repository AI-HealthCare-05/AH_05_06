/* **원문을 읽는 도구.**
 *
 * 화면을 그리는 코드는 shim 아래서 안 돌기 때문에, 어떤 것들은 원문으로 잴
 * 수밖에 없다 (「이 함수를 실제로 쓰는가」 같은 것). 그때 **주석에 적힌 말이
 * 코드로 세어지는** 함정에 여러 번 걸렸다:
 *
 *   · `document_type` 을 안 보낸다는 것을 확인하려는데 내 주석에 그 낱말이
 *     있어서 통과했다
 *   · `tab--later` 를 안 쓴다는 것을 확인하려는데 HTML 주석에 있었다
 *   · `/documents` 로 보내는 자리를 세려는데 주석의 `app/documents/api.py`
 *     가 걸렸다 — 줄이 `(` 로 시작해서 「주석 줄」로 안 걸러졌다
 *
 * 앞의 둘은 줄 첫 글자만 봐도 걸러졌지만, 셋째는 **여러 줄 주석의 가운데
 * 줄**이라 안 걸러진다. 그래서 여기서는 여러 줄 주석의 시작과 끝을 실제로
 * 따라간다.
 *
 * (이 주석 자체도 한 번 걸렸다 — 안에 주석 닫는 기호를 그대로 적었더니
 *  거기서 주석이 끝나고 파일이 깨졌다.)
 */
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/** **주석만** 걷는다. 주석 자리는 빈칸으로 채워 줄 수를 지킨다.
 *
 * 여기는 **글자열을 모른다** — `"https://…"` 의 `//` 를 주석 시작으로 본다.
 * 글자열 안의 낱말까지 세면 안 되는 자리에는 아래 `bareCode` 를 쓴다.
 * (이 주석이 「주석과 문자열 밖의 코드만 남긴다」라고 적혀 있었다 — 사실이
 *  아니라서 고쳤다. `#249` 리뷰 ②를 파다 나온 것이다.) */
function codeOnly(text) {
  let out = "";
  let i = 0;
  const n = text.length;

  while (i < n) {
    const two = text.slice(i, i + 2);

    if (two === "/*") {
      const end = text.indexOf("*/", i + 2);
      const stop = end === -1 ? n : end + 2;
      /* 줄바꿈은 남긴다 — 줄 번호로 짚는 검사가 어긋나지 않게 */
      out += text.slice(i, stop).replace(/[^\n]/g, " ");
      i = stop;
      continue;
    }

    if (two === "//") {
      const end = text.indexOf("\n", i);
      const stop = end === -1 ? n : end;
      out += " ".repeat(stop - i);
      i = stop;
      continue;
    }

    out += text[i];
    i += 1;
  }
  return out;
}

/* 글자열도 주석도 걷어 낸 코드.
 *
 * **`codeOnly` 를 안 쓴다.** 그쪽은 글자열을 모른다 — `"https://…"` 의 `//` 를
 * 주석 시작으로 보고 그 줄 끝까지 삼키고, 그러다 뒤엣것의 `/*` 짝이 어긋나
 * **진짜 주석이 코드로 남는다.** 실제로 `ocr-review.js` 의 주석 속
 * 「MEDICATION_NAME」이 그렇게 새어 나왔다.
 *
 * 여기서는 한 번만 훑으며 상태를 들고 간다 — 글자열 안의 `//` 는 주석이
 * 아니고, 주석 안의 따옴표는 글자열이 아니다.
 */
function bareCode(text) {
  let out = "";
  let i = 0;

  while (i < text.length) {
    const two = text.slice(i, i + 2);

    if (two === "/*") {
      const end = text.indexOf("*/", i + 2);
      const stop = end === -1 ? text.length : end + 2;
      out += text.slice(i, stop).replace(/[^\n]/g, " ");
      i = stop;
      continue;
    }
    if (two === "//") {
      const end = text.indexOf("\n", i);
      const stop = end === -1 ? text.length : end;
      out += " ".repeat(stop - i);
      i = stop;
      continue;
    }

    /* 정규식 리터럴도 글자열이다 — `/^MEDICATION_NAME(_\\d+)?$/` 안의 이름을
       「이 파일이 쓰는 이름」으로 세면 안 된다. 나눗셈과 가르는 규칙은 앞의
       마지막 글자다: 값이 올 자리(`(`, `=`, `,`, `return` …)면 정규식이다. */
    if (text[i] === "/") {
      const before = out.replace(/\s+$/, "");
      const last = before.slice(-1);
      const opensValue = last === "" || "(,=:[!&|?{};+-*%~^".includes(last) || /\breturn$/.test(before);
      if (opensValue) {
        let j = i + 1;
        let inClass = false;
        while (j < text.length) {
          if (text[j] === "\\") j += 2;
          else if (text[j] === "[") (inClass = true), (j += 1);
          else if (text[j] === "]") (inClass = false), (j += 1);
          else if (text[j] === "/" && !inClass) break;
          else if (text[j] === "\n") break; // 정규식이 아니었다
          else j += 1;
        }
        if (text[j] === "/") {
          out += text.slice(i, j + 1).replace(/[^\n]/g, " ");
          i = j + 1;
          continue;
        }
      }
    }

    const quote = text[i];
    if (quote === '"' || quote === "'" || quote === "`") {
      let j = i + 1;
      while (j < text.length && text[j] !== quote) {
        if (text[j] === "\\") j += 1;
        if (quote !== "`" && text[j] === "\n") break; // 안 닫힌 따옴표에 끌려가지 않는다
        j += 1;
      }
      out += text.slice(i, j + 1).replace(/[^\n]/g, " ");
      i = j + 1;
      continue;
    }

    out += text[i];
    i += 1;
  }
  return out;
}

/** HTML 주석을 뺀다. 같은 함정이 화면 파일에도 있다. */
function markupOnly(text) {
  return text.replace(/<!--[\s\S]*?-->/g, (m) => m.replace(/[^\n]/g, " "));
}

/** CSS 규칙 하나를 통째로. `.list__head` 를 찾다가 `.list--folded .list__head`
    에 걸린 적이 있어, **줄 처음에 오는** 선택자만 본다. */
function rule(css, selector) {
  const lines = css.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line !== selector + " {" && line !== selector + ",") continue;
    let j = i;
    while (j < lines.length && !lines[j].includes("{")) j += 1;
    const open = css.indexOf("{", lines.slice(0, j).join("\n").length);
    return css.slice(open, css.indexOf("}", open));
  }
  throw new Error(`${selector} 규칙이 없다 — 검사가 헛돈다`);
}

/** 그 화면이 싣는 `/js/*.js` 목록 — 실린 차례 그대로.
 *
 * `globals-defined` · `globals-collide` 두 검사에 **글자까지 같은 사본**이
 * 있었다 (`#249` 리뷰 ①). 스크립트 태그 모양이 바뀌는 날 한쪽만 고쳐진다.
 */
function scriptsOf(page) {
  const html = markupOnly(read(page));
  return [...html.matchAll(/<script\s+src="\/js\/([\w-]+\.js)"/g)].map((m) => m[1]);
}

/** 화면 목록표(`js/frames.js`)를 실제로 돌려 그 전역을 준다.
 *
 * `key234-frame-manifest` 와 `key218-status-doc` 두 검사에 **글자까지 같은
 * 사본**이 있었다 (2heej 님 `#276` 리뷰 ③). `scriptsOf` 를 여기로 모은 것과
 * 같은 자리다 — 표를 싣는 방법이 바뀌는 날 한쪽만 고쳐진다.
 *
 * 원문 대조가 아니라 **돌려서** 본다. `FRAMES` 는 배열 리터럴이지만
 * `needsGuideScreen` 같은 판단은 식이라, 글자로는 못 잰다.
 */
function loadFrames() {
  const context = { console };
  vm.createContext(context);
  vm.runInContext(read("js/frames.js"), context);
  return context;
}

module.exports = { read, codeOnly, bareCode, markupOnly, scriptsOf, rule, loadFrames };
