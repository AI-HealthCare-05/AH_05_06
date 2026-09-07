/* **한 화면이 쓰는 이름이 그 화면에 실려 있다.**
 *
 * `globals-collide.test.js` 는 같은 이름을 **두 번 얹는** 것을 잡는다. 그 짝이
 * 이것이다 — 이름을 **한 번도 안 얹는** 것.
 *
 * 실제로 그랬다. `e6c214c`(KEY-234)가 안내문 그리는 규칙을 `guide-view.js` 로
 * 옮기면서 `doctor.js` 의 `var GENDER_LABEL = {…}` 까지 함께 지웠는데, 쓰는
 * 자리(`renderHead`)는 남았다.
 *
 *     ReferenceError: GENDER_LABEL is not defined   at renderHead
 *
 * 그리고 그 자리를 감싼 `.catch` 가 그것을 **통신 오류로 오해해** 「안내문을
 * 불러오지 못했습니다」를 띄웠다. 서버는 멀쩡히 답하고 있었다. 의사 승인 화면이
 * 안내문 있는 진료를 **하나도 못 여는 채로 일주일**을 갔고, 어느 검사도 안
 * 걸렸다 — 화면 파일을 따로 읽으면 둘 다 멀쩡하기 때문이다.
 *
 * ## 왜 대문자 이름만 보나
 *
 * 전부를 재려면 파서가 필요하다. 대신 **이 저장소가 실제로 데인 모양** 하나를
 * 정확히 잡는다 — `SCREAMING_SNAKE` 로 쓰는 표·상수다. 옮기고 지우는 것이
 * 파일 단위라 함께 사라지기 쉽고, 사라지면 조용히 `ReferenceError` 다.
 *
 * 좁게 재는 대신 **거짓 경고가 없어야** 쓸모 있으므로, 글자열과 주석은 걷어
 * 내고 속성 접근(`a.NAME`)과 객체 키(`NAME:`)는 세지 않는다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { markupOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");

/** 브라우저·언어가 주는 대문자 이름. 화면이 얹지 않아도 있는 것들. */
const BUILT_IN = new Set(["JSON", "URL", "URLSearchParams", "NaN", "Infinity", "DOMParser", "Intl", "Math", "Promise"]);

function scriptsOf(page) {
  const html = markupOnly(fs.readFileSync(path.join(ROOT, page), "utf8"));
  return [...html.matchAll(/<script\s+src="\/js\/([\w-]+\.js)"/g)].map((m) => m[1]);
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
function bareCode(file) {
  const text = fs.readFileSync(path.join(ROOT, "js", file), "utf8");
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

function declaredIn(code) {
  const names = new Set();
  for (const m of code.matchAll(/(?:var|let|const|function)\s+([A-Za-z_$][\w$]*)/g)) names.add(m[1]);
  /* 함수 인자로 받은 대문자 이름도 그 파일 안에서는 있는 것이다. */
  for (const m of code.matchAll(/function\s*[\w$]*\s*\(([^)]*)\)/g)) {
    for (const part of m[1].split(",")) {
      const name = part.trim().split(/[\s=]/)[0];
      if (name) names.add(name);
    }
  }
  return names;
}

/** 그 파일이 **읽는** 대문자 이름 — 속성·객체 키는 뺀다. */
function usedIn(code) {
  const used = new Set();
  for (const m of code.matchAll(/(^|[^.\w$])([A-Z][A-Z0-9_]{2,})\b\s*(:)?/gm)) {
    if (m[3] === ":") continue; // 객체 키
    used.add(m[2]);
  }
  return used;
}

test("**화면이 쓰는 대문자 이름이 그 화면에 실려 있다**", () => {
  const pages = fs.readdirSync(ROOT).filter((n) => n.endsWith(".html"));
  assert.ok(pages.length >= 5, `화면 파일을 못 읽었다: ${pages.length}개`);

  const missing = [];
  for (const page of pages) {
    const files = scriptsOf(page);
    if (!files.length) continue;

    const known = new Set(BUILT_IN);
    const codes = new Map();
    for (const file of files) {
      const code = bareCode(file);
      codes.set(file, code);
      for (const name of declaredIn(code)) known.add(name);
    }

    for (const [file, code] of codes) {
      for (const name of usedIn(code)) {
        if (!known.has(name)) missing.push(`${page} · ${file} · ${name}`);
      }
    }
  }

  assert.deepEqual(missing, [], `그 화면에 없는 이름을 쓴다 (ReferenceError 로 죽는다):\n  ${missing.join("\n  ")}`);
});
