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
  chat: { busy: false, messages: [] },
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

function renderEmergency(lines) {
  var danger = el("section", "card card--danger");
  danger.appendChild(el("p", "card__badge", "⚠"));
  danger.appendChild(el("h2", "card__title", "🚨 바로 병원에 연락하세요"));
  var list = el("ul", "danger__list");
  (lines || []).forEach(function (line) {
    list.appendChild(el("li", null, line));
  });
  danger.appendChild(list);
  var contact = el("button", "button button--contact", "💬 문의하기");
  contact.type = "button";
  contact.addEventListener("click", function () {
    notice("문의 주소는 병원 설정에서 정합니다 — 서버가 붙으면 열립니다.");
  });
  danger.appendChild(contact);
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
    item.appendChild(el("p", "drug__sub", d.ingredient));
    item.appendChild(el("p", "drug__sub", d.dosage));
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
function renderChatMessage(message) {
  if (message.role === "user") {
    var row = el("div", "chat__row chat__row--user");
    row.appendChild(el("div", "chat__bubble chat__bubble--user", message.text));
    return row;
  }
  var answer = el("section", "chat__answer" + (message.urgent ? " chat__answer--urgent" : ""));
  if (message.urgent) answer.appendChild(el("p", "chat__urgent", "⚠ 긴급 안내"));
  answer.appendChild(
    el("p", "chat__answer-text", message.text || (message.error ? message.error : "답변을 준비하고 있어요…")),
  );
  if (message.evidence) answer.appendChild(el("p", "chat__evidence", "📎 " + message.evidence));
  if (message.source) answer.appendChild(el("p", "chat__meta", "출처 · " + message.source));
  if (message.limitation) answer.appendChild(el("p", "chat__meta", "한계 · " + message.limitation));
  if (!message.streaming && !message.error) {
    var contact = el("button", "button chat__contact", "💬 문의하기");
    contact.type = "button";
    contact.addEventListener("click", function () {
      notice("문의 주소는 병원 설정에서 정합니다 — 서버가 붙으면 열립니다.");
    });
    answer.appendChild(contact);
  }
  return answer;
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
  input.disabled = state.chat.busy;
  var submit = el("button", "chat__send", state.chat.busy ? "답변 중…" : "전송");
  submit.type = "submit";
  submit.disabled = state.chat.busy;
  form.appendChild(input);
  form.appendChild(submit);
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var question = input.value.trim();
    if (question) sendChatQuestion(question);
  });
  wrap.appendChild(form);
  wrap.appendChild(el("p", "chat__feedback", "이 안내가 도움이 되었나요?　👍　👎　오류 신고"));
  return wrap;
}

function sendChatQuestion(question) {
  if (state.chat.busy) return;
  state.chat.busy = true;
  state.chat.messages.push({ role: "user", text: question });
  var answer = { role: "assistant", text: "", streaming: true };
  state.chat.messages.push(answer);
  renderBody();

  streamChatbotAnswer(
    { link_token: state.token, question: question },
    {
      onDelta: function (chunk) {
        answer.text += chunk;
        renderBody();
      },
      onComplete: function (result) {
        answer.streaming = false;
        answer.urgent = !!result.urgent;
        answer.evidence = result.evidence;
        answer.source = result.source;
        answer.limitation = result.limitation;
      },
    },
  )
    .catch(function (err) {
      answer.streaming = false;
      answer.error = chatbotErrorMessage(err && err.code);
    })
    .finally(function () {
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
    });
    nav.appendChild(button);
  });
}

function renderBody() {
  var body = document.getElementById("guide-body");
  body.textContent = "";
  var g = state.guide;
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
