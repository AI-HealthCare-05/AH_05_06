/* KEY-95 챗봇 스트리밍 UI 계약 — 실제 API 계약은 KEY-77·KEY-96 대기. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const JS_DIR = path.join(__dirname, "..", "js");

function loadApi(search = "?mock=1") {
  const context = vm.createContext({
    URLSearchParams,
    Promise,
    String,
    window: { location: { search } },
    setTimeout: (fn, _ms, ...args) => setTimeout(fn, 0, ...args),
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "chatbot-api.js"), "utf8"), context);
  return context;
}

function loadGuideUi() {
  const context = vm.createContext({
    Promise,
    String,
    URLSearchParams,
    document: { addEventListener() {} },
    setTimeout,
    window: { location: { search: "?mock=1" } },
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "chatbot-api.js"), "utf8"), context);
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "guide.js"), "utf8"), context);
  return context;
}

test("합성 승인 안내 답변은 여러 조각으로 스트리밍되고 근거·출처·한계를 함께 준다", async () => {
  const api = loadApi();
  const chunks = [];
  let completed = null;

  const result = await api.streamChatbotAnswer(
    { link_token: "synthetic-link", question: "출혈이 있는데 약을 끊어도 되나요?" },
    {
      onDelta: (chunk) => chunks.push(chunk),
      onComplete: (answer) => {
        completed = answer;
      },
    },
  );

  assert.ok(chunks.length > 1, "완성 문장을 한 번에 반환하면 스트리밍 UI를 검증할 수 없다");
  assert.equal(chunks.join(""), result.answer);
  assert.equal(completed.answer, result.answer);
  assert.match(result.evidence, /주의사항/);
  assert.match(result.source, /승인한 진료 안내/);
  assert.match(result.limitation, /처방 변경/);
  assert.equal(result.urgent, false);
  assert.equal("raw_document" in result, false);
  assert.equal("conversation" in result, false);
});

test("긴급 신호 목업은 P6-2 강조 상태를 명시한다", async () => {
  const api = loadApi();
  const result = await api.streamChatbotAnswer({ question: "다리가 붓고 숨이 차요" }, {});

  assert.equal(result.urgent, true);
  assert.match(result.answer, /바로 병원에 연락/);
});

test("스트림 실패는 환자용 재시도 문구로 정규화한다", async () => {
  const api = loadApi("?mock=1&chat=error");

  await assert.rejects(
    () => api.streamChatbotAnswer({ question: "합성 질문" }, {}),
    (error) => error.code === "CHATBOT_STREAM_FAILED",
  );
  assert.equal(api.chatbotErrorMessage("CHATBOT_STREAM_FAILED"), "답변을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.");
});

test("KEY-95 UI는 챗봇 탭과 근거·출처·한계 표시를 실제 렌더 경로에 둔다", () => {
  const source = fs.readFileSync(path.join(JS_DIR, "guide.js"), "utf8");

  assert.match(source, /\{ key: "chat", label: "챗봇" \}/);
  assert.doesNotMatch(source, /\{ key: "chat", label: "챗봇", pending: true \}/);
  assert.match(source, /"📎 " \+ message\.evidence/);
  assert.match(source, /"출처 · " \+ message\.source/);
  assert.match(source, /"한계 · " \+ message\.limitation/);
  assert.match(source, /function renderContactButton\(className\)/);
  assert.equal(source.match(/notice\("문의 주소는 병원 설정에서 정합니다/g).length, 1);
  assert.match(source, /\.finally\(function \(\) \{[\s\S]*state\.chat\.busy = false/);
});

test("delta 뒤 스트림이 실패하면 잘린 답변 대신 오류를 표시하고 입력 포커스를 청크마다 다시 만들지 않는다", async () => {
  const ui = loadGuideUi();
  let renderCount = 0;
  const streamedTexts = [];
  ui.renderBody = () => {
    renderCount += 1;
  };
  ui.updateStreamingAnswer = (message) => {
    streamedTexts.push(ui.chatbotAnswerText(message));
    return true;
  };
  ui.streamChatbotAnswer = (_request, observer) => {
    observer.onDelta("전송 중 잘린 답변");
    return Promise.reject({ code: "CHATBOT_STREAM_FAILED" });
  };

  await ui.sendChatQuestion("합성 질문");

  const answer = ui.state.chat.messages[1];
  assert.equal(answer.text, "전송 중 잘린 답변");
  assert.equal(answer.error, "답변을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.");
  assert.equal(ui.chatbotAnswerText(answer), answer.error, "부분 답변보다 실패 문구가 우선해야 한다");
  assert.deepEqual(Array.from(streamedTexts), ["전송 중 잘린 답변"]);
  assert.equal(renderCount, 2, "최초 렌더와 종료 렌더만 허용해 입력 노드를 청크마다 교체하지 않는다");
  assert.equal(ui.state.chat.busy, false);
});
