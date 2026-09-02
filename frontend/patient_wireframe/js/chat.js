/* 챗봇 오버레이 — FAB → 하단 패널 */
(function () {
  /* P6 실제 API 연결은 KEY-241 범위 밖이다. 실제 화면에서 목업 답변을
     진짜 의료 안내처럼 보여 주지 않고, ?mock=1 미리보기에서만 연다. */
  if (typeof GUIDE_MOCK === 'undefined' || !GUIDE_MOCK) return;

  var SUGGESTIONS = [
    '약 먹는 시간을 바꿔도 되나요?',
    '부정출혈이 계속돼요',
    '약을 깜박 잊었어요',
  ];

  var MOCK_ANSWERS = {
    '약 먹는 시간을 바꿔도 되나요?':
      '네, 하루 중 편한 시간 하나를 정해 매일 같은 시간에 드시면 됩니다.\n이미 드셨다면 그날 것은 건너뛰지 말고 생각난 즉시 드세요.',
    '부정출혈이 계속돼요':
      '복용 초기 3개월 안에는 소량 출혈이 흔합니다.\n2주 이상 지속되거나 양이 많다면 진료 때 알려주세요.',
    '약을 깜박 잊었어요':
      '생각난 즉시 드세요. 다음 복용 시간이 많이 남지 않았다면 그날 것은 건너뛰고 다음 날 정해진 시간에 드세요.\n절대로 두 배로 드시지 마세요.',
  };

  var guide = null;
  var linkToken = null;
  var state = {
  messages: [],
  busy: false,
  draft: '',
  generation: 0,
  requestController: null,
  };

  /* ── DOM 초기화 ────────────────────────── */
  var backdrop   = document.getElementById('chat-backdrop');
  var panel      = document.getElementById('chat-panel');
  var closeBtn   = document.getElementById('chat-close');
  var messages   = document.getElementById('chat-messages');
  var input      = document.getElementById('chat-input');
  var sendBtn    = document.getElementById('chat-send');
  var abortBtn   = document.getElementById('chat-abort');

  if (!panel) return; /* 가드 */

  /* ── FAB ─── */
  /* .app의 max-width(430px)를 기준으로 오른쪽 여백을 계산한다.
   * 뷰포트가 430px보다 넓으면 앱 컨테이너 오른쪽 끝에서 20px 안쪽에 배치한다. */
  var _vw = window.innerWidth;
  var _appRight = Math.round(Math.max(20, (_vw - 430) / 2 + 20));
  var _vvh = (window.visualViewport && window.visualViewport.height > 100)
    ? window.visualViewport.height
    : window.innerHeight;
  var _fabBottom = Math.max(16, Math.round(_vvh * 0.04));
  var fab = Fab({ defaultBottom: _fabBottom, defaultRight: _appRight }, openPanel);
  document.body.appendChild(fab.el);

  /* ── 열기 / 닫기 ────────────────────────── */
  function openPanel() {
    panel.style.visibility = 'visible';
    backdrop.classList.add('chat-backdrop--open');
    panel.classList.add('chat-panel--open');
    fab.el.style.display = 'none';
    document.body.style.overflow = 'hidden';
    if (state.messages.length === 0) renderIntro();
    scrollBottom();
    /* 모바일 Safari에서 입력창 자동 포커스가 페이지 확대와 키보드 노출을
     * 일으키므로, 정밀 포인터를 쓰는 데스크톱 환경에서만 포커스한다. */
    if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
      input.focus();
    }
  }
  function closePanel() {
    backdrop.classList.remove('chat-backdrop--open');
    panel.classList.remove('chat-panel--open');
    document.body.style.overflow = '';
    setTimeout(function () {
      if (!panel.classList.contains('chat-panel--open')) {
        panel.style.visibility = '';
        fab.el.style.display = '';
      }
    }, 320);
  }

  backdrop.addEventListener('click', closePanel);
  closeBtn.addEventListener('click', closePanel);

  /* ── 안내 초기 화면 ─────────────────────── */
  function renderIntro() {
    var g = guide || {};
    var drugName = g.drug && g.drug.n ? g.drug.n : '처방 약';

    var intro = document.createElement('div');
    intro.className = 'chat-intro';

    var bubble = document.createElement('div');
    bubble.className = 'chat-intro__bubble';
    bubble.textContent = drugName + '에 대해 궁금한 것을 물어보세요.\n승인된 안내 내용 안에서 답해드려요.';
    intro.appendChild(bubble);

    var safe = document.createElement('p');
    safe.className = 'chat-intro__safe';
    safe.textContent = 'ⓘ 링크와 인증번호 원문은 서버 로그에 남기지 않아요.';
    intro.appendChild(safe);

    var sugg = document.createElement('div');
    sugg.className = 'chat-suggestions';
    SUGGESTIONS.forEach(function (q) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chat-suggestion';
      btn.textContent = q;
      btn.addEventListener('click', function () { sendQuestion(q); });
      sugg.appendChild(btn);
    });
    intro.appendChild(sugg);

    messages.appendChild(intro);
  }

  /* ── 메시지 렌더 ─────────────────────────── */
  function renderMessages() {
    /* intro 이후 유저 메시지부터 그린다 */
    var existingRows = messages.querySelectorAll('.chat-row');
    existingRows.forEach(function (r) { r.remove(); });

    state.messages.forEach(function (msg) {
      messages.appendChild(makeRow(msg));
    });
    scrollBottom();
  }

  function makeRow(msg) {
    var row = document.createElement('div');
    row.className = 'chat-row' + (msg.role === 'user' ? ' chat-row--user' : '');

    if (msg.role === 'user') {
      var bubble = document.createElement('div');
      bubble.className = 'chat-bubble chat-bubble--user';
      bubble.textContent = msg.text;
      row.appendChild(bubble);
    } else {
      var answer = document.createElement('div');
      answer.className = 'chat-answer' +
        (msg.urgent    ? ' chat-answer--urgent'    : '') +
        (msg.streaming ? ' chat-answer--streaming' : '') +
        (msg.aborted   ? ' chat-answer--aborted'   : '');

      if (msg.urgent) {
        var badge = document.createElement('p');
        badge.className = 'chat-answer__urgent-badge';
        badge.textContent = '⚠ 긴급 안내';
        answer.appendChild(badge);
      }

      var text = document.createElement('p');
      text.className = 'chat-answer__text';
      text.textContent = msg.aborted
        ? (msg.text ? msg.text + '\n\n(여기서 중단했어요)' : '중단했어요.')
        : (msg.error || msg.text || '답변을 준비하고 있어요…');
      if (msg.streaming) text.id = 'chat-stream-text';
      answer.appendChild(text);

      if (msg.source) {
        var meta = document.createElement('p');
        meta.className = 'chat-answer__meta';
        meta.textContent = '출처 · ' + msg.source;
        answer.appendChild(meta);
      }

      if (!msg.streaming) {
        var actions = document.createElement('div');
        actions.className = 'chat-answer__actions';
        if (msg.error || msg.aborted) {
          var retry = document.createElement('button');
          retry.type = 'button'; retry.className = 'chat-retry';
          retry.textContent = '다시 시도';
          retry.addEventListener('click', function () { retryAnswer(msg); });
          actions.appendChild(retry);
        }
        var contact = document.createElement('button');
        contact.type = 'button'; contact.className = 'chat-contact';
        contact.innerHTML = '<img src="/patient_wireframe/assets/chat_bot.png" alt="" class="chat-contact__icon" aria-hidden="true"> 문의하기';
        contact.addEventListener('click', function () {
          alert('문의 창구는 병원 설정에서 연결됩니다.');
        });
        actions.appendChild(contact);
        answer.appendChild(actions);

        if (!msg.error && !msg.aborted && !msg.fallback && msg.responseRef) {
          answer.appendChild(buildFeedbackActions(msg));
        }

      row.appendChild(answer);
    }
    return row;
  }

  function buildFeedbackActions(msg) {
    var wrap = document.createElement('div');
    wrap.className = 'chat-feedback';
    wrap.setAttribute('aria-label', '답변 도움 평가');

    var prompt = document.createElement('span');
    prompt.className = 'chat-feedback__prompt';
    prompt.textContent = '이 답변이 도움됐나요?';
    wrap.appendChild(prompt);

    [
      { category: 'HELPFUL', label: '도움됨' },
      { category: 'UNHELPFUL', label: '도움 안 됨' },
    ].forEach(function (option) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'chat-feedback__button' +
        (msg.feedbackCategory === option.category ? ' chat-feedback__button--selected' : '');
      button.textContent = msg.feedbackState === 'error' && msg.feedbackCategory === option.category
        ? '다시 시도'
        : option.label;
      button.disabled = msg.feedbackState === 'pending' || msg.feedbackState === 'saved' ||
        (msg.feedbackCategory && msg.feedbackCategory !== option.category);
      button.addEventListener('click', function () { sendFeedback(msg, option.category); });
      wrap.appendChild(button);
    });

    if (msg.feedbackState) {
      var status = document.createElement('span');
      status.className = 'chat-feedback__status';
      status.setAttribute('role', msg.feedbackState === 'error' ? 'alert' : 'status');
      status.textContent = msg.feedbackState === 'saved'
        ? '평가를 저장했어요.'
        : msg.feedbackState === 'error' ? '저장하지 못했어요. 다시 시도해 주세요.' : '저장 중…';
      wrap.appendChild(status);
    }
    return wrap;
  }

  function sendFeedback(msg, category) {
    if (msg.feedbackState === 'pending' || msg.feedbackState === 'saved') return;
    if (msg.feedbackCategory && msg.feedbackCategory !== category) return;
    msg.feedbackCategory = category;
    msg.feedbackSubmissionId = msg.feedbackSubmissionId || createFeedbackSubmissionId();
    msg.feedbackState = 'pending';
    renderMessages();

    submitPatientFeedback({
      submission_id: msg.feedbackSubmissionId,
      target: 'CHATBOT_RESPONSE',
      source_screen: 'P6',
      category: category,
      response_ref: msg.responseRef,
    }).then(function () {
      msg.feedbackState = 'saved';
      renderMessages();
    }).catch(function () {
      msg.feedbackState = 'error';
      renderMessages();
    });
  }

  /* ── 스트리밍 업데이트 ──────────────────── */
  function updateStream(text) {
    var el = document.getElementById('chat-stream-text');
    if (el) el.textContent = text;
  }

  function scrollBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  /* ── 질문 전송 ───────────────────────────── */
  function sendQuestion(q) {
    if (state.busy || !q.trim()) return;
    var gen = ++state.generation;

    state.messages.push({ role: 'user', text: q });
    var answerMsg = { role: 'assistant', text: '', streaming: true };
    state.messages.push(answerMsg);
    state.busy = true;
    state.draft = '';
    input.value = '';
    sendBtn.disabled = true;
    abortBtn.classList.add('chat-abort--show');
    renderMessages();

  if (!GUIDE_MOCK) {
    var controller = new AbortController();
    state.requestController = controller;

    requestChatbotResponse(linkToken, q, controller.signal)
      .then(function (result) {
        if (gen !== state.generation) return;

        answerMsg.text = result.answer || '';
        answerMsg.urgent = !!result.urgent;
        answerMsg.source = result.source;
        answerMsg.responseRef = result.response_ref;
        answerMsg.fallback = !!result.fallback;
      })
      .catch(function (error) {
        if (gen !== state.generation) return;

        if (error.name === 'AbortError') {
          answerMsg.aborted = true;
          return;
        }

        answerMsg.error =
          '답변을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.';
      })
      .finally(function () {
        if (state.requestController === controller) {
          state.requestController = null;
        }

        if (gen !== state.generation) return;

        answerMsg.streaming = false;
        state.busy = false;
        abortBtn.classList.remove('chat-abort--show');
        sendBtn.disabled = false;
        renderMessages();
      });

    return;
  }

    /* Mock: 글자를 조금씩 타이핑 */
    var raw  = MOCK_ANSWERS[q] || '담당 의료진이 확인한 내용 안에서만 답해드릴 수 있어요. 더 자세한 내용은 진료 때 여쭤봐 주세요.';
    var i    = 0;
    var tick = setInterval(function () {
      if (gen !== state.generation) { clearInterval(tick); return; }
      answerMsg.text = raw.slice(0, ++i);
      updateStream(answerMsg.text);
      scrollBottom();
      if (i >= raw.length) {
        clearInterval(tick);
        answerMsg.streaming = false;
        state.busy = false;
        abortBtn.classList.remove('chat-abort--show');
        sendBtn.disabled = false;
        renderMessages();
      }
    }, 18);
  }

  function retryAnswer(msg) {
    if (state.busy) return;
    var at = state.messages.indexOf(msg);
    if (at < 0) return;
    var from = at > 0 && state.messages[at - 1].role === 'user' ? at - 1 : at;
    var q = state.messages[from].text;
    state.messages.splice(from, at - from + 1);
    sendQuestion(q);
  }

  /* ── 입력 이벤트 ─────────────────────────── */
  input.addEventListener('input', function () {
    state.draft = input.value;
    sendBtn.disabled = !input.value.trim() || state.busy;
    /* 높이 자동 조정 */
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuestion(input.value);
    }
  });

  sendBtn.addEventListener('click', function () { sendQuestion(input.value); });

  abortBtn.addEventListener('click', function () {
    if (state.requestController) {
      state.requestController.abort();
      state.requestController = null;
    }

    state.generation++; /* 진행 중인 요청 또는 tick 무효화 */

    var last = state.messages[state.messages.length - 1];

    if (last && last.streaming) {
      last.streaming = false;
      last.aborted = true;
    }

    state.busy = false;
    abortBtn.classList.remove('chat-abort--show');
    sendBtn.disabled = false;
    renderMessages();
  });

  /* ── 외부에서 guide 데이터 주입 ─────────── */
  window.chatSetGuide = function (g, token) {
    guide = g;
    linkToken = token;
  };
})();
