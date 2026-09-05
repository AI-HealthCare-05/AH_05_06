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

/* 상태 넷. 화면은 이 값으로만 갈린다 — 조건을 화면에서 다시 세지 않는다. */
var LINK_STATE = {
  NOT_YET: "NOT_YET", // 아직 없다 — 승인 전이거나 발급 전
  LIVE: "LIVE", // 살아 있다
  FRESH: "FRESH", // 방금 만들었다 — 주소가 이 화면에만 잠깐 있다
  EXPIRED: "EXPIRED", // 기한이 지났다
};

/* **지금 어느 상태인가.**
 *
 * `now` 를 받는다 — 화면이 `new Date()` 를 부르면 검사가 시계를 못 고정한다
 * (`sms-plan.js` 와 같은 이유).
 *
 * `fresh` 는 「이 창에서 방금 만들어 주소를 쥐고 있다」는 뜻이다. 새로고침하면
 * 사라진다 — 서버가 원문을 안 갖고 있으니 되찾을 길이 없다. */
function patientLinkState(link, guideStatus, now) {
  if (guideStatus !== LINK_READY_STATUS) return LINK_STATE.NOT_YET;
  if (!link || !link.expiresAt) return LINK_STATE.NOT_YET;
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
  if (state === LINK_STATE.NOT_YET) return "의사가 승인하면 자동으로 발급됩니다";
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
  if (state === LINK_STATE.EXPIRED) return "기한 지남";
  return state === LINK_STATE.FRESH ? "방금 만듦" : "사용 중";
}

/* 언제까지인가. **시각까지 적는다** — 168 시간짜리라 날짜만 적으면
   「오늘 만료」와 「오늘 아침에 이미 만료」가 안 갈린다. */
function patientLinkWhen(link, state) {
  if (state === LINK_STATE.NOT_YET) return "아직 발급되지 않았습니다";
  if (!link || !link.expiresAt) return "";
  var at = new Date(link.expiresAt);
  if (isNaN(at.getTime())) return "";
  var when =
    at.getMonth() + 1 + "월 " + at.getDate() + "일 " + String(at.getHours()).padStart(2, "0") + ":" +
    String(at.getMinutes()).padStart(2, "0");
  return state === LINK_STATE.EXPIRED ? when + " 에 닫혔습니다" : when + " 까지";
}

/* 단추. **주소를 DOM 에 안 싣는다** — `data-*` 에도 안 담는다. 누른 뒤에
   화면이 제 손에 쥔 값으로 복사·열기를 한다(#224 가 의사 화면에서 쓴 방식). */
function patientLinkActionHtml(action) {
  var saying = { copy: "복사", open: "열기", new: "새 링크 만들기" };
  var kind = action === "new" ? "button-primary" : "button-ghost";
  return (
    '<button class="' + kind + ' ' + kind + '--sm" type="button" data-patient-link="' +
    action +
    '">' +
    saying[action] +
    "</button>"
  );
}
