/* KEY-280 — 「진료기록」으로 보내는 자리가 그 칸이 사는 화면을 안 봤다.
 *
 * 「재업로드」 둘과 환자 등록 직후가 `/patients.html?tab=record` 로 보냈는데,
 * 그 칸의 집은 KEY-233 이후 `/ocr-review.html` 이다. 받는 `detail.js` 의 `TABS` 는
 * `/patients.html` 에 사는 칸만 추리므로 `record` 가 없고, `showTab` 첫 줄
 * 「모르는 이름이면 아무것도 하지 않는다」에 걸려 **조용히 기본정보가 남았다.**
 *
 * 그래서 여기서 재는 것은 문자열이 아니라 **목적지**다. 「`tab=record` 라고
 * 적혀 있는가」를 재는 검사였다면 이 결함을 지켜 주지 못했을 것이다 — 그 글자는
 * 처음부터 옳게 적혀 있었고, 틀린 것은 앞의 화면 이름이었다.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { read, codeOnly } = require("./source.js");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");
const VISIT = 37;

/* 세 자리가 각자 어느 칸에 서서 부르는가 — 실제 코드와 같은 인자를 넘긴다. */
const CALLERS = [
  { what: "안내문 화면의 재업로드", from: "guide", page: "/patients.html" },
  { what: "환자 등록 직후", from: "basic", page: "/patients.html" },
  { what: "주소로 들어온 진료", from: null, page: "/patients.html" },
];

test("① 어느 자리에서 부르든 진료기록은 판독 화면으로 간다", () => {
  const { stepHref } = load("step-nav");

  for (const caller of CALLERS) {
    const href = stepHref("record", caller.from, caller.page, VISIT);
    assert.equal(
      href,
      `/ocr-review.html?visit=${VISIT}&tab=record`,
      `${caller.what} 가 엉뚱한 곳으로 보낸다 — ${href}`,
    );
  }
});

test("② 이 화면에 사는 칸은 주소를 안 만든다 — 탭으로 옮길 자리다", () => {
  /* 받는 쪽(`openRow`)이 이 `null` 로 「여기 있는 칸이다」를 판별한다.
     여기가 주소를 내주기 시작하면 기본정보를 누를 때마다 화면을 새로 받는다. */
  const { stepHref } = load("step-nav");

  for (const key of ["basic", "guide", "final", "status"]) {
    assert.equal(
      stepHref(key, null, "/patients.html", VISIT),
      null,
      `${key} 는 /patients.html 에 사는데 주소를 만들었다`,
    );
  }
});

test("③ 진료기록으로 가는 주소를 화면들이 각자 짓지 않는다", () => {
  /* **이 검사가 재발을 막는 축이다.** 세 자리가 각자 주소를 지었기 때문에 칸이
     옮겨졌을 때 세 곳이 함께 낡았고, 셋 다 조용히 틀렸다.

     `record` 로 좁혀 잰다. 이 저장소에는 `tab=basic`·`tab=guide` 를 손으로 짓는
     자리가 셋 더 있는데(`schedule-rules.js` · `ocr-groups.js` · `roster-rules.js`)
     그 둘은 아직 `/patients.html` 에 살아서 **지금은 맞다.** 맞는 것을 이 PR 에서
     함께 끌고 가지 않는다 — 다만 같은 위험을 안고 있다는 것은 PR 에 적는다. */
  const built = [];
  for (const name of fs.readdirSync(path.join(ROOT, "js")).filter((f) => f.endsWith(".js"))) {
    if (name === "step-nav.js") continue; // 짓는 일을 맡은 곳
    if (/["'][^"']*[?&]tab=record/.test(codeOnly(read(`js/${name}`)))) built.push(name);
  }
  assert.deepEqual(built, [], `진료기록 주소를 손으로 짓는다 — ${built.join(", ")}`);
});

test("④ 세 자리가 모두 step-nav 에 물어본다", () => {
  const sites = [
    ["js/visit-guide.js", 'closest("#guide-reupload")', "안내문 화면의 재업로드"],
    ["js/shell.js", "picked = selectedVisit", "환자 등록 직후"],
    ["js/shell.js", "function openRow", "주소로 들어온 진료"],
  ];

  for (const [file, anchor, what] of sites) {
    const code = codeOnly(read(file));
    const at = code.indexOf(anchor);
    assert.notEqual(at, -1, `${what} 자리를 못 찾았다 (${anchor})`);
    assert.match(
      code.slice(at, at + 900),
      /stepHref\(/,
      `${what} 가 목적지를 스스로 정한다 — 칸이 옮겨지면 또 낡는다`,
    );
  }
});

test("⑤ 판독 화면의 재업로드는 나가지 않고 제자리에서 판을 편다", () => {
  /* 「진료기록」의 집이 이 화면이다. 이미 여기 있는데 나갔다 오면 보던 것을 잃는다.
     예전 주석은 「실패 화면에서는 #work 가 숨겨져」라고 적었는데, 지금
     `job_failed` 는 `keepsWork: true` 라 그 판이 살아 있다. */
  const code = codeOnly(read("js/ocr-review.js"));
  const at = code.indexOf('target.id === "reupload"');
  assert.notEqual(at, -1, "재업로드를 받는 자리가 없다");

  const around = code.slice(at, at + 400);
  assert.doesNotMatch(around, /location\.href/, "제자리에 있으면서 화면을 새로 받는다");
  assert.match(around, /ocrRequestUpload\(\)/, "올리는 판을 안 편다");

  assert.match(
    code,
    /job_failed:\s*\{[^}]*keepsWork:\s*true/,
    "판독 실패에서 #work 가 접히면 제자리에서 펼 판이 없다 — 나가는 쪽으로 되돌려야 한다",
  );
});

test("⑤' 판을 못 펴면 아무 일도 안 일어나는 채로 두지 않는다", () => {
  /* `ocrRequestUpload` 는 `wireAddPanel()` 안에서만 정의되는데, 그 함수는 판을
     이루는 다섯 칸 중 하나라도 없으면 조용히 돌아간다. 지금은 다섯이 항상
     마크업에 있어 안 걸리지만, 이 판을 조건부로 그리게 되면 재업로드가 **이 PR 이
     고치려던 것과 똑같이** 다시 죽은 단추가 된다 (#241 이희진 ②). */
  const code = codeOnly(read("js/ocr-review.js"));
  const at = code.indexOf('target.id === "reupload"');
  const branch = code.slice(at, code.indexOf("\n    }", at));

  assert.match(branch, /typeof ocrRequestUpload === "function"/, "함수가 없을 때를 안 가린다");
  assert.match(branch, /textContent\s*=/, "못 펴는 경우에 아무 말도 안 한다");

  /* 그 말이 사람이 할 일을 담아야 한다 — 「안 됩니다」만으로는 갇힌다. */
  const said = branch.match(/textContent\s*=\s*"([^"]+)"/);
  assert.ok(said, "적는 문구를 못 찾았다");
  assert.match(said[1], /새로 고/, `다음에 무엇을 하라는 말이 없다 — ${said[1]}`);
});

test("⑥ 손으로 누른 판 펴기는 접지도, 초점을 두고 가지도 않는다", () => {
  /* 저절로 부르는 `ocrOpenAddPanel` 은 (ⓐ 펴져 있으면 아무 일도 안 하고
     ⓑ 초점을 안 옮긴다) — 화면에 막 들어온 참이라 둘 다 맞다. 눌러 온 사람에게는
     둘 다 틀리다: 죽은 단추가 되고, 올릴 자리를 한 번 더 찾아야 한다. */
  const code = codeOnly(read("js/ocr-review.js"));
  const at = code.indexOf("window.ocrRequestUpload");
  assert.notEqual(at, -1, "손누름용 진입점이 없다");

  /* **함수 본문까지만 본다** — 고정 길이로 자르면 바로 아래 `#add-doc` 처리기의
     `panel.hidden`(그쪽은 접었다 펴는 것이 맞다)을 삼켜서 엉뚱한 것을 보고 운다. */
  const body = code.slice(at, code.indexOf("};", at));
  assert.match(body, /openPanel\(true,\s*true\)/, "접거나(toggle) 초점을 두고 간다");
  assert.doesNotMatch(body, /panel\.hidden/, "이미 펴져 있으면 아무 일도 안 하는 죽은 단추다");

  /* 저절로 부르는 쪽은 그대로 남아야 한다 — 등록 직후 도착하는 길이 그것이다. */
  assert.match(code, /window\.ocrOpenAddPanel\s*=/, "저절로 펴는 함수가 사라졌다");
});
