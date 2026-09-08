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
const { read, bareCode, scriptsOf } = require("./source.js");

const ROOT = path.join(__dirname, "..");

/** 브라우저·언어가 주는 대문자 이름. 화면이 얹지 않아도 있는 것들. */
const BUILT_IN = new Set(["JSON", "URL", "URLSearchParams", "NaN", "Infinity", "DOMParser", "Intl", "Math", "Promise"]);

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
      const code = bareCode(read(path.join("js", file)));
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
