/* 안내문 API — ?mock=1 또는 file:// 자동 활성 */
var GUIDE_API_BASE = '/api/v1';

var GUIDE_MOCK = (function () {
  try {
    var q = new URLSearchParams(window.location.search);
    if (q.has('mock')) sessionStorage.setItem('pw_mock', q.get('mock') === '0' ? '0' : '1');
    var stored = sessionStorage.getItem('pw_mock');
    if (stored === '0') return false;
    if (stored === '1') return true;
    return location.protocol === 'file:' || location.hostname === 'localhost';
  } catch (e) { return true; }
})();

/* ── 와이어프레임 데이터 구조 그대로 ─── */
var MOCK = {
  ems: {
    visit:   '2026.08.13',
    clinic:  '〇〇여성의원',
    patient: '김서연',
    disease: '자궁내막증 · 비잔정 복용 중',

    /* 현황 탭 */
    stat: {
      drugName:      '비잔정 2mg',
      drugSub:       '성분 · 디에노게스트  · 1일 1회 · 84일분',
      prescribed:    84,
      dayOn:         12,
      remaining:     72,
      pct:           14,         /* Math.round(12/84*100) */
      out:           'ⓘ 11월 5일경 약이 소진돼요',
      why:           '이 약은 <b>병변이 다시 자라지 않게</b> 하는 약이에요. 계속 필요합니다.',
    },

    /* 복약지도 탭 */
    guide: {
      summary: '자궁내막증으로 진료받으셨고, <b>통증 관리를 위한 약</b>을 처방받으셨어요.',
      goals: [
        { n:'빈혈 Hb',    a:'10.2', now:'10.4', t:'12', hasChart:true,
          rangeLabel:'목표를 가운데 두고 본 지금 값' },
        { n:'자궁내막종', a:'2.8',  now:'2.4',  t:'─', hasChart:true,
          rangeLabel:'시작값을 기준으로 본 지금 값' },
        { n:'AMH 곧 나와요',   a:'─',   now:'─',    t:'─',  hasChart:false, dim:true,
          note:'결과가 나오면 채워드릴게요', startLine:'지금 ─' },
      ],

      drug: { n:'비잔정 2mg', s:'성분 · 디에노게스트', d:'1일 1회 · 84일분' },
      why: [
        '지난번 <b>8점</b>이던 생리통이 오늘 <b>4점</b>까지 내려왔어요. 약이 잘 듣고 있다는 뜻이에요.',
        '다만 통증이 줄었다고 <b>병변까지 없어진 것은 아니에요.</b> 남아 있으면 계속 염증을 일으켜 유착과 폐경 후 만성 골반통의 원인이 됩니다.',
        '끊을 시기는 <b>진료 때 함께 정해요.</b>',
      ],
      how:  '매일 같은 시간에 드세요.\n휴약기 없이 계속 복용합니다.',
      next: '3개월 뒤 재진 예정이에요. 아팠던 날이나 불편했던 점을 기억해 두셨다가 이야기해 주세요.',
    },

    /* 주의사항 탭 */
    care: {
      title: '비잔정 2mg 드시는 동안',
      blocks: [
        { t:'흔하고 괜찮은 반응', p:[
          '피가 조금씩 비치는 것이 가장 흔해요. 특히 <b>처음 3개월</b>에 그래요.',
          '가슴이 단단해지는 느낌, 몸이 붓는 느낌도 시간이 지나면 좋아집니다.',
          '생리가 없어지는 것은 <b>폐경이 아니에요.</b> 약을 끊으면 다시 돌아옵니다. 임의로 중단하지 마세요.',
        ]},
        { t:'이런 건 알려주세요', p:[
          '드물게 기분이 가라앉는 분들이 있어요. 평소와 다르게 느껴지면 <b>참지 마시고 알려주세요.</b>',
        ]},
        { t:'함께 드시면 안 되는 것', p:[
          '<b>세인트존스워트(성요한풀)</b>가 든 건강기능식품이나 허브차는 약효를 떨어뜨릴 수 있어요.',
          '드시는 영양제나 한약이 있으면 진료 때 말씀해 주세요.',
        ]},
        { t:'이 약은 피임약이 아니에요', p:[
          '피임이 필요하시면 별도의 방법을 함께 사용하세요.',
        ]},
      ],
      danger: [
        '· 기분이 심하게 가라앉아 일상생활이 어려울 때',
        '· 스스로를 해치고 싶은 생각이 들 때',
        '· 생리가 아닌데 출혈이 많아 어지럽거나 힘이 빠질 때',
      ],
      ask: '출혈이 2주 이상 계속되거나 심한 복통이 있으면 연락 주세요.',
    },

    /* 생활관리 탭 */
    life: {
      sub: '자궁내막증 · 비잔정 복용 중',
      challenges: [
        ['· 밤 11시 전에 잠들기', '주 5일'],
        ['· 칼슘 음식 챙겨 먹기', '주 5일'],
        ['· 주 3회 30분 걷기',    '주 3회'],
      ],
      axes: {
        '수면':    { chal:'· 밤 11시 전에 잠들기', goal:'주 5일',
          p:['지금은 새벽 1시쯤 주무신다고 하셨죠. <b>밤 10시~새벽 2시</b> 사이에 잠들어 있는 것이 좋아요.',
             '자기 전 2시간은 휴대폰을 보지 않으시면 더 좋아요.'] },
        '뼈 건강': { chal:'· 칼슘 음식 챙겨 먹기', goal:'주 5일',
          p:['우유 · 요거트 · 치즈 · 두부 · 녹색 잎채소를 매일 챙겨 드세요.',
             '약을 오래 드시는 동안 뼈를 함께 챙기면 좋습니다.'] },
        '운동':    { chal:'· 주 3회 30분 걷기',    goal:'주 3회',
          p:['걷기 · 계단 오르기처럼 <b>뼈에 체중이 실리는 운동</b>이 특히 좋아요.'] },
        '통증':    { title:'통증 관리', p:[
          '달력이나 메모에 생리통 점수를 <b>0점(안 아픔)~10점(아주 아픔)</b>으로 적어두세요.'] },
      },
    },

    /* 챗봇 */
    chat: {
      chips: ['내 약이 뭐였죠?', '출혈이 계속돼요', '언제까지 먹나요?'],
    },
  },

  pcos: {
    visit:   '2026.08.13',
    clinic:  '〇〇여성의원',
    patient: '이민지',
    disease: '다낭성난소증후군 · 야즈정 복용 중',
    stat: {
      drugName: '야즈정',
      drugSub:  '드로스피레논/에티닐에스트라디올 · 1일 1회 · 84일분',
      prescribed: 84, dayOn: 12, remaining: 72, pct: 14,
      out: 'ⓘ 11월 5일경 약이 소진돼요',
      why: '이 약은 <b>주기를 고르게</b> 하는 약이에요. 끊으면 다시 불규칙해집니다.',
    },
    guide: {
      summary: '다낭성난소증후군으로 진료받으셨고, <b>주기를 고르게 하는 약</b>을 처방받으셨어요.',
      goals: [
        { n:'LH / FSH 비율', a:'3.2', now:'2.4', t:'2.0', hasChart:true,
          rangeLabel:'목표를 가운데 두고 본 지금 값' },
        { n:'DHEA-S',        a:'260', now:'210', t:'200', hasChart:true,
          rangeLabel:'목표를 가운데 두고 본 지금 값' },
        { n:'생리 주기',      a:'안 옴', now:'38일', t:'35일', hasChart:false,
          note:'이번에는 추이만 기록해요', startLine:'시작 안 옴 · 지금 38일' },
      ],
      goalSay: '<b>주기가 돌아오고 있어요.</b>\n목표에 가까워지고 있습니다.',
      drug: { n:'야즈정', s:'드로스피레논/에티닐에스트라디올', d:'1일 1회 · 84일분' },
      why: ['주기가 규칙적이 된 것은 약이 잘 듣고 있다는 뜻이에요. 끊으면 다시 돌아옵니다.'],
      how: '분홍색 알약을 먼저 다 드시고, 이어서 흰색 알약을 드세요.\n매일 같은 시간에 드세요.',
      next: '3개월 뒤 재진 예정이에요.',
    },
    care: {
      title: '야즈정 드시는 동안',
      blocks: [
        { t:'흔하고 괜찮은 반응', p:['처음 몇 달은 부정출혈이 있을 수 있어요.'] },
        { t:'담배는 끊어 주세요', p:['흡연은 혈전 위험을 크게 높입니다.'] },
      ],
      danger: ['· 갑자기 숨이 차거나 가슴이 아플 때', '· 한쪽 종아리가 붓고 아플 때'],
      ask: '부정출혈이 3개월 이상 계속되면 연락 주세요.',
    },
    life: {
      sub: '다낭성난소증후군 · 야즈정 복용 중',
      challenges: [
        ['· 밤 11시 전에 잠들기', '주 5일'],
        ['· 배달음식 줄이기',     '주 5일'],
        ['· 주 3회 30분 걷기',    '주 3회'],
      ],
      axes: {
        '수면':    { chal:'· 밤 11시 전에 잠들기', goal:'주 5일', p:['규칙적인 수면이 호르몬 주기를 돕습니다.'] },
        '식이':    { chal:'· 배달음식 줄이기',     goal:'주 5일', p:['정제 탄수화물을 줄이면 인슐린 저항성 개선에 도움이 됩니다.'] },
        '운동':    { chal:'· 주 3회 30분 걷기',    goal:'주 3회', p:['가벼운 유산소로 꾸준히 이어가는 것이 중요합니다.'] },
        '월경주기':{ p:['생리 시작일을 달력에 적어두세요.'] },
      },
    },
    chat: { chips: ['내 약이 뭐였죠?', '부정출혈이 계속돼요', '언제까지 먹나요?'] },
  },
};

function fetchGuide(token) {
  if (GUIDE_MOCK) {
    var q   = new URLSearchParams(window.location.search);
    var key = q.get('case') || 'ems';
    return new Promise(function (resolve) {
      setTimeout(function () { resolve(MOCK[key] || MOCK.ems); }, 100);
    });
  }
  return fetch(GUIDE_API_BASE + '/guides/' + encodeURIComponent(token), {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  }).then(function (res) {
    if (res.ok) return res.json();
    return res.json().catch(function () { return {}; })
      .then(function (d) { throw new Error(d.code || 'NOT_FOUND'); });
  });
}
