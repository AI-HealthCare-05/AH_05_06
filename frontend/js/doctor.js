/* D1 의사 검토·수정·승인·반려 — KEY-86
 *
 * 원장님이 이 화면에서 하는 일은 하나다. **환자에게 나갈 글을 읽고 승인한다.**
 *
 * 그래서 지키는 원칙 넷 —
 *   ① 고칠 것이 없으면 승인 한 번. ⚠ 만 보면 되고, 없으면 읽지 않고 승인해도 된다.
 *   ② 🚨 응급 문장은 고칠 수 없다. 식약처 정보를 근거로 미리 써 둔 문장이라
 *      약이 바뀌면 문장도 함께 바뀐다 — 사람이 손댈 자리가 아니다.
 *   ③ 되돌릴 때는 **사유를 받는다.** 그 문장이 스탭의 알림에 그대로 뜬다.
 *      「승인 반려」만 뜨면 받는 사람은 무엇을 고쳐야 하는지 알 수 없다.
 *   ④ 승인은 화면을 갈아끼우지 않는다 — 모달로 덮고 뒤는 그대로 남긴다.
 *      방금 무엇을 승인했는지가 눈앞에서 사라지면 확인할 방법이 없다.
 *
 * 권한은 **서버가 판단한다**(`docs/models-layout.md`). 여기서 버튼을 잠그는 것은
 * 편의일 뿐이고, 스탭 계정으로 요청이 가면 서버가 403 으로 막는다.
 */

/* ── 화면과 무관한 규칙 ─────────────────────────────────────────────────
 *
 * IIFE **밖**에 두는 것은 검사가 부를 수 있게 하려는 것이다 (KEY-158).
 * 그리는 함수는 옮기지 않는다 — 그건 브라우저가 할 일이다.
 *
 * `alreadyDone` 은 닫힌 값(`visit`)을 읽고 있어서 **인자를 받도록 바꿨다.**
 * 그래야 검사가 조합을 표처럼 채울 수 있다.
 *
 * 안내문을 그리는 규칙은 `js/guide-view.js` 로 옮겼다 — 환자 카드의 「안내문」·
 * 「최종 확인」 탭이 같은 것을 쓴다. 거기 있는 것도 전부 순수 함수다.
 */

/* 서버는 `2026-08-21T18:00:00+09:00` 처럼 **병원 시간대를 달아서** 준다
   (`GuideService._send_at` 이 `astimezone(Asia/Seoul)` 로 만든다).

   `new Date(iso)` 로 옮기면 **브라우저 시간대**로 다시 그려진다. KST 가 아닌
   자리에서 열면 18:00 이 09:00 으로 뜬다 — 서버에서 이미 잡았던 「18시가 새벽
   3시로 나가는」 버그가 표시 쪽에서 되살아나는 것이다. 예약 시각은 스탭이
   환자에게 「몇 시에 갑니다」라고 말하는 근거라 틀리면 그대로 전달된다.

   그래서 `detail.js` 의 `dayLabel`·`timeLabel` 처럼 **문자열을 그대로 자른다.**
   값에 이미 병원 시간대가 박혀 있어 옮길 이유가 없다.

   **수신번호(`to`)는 받지 않는다.** 이 화면은 「누구 것인가」만 알면 되고
   발송 번호는 서버가 안다. 응답에 실으면 승인할 때마다 환자 전화번호가
   화면과 로그를 지난다(KEY-111 에서 서버 쪽도 그렇게 정했다). */
function whenText(iso) {
  if (!iso) return "곧";
  var m = String(iso).match(/^\d{4}-(\d{2})-(\d{2})T(\d{2}:\d{2})/);
  if (!m) return String(iso);
  return Number(m[1]) + "월 " + Number(m[2]) + "일 " + m[3];
}

/* 이미 승인한 진료는 다시 승인하지 않는다.

   예전에는 승인 직후에만 버튼을 잠갔는데(`target.disabled = true`), 다른 줄에
   갔다 돌아오면 `renderRole()` 이 되살려서 **같은 진료를 두 번 승인할 수
   있었다.** 환자에게 문자가 나가는 자리라 두 번 승인은 두 번 발송이 된다.

   화면 상태가 아니라 **그 진료의 상태**를 본다 — 목록 줄이 곧 사실이다. */
function alreadyDone(visit) {
  return !!(visit && visit.work_category && visit.work_category !== "APPROVAL_REQUESTED");
}

/* 안내문을 못 불러왔을 때 **무엇 때문인지**를 원장님 말로 옮긴다 — KEY-126.
 *
 * 예전에는 무엇이 오든 「잠시 뒤 다시 시도해 주세요」였다. 그런데 `404
 * GUIDE_NOT_FOUND` 는 **기다린다고 생기지 않는다** — 아직 아무도 안 만든
 * 것이다. 그 화면에서 원장님은 없는 것을 기다리며 새로고침을 반복한다
 * (`#106` 이 남긴 제한사항).
 *
 * 의사 화면에는 안내문을 만드는 길이 없다(승인·되돌리기뿐). 그래서 「만드세요」
 * 라고 하지 않는다 — **없는 버튼을 가리키지 않는다.** 지금 무슨 상태인지만
 * 정확히 말한다.
 */
var GUIDE_LOAD_SAYINGS = [
  { status: 404, say: "아직 안내문이 없습니다. 판독 결과 확인이 끝나고 안내문이 만들어지면 여기에 보입니다." },
  { status: 403, say: "안내문을 볼 수 없습니다. 의사 계정으로 로그인했는지 확인해 주세요." },
];

function guideLoadSaying(error) {
  return errorMessage(error, GUIDE_LOAD_SAYINGS, "안내문을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
}

/* 링크 응답의 API 경로에서 토큰만 꺼내 환자 화면의 fragment 로 옮긴다.

   fragment 는 서버 요청과 access log 에 실리지 않는다. 병원 화면의 주소나
   DOM 에도 토큰을 쓰지 않고, 새 환자 탭의 메모리로만 넘긴다. 서버가 정한
   `path` 모양이 아니면 임의 주소를 열지 않는다. */
function patientGuideUrl(result) {
  var path = result && result.path;
  var matched = typeof path === "string" && path.match(/^\/api\/v1\/guides\/([A-Za-z0-9_-]+)$/);
  if (!matched) throw new Error("invalid patient guide link response");
  return "/guide.html" + (typeof MOCK !== "undefined" && MOCK ? "?mock=1" : "") + "#t=" + encodeURIComponent(matched[1]);
}

var PATIENT_LINK_SAYINGS = [
  { code: "GUIDE_NOT_APPROVED", say: "승인 완료된 안내에서만 개발용 환자 화면을 열 수 있어요." },
  {
    code: "LINK_ALREADY_ISSUED",
    say: "이미 개발용 링크가 발급됐어요. 보관해 둔 기존 환자 화면을 이용해 주세요. 이 화면에서는 토큰을 다시 보여주지 않아요.",
  },
  { code: "GUIDE_NOT_FOUND", say: "이 진료의 안내문을 찾지 못했어요." },
  { status: 403, say: "이 진료의 개발용 링크를 발급할 권한이 없어요." },
];

function patientLinkSaying(error) {
  return errorMessage(error, PATIENT_LINK_SAYINGS, "환자 화면을 열지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
}

(function () {
  /* **자기 칸이 없는 페이지에서는 아무것도 하지 않는다.**
     이 파일은 `doctor.html` 에만 실린다. 뿌리가 없으면 조용히 돌아간다 —
     위 순수 규칙은 그대로 남아서 다른 파일도, 검사도 부를 수 있다 (KEY-158). */
  if (!document.getElementById("approve")) return;

  var el = function (id) {
    return document.getElementById(id);
  };

  /* 눈에는 안 보이고 소리로만 읽히는 한 줄. 패널 전체를 라이브 리전으로 두는
     대신 **알릴 만한 일이 있을 때만** 여기에 적는다. */
  function sayPanel(text) {
    var box = el("panel-say");
    if (box) box.textContent = text;
  }

  var guide = null;
  var visit = null;
  var me = null;
  var section = "medication";
  var loadSeq = 0;
  var patientLinkOpening = false;

  function isDoctor() {
    return !!(me && (me.roles || []).indexOf("doctor") !== -1);
  }

  function canIssuePatientLink() {
    var roles = (me && me.roles) || [];
    return roles.indexOf("doctor") !== -1 || roles.indexOf("staff") !== -1;
  }


  /* 안내문을 그리는 규칙은 `js/guide-view.js` 가 갖는다 — 환자 카드의
     「안내문」·「최종 확인」 탭이 같은 것을 쓴다. 와이어프레임에서 D1 은 별도
     화면이 아니라 그 탭 뒷칸이라, 두 곳이 같은 안내문을 그린다. 코드가 두
     벌이면 한쪽만 고쳐지고 화면마다 다른 말이 나온다. */

  /* 가로 탭은 한 판 안에 함께 그려진다(`guideScreenHtml`) — 이 칸은 비운다.
     와이어프레임 D1-1 이 S1-11 과 같은 화면이라 같은 것을 쓴다. */
  function renderTabs() {
    el("vtabs").innerHTML = "";
  }

  function currentSection() {
    return guideCurrentSection(guide.sections, section);
  }

  function renderPanel() {
    var now = currentSection();
    el("panel").innerHTML = now
      ? guideScreenHtml(guide.sections, now.key, "final", isDoctor(), guideEditingNow())
      : "";
  }

  function renderSummary() {
    var line = guideWarnLine(guide.sections);
    el("warn-line").className = line.className;
    el("warn-line").textContent = line.text;
  }

  /* 안내문이 없으면 **앞 환자의 이름을 지운다.** 안내문을 불러오는 동안 이름만
     남아 있으면, 화면은 앞 사람을 말하는데 `visit` 은 뒷사람이라 원장님이 읽는
     대상과 누를 대상이 어긋난다. 환자 식별이 걸린 자리라 비워 두는 편이 낫다. */
  function renderHead() {
    /* 단계 줄은 **스탭 화면과 같은 것**을 쓴다 (`js/step-nav.js`).
       전에는 이 화면만 정적 `<ol>` 이라 눌리지도 않았고, 그래서 의사가
       기본정보·진료기록·안내문으로 갈 길이 없었다. 의사가 서는 자리는
       「최종 확인」이지만 앞 단계를 되짚는 길은 열려 있어야 한다 —
       무엇을 보고 만든 글인지 확인하고 승인한다. */
    var steps = el("tabs");
    if (steps) {
      steps.innerHTML = stepsHtml("final", "/doctor.html", visit ? visit.visit_id : "");
    }

    if (guide === null) {
      el("p-name").textContent = "—";
      el("p-id").textContent = "";
      el("p-visit").textContent = "";
      return;
    }

    var p = guide.patient;
    el("p-name").textContent = p.name;
    /* 서버는 `FEMALE` 을 주고 화면이 「여」로 옮긴다. `age` 는 서버가 조회
       시점의 현지 날짜로 센 값이고, `birth_date` 는 동명이인을 가릴 근거로
       함께 온다(계약 §4). 화면에는 나이만 쓰지만 받는 것은 둘 다다. */
    el("p-id").textContent =
      (GENDER_LABEL[p.gender] || "—") + " " + p.age + "세 · 차트 " + p.hospital_patient_no;
    el("p-visit").textContent = guide.summary || "";
  }

  /* 단계 줄을 누르면 그 단계로 간다.
   *
   * 이 화면에는 그 탭들의 본문이 없다 — 「최종 확인」만 있다. 그래서 같은
   * 화면에서 바꾸지 않고 `patients.html` 의 그 탭으로 옮긴다.
   * 어디로 갈지는 `js/step-nav.js` 가 `data-href` 로 붙여 준다 —
   * 스탭 화면과 같은 규칙을 쓰기 위해서다.
   *
   * 지금 서 있는 단계에는 `data-href` 가 없다. **제자리로 오는 링크가 가장
   * 나쁘다** — 눌렀는데 아무 일도 안 일어나면 고장으로 읽힌다. */
  document.addEventListener("click", function (event) {
    var step = event.target.closest && event.target.closest(".tab[data-href]");
    if (!step) return;
    location.href = step.getAttribute("data-href");
  });

  /* ── 권한 ───────────────────────────────────────────── */


  /* `guide` 가 조건에 들어간 이유.

     `load()` 는 `visit` 을 **즉시** 새 환자로 바꾸는데 안내문은 응답이 와야
     온다. 그 사이 버튼이 살아 있으면 이렇게 된다.

         화면에 보이는 것   앞 환자의 안내문
         approve() 가 보내는 것   뒷 환자의 visit_id

     원장님은 **읽지 않은 안내문을 승인**하게 되고, 승인은 곧 환자에게 발송이다.
     그래서 「안내문이 화면에 있는가」를 최상위 조건으로 둔다 — 없으면 승인할
     대상도 없다. 실패했을 때도 `guide` 가 `null` 이라 그대로 잠긴다. */
  function renderRole() {
    var can = isDoctor() && !alreadyDone(visit) && guide !== null;
    el("approve").disabled = !can;
    el("return").disabled = !can;
    var approved = !!(guide && guide.status === "SCHEDULED_TO_SEND");
    el("patient-open").hidden = !approved;
    el("patient-open").disabled = !approved || !canIssuePatientLink();
    el("role-note").textContent = approved ? "스탭 또는 의사 권한이 있어야 열 수 있습니다" : "의사 권한이 있어야 승인합니다";
    el("role-note").hidden = approved ? canIssuePatientLink() : isDoctor();
  }

  /* 승인·되돌리기가 끝나면 왼쪽 줄도 그 사실을 말해야 한다. 목록이 「승인
     대기」인 채로 남으면 원장님은 안 나간 것으로 읽고 한 번 더 누른다. */
  /* 응답이 오는 사이에 의사가 다른 환자를 고를 수 있다. 그때 전역 `visit` 은
     이미 다른 사람이라, 그걸 고치면 **승인한 적 없는 환자가 발송 대기로
     바뀌고** 정작 승인한 환자는 목록에 남아 다시 승인된다.

     그래서 줄은 언제나 **요청을 보낼 때 잡아 둔 id** 로 찾는다. 전역은 그것이
     아직 같은 사람일 때만 손댄다. `load()` 가 `loadSeq` 로 하는 것과 같은 이유다. */
  function markDone(visitId, patch) {
    if (typeof updateRow === "function") updateRow(visitId, patch);
    if (visit && visit.visit_id === visitId) Object.assign(visit, patch);
    if (typeof renderChipCounts === "function") renderChipCounts();
    renderRole();
  }


  /* ── 모달 ───────────────────────────────────────────── */

  function openModal(html) {
    el("modal-body").innerHTML = html;
    el("modal").hidden = false;
  }

  function closeModal() {
    el("modal").hidden = true;
  }

  /* 권한 문제와 그 밖을 가른다.

     예전에는 `catch` 가 모든 오류를 받아 늘 「의사 계정으로 로그인했는지
     확인해 주세요」라고 했다. 서버가 500 을 줘도 그렇게 말하니, 원장님은 멀쩡한
     계정을 의심해 로그아웃했다 들어오고 그래도 안 되면 사람을 부른다 —
     **고칠 수 없는 것을 고치려 시간을 쓴다.** */
  function failedModal(title, error) {
    var lead =
      error && error.status === 403 ? "의사 계정으로 로그인했는지 확인해 주세요." : "잠시 뒤 다시 시도해 주세요.";
    return (
      '<h2 class="modal__title">' +
      esc(title) +
      "</h2>" +
      '<p class="modal__lead">' +
      lead +
      "</p>" +
      '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>'
    );
  }

  function approvedModal(result) {
    return (
      '<p class="modal__mark">✓</p>' +
      '<h2 class="modal__title">승인 완료</h2>' +
      '<p class="modal__lead">' +
      esc(whenText(result.scheduled_at)) +
      " 발송 예약</p>" +
      /* **없는 발송을 약속하지 않는다.**

         예전에는 「발송 예정」 + 「확인 문자와 소진 임박 안내는 자동
         발송됩니다」였다. 승인이 `scheduled_at` 을 채우는 것은 진짜지만
         **문자를 보내는 것은 아무것도 없다** — 발송기도 SMS 연동도 아직
         없다. 원장님이 그 문장을 읽고 「환자에게 갔다」고 믿으면, 안 간 것을
         갔다고 아는 상태가 된다.

         `KEY-148` §6 이 정한 대로 fallback 을 숨기지 않고 그 자리에 적는다.
         승인 자체의 뜻(= 발송 예약)은 그대로 두고 **무엇이 아직 없는지만**
         덧붙인다 (`KEY-160`). */
      '<p class="modal__note">[demo] 문자 발송은 아직 붙지 않았습니다 — 승인은 <b>발송 예약까지</b>입니다.<br />' +
      "확인 문자·소진 임박 안내의 실제 발송과 실패 알림은 S1-14 후속 계약입니다.</p>" +
      '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button>' +
      '<button class="button-primary" type="button" data-open-patient>개발용 환자 화면 열기</button></div>'
    );
  }

  function patientLinkFailedModal(error) {
    return (
      '<h2 class="modal__title">환자 화면을 열지 못했어요</h2>' +
      '<p class="modal__lead">' +
      esc(patientLinkSaying(error)) +
      "</p>" +
      '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>'
    );
  }

  /* 팝업 차단을 피하려고 클릭 순간 빈 탭을 만들고, 링크 발급이 성공한 뒤에만
     환자 화면으로 바꾼다. 실패하면 빈 탭을 닫고 병원 화면에는 안전한 사유만
     표시한다. 토큰은 console·DOM·저장소에 쓰지 않는다. */
  function openPatientGuide() {
    if (patientLinkOpening || !visit || !guide || guide.status !== "SCHEDULED_TO_SEND") return;
    patientLinkOpening = true;
    var openingId = visit.visit_id;
    var popup = window.open("about:blank", "_blank");
    /* 비동기 발급 뒤 다시 window.open()을 부르면 브라우저가 팝업으로 막는다.
       더 중요한 점은 `noopener`로 성공해도 반환값이 null일 수 있어 성공 여부를
       판정할 수 없다는 것이다. 클릭 순간 빈 탭을 못 만들었으면 링크를 발급하지
       않고 끝낸다 — 일회용 링크를 화면 없이 소진하지 않는다. */
    if (!popup) {
      patientLinkOpening = false;
      renderRole();
      openModal(patientLinkFailedModal(new Error("patient guide popup blocked")));
      return;
    }
    popup.opener = null;
    el("patient-open").disabled = true;

    doctorApi
      .issuePatientLink(openingId)
      .then(function (result) {
        var url = patientGuideUrl(result);
        popup.location.replace(url);
        patientLinkOpening = false;
        if (visit && visit.visit_id === openingId) renderRole();
        closeModal();
      })
      .catch(function (error) {
        patientLinkOpening = false;
        if (popup) popup.close();
        if (visit && visit.visit_id === openingId) renderRole();
        openModal(patientLinkFailedModal(error));
      });
  }

  function returnModal() {
    return (
      '<h2 class="modal__title">스탭에 되돌리기</h2>' +
      /* 사유가 스탭 알림에 그대로 뜬다는 것을 여기서 말한다.
         어디로 가는지 모르는 입력은 대충 적히고, 대충 적힌 사유는 왕복을 늘린다. */
      '<p class="modal__lead">고쳐야 할 것을 적어 주세요 — 이 문장이 스탭 알림에 그대로 뜹니다.</p>' +
      '<div class="reasons">' +
      RETURN_REASONS.map(function (r) {
        return '<button class="reason" type="button" data-reason="' + esc(r) + '">' + esc(r) + "</button>";
      }).join("") +
      "</div>" +
      '<textarea class="modal__input" id="reason-text" rows="3" placeholder="필요하면 덧붙여 주세요"></textarea>' +
      '<p class="modal__error" id="reason-error" hidden></p>' +
      '<div class="modal__acts"><button class="button-ghost" type="button" data-close>취소</button>' +
      '<span class="grow"></span><button class="button-primary" type="button" id="return-go">되돌리기</button></div>'
    );
  }

  /* ── 불러오기 ───────────────────────────────────────── */

  function load(next) {
    visit = next;
    var mine = ++loadSeq;

    /* 앞 환자의 것을 먼저 거둔다. `visit` 만 바뀌고 나머지가 남아 있는 순간이
       생기면 안 된다 — 그 틈이 곧 「읽은 것과 누른 것이 다른」 구간이다.

       창도 함께 닫는다. 반려 사유 창이 열린 채로 환자를 바꾸면, 앞 환자에게
       쓰던 사유가 뒷 환자의 이름 아래 남는다. 이름·버튼을 거두는 것과 같은
       이유다 — 화면이 말하는 사람과 눌렀을 때 가는 사람이 달라진다. */
    guide = null;
    /* 앞 환자에게 고친 문구가 남으면 남의 문자로 보낸 것이 된다 */
    smsForget();
    closeModal();
    renderHead();
    renderRole();

    el("panel").innerHTML = '<p class="block__hint">불러오는 중…</p>';
    el("warn-line").textContent = "";

    doctorApi
      .guide(visit.visit_id)
      .then(function (data) {
        if (mine !== loadSeq) return;
        guide = data;
        section = "medication";
        renderHead();
        renderTabs();
        renderPanel();
        renderSummary();
        renderRole();
        /* **환자가 바뀐 것만** 알린다. `renderPanel()` 은 탭을 누를 때도 불리므로
           패널 자체를 라이브 리전으로 두면 정상 탐색까지 읽힌다. */
        sayPanel((visit && visit.name ? visit.name + " · " : "") + "안내문을 불러왔습니다.");
      })
      .catch(function (error) {
        if (mine !== loadSeq) return;
        var saying = guideLoadSaying(error);
        el("panel").innerHTML = '<p class="block__hint">' + esc(saying) + "</p>";
        sayPanel(saying);
        renderRole(); // guide 가 null 이라 잠긴 채로 남는다
      });
  }

  /* ── 이벤트 ─────────────────────────────────────────── */

  document.addEventListener("click", function (event) {
    var target = event.target;

    var tab = target.closest("[data-section]");
    if (tab) {
      section = tab.getAttribute("data-section");
      renderTabs();
      renderPanel();
      return;
    }

    if (target.closest("[data-close]")) return closeModal();

    if (target.id === "patient-open" || target.closest("[data-open-patient]")) {
      openPatientGuide();
      return;
    }

    var reason = target.closest("[data-reason]");
    if (reason) {
      var box = el("reason-text");
      box.value = reason.getAttribute("data-reason");
      box.focus();
      return;
    }

    if (target.id === "approve" && guide) {
      target.disabled = true;
      var approvingId = visit.visit_id; // 지금 누른 그 환자. 전역은 곧 바뀔 수 있다
      doctorApi
        .approve(approvingId)
        .then(function (result) {
          /* 승인했으면 그 진료는 발송 대기다. 줄을 먼저 고치고 모달을 연다 —
             모달을 닫았을 때 목록이 이미 사실을 말하고 있어야 한다. */
          if (visit && visit.visit_id === approvingId) guide = result;
          markDone(approvingId, { work_category: "SEND_PENDING", detail_status: "SCHEDULED_TO_SEND" });
          openModal(approvedModal(result));
        })
        .catch(function (error) {
          /* target.disabled = false 로 그냥 되살리면 안 된다. 요청이 실패로
             돌아오는 사이 다른(이미 처리된) 진료로 넘어가 있을 수 있는데, 그 경우
             무조건 풀어 버리면 재승인 경합이 그대로 재현된다(위 markDone 과 같은
             이유). 항상 지금 화면의 상태를 다시 물어야 한다. */
          renderRole();
          openModal(failedModal("승인하지 못했습니다", error));
        });
      return;
    }

    if (target.id === "return" && guide) {
      openModal(returnModal());
      return;
    }

    if (target.id === "return-go") {
      var text = el("reason-text").value.trim();
      if (!text) {
        el("reason-error").textContent = "무엇을 고쳐야 하는지 적어 주세요.";
        el("reason-error").hidden = false;
        return;
      }
      target.disabled = true;
      var returningId = visit.visit_id; // 승인과 같은 이유로 지금 잡아 둔다
      doctorApi
        .returnToStaff(returningId, text)
        .then(function () {
          markDone(returningId, { work_category: "NEEDS_ATTENTION", detail_status: "APPROVAL_RETURNED" });
          openModal(
            '<h2 class="modal__title">스탭에 되돌렸습니다</h2>' +
              '<p class="modal__lead">「' +
              esc(text) +
              "」로 알렸습니다.</p>" +
              '<p class="modal__note">스탭이 고쳐 다시 승인 요청하면 목록에 돌아옵니다.</p>' +
              '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>',
          );
        })
        .catch(function () {
          /* 승인 쪽과 같은 이유다(이희진 님 `f184e4f`) — 응답이 실패로 돌아오는
             사이 다른 진료로 넘어가 있을 수 있다.

             다만 여기 `target` 은 **사유 창 안의 버튼**이라 `renderRole()` 이
             닿지 않는다. 그래서 「되돌리려던 그 진료가 아직 화면에 있을 때만」
             되살린다. 넘어갔으면 잠긴 채로 두고, `load()` 가 창을 닫는다. */
          if (visit && returningId === visit.visit_id) {
            target.disabled = false;
          }
          el("reason-error").textContent = "되돌리지 못했습니다. 잠시 뒤 다시 시도해 주세요.";
          el("reason-error").hidden = false;
        });
      return;
    }

  });

  /* 고치기는 `js/guide-view.js` 가 배선한다 — 스탭 화면과 같은 것을 쓴다.
     전에는 이 자리가 「항목 편집은 승인 API 가 붙은 뒤입니다」 안내창이었다.
     그 API 는 그 뒤에 붙었는데 안내창만 남아 있었다. */
  /* 문자 설정도 스탭 화면과 같은 배선을 쓴다. */
  wireSmsSettings({
    reRender: function () {
      renderPanel();
    },
    say: function (text) {
      var box = el("say");
      if (box) box.textContent = text;
    },
  });

  wireGuideEditing({
    visitId: function () {
      return visit ? visit.visit_id : null;
    },
    reRender: function (reload) {
      if (reload && visit) return load(visit);
      renderPanel();
    },
    say: function (text) {
      var box = el("say");
      if (box) box.textContent = text;
    },
  });

  document.addEventListener("session:ready", function (event) {
    me = event.detail;
    if (guide) return renderRole();
    /* 목록이 그려지면 맨 위 줄이 이미 골라져 있다(shell.js). 그런데 「고름」은
       클릭으로만 알려지므로, 처음 들어왔을 때는 오른쪽이 빈 채로 남는다 —
       원장님이 한 번 더 눌러야 한다. 골라져 있는 것을 그대로 연다. */
    var first = selectedVisit();
    if (first) load(first);
  });

  document.addEventListener("visit:selected", function (event) {
    load(event.detail);
  });

  /* 같은 사람인데 줄 값만 새로 왔다 — 머리만 고친다. `load()` 는 받아 둔
     안내문을 버리고 치던 문자 문구를 지운다(`smsForget`). */
  document.addEventListener("visit:refreshed", function (event) {
    if (!visit || !event.detail || visit.visit_id !== event.detail.visit_id) return;
    visit = event.detail;
    renderHead();
  });
})();
