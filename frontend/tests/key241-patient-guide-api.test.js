/* KEY-241 최종 환자 와이어프레임과 PatientGuideResponse 계약. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const FRONTEND = path.join(__dirname, '..');
const API_SOURCE = fs.readFileSync(
  path.join(FRONTEND, 'patient_wireframe/js/guide-api.js'),
  'utf8',
);

function storage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
  };
}

function payload(sections) {
  return {
    version: 1,
    approved_at: '2026-09-01T09:00:00+09:00',
    expires_at: '2026-09-08T09:00:00+09:00',
    sections,
    demo_only: true,
  };
}

function load(options = {}) {
  const box = options.storage || storage();
  let requested = null;
  const context = vm.createContext({
    URLSearchParams,
    Date,
    Promise,
    setTimeout,
    sessionStorage: box,
    location: {
      protocol: options.protocol || 'https:',
      hostname: options.hostname || 'localhost',
    },
    window: {
      location: { search: options.search || '' },
    },
    fetch(url, requestOptions) {
      requested = { url, requestOptions };
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(options.response || payload([])),
      });
    },
  });
  vm.runInContext(API_SOURCE, context);
  return { context, box, requested: () => requested };
}

test('localhost와 file 화면도 명시적인 mock=1 없이는 목업을 켜지 않는다', () => {
  assert.equal(load({ hostname: 'localhost' }).context.GUIDE_MOCK, false);
  assert.equal(load({ protocol: 'file:' }).context.GUIDE_MOCK, false);
  assert.equal(load({ search: '?mock=1' }).context.GUIDE_MOCK, true);
});

test('목업도 PatientGuideResponse와 같은 필드만 가진다', () => {
  const { context } = load({ search: '?mock=1' });
  const expected = ['approved_at', 'demo_only', 'expires_at', 'sections', 'version'];

  Object.values(context.MOCK_GUIDES).forEach((guide) => {
    assert.deepEqual(Object.keys(guide).sort(), expected);
    guide.sections.forEach((section) => {
      assert.deepEqual(Object.keys(section).sort(), ['body', 'key']);
    });
  });
});

test('실제 API 응답을 P2~P5 화면 모델로 매핑하고 토큰은 저장하지 않는다', async () => {
  const token = 'synthetic-key241-link-token';
  const response = payload([
    { key: 'medication', body: '승인 복약 안내' },
    { key: 'caution', body: '주의 문장' },
    { key: 'emergency', body: '응급 문장' },
    { key: 'life', body: '수면 안내\n운동 안내' },
    { key: 'messages', body: '병원 안내' },
  ]);
  const box = storage();
  const loaded = load({ response, storage: box });

  const result = await loaded.context.fetchGuide(token);

  assert.equal(loaded.requested().url, '/api/v1/guides/' + token);
  assert.equal(loaded.requested().requestOptions.credentials, 'include');
  assert.equal(result.stat.body, '승인 복약 안내');
  assert.equal(result.guide.summary, '승인 복약 안내');
  assert.deepEqual(JSON.parse(JSON.stringify(result.care.danger)), ['응급 문장']);
  assert.deepEqual(
    JSON.parse(JSON.stringify(result.life.axes['생활관리'].p)),
    ['수면 안내', '운동 안내'],
  );
  assert.equal(Array.from(box.values.values()).includes(token), false);
});

test('누락 섹션은 화면 중단 대신 비어 있는 안전 모델이 된다', () => {
  const { context } = load();
  const result = context.adaptGuideResponse(payload([]));

  assert.equal(result.stat.body, '');
  assert.equal(result.guide.summary, '');
  assert.deepEqual(JSON.parse(JSON.stringify(result.care.blocks)), []);
  assert.deepEqual(JSON.parse(JSON.stringify(result.life.axes)), {});
});

test('알 수 없는 DTO 필드와 중복 섹션은 계약 오류로 차단한다', () => {
  const { context } = load();
  const extra = { ...payload([]), patient_name: '노출 금지' };
  assert.throws(
    () => context.adaptGuideResponse(extra),
    (error) => error.code === 'GUIDE_CONTRACT_MISMATCH',
  );

  assert.throws(
    () => context.adaptGuideResponse(payload([
      { key: 'medication', body: '첫 번째' },
      { key: 'medication', body: '두 번째' },
    ])),
    (error) => error.code === 'GUIDE_CONTRACT_MISMATCH',
  );
});

test('서버 본문의 HTML과 합성 접두어를 그대로 화면에 삽입하지 않는다', () => {
  const { context } = load();
  const result = context.adaptGuideResponse(payload([
    { key: 'medication', body: '[합성 복약 안내]\n<img src=x onerror=alert(1)>승인 문구' },
  ]));

  assert.doesNotMatch(result.guide.summary, /\[합성/);
  assert.doesNotMatch(result.guide.summary, /<img/);
  assert.match(result.guide.summary, /&lt;img/);
});

test('실제 /guide.html은 최종 와이어프레임 자산을 사용한다', () => {
  const html = fs.readFileSync(path.join(FRONTEND, 'guide.html'), 'utf8');
  const chat = fs.readFileSync(path.join(FRONTEND, 'patient_wireframe/js/chat.js'), 'utf8');

  assert.match(html, /\/patient_wireframe\/js\/guide-api\.js/);
  assert.match(html, /\/patient_wireframe\/js\/guide\.js/);
  assert.match(html, /id="guide-body"/);
  assert.match(chat, /!GUIDE_MOCK\) return/);
});
