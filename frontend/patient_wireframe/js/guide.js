/* 진료 안내 — 화면 02~06  (guide.html) */
(function () {
  if (!document.getElementById('body')) return;

  /* OTP 인증 가드: 직접 URL 접근 차단 */
  if (!sessionStorage.getItem('otp_verified')) {
    location.replace('../html/otp.html');
    return;
  }

  var TOKEN = (function () {
    try { return new URLSearchParams(window.location.search).get('t') || 'mock'; }
    catch (e) { return 'mock'; }
  })();

  var TABS = ['현황', '복약지도', '주의사항', '생활관리'];

  var state = {
    data:          null,
    tab:           '현황',
    guideExpanded: false,
    careExpanded:  false,
    lifeAxis:      null,
    pdfSelected:   ['guide', 'care', 'life', 'stat'],
  };

  /* ── 유틸 ─── */
  function el(tag, cls) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    return n;
  }
  /* HTML 문자열을 innerHTML 로 삽입 (bold 등 와이어프레임 rich text 지원) */
  function richEl(tag, cls, html) {
    var n = el(tag, cls);
    n.innerHTML = html || '';
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

  /* ── 탭 바 (component/tab-bar.js 교체 — 와이어프레임 스타일) ─── */
  function buildTabBar(d) {
    var bar = document.getElementById('tab-bar');
    bar.innerHTML = '';
    TABS.forEach(function (key) {
      var b = el('button', 'tab-bar__btn' + (key === state.tab ? ' tab-bar__btn--active' : ''));
      b.type = 'button';
      b.textContent = key;
      b.setAttribute('role', 'tab');
      b.addEventListener('click', function () {
        if (key === state.tab) return;
        state.tab = key;
        buildTabBar(d);
        renderBody(d);
      });
      bar.appendChild(b);
    });
  }

  /* ── 헤더 메타 ─── */
  function fillHeader(d) {
    document.getElementById('header-patient').textContent =
      d.patient + ' 님 · ' + d.visit + ' · ' + d.clinic;
  }

  /* ════════════════════════
     2번 화면: 현황 (P5)
  ════════════════════════ */
  function renderStatus(d) {
    var s    = d.stat;
    var frag = document.createDocumentFragment();

    /* 처방일 힌트 */
    frag.appendChild(text('div', 'page-hint', d.visit + ' 처방 · ' + d.clinic));

    /* 약 카드 */
    var drugCard = el('div', 'card');
    drugCard.appendChild(text('div', 'stat-drug-name', s.drugName));
    drugCard.appendChild(text('div', 'stat-drug-sub', s.prescribed + '일분'));
    frag.appendChild(drugCard);

    /* 소진 예정 핑크 카드 */
    var pinkCard = el('div', 'card card--pink');
    pinkCard.appendChild(richEl('div', 'stat-out', s.out));
    pinkCard.appendChild(richEl('div', 'stat-why', s.why));
    pinkCard.appendChild(text('div', 'stat-cta-note', '재진 예약을 잡거나 병원에 문의해 주세요.'));

    var btns = el('div', 'stat-btns');
    btns.appendChild(btn('btn--primary', '예약하기 ↗', function () {
      alert('예약 창구는 병원 설정에서 연결됩니다.');
    }));
    btns.appendChild(btn('btn--outline', '문의하기', function () {
      alert('문의 창구는 병원 설정에서 연결됩니다.');
    }));
    pinkCard.appendChild(btns);
    frag.appendChild(pinkCard);

    /* 복약지도 보기 버튼 */
    frag.appendChild(btn('btn btn--full', '복약지도 보기', function () {
      state.tab = '복약지도';
      buildTabBar(d);
      renderBody(d);
      document.getElementById('body').scrollTop = 0;
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
    sumCard.appendChild(richEl('div', 'care-body-text', g.summary));
    frag.appendChild(sumCard);

    /* 나의 목표 */
    var goalCard = el('div', 'card');
    var goalHead = el('div');
    goalHead.style.cssText = 'display:flex;align-items:baseline;gap:8px;margin-bottom:4px';
    goalHead.appendChild(text('span', 'card__section-title', '나의 목표'));
    var goalDate = text('span', null, d.visit);
    goalDate.style.cssText = 'font-size:13px;color:var(--tx-muted);font-variant-numeric:tabular-nums';
    goalHead.appendChild(goalDate);
    goalCard.appendChild(goalHead);

    var visibleGoals = g.goals.filter(function (goal) {
      return !goal.dim && goal.now !== '─';
    });
    visibleGoals.forEach(function (goal, i) {
      var item = el('div', 'goal-item' + (i === 0 ? ' goal-item--first' : ''));
      item.appendChild(text('div', 'goal-name' + (goal.dim ? '" style="color:var(--tx-muted)' : ''), goal.n));
      item.appendChild(text('div', 'goal-range-label', goal.rangeLabel || ''));

      if (goal.hasChart) {
        var chart = el('div', 'goal-chart');
        /* 삼각형 포인터 */
        var pointerRow = el('div', 'goal-chart__pointer-row');
        var pointer    = el('div', 'goal-chart__pointer');
        pointer.style.left = goal.nowPct;
        pointer.appendChild(text('span', 'goal-chart__now-val', goal.now));
        pointer.appendChild(el('div', 'goal-chart__arrow'));
        pointerRow.appendChild(pointer);
        chart.appendChild(pointerRow);
        /* 그라디언트 바 */
        var barWrap = el('div', 'goal-chart__bar-wrap');
        if (goal.tPct !== '200%') {
          var tLine = el('span', 'goal-chart__target-line');
          tLine.style.left = goal.tPct;
          barWrap.appendChild(tLine);
        }
        if (goal.startPct !== '200%') {
          var sLine = el('span', 'goal-chart__start-line');
          sLine.style.left = goal.startPct;
          barWrap.appendChild(sLine);
        }
        chart.appendChild(barWrap);
        /* 텍스트 행 */
        var textRow = el('div', 'goal-chart__text-row');
        textRow.appendChild(text('span', null, goal.startLine));
        textRow.appendChild(text('span', null, goal.targetLabel));
        chart.appendChild(textRow);
        item.appendChild(chart);
      } else {
        var noChart = el('div', 'goal-no-chart');
        noChart.textContent = (goal.note || '') + ' · ' + (goal.startLine || '');
        item.appendChild(noChart);
      }
      goalCard.appendChild(item);
    });

    /* goalSay */
    goalCard.appendChild(richEl('div', 'goal-say', g.goalSay));
    frag.appendChild(goalCard);

    /* 처방받은 약 */
    var drugCard = el('div', 'card');
    drugCard.appendChild(text('div', 'card__section-title', '처방받은 약'));
    var drugRow = el('div', 'drug-row');
    drugRow.appendChild(text('div', 'drug-row__name', g.drug.n));
    drugRow.appendChild(text('div', 'drug-row__sub', g.drug.s));
    drugRow.appendChild(text('div', 'drug-row__sub', g.drug.d));
    drugCard.appendChild(drugRow);
    frag.appendChild(drugCard);

    /* 더 자세히 보기 토글 */
    var expandBtn = el('button', 'expand-btn' + (state.guideExpanded ? ' expand-btn--open' : ''));
    expandBtn.type = 'button';
    var expandLabel = text('span', null, state.guideExpanded ? '접기' : '더 자세히 보기');
    var expandIcon  = text('span', 'expand-btn__icon', '⌄');
    expandBtn.appendChild(expandLabel);
    expandBtn.appendChild(expandIcon);

    var expandBody = el('div', 'expand-body' + (state.guideExpanded ? ' expand-body--open' : ''));

    /* 이 약을 왜 드시나요 */
    var whyCard = el('div', 'card');
    whyCard.appendChild(text('div', 'card__section-title', '이 약을 왜 드시나요'));
    g.why.forEach(function (w, i) {
      var p = richEl('div', 'care-body-text', w);
      if (i === 0) p.style.marginTop = '0';
      whyCard.appendChild(p);
    });
    expandBody.appendChild(whyCard);

    /* 복용 방법 */
    var howCard = el('div', 'card');
    howCard.appendChild(text('div', 'card__section-title', '약별 복용 방법'));
    howCard.appendChild(richEl('div', 'care-body-text', g.how.replace(/\n/g, '<br>')));
    expandBody.appendChild(howCard);

    /* 다음 방문 */
    var nextCard = el('div', 'card');
    nextCard.appendChild(text('div', 'card__section-title', '다음 방문 계획'));
    nextCard.appendChild(text('div', 'care-body-text', g.next));
    var linkNote = text('p', 'link-expiry-note', '이 링크는 진료 후 3일간 열려요. 나중에도 보고 싶다면 PDF로 저장해 두세요.');
    linkNote.style.cssText = 'font-size:12px;line-height:14px;color:var(--tx-muted);margin-top:12px;';
    nextCard.appendChild(linkNote);
    expandBody.appendChild(nextCard);

    expandBtn.addEventListener('click', function () {
      state.guideExpanded = !state.guideExpanded;
      expandLabel.textContent = state.guideExpanded ? '접기' : '더 자세히 보기';
      expandBtn.className = 'expand-btn' + (state.guideExpanded ? ' expand-btn--open' : '');
      expandBody.className = 'expand-body' + (state.guideExpanded ? ' expand-body--open' : '');
    });

    frag.appendChild(expandBody);
    frag.appendChild(expandBtn);
    return frag;
  }

  /* ════════════════════════
     5번 화면: 주의사항 (P3)
  ════════════════════════ */
  function renderCare(d) {
    var c    = d.care;
    var frag = document.createDocumentFragment();

    /* 제목 */
    var titleWrap = el('div', 'tab-title');
    titleWrap.appendChild(text('div', 'tab-title__main', c.title));
    titleWrap.appendChild(text('div', 'tab-title__sub', '미리 알아두시면 걱정을 덜 수 있어요'));
    frag.appendChild(titleWrap);

    /* 블록 카드들 */
    var fadeWrap = el('div', 'care-fade-wrap');
    if (!state.careExpanded) fadeWrap.style.maxHeight = '420px';

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

    /* 긴급 카드 */
    var dangerCard = el('div', 'card card--danger');
    dangerCard.style.borderRadius = '22px';
    dangerCard.appendChild(text('div', 'danger-title', '🚨 바로 병원에 연락하세요'));
    c.danger.forEach(function (d) {
      dangerCard.appendChild(text('div', 'danger-item', d));
    });
    fadeWrap.appendChild(dangerCard);

    /* 문의할 사항 */
    var askCard = el('div', 'card');
    askCard.appendChild(text('div', 'card__section-title', '문의할 사항'));
    askCard.appendChild(text('div', 'care-body-text', c.ask));
    askCard.style.marginTop = '0';
    var askBtn = btn('btn btn--full', '문의하기', function () {
      alert('문의 창구는 병원 설정에서 연결됩니다.');
    });
    askBtn.style.marginTop = '16px';
    askCard.appendChild(askBtn);
    fadeWrap.appendChild(askCard);

    if (!state.careExpanded) {
      var fade = el('div', 'care-fade');
      fadeWrap.appendChild(fade);
    }
    frag.appendChild(fadeWrap);

    /* 더 보기 / 접기 버튼 */
    if (!state.careExpanded) {
      var moreBtn = btn('btn btn--full', '더 자세히 보기', function () {
        state.careExpanded = true;
        renderBody(d);
      });
      frag.appendChild(moreBtn);
    } else {
      var collapseBtn = btn('btn btn--full', '접기', function () {
        state.careExpanded = false;
        renderBody(d);
        document.getElementById('body').scrollTop = 0;
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
    if (!state.lifeAxis || axisKeys.indexOf(state.lifeAxis) < 0) state.lifeAxis = axisKeys[0];

    /* 제목 */
    var titleWrap = el('div', 'tab-title');
    titleWrap.appendChild(text('div', 'tab-title__main', '생활관리'));
    titleWrap.appendChild(text('div', 'tab-title__sub', life.sub));
    frag.appendChild(titleWrap);

    /* 4주 챌린지 카드 */
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

    /* 축 칩 탭 */
    var axisTabBar = el('div', 'axis-tabs');
    axisTabBar.setAttribute('role', 'tablist');

    var axisSections = {};
    axisKeys.forEach(function (key) {
      var isActive = key === state.lifeAxis;
      var chip = el('button', 'axis-tab ' + (isActive ? 'axis-tab--active' : 'axis-tab--inactive'));
      chip.type = 'button';
      chip.textContent = key;
      chip.setAttribute('role', 'tab');
      chip.setAttribute('aria-selected', isActive ? 'true' : 'false');
      chip.addEventListener('click', function () {
        state.lifeAxis = key;
        /* 칩 스타일 업데이트 */
        axisTabBar.querySelectorAll('.axis-tab').forEach(function (c) {
          c.className = 'axis-tab axis-tab--inactive';
          c.setAttribute('aria-selected', 'false');
        });
        chip.className = 'axis-tab axis-tab--active';
        chip.setAttribute('aria-selected', 'true');
        /* 섹션 전환 */
        Object.keys(axisSections).forEach(function (k) {
          axisSections[k].style.display = k === key ? 'block' : 'none';
        });
      });
      axisTabBar.appendChild(chip);
    });
    frag.appendChild(axisTabBar);

    /* 각 축 내용 카드 */
    axisKeys.forEach(function (key) {
      var ax   = life.axes[key];
      var isActive = key === state.lifeAxis;
      var sec  = el('div');
      sec.style.display = isActive ? 'block' : 'none';

      var axCard = el('div', 'card');
      axCard.appendChild(text('div', 'card__section-title', ax.title || key));
      if (ax.chal) {
        axCard.appendChild(text('div', 'axis-chal-label', '★ 이번 챌린지'));
        var chalRow = el('div', 'axis-chal-row');
        chalRow.appendChild(text('span', 'axis-chal-text', ax.chal));
        chalRow.appendChild(text('span', 'axis-chal-freq', ax.goal || ''));
        axCard.appendChild(chalRow);
        axCard.appendChild(el('hr', 'card__divider'));
      }
      ax.p.forEach(function (p, i) {
        var pEl = richEl('div', 'axis-body-text', p);
        if (i === 0 && !ax.chal) pEl.style.marginTop = '0';
        axCard.appendChild(pEl);
      });
      sec.appendChild(axCard);
      axisSections[key] = sec;
      frag.appendChild(sec);
    });

    return frag;
  }

  /* ── 본문 렌더 ─── */
  function renderBody(d) {
    var body = document.getElementById('body');
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
      ? GuideFooter({ generatedAt: d.visit + ' 10:44', onReport: function () { openReport(); } })
      : (function () {
          var f = document.createElement('div');
          f.className = 'guide-footer';
          [
            { cls: 'guide-footer__note', t: 'ⓘ 이 안내는 담당 의료진이 확인한 내용입니다' },
            { cls: 'guide-footer__meta', t: '출처 · 식약처 의약품정보' },
            { cls: 'guide-footer__meta', t: '생성 · ' + d.visit + ' 10:44' },
          ].forEach(function (item) {
            var s = document.createElement('span');
            s.className = item.cls;
            s.textContent = item.t;
            f.appendChild(s);
          });
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'guide-footer__report';
          btn.textContent = '오류 신고';
          btn.addEventListener('click', function () { alert('오류 신고 기능은 서버 연동 후 동작합니다.'); });
          f.appendChild(btn);
          return f;
        })();
    body.appendChild(footer);
  }

  /* ── 오류 신고 오버레이 ─── */
  var REPORT_SCREENS = [
    '복약지도 · 오늘 진료 요약',
    '복약지도 · 나의 목표',
    '복약지도 · 처방받은 약',
    '복약지도 · 이 약을 왜 드시나요',
    '복약지도 · 복용 방법',
    '복약지도 · 다음 방문 계획',
    '주의사항 · 흔한 반응',
    '주의사항 · 함께 드시면 안 되는 것',
    '주의사항 · 바로 병원에 연락할 경우',
    '생활관리 · 4주 챌린지',
    '생활관리 · 수면',
    '생활관리 · 뼈 건강',
    '생활관리 · 운동',
    '생활관리 · 통증',
  ];
  var REPORT_REASONS = [
    '도움이 됨',
    '도움이 되지 않음',
    '안내와 다른 내용',
    '이해하기 어려움',
    '부적절한 의료 안내',
    '기타',
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
    screenLabel.textContent = '신고할 화면';
    content.appendChild(screenLabel);

    var select = document.createElement('select');
    select.className = 'report-select';
    REPORT_SCREENS.forEach(function (s) {
      var opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      select.appendChild(opt);
    });
    var currentScreen = state.tab === '복약지도' ? '복약지도 · 이 약을 왜 드시나요'
                      : state.tab === '주의사항' ? '주의사항 · 흔한 반응'
                      : state.tab === '생활관리' ? '생활관리 · 4주 챌린지'
                      : '복약지도 · 오늘 진료 요약';
    select.value = currentScreen;
    content.appendChild(select);

    var screenHint = document.createElement('p');
    screenHint.className = 'report-hint';
    screenHint.textContent = 'ⓘ 눌렀던 화면이 골라져 있어요 · 다른 화면 이야기면 바꿔 주세요';
    content.appendChild(screenHint);

    /* 문제 유형 */
    var reasonLabel = document.createElement('div');
    reasonLabel.className = 'report-field-label';
    reasonLabel.textContent = '어떤 점이 문제였나요?';
    content.appendChild(reasonLabel);

    var selectedReason = null;
    var reasonBtns = [];
    REPORT_REASONS.forEach(function (r) {
      var row = document.createElement('div');
      row.className = 'report-reason';

      var radio = document.createElement('span');
      radio.className = 'report-reason__radio';

      var label = document.createElement('span');
      label.className = 'report-reason__label';
      label.textContent = r;

      row.appendChild(radio);
      row.appendChild(label);
      row.addEventListener('click', function () {
        selectedReason = r;
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
    content.appendChild(textarea);

    /* 제출 버튼 */
    var submitBtn = document.createElement('button');
    submitBtn.type = 'button';
    submitBtn.className = 'btn btn--primary report-submit';
    submitBtn.textContent = '보내기';
    submitBtn.addEventListener('click', function () {
      alert('[미구현] 오류 신고 기능은 서버 연동 후 동작합니다.');
      closeReport();
    });
    content.appendChild(submitBtn);

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
    { key:'stat',  label:'복약 현황', desc:'약별 남은 일수와 소진 예정일' },
  ];
  var pdfSheet = Sheet({
    title: 'PDF로 저장',
    options: PDF_OPTIONS,
    defaultSelected: state.pdfSelected,
    onSave: function (chosen) {
      state.pdfSelected = chosen;
      alert('PDF 저장: ' + chosen.join(', ') + '\n(실제 저장은 서버 연동 후 동작합니다)');
    },
  });
  document.body.appendChild(pdfSheet.backdrop);
  document.body.appendChild(pdfSheet.el);
  document.getElementById('pdf-btn').addEventListener('click', function () { pdfSheet.open(); });

  /* ── 시작 ─── */
  fetchGuide(TOKEN)
    .then(function (d) {
      state.data = d;
      fillHeader(d);
      buildTabBar(d);
      renderBody(d);
      if (window.chatSetGuide) chatSetGuide(d);
    })
    .catch(function (err) {
      document.getElementById('body').innerHTML =
        '<div style="padding:40px 20px;text-align:center;color:var(--tx-muted)">안내를 불러오지 못했어요.<br>잠시 뒤 다시 열어 주세요.</div>';
      console.error(err);
    });
})();
