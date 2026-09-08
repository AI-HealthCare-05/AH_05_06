/* KEY-281 — 중단·늦은 조각·다시 시도를 **실제로 실리는 파일**에서 잰다.
 *
 * 여태 이것을 재던 두 검사(`chatbot-abort-state` · `chatbot-abort-retry`)가
 * `frontend/js/guide.js` 를 싣고 있었다. **그 파일은 어떤 화면도 안 싣는다** —
 * `guide.html` 이 싣는 것은 이름만 비슷한 `patient_wireframe/js/guide.js` 다.
 * 그래서 초록불이 지키고 있던 것은 사용자에게 가지 않는 코드였다.
 *
 * 옮겨 보니 옛 검사가 붙잡고 있던 계약 하나가 **실제 화면에서 깨져 있었다** —
 * 「다시 시도」가 치던 글자를 지웠다. 그 검사의 말이 이랬다.
 *
 *   보내는 함수가 초안을 지운다 — 재시도까지 지운다
 *
 * 지키는 자리가 아무도 안 보는 파일이면, 지켜지는지 아무도 모른다.
 *
 * ── 왜 원문 대조가 아니라 돌려 보는가 ────────────────────────────────
 * 이 여섯은 **타이밍**이다. 「가드가 코드에 있는가」를 재면 가드가 엉뚱한 값을
 * 비교해도 통과한다. 늦은 조각을 실제로 늦게 흘려 보내야 드러난다.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const FRONTEND = path.join(__dirname, "..");
const CHAT = "patient_wireframe/js/chat.js";

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

function allText(el) {
  return [el.textContent, ...el.children.flatMap(allText)].join("\n");
}

/** 스트림을 **손에 쥔 채** 화면을 세운다 — 조각·완성·실패를 원할 때 흘린다. */
function chatScreen() {
  const ids = {};
  for (const id of ["chat-backdrop", "chat-panel", "chat-close", "chat-messages", "chat-input", "chat-send", "chat-abort"]) {
    ids[id] = new FakeElement();
  }

  const streams = [];
  const context = vm.createContext({
    AbortController,
    GUIDE_MOCK: true,
    Promise,
    alert() {},
    createFeedbackSubmissionId: () => "synthetic",
    document: { body: new FakeElement(), createElement: () => new FakeElement(), getElementById: (id) => ids[id] || null },
    setTimeout,
    streamChatbotAnswer: (request, observer) => {
      let settle;
      const done = new Promise((resolve) => {
        settle = resolve;
      });
      streams.push({ request, observer, finish: (value) => settle(value || {}) });
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
  vm.runInContext(read(CHAT), context);

  const ask = (text) => {
    ids["chat-input"].value = text;
    ids["chat-input"].fire("input");
    ids["chat-send"].fire("click");
    return streams[streams.length - 1];
  };
  const abort = () => ids["chat-abort"].fire("click");
  const retryButtons = () => ids["chat-messages"].querySelectorAll(".chat-retry");
  const shown = () => allText(ids["chat-messages"]);

  return { ids, streams, ask, abort, retryButtons, shown, input: ids["chat-input"] };
}

/* ── 이 파일이 무엇을 싣는지부터 못 박는다 ─────────────────────────── */

test("① 실제 화면이 싣는 파일을 잰다 — 고아가 아니라", () => {
  const html = read("guide.html");
  assert.match(html, /src="\/patient_wireframe\/js\/chat\.js/, "화면이 이 파일을 안 싣는다");

  /* 고아 둘은 아직 지우지 않는다(처분은 이희진 님 확인 전까지 미룬다 — KEY-233).
     다만 **어떤 화면도 안 싣는다**는 사실은 여기서 못 박는다. 다시 실리기
     시작하면 이 검사가 울고, 그때 처분을 다시 이야기하면 된다. */
  for (const orphan of ["js/guide.js", "css/guide.css"]) {
    const loaded = fs
      .readdirSync(FRONTEND)
      .filter((f) => f.endsWith(".html"))
      /* **부분문자열로 재면 안 된다** — `/patient_wireframe/js/guide.js` 안에
         `/js/guide.js` 가 그대로 들어 있어서, 실제로 싣는 파일이 고아로 잡힌다. */
      .filter((f) => new RegExp(`(src|href)="/${orphan.replace(".", "\\.")}[?"]`).test(read(f)));
    assert.deepEqual(loaded, [], `${orphan} 가 다시 실린다 — 검사 겨냥을 다시 봐야 한다`);
  }
});

/* ── 중단 ─────────────────────────────────────────────────────────── */

test("② 중단한 뒤 늦게 온 조각은 답변에 안 붙는다", async () => {
  const s = chatScreen();
  const stream = s.ask("약을 언제 먹나요");
  stream.observer.onDelta("정해진 시간에");

  s.abort();
  stream.observer.onDelta(" 이 문장은 늦었다");
  stream.finish({});
  await new Promise(setImmediate);

  assert.ok(!s.shown().includes("늦었다"), `중단 뒤 온 조각이 붙었다 —\n${s.shown()}`);
});

test("③ 중단한 뒤 늦게 온 완성 신호가 화면을 되살리지 않는다", async () => {
  const s = chatScreen();
  const stream = s.ask("약을 언제 먹나요");
  stream.observer.onDelta("정해진 시간에");
  s.abort();

  stream.finish({ answer: "되살아난 답", source: "허가정보" });
  await new Promise(setImmediate);

  assert.ok(!s.shown().includes("되살아난 답"), `늦은 완성이 화면을 되살렸다 —\n${s.shown()}`);
  assert.match(s.shown(), /중단했어요/, "중단 표시가 사라졌다");
});

test("④ 중단하면 마지막 답변에 중단 표시가 남는다", () => {
  const s = chatScreen();
  const stream = s.ask("약을 언제 먹나요");
  stream.observer.onDelta("정해진 시간에");
  s.abort();

  assert.match(s.shown(), /여기서 중단했어요/, "받던 것이 있으면 그 뒤에 표시가 붙어야 한다");
});

test("⑤ 받은 것이 없을 때 중단해도 터지지 않는다", () => {
  const s = chatScreen();
  s.ask("약을 언제 먹나요");

  assert.doesNotThrow(() => s.abort(), "조각을 하나도 못 받은 채 중단하면 터진다");
  assert.match(s.shown(), /중단했어요/, "중단했다는 말이 없다");
});

test("⑥ 중단하고 새 질문을 한 뒤 온 늦은 조각은 옛 답도 새 답도 안 건드린다", async () => {
  const s = chatScreen();
  const first = s.ask("첫 질문");
  first.observer.onDelta("첫 답 조각");
  s.abort();

  const second = s.ask("둘째 질문");
  second.observer.onDelta("둘째 답");

  /* 첫 요청이 이제야 조각과 완성을 흘린다 — 좀비다. */
  first.observer.onDelta(" 좀비 조각");
  first.finish({ answer: "좀비 완성" });
  /* 흐르는 조각을 화면에 얹는 것은 `updateStream` 이고 그건 브라우저가 할 일이다.
     여기서는 끝난 뒤 다시 그려진 것을 본다 — 새 답이 살아 있어야 한다. */
  second.finish({ answer: "둘째 답" });
  await new Promise(setImmediate);

  const said = s.shown();
  assert.ok(!said.includes("좀비 조각"), `늦은 조각이 붙었다 —\n${said}`);
  assert.ok(!said.includes("좀비 완성"), `늦은 완성이 붙었다 —\n${said}`);
  assert.match(said, /둘째 답/, "새 답이 사라졌다");
});

/* ── 다시 시도 ───────────────────────────────────────────────────── */

test("⑦ **다시 시도가 치던 글자를 지우지 않는다**", async () => {
  /* 옛 검사가 붙잡고 있던 계약이고, 실제 화면에서 깨져 있던 자리다.
     답이 실패해 다음 질문을 치던 환자가 「다시 시도」를 누르면, 지워야 할 것은
     방금 보낸 질문이지 치고 있던 글자가 아니다. */
  const s = chatScreen();
  const stream = s.ask("약을 언제 먹나요");
  stream.observer.onDelta("정해진");
  s.abort();

  s.input.value = "치고 있던 다음 질문";
  s.input.fire("input");

  const retry = s.retryButtons();
  assert.equal(retry.length, 1, `다시 시도 단추가 ${retry.length}개다`);
  retry[0].fire("click");

  assert.equal(s.input.value, "치고 있던 다음 질문", "다시 시도가 치던 글자를 지웠다");
});

test("⑧ 입력칸에서 보낸 것은 지운다 — 안 지우면 두 번 보낸다", () => {
  const s = chatScreen();
  s.ask("약을 언제 먹나요");

  assert.equal(s.input.value, "", "보낸 질문이 입력칸에 남았다");
});

test("⑨ 보내지 못한 것은 지우지도 않는다", () => {
  /* 도는 중에 한 번 더 누르면 `sendQuestion` 이 그냥 돌아간다. 그때 입력칸을
     비우면 **보내지도 않고 글자만 사라진다.** */
  const s = chatScreen();
  s.ask("첫 질문");

  s.input.value = "도는 중에 친 것";
  s.input.fire("input");
  s.ids["chat-send"].fire("click");

  assert.equal(s.input.value, "도는 중에 친 것", "안 보냈는데 글자를 지웠다");
});

test("⑩ 다시 시도는 옛 질문과 답을 걷고 다시 묻는다", async () => {
  const s = chatScreen();
  const stream = s.ask("약을 언제 먹나요");
  stream.observer.onDelta("정해진");
  s.abort();

  const before = s.streams.length;
  s.retryButtons()[0].fire("click");

  assert.equal(s.streams.length, before + 1, "다시 묻지 않았다");
  assert.equal(s.streams[before].request.question, "약을 언제 먹나요", "다른 것을 묻는다");

  const rows = s.ids["chat-messages"].querySelectorAll(".chat-row");
  assert.equal(rows.length, 2, `옛 질문·답을 안 걷어서 줄이 ${rows.length}개다`);
});
