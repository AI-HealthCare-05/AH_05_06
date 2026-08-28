/* 「안내문 만들기」가 두 번 만들지 않는가 — KEY-204.
 *
 * 이 파일이 재는 것은 하나다. **버튼이 도는 동안 잠겨 있는가.**
 *
 * 처음에는 `submit.disabled = true` 한 줄이면 될 것 같았다. 아니었다 —
 * `renderSummary()` 가 매 `redraw()` 마다 그 값을 **무조건 다시 쓴다**.
 * 그리고 필드를 하나 저장하면 2.5 초 뒤 타이머가 `redraw()` 를 부른다.
 *
 *     saveField() → 성공 → redraw()
 *                 → setTimeout(2500) → delete saved[id] → redraw()   ← 여기
 *
 * 그래서 요청이 3 초 걸리면 그 사이 버튼이 **저 혼자 풀린다.** 화면만 보면
 * 잠근 것 같은데 실제로는 두 번 눌린다. 잠금을 상태로 두고 `renderSummary`
 * 가 규칙으로 계산해야 그 타이머를 지나도 살아남는다.
 *
 * 그리는 것은 여기서 재지 않는다 — 이 폴더의 관례다. 순수 규칙만 부른다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");

function box() {
  return load("api", "session", "patients-api", "shell", "ocr-api", "ocr-review");
}

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/* ── 잠금 ───────────────────────────────────────────────────────────────── */

test("**요청이 도는 동안은 잠긴다** — 다 읽혔고 충돌이 없어도", () => {
  const { generateBlocked } = box();

  assert.equal(generateBlocked({ missing: 0 }, 0, false), false, "깨끗하면 눌러야 한다");
  assert.equal(generateBlocked({ missing: 0 }, 0, true), true, "도는 중인데 또 눌리면 두 건이 생긴다");
});

test("못 읽은 값이나 충돌이 남으면 잠근다 — 빈칸 안내문이 환자에게 나간다", () => {
  const { generateBlocked } = box();

  assert.equal(generateBlocked({ missing: 1 }, 0, false), true, "못 읽은 값이 남았다");
  assert.equal(generateBlocked({ missing: 0 }, 1, false), true, "안 푼 충돌이 남았다");
});

test("**`renderSummary` 가 이 규칙을 부른다** — 안 부르면 2.5 초 뒤 타이머가 잠금을 푼다", () => {
  /* 이 검사가 이 파일의 존재 이유다. `submit.disabled` 를 직접 계산하는 자리가
     남아 있으면, 그 자리는 `generating` 을 모르므로 타이머가 지날 때 버튼을
     되살린다. 그리는 코드는 shim 아래서 안 돌기 때문에 원문으로 잰다. */
  const source = read("js/ocr-review.js");

  const assigns = source.split("\n").filter((line) => line.includes("submit.disabled ="));
  assert.ok(assigns.length > 0, "submit.disabled 를 쓰는 자리가 없다 — 검사가 헛돈다");

  for (const line of assigns) {
    assert.ok(
      line.includes("generateBlocked(") || line.includes("blank.") || line.includes("= true"),
      `잠금을 규칙 밖에서 계산한다 — 타이머가 지나면 풀린다: 「${line.trim()}」`,
    );
  }
});

test("잠근 이유가 다르면 말도 다르다", () => {
  const { generateBlockedSaying } = box();

  assert.match(generateBlockedSaying({ missing: 0 }, 0, true), /만드는 중/);
  assert.match(generateBlockedSaying({ missing: 2 }, 0, false), /정리한 뒤/);
  assert.equal(generateBlockedSaying({ missing: 0 }, 0, false), "", "잠기지 않았으면 할 말이 없다");
});

test("**상태 칸에 들어 있다** — `blankReviewState()` 가 모르면 화면을 바꿀 때 안 지워진다", () => {
  const { blankReviewState } = box();

  assert.equal(blankReviewState().generating, false, "generating 이 초기 상태에 없다");
});

/* ── 오류를 사람 말로 ───────────────────────────────────────────────────── */

test("**서버 message 를 그대로 흘리지 않는다** — OCR 원문이 실릴 수 있는 자리다", () => {
  const { generateFailureSaying } = box();

  const leak = { code: "OCR_NOT_CONFIRMED", status: 422, message: "환자 윤지아 · 비잔정 2mg" };
  const said = generateFailureSaying(leak);

  assert.ok(!said.includes("윤지아"), `서버 문구가 새어 나왔다: ${said}`);
  assert.ok(!said.includes("비잔정"), `서버 문구가 새어 나왔다: ${said}`);
  assert.match(said, /확정한 항목/);
});

test("**화면이 그 함수를 실제로 쓴다** — 규칙만 있고 안 쓰면 소용없다", () => {
  /* 순수 함수만 재면 「함수는 안전한데 화면은 `error.message` 를 뿌리는」
     상태를 못 잡는다. 부르는 자리를 원문으로 확인한다. */
  const source = read("js/ocr-review.js");
  const at = source.indexOf('if (target.id === "submit")');
  const branch = source.slice(at, source.indexOf("var jump = target.closest", at));

  assert.match(branch, /generateFailureSaying\(/, "실패 문구를 규칙으로 안 만든다");
  assert.ok(
    !/error\.message/.test(branch),
    "서버 message 를 화면에 직접 쓴다 — OCR 원문이 실릴 수 있는 자리다",
  );
});

test("아는 코드마다 다른 말을 한다 — 「알 수 없는 오류」로 뭉개지 않는다", () => {
  const { generateFailureSaying } = box();

  const said = {
    ocr: generateFailureSaying({ code: "OCR_NOT_CONFIRMED", status: 422 }),
    visit: generateFailureSaying({ code: "VISIT_NOT_FOUND", status: 404 }),
    forbidden: generateFailureSaying({ code: "FORBIDDEN", status: 403 }),
    expired: generateFailureSaying({ status: 401 }),
    offline: generateFailureSaying({ status: 0 }),
  };

  const uniq = new Set(Object.values(said));
  assert.equal(uniq.size, Object.keys(said).length, `같은 말을 두 번 한다: ${JSON.stringify(said)}`);
});

test("모르는 코드에도 다음 행동이 있다 — 막다른 골목을 만들지 않는다", () => {
  const { generateFailureSaying } = box();

  const said = generateFailureSaying({ code: "SOMETHING_NEW", status: 500 });

  assert.ok(said.length > 0);
  assert.match(said, /다시/, `무엇을 하면 되는지 안 알려 준다: ${said}`);
});

/* ── 409 는 실패가 아니다 ───────────────────────────────────────────────── */

test("**이미 있으면 실패가 아니다** — 새로고침 뒤 다시 누른 것이다", () => {
  const { guideAlreadyThere } = box();

  assert.equal(guideAlreadyThere({ code: "GUIDE_ALREADY_EXISTS", status: 409 }), true);
  assert.equal(guideAlreadyThere({ code: "OCR_NOT_CONFIRMED", status: 422 }), false);
  assert.equal(guideAlreadyThere(null), false, "오류가 없을 때도 물어볼 수 있어야 한다");
});

test("그 경우엔 「이미 있다」고 말한다 — 빨간 오류로 보여 주지 않는다", () => {
  const source = read("js/ocr-review.js");

  /* **정의부가 아니라 부르는 자리를 본다.** 처음에는 `indexOf` 가 함수 선언을
     먼저 잡아서, 실제로 화면이 그 갈래를 쓰는지 못 재고 있었다. */
  const branchAt = source.indexOf('if (target.id === "submit")');
  assert.ok(branchAt !== -1, "생성 버튼 분기가 없다");
  const branch = source.slice(branchAt, source.indexOf("var jump = target.closest", branchAt));

  assert.match(branch, /guideAlreadyThere\(/, "409 를 가르지 않는다");
  assert.match(branch, /이미 있습니다/, "409 를 다른 말로 알려 주지 않는다");
});

/* ── 어느 진료에 붙는가 ─────────────────────────────────────────────────── */

test("**요청 직전에 visit_id 를 붙잡는다** — 응답 오는 사이 목록이 바뀐다", () => {
  /* `doctor.js` 가 승인에서 `approvingId` 를 따로 잡는 것과 같은 이유다.
     전역 `visit` 을 콜백에서 다시 읽으면, A 를 눌러 놓고 B 의 안내문을
     만든 것처럼 보인다. */
  const source = read("js/ocr-review.js");

  const at = source.indexOf('if (target.id === "submit")');
  assert.ok(at !== -1, "생성 버튼 분기가 없다");

  const branch = source.slice(at, source.indexOf("var jump = target.closest", at));

  assert.match(branch, /var wantedId = visit\.visit_id/, "visit_id 를 미리 붙잡지 않는다");
  assert.ok(
    !/generateGuide\(\s*visit\.visit_id\s*\)/.test(branch),
    "요청할 때 전역 visit 을 다시 읽는다 — 그 사이 바뀔 수 있다",
  );

  /* **성공·실패 두 갈래 모두** 늦은 응답을 버려야 한다. 한쪽만 막으면
     다른 쪽이 남의 화면에 글을 쓴다. */
  const guards = branch.match(/mine !== loadSeq/g) || [];
  assert.equal(guards.length, 2, `늦게 온 응답을 한쪽에서만 버린다 — ${guards.length} 곳`);
});

test("병원을 실어 보내지 않는다 — 서버가 토큰으로 판단한다", () => {
  const source = read("js/ocr-api.js");

  const at = source.indexOf("generateGuide:");
  assert.ok(at !== -1, "생성 헬퍼가 없다");

  const fn = source.slice(at, at + 240);
  assert.ok(!/hospital/i.test(fn), "화면이 병원을 보낸다 — 보낸 값을 믿는 길이 생긴다");
  assert.match(fn, /encodeURIComponent/, "경로에 값을 그대로 끼운다");
});

/* ── 낡은 말이 남지 않았는가 ───────────────────────────────────────────── */

test("「아직 연결되지 않았습니다」가 사라졌다", () => {
  const source = read("js/ocr-review.js");
  const html = read("ocr-review.html");

  assert.ok(!source.includes("안내문 생성은 아직 연결되지 않았습니다"), "JS 에 낡은 문구가 남아 있다");

  /* HTML 은 **사람이 보는 자리**만 본다. 주석까지 훑으면 「예전에는 이렇게
     적혀 있었다」는 회고 설명에 걸린다 — 글자만 보는 검사는 주장과 회고를
     못 가른다(오늘 여러 번 밟았다). 주석을 떼고 남는 것으로 잰다. */
  const visible = html.replace(/<!--[\s\S]*?-->/g, "");
  assert.ok(!/아직 연결되지 않았습니다/.test(visible), "HTML 에 낡은 안내가 남아 있다");
  assert.ok(!/KEY-\d+/.test(visible), "화면에 일감 번호가 보인다 — 스탭이 알 필요 없는 말이다");
});
