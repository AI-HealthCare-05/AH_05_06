/* KEY-241 최종 환자 와이어프레임과 PatientGuideResponse v3 계약. */
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
const GUIDE_SOURCE = fs.readFileSync(
  path.join(FRONTEND, 'patient_wireframe/js/guide.js'),
  'utf8',
);
const GUIDE_CSS = fs.readFileSync(
  path.join(FRONTEND, 'patient_wireframe/css/guide.css'),
  'utf8',
);
const FOOTER_SOURCE = fs.readFileSync(
  path.join(FRONTEND, 'patient_wireframe/component/guide-footer.js'),
  'utf8',
);
const OTP_SOURCE = fs.readFileSync(
  path.join(FRONTEND, 'patient_wireframe/html/otp.html'),
  'utf8',
);
const OTP_VERIFY_SOURCE = fs.readFileSync(
  path.join(FRONTEND, 'patient_wireframe/html/otp-verify.html'),
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

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function payload(sections = [], overrides = {}) {
  return {
    version: 1,
    approved_at: '2026-09-01T09:00:00+09:00',
    expires_at: '2026-09-08T09:00:00+09:00',
    sections,
    demo_only: true,
    ...overrides,
  };
}

function richPayload(overrides = {}) {
  return payload([
    { key: 'medication', body: '승인 복약 안내' },
    { key: 'caution', body: '승인 주의 문장' },
    { key: 'emergency', body: '승인 응급 문장' },
    { key: 'life', body: '승인 생활 안내' },
    { key: 'messages', body: '승인 병원 안내' },
  ], {
    visit: '2026.08.13',
    clinic: '여성의원',
    disease: '자궁내막증 · 비잔정 복용 중',
    stat: {
      drugName: '비잔정 2mg',
      drugSub: '성분 · 디에노게스트 · 1일 1회 · 84일분',
      prescribed: 84,
      dayOn: 12,
      remaining: 72,
      pct: 14,
      out: '11월 5일경 약이 소진돼요',
      why: '병변이 다시 자라지 않게 하는 약이에요.',
    },
    guide: {
      summary: '진료 요약',
      goals: [
        {
          n: '빈혈 Hb',
          a: '10.2',
          now: '10.4',
          t: '12',
          hasChart: true,
          rangeLabel: '목표를 가운데 두고 본 지금 값',
        },
        {
          n: 'AMH 곧 나와요',
          now: null,
          hasChart: false,
          rangeLabel: '검사 결과 대기 중',
        },
      ],
      goalSay: '검사 결과가 있는 목표만 눈금으로 보여 드려요.',
      drug: { n: '비잔정 2mg', s: '성분 · 디에노게스트', d: '1일 1회 · 84일분' },
      why: ['임의로 약을 끊지 마세요.'],
      how: '매일 같은 시간에 드세요.',
      next: '3개월 뒤 재진 예정이에요.',
    },
    care: {
      title: '비잔정 2mg 드시는 동안',
      blocks: [{ t: '흔하고 괜찮은 반응', p: ['처음에는 피가 조금 비칠 수 있어요.'] }],
      danger: ['출혈이 많아 어지러우면 바로 병원에 연락하세요.'],
      ask: '심한 복통이 있으면 연락 주세요.',
    },
    life: {
      sub: '자궁내막증 · 비잔정 복용 중',
      challenges: [['밤 11시 전에 잠들기', '주 5일']],
      axes: {
        '수면': {
          chal: '밤 11시 전에 잠들기',
          goal: '주 5일',
          title: '수면 관리',
          p: ['규칙적인 수면 시간을 유지해 주세요.'],
        },
      },
    },
    chat: { chips: ['내 약이 뭐였죠?', '언제까지 먹나요?'] },
    ...overrides,
  });
}

function load(options = {}) {
  const box = options.storage || storage();
  let requested = null;
  const context = vm.createContext({
    URLSearchParams,
    Date,
    Intl,
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
        json: () => Promise.resolve(options.response || payload()),
      });
    },
  });
  vm.runInContext(API_SOURCE, context);
  return { context, box, requested: () => requested };
}

test('localhost와 file 화면도 현재 URL의 mock=1 없이는 목업을 켜지 않는다', () => {
  const box = storage({ guide_mock: '1', GUIDE_MOCK: '1', mock: '1' });

  assert.equal(load({ hostname: 'localhost', storage: box }).context.GUIDE_MOCK, false);
  assert.equal(load({ protocol: 'file:', storage: box }).context.GUIDE_MOCK, false);
  assert.equal(load({ search: '?mock=1', storage: box }).context.GUIDE_MOCK, true);
  assert.equal(load({ storage: box }).context.GUIDE_MOCK, false);
  assert.doesNotMatch(API_SOURCE, /sessionStorage\.setItem/);
});

test('v3 목업 응답도 공개 DTO로 검증되며 환자 PII를 만들지 않는다', () => {
  const { context } = load({ search: '?mock=1' });
  const allowed = [
    'approved_at', 'care', 'chat', 'clinic', 'demo_only', 'disease',
    'expires_at', 'guide', 'life', 'sections', 'stat', 'version', 'visit',
  ];

  Object.values(context.MOCK_GUIDES).forEach((guide) => {
    assert.equal(Object.keys(guide).every((key) => allowed.includes(key)), true);
    assert.equal(Object.hasOwn(guide, 'patient'), false);
    assert.equal(Object.hasOwn(guide, 'patient_name'), false);
    assert.doesNotThrow(() => context.adaptGuideResponse(guide));
    assert.equal(context.adaptGuideResponse(guide).patient, '');
  });
});

test('v3 중첩 DTO를 P2~P5 화면 모델로 손실 없이 매핑한다', () => {
  const { context } = load();
  const result = plain(context.adaptGuideResponse(richPayload()));

  assert.equal(result.visit, '2026.08.13');
  assert.equal(result.clinic, '여성의원');
  assert.equal(result.patient, '');
  assert.equal(result.disease, '자궁내막증 · 비잔정 복용 중');
  assert.deepEqual(result.stat, {
    drugName: '비잔정 2mg',
    drugSub: '성분 · 디에노게스트 · 1일 1회 · 84일분',
    prescribed: 84,
    dayOn: 12,
    remaining: 72,
    pct: 14,
    out: '11월 5일경 약이 소진돼요',
    why: '병변이 다시 자라지 않게 하는 약이에요.',
    body: '승인 복약 안내',
  });
  assert.equal(result.guide.goals.length, 2);
  assert.equal(result.guide.goals[0].hasChart, true);
  assert.equal(result.guide.goals[1].hasChart, false);
  assert.equal(result.guide.goalSay, '검사 결과가 있는 목표만 눈금으로 보여 드려요.');
  assert.deepEqual(result.guide.drug, {
    n: '비잔정 2mg',
    s: '성분 · 디에노게스트',
    d: '1일 1회 · 84일분',
  });
  assert.deepEqual(result.care.blocks[0], {
    t: '흔하고 괜찮은 반응',
    p: ['처음에는 피가 조금 비칠 수 있어요.'],
  });
  assert.deepEqual(result.life.challenges, [['밤 11시 전에 잠들기', '주 5일']]);
  assert.deepEqual(result.life.axes['수면'], {
    chal: '밤 11시 전에 잠들기',
    goal: '주 5일',
    title: '수면 관리',
    p: ['규칙적인 수면 시간을 유지해 주세요.'],
  });
  assert.deepEqual(result.chat.chips, ['내 약이 뭐였죠?', '언제까지 먹나요?']);
});

test('UTC 승인 시각은 진료소 시간대의 승인일로 표시한다', () => {
  const { context } = load();
  const result = plain(context.adaptGuideResponse(payload([], {
    approved_at: '2026-08-31T18:00:00+00:00',
  })));

  assert.equal(result.approvedAt, '2026.09.01');
  assert.throws(
    () => context.adaptGuideResponse(payload([], { approved_at: '2026-09-01T03:00:00' })),
    (error) => error.code === 'GUIDE_CONTRACT_MISMATCH',
  );
});

test('기존 sections-only 응답도 승인 문구 기반 안전 모델로 호환한다', () => {
  const { context } = load();
  const result = plain(context.adaptGuideResponse(payload([
    { key: 'medication', body: '승인 복약 안내' },
    { key: 'caution', body: '주의 첫 줄\n주의 둘째 줄' },
    { key: 'emergency', body: '응급 문장' },
    { key: 'life', body: '수면 안내\n운동 안내' },
    { key: 'messages', body: '병원 안내' },
  ])));

  assert.equal(result.visit, '');
  assert.equal(result.stat.drugName, '복약 현황');
  assert.equal(result.stat.body, '승인 복약 안내');
  assert.equal(result.guide.summary, '승인 복약 안내');
  assert.equal(result.guide.next, '');
  assert.deepEqual(result.care.blocks, [
    { t: '주의사항', p: ['주의 첫 줄', '주의 둘째 줄'] },
  ]);
  assert.deepEqual(result.care.danger, ['응급 문장']);
  assert.equal(result.care.ask, '');
  assert.deepEqual(result.life.axes['생활관리'].p, ['수면 안내', '운동 안내']);
  assert.deepEqual(result.chat.chips, []);
});

test('선택 구조가 없거나 비어 있어도 200 응답용 빈 상태를 만든다', () => {
  const { context } = load();
  const omitted = plain(context.adaptGuideResponse(payload()));
  const explicitEmpty = plain(context.adaptGuideResponse(payload([], {
    visit: null,
    clinic: null,
    disease: null,
    stat: null,
    guide: { goals: [], why: [] },
    care: { blocks: [], danger: [] },
    life: { challenges: [], axes: {} },
    chat: { chips: [] },
  })));

  [omitted, explicitEmpty].forEach((result) => {
    assert.equal(result.visit, '');
    assert.equal(result.clinic, '');
    assert.equal(result.patient, '');
    assert.equal(result.stat.body, '');
    assert.deepEqual(result.guide.goals, []);
    assert.deepEqual(result.care.blocks, []);
    assert.deepEqual(result.care.danger, []);
    assert.equal(result.care.ask, '');
    assert.deepEqual(result.life.challenges, []);
    assert.deepEqual(result.life.axes, {});
    assert.deepEqual(result.chat.chips, []);
  });
});

test('OCR started_at이 없어 서버가 진행률을 생략하면 약 정보만 유지한다', () => {
  const { context } = load();
  const response = richPayload({
    stat: {
      drugName: '비잔정 2mg',
      drugSub: '1일 1회 · 84일분',
      prescribed: 84,
    },
  });
  const result = plain(context.adaptGuideResponse(response));

  assert.equal(result.stat.drugName, '비잔정 2mg');
  assert.equal(result.stat.prescribed, 84);
  assert.equal(result.stat.dayOn, null);
  assert.equal(result.stat.remaining, null);
  assert.equal(result.stat.pct, null);
  assert.equal(result.stat.out, '');
  assert.equal(Object.hasOwn(result.stat, 'started_at'), false);
});

test('알 수 없는 루트·중첩 필드와 중복 sections를 계약 오류로 차단한다', () => {
  const { context } = load();
  const assertContractError = (value) => assert.throws(
    () => context.adaptGuideResponse(value),
    (error) => error.code === 'GUIDE_CONTRACT_MISMATCH',
  );

  assertContractError(payload([], { patient_name: '노출 금지' }));
  assertContractError(richPayload({
    stat: { drugName: '비잔정', prescribed: 84, patientName: '노출 금지' },
  }));
  assertContractError(richPayload({
    guide: { summary: '안내', goals: [{ n: '목표', internalId: 'secret' }] },
  }));
  assertContractError(payload([
    { key: 'medication', body: '첫 번째' },
    { key: 'medication', body: '두 번째' },
  ]));
});

test('HTML·합성 표식은 제거하되 일반 특수문자는 이중 이스케이프하지 않는다', () => {
  const { context } = load();
  const response = richPayload({
    clinic: "A&B's <script>alert(1)</script>여성의원",
    disease: '[합성 진단] <b>자궁내막증</b>',
    guide: {
      summary: '[합성 안내] <img src=x onerror=alert(1)>승인 문구',
      goals: [{ n: '<b>Hb</b>', hasChart: false }],
      why: ['[합성 이유] <svg onload=alert(1)>설명</svg>'],
    },
    care: {
      title: '<i>주의</i>',
      blocks: [{ t: '<b>반응</b>', p: ['[합성 반응] <img src=x>내용'] }],
      danger: [],
    },
    life: {
      challenges: [['[합성 습관] <em>수면</em>', '주 5일']],
      axes: { '<img src=x>수면': { p: ['[합성 생활] <script>bad</script>안내'] } },
    },
    chat: { chips: ['[합성 질문] <b>내 약</b>'] },
  });
  const result = plain(context.adaptGuideResponse(response));
  const serialized = JSON.stringify(result);

  assert.doesNotMatch(serialized, /\[합성/);
  assert.doesNotMatch(serialized, /<(?:script|img|svg|b|i|em)\b/i);
  assert.equal(result.clinic, "A&B's 여성의원");
  assert.equal(result.disease, '자궁내막증');
  assert.equal(result.guide.summary, '승인 문구');
  assert.doesNotMatch(serialized, /&(?:amp|lt|gt|quot|#39);/);
});

test('승인 문장 중간의 합성 계열 의학 표현은 섹션을 지우지 않는다', () => {
  const { context } = load();
  const result = plain(context.adaptGuideResponse(payload([
    { key: 'medication', body: '이 약은 [합성 프로게스틴] 제제입니다.' },
  ])));

  assert.equal(result.stat.body, '이 약은 [합성 프로게스틴] 제제입니다.');
  assert.equal(result.guide.summary, '이 약은 [합성 프로게스틴] 제제입니다.');
});

test('실제 API 요청은 토큰을 인코딩하고 브라우저 저장소에 남기지 않는다', async () => {
  const token = 'synthetic/key?241#토큰';
  const box = storage();
  const loaded = load({ response: richPayload(), storage: box });

  const result = await loaded.context.fetchGuide(token);

  assert.equal(loaded.requested().url, '/api/v1/guides/' + encodeURIComponent(token));
  assert.equal(loaded.requested().requestOptions.credentials, 'include');
  assert.deepEqual(plain(loaded.requested().requestOptions.headers), { Accept: 'application/json' });
  assert.equal(result.patient, '');
  assert.equal(Array.from(box.values.values()).includes(token), false);
  assert.doesNotMatch(API_SOURCE, /(?:localStorage|sessionStorage)\.setItem\([^\n]*token/i);
});

test('실제 /guide.html은 최종 와이어프레임 자산을 사용한다', () => {
  const html = fs.readFileSync(path.join(FRONTEND, 'guide.html'), 'utf8');
  const preview = fs.readFileSync(path.join(FRONTEND, 'patient_wireframe/html/guide.html'), 'utf8');
  const chat = fs.readFileSync(path.join(FRONTEND, 'patient_wireframe/js/chat.js'), 'utf8');
  const fab = fs.readFileSync(path.join(FRONTEND, 'patient_wireframe/component/fab.js'), 'utf8');

  assert.match(html, /\/patient_wireframe\/js\/guide-api\.js/);
  assert.match(html, /\/patient_wireframe\/js\/guide\.js/);
  assert.match(html, /id="guide-body"/);
  assert.match(preview, /location\.replace\('\.\.\/\.\.\/guide\.html'/);
  assert.doesNotMatch(preview, /guide-api\.js|guide\.css|id="guide-body"/);
  assert.match(chat, /!GUIDE_MOCK\) return/);
  assert.match(fab, /\/patient_wireframe\/assets\/chat_bot\.png/);
  assert.doesNotMatch(fab, /src="\.\.\/assets\//);
});

test('P2~P5 렌더러가 v3 진행률·빈 목표·부분 펼침·승인 시각 계약을 유지한다', () => {
  assert.match(GUIDE_SOURCE, /stat-bar-wrap/);
  assert.match(GUIDE_SOURCE, /s\.dayOn !== null/);
  assert.match(GUIDE_SOURCE, /s\.prescribed !== null && s\.prescribed > 0/);
  assert.match(GUIDE_SOURCE, /처방 일수가 없어 복약 기간을 표시하지 않아요/);
  assert.doesNotMatch(GUIDE_SOURCE, /if \(s\.prescribed !== null\) progressParts/);
  assert.match(GUIDE_SOURCE, /등록된 검사 목표가 없어 차트를 표시하지 않아요/);
  assert.match(GUIDE_SOURCE, /g\.goalSay/);
  assert.match(GUIDE_SOURCE, /다음 방문 계획/);
  assert.match(GUIDE_SOURCE, /lifeExpanded/);
  assert.match(GUIDE_SOURCE, /tab:\s*'현황'/);
  assert.doesNotMatch(GUIDE_SOURCE, /pw_guide_tab/);
  assert.match(GUIDE_SOURCE, /!isNaN\(nowNum\)\s*&&\s*\(hasStart \|\| hasTarget\)/);
  assert.ok(
    GUIDE_SOURCE.indexOf('expandBody.appendChild(drugCard)') >
      GUIDE_SOURCE.indexOf("var expandBody = el('div', 'expand-body'"),
    '처방약 카드가 P2 접힘 영역 안에 있지 않다',
  );
  assert.match(GUIDE_SOURCE, /hasAxisDetail = activeAxis\.p\.length > 0/);
  assert.doesNotMatch(GUIDE_SOURCE, /axisCopyLength|activeAxis\.p\.length > 2/);
  assert.match(GUIDE_SOURCE, /function richEl[\s\S]*?n\.textContent = value/);
  assert.doesNotMatch(GUIDE_SOURCE, /n\.innerHTML = html/);
  assert.match(GUIDE_SOURCE, /GuideFooter\(\{ approvedAt: d\.approvedAt/);
  assert.doesNotMatch(GUIDE_SOURCE, /goal\.dim/);

  assert.match(GUIDE_CSS, /\.expand-body[\s\S]*max-height:\s*430px/);
  assert.match(GUIDE_CSS, /\.life-fade-wrap[\s\S]*max-height:\s*300px/);
  assert.match(GUIDE_CSS, /border-bottom-color:\s*#D9AECB/);
  assert.match(FOOTER_SOURCE, /승인 ·/);
  assert.doesNotMatch(FOOTER_SOURCE, /생성 ·/);
});

test('KEY-219 실제 OTP 왕복을 보존하고 고정 OTP 우회는 명시적 목업에만 둔다', () => {
  assert.match(GUIDE_SOURCE, /function otpEntryUrl\(\)/);
  assert.match(GUIDE_SOURCE, /safeFragment\.set\('t', token\)/);
  assert.match(GUIDE_SOURCE, /GUIDE_MOCK && !sessionStorage\.getItem\('otp_verified'\)/);
  assert.match(GUIDE_SOURCE, /location\.replace\(otpEntryUrl\(\)\)/);
  assert.doesNotMatch(GUIDE_SOURCE, /sessionStorage\.setItem\([^\n]*token/i);

  assert.match(OTP_SOURCE, /\/patient-auth\/session\?link_token=/);
  assert.match(OTP_SOURCE, /\/patient-auth\/context/);
  assert.match(OTP_SOURCE, /\/patient-auth\/otp\/issue/);
  assert.match(OTP_SOURCE, /if \(isMock\)/);
  assert.match(OTP_SOURCE, /function mockVerifyUrl\(token\)/);
  assert.match(OTP_SOURCE, /\/guide\.html#t=/);

  assert.match(OTP_VERIFY_SOURCE, /function guideReturnUrl\(\)/);
  assert.match(OTP_VERIFY_SOURCE, /return '\/guide\.html'/);
  assert.match(OTP_VERIFY_SOURCE, /safeFragment\.set\('t', token\)/);
  assert.match(OTP_VERIFY_SOURCE, /\/patient-auth\/otp\/verify/);
  assert.match(OTP_VERIFY_SOURCE, /if \(isMock\)[\s\S]*code === '000000'/);
  assert.match(OTP_VERIFY_SOURCE, /if \(res\.ok\) \{[\s\S]*window\.location\.replace\('\/guide\.html#t='/);
  assert.equal((OTP_VERIFY_SOURCE.match(/sessionStorage\.setItem\('otp_verified'/g) || []).length, 1);
  assert.doesNotMatch(OTP_VERIFY_SOURCE, /sessionStorage\.setItem\([^\n]*(?:token|visit)/i);
});
