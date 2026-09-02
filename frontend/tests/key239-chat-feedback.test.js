const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..');

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), 'utf8');
}

test('환자 피드백 요청은 세션 쿠키만 사용하고 링크 토큰을 보내지 않는다', async () => {
  const calls = [];
  const storage = new Map();
  const context = vm.createContext({
    URLSearchParams,
    Uint8Array,
    setTimeout,
    location: { protocol: 'https:', hostname: 'patient.example' },
    sessionStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
    },
    window: {
      location: { search: '' },
      crypto: { randomUUID: () => '00000000-0000-4000-8000-000000000239' },
    },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, json: async () => ({ feedback_id: 239, saved: true }) };
    },
  });
  vm.runInContext(read('patient_wireframe/js/guide-api.js'), context);

  await context.submitPatientFeedback({
    submission_id: context.createFeedbackSubmissionId(),
    target: 'CHATBOT_RESPONSE',
    source_screen: 'P6',
    category: 'HELPFUL',
    response_ref: 'synthetic-response-ref',
  });

  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].url, '/api/v1/patient-feedback');
  assert.strictEqual(calls[0].options.credentials, 'include');
  assert.strictEqual(calls[0].options.method, 'POST');
  const body = JSON.parse(calls[0].options.body);
  assert.strictEqual(body.source_screen, 'P6');
  assert.strictEqual(body.response_ref, 'synthetic-response-ref');
  assert.ok(!('link_token' in body));
});

test('도움 평가 UI는 서버가 준 response_ref가 있는 답변에만 표시된다', () => {
  const source = read('patient_wireframe/js/chat.js');
  assert.match(source, /!msg\.error && !msg\.aborted && msg\.responseRef/);
  assert.match(source, /category: 'HELPFUL'/);
  assert.match(source, /category: 'UNHELPFUL'/);
  assert.match(source, /response_ref: msg\.responseRef/);
});

test('네트워크 재시도는 같은 submission_id를 다시 사용한다', () => {
  const source = read('patient_wireframe/js/chat.js');
  assert.match(source, /msg\.feedbackSubmissionId = msg\.feedbackSubmissionId \|\| createFeedbackSubmissionId\(\)/);
  assert.match(source, /msg\.feedbackState = 'error'/);
  assert.match(source, /'다시 시도'/);
});
