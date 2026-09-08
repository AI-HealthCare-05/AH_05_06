/* 환자 링크 블록의 규칙 — KEY-275.
 *
 * 문자 문구에 `{링크}` 자리표시자가 있는데 **그 링크가 어느 화면에도 안
 * 보였다.** 스탭이 환자와 통화하며 「링크 다시 보내드릴게요」를 하려면 살아
 * 있는지 · 언제까지인지 · 새로 만들 수 있는지를 봐야 한다.
 *
 * 블록은 두 화면에 선다 — 안내문의 「문자 설정」(S1-14) 문구 블록 아래,
 * 그리고 현황(D1-6)의 환자 액션 현황 아래. 와이어프레임이 현황 맨 아래에
 * 「[링크 무효화] [재발송]」 자리를 이미 잡아 두었다.
 *
 * **여기 있는 것은 전부 순수 함수다.** 데이터를 받아 문자열·상태를 돌려준다.
 * 화면 두 곳이 같은 답을 보려면 규칙이 한 군데 있어야 한다 — 두 벌이 되면
 * 한쪽만 고쳐지고, 그러면 같은 링크가 화면마다 다르게 보인다.
 *
 * ## 🚩 주소는 되읽을 수 없다
 *
 * 서버는 링크 **원문을 저장하지 않는다.** `PatientGuideLink` 는 해시
 * (`token_digest`)만 갖고, 원문은 발급·재발급 응답에 **한 번만** 실려 온다.
 *
 * 그래서 두 화면이 나눠 갖는 것은 **발급됐나 · 언제까지인가 · 살아 있나**
 * 셋이다. 주소는 「방금 만든」 그 화면에서만 잠깐 보인다.
 *
 * 늘 보이게 하려면 원문을 저장해야 하는데, 그러면 DB 가 새는 순간 살아 있는
 * 환자 링크가 통째로 넘어간다. AGENTS.md 「환자 링크 토큰을 코드·화면·로그·
 * 커밋에 남기지 않는다」에도 걸린다.
 */

/* 블록이 설 수 있는 자리 — 안내문이 승인돼 발송 예약까지 간 뒤다.
   그 앞에서는 링크 자체가 없다(`patient_links.py` 가 그 상태만 발급한다). */
var LINK_READY_STATUS = "SCHEDULED_TO_SEND";

/* 상태 여섯 — NOT_YET · NOT_ISSUED · LIVE · FRESH · EXPIRED · ORPHAN.
   화면은 이 값으로만 갈린다 — 조건을 화면에서 다시 세지 않는다.

   **이름을 함께 적는다.** 「넷」이라고만 적어 두었더니 `NOT_ISSUED` 를 더할 때
   따라 안 고쳐졌다(`#250` 리뷰 ⑧). 이름이 있으면 값이 늘 때 눈에 띄고 grep 에도
   걸린다. */
var LINK_STATE = {
  NOT_YET: "NOT_YET", // 승인 전 — 링크라는 것이 아직 없을 때다
  /* **승인은 됐는데 아직 안 만들었다.** 서버의 `approve()` 는 링크를 자동으로
     만들지 않는다(`guides.py` — 만드는 코드가 없다). 그래서 이 상태가 실제로
     지나가는 자리인데, 앞서는 승인 전과 한 덩어리라 화면이 「의사가 승인하면
     자동으로 발급됩니다」라고 **이미 승인된 건에 대고** 말했고 단추도 안 냈다.
     스탭이 첫 링크를 만들 길이 화면에서 사라져 있었다(인수조건 ③). */
  NOT_ISSUED: "NOT_ISSUED",
  LIVE: "LIVE", // 살아 있다
  FRESH: "FRESH", // 방금 만들었다 — 주소가 이 화면에만 잠깐 있다
  EXPIRED: "EXPIRED", // 기한이 지났다
  /* **승인이 철회됐는데 링크는 아직 살아 있다.** — `#250` 리뷰 ②
     `guides.py` 의 `unapprove()` 는 상태만 되돌리고 `PatientGuideLink` 를 안
     건드린다. 그런데 화면은 승인 상태만 보고 전부 `NOT_YET` 으로 접어서,
     **살아 있는 링크가 아무에게도 안 보였다** — 스탭이 그것을 폐기할 길도
     사라졌고, 나중에 재승인되면 회전된 적 없는 옛 토큰이 조용히 다시 산다.
     서버는 이미 열려 있다 — `revoke()` 가 `require_approved=False` 로 부른다. */
  ORPHAN: "ORPHAN",
};

/* **지금 어느 상태인가.**
 *
 * `now` 를 받는다 — 화면이 `new Date()` 를 부르면 검사가 시계를 못 고정한다
 * (`sms-plan.js` 와 같은 이유).
 *
 * `fresh` 는 「이 창에서 방금 만들어 주소를 쥐고 있다」는 뜻이다. 새로고침하면
 * 사라진다 — 서버가 원문을 안 갖고 있으니 되찾을 길이 없다. */
function patientLinkState(link, guideStatus, now) {
  if (guideStatus !== LINK_READY_STATUS) {
    /* 승인이 아니어도 **살아 있는 링크는 감추지 않는다.** 감추면 스탭이
       그것이 있다는 것도, 폐기할 길도 모른다 (`#250` 리뷰 ②). */
    var alive = link && link.expiresAt && !patientLinkExpired(link, now);
    return alive ? LINK_STATE.ORPHAN : LINK_STATE.NOT_YET;
  }
  if (!link || !link.expiresAt) return LINK_STATE.NOT_ISSUED;
  if (patientLinkExpired(link, now)) return LINK_STATE.EXPIRED;
  return link.fresh ? LINK_STATE.FRESH : LINK_STATE.LIVE;
}

/* 기한이 지났는가. **못 읽는 값은 지난 것으로 보지 않는다** — 서버가 준 값을
   못 읽었다고 「닫혔다」고 말하면, 멀쩡한 링크를 스탭이 새로 만들어 환자가
   쥔 것을 죽인다. 모르면 살아 있는 쪽으로 둔다. */
function patientLinkExpired(link, now) {
  if (!link || !link.expiresAt) return false;
  var until = new Date(link.expiresAt).getTime();
  if (isNaN(until)) return false;
  return until <= now.getTime();
}

/* 남은 날. 하루가 안 남으면 0 이다 — 「0일 남음」이 아니라 화면이 시각을 쓴다. */
function patientLinkDaysLeft(link, now) {
  if (!link || !link.expiresAt) return null;
  var until = new Date(link.expiresAt).getTime();
  if (isNaN(until)) return null;
  var left = until - now.getTime();
  return left <= 0 ? 0 : Math.floor(left / 86400000);
}

/* 상태마다 사람이 읽을 말. **각 상태가 다음에 무엇을 할지 말해야 한다** —
   「링크 없음」만 있으면 스탭은 자기가 뭘 잘못했는지 묻는다. */
function patientLinkStateNote(state, link, now) {
  if (state === LINK_STATE.NOT_YET) return "의사가 승인하면 발급할 수 있습니다";
  if (state === LINK_STATE.ORPHAN) {
    return "승인이 철회됐는데 이 링크는 아직 열립니다 — 폐기하거나, 다시 승인한 뒤 새 링크를 만들어 주세요";
  }
  if (state === LINK_STATE.NOT_ISSUED) return "승인됐습니다 — [새 링크] 를 누르면 환자에게 보낼 주소가 생깁니다";
  if (state === LINK_STATE.EXPIRED) {
    return "기한이 지났습니다 — 환자가 지금 열면 안내문이 안 보입니다";
  }
  var days = patientLinkDaysLeft(link, now);
  if (days === null) return "";
  return days > 0 ? days + "일 남음" : "오늘 안에 만료됩니다";
}

/* 이 상태에서 눌러도 되는 것. 화면이 단추를 세지 않게 여기서 답한다. */
function patientLinkActions(state) {
  if (state === LINK_STATE.NOT_YET) return [];
  /* 폐기만 낸다. 「새 링크」는 서버가 승인을 요구해 409 (`GUIDE_NOT_APPROVED`)
     로 막는다 — 눌러도 안 되는 단추를 두지 않는다. */
  if (state === LINK_STATE.ORPHAN) return ["revoke"];
  if (state === LINK_STATE.EXPIRED) return ["new"];
  return state === LINK_STATE.FRESH ? ["copy", "open", "new"] : ["new"];
}

/* **블록 자체도 한 벌이다.** 두 화면이 같은 HTML 을 그린다 — 모양이 갈리면
   같은 링크가 화면마다 다르게 보인다. 그리는 자리만 각자 정한다.

   `esc` 는 두 화면이 이미 싣는 `js/api.js` 것이다. `.grow` 는 쓰지 않는다 —
   그 클래스가 `doctor.css` 에만 있어서 스탭 화면에서는 안 밀린다. */
function patientLinkBlockHtml(link, guideStatus, now) {
  var state = patientLinkState(link, guideStatus, now);
  var acts = patientLinkActions(state);
  var fresh = state === LINK_STATE.FRESH;

  return (
    '<section class="box pl pl--' +
    state.toLowerCase() +
    '">' +
    '<div class="box__head pl__head">' +
    '<span class="box__title">환자 링크</span>' +
    (state === LINK_STATE.NOT_YET ? "" : '<span class="pl__tag">' + esc(patientLinkTag(state)) + "</span>") +
    "</div>" +
    '<div class="pl__body">' +
    '<p class="pl__when">' +
    esc(patientLinkWhen(link, state)) +
    "</p>" +
    '<p class="pl__sub">' +
    esc(patientLinkStateNote(state, link, now)) +
    "</p>" +
    (fresh ? '<p class="pl__once">주소는 이 자리에서만 한 번 보입니다 — 새로고침하면 사라집니다</p>' : "") +
    (acts.length ? '<div class="pl__acts">' + acts.map(patientLinkActionHtml).join("") + "</div>" : "") +
    "</div></section>"
  );
}

/* 배지 — 상태를 한 낱말로. 「없음」은 배지를 안 단다(없는 것을 굳이 표시 안 한다). */
function patientLinkTag(state) {
  if (state === LINK_STATE.ORPHAN) return "승인 철회됨";
  if (state === LINK_STATE.NOT_ISSUED) return "발급 전";
  if (state === LINK_STATE.EXPIRED) return "기한 지남";
  return state === LINK_STATE.FRESH ? "방금 만듦" : "사용 중";
}

/* 언제까지인가. **시각까지 적는다** — 168 시간짜리라 날짜만 적으면
   「오늘 만료」와 「오늘 아침에 이미 만료」가 안 갈린다. */
function patientLinkWhen(link, state) {
  if (state === LINK_STATE.NOT_YET) return "아직 승인 전입니다";
  if (state === LINK_STATE.NOT_ISSUED) return "아직 발급되지 않았습니다";
  if (!link || !link.expiresAt) return "";
  /* 🚩 **보는 사람의 시계로 읽지 않는다** (이희진 님 `#250` 리뷰 ①).
   *
   * 여기는 `new Date(...).getMonth()/getDate()/getHours()` 였다. 그 넷은 전부
   * **브라우저 시간대**로 답한다 — 같은 만료 시각이 이렇게 갈렸다.
   *
   *     TZ=Asia/Seoul       9월 10일 18:00 까지
   *     TZ=UTC              9월 10일 09:00 까지
   *     TZ=America/New_York 9월 10일 05:00 까지
   *
   * 이 저장소가 이미 그 자리를 한 번 밟고 고쳤다 (`clinic-clock.js` —
   * 「KST 아닌 자리에서 열면 18시가 09시로 뜬다」). **그 해법을 그대로 쓴다** —
   * `Date` 를 안 만들고 ISO 문자열을 그대로 읽으므로 시계에 안 흔들린다.
   *
   * 판정(`patientLinkExpired`·`patientLinkDaysLeft`)은 `getTime()` 으로 하니
   * 원래 맞았다. 틀린 것은 **사람에게 보이는 글자**뿐이었다. */
  var when = clinicWhenText(link.expiresAt);
  if (!when) return "";
  return state === LINK_STATE.EXPIRED ? when + " 에 닫혔습니다" : when + " 까지";
}

/* 단추. **주소를 DOM 에 안 싣는다** — `data-*` 에도 안 담는다. 누른 뒤에
   화면이 제 손에 쥔 값으로 복사·열기를 한다(#224 가 의사 화면에서 쓴 방식). */
function patientLinkActionHtml(action) {
  var saying = { copy: "복사", open: "열기", new: "새 링크 만들기", revoke: "링크 폐기" };
  var kind = action === "new" || action === "revoke" ? "button-primary" : "button-ghost";
  return (
    '<button class="' + kind + ' ' + kind + '--sm" type="button" data-patient-link="' +
    action +
    '">' +
    saying[action] +
    "</button>"
  );
}

/* ── 화면이 쥔 링크 — 한 벌이다 ─────────────────────────────────────────
 *
 * 상태는 서버가 갖고 화면은 **다시 물어서** 쓴다. 두 화면이 저절로 맞는
 * 까닭이 그것이다 — 한쪽에서 새로 만들면 다른 쪽도 다음에 물을 때 새
 * 만료일을 읽는다.
 *
 * 서버가 못 주는 것이 딱 하나, **주소**다. 재발급 응답에 한 번 실려 오고 그
 * 뒤로는 세상 어디에도 없다(서버는 해시만 갖는다). 그래서 「방금 만들었다」는
 * 이 창의 기억이고, 새로고침하면 사라진다.
 *
 * ## 🚩 진료 번호를 함께 쥔다
 *
 * 환자를 옮겼는데 쥔 것이 남아 있으면 **앞 사람의 주소를 다음 사람 화면에서
 * 복사한다.** 이 저장소가 가장 두려워하는 부류의 사고다. 그래서 꺼낼 때마다
 * 번호를 대조하고, 안 맞으면 없는 것으로 답한다 — 「지우는 것을 잊었나」를
 * 걱정하지 않아도 되게.
 */
var patientLinkHeldOne = null;

/** 쥔다. `link` 가 없으면 놓는다. */
function patientLinkKeep(visitId, link) {
  patientLinkHeldOne = link ? { visitId: visitId, expiresAt: link.expiresAt, fresh: !!link.fresh, url: link.url || "" } : null;
}

/** 이 진료의 것만 돌려준다. **번호가 다르면 없는 것이다.** */
function patientLinkOf(visitId) {
  if (!patientLinkHeldOne) return null;
  if (String(patientLinkHeldOne.visitId) !== String(visitId)) return null;
  return patientLinkHeldOne;
}

function patientLinkForget() {
  patientLinkHeldOne = null;
}

/** 상태 응답 → 블록이 읽는 모양. **주소는 안 온다.** */
function patientLinkFromServer(answer) {
  if (!answer || !answer.issued) return null;
  return { expiresAt: answer.expires_at || null, fresh: false, url: "" };
}

/** 쥐고 있는 것과 서버가 준 것이 **같은 세대의 링크인가.**
 *
 * 재발급은 새 토큰과 새 만료 시각을 함께 만든다. 그래서 만료 시각이 달라졌다면
 * 그 사이에 **다른 창이나 다른 직원이 링크를 돌린 것**이고, 이 창이 쥔 주소는
 * 이미 폐기된 것이다.
 *
 * 글자가 아니라 **시각으로** 견준다 — 서버가 같은 순간을 다른 모양
 * (`+09:00` · `Z`)으로 적어 보내도 같은 세대다.
 *
 * 못 읽는 값은 **다른 세대로 친다.** 「모르겠으니 그냥 쥔 것을 쓰자」로 기울면
 * 폐기된 주소가 살아남고, 그 값이 환자에게 그대로 간다. */
function patientLinkSameGeneration(held, fromServer) {
  var a = Date.parse(String(held == null ? "" : held));
  var b = Date.parse(String(fromServer == null ? "" : fromServer));
  if (isNaN(a) || isNaN(b)) return false;
  return a === b;
}

/* 상태를 다시 읽어 쥔다.
 *
 * **방금 만든 주소는 지킨다** — 다시 읽었다고 그 주소를 버리면, 스탭이 새
 * 링크를 만든 직후 화면이 한 번 갱신되는 것만으로 [복사] 가 사라진다.
 * 만료 시각은 서버 것을 쓴다(그쪽이 정본이다).
 *
 * 🚩 **단, 같은 세대일 때만이다** (유가은 님 `#250`).
 *
 * 여태는 만료 시각이 달라져도 쥔 `fresh` · `url` 을 그대로 새 상태에 옮겼다.
 * 그래서 다른 창(또는 다른 직원)이 같은 진료의 링크를 다시 발급한 뒤 이 화면이
 * 상태를 한 번 더 읽으면, **만료 시각은 새 링크의 것인데 주소는 폐기된 옛
 * 것**인 상태가 만들어졌다. 스탭이 그걸 복사하면 환자는 열리지 않는 링크를
 * 받는다 — 화면에는 아무 이상이 없어 보인다.
 *
 * 세대가 달라졌으면 주소를 놓는다. [복사] 가 사라지는 편이, 안 열리는 주소를
 * 쥐고 있는 것보다 낫다.
 *
 * 서버가 `issued: false` 라고 하면 정말 없는 것이라 쥔 것도 놓는다. */
function patientLinkAdopt(visitId, answer) {
  var held = patientLinkOf(visitId);
  var next = patientLinkFromServer(answer);
  if (next && held && held.fresh && patientLinkSameGeneration(held.expiresAt, next.expiresAt)) {
    next.fresh = true;
    next.url = held.url;
  }
  patientLinkKeep(visitId, next);
  return next;
}

/** 재발급 응답 → 방금 만든 것. 주소는 **이 창의 기억에만** 둔다. */
function patientLinkFromIssue(answer) {
  return { expiresAt: (answer && answer.expires_at) || null, fresh: true, url: patientGuideUrl(answer) };
}

/** 링크 상태를 읽어 쥔다 — 두 화면이 같은 길로.
 *
 * 🚩 이 배선이 `doctor.js` 와 `visit-guide.js` 에 **거의 그대로 두 번** 있었다
 * (`#250` 리뷰 ⑤). 이 파일이 정확히 그 중복을 막으려고 있는데 로드만 빠져
 * 있었다. 두 벌이면 한쪽만 고쳐지고, 그러면 같은 링크가 화면마다 다르게 보인다.
 *
 * 🚩 그리고 두 `.catch` 가 **아무것도 안 받고 통째로 삼켰다** (리뷰 ④).
 * 서버는 「없다」(200 · `issued:false`)와 「못 준다」(403 · 404 · 연결 실패)를
 * 갈라 놓았는데 화면이 둘을 같은 그림으로 뭉갰다 — 권한이 없어 못 읽은 것도
 * 「아직 발급 안 함」으로 보였다. 이제 **모르는 것은 모른다고 말한다.**
 *
 * `isStale` 은 화면이 준다. 화면마다 세대 번호(`loadSeq`)를 제 방식으로 세고
 * 있어서, 여기서 진료 번호로만 가르면 **같은 진료를 두 번 부른 경우**를 놓친다.
 */
/** 늦게 온 답이 **지금 화면의 것인가.**
 *
 * 이름을 붙여 밖에 낸다 — 안에 인라인으로 두면 검사가 못 닿고, 지워져도
 * 아무것도 안 운다(실제로 그렇게 빠져 있었다 — `#250` 리뷰 ③).
 * `doctor.js` 의 `isCurrentPatientLinkRequest` 와 같은 판정이다.
 */
function patientLinkStillCurrent(opts, visitId) {
  return String(opts && opts.visitId && opts.visitId()) === String(visitId);
}

function patientLinkLoad(opts, visitId, isStale) {
  var reRender = opts.reRender || function () {};
  var say = opts.say || function () {};
  var stale = function () {
    return !!(isStale && isStale());
  };
  return doctorApi
    .readPatientLink(visitId)
    .then(function (answer) {
      if (stale()) return;
      patientLinkAdopt(visitId, answer);
      reRender();
    })
    .catch(function (error) {
      if (stale()) return;
      say(patientLinkSaying(error));
    });
}

/* ── 배선 — 두 화면이 같은 것을 쓴다 ────────────────────────────────────
 *
 * `wireSmsSettings` 와 같은 모양이다. 두 벌이면 어느 화면에서 눌렀느냐에
 * 따라 되고 안 되고가 갈린다.
 *
 *   visitId()  지금 보고 있는 진료. 없으면 아무것도 안 한다
 *   reRender() 블록을 다시 그린다
 *   say(text)  무슨 일이 일어났는지 한 줄
 */
function wirePatientLink(opts) {
  var reRender = opts.reRender || function () {};
  var say = opts.say || function () {};

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var pressed = target.closest("[data-patient-link]");
    if (!pressed) return;

    var visitId = opts.visitId && opts.visitId();
    if (!visitId) return;
    var action = pressed.getAttribute("data-patient-link");

    if (action === "new") {
      /* **첫 발급과 교체는 다른 종점이다.** 없는 링크에 `re-issue` 를 부르면
         서버가 `LINK_NOT_ISSUED` 404 로 막는다 — 스탭에게는 「새 링크가 안
         만들어진다」로 보인다. 쥔 것이 있느냐로 가른다. */
      var making = patientLinkOf(visitId) ? doctorApi.reIssuePatientLink : doctorApi.issuePatientLink;
      /* **두 번 눌러 두 개가 생기지 않게 한다.** 재발급은 옛것을 폐기하므로
         두 번 누르면 첫 번째로 만든 주소가 이미 죽은 채 화면에 남는다. */
      if (pressed.disabled) return;
      pressed.disabled = true;
      say("새 링크를 만드는 중입니다…");
      making
        .call(doctorApi, visitId)
        .then(function (answer) {
          /* 🚩 **늦게 온 답은 지금 화면의 것이 아니다** (이희진 님 `#250` 리뷰 ③).
           *
           * 여기에 가드가 없었다. 쥔 자리(`patientLinkHeldOne`)가 지도가 아니라
           * **칸 하나**라서, 진료 A 의 답이 늦게 오면 `patientLinkKeep(A, …)` 이
           * B 가 방금 만든 링크를 **통째로 밀어낸다** — B 화면은 그 뒤로
           * 「주소는 만든 그 자리에서만 보입니다」만 말한다. 문구와 다시그리기도
           * B 화면에 A 의 것으로 뜬다.
           *
           * `doctor.js` 의 `isCurrentPatientLinkRequest` 와 같은 판정이다.
           * 여기서는 세대 번호 대신 **지금 고른 진료**를 다시 물어 본다 —
           * `opts.visitId()` 가 그 답을 준다.
           *
           * 늦은 답은 **아무것도 안 한다.** 그 주소는 이 자리에서만 보이는
           * 것이라 잃지만, 남의 것을 지우는 것보다 낫다 — 스탭은 A 로 돌아가
           * 새 링크를 만들면 된다. */
          if (!patientLinkStillCurrent(opts, visitId)) return;
          patientLinkKeep(visitId, patientLinkFromIssue(answer));
          say(
            making === doctorApi.issuePatientLink
              ? "환자 링크를 만들었습니다 — 주소는 이 자리에서만 보입니다"
              : "새 링크를 만들었습니다 — 옛 링크와 인증번호는 지금 막혔습니다",
          );
          reRender();
        })
        .catch(function (error) {
          /* 단추는 되살린다 — 화면이 바뀌었으면 이미 떨어져 나간 조각이라
             아무 일도 안 일어난다. **말은 지금 화면의 것만 한다** — A 의 실패를
             B 화면에 적으면 B 에서 뭔가 잘못된 것으로 읽힌다. */
          pressed.disabled = false;
          if (!patientLinkStillCurrent(opts, visitId)) return;
          say(patientLinkSaying(error));
        });
      return;
    }

    if (action === "revoke") {
      /* 승인이 철회됐는데 살아 있는 링크를 끊는다 (`#250` 리뷰 ②).
         서버가 `require_approved=False` 로 열어 둔 자리다 — 승인 상태와
         무관하게 digest 를 회전해 그 자리에서 죽인다. */
      if (pressed.disabled) return;
      pressed.disabled = true;
      say("링크를 폐기하는 중입니다…");
      doctorApi
        .revokePatientLink(visitId)
        .then(function () {
          if (!patientLinkStillCurrent(opts, visitId)) return;
          patientLinkForget();
          say("링크를 폐기했습니다 — 환자가 열면 이제 안 보입니다");
          reRender();
        })
        .catch(function (error) {
          pressed.disabled = false;
          if (!patientLinkStillCurrent(opts, visitId)) return;
          say(patientLinkSaying(error));
        });
      return;
    }

    var held = patientLinkOf(visitId);
    if (!held || !held.url) {
      /* 새로고침하면 주소가 사라진다 — 「눌러도 아무 일 없는 단추」로 두지
         않고 왜 없는지 말한다. */
      say("주소는 만든 그 자리에서만 보입니다 — 보내시려면 새 링크를 만들어 주세요");
      return;
    }

    if (action === "copy") {
      patientLinkCopy(held.url, say);
      return;
    }
    if (action === "open") {
      window.open(held.url, "_blank", "noopener");
      say("환자 화면을 새 탭에서 열었습니다");
    }
  });
}

/* 클립보드로만 보낸다 — **DOM 에 그리지 않는다.** 주소가 화면에 있으면
   화면 갈무리·화면낭독기·개발자도구 어디로든 샌다(#224 가 의사 화면에서 쓴
   방식과 같다).

   클립보드를 못 쓰는 환경이 있다(권한 거부·비보안 컨텍스트). 그때 조용히
   실패하면 스탭은 붙여넣기를 하고 나서야 안다. */
function patientLinkCopy(url, say) {
  var full = location.origin + url;
  var clip = navigator.clipboard;
  if (!clip || !clip.writeText) {
    say("이 브라우저에서는 자동 복사가 안 됩니다 — [열기] 로 연 뒤 주소창에서 복사해 주세요");
    return;
  }
  clip.writeText(full).then(
    function () {
      say("환자 링크를 복사했습니다");
    },
    function () {
      say("복사하지 못했습니다 — [열기] 로 연 뒤 주소창에서 복사해 주세요");
    },
  );
}
