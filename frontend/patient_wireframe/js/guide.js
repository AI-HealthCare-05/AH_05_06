/* 진료 안내 — 화면 02~06  (guide.html) */
(function () {
  var bodyRoot = document.getElementById('body') || document.getElementById('guide-body');
  if (!bodyRoot) return;

  /* P1 목업 인증 가드. 실제 안내 조회는 정본 API 계약대로 링크 자체가 접근
     증명이며, 고정 OTP 목업으로 실제 환자 진입을 막지 않는다. 목업 왕복 중
     토큰은 fragment로만 전달하고 브라우저 저장소에는 복사하지 않는다. */
  /* **주소에서 지운 뒤에도 토큰을 찾을 수 있어야 한다** — KEY-260.
   *
   * 아래 `takeGuideToken()` 이 access log 에 안 남기려고 토큰을 주소에서 지우고
   * `TOKEN` 에 담는다(KEY-205). 그런데 이 함수가 **주소를 다시 읽고** 있어서, 그
   * 뒤에 부르면 빈 손으로 돌아온다.
   *
   * 실제로 그런 자리가 있다 — 세션만 끝난 401 에서 OTP 화면으로 돌려보내는 갈래
   * (KEY-178). 거기서 토큰을 잃으면 환자는 **어느 안내로 돌아가야 하는지 모르는**
   * OTP 화면에 떨어져, 받았던 문자를 다시 찾아야 한다.
   *
   * `TOKEN` 을 먼저 본다. 이 함수는 그것이 담기기 **전에도** 한 번 불리므로
   * (목업 갈래) 주소 읽기를 폴백으로 남긴다 — `var` 는 끌어올려져 그때는
   * `undefined` 다. */
  function otpEntryUrl() {
    var query = new URLSearchParams(window.location.search);
    var token = TOKEN || linkTokenFrom(window.location, ['t', 'visit']);
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
    /* 읽는 규칙은 `frontend/js/link-token.js` 한 곳에 있다 (이희진 님 `#255` ③).
       지우는 일은 이 화면만 한다 — 안내 화면은 토큰을 주소에서 **떼어** 내고
       기억에만 둔다(KEY-205). */
    var token = linkTokenFrom(window.location, ['t', 'visit']);

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
    pdfSelected:   ['guide', 'care', 'life'],
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
        /* 서버에 「이 장을 열었다」를 남긴다 (KEY-256). 그리기 전에 부르되
           **기다리지 않는다** — 통계가 화면을 늦추면 안 된다. */
        markGuidePageRead(TOKEN, key);
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
    /* 이름은 서버가 OTP 인증한 뷰어에게만 넣어 준다(KEY-268). 없으면 진료일·의원명만. */
    var meta = [d.patient || null, d.visit ? d.visit + ' 진료' : '승인된 진료 안내', d.clinic].filter(Boolean);
    var header = document.getElementById('header-patient');
    header.textContent = '';
    if (d.patient) {
      var name = richEl('strong', 'header__patient-name', d.patient);
      header.appendChild(name);
      header.appendChild(document.createTextNode(' 님 · ' + meta.slice(1).join(' · ')));
    } else {
      header.textContent = meta.join(' · ');
    }
  }

  function showMockBadge() {
    if (!GUIDE_MOCK || document.getElementById('mock-mode-banner')) return;
    var badge = text('div', 'guide-mock-badge', '개발용 MOCK 모드 — 실제 서버 데이터가 아닙니다');
    badge.id = 'mock-mode-banner';
    badge.setAttribute('role', 'status');
    document.body.prepend(badge);
    /* fixed 배너가 sticky 헤더와 PDF 저장 버튼을 덮지 않도록 실제 높이만큼
       본문을 내린다. 좁은 화면에서 문구가 두 줄이 되어도 고정값에 기대지 않는다. */
    var badgeHeight = badge.getBoundingClientRect ? Math.ceil(badge.getBoundingClientRect().height) : 0;
    var offset = badgeHeight || 36;
    document.body.style.paddingTop = offset + 'px';
    document.documentElement.style.setProperty('--guide-mock-offset', offset + 'px');
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
      /* 탭을 바꾸는 길이 둘이다 — 탭 단추와 이 버튼. 한쪽만 남기면
         「버튼으로 넘어간 환자」가 안 세어진다. */
      markGuidePageRead(TOKEN, state.tab);
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

    /* 오늘 진료 요약 — 서버가 확정 데이터로 지은 문장이다. 처방 세트가 없는
       진료는 문장이 없고, 그때는 카드를 세우지 않는다(KEY-365). */
    if (g.summary) {
      var sumCard = el('div', 'card');
      sumCard.appendChild(text('div', 'card__section-title', '오늘 진료 요약'));
      sumCard.appendChild(richEl('div', 'care-body-text', g.summary));
      frag.appendChild(sumCard);
    }

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

    /* 본문의 「■ 소제목」 중 고정 카드와 짝이 없는 것 (KEY-365) */
    (g.blocks || []).forEach(function (block) {
      var blockCard = el('div', 'card');
      blockCard.appendChild(text('div', 'card__section-title', block.t));
      block.p.forEach(function (p, i) {
        var pEl = richEl('div', 'care-body-text', p);
        if (i === 0) pEl.style.marginTop = '0';
        blockCard.appendChild(pEl);
      });
      expandBody.appendChild(blockCard);
    });

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

    if (!expandBody.children.length) {
      if (!g.summary) {
        var emptyCard = el('div', 'card');
        emptyCard.appendChild(emptyState('표시할 승인 복약 안내가 아직 없어요.'));
        frag.appendChild(emptyCard);
      }
    } else if (!g.summary) {
      /* 접어 둘 위 카드가 없으면 단추 하나만 덩그러니 남는다 — 펼친 채로 둔다. */
      expandBody.className = 'expand-body expand-body--open';
      frag.appendChild(expandBody);
    } else {
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
      ? GuideFooter({
          approvedAt: d.approvedAt,
          onHelpful: submitHelpful,
          onUnhelpful: function () { openReport('UNHELPFUL'); },
          onReport: function () { openReport(); },
        })
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
          var report = document.createElement('button');
          report.type = 'button';
          report.className = 'guide-footer__report';
          report.textContent = '오류 신고';
          report.addEventListener('click', function () { openReport(); });
          f.appendChild(report);
          return f;
        })();
    body.appendChild(footer);
  }

  /* ── 오류 신고 오버레이 ─── */
  var REPORT_SCREENS = [
    { label: '복약지도 · 오늘 진료 요약', sectionKey: 'medication', contentKey: 'medication.summary' },
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

  function currentReportScreen() {
    var currentScreen = state.tab === '복약지도' ? '복약지도 · 이 약을 왜 드시나요'
                      : state.tab === '주의사항' ? '주의사항 · 흔한 반응'
                      : state.tab === '생활관리' ? '생활관리 · 4주 챌린지'
                      : '복약지도 · 오늘 진료 요약';
    return REPORT_SCREENS.find(function (screen) { return screen.label === currentScreen; });
  }

  function buildReportOverlay(presetCategory) {
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
    var currentScreenOption = currentReportScreen();
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
      /* 👎 에서 들어왔으면 UNHELPFUL 이유를 미리 골라 둔다 — KEY-361.
         환자가 이미 부정적 의사를 한 번 밝혔으니, 같은 것을 또 고르게
         하지 않는다. */
      if (presetCategory && reason.category === presetCategory) {
        selectedReason = reason;
        row.classList.add('report-reason--selected');
        radio.classList.add('report-reason__radio--selected');
      }
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
    submitBtn.disabled = !selectedReason;
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
  function openReport(presetCategory) {
    if (reportOverlay) reportOverlay.remove();
    reportOverlay = buildReportOverlay(presetCategory);
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

  /* 👍 — 오버레이 없이 즉시 HELPFUL로 제출한다. 대부분의 환자는 문제가
     없으니, 한 번의 탭으로 끝나야 한다(KEY-361). */
  var helpfulSubmitting = false;
  var helpfulSubmissionId = null;
  function submitHelpful(event) {
    if (helpfulSubmitting) return;
    helpfulSubmitting = true;
    var btn = event && event.currentTarget;
    var status = btn && btn.closest('.guide-footer__helpful')
      ? btn.closest('.guide-footer__helpful').querySelector('[data-feedback-status]')
      : null;
    if (btn) { btn.disabled = true; }
    if (status) { status.textContent = ''; }
    helpfulSubmissionId = helpfulSubmissionId || createFeedbackSubmissionId();
    var screen = currentReportScreen();
    submitPatientFeedback({
      submission_id: helpfulSubmissionId,
      target: 'GUIDE_SECTION',
      source_screen: 'P9',
      category: 'HELPFUL',
      section_key: screen.sectionKey,
      content_key: screen.contentKey,
      detected_tab: state.tab,
      details: null,
    }).then(function () {
      if (btn) { btn.textContent = '✓'; }
    }).catch(function () {
      helpfulSubmitting = false;
      if (btn) { btn.disabled = false; }
      if (status) { status.textContent = '전송하지 못했어요. 다시 눌러 주세요.'; }
    });
  }

  /* ── PDF 시트 ─── */
  var PDF_OPTIONS = [
    { key:'guide', label:'복약지도', desc:'오늘 진료 요약 · 처방받은 약 · 복용 방법' },
    { key:'care',  label:'주의사항', desc:'흔한 반응 · 함께 드시면 안 되는 것 · 바로 병원에 연락할 경우' },
    { key:'life',  label:'생활관리', desc:'수면 · 뼈 건강 · 운동 · 통증' },
  ];
  // 기존 렌더러를 사용하되 생활관리의 모든 하위 축을 포함한다.
  // 임시 렌더링은 화면 탭/펼침 상태나 열람 이벤트를 변경하지 않는다.
  function printSections(chosen) {
    var d = state.data;
    if (!d || !chosen.length) return;
    var sections = [];
    PDF_OPTIONS.forEach(function (option) {
      if (chosen.indexOf(option.key) < 0) return;
      var content;
      if (option.key === 'guide') content = renderGuide(d);
      else if (option.key === 'care') content = renderCare(d);
      else {
        var previousAxis = state.lifeAxis;
        var previousExpanded = state.lifeExpanded;
        try {
          state.lifeExpanded = true;
          var axes = Object.keys(d.life.axes);
          state.lifeAxis = axes[0] || null;
          content = renderLife(d);
          axes.slice(1).forEach(function (key) {
            state.lifeAxis = key;
            var detail = renderLife(d).querySelector('.life-fade-wrap');
            if (detail) content.appendChild(detail);
          });
        } finally {
          state.lifeAxis = previousAxis;
          state.lifeExpanded = previousExpanded;
        }
      }
      sections.push({ label: option.label, content: content });
    });
    GuidePdf.preview(d, sections);
  }
  if (typeof Sheet === 'function' && typeof GuidePdf !== 'undefined') {
    var pdfSheet = Sheet({
      title: 'PDF 저장',
      subtitle: '저장할 항목을 고르세요. 미리보기에서 확인한 뒤 다운로드할 수 있어요.',
      note: '챗봇 대화는 포함되지 않아요. 이름과 진료일이 들어가니 공유에 주의해 주세요.',
      saveLabel: 'PDF 저장',
      options: PDF_OPTIONS,
      defaultSelected: state.pdfSelected,
      onSave: function (chosen) {
        state.pdfSelected = chosen;
        printSections(chosen);
      },
    });
    document.body.appendChild(pdfSheet.backdrop);
    document.body.appendChild(pdfSheet.el);
    document.getElementById('pdf-btn').addEventListener('click', function () {
      if (state.data) pdfSheet.open();
    });
  } else {
    document.getElementById('pdf-btn').hidden = true;
    document.getElementById('pdf-btn').style.display = 'none';
  }

  /* ── 시작 ─── */
  function renderLoadError(error) {
    state.data = null;
    document.getElementById('pdf-btn').hidden = true;
    document.getElementById('pdf-btn').style.display = 'none';
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
    state.data = null;
    document.getElementById('pdf-btn').disabled = true;
    document.getElementById('pdf-btn').hidden = true;
    document.getElementById('pdf-btn').style.display = 'none';
    bodyRoot.innerHTML = '';
    bodyRoot.appendChild(text('div', 'guide-loading', '안내를 불러오는 중이에요…'));
    return fetchGuide(TOKEN)
      .then(function (d) {
        state.data = d;
        document.getElementById('pdf-btn').disabled = false;
        if (typeof Sheet === 'function' && typeof GuidePdf !== 'undefined') {
          document.getElementById('pdf-btn').hidden = false;
          document.getElementById('pdf-btn').style.display = '';
        }
        fillHeader(d);
        buildTabBar(d);
        renderBody(d);
        /* **처음 열리는 장도 읽은 것이다.** 클릭이 없어 탭 손잡이를 안 타므로
           여기서 한 번 남긴다 — 빼면 「현황만 보고 닫은 환자」가 0장으로 뜬다. */
        markGuidePageRead(TOKEN, state.tab);
        sayGuide('승인된 안내를 불러왔어요');
        if (window.chatSetGuide) chatSetGuide(d.guide || d);
      })
      .catch(function (error) {
        // 링크는 살아 있는데 세션만 없거나 끝난 상태다 — 오류로 보여주지
        // 않고 OTP 화면으로 보낸다 (KEY-178). 목업 모드는 이미 위에서 걸러진다.
        if (error && error.code === GUIDE_ERROR.SESSION_EXPIRED) {
          location.replace(otpEntryUrl());
          return;
        }
        renderLoadError(error);
      });
  }

  showMockBadge();
  loadGuide();
})();
