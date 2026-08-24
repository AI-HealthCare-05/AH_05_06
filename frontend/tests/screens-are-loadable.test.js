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
  "upload.js": ["api", "session", "patients-api", "shell", "upload"],
  "doctor.js": ["api", "session", "patients-api", "shell", "doctor-api", "doctor"],
  "ocr-review.js": ["api", "session", "patients-api", "shell", "ocr-api", "ocr-review"],
  "checkin.js": ["api", "checkin-api", "checkin"],
};

for (const [file, files] of Object.entries(SCREENS)) {
  test(`${file} 는 화면 없이도 불려진다`, () => {
    assert.doesNotThrow(() => load(...files), `${file} 가 로드 중에 죽는다`);
  });
}

test("검사 대상 여섯이 실제로 그 파일들이다", () => {
  /* 목록이 비거나 파일명이 바뀌면 위 검사들이 조용히 사라진다. */
  const jsDir = path.join(__dirname, "..", "js");
  assert.strictEqual(Object.keys(SCREENS).length, 6);
  for (const file of Object.keys(SCREENS)) {
    assert.ok(fs.existsSync(path.join(jsDir, file)), `${file} 가 없다`);
  }
});

test("여섯 모두 자기 뿌리가 없으면 돌아간다", () => {
  /* 가드가 사라지면 검사 환경에서 그리기 시작하고, 껍데기가 던진다.
     위 `doesNotThrow` 가 그것을 잡지만, **왜** 통과하는지도 못 박아 둔다. */
  const jsDir = path.join(__dirname, "..", "js");
  const guarded = ["detail.js", "patients.js", "upload.js", "doctor.js", "ocr-review.js", "checkin.js"];
  for (const file of guarded) {
    const source = fs.readFileSync(path.join(jsDir, file), "utf8");
    assert.match(source, /if \(!document\.getElementById\("[\w-]+"\)\) return;/, `${file} 에 뿌리 가드가 없다`);
  }
});

test("shell.js 도 같은 규칙을 따른다", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "js", "shell.js"), "utf8");
  assert.match(source, /function bindShell\(\)/);
  assert.match(source, /if \(!document\.getElementById\("logout"\)\) return false;/);
});
