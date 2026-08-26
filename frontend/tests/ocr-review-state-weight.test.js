/* 예외 상태가 **사람 말로, 무게를 갖고, 빠져나갈 길과 함께** 나오는가 — KEY-126.
 *
 * 처음 판에서 셋을 고쳤다 — 기계 말 노출, 무게가 같음, 소리로 안 알림.
 * 그 판을 이희진 님이 리뷰해서 **더 깊은 둘**을 찾았다(`#121`).
 *
 *   ① `not_ready` 를 busy 로 그렸는데 폴링이 재시작되지 않아 **영영 기다린다**
 *   ② `poll_failed` 는 warn 인데 누를 것이 없어 **화면에 갇힌다**
 *
 * 둘 다 같은 병이다 — 「무게」와 「다음 행동」이 따로 놀았다. 그래서 이제
 * **규칙 하나로 묶는다: warn 이면 반드시 다음 행동이 있다.**
 *
 * 그리는 것은 여기서 재지 않는다 — 이 파일의 관례다.
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

/* ── 이희진 님이 찾은 것 — 갇히는 화면이 없다 ─────────────────────────── */

test("**warn 이면 반드시 다음 행동이 있다** — 갇히는 화면을 만들지 않는다", () => {
  /* 이 PR 의 1·2 번이 정확히 이 불변식을 어겼다. warn 은 「사람이 손대야
     다음이 있다」는 뜻인데, 손댈 것이 없으면 그냥 막다른 골목이다. */
  const { stateRules } = box();
  const rules = stateRules();

  const trapped = Object.keys(rules).filter((kind) => rules[kind].tone === "warn" && !rules[kind].action);

  assert.deepStrictEqual(trapped, [], `warn 인데 누를 것이 없다 — 스탭이 갇힌다: ${trapped}`);
});

test("반대도 참이다 — 행동이 있으면 warn 이다", () => {
  /* busy 에 버튼을 달면 「기다리면 된다면서 왜 누르라는가」가 된다. */
  const { stateRules } = box();
  const rules = stateRules();

  const odd = Object.keys(rules).filter((kind) => rules[kind].action && rules[kind].tone !== "warn");

  assert.deepStrictEqual(odd, [], `warn 이 아닌데 행동이 붙었다: ${odd}`);
});

test("영영 기다리게 하던 둘이 이제 warn 이고 다시 확인할 수 있다", () => {
  const { stateRule } = box();

  for (const kind of ["not_ready", "poll_failed"]) {
    assert.strictEqual(stateRule(kind).tone, "warn", `${kind} 이 아직 평온하다`);
    assert.strictEqual(stateRule(kind).action, "recheck", `${kind} 에서 빠져나갈 길이 없다`);
  }
});

test("도는 상태는 그대로 조용하다 — 저절로 풀리는 것까지 재촉하지 않는다", () => {
  const { stateRule, stateTakesFocus } = box();

  for (const kind of ["loading", "processing"]) {
    assert.strictEqual(stateRule(kind).tone, "busy");
    assert.strictEqual(stateRule(kind).action, null);
    assert.strictEqual(stateTakesFocus(stateRule(kind).tone), false, `${kind} 이 초점을 뺏는다`);
  }
});

test("「다시 확인」이 처음부터 다시 타는 길로 이어진다", () => {
  /* 규칙만 맞고 버튼이 아무것도 안 하면 소용이 없다. `loadVisit()` 은
     `loadSeq` 를 올리고 작업을 다시 물으며, 아직 도는 중이면 폴링에 재진입한다 —
     환자를 다시 고른 것과 같은 길이다. */
  const source = read("js/ocr-review.js");
  const at = source.indexOf('target.id === "recheck"');

  assert.notStrictEqual(at, -1, "다시 확인 버튼에 처리기가 없다");
  assert.match(source.slice(at, at + 200), /loadVisit\(visit\)/, "버튼이 다시 타지 않는다");
});

/* ── 기계 말이 스탭에게 안 간다 ───────────────────────────────────────── */

test("아는 실패 사유는 사람 말로 바뀐다", () => {
  const { failureSaying } = box();
  const said = failureSaying("OCR_ENGINE_TIMEOUT");

  assert.match(said.why, /시간/);
  assert.doesNotMatch(said.why, /OCR_ENGINE_TIMEOUT/, "기계 말이 그대로 나왔다");
});

test("**모르는 사유에도** 사람 말을 준다", () => {
  const { failureSaying } = box();

  for (const code of ["NEVER_SEEN_BEFORE", "OCR_ENGINE_MELTDOWN", "", null, undefined]) {
    const said = failureSaying(code);
    assert.ok(said.why && said.why.length > 0, `${code} 에 할 말이 없다`);
    assert.doesNotMatch(said.why, /[A-Z]{3,}_[A-Z]/, `${code} 의 안내에 기계 말이 섞였다: ${said.why}`);
  }
});

test("사유 코드는 버리지 않되 꼬리말로 간다", () => {
  const { failureSaying } = box();

  assert.strictEqual(failureSaying("OCR_ENGINE_TIMEOUT").code, "OCR_ENGINE_TIMEOUT");
  assert.strictEqual(failureSaying(null).code, null, "코드가 없으면 빈 줄을 만들지 않는다");
});

test("돌려주는 것은 **달라지는 둘뿐**이다", () => {
  /* 제목·다음 행동 문구는 어떤 코드가 와도 같은 상수라 부르는 쪽에 둔다
     (이희진 님 `#121` 리뷰). */
  const { failureSaying } = box();

  assert.deepStrictEqual(Object.keys(failureSaying("X")).sort(), ["code", "why"]);
});

test("원문 코드는 **오직 옮기는 함수를 통해서만** 화면에 닿는다", () => {
  const source = read("js/ocr-review.js");
  const from = source.indexOf('if (phase === "failed") {');
  assert.notStrictEqual(from, -1, "실패 분기를 못 찾았다 — 검사가 헛돈다");
  const failedBlock = source.slice(from, source.indexOf("return false;", from));

  assert.ok(failedBlock.includes("showState("), "블록이 그리는 자리를 안 담았다");
  const direct = failedBlock.match(/job\.failure_code/g) || [];
  assert.strictEqual(direct.length, 1, `원문 코드를 ${direct.length}곳에서 쓴다`);
  assert.match(failedBlock, /failureSaying\(job\.failure_code\)/);
});

/* ── 무게가 부르는 쪽 마음대로가 아니다 ───────────────────────────────── */

test("모든 상태 표시가 **갈래를 대고** 나간다", () => {
  /* 무게를 부르는 쪽이 고르면 「warn 인데 누를 것이 없는」 화면이 다시 생긴다.
     갈래만 대면 무게도 행동도 규칙이 정한다. */
  const source = read("js/ocr-review.js");
  const kinds = Object.keys({
    loading: 1,
    processing: 1,
    no_job: 1,
    job_failed: 1,
    not_ready: 1,
    poll_failed: 1,
    result_failed: 1,
  });

  const naked = [];
  let at = 0;
  for (;;) {
    at = source.indexOf("showState(", at);
    if (at === -1) break;
    if (source.slice(at - 9, at) === "function ") {
      at += 1;
      continue;
    }
    const head = source.slice(at, at + 40);
    if (!kinds.some((k) => head.includes(`"${k}"`))) naked.push(head.replace(/\s+/g, " "));
    at += 1;
  }

  assert.deepStrictEqual(naked, [], "갈래 없이 그리는 상태가 남았다");
});

test("CSS 가 무게를 색만이 아니라 모양으로도 나눈다", () => {
  const css = read("css/ocr-review.css");

  assert.match(css, /\.state--warn\s*\{[^}]*box-shadow/, "굵은 띠가 없다 — 색만으로 나눈다");
  assert.match(css, /\.state--warn\s*\{[^}]*var\(--danger/);
  assert.match(css, /\.state:focus-visible/, "초점을 받는데 어디인지 안 보인다");
});

/* ── 소리가 **시끄럽지 않게** 알린다 ──────────────────────────────────── */

test("진행률이 라이브 리전 안에 있지 않다", () => {
  /* `#state` 를 통째로 실어 두면 1.5 초마다 「판독 중입니다 NN%」가 다시 읽혀
     수십 초짜리 판독에서 20~40 번을 연달아 듣는다 (이희진 님 `#121` 리뷰). */
  const html = read("ocr-review.html");
  const state = html.slice(html.indexOf('id="state"') - 120, html.indexOf('id="state"') + 80);

  assert.doesNotMatch(state, /aria-live/, "판독 상태 박스가 아직 라이브 리전이다");
  assert.match(state, /tabindex="-1"/, "초점을 옮기는데 받을 수가 없다");
  assert.match(html, /id="state-say"[^>]*role="status"/, "소리로 알릴 자리가 없다");
});

test("소리는 **갈래가 바뀔 때만** 나간다", () => {
  const source = read("js/ocr-review.js");
  const at = source.indexOf("if (shownKind !== kind) {");

  assert.notStrictEqual(at, -1, "갈래가 바뀔 때만 알리는 자리가 없다");
  assert.match(source.slice(at, at + 300), /say\(/, "그 자리에서 알리지 않는다");
});

test("의사 화면 패널도 탭 클릭마다 읽히지 않는다", () => {
  /* `renderPanel()` 은 탭을 누를 때도 불린다. 패널을 통째로 실어 두면
     복약지도↔주의사항을 오갈 때마다 섹션 본문 전체가 다시 읽힌다. */
  const html = read("doctor.html");
  const panel = html.slice(html.indexOf('id="panel"') - 60, html.indexOf('id="panel"') + 60);

  assert.doesNotMatch(panel, /aria-live/, "패널이 아직 라이브 리전이다");
  assert.match(html, /id="panel-say"[^>]*role="status"/, "환자 전환을 알릴 자리가 없다");
});

/* ── 프로그레스바를 두 벌 유지하지 않는다 ─────────────────────────────── */

test("진행 막대는 공용 `.bar` 하나뿐이다", () => {
  /* `upload.css` 에 이미 있던 것을 판독 화면이 또 만들었었다 (이희진 님 `#121`). */
  const shared = read("css/style.css");
  const ocr = read("css/ocr-review.css");
  const upload = read("css/upload.css");

  assert.match(shared, /^\.bar \{/m, "공용 자리에 막대가 없다");
  assert.match(shared, /\.bar--pulse/, "도는 표시 변형이 공용에 없다");
  assert.doesNotMatch(ocr, /state__bar/, "판독 화면이 아직 자기 막대를 갖는다");
  assert.doesNotMatch(upload, /^\.bar__fill \{/m, "업로드 화면에 사본이 남았다");
  assert.doesNotMatch(shared, /border-radius:\s*999px/, "토큰 대신 값을 박았다");
});

test("도는 표시가 「움직임 줄이기」를 존중한다", () => {
  const css = read("css/style.css");
  const reduced = css.slice(css.indexOf("prefers-reduced-motion"));

  assert.match(reduced, /animation:\s*none/, "움직임을 못 끄면 어지럼을 부른다");
});
