/* 환자 안내 API 계약 — KEY-241
 *
 * 실제 화면은 GET /api/v1/guides/{token}의 PatientGuideResponse만 받는다.
 * 목업도 같은 DTO를 거쳐야 하며, 실제 응답에 없는 환자명·병원명·처방량을
 * 화면 편의를 위해 지어내지 않는다.
 */
var GUIDE_API_BASE = '/api/v1';

var GUIDE_ERROR = {
  CONTRACT: 'GUIDE_CONTRACT_MISMATCH',
  LINK_REQUIRED: 'LINK_REQUIRED',
  NOT_APPROVED: 'GUIDE_NOT_APPROVED',
  NOT_FOUND: 'LINK_NOT_FOUND',
  LINK_EXPIRED: 'LINK_EXPIRED',
};

var GUIDE_MOCK = (function () {
  try {
    var q = new URLSearchParams(window.location.search);
    if (q.has('mock')) sessionStorage.setItem('pw_mock', q.get('mock') === '0' ? '0' : '1');
    return sessionStorage.getItem('pw_mock') === '1';
  } catch (e) {
    return false;
  }
})();

/* 화면 미리보기도 서버 DTO보다 관대하지 않게 같은 계약으로 둔다. */
var MOCK_GUIDES = {
  ems: {
    version: 1,
    approved_at: '2026-09-01T09:00:00+09:00',
    expires_at: '2026-09-08T09:00:00+09:00',
    sections: [
      {
        key: 'medication',
        body: '비잔정(디에노게스트) 2mg을 처방받으셨어요.\n매일 같은 시간에 처방받은 용법대로 복용해 주세요.',
      },
      {
        key: 'caution',
        body: '복용 중 평소와 다른 불편감이 생기거나 증상이 계속되면 의료진에게 알려 주세요.',
      },
      {
        key: 'emergency',
        body: '호흡 곤란이나 심한 복통처럼 급한 증상이 생기면 즉시 응급실을 방문하세요.',
      },
      {
        key: 'life',
        body: '충분한 수분 섭취와 규칙적인 수면을 유지해 주세요.\n무리하지 않는 범위에서 가볍게 걸어 주세요.',
      },
      { key: 'messages', body: '궁금한 점은 진료받은 병원에 문의해 주세요.' },
    ],
    demo_only: true,
  },
  pcos: {
    version: 1,
    approved_at: '2026-09-01T09:00:00+09:00',
    expires_at: '2026-09-08T09:00:00+09:00',
    sections: [
      {
        key: 'medication',
        body: '야즈정을 처방받으셨어요.\n매일 같은 시간에 처방받은 용법대로 복용해 주세요.',
      },
      { key: 'caution', body: '처음 몇 달은 불규칙한 출혈이 나타날 수 있어요.' },
      {
        key: 'emergency',
        body: '갑자기 숨이 차거나 가슴이 아프면 즉시 응급실을 방문하세요.',
      },
      {
        key: 'life',
        body: '규칙적인 수면과 식사를 유지해 주세요.\n가벼운 유산소 운동을 꾸준히 이어가 주세요.',
      },
      { key: 'messages', body: '불편감이 계속되면 진료받은 병원에 알려 주세요.' },
    ],
    demo_only: true,
  },
};

function GuideError(code) {
  this.name = 'GuideError';
  this.code = code;
}
GuideError.prototype = Object.create(Error.prototype);

function sameKeys(value, expected) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  var keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every(function (key, index) {
    return key === expected[index];
  });
}

function publicBody(body) {
  if (typeof body !== 'string') throw new GuideError(GUIDE_ERROR.CONTRACT);
  var cleaned = body.trim().replace(/^\[합성[^\]]*\]\s*/, '');
  /* 중간에 남은 표시는 승인 문장 일부인지 구분할 수 없으므로 화면에 내보내지 않는다. */
  if (/\[합성[^\]]*\]/.test(cleaned)) return '';
  return cleaned;
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function bodyLines(body) {
  return publicBody(body).split(/\n+/).map(function (line) {
    return escapeHtml(line.trim());
  }).filter(Boolean);
}

function displayDate(value) {
  var date = new Date(value);
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(value) || isNaN(date.getTime())) {
    throw new GuideError(GUIDE_ERROR.CONTRACT);
  }
  // 승인일은 서버가 보낸 진료 기준일을 그대로 표시한다.
  // 브라우저 타임존으로 재계산하면 날짜가 하루 바뀐 수 있다.
  return value.slice(0, 10).replace(/-/g, '.');
}

function adaptGuideResponse(payload) {
  var responseFields = ['approved_at', 'demo_only', 'expires_at', 'sections', 'version'];
  var sectionFields = ['body', 'key'];
  var allowedKeys = ['medication', 'caution', 'emergency', 'life', 'messages'];

  if (!sameKeys(payload, responseFields) ||
      typeof payload.version !== 'number' ||
      payload.demo_only !== true ||
      !Array.isArray(payload.sections)) {
    throw new GuideError(GUIDE_ERROR.CONTRACT);
  }

  var sections = {};
  payload.sections.forEach(function (section) {
    if (!sameKeys(section, sectionFields) ||
        allowedKeys.indexOf(section.key) < 0 ||
        Object.prototype.hasOwnProperty.call(sections, section.key)) {
      throw new GuideError(GUIDE_ERROR.CONTRACT);
    }
    sections[section.key] = publicBody(section.body);
  });

  var approvedDate = displayDate(payload.approved_at);
  displayDate(payload.expires_at);
  var medication = sections.medication || '';
  var caution = sections.caution || '';
  var emergency = sections.emergency || '';
  var life = sections.life || '';
  var messages = sections.messages || '';

  return {
    visit: approvedDate,
    clinic: '',
    patient: '',
    disease: '',
    generatedAt: payload.approved_at,
    expiresAt: payload.expires_at,
    stat: {
      drugName: '복약 현황',
      prescribed: null,
      body: escapeHtml(medication),
      out: '',
      why: '',
    },
    guide: {
      summary: escapeHtml(medication),
      goals: [],
      drug: null,
      why: [],
      how: '',
      next: escapeHtml(messages),
    },
    care: {
      title: '복약 중 주의사항',
      blocks: caution ? [{ t: '주의사항', p: bodyLines(caution) }] : [],
      danger: bodyLines(emergency),
      ask: escapeHtml(messages),
    },
    life: {
      sub: '담당 의료진이 확인한 생활관리 안내',
      challenges: [],
      axes: life ? { '생활관리': { p: bodyLines(life) } } : {},
    },
    chat: { chips: [] },
  };
}

function fetchGuide(token) {
  if (GUIDE_MOCK) {
    var q = new URLSearchParams(window.location.search);
    var key = q.get('case') || 'ems';
    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        if (key === 'none') {
          reject(new GuideError(GUIDE_ERROR.NOT_APPROVED));
          return;
        }
        if (!MOCK_GUIDES[key]) {
          reject(new GuideError(GUIDE_ERROR.NOT_FOUND));
          return;
        }
        try {
          resolve(adaptGuideResponse(MOCK_GUIDES[key]));
        } catch (error) {
          reject(error);
        }
      }, 100);
    });
  }

  if (!token) return Promise.reject(new GuideError(GUIDE_ERROR.LINK_REQUIRED));

  return fetch(GUIDE_API_BASE + '/guides/' + encodeURIComponent(token), {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  }).then(function (res) {
    if (res.ok) return res.json().then(adaptGuideResponse);
    return res.json().catch(function () { return {}; })
      .then(function (data) { throw new GuideError(data.code || GUIDE_ERROR.NOT_FOUND); });
  });
}
