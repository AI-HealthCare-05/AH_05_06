/* 화면 파일 여섯이 **초기화 없이** 불려지는가 — KEY-158.
 *
 * 예전에는 최상위 또는 IIFE 안에서 곧장 DOM 을 잡고 그렸다. 그래서 검사기가
 * 파일을 부르면 그 자리에서 죽었고(`upload.js` 는 `render()` 를, `shell.js` 는
 * `getElementById("logout").addEventListener` 를 불렀다), 안에 있던 순수
 * 규칙도 함께 꺼낼 수 없었다.
 *
 * 지금은 자기 뿌리가 없으면 조용히 돌아간다. 검사 환경에는 그 칸이 없으므로
 * **화면은 초기화되지 않고 규칙만 남는다.**
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

/* 파일마다 함께 실어야 하는 것 — 브라우저의 `<script>` 차례와 같다. */
const SCREENS = {
  "detail.js": ["api", "session", "patients-api", "shell", "patients", "detail"],
  "patients.js": ["api", "session", "patients-api", "shell", "patients"],
  "doctor.js": ["api", "session", "patients-api", "shell", "doctor-api", "doctor"],
  "ocr-review.js": ["api", "session", "patients-api", "shell", "ocr-api", "ocr-review"],
  "checkin.js": ["api", "checkin-api", "checkin"],
};

for (const [file, files] of Object.entries(SCREENS)) {
  test(`${file} 는 화면 없이도 불려진다`, () => {
    assert.doesNotThrow(() => load(...files), `${file} 가 로드 중에 죽는다`);
  });
}

test("검사 대상 다섯이 실제로 그 파일들이다", () => {
  /* 목록이 비거나 파일명이 바뀌면 위 검사들이 조용히 사라진다. */
  const jsDir = path.join(__dirname, "..", "js");
  assert.strictEqual(Object.keys(SCREENS).length, 5);
  for (const file of Object.keys(SCREENS)) {
    assert.ok(fs.existsSync(path.join(jsDir, file)), `${file} 가 없다`);
  }
});

test("다섯 모두 자기 뿌리가 없으면 돌아간다", () => {
  /* 가드가 사라지면 검사 환경에서 그리기 시작하고, 껍데기가 던진다.
     위 `doesNotThrow` 가 그것을 잡지만, **왜** 통과하는지도 못 박아 둔다. */
  const jsDir = path.join(__dirname, "..", "js");
  const guarded = ["detail.js", "patients.js", "doctor.js", "ocr-review.js", "checkin.js"];
  for (const file of guarded) {
    const source = fs.readFileSync(path.join(jsDir, file), "utf8");
    assert.match(source, /if \(!document\.getElementById\("[\w-]+"\)\) return;/, `${file} 에 뿌리 가드가 없다`);
  }
});

/* 가드가 있어도 **그 id 가 다른 화면에도 있으면** 가드가 아니다.
   앞 검사는 가드의 **존재**만 본다 — 판별력은 id 가 고유해야 생긴다.

   실제로 `patients.js` 가 `view-register` 로 막고 있었는데, 그 id 는
   `doctor.html` · `ocr-review.html` 에도 `shell.js` 뷰 전환용 빈 스텁으로
   있었다. 그 두 화면에서 `patients.js` 를 부르면 가드가 통과해 초기화된다
   (이희진 님 `#103` 리뷰). */
const GUARD_ID = {
  "detail.js": "patient-facts",
  "patients.js": "find-form",
  "doctor.js": "approve",
  "ocr-review.js": "fields",
  "checkin.js": "form",
};

test("가드 id 는 그 화면에만 있다", () => {
  const htmlDir = path.join(__dirname, "..");
  const pages = fs.readdirSync(htmlDir).filter((name) => name.endsWith(".html"));
  assert.ok(pages.length >= 5, `화면 파일을 못 읽었다: ${pages.length}개`);

  for (const [file, id] of Object.entries(GUARD_ID)) {
    const found = pages.filter((page) =>
      fs.readFileSync(path.join(htmlDir, page), "utf8").includes(`id="${id}"`),
    );
    assert.deepStrictEqual(
      found.length,
      1,
      `${file} 의 가드 id "${id}" 가 ${found.length}개 화면에 있다: ${found.join(", ")}`,
    );
  }
});

test("검사에 적힌 가드 id 가 파일에 실제로 박혀 있다", () => {
  /* 위 표가 코드와 어긋나면 「고유한 id」를 재면서 **아무도 안 쓰는 id** 를
     재게 된다. 원문에서 확인한다. */
  const jsDir = path.join(__dirname, "..", "js");
  for (const [file, id] of Object.entries(GUARD_ID)) {
    const source = fs.readFileSync(path.join(jsDir, file), "utf8");
    assert.match(
      source,
      new RegExp(`if \\(!document\\.getElementById\\("${id}"\\)\\) return;`),
      `${file} 이 "${id}" 로 막지 않는다 — 위 표가 낡았다`,
    );
  }
});

test("다섯 파일 모두 꺼낼 수 있는 규칙을 하나 이상 갖는다", () => {
  /* `doctor.js` 는 가드만 붙고 순수 규칙이 **0개**였다. 파일은 불려도
     검사기가 아무것도 못 부르니, 인수조건(「분리된 순수 규칙을 vm 테스트에서
     불러올 수 있음」)을 형식적으로만 만족했다 (이희진 님 `#103` 리뷰). */
  const empty = [];
  for (const [file, files] of Object.entries(SCREENS)) {
    /* **그 파일이 더한 것만 센다.** 함께 실리는 `shell.js` · `*-api.js` 도
       전역에 함수를 얹으므로, 통째로 세면 화면 파일이 아무것도 안 내놔도
       목록이 비지 않는다 — 검사가 헛돈다. 빼고 한 번, 넣고 한 번 불러
       **차이**를 본다. */
    const without = new Set(Object.keys(load(...files.slice(0, -1))));
    const added = Object.keys(load(...files)).filter(
      (name) => !without.has(name) && typeof load(...files)[name] === "function",
    );
    if (added.length === 0) empty.push(file);
  }
  assert.deepStrictEqual(empty, [], `순수 규칙을 하나도 안 내놓는 파일: ${empty.join(", ")}`);
});

test("shell.js 도 같은 규칙을 따른다", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "js", "shell.js"), "utf8");
  assert.match(source, /function bindShell\(\)/);
  assert.match(source, /if \(!document\.getElementById\("logout"\)\) return false;/);
});
