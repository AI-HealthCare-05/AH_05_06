const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const FRONTEND = path.join(__dirname, '..');

function read(relativePath) {
  return fs.readFileSync(path.join(FRONTEND, relativePath), 'utf8');
}

function loadTransport(search = '?mock=1') {
  const context = vm.createContext({
    URLSearchParams,
    Promise,
    String,
    window: { location: { search, hostname: 'localhost', protocol: 'http:' } },
    setTimeout: (callback, _delay, ...args) => setTimeout(callback, 0, ...args),
  });
  vm.runInContext(read('js/chatbot-api.js'), context);
  return context;
}

function loadPatientChatUi(result) {
  class FakeElement {
    constructor() {
      this.children = [];
      this.listeners = {};
      this.style = {};
      this.value = '';
      this.className = '';
      this.textContent = '';
      this.classList = {
        values: new Set(),
        add: (...names) => names.forEach((name) => this.classList.values.add(name)),
        remove: (...names) => names.forEach((name) => this.classList.values.delete(name)),
        contains: (name) => this.classList.values.has(name),
      };
    }

    appendChild(child) {
      child.parent = this;
      this.children.push(child);
      return child;
    }

    addEventListener(name, listener) {
      this.listeners[name] = listener;
    }

    querySelectorAll(selector) {
      const found = [];
      const className = selector.startsWith('.') ? selector.slice(1) : null;
      const visit = (node) => {
        if (className && node.className.split(' ').includes(className)) found.push(node);
        node.children.forEach(visit);
      };
      this.children.forEach(visit);
      return found;
    }

    remove() {
      if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this);
    }

    setAttribute() {}
    focus() {}
  }

  const ids = {};
  for (const id of [
    'chat-backdrop',
    'chat-panel',
    'chat-close',
    'chat-messages',
    'chat-input',
    'chat-send',
    'chat-abort',
  ]) {
    ids[id] = new FakeElement();
  }
  const body = new FakeElement();
  const document = {
    body,
    createElement: () => new FakeElement(),
    getElementById: (id) => ids[id] || null,
  };
  const context = vm.createContext({
    AbortController,
    GUIDE_MOCK: true,
    Promise,
    alert() {},
    createFeedbackSubmissionId: () => 'synthetic-submission',
    document,
    setTimeout,
    streamChatbotAnswer: (_request, observer) => {
      observer.onDelta(result.answer);
      return Promise.resolve(result);
    },
    submitPatientFeedback: () => Promise.resolve(),
    window: {
      innerHeight: 800,
      innerWidth: 390,
      location: { search: '?mock=1' },
      matchMedia: () => ({ matches: false }),
      visualViewport: { height: 800 },
    },
    Fab: (_options, open) => {
      const el = new FakeElement();
      el.open = open;
      return { el };
    },
  });
  vm.runInContext(read('patient_wireframe/js/chat.js'), context);
  return { ids };
}

function allText(element) {
  return [element.textContent, ...element.children.flatMap(allText)].join('\n');
}

test('실제 guide.html은 공용 챗봇 전송 모듈 뒤에 P6 UI를 올린다', () => {
  const html = read('guide.html');
  const transportAt = html.indexOf('/js/chatbot-api.js');
  const chatAt = html.indexOf('/patient_wireframe/js/chat.js');

  assert.ok(transportAt >= 0);
  assert.ok(chatAt > transportAt);
});

test('P6 정본은 실환경에서도 시작하고 응답 계약 전체를 화면 상태에 반영한다', () => {
  const source = read('patient_wireframe/js/chat.js');

  assert.doesNotMatch(source, /!GUIDE_MOCK\) return/);
  assert.match(source, /streamChatbotAnswer\(/);
  assert.match(source, /answerMsg\.evidence = result\.evidence/);
  assert.match(source, /answerMsg\.source = result\.source/);
  assert.match(source, /answerMsg\.limitation = result\.limitation/);
  assert.match(source, /answerMsg\.groundedSection = result\.grounded_section/);
  assert.match(source, /answerMsg\.urgent = !!result\.urgent/);
  assert.match(source, /answerMsg\.fallback = !!result\.fallback/);
  assert.match(source, /chatbotErrorMessage\(error && error\.code\)/);
});

test('정상·응급·승인 근거 없음 목업 결과가 서로 구분된다', async () => {
  const transport = loadTransport();
  const normal = await transport.streamChatbotAnswer({ question: '출혈이 계속돼요' }, {});
  const urgent = await transport.streamChatbotAnswer({ question: '다리가 붓고 숨이 차요' }, {});
  const fallback = await transport.streamChatbotAnswer({ question: '오늘 날씨는 어때요?' }, {});

  assert.equal(normal.urgent, false);
  assert.equal(normal.fallback, false);
  assert.equal(urgent.urgent, true);
  assert.equal(urgent.grounded_section, 'emergency');
  assert.equal(fallback.fallback, true);
  assert.equal(fallback.grounded_section, null);
});

test('만료·없는 링크·API 미준비·응답 실패는 환자용 문구로 정규화된다', () => {
  const transport = loadTransport();

  for (const code of [
    'PATIENT_SESSION_EXPIRED',
    'LINK_EXPIRED',
    'LINK_NOT_FOUND',
    'CHATBOT_API_NOT_READY',
    'CHATBOT_STREAM_FAILED',
  ]) {
    const message = transport.chatbotErrorMessage(code);
    assert.equal(typeof message, 'string');
    assert.ok(message.length > 0);
    assert.doesNotMatch(message, /stack|trace|exception|token/i);
  }
});

test('?mock=1도 공통 응답 경로로 근거·한계·승인 섹션과 fallback을 그린다', async () => {
  const result = {
    answer: '승인 안내 범위의 합성 답변',
    evidence: '승인된 복약 안내',
    limitation: '승인된 안내 범위에서만 답변합니다.',
    grounded_section: 'medication',
    fallback: true,
    urgent: false,
  };
  const ui = loadPatientChatUi(result);
  ui.ids['chat-input'].value = '합성 질문';
  ui.ids['chat-send'].listeners.click();
  await new Promise((resolve) => setImmediate(resolve));

  const rendered = allText(ui.ids['chat-messages']);
  assert.match(rendered, /근거 · 승인된 복약 안내/);
  assert.match(rendered, /한계 · 승인된 안내 범위에서만 답변합니다\./);
  assert.match(rendered, /승인 안내 · 복약 안내/);
  assert.match(rendered, /승인된 안내 범위 밖이라 답할 수 없어요\./);
  assert.doesNotMatch(rendered, /승인 안내 · medication/);
});
