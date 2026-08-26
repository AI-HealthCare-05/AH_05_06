/* 진료 안내 화면 — P2 복약지도 · P3 주의사항 · P4 생활관리 (KEY-93)
 *
 * 탭 다섯 중 복약·주의·생활·챗봇을 그린다. 「현황」은 다른 일감에서 채운다 —
 * 탭을 지우면 환자가 「다섯 중 셋만 있다」는 것을 알 수 없고, 나중에 넣을 때
 * 자리가 달라져 익숙해진 순서가 깨진다.
 *
 * 판정하지 않는다. 목표 표는 「2 남았어요」까지만 쓰고 「정상입니다」·「호전 중」은
 * 쓰지 않는다 — 해석은 진료실에서 한다.
 * 챌린지에 체크박스를 두지 않는다. 의사가 주는 한 방향 권고라 되묻지 않기 때문이다.
 * 누르면 아무 일도 안 일어나는 체크박스는 「눌렀으니 기록됐겠지」로 읽힌다.
 */

var TABS = [
  { key: "guide", label: "복약지도" },
  { key: "caution", label: "주의사항" },
  { key: "life", label: "생활관리" },
  { key: "status", label: "현황", pending: true },
  { key: "chat", label: "챗봇" },
];

var state = {
  guide: null,
  tab: "guide",
  token: "",
  /* `draft` — 치던 글자. 화면을 다시 그리면 입력칸이 새로 만들어져서
       **치던 것이 사라진다.** 실측했다: 질문 하나를 보내는 동안 다른 질문을
       치고 있으면 그대로 날아간다 (KEY-130).

     `generation` — 몇 번째 요청인가. 중단은 **늦게 온 콜백을 버리는 것**으로
       한다. 목업 스트림은 `setTimeout` 재귀라 취소 훅이 없어서, 중단을
       눌러도 조각이 계속 들어오고 끝내 완성본이 화면에 되살아난다. */
  chat: { busy: false, messages: [], draft: "", generation: 0 },
};

function el(tag, className, text) {
  var node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function section(title, opts) {
  var box = el("section", "card" + (opts && opts.strong ? " card--strong" : ""));
  if (title) box.appendChild(el("h2", "card__title", title));
  return box;
}

function paragraphs(parent, lines) {
  (lines || []).forEach(function (line) {
    parent.appendChild(el("p", "card__text", line));
  });
  return parent;
}

function renderContactButton(className) {
  var contact = el("button", className, "💬 문의하기");
  contact.type = "button";
  contact.addEventListener("click", function () {
    notice("문의 주소는 병원 설정에서 정합니다 — 서버가 붙으면 열립니다.");
  });
  return contact;
}

function renderEmergency(lines) {
  var danger = el("section", "card card--danger");
  danger.appendChild(el("p", "card__badge", "⚠"));
  danger.appendChild(el("h2", "card__title", "🚨 바로 병원에 연락하세요"));
  var list = el("ul", "danger__list");
  (lines || []).forEach(function (line) {
    list.appendChild(el("li", null, line));
  });
  danger.appendChild(list);
  danger.appendChild(renderContactButton("button button--contact"));
  return danger;
}

/* ── P2 복약지도 ─────────────────────────────── */
function renderGuideTab(g) {
  var frag = document.createDocumentFragment();

  frag.appendChild(paragraphs(section("오늘 진료 요약"), [g.summary]));

  var goals = section("나의 목표");
  var table = el("table", "goals");
  var head = el("tr");
  ["", "시작", "지금", "목표"].forEach(function (h) {
    head.appendChild(el("th", null, h));
  });
  table.appendChild(head);
  (g.goals || []).forEach(function (row) {
    var tr = el("tr");
    tr.appendChild(el("th", "goals__name", row.name));
    [row.start, row.now, row.target].forEach(function (v, i) {
      tr.appendChild(el("td", i === 1 ? "goals__now" : null, v));
    });
    table.appendChild(tr);
  });
  goals.appendChild(table);
  (g.goal_note || "").split("\n").forEach(function (line) {
    if (line) goals.appendChild(el("p", "card__note", line));
  });
  frag.appendChild(goals);

  var drugs = section("처방받은 약");
  (g.drugs || []).forEach(function (d) {
    var item = el("div", "drug");
    item.appendChild(el("p", "drug__name", d.name));
    /* 성분은 **이름 줄에 괄호로 함께** 적는다 — `브랜드명(성분명) 용량`(KEY-183).
       따로 한 줄을 더 두면 같은 말이 두 번 나온다. 빈 값이 오면 그 줄을 아예
       안 만든다 — 예전에는 빈 `<p>` 가 남아 줄 간격만 벌어졌다. */
    [d.ingredient, d.dosage].forEach(function (line) {
      if (line) item.appendChild(el("p", "drug__sub", line));
    });
    drugs.appendChild(item);
  });
  frag.appendChild(drugs);

  /* 2px 강조 — 좋아져서 끊는 것을 막는 문장이다 */
  frag.appendChild(paragraphs(section("이 약을 왜 드시나요", { strong: true }), g.why));
  frag.appendChild(paragraphs(section("약별 복용 방법"), g.how));
  frag.appendChild(paragraphs(section("다음 방문 계획"), [g.next_visit]));
  frag.appendChild(
    paragraphs(section(null), ["이 링크는 진료 후 3일간 열려요. 나중에도 보고 싶다면 PDF로 저장해 두세요."]),
  );
  return frag;
}

/* ── P3 주의사항 ─────────────────────────────── */
function renderCautionTab(g) {
  var c = g.caution || {};
  var frag = document.createDocumentFragment();

  var head = section(c.title);
  head.appendChild(el("p", "card__note", c.lead));
  frag.appendChild(head);

  (c.groups || []).forEach(function (group) {
    frag.appendChild(paragraphs(section(group.title, { strong: group.strong }), group.items));
  });

  /* 🚨 응급 블록 — 테두리 3px. 이 문구는 어떤 화면에서도 지우거나 고치지 않는다.
     119 안내는 넣지 않는다 — 응급 판단을 화면이 대신하는 꼴이 된다. */
  frag.appendChild(renderEmergency(c.emergency));

  frag.appendChild(paragraphs(section("문의할 사항"), [c.ask]));
  return frag;
}

/* ── P4 생활관리 ─────────────────────────────── */
function renderLifeTab(g) {
  var frag = document.createDocumentFragment();
  frag.appendChild(el("p", "guide__disease", g.disease_label));

  var challenge = section("이번 4주 챌린지", { strong: true });
  var list = el("ul", "challenge");
  (g.challenge || []).forEach(function (item) {
    var li = el("li");
    li.appendChild(el("span", "challenge__text", "· " + item.text));
    li.appendChild(el("span", "challenge__freq", item.freq));
    list.appendChild(li);
  });
  challenge.appendChild(list);
  challenge.appendChild(el("p", "card__note", "이번 4주 동안 권해드리는 것이에요"));
  challenge.appendChild(el("p", "card__note", "따로 확인하거나 여쭤보지 않아요"));
  challenge.appendChild(el("p", "card__note", "담당 의료진이 확인한 내용이에요. 무리해서 다 지키지 않아도 괜찮아요."));
  frag.appendChild(challenge);

  var chips = el("div", "chips");
  (g.axes || []).forEach(function (axis) {
    chips.appendChild(el("span", "chip" + (axis.challenge ? " chip--on" : ""), axis.name));
  });
  frag.appendChild(chips);

  (g.axes || []).forEach(function (axis) {
    var box = section(axis.name);
    if (axis.challenge && axis.item) {
      box.appendChild(el("p", "card__badge-line", "★ 이번 챌린지"));
      var row = el("p", "challenge__row");
      row.appendChild(el("span", "challenge__text", "· " + axis.item.text));
      row.appendChild(el("span", "challenge__freq", axis.item.freq));
      box.appendChild(row);
    }
    paragraphs(box, axis.body);
    frag.appendChild(box);
  });
  return frag;
}

/* ── P6 챗봇 ─────────────────────────────────── */
function chatbotAnswerText(message) {
  if (message.error) return message.error;
  /* 중단은 **실패가 아니다.** 사용자가 그만 받겠다고 한 것이라 사과할 일이
     아니고, 받다 만 글자는 그대로 둔다 — 거기까지는 읽을 수 있다. */
  if (message.aborted) return message.text ? message.text + "\n\n(여기서 중단했어요)" : "중단했어요.";
  return message.text || "답변을 준비하고 있어요…";
}

function updateStreamingAnswer(message) {
  var text = document.getElementById("chat-stream-answer");
  if (!text) return false;
  text.textContent = chatbotAnswerText(message);
  return true;
}

function renderChatMessage(message) {
  if (message.role === "user") {
    var row = el("div", "chat__row chat__row--user");
    row.appendChild(el("div", "chat__bubble chat__bubble--user", message.text));
    return row;
  }
  var answer = el(
    "section",
    "chat__answer" +
      (message.urgent ? " chat__answer--urgent" : "") +
      (message.streaming ? " chat__answer--streaming" : "") +
      (message.aborted ? " chat__answer--aborted" : ""),
  );
  if (message.urgent) answer.appendChild(el("p", "chat__urgent", "⚠ 긴급 안내"));
  var answerText = el("p", "chat__answer-text", chatbotAnswerText(message));
  if (message.streaming) answerText.id = "chat-stream-answer";
  answer.appendChild(answerText);
  if (message.evidence) answer.appendChild(el("p", "chat__evidence", "📎 " + message.evidence));
  if (message.source) answer.appendChild(el("p", "chat__meta", "출처 · " + message.source));
  if (message.limitation) answer.appendChild(el("p", "chat__meta", "한계 · " + message.limitation));
  if (!message.streaming) {
    /* 실패했거나 중단한 답변에는 **다시 시도**가 다음 행동이다. 예전에는
       「잠시 뒤 다시 시도해 주세요」라는 문구만 있고 버튼이 없어서, 환자가
       질문을 손으로 다시 쳐야 했다 (KEY-130). */
    if ((message.error || message.aborted) && message.question) {
      var retry = el("button", "button chat__retry", "다시 시도");
      retry.type = "button";
      retry.addEventListener("click", function () {
        retryChatAnswer(message);
      });
      answer.appendChild(retry);
    }
    answer.appendChild(renderContactButton("button chat__contact"));
  }
  return answer;
}

/* 같은 질문으로 다시 묻는다 — KEY-130.
 *
 * 실패한 답변을 **지우고** 다시 보낸다. 남겨 두면 같은 질문에 대한 답이 둘이
 * 되어 「중복 메시지」가 된다 — 완료 조건이 막으라고 한 것이다. 사용자 질문
 * 말풍선도 함께 지운다. `sendChatQuestion` 이 다시 넣는다.
 */
function retryChatAnswer(message) {
  if (state.chat.busy) return;
  var at = state.chat.messages.indexOf(message);
  if (at === -1) return;
  /* 답변과 그 앞의 질문을 함께 걷는다. */
  var from = at > 0 && state.chat.messages[at - 1].role === "user" ? at - 1 : at;
  state.chat.messages.splice(from, at - from + 1);
  sendChatQuestion(message.question);
}

function renderChatTab() {
  var wrap = el("section", "chat");
  var intro = el("div", "chat__intro");
  intro.appendChild(
    el("p", "chat__intro-text", "받으신 진료 안내를 바탕으로 답변해 드려요. 진단이나 처방 변경은 안내할 수 없어요."),
  );
  var prompts = el("div", "chat__prompts");
  ["내 약이 뭐였죠?", "출혈이 계속돼요", "언제까지 먹나요?"].forEach(function (text) {
    var prompt = el("button", "chat__prompt", text);
    prompt.type = "button";
    prompt.disabled = state.chat.busy;
    prompt.addEventListener("click", function () {
      sendChatQuestion(text);
    });
    prompts.appendChild(prompt);
  });
  intro.appendChild(prompts);
  wrap.appendChild(intro);

  var thread = el("div", "chat__thread");
  thread.setAttribute("aria-live", "polite");
  if (!state.chat.messages.length) {
    thread.appendChild(el("p", "chat__empty", "궁금한 내용을 아래에 입력하거나 질문 예시를 선택해 주세요."));
  }
  state.chat.messages.forEach(function (message) {
    thread.appendChild(renderChatMessage(message));
  });
  wrap.appendChild(thread);

  var form = el("form", "chat__form");
  var input = el("input", "chat__input");
  input.type = "text";
  input.name = "question";
  input.placeholder = "메시지를 입력하세요";
  input.setAttribute("aria-label", "챗봇 질문");
  input.maxLength = 500;
  /* **답변 중에도 다음 질문을 칠 수 있다.** 예전에는 입력칸을 잠갔는데,
     기다리는 동안 할 수 있는 일이 없어진다. 보내는 것만 막으면 된다. */
  input.value = state.chat.draft;
  input.addEventListener("input", function () {
    state.chat.draft = input.value;
  });

  var submit = el("button", "chat__send", "전송");
  submit.type = "submit";
  submit.disabled = state.chat.busy;
  form.appendChild(input);
  form.appendChild(submit);

  /* 답변이 오는 동안에는 **중단**이 다음 행동이다. 「답변 중…」이라고만
     적어 두면 기다리는 것 말고 할 수 있는 것이 없다. */
  if (state.chat.busy) {
    var stop = el("button", "chat__stop", "중단");
    stop.type = "button";
    stop.addEventListener("click", abortChatAnswer);
    form.appendChild(stop);
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var question = input.value.trim();
    if (!question) return;
    /* **초안은 여기서만 비운다** — 입력칸에서 꺼내 보낸 자리다.
       예전에는 `sendChatQuestion` 이 무조건 비웠는데, **다시 시도**도 그 길로
       들어온다. 실패한 답변 아래에서 다음 질문을 치던 중 「다시 시도」를 누르면
       치던 글자가 조용히 사라졌다 — 이 티켓이 고치려던 ③ 이 재시도 경로로
       되살아난 꼴이다 (이희진 님 `#135` 리뷰). */
    state.chat.draft = "";
    sendChatQuestion(question);
  });
  wrap.appendChild(form);
  wrap.appendChild(el("p", "chat__feedback", "이 안내가 도움이 되었나요?　👍　👎　오류 신고"));
  return wrap;
}

/* 답변을 그만 받는다 — KEY-130.
 *
 * **취소 훅이 없다.** 목업 스트림은 `setTimeout` 재귀이고(`chatbot-api.js`),
 * 실서버 어댑터도 `Promise` 만 돌려준다. 그래서 「멈추게」 할 수가 없다.
 *
 * 대신 **세대를 올려 늦게 온 것을 버린다.** 이걸 안 하면 중단을 눌러도
 * 조각이 계속 들어오고, 끝내 완성본(근거·출처·한계까지 붙은)이 화면에
 * 되살아난다 — 사용자는 멈췄다고 생각하는데.
 */
function abortChatAnswer() {
  if (!state.chat.busy) return;
  state.chat.generation += 1;
  state.chat.busy = false;

  var last = state.chat.messages[state.chat.messages.length - 1];
  if (last && last.role === "assistant" && last.streaming) {
    last.streaming = false;
    last.aborted = true;
  }
  renderBody();
}

function sendChatQuestion(question) {
  if (state.chat.busy) return;
  state.chat.busy = true;
  /* 초안은 **건드리지 않는다.** 보내는 길이 둘이라(전송 · 다시 시도) 여기서
     비우면 재시도가 남의 초안을 지운다. 비우는 것은 전송 핸들러의 몫이다. */
  var mine = ++state.chat.generation;
  state.chat.messages.push({ role: "user", text: question });
  /* 질문을 답변에 함께 담는다 — **다시 시도**가 그것을 그대로 쓴다. */
  var answer = { role: "assistant", text: "", streaming: true, question: question };
  state.chat.messages.push(answer);
  renderBody();

  /* 늦게 온 콜백인가. 중단했거나 다음 질문이 시작된 뒤에 도착한 것이다. */
  function stale() {
    return mine !== state.chat.generation;
  }

  return streamChatbotAnswer(
    { link_token: state.token, question: question },
    {
      onDelta: function (chunk) {
        if (stale()) return;
        answer.text += chunk;
        if (!updateStreamingAnswer(answer)) renderBody();
      },
      onComplete: function (result) {
        if (stale()) return;
        answer.streaming = false;
        answer.urgent = !!result.urgent;
        answer.evidence = result.evidence;
        answer.source = result.source;
        answer.limitation = result.limitation;
      },
    },
  )
    .catch(function (err) {
      if (stale()) return;
      answer.streaming = false;
      answer.error = chatbotErrorMessage(err && err.code);
    })
    .finally(function () {
      if (stale()) return;
      state.chat.busy = false;
      renderBody();
    });
}

/* 아직 안 만든 탭 — 무엇이 없는지 말한다. 빈 화면은 고장으로 읽힌다. */
function renderPending(label) {
  var box = section(label);
  box.appendChild(el("p", "card__text", "이 탭은 아직 준비 중이에요. 다른 탭의 안내는 지금 보실 수 있어요."));
  return box;
}

function notice(message) {
  var body = document.getElementById("guide-body");
  var bar = document.getElementById("notice") || el("p", "notice");
  bar.id = "notice";
  bar.textContent = message;
  body.insertBefore(bar, body.firstChild);
  /* **이 배너는 본문이 라이브 리전이라 소리로도 났었다.** 그 속성을 걷으면서
     문의하기·PDF 저장·오류 신고 셋이 조용해졌다 — 고치려던 병을 다른 자리로
     옮긴 셈이었다 (이희진 님 `#131` 리뷰).

     부르는 쪽 셋에 각각 붙이지 않고 **여기 한 곳**에서 알린다. 새 호출부가
     생겨도 따라온다. */
  sayGuide(message);
}

/* 눈에는 안 보이고 **소리로만** 읽히는 한 줄 — KEY-129.
 *
 * 본문(`#guide-body`)을 통째로 라이브 리전으로 두면 탭을 옮길 때마다 안내문
 * 전체가 다시 낭독된다. 실측했더니 탭 3 번에 6 번 읽혔다.
 *
 * 그래서 **무엇으로 바뀌었는지만** 말한다. 내용은 화면이 보여 준다.
 */
function sayGuide(text) {
  var box = document.getElementById("guide-say");
  if (box) box.textContent = text;
}

function renderTabs() {
  var nav = document.getElementById("tabs");
  nav.textContent = "";
  TABS.forEach(function (tab) {
    var button = el("button", "tab" + (state.tab === tab.key ? " tab--on" : ""), tab.label);
    button.type = "button";
    button.setAttribute("aria-current", state.tab === tab.key ? "page" : "false");
    button.addEventListener("click", function () {
      state.tab = tab.key;
      renderTabs();
      renderBody();
      window.scrollTo(0, 0);
      /* **바뀐 것만** 알린다 — 어느 탭으로 왔는지 한 줄. */
      sayGuide(tab.label);
    });
    nav.appendChild(button);
  });
}

/* 다시 그리기 **전에** 커서가 입력칸의 어디에 있었는가. 없으면 `-1`.

   비우고 나서 물으면 늦다 — 지운 노드에서 포커스가 이미 빠져 있다. */
function chatTypingAt() {
  var live = document.activeElement;
  if (!live || String(live.className || "").indexOf("chat__input") === -1) return -1;
  return typeof live.selectionStart === "number" ? live.selectionStart : 0;
}

/* 초안(`draft`)은 되찾는데 **커서는 안 되찾으면**, 다음 질문을 치던 중 앞 답변이
   끝나는 순간 손이 멈춘다. 다시 클릭해야 이어 칠 수 있다 (이희진 님 `#135` 리뷰).

   **치던 자리까지 돌려준다.** 포커스만 주면 커서가 글 끝으로 가서, 문장 중간을
   고치던 중이면 거기서 또 어긋난다. 값은 `draft` 로 똑같이 되살아나 있으므로
   자리는 그대로 유효하다. */
function focusChatInput(at) {
  var input = document.querySelector(".chat__input");
  if (!input || !input.focus) return;
  input.focus();
  if (at >= 0 && input.setSelectionRange) input.setSelectionRange(at, at);
}

function renderBody() {
  var body = document.getElementById("guide-body");
  /* 커서 자리는 **비우기 전에** 들고 온다. */
  var typingAt = chatTypingAt();
  body.textContent = "";
  fillGuideBody(body, state.guide);
  /* 채우는 길이 여럿이다 — 안내문 구조가 새 것이냐 옛 것이냐로 갈리고, 그
     안에서 다시 탭으로 갈린다. **그래서 되돌리는 일은 여기 한 곳에서 한다.**
     분기마다 붙이면 새 분기가 생길 때 또 빠지는데, 실제로 한 번 빠뜨렸다
     (이희진 님 `#135` 리뷰 — 챗봇 탭을 그리는 자리가 둘인데 하나만 이었다). */
  if (state.tab === "chat" && typingAt >= 0) focusChatInput(typingAt);
}

/* 본문을 채우기만 한다 — 커서는 부르는 쪽이 되돌린다. */
function fillGuideBody(body, g) {
  if (!g) return;
  if (g.sections) {
    var keys =
      state.tab === "guide"
        ? ["medication"]
        : state.tab === "caution"
          ? ["caution", "emergency"]
          : state.tab === "life"
            ? ["life"]
            : [];
    if (!keys.length) {
      body.appendChild(state.tab === "chat" ? renderChatTab() : renderPending("복약 현황"));
      return;
    }
    var titles = { medication: "복약지도", caution: "주의사항", emergency: "응급 안내", life: "생활관리" };
    g.sections
      .filter(function (item) {
        return keys.indexOf(item.key) !== -1;
      })
      .forEach(function (item) {
        var lines = String(item.body || "").split("\n");
        body.appendChild(
          item.key === "emergency" ? renderEmergency(lines) : paragraphs(section(titles[item.key]), lines),
        );
      });
    return;
  }
  if (state.tab === "guide") body.appendChild(renderGuideTab(g));
  else if (state.tab === "caution") body.appendChild(renderCautionTab(g));
  else if (state.tab === "life") body.appendChild(renderLifeTab(g));
  else if (state.tab === "chat") body.appendChild(renderChatTab());
  else body.appendChild(renderPending("복약 현황"));
}

/* 안내문이 없을 때 — 승인 전이거나 링크가 닫힌 경우다.
   어느 쪽인지 환자에게 말해 주고, 할 수 있는 일을 남긴다. */
function renderError(code) {
  var body = document.getElementById("guide-body");
  body.textContent = "";
  /* 안내를 못 여는 것은 **알려야 하는 일**이다 — 화면에만 뜨면 못 보는 사람은
     계속 기다린다. */
  sayGuide("아직 안내를 보실 수 없어요");
  var box = section("아직 안내를 보실 수 없어요");
  var message =
    code === GUIDE_ERROR.LINK_EXPIRED
      ? "링크가 닫혔어요. 문자를 다시 받으시면 열립니다."
      : "담당 의료진이 확인을 마치면 문자로 다시 알려드릴게요.";
  box.appendChild(el("p", "card__text", message));
  body.appendChild(box);
  document.getElementById("tabs").textContent = "";
}

function start() {
  var params = new URLSearchParams(window.location.search);
  var token = params.get("t") || params.get("visit") || "";
  state.token = token;

  fetchGuide(token)
    .then(function (guide) {
      state.guide = guide;
      document.getElementById("visit-meta").textContent = guide.sections ? "" : guide.visit_date + " · " + guide.clinic_name;
      document.getElementById("guide-source").textContent = guide.sections
        ? ""
        : "출처 · 식약처 의약품정보 · 생성 " + guide.generated_at;
      renderTabs();
      renderBody();
    })
    .catch(function (err) {
      renderError(err && err.code);
    });

  document.getElementById("pdf-button").addEventListener("click", function () {
    notice("PDF 저장은 다른 일감에서 붙습니다 (P8).");
  });
  document.getElementById("report-button").addEventListener("click", function () {
    notice("오류 신고는 다른 일감에서 붙습니다 (P9).");
  });
}

document.addEventListener("DOMContentLoaded", start);
