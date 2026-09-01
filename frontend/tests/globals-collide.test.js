/* **한 화면이 싣는 파일들이 같은 이름을 두 번 얹지 않는다.**
 *
 * 이 저장소의 화면 코드는 모듈이 아니다 — `<script src>` 로 그냥 실려서 전역에
 * 얹힌다. 그래서 **이름이 곧 자리**이고, 두 파일이 같은 이름을 선언하면 나중에
 * 실린 쪽이 앞의 것을 통째로 덮는다.
 *
 * 실제로 그랬다. `patients-api.js` 의 `MOCK_PATIENTS`(배열)를 `doctor-api.js`
 * 의 `MOCK_PATIENTS`(객체)가 덮어서, 목록 목업이 `.find is not a function` 으로
 * 죽었다. 화면은 「환자가 없습니다」만 띄웠고, 오류는 콘솔에만 있었다.
 *
 * 덮어쓰기는 **조용하다.** 어느 검사도 안 걸리고, 두 파일을 따로 읽으면 둘 다
 * 멀쩡하다. 같이 실었을 때만 드러난다 — 그래서 화면 단위로 잰다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { codeOnly, markupOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");

/** 그 화면이 싣는 스크립트를 실리는 차례대로. */
function scriptsOf(page) {
  const html = markupOnly(fs.readFileSync(path.join(ROOT, page), "utf8"));
  return [...html.matchAll(/<script\s+src="\/js\/([\w-]+\.js)"/g)].map((m) => m[1]);
}

/** 그 파일이 전역에 얹는 이름들 — 맨 왼쪽에서 시작하는 선언만 본다.
    함수 안의 `var` 는 들여쓰기가 있어 걸리지 않는다. */
function globalsOf(file) {
  const code = codeOnly(fs.readFileSync(path.join(ROOT, "js", file), "utf8"));
  const names = new Set();
  for (const m of code.matchAll(/^(?:var|let|const|function)\s+([A-Za-z_$][\w$]*)/gm)) {
    names.add(m[1]);
  }
  return names;
}

test("**한 화면 안에서 전역 이름이 겹치지 않는다**", () => {
  const pages = fs.readdirSync(ROOT).filter((n) => n.endsWith(".html"));
  assert.ok(pages.length >= 5, `화면 파일을 못 읽었다: ${pages.length}개`);

  const clashes = [];
  let checked = 0;

  for (const page of pages) {
    const scripts = scriptsOf(page).filter((f) => fs.existsSync(path.join(ROOT, "js", f)));
    if (scripts.length < 2) continue;
    checked += 1;

    const owner = new Map();
    for (const file of scripts) {
      for (const name of globalsOf(file)) {
        if (owner.has(name) && owner.get(name) !== file) {
          clashes.push(`${page}: ${name} — ${owner.get(name)} 을 ${file} 이 덮는다`);
        } else {
          owner.set(name, file);
        }
      }
    }
  }

  assert.ok(checked >= 3, `여러 파일을 싣는 화면을 못 찾았다: ${checked}개 — 검사가 헛돈다`);
  assert.deepEqual(
    [...new Set(clashes)],
    [],
    "전역 이름이 덮인다 — 나중에 실린 쪽이 이깁니다:\n  " + [...new Set(clashes)].join("\n  "),
  );
});

test("검사가 실제로 이름을 읽는다 — 못 읽으면 늘 초록이다", () => {
  /* 정규식이 어긋나 이름을 하나도 못 읽으면 위 검사가 조용히 통과한다.
     아는 이름 몇 개가 실제로 걸리는지 본다. */
  assert.ok(globalsOf("patients-api.js").has("MOCK_PATIENTS"), "목록 목업을 못 읽었다");
  assert.ok(globalsOf("doctor-api.js").has("MOCK_GUIDE_PATIENTS"), "의사 목업을 못 읽었다");
  assert.ok(globalsOf("shell.js").has("selectedVisit"), "함수 선언을 못 읽었다");

  /* 함수 **안**의 것은 안 읽어야 한다 — 전역이 아니다 */
  assert.ok(!globalsOf("shell.js").has("mine"), "함수 안의 이름까지 전역으로 센다");
});
