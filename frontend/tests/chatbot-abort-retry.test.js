/* 답변을 **그만 받고, 다시 물을 수 있는가** — KEY-130.
 *
 * KEY-95(`#120`)가 스트리밍·근거·긴급 표시까지 넣었다. 남은 것은 셋이었다.
 *
 *   ① 중단이 **코드에 없었다** — 취소 버튼도 AbortController 도 0 건
 *   ② 재시도가 **문구만** 있었다 — 버튼이 없어 환자가 질문을 다시 쳐야 했다
 *   ③ 치던 글자가 **날아갔다** — 화면을 다시 그리면 입력칸이 새로 만들어진다
 *
 * ③은 브라우저에서 재현했다. 질문을 보내는 동안 다음 질문을 치고 있으면
 * `renderBody()` 가 입력칸을 갈아 끼워 그대로 사라진다.
 *
 * **중단이 가장 까다롭다.** 목업 스트림은 `setTimeout` 재귀라 취소 훅이 없고,
 * 실서버 어댑터도 `Promise` 만 돌려준다. 그래서 「멈추게」 할 수가 없다 —
 * 세대를 올려 **늦게 온 콜백을 버린다.** 이걸 안 하면 중단을 눌러도 조각이
 * 계속 들어와 끝내 완성본이 화면에 되살아난다.
 *
 * `chatbot-api.js` 는 건드리지 않았다 — 김고은 님 `#125`(KEY-96)가 그 파일을
 * 고치는 중이다. 이 검사도 그 파일을 안 잰다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/* ── ③ 치던 글자가 안 날아간다 ────────────────────────────────────────── */

test("치던 질문을 상태가 들고 있다", () => {
  /* 입력칸(DOM)에만 있으면 다시 그릴 때 사라진다. */
  const js = read("js/guide.js");

  assert.match(js, /chat:\s*\{[^}]*draft:/, "초안을 보관할 자리가 없다");
  assert.match(js, /input\.value = state\.chat\.draft/, "다시 그릴 때 되찾지 않는다");
  assert.match(js, /state\.chat\.draft = input\.value/, "치는 대로 보관하지 않는다");
});

test("보낸 뒤에는 초안을 비운다", () => {
  /* 안 비우면 보낸 질문이 입력칸에 남아 두 번 보내기 쉬워진다. */
  const js = read("js/guide.js");
  const at = js.indexOf("function sendChatQuestion(");

  assert.match(js.slice(at, at + 400), /state\.chat\.draft = ""/, "보낸 뒤 초안이 남는다");
});

test("**답변 중에도 다음 질문을 칠 수 있다**", () => {
  /* 예전에는 입력칸을 잠갔다. 기다리는 동안 할 수 있는 일이 없어진다.
     보내는 것만 막으면 된다. */
  const js = read("js/guide.js");
  const at = js.indexOf('input.setAttribute("aria-label", "챗봇 질문")');
  const block = js.slice(at, js.indexOf("form.addEventListener", at));

  assert.doesNotMatch(block, /input\.disabled\s*=\s*state\.chat\.busy/, "입력칸을 잠근다");
  assert.match(block, /submit\.disabled\s*=\s*state\.chat\.busy/, "전송은 막아야 중복 전송이 없다");
});

/* ── ① 중단 ───────────────────────────────────────────────────────────── */

test("중단이 **늦게 온 콜백을 버린다** — 답변이 되살아나지 않게", () => {
  /* 이게 이 티켓에서 제일 중요한 자리다. 목업 스트림은 취소 훅이 없어서
     `busy = false` 로만 놓으면 조각이 계속 들어오고, 끝내 완성본(근거·출처·
     한계까지 붙은)이 화면에 되살아난다. */
  const js = read("js/guide.js");

  assert.match(js, /generation:\s*0/, "세대를 셀 자리가 없다");
  assert.match(js, /function abortChatAnswer\(\)/, "중단이 없다");

  const abort = js.slice(js.indexOf("function abortChatAnswer()"), js.indexOf("function sendChatQuestion("));
  assert.match(abort, /state\.chat\.generation \+= 1/, "세대를 안 올린다 — 늦은 콜백이 그대로 들어온다");
});

test("모든 콜백이 세대를 확인한다 — 하나라도 빠지면 그리로 샌다", () => {
  const js = read("js/guide.js");
  const send = js.slice(js.indexOf("function sendChatQuestion("), js.indexOf("/* 아직 안 만든 탭"));

  for (const hook of ["onDelta", "onComplete", ".catch", ".finally"]) {
    const at = send.indexOf(hook);
    assert.notStrictEqual(at, -1, `${hook} 를 못 찾았다 — 검사가 헛돈다`);
    assert.match(send.slice(at, at + 160), /if \(stale\(\)\) return/, `${hook} 가 세대를 안 본다`);
  }
});

test("답변 중에만 중단 버튼이 있다", () => {
  const js = read("js/guide.js");
  const at = js.indexOf("if (state.chat.busy) {");

  assert.notStrictEqual(at, -1, "중단 버튼을 조건 없이 그린다");
  assert.match(js.slice(at, at + 300), /chat__stop/);
  assert.match(js.slice(at, at + 300), /abortChatAnswer/);
});

test("중단은 실패가 아니다 — 받은 데까지 남기고 사과하지 않는다", () => {
  const js = read("js/guide.js");
  const at = js.indexOf("function chatbotAnswerText(");
  const fn = js.slice(at, js.indexOf("}", js.indexOf("return message.text ||", at)));

  assert.match(fn, /message\.aborted/, "중단한 답변에 할 말이 없다");
  assert.doesNotMatch(fn, /aborted.*죄송|죄송.*aborted/, "사용자가 그만 받은 것을 사과한다");
});

/* ── ② 재시도 ─────────────────────────────────────────────────────────── */

test("실패·중단한 답변에 **다시 시도**가 붙는다", () => {
  const js = read("js/guide.js");
  const at = js.indexOf("if (!message.streaming) {");
  const block = js.slice(at, js.indexOf("return answer;", at));

  assert.match(block, /message\.error \|\| message\.aborted/, "실패·중단에만 붙지 않는다");
  assert.match(block, /chat__retry/);
  assert.match(block, /retryChatAnswer\(message\)/);
});

test("다시 시도가 **중복 메시지를 만들지 않는다**", () => {
  /* 완료 조건이 막으라고 한 것이다. 실패한 답변을 남겨 두면 같은 질문에
     대한 답이 둘이 된다. */
  const js = read("js/guide.js");
  const at = js.indexOf("function retryChatAnswer(");
  assert.notStrictEqual(at, -1, "다시 시도 처리기가 없다");

  const fn = js.slice(at, js.indexOf("\n}", at));
  assert.match(fn, /splice\(/, "옛 답변을 안 걷는다 — 중복이 남는다");
  assert.match(fn, /role === "user"/, "질문 말풍선도 함께 걷어야 한 쌍이 된다");
  assert.match(fn, /if \(state\.chat\.busy\) return/, "답변 중에도 다시 보낼 수 있다");
});

test("질문을 답변에 담아 둔다 — 다시 시도가 그것을 쓴다", () => {
  const js = read("js/guide.js");
  const at = js.indexOf("var answer = { role: \"assistant\"");

  assert.match(js.slice(at, at + 160), /question: question/, "무엇을 다시 물을지 모른다");
});

/* ── 상태가 눈에 보인다 ───────────────────────────────────────────────── */

test("받는 중·중단됨이 **글자 말고도** 구분된다", () => {
  /* 예전에는 상태 신호가 전송 버튼 라벨 하나뿐이었다. */
  const css = read("css/guide.css");

  assert.match(css, /\.chat__answer--streaming/, "받는 중 표시가 없다");
  assert.match(css, /\.chat__answer--aborted/, "중단 표시가 없다");
  assert.match(css, /\.chat__stop/, "중단 버튼 모양이 없다");
});

test("받는 중 표시가 「움직임 줄이기」를 존중한다", () => {
  const css = read("css/guide.css");
  const reduced = css.slice(css.lastIndexOf("prefers-reduced-motion"));

  assert.match(reduced, /chat__answer--streaming[\s\S]*animation:\s*none/, "움직임을 못 끈다");
  /* 점선 테두리는 남으므로 **상태는 여전히 보인다** — 움직임만 뺀다. */
  assert.match(css, /\.chat__answer--streaming\s*\{[^}]*border-style/, "움직임을 끄면 상태가 사라진다");
});

test("김고은 님 `#125` 가 고치는 파일은 안 건드린다", () => {
  /* KEY-96 이 `chatbot-api.js` 와 그 검사를 고치는 중이다. 경계를 지킨다. */
  const js = read("js/guide.js");

  assert.doesNotMatch(js, /streamMockResult|chatbotStreamTransport/, "목업 내부를 건드린다");
  assert.match(js, /streamChatbotAnswer\(/, "공개 인터페이스로만 부른다");
});
