const API = "/api/v1/patient";
const app = document.querySelector("#app");
const state = {
  token: new URLSearchParams(location.hash.slice(1)).get("access"),
  link: null,
  guidance: null,
  tab: "medication",
  adherence: null,
  pain: false,
  painTypes: new Set(),
};

const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>'"]/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character],
  );

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "잠시 뒤 다시 시도해 주세요." }));
    const error = new Error(body.detail);
    error.code = body.code;
    error.status = response.status;
    error.retry = Number(response.headers.get("Retry-After") || body.retry_after_seconds || 0);
    throw error;
  }
  return response;
}

function authCard(subtitle) {
  return `<section class="center" data-screen="P1-1">
    <div class="logo"></div>
    <div class="title"><h1>본인 확인이 필요해요</h1><p>${escapeHtml(subtitle)}</p></div>
    <div class="card">
      <div class="phone-number">${escapeHtml(state.link.masked_phone)}</div>
      <p class="muted text-center">이 번호로 인증번호를 보내드려요</p>
    </div>
    <button id="otp-request" class="button primary">인증번호 받기</button>
    <button id="changed" class="link-button">번호가 바뀌셨나요?</button>
  </section>`;
}

async function start() {
  if (!state.token) return renderClosed("유효하지 않은 링크입니다.");
  try {
    const response = await api("/auth/link", {
      method: "POST",
      body: JSON.stringify({ token: state.token }),
    });
    state.link = await response.json();
    const subtitle =
      state.link.purpose === "follow_up"
        ? "복약 7일째 확인 안내입니다"
        : `${state.link.encounter_date} 진료 안내입니다`;
    app.innerHTML = authCard(subtitle);
    document.querySelector("#otp-request").onclick = requestOtp;
    document.querySelector("#changed").onclick = () => renderClosed("휴대폰 번호로 다시 확인해 주세요.");
  } catch (error) {
    renderClosed(error.message);
  }
}

async function requestOtp() {
  try {
    const response = await api("/auth/otp", {
      method: "POST",
      body: JSON.stringify({ token: state.token }),
    });
    renderOtp(await response.json());
  } catch (error) {
    showError(error);
  }
}

function renderOtp(data) {
  app.innerHTML = `<section class="center" data-screen="P1-2">
    <div class="title"><h1>인증번호를 넣어주세요</h1><p>${escapeHtml(data.masked_phone)} 로 보냈어요</p></div>
    <div class="field"><input id="otp" class="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" aria-label="6자리 인증번호"></div>
    <p id="timer" class="muted text-center">3분 00초 남았어요</p>
    <button id="verify" class="button primary">확인</button>
    <button id="resend" class="link-button" disabled>다시 받기 (60초)</button>
    <div id="inline-error"></div>
  </section>`;

  let secondsLeft = 180;
  const timer = setInterval(() => {
    secondsLeft -= 1;
    const element = document.querySelector("#timer");
    if (!element) return clearInterval(timer);
    element.textContent = `${Math.floor(secondsLeft / 60)}분 ${String(secondsLeft % 60).padStart(2, "0")}초 남았어요`;
    if (secondsLeft <= 0) clearInterval(timer);
  }, 1000);

  let resendSeconds = 60;
  const cooldown = setInterval(() => {
    resendSeconds -= 1;
    const element = document.querySelector("#resend");
    if (!element) return clearInterval(cooldown);
    element.textContent = resendSeconds > 0 ? `다시 받기 (${resendSeconds}초)` : "인증번호 다시 받기";
    element.disabled = resendSeconds > 0;
    if (resendSeconds <= 0) clearInterval(cooldown);
  }, 1000);

  document.querySelector("#verify").onclick = async () => {
    try {
      await api("/auth/verify", {
        method: "POST",
        body: JSON.stringify({ challenge_id: data.challenge_id, code: document.querySelector("#otp").value }),
      });
      location.hash = "";
      await loadGuidance();
    } catch (error) {
      document.querySelector("#inline-error").innerHTML = `<div class="error">⚠ ${escapeHtml(error.message)}</div>`;
    }
  };
  document.querySelector("#resend").onclick = requestOtp;
}

function renderClosed(message) {
  app.innerHTML = `<section class="center" data-screen="P1-3">
    <div class="error"><strong>⚠ 링크가 닫혔어요</strong><br>${escapeHtml(message)}</div>
    <div class="field"><label>휴대폰 번호</label><input id="phone" inputmode="tel" placeholder="010-1234-5678"></div>
    <div class="field"><label>생년월일</label><input id="birth" inputmode="numeric" maxlength="6" placeholder="900101"></div>
    <button id="reissue" class="button primary">확인</button>
    <p class="muted">ⓘ 누르면 이 번호로 안내문 링크를 다시 보내드립니다 · 하루 3번까지</p>
    <div id="inline-error"></div>
  </section>`;
  document.querySelector("#reissue").onclick = async () => {
    try {
      await api("/auth/reissue", {
        method: "POST",
        body: JSON.stringify({
          token: state.token || "invalid-token-value-long-enough",
          phone_number: document.querySelector("#phone").value,
          birth_date: document.querySelector("#birth").value,
        }),
      });
      app.innerHTML = `<section class="center success"><div class="check">✓</div><h2>안내문 문자를 다시 보내드렸어요</h2><p class="muted">새 문자에 있는 링크로 들어와 주세요.</p></section>`;
    } catch (error) {
      document.querySelector("#inline-error").innerHTML = `<div class="error">⚠ ${escapeHtml(error.message)}</div>`;
    }
  };
}

function showError(error) {
  if (error.code === "otp_locked") {
    app.innerHTML = `<section class="center" data-screen="P1-4"><div class="title"><h1>인증을 잠시 멈췄어요</h1><p>${escapeHtml(error.message)}</p></div></section>`;
  } else {
    window.alert(error.message);
  }
}

async function loadGuidance() {
  try {
    const response = await api("/guidance");
    state.guidance = await response.json();
    if (state.link?.purpose === "follow_up") return renderFollowUpRoute();
    renderShell();
  } catch (error) {
    if (error.status === 401) {
      app.innerHTML = `<section class="center" data-screen="P1-5"><div class="title"><h1>다시 본인 확인이 필요해요</h1><p>${escapeHtml(error.message)}</p></div></section>`;
    } else {
      showError(error);
    }
  }
}

function shell(content) {
  const guidance = state.guidance;
  const tabs = [
    ["medication", "복약지도"],
    ["cautions", "주의사항"],
    ["lifestyle", "생활관리"],
    ["status", "현황"],
    ["chat", "챗봇"],
  ];
  return `<header class="topbar"><div><strong>진료 안내</strong><small>${guidance.encounter_date} · ${escapeHtml(guidance.clinic_name)}</small></div></header>
    <nav class="tabs">${tabs.map(([id, label]) => `<button class="tab ${state.tab === id ? "active" : ""}" data-tab="${id}">${label}</button>`).join("")}</nav>
    ${content}`;
}

function renderShell() {
  const guidance = state.guidance;
  if (state.tab === "chat") return renderChat();
  if (state.tab === "status") return renderMedicationStatus();
  const items =
    state.tab === "medication"
      ? guidance.medication_guidance
      : state.tab === "cautions"
        ? guidance.cautions
        : guidance.lifestyle_guidance;
  const medications =
    state.tab === "medication"
      ? guidance.medications
          .map(
            (medication) => `<article class="med"><h3>${escapeHtml(medication.name)}</h3><p>${escapeHtml(medication.dosage)} · ${escapeHtml(medication.purpose)}</p></article>`,
          )
          .join("")
      : "";
  const screen = state.tab === "medication" ? "P2" : state.tab === "cautions" ? "P3" : "P4";
  const title = state.tab === "medication" ? "처방받은 약" : state.tab === "cautions" ? "주의사항" : "생활관리";
  app.innerHTML = shell(`<section class="content" data-screen="${screen}">
    <h2 class="section-title">${title}</h2>${medications}
    ${items.map((item) => `<article class="section card"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.body)}</p><small class="muted">출처 · ${escapeHtml(item.source_label)}</small></article>`).join("")}
  </section>`);
  bindTabs();
}

function bindTabs() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.onclick = () => {
      state.tab = button.dataset.tab;
      renderShell();
    };
  });
}

async function renderMedicationStatus() {
  try {
    const response = await api("/medication-status");
    const status = await response.json();
    app.innerHTML = shell(`<section class="content" data-screen="P5-1">
      <p class="muted">${status.prescription_date} 처방 · ${escapeHtml(status.clinic_name)}</p>
      ${status.medications
        .map(
          (medication) => `<article class="med">
            <h3>${escapeHtml(medication.name)} ${escapeHtml(medication.strength || "")}</h3>
            <p>${medication.total_days}일분 · ${medication.elapsed_days}일째 · ${medication.remaining_days}일 남음</p>
            <progress max="100" value="${medication.progress_percent}">${medication.progress_percent}%</progress>
            <small class="muted">소진 예정일 · ${medication.depletion_date}</small>
          </article>`,
        )
        .join("")}
    </section>`);
    bindTabs();
  } catch (error) {
    showError(error);
  }
}

async function renderFollowUpRoute() {
  try {
    const response = await api("/follow-up");
    const status = await response.json();
    if (!status.due) {
      app.innerHTML = `<section class="center"><div class="card"><strong>다음 확인</strong><p>${escapeHtml(status.due_date)}에 문자로 여쭤볼게요.</p></div></section>`;
    } else if (status.submitted) {
      renderFollowUpComplete();
    } else {
      renderFollowUp();
    }
  } catch (error) {
    showError(error);
  }
}

const followUpOptions = [
  ["taking", "잘 먹고 있어요", null],
  ["uncomfortable", "먹고 있는데 불편해요", "P7-2"],
  ["sometimes_missed", "가끔 놓쳐요", "P7-3"],
  ["stopped_side_effects", "불편해서 중단했어요", "P7-4"],
  ["stopped_better", "증상이 좋아져서 그만뒀어요", "P7-5"],
];

function followUpNotice(adherence) {
  if (adherence === "uncomfortable") {
    return `<div class="followup-notice"><p>복용 초기 몇 달간 피가 조금씩 비칠 수 있어요. 흔한 반응입니다.<br>대개 3개월 안에 줄어드니 그대로 드셔도 괜찮아요.<br>불편하신 점은 원장님께 전해드릴게요 — 다음 진료 때 함께 봐요.</p><hr><strong>🚨 이런 증상이면 바로 병원에 오세요</strong><p>한쪽 다리가 붓고 아플 때 · 갑자기 숨이 찰 때 · 가슴이 아플 때</p><button class="button">💬 문의하기</button></div>`;
  }
  if (adherence === "sometimes_missed") {
    return `<div class="followup-notice"><p>괜찮아요. 가끔 놓치는 분이 많아요.<br>복용을 잊으셨다면 생각난 즉시 드시고, 다음 약은 원래 시간에 드세요.</p><strong>잊지 않는 데 도움이 되는 것</strong><p>· 매일 같은 시간에 알람을 맞춰 두세요<br>· 칫솔처럼 매일 보는 자리에 약을 두세요</p><p class="muted">ⓘ 이 답은 기록으로만 남습니다 — 따로 연락드리지 않아요</p></div>`;
  }
  if (adherence === "stopped_side_effects") {
    return `<div class="followup-notice"><p>복용 초기 몇 달간 생리가 불규칙하거나 출혈이 있을 수 있어요. 흔한 반응입니다.<br>임의로 중단하시면 치료가 어려워질 수 있어요. 병원에 문의해 주세요.</p><button class="button">💬 문의하기</button></div>`;
  }
  if (adherence === "stopped_better") {
    return `<div class="followup-notice"><p>좋아진 것은 약이 잘 듣고 있다는 뜻이에요.<br>통증이 사라졌다고 병변까지 없어진 것은 아니라서, 지금 끊으면 다시 자랄 수 있어요.<br>끊을 시기는 진료 때 함께 정해요. 병원에 문의해 주세요.</p><button class="button">💬 문의하기</button></div>`;
  }
  return "";
}

function renderFollowUp() {
  app.innerHTML = `<section class="content" data-screen="P7-1">
    <div><h1>약은 잘 드시고<br>계신가요?</h1></div>
    ${followUpOptions
      .map(
        ([id, label]) => `<div class="followup-choice"><button class="followup-option" data-adherence="${id}">${label}</button><div data-notice="${id}"></div></div>`,
      )
      .join("")}
    <hr><strong>통증이 있었나요?</strong>
    <div class="row"><button class="pain-chip" data-pain="true">있었어요</button><button class="pain-chip" data-pain="false">없었어요</button></div>
    <div id="pain-detail" hidden>
      <label>정도 <output id="pain-output">0 / 10</output></label>
      <input id="pain-score" type="range" min="0" max="10" value="0">
      <div class="row">${[
        ["dysmenorrhea", "월경통"],
        ["dyspareunia", "성교통"],
        ["dyschezia", "배변통"],
        ["chronic_pelvic", "만성골반통"],
      ]
        .map(([id, label]) => `<button class="pain-chip" data-pain-type="${id}">${label}</button>`)
        .join("")}</div>
    </div>
    <div class="field"><textarea id="memo" placeholder="메모 (선택)"></textarea></div>
    <button id="save-followup" class="button primary">저장</button>
    <p class="muted">ⓘ 담당 의료진이 요청한 기록이에요</p><div id="inline-error"></div>
  </section>`;

  document.querySelectorAll("[data-adherence]").forEach((element) => {
    element.onclick = async () => {
      state.adherence = element.dataset.adherence;
      document.querySelectorAll("[data-adherence]").forEach((item) => item.classList.toggle("selected", item === element));
      document.querySelectorAll("[data-notice]").forEach((item) => {
        item.innerHTML = item.dataset.notice === state.adherence ? followUpNotice(state.adherence) : "";
      });
      const screen = followUpOptions.find(([id]) => id === state.adherence)?.[2];
      document.querySelector("[data-screen]").dataset.screen = screen || "P7-1";
      if (["stopped_side_effects", "stopped_better"].includes(state.adherence)) {
        try {
          await api("/follow-up/adherence-selection", {
            method: "POST",
            body: JSON.stringify({ adherence: state.adherence }),
          });
        } catch (error) {
          document.querySelector("#inline-error").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
        }
      }
    };
  });
  document.querySelectorAll("[data-pain]").forEach((element) => {
    element.onclick = () => {
      state.pain = element.dataset.pain === "true";
      document.querySelectorAll("[data-pain]").forEach((item) => item.classList.toggle("selected", item === element));
      document.querySelector("#pain-detail").hidden = !state.pain;
    };
  });
  document.querySelector("#pain-score").oninput = (event) => {
    document.querySelector("#pain-output").value = `${event.target.value} / 10`;
  };
  document.querySelectorAll("[data-pain-type]").forEach((element) => {
    element.onclick = () => {
      if (state.painTypes.has(element.dataset.painType)) state.painTypes.delete(element.dataset.painType);
      else state.painTypes.add(element.dataset.painType);
      element.classList.toggle("selected");
    };
  });
  document.querySelector("#save-followup").onclick = submitFollowUp;
}

async function submitFollowUp() {
  if (!state.adherence) {
    document.querySelector("#inline-error").innerHTML = '<div class="error">복약 여부를 선택해 주세요.</div>';
    return;
  }
  try {
    await api("/follow-up", {
      method: "POST",
      body: JSON.stringify({
        adherence: state.adherence,
        has_pain: state.pain,
        pain_score: state.pain ? Number(document.querySelector("#pain-score").value) : null,
        pain_types: state.pain ? [...state.painTypes] : [],
        memo: document.querySelector("#memo").value || null,
      }),
    });
    renderFollowUpComplete();
  } catch (error) {
    document.querySelector("#inline-error").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
  }
}

function renderFollowUpComplete() {
  app.innerHTML = `<section class="center success" data-screen="P7-6"><div class="check">✓</div><h2>기록이 저장됐어요</h2><p class="muted">다 보시고 닫으셔도 됩니다.</p></section>`;
}

function renderChat() {
  app.innerHTML = shell(`<section class="chat" data-screen="P6-2">
    <div class="chat-note">받으신 진료 안내를 바탕으로 답변해 드려요. 진단이나 처방 변경은 안내할 수 없어요.
      <div class="chips">${["내 약이 뭐였죠?", "출혈이 계속돼요", "언제까지 먹나요?"]
        .map((question) => `<button class="chip" data-question="${question}">${question}</button>`)
        .join("")}</div>
    </div>
    <div id="messages" class="messages"></div>
    <form id="composer" class="composer"><input id="question" maxlength="500" placeholder="메시지를 입력하세요"><button class="button" type="submit">전송</button></form>
  </section>`);
  bindTabs();
  document.querySelectorAll("[data-question]").forEach((element) => {
    element.onclick = () => sendChat(element.dataset.question);
  });
  document.querySelector("#composer").onsubmit = (event) => {
    event.preventDefault();
    const input = document.querySelector("#question");
    if (input.value.trim()) sendChat(input.value.trim());
    input.value = "";
  };
}

async function sendChat(question) {
  const messages = document.querySelector("#messages");
  messages.insertAdjacentHTML(
    "beforeend",
    `<div class="bubble me">${escapeHtml(question)}</div><div class="bubble bot"><span class="answer"></span><div class="evidence"></div></div>`,
  );
  const bot = messages.lastElementChild;
  try {
    const response = await api("/chat/stream", { method: "POST", body: JSON.stringify({ question }) });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const block of events) {
        const type = block.match(/event: (.+)/)?.[1];
        const raw = block.match(/data: (.+)/)?.[1];
        if (!raw) continue;
        const data = JSON.parse(raw);
        if (type === "delta") bot.querySelector(".answer").textContent += data.text;
        if (type === "evidence") {
          bot.querySelector(".evidence").insertAdjacentHTML(
            "beforeend",
            `<div>📎 ${escapeHtml(data.title)} · ${escapeHtml(data.source_label)}</div>`,
          );
        }
        if (type === "limitation") bot.querySelector(".evidence").textContent = data.text;
      }
    }
  } catch (error) {
    bot.querySelector(".answer").textContent = error.message;
  }
  messages.scrollTop = messages.scrollHeight;
}

start();
