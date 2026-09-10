/* KEY-95 UI와 KEY-96 단일 응답 API 어댑터 계약. */

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
    window: { location: { search, hostname: "localhost", protocol: "http:" } },
    setTimeout: (fn, _ms, ...args) => setTimeout(fn, 0, ...args),
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "chatbot-api.js"), "utf8"), context);
  return context;
}


test("합성 승인 안내 답변은 여러 조각으로 스트리밍되고 근거·출처·한계를 함께 준다", async () => {
  const api = loadApi();
  const chunks = [];
  let completed = null;

  const result = await api.streamChatbotAnswer(
    { question: "출혈이 있는데 약을 끊어도 되나요?" },
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

test("승인 컨텍스트를 사용할 수 없는 링크 오류는 내부 정보 없이 다음 행동을 안내한다", () => {
  const api = loadApi();

  assert.equal(
    api.chatbotErrorMessage("LINK_EXPIRED"),
    "안내 링크가 만료되어 답변을 만들 수 없어요. 새 안내 문자를 받은 뒤 다시 이용해 주세요.",
  );
  assert.equal(
    api.chatbotErrorMessage("LINK_NOT_FOUND"),
    "승인된 안내를 확인할 수 없어 답변을 만들 수 없어요. 담당 병원에 문의해 주세요.",
  );
  assert.equal(
    api.chatbotErrorMessage("SYNTHETIC_INTERNAL_DATABASE_ERROR"),
    "답변을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.",
  );
});

test("KEY-95 UI는 근거·출처·한계를 **실제 렌더 경로**에 둔다", () => {
  /* 전에는 `js/guide.js` 를 봤다 — 아무 화면도 안 싣는 고아였다 (KEY-281).
     `guide.html` 이 싣는 챗봇은 `patient_wireframe/js/chat.js` 이고, 라벨
     모양이 다르다(`📎`·`한계 · ` 대신 `근거 · `·`한계 · ` 한 벌). 지키려던
     것은 라벨의 글자가 아니라 **셋을 환자에게 보인다**는 계약이다. */
  const chat = fs.readFileSync(path.join(__dirname, "..", "patient_wireframe", "js", "chat.js"), "utf8");

  assert.match(chat, /'출처 · ' \+ msg\.source/, "출처를 안 보인다");
  assert.match(chat, /\['근거', msg\.evidence\]/, "근거를 안 보인다");
  assert.match(chat, /\['한계', msg\.limitation\]/, "한계를 안 보인다");
  /* 승인 범위 밖이면 그렇다고 말한다 — 지어낸 답을 안 준다 */
  assert.match(chat, /승인된 안내 범위 밖이라 답할 수 없어요/, "범위 밖을 안 말한다");
});

/* 「delta 뒤 스트림 실패」와 그 이웃은 실리는 파일에서 잰다 —
   `key281-chat-abort-on-real-path.test.js` ②③⑦ 이 같은 자리를 **돌려 본다.**
   여기 있던 판은 아무 화면도 안 싣는 `js/guide.js` 를 vm 에 올리고 있었다. */


test("실제 전송은 환자 세션 쿠키를 사용하고 질문만 본문에 담아 UI 어댑터로 전달한다", async () => {
  let request = null;
  const response = {
    answer: "합성 승인 안내 기반 답변",
    evidence: "복약 안내 · 합성 승인 문구",
    source: "담당 의료진이 승인한 진료 안내",
    limitation: "승인된 안내 범위에서만 답합니다.",
    urgent: false,
    fallback: false,
    grounded_section: "medication",
  };
  const context = vm.createContext({
    URLSearchParams,
    Promise,
    String,
    fetch: async (url, options) => {
      request = { url, options };
      return { ok: true, json: async () => response };
    },
    window: { location: { search: "" } },
    setTimeout,
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "chatbot-api.js"), "utf8"), context);
  const deltas = [];
  let completed = null;

  const result = await context.streamChatbotAnswer(
    { question: "약은 언제 먹나요?" },
    {
      onDelta: (chunk) => deltas.push(chunk),
      onComplete: (value) => {
        completed = value;
      },
    },
  );

  assert.equal(request.url, "/api/v1/chatbot/responses");
  assert.deepEqual(JSON.parse(request.options.body), {
    question: "약은 언제 먹나요?",
  });
  assert.equal(request.options.credentials, "include");
  assert.deepEqual(deltas, [response.answer]);
  assert.equal(completed, result);
});

test("실환경 네트워크 실패는 재시도 가능한 스트림 실패로 분류한다", async () => {
  const context = vm.createContext({
    URLSearchParams,
    Promise,
    String,
    fetch: async () => {
      throw new TypeError("synthetic network failure");
    },
    window: { location: { search: "" } },
    setTimeout,
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "chatbot-api.js"), "utf8"), context);

  await assert.rejects(
    () => context.streamChatbotAnswer({ question: "합성 질문" }, {}),
    (error) => error.code === "CHATBOT_STREAM_FAILED",
  );
});

test("응답 관찰자 오류는 API 준비 오류로 바꾸지 않고 그대로 전달한다", async () => {
  const observerError = new Error("synthetic observer failure");
  const context = vm.createContext({
    URLSearchParams,
    Promise,
    String,
    fetch: async () => ({ ok: true, json: async () => ({ answer: "합성 답변" }) }),
    window: { location: { search: "" } },
    setTimeout,
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "chatbot-api.js"), "utf8"), context);

  await assert.rejects(
    () => context.streamChatbotAnswer(
      { question: "합성 질문" },
      { onComplete: () => { throw observerError; } },
    ),
    (error) => error === observerError,
  );
});
