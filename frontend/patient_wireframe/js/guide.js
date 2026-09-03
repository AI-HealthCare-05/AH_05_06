/* 진료 안내 — 화면 02~06  (guide.html) */
(function () {
  var bodyRoot = document.getElementById('body') || document.getElementById('guide-body');
  if (!bodyRoot) return;

  /* P1 목업 인증 가드. 실제 안내 조회는 정본 API 계약대로 링크 자체가 접근
     증명이며, 고정 OTP 목업으로 실제 환자 진입을 막지 않는다. 목업 왕복 중
     토큰은 fragment로만 전달하고 브라우저 저장소에는 복사하지 않는다. */
  function otpEntryUrl() {
    var query = new URLSearchParams(window.location.search);
    var fragment = new URLSearchParams(String(window.location.hash || '').replace(/^#/, ''));
    var token = fragment.get('t') || query.get('t') || query.get('visit') || '';
    var safeQuery = new URLSearchParams();
    var mock = query.get('mock');
    var previewCase = query.get('case');
    if (mock === '1') safeQuery.set('mock', '1');
    if (previewCase && /^[a-z0-9_-]{1,32}$/i.test(previewCase)) safeQuery.set('case', previewCase);
    var safeFragment = new URLSearchParams();
    if (token) safeFragment.set('t', token);
    return '/patient_wireframe/html/otp.html' +
      (safeQuery.toString() ? '?' + safeQuery.toString() : '') +
      (safeFragment.toString() ? '#' + safeFragment.toString() : '');
  }

  if (typeof GUIDE_MOCK !== 'undefined' && GUIDE_MOCK && !sessionStorage.getItem('otp_verified')) {
    location.replace(otpEntryUrl());
    return;
  }

  /* 토큰은 access log에 남지 않는 fragment로 받고 즉시 주소에서 지운다.
     sessionStorage·DOM·console에는 저장하지 않는다(KEY-205 계약 유지). */
  function takeGuideToken() {
    var query = new URLSearchParams(window.location.search);
    var fragment = new URLSearchParams(String(window.location.hash || '').replace(/^#/, ''));
    var token = fragment.get('t') || query.get('t') || query.get('visit') || '';

    fragment.delete('t');
    query.delete('t');
    query.delete('visit');
    var safeQuery = query.toString();
    var safeFragment = fragment.toString();
    var safeUrl = window.location.pathname + (safeQuery ? '?' + safeQuery : '') +
      (safeFragment ? '#' + safeFragment : '');
    if (window.history && typeof window.history.replaceState === 'function') {
      window.history.replaceState(null, '', safeUrl);
    }
    return token;
  }

  var TOKEN = takeGuideToken();

  var TABS = ['현황', '복약지도', '주의사항', '생활관리'];

  var state = {
    data:          null,
    /* 새 안내 링크는 v3 정본 순서대로 항상 P5 현황에서 시작한다. */
    tab:           '현황',
    guideExpanded: false,
    careExpanded:  false,
    lifeAxis:      null,
    lifeExpanded:  false,
    pdfSelected:   ['guide', 'care', 'life', 'stat'],
  };

  /* ── 유틸 ─── */
  function el(tag, cls) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    return n;
  }
  /* API 안내문은 평문 계약이다. 줄바꿈은 CSS `white-space: pre-line`으로
     보존하고, 환자에게 보이는 값은 모두 textContent로 넣는다. */
  function richEl(tag, cls, value) {
    var n = el(tag, cls);
    n.textContent = value || '';
    return n;
  }
  function text(tag, cls, txt) {
    var n = el(tag, cls);
    n.textContent = txt || '';
    return n;
  }
  function btn(cls, label, onClick) {
    var b = el('button', 'btn ' + cls);
    b.type = 'button';
    b.textContent = label;
    if (onClick) b.addEventListener('click', onClick);
    return b;
  }
  function emptyState(message) {
    return text('div', 'guide-empty', message || '표시할 승인 안내가 아직 없어요.');
  }
  function sayGuide(message) {
    var live = document.getElementById('guide-say');
    if (live) live.textContent = message || '';
  }

  /* ── 탭 바 (component/tab-bar.js 교체 — 와이어프레임 스타일) ─── */
  function buildTabBar(d) {
    var bar = document.getElementById('tab-bar');
    bar.innerHTML = '';
    TABS.forEach(function (key) {
      var b = el('button', 'tab-bar__btn' + (key === state.tab ? ' tab-bar__btn--active' : ''));
      b.type = 'button';
      b.textContent = key;
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', key === state.tab ? 'true' : 'false');
      b.addEventListener('click', function () {
        if (key === state.tab) return;
        state.tab = key;
        buildTabBar(d);
        renderBody(d);
        sayGuide(key);
        window.scrollTo(0, 0);
      });
      bar.appendChild(b);
    });
  }

  /* ── 헤더 메타 ─── */
  function fillHeader(d) {
    /* 공개 응답에는 환자명이 없으므로 와이어프레임의 환자명 자리를 지어내지 않는다. */
    var meta = [d.visit ? d.visit + ' 진료' : '승인된 진료 안내', d.clinic].filter(Boolean);
    document.getElementById('header-patient').textContent = meta.join(' · ');
  }

  function showMockBadge() {
    if (!GUIDE_MOCK || document.getElementById('guide-mock-badge')) return;
    var badge = text('div', 'guide-mock-badge', '개발용 목업 화면');
    badge.id = 'guide-mock-badge';
    document.querySelector('.header').appendChild(badge);
  }

  /* ════════════════════════
     2번 화면: 현황 (P5)
  ════════════════════════ */
  function renderStatus(d) {
    var s    = d.stat;
    var frag = document.createDocumentFragment();

    /* 처방일 힌트 */
    var hint = [d.visit ? d.visit + ' 처방' : '', d.clinic].filter(Boolean).join(' · ');
    if (hint) frag.appendChild(text('div', 'page-hint', hint));

    /* 약 카드 */
    var drugCard = el('div', 'card');
    if (s.drugName) drugCard.appendChild(text('div', 'stat-drug-name', s.drugName));
    if (s.drugSub) drugCard.appendChild(text('div', 'stat-drug-sub', s.drugSub));

    var progressParts = [];
    if (s.prescribed !== null && s.prescribed > 0) progressParts.push(s.prescribed + '일분');
    if (s.dayOn !== null) progressParts.push(s.dayOn + '일째');
    if (s.remaining !== null) progressParts.push(s.remaining + '일 남음');
    if (progressParts.length) {
      drugCard.appendChild(text('div', 'stat-progress-copy', progressParts.join(' · ')));
    }
    if (s.pct !== null) {
      var progress = el('div', 'stat-bar-wrap');
      progress.setAttribute('role', 'progressbar');
      progress.setAttribute('aria-label', '복약 진행률');
      progress.setAttribute('aria-valuemin', '0');
      progress.setAttribute('aria-valuemax', '100');
      progress.setAttribute('aria-valuenow', String(s.pct));
      var fill = el('span', 'stat-bar-fill');
      fill.style.width = s.pct + '%';
      progress.appendChild(fill);
      drugCard.appendChild(progress);
      drugCard.appendChild(text('div', 'stat-bar-pct', s.pct + '% 복용했어요'));
    } else if (s.prescribed === 0) {
      drugCard.appendChild(text('div', 'stat-progress-empty',
        '처방 일수가 없어 복약 기간을 표시하지 않아요.'));
    } else if (s.prescribed !== null && s.prescribed > 0) {
      drugCard.appendChild(text('div', 'stat-progress-empty',
        '복약 시작일이 없어 진행률과 남은 일수를 표시하지 않아요.'));
    }
    /* v3의 사유 카드가 있으면 같은 승인 문구를 약 카드에 중복 노출하지 않는다. */
    if (s.body && !s.why) drugCard.appendChild(richEl('div', 'care-body-text', s.body));
    if (!s.drugName && !s.body) drugCard.appendChild(emptyState('표시할 승인 복약 안내가 아직 없어요.'));
    frag.appendChild(drugCard);

    /* 소진 예정 핑크 카드 */
    if (s.out || s.why) {
      var pinkCard = el('div', 'card card--pink');
      if (s.out) pinkCard.appendChild(richEl('div', 'stat-out', s.out));
      if (s.why) pinkCard.appendChild(richEl('div', 'stat-why', s.why));
      pinkCard.appendChild(text('div', 'stat-cta-note', '재진 예약을 잡거나 병원에 문의해 주세요.'));
      frag.appendChild(pinkCard);
    }

    /* 복약지도 보기 버튼 */
    frag.appendChild(btn('btn--full btn--accent', '복약지도 보기', function () {
      state.tab = '복약지도';
      buildTabBar(d);
      renderBody(d);
      window.scrollTo(0, 0);
    }));

    return frag;
  }

  /* ════════════════════════
     3·4번 화면: 복약지도 (P2)
  ════════════════════════ */
  function renderGuide(d) {
    var g    = d.guide;
    var frag = document.createDocumentFragment();

    /* 오늘 진료 요약 */
    var sumCard = el('div', 'card');
    sumCard.appendChild(text('div', 'card__section-title', '오늘 진료 요약'));
    sumCard.appendChild(g.summary
      ? richEl('div', 'care-body-text', g.summary)
      : emptyState('표시할 승인 복약 안내가 아직 없어요.'));
    frag.appendChild(sumCard);

    /* 나의 목표 — 값이 없는 목표도 숨기지 않고 차트 없는 상태로 설명한다. */
    var goalCard = el('div', 'card');
    var goalHead = el('div', 'goal-head');
    goalHead.appendChild(text('span', 'card__section-title', '나의 목표'));
    if (d.visit) goalHead.appendChild(text('span', 'goal-date', d.visit));
    goalCard.appendChild(goalHead);

    if (!g.goals || !g.goals.length) {
      goalCard.appendChild(emptyState('등록된 검사 목표가 없어 차트를 표시하지 않아요.'));
    } else {
      g.goals.forEach(function (goal, i) {
        var item = el('div', 'goal-item' + (i === 0 ? ' goal-item--first' : ''));
        item.appendChild(text('div', 'goal-name', goal.n));
        if (goal.rangeLabel) item.appendChild(text('div', 'goal-range-label', goal.rangeLabel));

        var nowNum    = parseFloat(goal.now);
        var startNum  = parseFloat(goal.a);
        var targetNum = parseFloat(goal.t);
        var hasStart  = !isNaN(startNum);
        var hasTarget = !isNaN(targetNum);
        var chartReady = goal.hasChart && !isNaN(nowNum) && (hasStart || hasTarget);

        if (chartReady) {
        var chart = el('div', 'goal-chart');

        /* 목표값을 중앙(50%)에 고정하고 나머지 값을 상대 위치로 계산.
           목표가 없는 경우(추이 관찰)는 시작값을 중앙 기준으로 사용. */
        var center    = hasTarget ? targetNum : startNum;
        var maxDiff   = Math.max(
          Math.abs(nowNum - center),
          hasStart ? Math.abs(startNum - center) : 0,
          1
        );
        var half      = maxDiff * 1.5;
        function pctNum(v) {
          return Math.min(95, Math.max(5, 50 + (v - center) / half * 50));
        }
        function pct(v) { return pctNum(v) + '%'; }

        /* 삼각형 포인터 */
        var pointerRow = el('div', 'goal-chart__pointer-row');
        var pointer    = el('div', 'goal-chart__pointer');
        pointer.style.left = pct(nowNum);
        pointer.appendChild(text('span', 'goal-chart__now-val', goal.now));
        pointer.appendChild(el('div', 'goal-chart__arrow'));
        pointerRow.appendChild(pointer);
        chart.appendChild(pointerRow);

        /* 그라디언트 바 */
        var barWrap = el('div', 'goal-chart__bar-wrap');
        if (hasTarget) {
          var tLine = el('span', 'goal-chart__target-line');
          tLine.style.left = '50%';
          barWrap.appendChild(tLine);
        }
        if (hasStart) {
          var sLine = el('span', 'goal-chart__start-line');
          sLine.style.left = hasTarget ? pct(startNum) : '50%';
          barWrap.appendChild(sLine);
        }
        chart.appendChild(barWrap);

        /* v3 정본은 목표(또는 시작)를 가운데 둔 세 구간과 실제 시작·현재 값을
           따로 보여 준다. 저장된 값 밖의 임상 기준치는 만들지 않는다. */
        var scaleLabels = el('div', 'goal-chart__scale-labels');
        [
          hasTarget ? '목표보다 낮음' : '시작보다 낮음',
          hasTarget ? '목표 ' + goal.t : '추이 관찰',
          hasTarget ? '목표보다 높음' : '시작보다 높음',
        ].forEach(function (label) {
          scaleLabels.appendChild(text('span', 'goal-chart__scale-label', label));
        });
        chart.appendChild(scaleLabels);
        var valueSummary = [];
        if (hasStart) valueSummary.push('시작 ' + goal.a);
        valueSummary.push('지금 ' + goal.now);
        chart.appendChild(text('div', 'goal-chart__start-summary', valueSummary.join(' · ')));
        item.appendChild(chart);
        } else {
          var noChart = el('div', 'goal-no-chart');
          noChart.textContent = goal.now
            ? '현재 ' + goal.now
            : '결과가 나오면 채워드릴게요 · 지금 ─';
          item.appendChild(noChart);
        }
        goalCard.appendChild(item);
      });
    }
    if (g.goalSay) goalCard.appendChild(text('div', 'goal-say', g.goalSay));
    frag.appendChild(goalCard);

    /* 더 자세히 보기 토글 */
    var expandBtn = el('button', 'expand-btn' + (state.guideExpanded ? ' expand-btn--open' : ''));
    expandBtn.type = 'button';
    expandBtn.setAttribute('aria-expanded', state.guideExpanded ? 'true' : 'false');
    var expandLabel = text('span', null, state.guideExpanded ? '접기' : '더 자세히 보기');
    var expandIcon  = text('span', 'expand-btn__icon', '⌄');
    expandBtn.appendChild(expandLabel);
    expandBtn.appendChild(expandIcon);

    var expandBody = el('div', 'expand-body' + (state.guideExpanded ? ' expand-body--open' : ''));

    /* v3 정본은 처방약 카드부터 430px 접힘 영역에 포함한다. */
    if (g.drug) {
      var drugCard = el('div', 'card');
      drugCard.appendChild(text('div', 'card__section-title', '처방받은 약'));
      var drugRow = el('div', 'drug-row');
      if (g.drug.n) drugRow.appendChild(text('div', 'drug-row__name', g.drug.n));
      if (g.drug.s) drugRow.appendChild(text('div', 'drug-row__sub', g.drug.s));
      if (g.drug.d) drugRow.appendChild(text('div', 'drug-row__sub', g.drug.d));
      drugCard.appendChild(drugRow);
      expandBody.appendChild(drugCard);
    }

    /* 이 약을 왜 드시나요 */
    if (g.why && g.why.length) {
      var whyCard = el('div', 'card');
      whyCard.appendChild(text('div', 'card__section-title', '이 약을 왜 드시나요'));
      g.why.forEach(function (w, i) {
        var p = richEl('div', 'care-body-text', w);
        if (i === 0) p.style.marginTop = '0';
        whyCard.appendChild(p);
      });
      expandBody.appendChild(whyCard);
    }

    /* 복용 방법 */
    if (g.how) {
      var howCard = el('div', 'card');
      howCard.appendChild(text('div', 'card__section-title', '약별 복용 방법'));
      howCard.appendChild(richEl('div', 'care-body-text', g.how));
      expandBody.appendChild(howCard);
    }

    /* 다음 방문 */
    if (g.next) {
      var nextCard = el('div', 'card');
      nextCard.appendChild(text('div', 'card__section-title', '다음 방문 계획'));
      nextCard.appendChild(richEl('div', 'care-body-text', g.next));
      expandBody.appendChild(nextCard);
    }

    expandBtn.addEventListener('click', function () {
      state.guideExpanded = !state.guideExpanded;
      expandLabel.textContent = state.guideExpanded ? '접기' : '더 자세히 보기';
      expandBtn.className = 'expand-btn' + (state.guideExpanded ? ' expand-btn--open' : '');
      expandBtn.setAttribute('aria-expanded', state.guideExpanded ? 'true' : 'false');
      expandBody.className = 'expand-body' + (state.guideExpanded ? ' expand-body--open' : '');
    });

    if (expandBody.children.length) {
      frag.appendChild(expandBody);
      frag.appendChild(expandBtn);
    }
    return frag;
  }

  /* ════════════════════════
     5번 화면: 주의사항 (P3)
  ════════════════════════ */
  function renderCare(d) {
    var c    = d.care;
    var frag = document.createDocumentFragment();
    var hasCareContent = c.blocks.length || c.danger.length || c.ask;

    /* 제목 */
    var titleWrap = el('div', 'tab-title');
    titleWrap.appendChild(text('div', 'tab-title__main', c.title));
    titleWrap.appendChild(text('div', 'tab-title__sub', '미리 알아두시면 걱정을 덜 수 있어요'));
    frag.appendChild(titleWrap);

    /* 블록 카드들 */
    var fadeWrap = el('div', 'care-fade-wrap');
    if (!state.careExpanded && hasCareContent) fadeWrap.style.maxHeight = '430px';

    c.blocks.forEach(function (block) {
      var card = el('div', 'card');
      card.appendChild(text('div', 'card__section-title', block.t));
      block.p.forEach(function (p, i) {
        var pEl = richEl('div', 'care-body-text', p);
        if (i === 0) pEl.style.marginTop = '0';
        card.appendChild(pEl);
      });
      fadeWrap.appendChild(card);
    });

    if (!c.blocks.length && !c.danger.length && !c.ask) {
      fadeWrap.appendChild(emptyState('표시할 승인 주의사항이 아직 없어요.'));
    }

    /* 긴급 카드 */
    if (c.danger.length) {
      var dangerCard = el('div', 'card card--danger');
      dangerCard.style.borderRadius = '22px';
      dangerCard.appendChild(text('div', 'danger-title', '🚨 바로 병원에 연락하세요'));
      c.danger.forEach(function (d) {
        dangerCard.appendChild(richEl('div', 'danger-item', d));
      });
      fadeWrap.appendChild(dangerCard);
    }

    /* 문의할 사항 */
    if (c.ask) {
      var askCard = el('div', 'card');
      askCard.appendChild(text('div', 'card__section-title', '문의할 사항'));
      askCard.appendChild(richEl('div', 'care-body-text', c.ask));
      askCard.style.marginTop = '0';
      fadeWrap.appendChild(askCard);
    }

    if (!state.careExpanded && hasCareContent) {
      var fade = el('div', 'care-fade');
      fadeWrap.appendChild(fade);
    }
    frag.appendChild(fadeWrap);

    /* 더 보기 / 접기 버튼 */
    if (!state.careExpanded && hasCareContent) {
      var moreBtn = btn('btn--full btn--accent', '더 자세히 보기', function () {
        state.careExpanded = true;
        renderBody(d);
      });
      frag.appendChild(moreBtn);
    } else if (hasCareContent) {
      var collapseBtn = btn('btn--full btn--accent', '접기', function () {
        state.careExpanded = false;
        renderBody(d);
      });
      frag.appendChild(collapseBtn);
    }

    return frag;
  }

  /* ════════════════════════
     6번 화면: 생활관리 (P4)
  ════════════════════════ */
  function renderLife(d) {
    var life = d.life;
    var frag = document.createDocumentFragment();
    var axisKeys = Object.keys(life.axes);
    if (!state.lifeAxis || axisKeys.indexOf(state.lifeAxis) < 0) state.lifeAxis = axisKeys[0] || null;

    /* 제목 */
    var titleWrap = el('div', 'tab-title');
    titleWrap.appendChild(text('div', 'tab-title__main', '생활관리'));
    titleWrap.appendChild(text('div', 'tab-title__sub', life.sub));
    frag.appendChild(titleWrap);

    if (!life.challenges.length && !axisKeys.length) {
      frag.appendChild(emptyState('표시할 승인 생활관리 안내가 아직 없어요.'));
      return frag;
    }

    /* 4주 챌린지 카드 */
    if (life.challenges.length) {
      var chalCard = el('div', 'card');
      chalCard.appendChild(text('div', 'card__section-title', '이번 4주 챌린지'));
      life.challenges.forEach(function (ch, i) {
        var row = el('div', 'challenge-row' + (i === 0 ? ' challenge-row--first' : ''));
        row.appendChild(text('span', 'challenge-row__text', ch[0]));
        row.appendChild(text('span', 'challenge-row__freq', ch[1]));
        chalCard.appendChild(row);
      });
      chalCard.appendChild(text('div', 'challenge-note',
        '이번 4주 동안 권해드리는 것이에요 · 따로 확인하거나 여쭤보지 않아요\n담당 의료진이 확인한 내용이에요. 무리해서 다 지키지 않아도 괜찮아요.'));
      frag.appendChild(chalCard);
    }

    if (!axisKeys.length) {
      frag.appendChild(emptyState('승인된 세부 생활관리 항목이 아직 없어요.'));
      return frag;
    }

    /* 축 칩 탭 */
    var axisTabBar = el('div', 'axis-tabs');
    axisTabBar.setAttribute('role', 'tablist');
    axisKeys.forEach(function (key) {
      var isActive = key === state.lifeAxis;
      var chip = el('button', 'axis-tab ' + (isActive ? 'axis-tab--active' : 'axis-tab--inactive'));
      chip.type = 'button';
      chip.textContent = key;
      chip.setAttribute('role', 'tab');
      chip.setAttribute('aria-selected', isActive ? 'true' : 'false');
      chip.addEventListener('click', function () {
        state.lifeAxis = key;
        state.lifeExpanded = false;
        renderBody(d);
      });
      axisTabBar.appendChild(chip);
    });
    frag.appendChild(axisTabBar);

    /* 선택한 축의 본문은 v3처럼 일부를 먼저 보여 주고 펼칠 수 있게 한다. */
    var activeAxis = life.axes[state.lifeAxis];
    var hasAxisDetail = activeAxis.p.length > 0;
    var axisIsOpen = state.lifeExpanded || !hasAxisDetail;
    var fadeWrap = el('div', 'life-fade-wrap' + (axisIsOpen ? ' life-fade-wrap--open' : ''));
    var axCard = el('div', 'card');
    axCard.appendChild(text('div', 'card__section-title', activeAxis.title || state.lifeAxis));
    if (activeAxis.chal) {
      axCard.appendChild(text('div', 'axis-chal-label', '★ 이번 챌린지'));
      var chalRow = el('div', 'axis-chal-row');
      chalRow.appendChild(text('span', 'axis-chal-text', activeAxis.chal));
      chalRow.appendChild(text('span', 'axis-chal-freq', activeAxis.goal || ''));
      axCard.appendChild(chalRow);
      axCard.appendChild(el('hr', 'card__divider'));
    }
    activeAxis.p.forEach(function (p, i) {
      var pEl = richEl('div', 'axis-body-text', p);
      if (i === 0 && !activeAxis.chal) pEl.style.marginTop = '0';
      axCard.appendChild(pEl);
    });
    if (!activeAxis.chal && !activeAxis.p.length) {
      axCard.appendChild(emptyState('표시할 승인 생활관리 내용이 아직 없어요.'));
    }
    fadeWrap.appendChild(axCard);
    if (!axisIsOpen) fadeWrap.appendChild(el('div', 'life-fade'));
    frag.appendChild(fadeWrap);

    if (hasAxisDetail) {
      var lifeBtn = btn('btn--full btn--accent', state.lifeExpanded ? '접기' : '더 자세히 보기', function () {
        state.lifeExpanded = !state.lifeExpanded;
        renderBody(d);
      });
      lifeBtn.setAttribute('aria-expanded', state.lifeExpanded ? 'true' : 'false');
      frag.appendChild(lifeBtn);
    }

    return frag;
  }

  /* ── 본문 렌더 ─── */
  function renderBody(d) {
    var body = bodyRoot;
    body.innerHTML = '';
    var frag;
    switch (state.tab) {
      case '현황':    frag = renderStatus(d); break;
      case '복약지도': frag = renderGuide(d);  break;
      case '주의사항': frag = renderCare(d);   break;
      case '생활관리': frag = renderLife(d);   break;
      default:         frag = document.createDocumentFragment();
    }
    body.appendChild(frag);

    /* 모든 탭 공통 하단 푸터 */
    var footer = (typeof GuideFooter === 'function')
      ? GuideFooter({ approvedAt: d.approvedAt, onReport: GUIDE_MOCK ? function () { openReport(); } : null })
      : (function () {
          var f = document.createElement('div');
          f.className = 'guide-footer';
          [
            { cls: 'guide-footer__note', t: 'ⓘ 이 안내는 담당 의료진이 확인한 내용입니다' },
            { cls: 'guide-footer__meta', t: '출처 · 식약처 의약품정보' },
            { cls: 'guide-footer__meta', t: '승인 · ' + (d.approvedAt || '') },
          ].forEach(function (item) {
            var s = document.createElement('span');
            s.className = item.cls;
            s.textContent = item.t;
            f.appendChild(s);
          });
          if (GUIDE_MOCK) {
            var report = document.createElement('button');
            report.type = 'button';
            report.className = 'guide-footer__report';
            report.textContent = '오류 신고';
            report.addEventListener('click', openReport);
            f.appendChild(report);
          }
          return f;
        })();
    body.appendChild(footer);
  }

  /* ── 오류 신고 오버레이 ─── */
  var REPORT_SCREENS = [
    { label: '복약지도 · 오늘 진료 요약', sectionKey: 'medication', contentKey: 'medication.summary' },
    { label: '복약지도 · 나의 목표', sectionKey: 'medication', contentKey: 'medication.goals' },
    { label: '복약지도 · 처방받은 약', sectionKey: 'medication', contentKey: 'medication.list' },
    { label: '복약지도 · 이 약을 왜 드시나요', sectionKey: 'medication', contentKey: 'medication.why' },
    { label: '복약지도 · 복용 방법', sectionKey: 'medication', contentKey: 'medication.how' },
    { label: '복약지도 · 다음 방문 계획', sectionKey: 'medication', contentKey: 'medication.next_visit' },
    { label: '주의사항 · 흔한 반응', sectionKey: 'caution', contentKey: 'caution.common' },
    { label: '주의사항 · 함께 드시면 안 되는 것', sectionKey: 'caution', contentKey: 'caution.interactions' },
    { label: '주의사항 · 바로 병원에 연락할 경우', sectionKey: 'emergency', contentKey: 'emergency.items' },
    { label: '생활관리 · 4주 챌린지', sectionKey: 'life', contentKey: 'life.challenges' },
    { label: '생활관리 · 수면', sectionKey: 'life', contentKey: 'life.sleep' },
    { label: '생활관리 · 뼈 건강', sectionKey: 'life', contentKey: 'life.bone' },
    { label: '생활관리 · 운동', sectionKey: 'life', contentKey: 'life.exercise' },
    { label: '생활관리 · 통증', sectionKey: 'life', contentKey: 'life.pain' },
  ];
  var REPORT_REASONS = [
    { label: '도움이 됨', category: 'HELPFUL' },
    { label: '도움이 되지 않음', category: 'UNHELPFUL' },
    { label: '안내와 다른 내용', category: 'WRONG' },
    { label: '이해하기 어려움', category: 'HARD_TO_UNDERSTAND' },
    { label: '부적절한 의료 안내', category: 'UNSAFE' },
    { label: '기타', category: 'OTHER' },
  ];

  function buildReportOverlay() {
    var overlay = document.createElement('div');
    overlay.className = 'report-overlay';

    /* 헤더 */
    var header = document.createElement('div');
    header.className = 'report-overlay__header';
    var backBtn = document.createElement('button');
    backBtn.type = 'button';
    backBtn.className = 'report-overlay__back';
    backBtn.textContent = '‹';
    backBtn.addEventListener('click', function () { closeReport(); });
    header.appendChild(backBtn);
    overlay.appendChild(header);

    /* 콘텐츠 */
    var content = document.createElement('div');
    content.className = 'report-overlay__content';

    var title = document.createElement('h2');
    title.className = 'report-overlay__title';
    title.textContent = '오류 신고 · 피드백';
    content.appendChild(title);

    var sub = document.createElement('p');
    sub.className = 'report-overlay__sub';
    sub.textContent = '받으신 안내에 대해 알려주세요';
    content.appendChild(sub);

    /* 신고할 화면 */
    var screenLabel = document.createElement('div');
    screenLabel.className = 'report-field-label';
    screenLabel.innerHTML = '신고할 화면 <span aria-hidden="true" style="color:var(--p-dark)">*</span>';
    content.appendChild(screenLabel);

    var select = document.createElement('select');
    select.className = 'report-select';
    REPORT_SCREENS.forEach(function (screen) {
      var opt = document.createElement('option');
      opt.value = screen.contentKey;
      opt.textContent = screen.label;
      select.appendChild(opt);
    });
    var currentScreen = state.tab === '복약지도' ? '복약지도 · 이 약을 왜 드시나요'
                      : state.tab === '주의사항' ? '주의사항 · 흔한 반응'
                      : state.tab === '생활관리' ? '생활관리 · 4주 챌린지'
                      : '복약지도 · 오늘 진료 요약';
    var currentScreenOption = REPORT_SCREENS.find(function (screen) { return screen.label === currentScreen; });
    select.value = currentScreenOption.contentKey;
    content.appendChild(select);

    var screenHint = document.createElement('p');
    screenHint.className = 'report-hint';
    screenHint.textContent = 'ⓘ 눌렀던 화면이 골라져 있어요 · 다른 화면 이야기면 바꿔 주세요';
    content.appendChild(screenHint);

    /* 문제 유형 */
    var reasonLabel = document.createElement('div');
    reasonLabel.className = 'report-field-label';
    reasonLabel.innerHTML = '어떤 점이 문제였나요? <span aria-hidden="true" style="color:var(--p-dark)">*</span>';
    content.appendChild(reasonLabel);

    var selectedReason = null;
    var submissionId = null;
    var reasonBtns = [];
    REPORT_REASONS.forEach(function (reason) {
      var row = document.createElement('div');
      row.className = 'report-reason';

      var radio = document.createElement('span');
      radio.className = 'report-reason__radio';

      var label = document.createElement('span');
      label.className = 'report-reason__label';
      label.textContent = reason.label;

      row.appendChild(radio);
      row.appendChild(label);
      row.addEventListener('click', function () {
        selectedReason = reason;
        reasonBtns.forEach(function (b) { b.classList.remove('report-reason--selected'); });
        row.classList.add('report-reason--selected');
        radio.classList.add('report-reason__radio--selected');
        reasonBtns.forEach(function (b) {
          if (b !== row) b.querySelector('.report-reason__radio').classList.remove('report-reason__radio--selected');
        });
      });
      reasonBtns.push(row);
      content.appendChild(row);
    });

    /* 자세히 */
    var detailLabel = document.createElement('div');
    detailLabel.className = 'report-field-label';
    detailLabel.textContent = '자세히 (선택)';
    content.appendChild(detailLabel);

    var textarea = document.createElement('textarea');
    textarea.className = 'report-textarea';
    textarea.placeholder = '어떤 부분이 다른지 적어주세요';
    textarea.rows = 4;
    textarea.maxLength = 1000;
    content.appendChild(textarea);

    var submitStatus = document.createElement('p');
    submitStatus.className = 'report-hint';
    submitStatus.setAttribute('aria-live', 'polite');
    content.appendChild(submitStatus);

    /* 제출 버튼 */
    var submitBtn = document.createElement('button');
    submitBtn.type = 'button';
    submitBtn.className = 'btn btn--primary report-submit';
    submitBtn.textContent = '보내기';
    submitBtn.disabled = true;
    submitBtn.addEventListener('click', function () {
      if (!selectedReason || submitBtn.disabled) return;
      var selectedScreen = REPORT_SCREENS.find(function (screen) {
        return screen.contentKey === select.value;
      });
      submissionId = submissionId || createFeedbackSubmissionId();
      submitBtn.disabled = true;
      submitBtn.textContent = '보내는 중…';
      submitStatus.textContent = '';
      submitPatientFeedback({
        submission_id: submissionId,
        target: 'GUIDE_SECTION',
        source_screen: 'P9',
        category: selectedReason.category,
        section_key: selectedScreen.sectionKey,
        content_key: selectedScreen.contentKey,
        detected_tab: state.tab,
        details: textarea.value.trim() || null,
      }).then(function () {
        submitBtn.textContent = '저장했어요';
        submitStatus.textContent = '의견을 보내주셔서 감사해요.';
        setTimeout(function () { closeReport(); }, 600);
      }).catch(function () {
        submitBtn.disabled = false;
        submitBtn.textContent = '다시 시도';
        submitStatus.setAttribute('role', 'alert');
        submitStatus.textContent = '저장하지 못했어요. 입력한 내용을 확인한 뒤 다시 시도해 주세요.';
      });
    });
    content.appendChild(submitBtn);

    /* 문제 유형 선택 시 보내기 버튼 활성화 */
    reasonBtns.forEach(function (b) {
      b.addEventListener('click', function () {
        submitBtn.disabled = false;
      });
    });

    overlay.appendChild(content);
    return overlay;
  }

  var reportOverlay = null;
  function openReport() {
    if (reportOverlay) reportOverlay.remove();
    reportOverlay = buildReportOverlay();
    document.body.appendChild(reportOverlay);
    requestAnimationFrame(function () { reportOverlay.classList.add('report-overlay--open'); });
    document.body.style.overflow = 'hidden';
  }
  function closeReport() {
    if (!reportOverlay) return;
    var closing = reportOverlay;
    reportOverlay = null;
    closing.classList.remove('report-overlay--open');
    document.body.style.overflow = '';
    setTimeout(function () { closing.remove(); }, 300);
  }

  /* ── PDF 시트 ─── */
  var PDF_OPTIONS = [
    { key:'guide', label:'복약지도', desc:'오늘 진료 요약 · 나의 목표 · 처방받은 약 · 복용 방법' },
    { key:'care',  label:'주의사항', desc:'흔한 반응 · 함께 드시면 안 되는 것 · 바로 병원에 연락할 경우' },
    { key:'life',  label:'생활관리', desc:'수면 · 뼈 건강 · 운동 · 통증' },
    { key:'stat',  label:'복약 현황', desc:'처방일 기준 소진 예정일' },
  ];
  if (GUIDE_MOCK) {
    var pdfSheet = Sheet({
      title: 'PDF로 저장',
      options: PDF_OPTIONS,
      defaultSelected: state.pdfSelected,
      onSave: function (chosen) {
        state.pdfSelected = chosen;
        alert('PDF 저장 미리보기: ' + chosen.join(', '));
      },
    });
    document.body.appendChild(pdfSheet.backdrop);
    document.body.appendChild(pdfSheet.el);
    document.getElementById('pdf-btn').addEventListener('click', function () { pdfSheet.open(); });
  } else {
    document.getElementById('pdf-btn').hidden = true;
    document.getElementById('pdf-btn').style.display = 'none';
  }

  /* ── 시작 ─── */
  function renderLoadError(error) {
    var code = error && error.code;
    var message = code === GUIDE_ERROR.LINK_EXPIRED
      ? '링크 사용 기간이 끝났어요. 병원에 새 안내 링크를 요청해 주세요.'
      : code === GUIDE_ERROR.LINK_REQUIRED
        ? '안내 링크 정보가 없어요. 받으신 문자 링크를 다시 열어 주세요.'
        : code === GUIDE_ERROR.NOT_FOUND
          ? '링크가 없거나 더 이상 사용할 수 없어요. 병원에 안내 링크를 문의해 주세요.'
        : code === GUIDE_ERROR.CONTRACT
          ? '안내 형식이 맞지 않아 안전하게 표시하지 않았어요. 병원에 문의해 주세요.'
          : '안내를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.';
    bodyRoot.innerHTML = '';
    var box = el('div', 'guide-load-error');
    box.setAttribute('role', 'alert');
    box.appendChild(text('strong', 'guide-load-error__title', '안내를 열 수 없어요'));
    box.appendChild(text('p', 'guide-load-error__message', message));
    if (TOKEN || GUIDE_MOCK) box.appendChild(btn('btn--full', '다시 시도', loadGuide));
    bodyRoot.appendChild(box);
    document.getElementById('tab-bar').innerHTML = '';
    sayGuide('안내를 열 수 없어요');
  }

  function loadGuide() {
    bodyRoot.innerHTML = '';
    bodyRoot.appendChild(text('div', 'guide-loading', '안내를 불러오는 중이에요…'));
    return fetchGuide(TOKEN)
      .then(function (d) {
        state.data = d;
        fillHeader(d);
        buildTabBar(d);
        renderBody(d);
        sayGuide('승인된 안내를 불러왔어요');
        if (window.chatSetGuide) chatSetGuide(d.guide || d);
      })
      .catch(renderLoadError);
  }

  showMockBadge();
  loadGuide();
})();
