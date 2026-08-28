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

  /* **붙잡은 값이 호출부까지 이어지는지 본다** — 이희진 님 `#162` ②.
     예전 판은 「`var wantedId =` 가 있다」와 「`generateGuide(visit.visit_id)` 가
     아니다」 둘만 봤다. 그러면 `generateGuide(current && current.visit_id)` 로
     바꾸고 `wantedId` 를 죽은 채로 둬도 전부 통과한다. 프런트에 린터가 없어
     죽은 변수도 아무도 안 잡는다.

     그래서 붙잡은 **이름을 꺼내** 그 이름이 그대로 넘어가는지 잰다. */
  const capture = branch.match(/var\s+(\w+)\s*=\s*visit\.visit_id\b/);
  assert.ok(capture, "visit_id 를 미리 붙잡지 않는다");

  const held = capture[1];
  assert.match(
    branch,
    new RegExp("\\.generateGuide\\(\\s*" + held + "\\s*\\)"),
    `붙잡은 \`${held}\` 를 안 넘긴다 — 붙잡아 놓고 딴 값을 보내면 붙잡은 뜻이 없다`,
  );

  /* **성공·실패 두 갈래 모두** 늦은 소식을 가려야 한다. 한쪽만 막으면
     다른 쪽이 남의 화면에 글을 쓴다. */
  const guards = branch.match(/outcomeBelongsToScreen\(/g) || [];
  assert.equal(guards.length, 2, `늦게 온 소식을 한쪽에서만 가린다 — ${guards.length} 곳`);
});

/* ── 떠났다 돌아오면 ───────────────────────────────────────────────────── */

test("**같은 진료로 돌아오면 결과를 보여 준다** — 세대 번호로 가르지 않는다", () => {
  /* 이희진 님 `#162` ③. 예전 판은 `mine !== loadSeq` 로 갈랐다. A 에서 누르고
     B 로 갔다가 다시 A 로 오면 세대가 달라져 결과를 버렸다 — 안내문은 실제로
     만들어졌는데 화면은 아무 말이 없고, 다시 눌러 409 를 받아야 알았다. */
  const box = load("ocr-review");

  assert.equal(box.outcomeBelongsToScreen(8801, { visit_id: 8801 }), true, "같은 진료인데 버린다");
  assert.equal(box.outcomeBelongsToScreen(8801, { visit_id: 8802 }), false, "다른 진료인데 쓴다");
  assert.equal(box.outcomeBelongsToScreen(8801, null), false, "보고 있는 진료가 없는데 쓴다");
});

test("판 번호(loadSeq)로 가르던 자리가 남아 있지 않다", () => {
  const source = read("js/ocr-review.js");

  const at = source.indexOf('if (target.id === "submit")');
  const branch = source.slice(at, source.indexOf("var jump = target.closest", at));

  assert.ok(
    !/mine !== loadSeq/.test(branch),
    "안내문 생성 갈래가 아직 세대 번호로 가른다 — 돌아온 사람에게 아무 말도 못 한다",
  );
});

test("**잠금은 내가 쥔 것일 때만 푼다** — 늦게 온 옛 응답이 새 요청을 열지 않게", () => {
  /* 이희진 님 `KEY-210`. 앞 판은 「어느 화면이든 잠금부터 푼다」였고, 검사도
     그 순서를 강제하고 있었다. 그러면 이렇게 된다.

       A 에서 누름(req1) → B 로 감 → A 로 돌아옴 → 다시 누름(req2)
       → req1 응답 도착 → generating=false → **req2 가 나가 있는데 버튼이 열린다**

     물어야 할 것은 「끝났는가」가 아니라 **「내가 지금 나가 있는 그 요청인가」**다. */
  const box = load("ocr-review");

  assert.equal(box.generateLockIsMine(3, 3), true, "내가 최신인데 잠금을 안 푼다");
  assert.equal(box.generateLockIsMine(2, 3), false, "옛 요청이 새 잠금을 푼다");
});

test("재현 순서 — 돌아와 다시 누른 뒤 옛 응답이 와도 잠금이 유지된다", () => {
  /* `KEY-210` 인수조건 ①②. 화면 코드를 부를 수 없으니(껍데기의 `getElementById`
     가 `null` 이면 IIFE 가 통째로 안 돈다) **두 규칙의 조합**으로 재현한다.

       req1 = 1세대 · A         req2 = 2세대 · A (재클릭)
       지금 나가 있는 것은 2세대, 화면은 A */
  const box = load("ocr-review");
  const latest = 2;
  const shown = { visit_id: 8801 };

  const req1 = { seq: 1, wanted: 8801 };
  const req2 = { seq: 2, wanted: 8801 };

  const mayTouch = (r) =>
    box.generateLockIsMine(r.seq, latest) && box.outcomeBelongsToScreen(r.wanted, shown);

  assert.equal(mayTouch(req1), false, "늦게 온 req1 이 잠금·문구를 건드린다");
  assert.equal(mayTouch(req2), true, "지금 나가 있는 req2 가 결과를 못 쓴다");
});

test("떠났다 돌아온 정상 케이스는 그대로다 — 재클릭이 없으면 결과를 보여 준다", () => {
  /* `KEY-210` 인수조건 ③ — KEY-204 회귀를 유지한다. */
  const box = load("ocr-review");

  const stillMine = box.generateLockIsMine(1, 1);
  const sameVisit = box.outcomeBelongsToScreen(8801, { visit_id: 8801 });

  assert.ok(stillMine && sameVisit, "재클릭 없이 돌아왔는데 결과를 못 쓴다");
});

test("**요청마다 세대가 올라간다** — 안 올리면 규칙이 늘 참이 된다", () => {
  /* `generateLockIsMine` 만 잘 만들어도 소용이 없다. 세대를 안 올리면 모든
     요청이 같은 번호를 갖고, 규칙은 언제나 「내 것」이라고 답한다 — 결함이
     조용히 되돌아온다. 실제로 주입해 보니 규칙 검사 넷이 다 통과했다.

     그래서 **올리는 자리**를 따로 잰다. */
  const source = read("js/ocr-review.js");

  const at = source.indexOf('if (target.id === "submit")');
  const branch = source.slice(at, source.indexOf("var jump = target.closest", at));

  assert.match(
    branch,
    /var\s+\w+\s*=\s*\+\+generateSeq/,
    "요청 세대를 올리지 않고 그냥 읽는다 — 모든 요청이 같은 번호가 되어 규칙이 늘 참이 된다",
  );
});

test("두 갈래 모두 잠금 주인을 확인한다", () => {
  const source = read("js/ocr-review.js");

  const at = source.indexOf('if (target.id === "submit")');
  const branch = source.slice(at, source.indexOf("var jump = target.closest", at));

  const checks = branch.match(/generateLockIsMine\(/g) || [];
  assert.equal(checks.length, 2, `성공·실패 중 한쪽만 잠금 주인을 본다 — ${checks.length} 곳`);
  assert.ok(
    !/^\s*generating = false;\s*$/m.test(branch.replace(/if \(lockIsMine\) generating = false;/g, "")),
    "잠금을 무조건 푸는 줄이 남아 있다",
  );
});


/* ── 치우는 자리와 쓰는 자리 ───────────────────────────────────────────── */

test("**`saveNote` 는 글자와 숨김을 늘 짝지어 다룬다**", () => {
  /* 이희진 님 `#162` ④. 쓰는 자리 셋은 `textContent` 와 `hidden` 을 짝지어
     다루는데 `resetState` 만 글자를 지우고 숨기지 않았다. 빈 칸이 12px 자리를
     차지한 채 남는다.

     화면 코드라 검사에서 부를 수가 없다 — 껍데기의 `getElementById` 가 `null`
     을 주면 IIFE 가 통째로 안 돈다. 그래서 **짝이 맞는지**를 센다. */
  const source = read("js/ocr-review.js");

  const writes = (source.match(/saveNote\.textContent\s*=/g) || []).length;
  const shows = (source.match(/saveNote\.hidden\s*=/g) || []).length;

  assert.ok(writes > 2, `saveNote 를 다루는 자리를 거의 못 찾았다 — 검사가 헛돈다 (${writes})`);
  assert.equal(shows, writes, `글자를 ${writes} 곳에서 다루는데 숨김은 ${shows} 곳뿐이다 — 한쪽이 빠졌다`);
});

test("문구 표에 **절대 안 걸리는 규칙**을 두지 않는다", () => {
  /* 이희진 님 `#162` ⑤. `{ status: 0 }` 규칙이 있었는데 `request()` 는
     `ApiError` 에 `res.status` 만 싣는다 — `fetch` 가 던지는 `TypeError` 에는
     `.status` 자체가 없다. 그 규칙은 한 번도 안 걸렸다.

     안 걸리는 규칙은 「이 경우도 챙겼다」는 착각만 남긴다. 진짜로 챙기려면
     `request()` 가 네트워크 실패를 `status: 0` 으로 정규화해야 하는데, 그건
     모든 화면의 오류 모양을 바꾸는 일이라 이 PR 밖이다. 여기서는 없앤다. */
  const box = load("ocr-review");
  const rules = box.GENERATE_SAYINGS;

  assert.ok(Array.isArray(rules) && rules.length > 2, `문구 표를 못 찾았다 — ${JSON.stringify(rules)}`);
  const unreachable = rules.filter((rule) => rule.status === 0);
  assert.deepEqual(unreachable, [], "request() 가 status 0 을 안 만든다 — 이 규칙은 안 걸린다");
});
