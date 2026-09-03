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
    window: { location: { search } },
    setTimeout: (callback, _delay, ...args) => setTimeout(callback, 0, ...args),
  });
  vm.runInContext(read('js/chatbot-api.js'), context);
  return context;
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
