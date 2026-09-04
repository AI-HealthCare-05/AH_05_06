/* 환자 안내 API 계약 — KEY-241
 *
 * GET /api/v1/guides/{token}의 v3.0.0 응답을 P2~P5 화면 모델로 바꾼다.
 * 기존 sections는 D+7·챗봇 호환을 위해 서버가 계속 제공하므로, 배포 순서가
 * 어긋난 동안에도 승인 문구만으로 안전한 빈 화면을 만들 수 있게 유지한다.
 * 화면 편의를 위해 환자명·검사값·처방 진행률을 지어내지는 않는다.
 */
var GUIDE_API_BASE = '/api/v1';

var GUIDE_ERROR = {
  CONTRACT: 'GUIDE_CONTRACT_MISMATCH',
  LINK_REQUIRED: 'LINK_REQUIRED',
  NOT_APPROVED: 'GUIDE_NOT_APPROVED',
  NOT_FOUND: 'LINK_NOT_FOUND',
  LINK_EXPIRED: 'LINK_EXPIRED',
  SESSION_EXPIRED: 'PATIENT_SESSION_EXPIRED',
};

/* 목업은 현재 주소에 ?mock=1이 명시된 경우에만 쓴다. 세션에 남기면 실제
   링크로 다시 들어와도 목업이 보이는 위험한 상태가 된다. */
var GUIDE_MOCK = (function () {
  try {
    var host = String(window.location.hostname || '').toLowerCase();
    var local = window.location.protocol === 'file:' || host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
    return local && new URLSearchParams(window.location.search).get('mock') === '1';
  } catch (e) {
    return false;
  }
})();

/* 브라우저 미리보기용 합성 응답도 실제 v3 DTO를 그대로 따른다. */
var MOCK_GUIDES = {
  ems: {
    version: 1,
    approved_at: '2026-09-01T09:00:00+09:00',
    expires_at: '2026-09-04T09:00:00+09:00',
    visit: '2026.08.13',
    clinic: '여성의원',
    patient_name: '김서연',
    disease: '자궁내막증 · 비잔정 복용 중',
    stat: {
      drugName: '비잔정 2mg',
      drugSub: '성분 · 디에노게스트 · 1일 1회 · 84일분',
      prescribed: 84,
      dayOn: 12,
      remaining: 72,
      pct: 14,
      out: 'ⓘ 11월 5일경 약이 소진돼요',
      why: '이 약은 병변이 다시 자라지 않게 하는 약이에요.',
    },
    guide: {
      summary: '자궁내막증으로 진료받으셨고, 통증 관리를 위한 약을 처방받으셨어요.',
      goals: [
        { n: '빈혈 Hb', a: '10.2', now: '10.4', t: '12', hasChart: true, rangeLabel: '목표를 가운데 두고 본 지금 값' },
        { n: '자궁내막종', a: '2.8', now: '2.4', t: null, hasChart: true, rangeLabel: '시작값을 기준으로 본 지금 값' },
        { n: 'AMH 곧 나와요', now: null, hasChart: false, rangeLabel: '검사값 추이' },
      ],
      goalSay: '빈혈은 목표까지 다 왔어요.\n자궁내막종은 더 커지지 않게 · AMH는 결과가 나오면 채워드릴게요.',
      drug: { n: '비잔정 2mg', s: '성분 · 디에노게스트', d: '1일 1회 · 84일분' },
      why: ['통증이 줄어도 임의로 약을 끊지 말고 진료 때 함께 정해 주세요.'],
      how: '매일 같은 시간에 드세요. 휴약기 없이 계속 복용합니다.',
      next: '3개월 뒤 재진 예정이에요. 불편했던 점을 기억해 두셨다가 이야기해 주세요.',
    },
    care: {
      title: '비잔정 2mg 드시는 동안',
      blocks: [{ t: '흔하고 괜찮은 반응', p: ['처음 3개월에는 피가 조금씩 비칠 수 있어요.'] }],
      danger: ['기분이 심하게 가라앉거나 출혈이 많아 어지러우면 바로 병원에 연락하세요.'],
      ask: '출혈이 2주 이상 계속되거나 심한 복통이 있으면 연락 주세요.',
    },
    life: {
      sub: '자궁내막증 · 비잔정 복용 중',
      challenges: [
        ['· 밤 11시 전에 잠들기', '주 5일'],
        ['· 칼슘 음식 챙겨 먹기', '주 5일'],
        ['· 주 3회 30분 걷기', '주 3회'],
      ],
      axes: {
        '수면': {
          chal: '· 밤 11시 전에 잠들기', goal: '주 5일', title: '수면',
          p: [
            '지금은 새벽 1시쯤 주무신다고 하셨죠.',
            '밤 10시~새벽 2시 사이에 잠들어 있는 것이 좋아요.',
            '자기 전 2시간은 휴대폰을 보지 않으시면 더 좋아요.',
          ],
        },
        '뼈 건강': { chal: '· 칼슘 음식 챙겨 먹기', goal: '주 5일', title: '뼈 건강', p: ['식사에서 칼슘이 든 음식을 챙겨 보세요.'] },
        '운동': { chal: '· 주 3회 30분 걷기', goal: '주 3회', title: '운동', p: ['무리하지 않는 범위에서 걷기를 이어 가세요.'] },
        '통증': { title: '통증 관리', p: ['아팠던 날과 정도를 기록해 다음 진료 때 알려 주세요.'] },
      },
    },
    chat: { chips: [] },
    sections: [
      { key: 'medication', body: '자궁내막증으로 진료받으셨고, 통증 관리를 위한 약을 처방받으셨어요.' },
      { key: 'caution', body: '처음 3개월에는 피가 조금씩 비칠 수 있어요.' },
      { key: 'emergency', body: '출혈이 많아 어지러우면 바로 병원에 연락하세요.' },
      { key: 'life', body: '규칙적인 수면 시간을 유지해 주세요.' },
      { key: 'messages', body: '궁금한 점은 진료받은 병원에 문의해 주세요.' },
    ],
    demo_only: true,
  },
  pcos: {
    version: 1,
    approved_at: '2026-09-01T09:00:00+09:00',
    expires_at: '2026-09-04T09:00:00+09:00',
    visit: '2026.08.13',
    clinic: '여성의원',
    patient_name: '이지우',
    disease: '다낭성난소증후군 · 야즈정 복용 중',
    stat: { drugName: '야즈정', drugSub: '성분 · 드로스피레논 · 에티닐에스트라디올 · 1일 1회 · 84일분', prescribed: 84, dayOn: 12, remaining: 72, pct: 14 },
    guide: {
      summary: '다낭성난소증후군으로 진료받으셨고, 호르몬 균형을 돕는 약을 처방받으셨어요.',
      goals: [
        { n: 'LH / FSH 비율', a: '3.2', now: '2.4', t: '2.0', hasChart: true, rangeLabel: '목표를 가운데 두고 본 지금 값' },
        { n: 'DHEA-S', a: '260', now: '210', t: '200', hasChart: true, rangeLabel: '목표를 가운데 두고 본 지금 값' },
        { n: '생리 주기', a: '42', now: '38', t: '35', hasChart: true, rangeLabel: '목표를 가운데 두고 본 지금 값' },
      ],
      goalSay: '0.4 남았어요. 잘 가고 있어요.',
      drug: { n: '야즈정', s: '성분 · 드로스피레논 · 에티닐에스트라디올', d: '1일 1회 · 84일분' },
      why: ['생리 주기를 규칙적으로 만들고 자궁내막이 두꺼워지는 것을 막아 줘요.'],
      how: '분홍색 알약을 먼저 다 드시고 이어서 흰색 알약을 드세요.',
    },
    care: { blocks: [{ t: '주의사항', p: ['처음 몇 달은 불규칙한 출혈이 나타날 수 있어요.'] }], danger: [], ask: null },
    life: {
      sub: '다낭성난소증후군 · 야즈정 복용 중',
      challenges: [
        ['· 밤 11시 전에 잠들기', '주 5일'],
        ['· 배달음식 줄이기', '주 5일'],
        ['· 주 3회 30분 걷기', '주 3회'],
      ],
      axes: {
        '수면': {
          chal: '· 밤 11시 전에 잠들기', goal: '주 5일', title: '수면',
          p: [
            '다낭성난소증후군에서 생활관리의 첫째는 수면이에요.',
            '하루 7~8시간, 밤 10시~새벽 2시 사이에 잠들어 있는 것이 좋습니다.',
            '자기 전 2시간은 휴대폰을 보지 않고 방을 어둡게 해 주세요.',
          ],
        },
        '식이': { chal: '· 배달음식 줄이기', goal: '주 5일', title: '식이', p: ['규칙적으로 식사하고 배달음식 횟수를 줄여 보세요.'] },
        '운동': { chal: '· 주 3회 30분 걷기', goal: '주 3회', title: '운동', p: ['무리하지 않는 범위에서 걷기를 이어 가세요.'] },
        '월경주기': { title: '월경주기', p: ['월경 시작일을 기록해 다음 진료 때 알려 주세요.'] },
      },
    },
    chat: { chips: [] },
    sections: [
      { key: 'medication', body: '야즈정을 처방받으셨어요.' },
      { key: 'caution', body: '처음 몇 달은 불규칙한 출혈이 나타날 수 있어요.' },
    ],
    demo_only: true,
  },
};

function GuideError(code) {
  this.name = 'GuideError';
  this.code = code;
}
GuideError.prototype = Object.create(Error.prototype);

function isRecord(value) {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function validKeys(value, allowed, required) {
  if (!isRecord(value)) return false;
  var keys = Object.keys(value);
  return keys.every(function (key) { return allowed.indexOf(key) >= 0; }) &&
    (required || []).every(function (key) { return Object.prototype.hasOwnProperty.call(value, key); });
}

function publicBody(body) {
  if (typeof body !== 'string') throw new GuideError(GUIDE_ERROR.CONTRACT);
  /* fixture가 붙이는 선두 표식만 제거한다. 승인 문장 중간의
     "[합성 프로게스틴]" 같은 실제 의학 표현은 콘텐츠이므로 보존한다. */
  return body.trim().replace(/^(?:\[합성[^\]]*\]\s*)+/, '');
}

function optionalBody(value) {
  return value === null || typeof value === 'undefined' ? '' : publicBody(value);
}

function safeText(value) {
  /* 공개 계약은 평문이다. 태그는 표시 모델에서 제거하고, 렌더러는 반드시
     textContent를 사용한다. 여기서 HTML entity로 바꾸면 `&`·따옴표가
     화면에 `&amp;`·`&#39;`로 이중 표시된다. */
  return optionalBody(value)
    .replace(/<\s*(script|style)\b[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi, '')
    .replace(/<[^>]*>/g, '')
    .trim();
}

function bodyLines(body) {
  return optionalBody(body).split(/\n+/).map(function (line) {
    return safeText(line);
  }).filter(Boolean);
}

function displayDate(value) {
  var date = new Date(value);
  if (typeof value !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) ||
      isNaN(date.getTime())) {
    throw new GuideError(GUIDE_ERROR.CONTRACT);
  }
  var parts = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(date);
  var values = {};
  parts.forEach(function (part) { values[part.type] = part.value; });
  return values.year + '.' + values.month + '.' + values.day;
}

function displayVisit(value) {
  if (value === null || typeof value === 'undefined') return '';
  if (typeof value !== 'string' || !/^\d{4}\.\d{2}\.\d{2}$/.test(value)) {
    throw new GuideError(GUIDE_ERROR.CONTRACT);
  }
  return value;
}

function optionalNumber(value, minimum, maximum) {
  if (value === null || typeof value === 'undefined') return null;
  if (typeof value !== 'number' || !isFinite(value) || Math.floor(value) !== value ||
      value < minimum || (maximum !== null && value > maximum)) {
    throw new GuideError(GUIDE_ERROR.CONTRACT);
  }
  return value;
}

function mapTextArray(value) {
  if (!Array.isArray(value)) throw new GuideError(GUIDE_ERROR.CONTRACT);
  return value.map(safeText).filter(Boolean);
}

function readSections(value) {
  var allowedKeys = ['medication', 'caution', 'emergency', 'life', 'messages'];
  if (!Array.isArray(value)) throw new GuideError(GUIDE_ERROR.CONTRACT);
  var sections = {};
  value.forEach(function (section) {
    if (!validKeys(section, ['body', 'key'], ['body', 'key']) ||
        allowedKeys.indexOf(section.key) < 0 ||
        Object.prototype.hasOwnProperty.call(sections, section.key)) {
      throw new GuideError(GUIDE_ERROR.CONTRACT);
    }
    sections[section.key] = publicBody(section.body);
  });
  return sections;
}

function mapStat(value, medication) {
  if (value === null || typeof value === 'undefined') {
    return { drugName: medication ? '복약 현황' : '', drugSub: '', prescribed: null, dayOn: null, remaining: null, pct: null, out: '', why: '', body: safeText(medication) };
  }
  if (!validKeys(value,
    ['drugName', 'drugSub', 'prescribed', 'dayOn', 'remaining', 'pct', 'out', 'why'],
    ['drugName', 'prescribed'])) throw new GuideError(GUIDE_ERROR.CONTRACT);
  return {
    drugName: safeText(value.drugName),
    drugSub: safeText(value.drugSub),
    prescribed: optionalNumber(value.prescribed, 0, null),
    dayOn: optionalNumber(value.dayOn, 0, null),
    remaining: optionalNumber(value.remaining, 0, null),
    pct: optionalNumber(value.pct, 0, 100),
    out: safeText(value.out),
    why: safeText(value.why),
    body: safeText(medication),
  };
}

function mapGuide(value, medication) {
  if (value === null || typeof value === 'undefined') {
    return { summary: safeText(medication), goals: [], goalSay: '', drug: null, why: [], how: '', next: '' };
  }
  if (!validKeys(value, ['summary', 'goals', 'goalSay', 'drug', 'why', 'how', 'next'], [])) {
    throw new GuideError(GUIDE_ERROR.CONTRACT);
  }
  var goals = value.goals || [];
  if (!Array.isArray(goals)) throw new GuideError(GUIDE_ERROR.CONTRACT);
  goals = goals.map(function (goal) {
    if (!validKeys(goal, ['n', 'a', 'now', 't', 'hasChart', 'rangeLabel'], ['n'])) {
      throw new GuideError(GUIDE_ERROR.CONTRACT);
    }
    if (typeof goal.hasChart !== 'undefined' && typeof goal.hasChart !== 'boolean') {
      throw new GuideError(GUIDE_ERROR.CONTRACT);
    }
    return {
      n: safeText(goal.n), a: safeText(goal.a), now: safeText(goal.now), t: safeText(goal.t),
      hasChart: goal.hasChart === true, rangeLabel: safeText(goal.rangeLabel),
    };
  });
  var drug = null;
  if (value.drug !== null && typeof value.drug !== 'undefined') {
    if (!validKeys(value.drug, ['n', 's', 'd'], ['n'])) throw new GuideError(GUIDE_ERROR.CONTRACT);
    drug = { n: safeText(value.drug.n), s: safeText(value.drug.s), d: safeText(value.drug.d) };
  }
  return {
    summary: safeText(typeof value.summary === 'undefined' ? medication : value.summary),
    goals: goals,
    goalSay: safeText(value.goalSay),
    drug: drug,
    why: mapTextArray(value.why || []),
    how: safeText(value.how),
    next: safeText(value.next),
  };
}

function mapCare(value, caution, emergency) {
  if (value === null || typeof value === 'undefined') {
    return {
      title: '복약 중 주의사항',
      blocks: caution ? [{ t: '주의사항', p: bodyLines(caution) }] : [],
      danger: bodyLines(emergency), ask: '',
    };
  }
  if (!validKeys(value, ['title', 'blocks', 'danger', 'ask'], [])) throw new GuideError(GUIDE_ERROR.CONTRACT);
  var blocks = value.blocks || [];
  if (!Array.isArray(blocks)) throw new GuideError(GUIDE_ERROR.CONTRACT);
  blocks = blocks.map(function (block) {
    if (!validKeys(block, ['t', 'p'], [])) throw new GuideError(GUIDE_ERROR.CONTRACT);
    return { t: safeText(block.t), p: mapTextArray(block.p || []) };
  });
  return { title: safeText(value.title) || '복약 중 주의사항', blocks: blocks, danger: mapTextArray(value.danger || []), ask: safeText(value.ask) };
}

function mapLife(value, lifeBody, disease) {
  if (value === null || typeof value === 'undefined') {
    return { sub: disease || '담당 의료진이 확인한 생활관리 안내', challenges: [], axes: lifeBody ? { '생활관리': { chal: '', goal: '', title: '생활관리', p: bodyLines(lifeBody) } } : {} };
  }
  if (!validKeys(value, ['sub', 'challenges', 'axes'], [])) throw new GuideError(GUIDE_ERROR.CONTRACT);
  var challenges = value.challenges || [];
  if (!Array.isArray(challenges)) throw new GuideError(GUIDE_ERROR.CONTRACT);
  challenges = challenges.map(function (challenge) {
    if (!Array.isArray(challenge) || challenge.length !== 2) throw new GuideError(GUIDE_ERROR.CONTRACT);
    return [safeText(challenge[0]), safeText(challenge[1])];
  });
  var sourceAxes = value.axes || {};
  if (!isRecord(sourceAxes)) throw new GuideError(GUIDE_ERROR.CONTRACT);
  var axes = {};
  Object.keys(sourceAxes).forEach(function (name) {
    var axis = sourceAxes[name];
    if (!validKeys(axis, ['chal', 'goal', 'title', 'p'], [])) throw new GuideError(GUIDE_ERROR.CONTRACT);
    var publicName = safeText(name);
    if (publicName) axes[publicName] = { chal: safeText(axis.chal), goal: safeText(axis.goal), title: safeText(axis.title), p: mapTextArray(axis.p || []) };
  });
  return { sub: safeText(value.sub) || disease, challenges: challenges, axes: axes };
}

function mapChat(value) {
  if (value === null || typeof value === 'undefined') return { chips: [] };
  if (!validKeys(value, ['chips'], [])) throw new GuideError(GUIDE_ERROR.CONTRACT);
  return { chips: mapTextArray(value.chips || []) };
}

function adaptGuideResponse(payload) {
  var rootFields = ['approved_at', 'care', 'chat', 'clinic', 'demo_only', 'disease', 'expires_at', 'guide', 'life', 'patient_name', 'sections', 'stat', 'version', 'visit'];
  var required = ['approved_at', 'demo_only', 'expires_at', 'sections', 'version'];
  if (!validKeys(payload, rootFields, required) || typeof payload.version !== 'number' || payload.demo_only !== true) {
    throw new GuideError(GUIDE_ERROR.CONTRACT);
  }
  var sections = readSections(payload.sections);
  var approvedDate = displayDate(payload.approved_at);
  displayDate(payload.expires_at);
  var medication = sections.medication || '';
  var disease = safeText(payload.disease);
  return {
    // 서버가 OTP 인증한 뷰어에게만 patient_name 을 실어 준다(KEY-268). 없으면 ''.
    visit: displayVisit(payload.visit), clinic: safeText(payload.clinic), patient: safeText(payload.patient_name), disease: disease,
    approvedAt: approvedDate, expiresAt: payload.expires_at,
    stat: mapStat(payload.stat, medication),
    guide: mapGuide(payload.guide, medication),
    care: mapCare(payload.care, sections.caution || '', sections.emergency || ''),
    life: mapLife(payload.life, sections.life || '', disease),
    chat: mapChat(payload.chat),
  };
}

/* 탭 이름 → 서버가 아는 장 이름. **화면 글자를 그대로 보내지 않는다** —
   탭 이름은 언제든 바뀌는 글이고, 바뀌는 날 조용히 안 세어진다. */
var GUIDE_PAGE_KEY = {
  '현황': 'messages',
  '복약지도': 'medication',
  '주의사항': 'caution',
  '생활관리': 'life',
};

/* 환자가 한 장을 열었다고 알린다 — KEY-256, 원문 S2-2 「(4장 중 2장)」.

   **기다리지 않는다.** 이 호출이 늦거나 실패해도 환자는 계속 읽어야 한다 —
   통계가 안내 열람을 막으면 안 된다. 그래서 답을 안 보고, 실패도 삼킨다.
   서버 쪽도 같은 이유로 `204` 만 준다. */
function markGuidePageRead(token, tabName) {
  var section = GUIDE_PAGE_KEY[tabName];
  if (!section || GUIDE_MOCK || !token) return;
  fetch(GUIDE_API_BASE + '/guides/' + encodeURIComponent(token) + '/views', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section: section }),
  }).catch(function () {
    /* 삼킨다 — 읽기를 막지 않는다 */
  });
}

function fetchGuide(token) {
  if (GUIDE_MOCK) {
    var q = new URLSearchParams(window.location.search);
    var key = q.get('case') || 'ems';
    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        /* 승인 전에는 공개 링크 자체를 발급할 수 없다. 환자 조회 경로에서는
           서버처럼 존재하지 않는 링크(404)로만 보인다. */
        if (key === 'none') return reject(new GuideError(GUIDE_ERROR.NOT_FOUND));
        if (!MOCK_GUIDES[key]) return reject(new GuideError(GUIDE_ERROR.NOT_FOUND));
        try { resolve(adaptGuideResponse(MOCK_GUIDES[key])); } catch (error) { reject(error); }
      }, 100);
    });
  }
  if (!token) return Promise.reject(new GuideError(GUIDE_ERROR.LINK_REQUIRED));
  return fetch(GUIDE_API_BASE + '/guides/' + encodeURIComponent(token), {
    credentials: 'include', headers: { Accept: 'application/json' },
  }).then(function (res) {
    if (res.ok) return res.json().then(adaptGuideResponse);
    return res.json().catch(function () { return {}; })
      .then(function (data) { throw new GuideError(data.code || GUIDE_ERROR.NOT_FOUND); });
  });
}

function createFeedbackSubmissionId() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  var bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  var hex = Array.from(bytes, function (value) { return value.toString(16).padStart(2, '0'); }).join('');
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
}

function submitPatientFeedback(payload) {
  return fetch(GUIDE_API_BASE + '/patient-feedback', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  }).then(function (res) {
    if (res.ok) return res.json();
    return res.json().catch(function () { return {}; }).then(function (data) {
      var error = new Error(data.code || 'FEEDBACK_FAILED');
      error.code = data.code || 'FEEDBACK_FAILED';
      throw error;
    });
  });
}
