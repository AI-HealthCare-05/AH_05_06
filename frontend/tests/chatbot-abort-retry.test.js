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
const { load } = require("./browser-shim.js");

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

test("보낸 뒤에는 초안을 비운다 — **입력칸에서 꺼내 보낸 경우에만**", () => {
  /* 안 비우면 보낸 질문이 입력칸에 남아 두 번 보내기 쉬워진다. 그런데 비우는
     자리가 `sendChatQuestion` 이면 **다시 시도**도 그 길로 들어와 남의 초안을
     지운다. 입력칸에서 꺼낸 자리에서만 비운다. */
  const js = read("js/guide.js");
  const at = js.indexOf("function sendChatQuestion(");

  assert.doesNotMatch(js.slice(at, at + 500), /state\.chat\.draft = ""/, "보내는 함수가 초안을 지운다 — 재시도까지 지운다");

  const submit = js.slice(js.indexOf('form.addEventListener("submit"'), js.indexOf("wrap.appendChild(form)"));
  assert.match(submit, /state\.chat\.draft = ""/, "전송한 뒤에도 초안이 남는다");
});

test("**다시 시도가 치던 글자를 지우지 않는다** — 실제로 불러 본다", () => {
  /* 이 티켓이 고치려던 ③(치던 글자가 날아간다)이 **재시도 경로로 되살아나
     있었다.** 문자열만 보던 검사로는 안 잡혔다 (이희진 님 `#135` 리뷰).

     시나리오 — 질문이 실패해 「다시 시도」가 떴고, 그 아래에서 다음 질문을
     치던 중 「다시 시도」를 누른다. */
  const { state, retryChatAnswer } = load("api", "session", "patients-api", "shell", "guide-api", "guide");

  const failed = { role: "assistant", text: "", error: "잠시 뒤 다시 시도해 주세요.", question: "첫 질문" };
  state.chat.messages = [{ role: "user", text: "첫 질문" }, failed];
  state.chat.busy = false;
  state.chat.draft = "치고 있던 다음 질문";

  try {
    retryChatAnswer(failed);
  } catch (err) {
    /* 껍데기는 **그리려 하면 던진다** — 화면은 브라우저에서 눈으로 본다. 초안은
       그리기 전에 정해지므로 여기까지 온 것으로 충분하다. 두 모습으로 오는데,
       그 둘만 받아 넘기고 나머지는 그대로 터뜨린다 — 진짜 버그를 삼키면 안 된다. */
    const said = String(err && err.message);
    if (!/화면을 그리려/.test(said) && !/Cannot set properties of null/.test(said)) throw err;
  }

  assert.strictEqual(state.chat.draft, "치고 있던 다음 질문", "다시 시도가 치던 글자를 지웠다");
});

test("커서가 입력칸의 **어디에** 있었는지 비우기 전에 본다", () => {
  /* 초안은 되찾는데 커서를 안 되찾으면, 다음 질문을 치던 중 앞 답변이 끝나는
     순간 손이 멈춘다. 그리고 다 비운 뒤에 물으면 늦다 — 지운 노드에서 포커스가
     이미 빠져 있다 (이희진 님 `#135` 리뷰). */
  const box = load("api", "session", "patients-api", "shell", "guide-api", "guide");

  box.document.activeElement = { className: "chat__input", selectionStart: 4 };
  assert.strictEqual(box.chatTypingAt(), 4, "치던 자리를 안 들고 온다 — 커서가 글 끝으로 간다");

  box.document.activeElement = { className: "chat__input" };
  assert.strictEqual(box.chatTypingAt(), 0, "자리를 모르면 처음으로 둔다");

  box.document.activeElement = { className: "tabs__button", selectionStart: 4 };
  assert.strictEqual(box.chatTypingAt(), -1, "아무 데나 커서가 있으면 포커스를 뺏는다");

  box.document.activeElement = null;
  assert.strictEqual(box.chatTypingAt(), -1, "커서가 없는데도 가져간다");

  const body = read("js/guide.js").slice(read("js/guide.js").indexOf("function renderBody()"));
  assert.ok(body.indexOf("chatTypingAt()") < body.indexOf('body.textContent = ""'), "비운 뒤에 묻는다 — 그때는 이미 늦다");

  /* 부품 둘이 멀쩡해도 **연결이 없으면** 아무 일도 안 일어난다.

     예전 판은 `renderChatTab()` 바로 뒤만 봤는데, 챗봇 탭을 그리는 자리가
     **둘**이라 하나만 이어 놓고도 통과했다 (이희진 님 `#135` 리뷰). 그래서
     지금은 「어느 분기 뒤에 붙었나」가 아니라 **「채우기가 다 끝난 뒤 한 곳에서
     되돌리나」**를 잰다 — 자리가 셋이 되어도 이 검사는 그대로 유효하다. */
  const js = read("js/guide.js");
  const renderBody = js.slice(js.indexOf("function renderBody()"), js.indexOf("function fillGuideBody"));
  const fill = js.slice(js.indexOf("function fillGuideBody"), js.indexOf("function renderError"));

  assert.strictEqual(
    (renderBody.match(/focusChatInput\(/g) || []).length,
    1,
    "되돌리는 자리가 한 곳이 아니다 — 분기마다 붙이면 새 분기에서 또 빠진다",
  );
  assert.doesNotMatch(fill, /focusChatInput\(/, "채우는 쪽이 커서까지 건드린다 — 분기마다 흩어진다");
  assert.ok(
    renderBody.indexOf("fillGuideBody(") < renderBody.indexOf("focusChatInput("),
    "다 채우기 전에 되돌린다 — 그리면서 노드가 다시 갈린다",
  );
  assert.match(fill, /renderChatTab\(\)/, "채우는 쪽에서 챗봇 탭을 안 그린다 — 검사가 헛돈다");
});

test("커서를 돌려줄 때 **치던 자리로** 돌려준다", () => {
  /* 자리를 들고 오기만 하고 안 쓰면 소용없다 — 포커스만 주면 커서가 글 끝으로
     간다. 껍데기 입력칸을 하나 물려 주고 **무엇을 불렀는지** 본다. 값을 넣지
     않으므로 「그리는 것」이 아니다. */
  const box = load("api", "session", "patients-api", "shell", "guide-api", "guide");

  const calls = [];
  box.document.querySelector = () => ({
    className: "chat__input",
    focus: () => calls.push("focus"),
    setSelectionRange: (a, b) => calls.push("range:" + a + "," + b),
  });

  box.focusChatInput(4);
  assert.deepStrictEqual(calls, ["focus", "range:4,4"], "치던 자리로 안 돌려준다");

  calls.length = 0;
  box.focusChatInput(-1);
  assert.deepStrictEqual(calls, ["focus"], "자리를 모르는데 0 으로 밀어 넣는다");
});

test("입력칸을 안 잠그므로 `:disabled` 규칙도 없다 — 둘은 같이 움직인다", () => {
  /* 이 PR 이 `input.disabled = state.chat.busy` 를 걷어 냈으므로
     `.chat__input:disabled` 는 **어떤 경로로도 안 붙는다.** 남겨 두면 다음
     사람이 「잠기는 상태가 있나 보다」로 읽는다 (이희진 님 `#135` 리뷰).
     한쪽만 되돌아가지 않도록 둘을 한 검사에 묶어 둔다. */
  const locks = /input\.disabled\s*=\s*state\.chat\.busy/.test(read("js/guide.js"));
  const styled = /^\s*\.chat__input:disabled\s*,?\s*$/m.test(read("css/guide.css"));

  assert.strictEqual(styled, locks, locks ? "잠그는데 그 모양이 없다" : "안 잠그는데 죽은 규칙이 남았다");
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
