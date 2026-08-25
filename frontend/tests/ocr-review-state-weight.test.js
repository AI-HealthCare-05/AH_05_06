/* 예외 상태가 **사람 말로, 무게를 갖고** 나오는가 — KEY-126.
 *
 * 진단에서 셋을 찾았다.
 *
 *   ① 실패 화면이 `OCR_ENGINE_TIMEOUT` 원문을 그대로 보여 준다
 *   ② 「처리 중」과 「실패」가 시각적으로 같은 무게다
 *   ③ 상태가 바뀌어도 소리로는 아무 일이 없다
 *
 * 그리는 것은 여기서 재지 않는다 — 이 파일의 관례다. 대신 **무엇을 그릴지
 * 정하는 규칙**과, 화면 파일·CSS 가 그 규칙을 실제로 쓰는지를 잰다.
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

/* ── ① 기계 말이 스탭에게 안 간다 ───────────────────────────────────── */

test("아는 실패 사유는 사람 말로 바뀐다", () => {
  const { failureSaying } = box();
  const said = failureSaying("OCR_ENGINE_TIMEOUT");

  assert.match(said.why, /시간/, "왜 실패했는지를 말해야 한다");
  assert.doesNotMatch(said.why, /OCR_ENGINE_TIMEOUT/, "기계 말이 그대로 나왔다");
  assert.doesNotMatch(said.title, /OCR_ENGINE_TIMEOUT/);
  assert.doesNotMatch(said.next, /OCR_ENGINE_TIMEOUT/);
});

test("**모르는 사유에도** 사람 말을 준다", () => {
  /* 코드 목록은 닫혀 있지 않다 — `failure_code` 는 CharField(64) 이고 실제
     판독기는 아직 안 붙었다(KEY-56). 아는 것만 옮기면 결국 원문이 보이는
     화면이 남는다. 이 검사가 그 구멍을 막는다. */
  const { failureSaying } = box();

  for (const code of ["NEVER_SEEN_BEFORE", "OCR_ENGINE_MELTDOWN", "", null, undefined]) {
    const said = failureSaying(code);
    assert.ok(said.why && said.why.length > 0, `${code} 에 할 말이 없다`);
    assert.doesNotMatch(said.why, /[A-Z]{3,}_[A-Z]/, `${code} 의 안내에 기계 말이 섞였다: ${said.why}`);
  }
});

test("사유 코드는 버리지 않되 꼬리말로 간다", () => {
  /* 스탭이 문의할 때 그 한 줄이 필요하다. 다만 머리말이면 안 된다. */
  const { failureSaying } = box();

  assert.strictEqual(failureSaying("OCR_ENGINE_TIMEOUT").code, "OCR_ENGINE_TIMEOUT");
  assert.strictEqual(failureSaying(null).code, null, "코드가 없으면 빈 줄을 만들지 않는다");
});

test("원문 코드는 **오직 옮기는 함수를 통해서만** 화면에 닿는다", () => {
  /* 처음에는 제목만 지켰다. 그랬더니 코드를 **본문**에 도로 넣는 돌연변이가
     통과했다 — 지키는 자리를 하나 정해 두면 나머지로 새어 나온다.
     그래서 「제목에 없다」가 아니라 **「직접 쓰는 자리가 하나도 없다」** 로
     건다. `job.failure_code` 는 `failureSaying()` 에 넘길 때 딱 한 번만
     나온다. 화면에 나가는 코드는 그 함수가 돌려준 `saying.code` 뿐이다. */
  const source = read("js/ocr-review.js");

  /* **`stateTone()` 이 아니라 그리는 분기**를 잡는다. `phase === "failed"` 로
     찾으면 위쪽 순수 함수가 먼저 걸려서 엉뚱한 19,000자를 재게 된다 —
     실제로 그렇게 썼다가 깨끗한 코드에서 검사가 죽었다. */
  const from = source.indexOf('if (phase === "failed") {');
  assert.notStrictEqual(from, -1, "실패 분기를 못 찾았다 — 검사가 헛돈다");
  const failedBlock = source.slice(from, source.indexOf("return false;", from));

  assert.ok(failedBlock.includes("showState("), "블록이 그리는 자리를 안 담았다 — 검사가 헛돈다");

  const direct = failedBlock.match(/job\.failure_code/g) || [];
  assert.strictEqual(direct.length, 1, `원문 코드를 ${direct.length}곳에서 쓴다 — 옮기지 않고 흘리는 자리가 있다`);
  assert.match(failedBlock, /failureSaying\(job\.failure_code\)/, "그 한 곳이 옮기는 함수가 아니다");
});

/* ── ② 상태마다 무게가 다르다 ───────────────────────────────────────── */

test("도는 상태와 멈춘 상태의 무게가 다르다", () => {
  const { stateTone } = box();

  assert.strictEqual(stateTone("processing"), "busy");
  assert.strictEqual(stateTone("failed"), "warn");
  assert.notStrictEqual(stateTone("processing"), stateTone("failed"), "둘이 같으면 눈으로 못 가른다");
});

test("초점은 **손대야 하는 상태에서만** 옮긴다", () => {
  /* 저절로 풀리는 상태까지 커서를 뺏으면 키보드로 일하던 사람이 자리를 잃는다. */
  const { stateTakesFocus, stateTone } = box();

  assert.strictEqual(stateTakesFocus(stateTone("failed")), true);
  assert.strictEqual(stateTakesFocus(stateTone("processing")), false);
  assert.strictEqual(stateTakesFocus(stateTone("ready")), false);
});

test("모든 상태 표시가 무게를 달고 나간다", () => {
  /* 하나라도 빠지면 그 상태만 옛 흰 박스로 남는다 — 고친 티가 안 나는 자리다. */
  const source = read("js/ocr-review.js");
  const calls = source.match(/showState\(/g) || [];
  const naked = [];

  let at = 0;
  for (let i = 0; i < calls.length; i += 1) {
    at = source.indexOf("showState(", at);
    if (source.slice(at - 9, at) === "function ") {
      at += 1;
      continue;
    }
    /* 괄호 짝을 세어 이 호출의 끝을 찾는다. */
    let depth = 0;
    let end = at + "showState".length;
    do {
      if (source[end] === "(") depth += 1;
      if (source[end] === ")") depth -= 1;
      end += 1;
    } while (depth > 0 && end < source.length);
    const call = source.slice(at, end);
    if (!/"(busy|warn|info)"|stateTone\(/.test(call)) naked.push(call.slice(0, 60));
    at = end;
  }

  assert.deepStrictEqual(naked, [], "무게 없이 그리는 상태가 남았다");
});

test("CSS 가 무게를 색만이 아니라 모양으로도 나눈다", () => {
  /* 색맹인 사람에게 색만으로 나누면 아무 차이가 없다 (WCAG 1.4.1). */
  const css = read("css/ocr-review.css");

  assert.match(css, /\.state--warn\s*\{[^}]*box-shadow/, "굵은 띠가 없다 — 색만으로 나눈다");
  assert.match(css, /\.state--warn\s*\{[^}]*var\(--danger/, "항목 목록과 다른 색 규칙을 쓴다");
  assert.match(css, /\.state:focus-visible/, "초점을 받는데 어디인지 안 보인다");
});

test("도는 표시가 「움직임 줄이기」를 존중한다", () => {
  const css = read("css/ocr-review.css");
  const reduced = css.slice(css.indexOf("prefers-reduced-motion"));

  assert.match(reduced, /\.state__bar-fill\s*\{[^}]*animation:\s*none/, "움직임을 못 끄면 어지럼을 부른다");
});

/* ── ③ 소리로도 알린다 ──────────────────────────────────────────────── */

test("두 화면의 바뀌는 자리가 스크린리더에 알려진다", () => {
  /* 진단표에서 이 둘이 가장 비어 있었다 — 판독이 끝나거나 실패해도
     소리로는 아무 일이 없었다. */
  const ocr = read("ocr-review.html");
  const doctor = read("doctor.html");

  const state = ocr.slice(ocr.indexOf('id="state"') - 60, ocr.indexOf('id="state"') + 120);
  assert.match(state, /aria-live/, "판독 상태가 소리로 안 알려진다");
  assert.match(state, /role="status"/);
  assert.match(state, /tabindex="-1"/, "초점을 옮기는데 받을 수가 없다");

  const panel = doctor.slice(doctor.indexOf('id="panel"') - 60, doctor.indexOf('id="panel"') + 120);
  assert.match(panel, /aria-live/, "안내문이 바뀌어도 소리로는 아무 일이 없다");
});
