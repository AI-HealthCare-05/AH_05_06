/* 물음 하나에 열쇠 하나, **다시 시도해도 같은 것** — KEY-328.
 *
 * 화면은 `state.busy` 로 두 번 누름을 막는다. 그런데 **서버가 답을 만든 뒤
 * 응답이 유실되면** 화면에는 오류가 뜨고 잠금은 이미 풀려 있다. 환자가
 * 「다시 시도」를 누르면 같은 물음이 한 번 더 가고 모델도 한 번 더 불린다 —
 * 돈이 두 번 나가고 이용 기록이 두 줄이 된다.
 *
 * 그래서 열쇠는 **물음에 붙고 재시도에 살아남아야** 한다.
 *
 * 서버 쪽이 붙은 뒤로 하나가 더 늘었다 — **다 쓴 열쇠를 버리는 것**이다.
 * 서버가 「이미 답했다」거나 「그 열쇠는 다른 물음 것이다」라고 하면 그 열쇠로는
 * 무엇을 해도 409 다. 안 버리면 「다시 시도」가 영원히 같은 오류를 받는다.
 *
 * 원문 대조가 아니라 돌려 보는 까닭은 `key281` 과 같다 — 「코드에 있는가」를
 * 재면 엉뚱한 값을 실어도 통과한다. `retryAnswer` 는 열쇠가 붙은 줄을
 * `splice` 로 지우므로, 실제로 흘려 봐야 살아남는지 드러난다.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const FRONTEND = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(FRONTEND, rel), "utf8");
}

class FakeElement {
  constructor() {
    this.children = [];
    this.listeners = {};
    this.style = {};
    this.value = "";
    this.className = "";
    this.textContent = "";
    this.disabled = false;
    this.classList = {
      values: new Set(),
      add: (...n) => n.forEach((x) => this.classList.values.add(x)),
      remove: (...n) => n.forEach((x) => this.classList.values.delete(x)),
      contains: (x) => this.classList.values.has(x),
    };
  }
  appendChild(child) {
    child.parent = this;
    this.children.push(child);
    return child;
  }
  addEventListener(name, fn) {
    (this.listeners[name] = this.listeners[name] || []).push(fn);
  }
  fire(name, event) {
    (this.listeners[name] || []).forEach((fn) => fn(event || {}));
  }
  querySelectorAll(selector) {
    const wanted = selector.startsWith(".") ? selector.slice(1) : null;
    const found = [];
    const walk = (node) => {
      if (wanted && node.className.split(" ").includes(wanted)) found.push(node);
      node.children.forEach(walk);
    };
    this.children.forEach(walk);
    return found;
  }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this);
  }
  setAttribute() {}
  focus() {}
}

/** 화면을 세우고 스트림을 손에 쥔다. 열쇠 생성기는 **부를 때마다 다른 값**을
    준다 — 같은 값을 주면 「되썼다」와 「새로 만들었다」가 구분이 안 된다. */
function chatScreen() {
  const ids = {};
  for (const id of ["chat-backdrop", "chat-panel", "chat-close", "chat-messages", "chat-input", "chat-send", "chat-abort"]) {
    ids[id] = new FakeElement();
  }

  const streams = [];
  let made = 0;
  const context = vm.createContext({
    AbortController,
    GUIDE_MOCK: true,
    Promise,
    alert() {},
    createFeedbackSubmissionId: () => `key-${++made}`,
    document: { body: new FakeElement(), createElement: () => new FakeElement(), getElementById: (id) => ids[id] || null },
    setTimeout,
    streamChatbotAnswer: (request, observer) => {
      let settle;
      let reject;
      const done = new Promise((resolve, fail) => {
        settle = resolve;
        reject = fail;
      });
      streams.push({ request, observer, finish: (v) => settle(v || {}), fail: (e) => reject(e) });
      return done;
    },
    submitPatientFeedback: () => Promise.resolve(),
    window: {
      innerHeight: 800,
      innerWidth: 390,
      location: { search: "?mock=1" },
      matchMedia: () => ({ matches: false }),
      visualViewport: { height: 800 },
    },
    Fab: (_o, open) => ({ el: Object.assign(new FakeElement(), { open }) }),
  });

  const heldStream = context.streamChatbotAnswer;
  vm.runInContext(read("js/chatbot-api.js"), context);
  context.streamChatbotAnswer = heldStream;
  vm.runInContext(read("patient_wireframe/js/chat.js"), context);

  const ask = (text) => {
    ids["chat-input"].value = text;
    ids["chat-input"].fire("input");
    ids["chat-send"].fire("click");
    return streams[streams.length - 1];
  };
  const retryButtons = () => ids["chat-messages"].querySelectorAll(".chat-retry");
  return { ids, streams, ask, retryButtons, made: () => made };
}

test("물음을 보내면 열쇠가 함께 간다", () => {
  const screen = chatScreen();

  const stream = screen.ask("약은 언제 먹나요?");

  assert.ok(stream.request.submissionId, "열쇠 없이 보냈다");
  assert.equal(screen.made(), 1, "열쇠를 한 번만 만든다");
});

test("**다시 시도해도 같은 열쇠다** — 모델을 두 번 부르지 않게", async () => {
  const screen = chatScreen();

  const first = screen.ask("약은 언제 먹나요?");
  const firstKey = first.request.submissionId;
  first.fail(new Error("stream died"));
  await new Promise((r) => setTimeout(r, 0));

  const retry = screen.retryButtons()[0];
  assert.ok(retry, "실패했는데 다시 시도 단추가 없다");
  retry.fire("click");

  const second = screen.streams[screen.streams.length - 1];
  assert.notEqual(second, first, "다시 보내지 않았다");
  assert.equal(second.request.submissionId, firstKey, "다시 시도가 새 열쇠로 갔다");
  assert.equal(screen.made(), 1, "재시도인데 열쇠를 새로 만들었다");
});

test("다른 물음은 다른 열쇠다 — 열쇠 하나로 두 물음을 덮지 않게", async () => {
  const screen = chatScreen();

  const first = screen.ask("약은 언제 먹나요?");
  const firstKey = first.request.submissionId;
  first.finish({ answer: "식후 30분에 드세요." });
  await new Promise((r) => setTimeout(r, 0));

  const second = screen.ask("아프면 어떻게 하나요?");

  assert.notEqual(second.request.submissionId, firstKey, "다른 물음이 같은 열쇠로 갔다");
});

test("보내는 몸에 `submission_id` 로 실린다 — 서버가 읽는 이름으로", async () => {
  /* 화면 안에서만 맞고 전송에서 이름이 갈리면 서버는 못 받는다. 실제 전송
     함수(`apiChatbotStreamTransport`)를 가짜 `fetch` 로 돌려 본다. */
  let sent = null;
  const context = vm.createContext({
    Promise,
    window: { location: { search: "" } },
    URLSearchParams,
    setTimeout,
    fetch: (_url, options) => {
      sent = JSON.parse(options.body);
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ answer: "" }) });
    },
  });
  vm.runInContext(read("js/chatbot-api.js"), context);

  await context.apiChatbotStreamTransport({ question: "약은 언제 먹나요?", submissionId: "key-1" }, {});
  assert.deepEqual(sent, { question: "약은 언제 먹나요?", submission_id: "key-1" });

  await context.apiChatbotStreamTransport({ question: "약은 언제 먹나요?" }, {});
  assert.deepEqual(sent, { question: "약은 언제 먹나요?" }, "열쇠가 없으면 그 칸도 없다");
});

test("**처리 중**이라는 409 에는 같은 열쇠로 다시 간다", async () => {
  /* 앞의 요청이 아직 답하는 중이다. 같은 열쇠로 다시 물어야 **그 답**을 받는다 —
     새 열쇠로 가면 모델이 한 번 더 불리고 이용 기록도 두 줄이 된다. */
  const screen = chatScreen();

  const first = screen.ask("약은 언제 먹나요?");
  const firstKey = first.request.submissionId;
  first.fail({ code: "CHATBOT_ANSWER_IN_PROGRESS" });
  await new Promise((r) => setTimeout(r, 0));

  screen.retryButtons()[0].fire("click");

  const second = screen.streams[screen.streams.length - 1];
  assert.equal(second.request.submissionId, firstKey, "처리 중인데 새 열쇠로 갔다");
  assert.equal(screen.made(), 1, "열쇠를 새로 만들었다");
});

test("**다 쓴 열쇠는 버린다** — 이미 답한 물음·어긋난 물음", async () => {
  for (const code of ["CHATBOT_ANSWER_EXPIRED", "CHATBOT_SUBMISSION_CONFLICT"]) {
    const screen = chatScreen();

    const first = screen.ask("약은 언제 먹나요?");
    const firstKey = first.request.submissionId;
    first.fail({ code });
    await new Promise((r) => setTimeout(r, 0));

    screen.retryButtons()[0].fire("click");

    const second = screen.streams[screen.streams.length - 1];
    assert.notEqual(second.request.submissionId, firstKey, `${code} 인데 다 쓴 열쇠로 다시 갔다`);
    assert.equal(screen.made(), 2, `${code} 뒤에 새 열쇠를 안 만들었다`);
  }
});

test("겹친 요청 셋에 서로 다른 문구를 준다", () => {
  /* 환자가 해야 할 일이 다르다 — 기다린다 · 다시 묻는다 · 다시 묻는다.
     한 문구로 뭉치면 「잠시 뒤 다시」만 보고 계속 눌러 409 를 반복한다. */
  const context = vm.createContext({ Promise, window: { location: { search: "" } }, URLSearchParams, setTimeout });
  vm.runInContext(read("js/chatbot-api.js"), context);
  const say = (code) => vm.runInContext(`chatbotErrorMessage(${JSON.stringify(code)})`, context);

  const fallback = say("SOMETHING_ELSE");
  const messages = ["CHATBOT_ANSWER_IN_PROGRESS", "CHATBOT_ANSWER_EXPIRED", "CHATBOT_SUBMISSION_CONFLICT"].map(say);

  for (const message of messages) {
    assert.notEqual(message, fallback, "겹친 요청인데 기본 문구를 준다");
  }
  assert.equal(new Set(messages).size, 3, "셋이 같은 말을 한다");
  assert.match(messages[0], /기다|잠시/, "처리 중인데 다시 물으라고 한다");
});
