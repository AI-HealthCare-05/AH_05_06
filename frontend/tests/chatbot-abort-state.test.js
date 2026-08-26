/* 중단이 **실제로 멈추는가** — KEY-186.
 *
 * 같은 파일의 문자열 검사 158 개는 `abortChatAnswer()` 본문을 잘라 패턴을
 * 맞춘다. 그래서 **줄은 그대로 두고 뜻만 망가뜨리면 전부 초록이다.**
 *
 *   stale() 이 늘 거짓을 돌려주게        158 개 통과   🔴 중단이 통째로 무력화
 *   중단 표시(aborted)를 안 남기게       158 개 통과   🔴
 *
 * 앞의 것이 특히 나쁘다. `stale()` 이 늘 거짓이면 중단을 눌러도 늦게 온 조각이
 * 전부 들어와 **완성본이 화면에 되살아난다** — KEY-130 이 막으려던 바로 그것이
 * 돌아오는데 검사는 아무 말을 안 한다.
 *
 * 여기서는 그리지 않고 **상태만 보고** 잰다. `browser-shim` 이 그리기를 막는
 * 것은 정책이라 그대로 두고, 대신 그리는 함수와 밖으로 나가는 호출을 컨텍스트
 * 에서 갈아 끼운다 — 판정에 필요한 것은 화면이 아니라 `state.chat` 이다
 * (`docs/qa/frontend-manual-browser-check.md` §1 선행 질문).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

/** 그리기와 스트림을 갈아 끼운 채 안내 화면을 세운다. */
function boot() {
  const ctx = load("api", "session", "patients-api", "shell", "guide-api", "guide");

  /* 그리기는 판정에 필요 없다. 껍데기는 그리려 하면 던지므로 갈아 끼운다. */
  ctx.renderBody = function () {};
  ctx.updateStreamingAnswer = function () {
    return true;
  };

  /* 스트림을 손에 쥔다 — 훅을 우리가 원할 때 부른다. 실서버 어댑터도 목업도
     `Promise` 만 돌려주고 취소 훅이 없어서, 중단은 「멈추게」 하는 것이 아니라
     **늦게 온 것을 버리는** 방식이다. 그 버리는 자리를 재는 것이 요점이다. */
  let hooks = null;
  ctx.streamChatbotAnswer = function (_request, given) {
    hooks = given;
    return { catch: () => ({ finally: () => {} }) };
  };

  ctx.state.token = "synthetic-token";
  ctx.state.chat.messages = [];
  ctx.state.chat.busy = false;
  ctx.state.chat.draft = "";
  ctx.state.chat.generation = 0;

  return {
    ctx,
    ask(question) {
      ctx.sendChatQuestion(question);
      return hooks;
    },
    answer() {
      const messages = ctx.state.chat.messages;
      return messages[messages.length - 1];
    },
  };
}

test("중단한 뒤 **늦게 온 조각은 답변에 안 붙는다**", () => {
  /* `stale()` 이 하는 일이 이것뿐이다. 이 검사가 없으면 그 함수를 통째로
     망가뜨려도 아무도 안 운다. */
  const box = boot();
  const stream = box.ask("질문");

  stream.onDelta("먼저 온 조각");
  const beforeAbort = box.answer().text;

  box.ctx.abortChatAnswer();
  stream.onDelta("늦게 온 조각");

  assert.strictEqual(box.answer().text, beforeAbort, "중단했는데 늦은 조각이 답변에 붙었다");
  assert.doesNotMatch(box.answer().text, /늦게 온 조각/);
});

test("중단한 뒤 **늦게 온 완성 신호도 화면을 되살리지 않는다**", () => {
  /* 조각보다 이쪽이 더 아프다 — `onComplete` 가 들어오면 답변이 「완성됨」으로
     바뀌어, 환자는 자기가 멈춘 답이 끝내 나온 것을 본다. */
  const box = boot();
  const stream = box.ask("질문");
  stream.onDelta("받다 만 조각");

  box.ctx.abortChatAnswer();
  stream.onComplete({ urgent: true, evidence: "근거", source: "출처", limitation: "한계" });

  const answer = box.answer();
  assert.strictEqual(answer.streaming, false);
  assert.strictEqual(answer.aborted, true, "중단 표시가 완성 신호에 덮였다");
  assert.strictEqual(answer.evidence, undefined, "중단한 답변에 근거가 붙었다 — 되살아났다");
});

test("중단하면 **마지막 답변에 중단 표시가 남는다**", () => {
  /* 표시가 없으면 화면이 「그냥 짧은 답」과 「멈춘 답」을 구분할 수 없다. */
  const box = boot();
  const stream = box.ask("질문");
  stream.onDelta("받다 만 조각");

  box.ctx.abortChatAnswer();

  const answer = box.answer();
  assert.strictEqual(answer.aborted, true, "중단했는데 표시가 안 남았다");
  assert.strictEqual(answer.streaming, false, "중단했는데 아직 받는 중이다");
  assert.strictEqual(box.ctx.state.chat.busy, false, "중단했는데 아직 바쁘다");
  assert.strictEqual(answer.text, "받다 만 조각", "받은 데까지는 남아야 한다");
});

test("받은 것이 없을 때 중단해도 터지지 않는다", () => {
  const box = boot();
  box.ask("질문");

  box.ctx.abortChatAnswer();

  assert.strictEqual(box.answer().aborted, true);
  assert.strictEqual(box.answer().text, "");
});

test("중단하지 않았으면 조각이 **그대로 붙는다** — 검사가 늘 통과하지 않게", () => {
  /* 위 셋이 「안 붙는다」만 재므로, 아무것도 안 붙는 구현도 만점을 받는다.
     반대 방향을 함께 박아 둔다. */
  const box = boot();
  const stream = box.ask("질문");

  stream.onDelta("첫 조각");
  stream.onDelta(" 둘째 조각");

  assert.strictEqual(box.answer().text, "첫 조각 둘째 조각");
  assert.notStrictEqual(box.answer().aborted, true);
});
