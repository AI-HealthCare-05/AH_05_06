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
/* 최종 확인 단추의 상태와 이유를 한 번에 정한다 — KEY-353.
 *
 * 승인 가능 여부의 정본은 목록의 파생 카테고리가 아니라 안내문 자체의 상태다.
 * 한 진료에 보완 신호가 함께 있으면 목록 카테고리는 다른 우선순위를 택할 수
 * 있지만, 서버 승인 계약은 `APPROVAL_PENDING` 하나를 본다. 화면도 같은 사실을
 * 봐야 눌러야 할 단추를 잘못 잠그지 않는다.
 *
 * 이유도 권한·로딩·이미 처리됨을 가른다. 의사인데 안내문이 없거나 이미 승인된
 * 경우를 「의사 권한 없음」이라고 하면 사용자가 계정을 의심하게 된다. */
function doctorApprovalState(who, currentGuide) {
  var roles = (who && who.roles) || [];
  if (roles.indexOf("doctor") === -1) {
    return { canAct: false, why: "의사 권한이 있어야 승인합니다" };
  }
  if (!currentGuide) {
    return { canAct: false, why: "안내문을 불러온 뒤 승인할 수 있습니다" };
  }
  if (currentGuide.status !== "APPROVAL_PENDING") {
    return {
      canAct: false,
      why:
        currentGuide.status === "SCHEDULED_TO_SEND"
          ? "이미 승인되어 발송을 기다립니다"
          : "지금은 승인할 수 없는 안내문입니다",
    };
  }
  return { canAct: true, why: "" };
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
  NETWORK_SAYING, // 서버에 닿지도 못한 것 — KEY-211
  { status: 404, say: "아직 안내문이 없습니다. 판독 결과 확인이 끝나고 안내문이 만들어지면 여기에 보입니다." },
  { status: 403, say: "안내문을 볼 수 없습니다. 의사 계정으로 로그인했는지 확인해 주세요." },
];

function guideLoadSaying(error) {
  return errorMessage(error, GUIDE_LOAD_SAYINGS, "안내문을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
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
  /* 문자 설정 카드 아래 한 줄 — `visit-guide.js` 와 같은 이름·같은 이유다.
     저장 중·저장함·실패를 말한다. 눌렀는데 아무 말이 없으면 「됐나」가 된다. */
  var smsSaying = "";

  /* 서버가 준 문자 설정을 실제로 받았는지 — KEY-353 2차 리뷰(유가은 님).
   *
   * `guide` 가 오면 `canSave` 부터 켜졌는데, `doctorApi.messagePlan()` 은 별도
   * 요청이라 그보다 늦게(또는 실패로) 올 수 있다. 그 사이 「이 환자만 적용」을
   * 누르면 **아직 못 받은 서버 값**이 아니라 화면 기본값(월요일 10시)을 그
   * 환자의 설정으로 알고 통째로 덮어쓴다. 실제로 받아 온 뒤에만 저장을 연다. */
  var smsPlanState = "loading"; // loading | ready | failed

  /* 저장 요청이 도는 동안에도 잠근다 — 같은 리뷰에서 잡힌 두 번째 것.
   *
   * `wireSmsSettings` 가 누른 버튼을 `disabled` 로 바꿔도, `save` 콜백이 곧바로
   * `renderPanel()` 을 불러 패널을 통째로 새로 그리면 그 버튼 DOM 은 버려지고
   * `guideSmsPlan().canSave` 로만 다시 판정된 새 버튼이 선다. 이 값 없이는
   * `guide.status` 만 보고 다시 활성화돼 「저장하는 중…」과 눌리는 버튼이
   * 동시에 뜬다 — 두 번째 클릭이 첫 요청 위에 겹쳐 나간다. */
  var smsSaving = false;

  /* **다시 세운다.** `e6c214c`(KEY-234)가 안내문 그리는 규칙을 `guide-view.js`
     로 옮기면서 이 줄까지 함께 지웠는데, **쓰는 자리(`renderHead`)는 남았다.**

     그래서 `load()` 가 안내문을 받아 머리를 그리는 순간
     `ReferenceError: GENDER_LABEL is not defined` 로 죽고, `.catch` 가 그것을
     통신 오류로 오해해 **「안내문을 불러오지 못했습니다」**를 띄웠다. 서버는
     멀쩡히 답하고 있었다 — 의사 승인 화면이 안내문 있는 진료를 하나도 못 열었다.

     옮기지 않고 여기 둔다. 쓰는 곳이 이 파일 하나뿐이라 공용으로 낼 이유가
     없고, 공용으로 내면 「어느 화면이 싣나」를 또 따져야 한다. */
  var GENDER_LABEL = { FEMALE: "여", MALE: "남", OTHER: "기타", UNKNOWN: "—" };
  var section = "medication";
  var loadSeq = 0;
  function isDoctor() {
    return !!(me && (me.roles || []).indexOf("doctor") !== -1);
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

  /* 문자 설정 탭이 읽는 값 — KEY-275.
   *
   * **이 화면에는 없던 것이다.** `guide-view.js` 를 두 HTML 이 싣는데 이 함수는
   * `visit-guide.js`(스탭 화면)에만 있었다. 그래서 의사 화면의 문자 설정 탭은
   * 재료를 못 받았고, 링크 블록도 늘 「아직 없음」으로 섰다.
   *
   * 링크 상태와 함께 **지금 이 역할·안내 상태에서 저장할 수 있는지**도 준다.
   * 의사도 최종 확인에서 문자 설정을 고칠 수 있고, 승인 뒤에는 다시 잠긴다는
   * 서버 계약(`GuideService.save_message_plan`)과 같은 판정이다.
   */
  window.guideSmsPlan = function () {
    var roleEditable =
      isDoctor() &&
      !!guide &&
      ["STAFF_REVIEW", "APPROVAL_RETURNED", "APPROVAL_PENDING"].indexOf(guide.status) !== -1;
    /* 역할·상태가 열려 있어도 서버 값을 실제로 받아 오기 전이나 저장이 도는
       동안은 잠근다 — 위 `smsPlanState`·`smsSaving` 선언과 같은 이유다.
       판정 자체는 `guide-view.js` 의 `smsSaveLock` 이 갖는다 — visit-guide.js
       (스탭 화면)와 거의 같은 코드가 두 벌 있던 것을 iljun-sys 님 리뷰로
       한 벌로 뺐다. */
    var lock = smsSaveLock(
      roleEditable,
      smsPlanState,
      smsSaving,
      isDoctor()
        ? "승인된 뒤에는 고칠 수 없습니다 — 현황에서 승인을 거두고 고쳐 주세요"
        : "의사 권한이 있어야 문자 설정을 고칠 수 있습니다",
    );
    return {
      guideStatus: (guide && guide.status) || "",
      showPatientLink: false,
      canSave: lock.canSave,
      lockedSaying: lock.lockedSaying,
      saying: smsSaying,
    };
  };

  function renderPanel() {
    var now = currentSection();
    el("panel").innerHTML = now
      ? guideScreenHtml(guide.sections, now.key, "final", isDoctor(), guideEditingNow(), guide.summary, guide.preview)
      : "";
  }

  /* 머리말은 **진료에서** 채운다 — `js/step-nav.js` 의 `visitHeadLines` (KEY-300).
   *
   * 여기는 안내문(`guide.patient`)에서 뽑고, 없으면 통째로 비웠다. 그래서
   * 아직 안내문이 없는 진료를 고르면 **누구의 기록인지가 지워졌다.**
   *
   * 비운 까닭은 「불러오는 동안 앞 환자 이름이 남으면 읽는 대상과 누를 대상이
   * 어긋난다」였는데, 그 위험은 안내문에서 뽑을 때만 생긴다. `visit` 은
   * `load(next)` 가 동기적으로 갈아 끼우므로 언제나 지금 고른 환자다.
   *
   * 성별만 안내문에서 온다 — 진료 목록 계약(§6)에 없는 값이다. 있으면 붙이고
   * 없으면 뺀다. 그것 하나 때문에 이름과 차트번호를 비우지 않는다. */
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

    /* 서버는 `FEMALE` 을 주고 화면이 「여」로 옮긴다 — 안내문이 있을 때만 온다. */
    var head = visitHeadLines(visit, {
      gender: guide && guide.patient ? GENDER_LABEL[guide.patient.gender] : "",
      summary: guide ? guide.summary : "",
    });
    el("p-name").textContent = head.name;
    el("p-id").textContent = head.id;
    el("p-visit").textContent = head.line;
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

  /* ── 권한 ─────────────────────────────────────────────
   * `guide` 가 없는 로딩·실패 구간도 잠근다. 그 사이 `visit` 은 이미 새 환자인데
   * 화면에는 앞 환자의 안내문이 남을 수 있어, 살아 있으면 읽지 않은 안내문을
   * 다른 진료 번호로 승인하게 된다. */
  function renderRole() {
    var state = doctorApprovalState(me, guide);
    el("approve").disabled = !state.canAct;
    el("return").disabled = !state.canAct;
    el("role-note").textContent = state.why;
    el("role-note").hidden = !state.why;
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

  /* 「현황 보기」가 어디로 가는지는 그것을 그리는 `guide-view.js` 가 정한다
     (KEY-302). 이 화면이 할 일은 제 모달을 닫는 것뿐이다.

     이벤트 자체는 여전히 `cancelable: true` 로 뜬다(`guide-view.js`) — 이
     화면은 이제 막지 않지만, 스탭 화면(`visit-guide.js`)도 같은 이벤트를
     듣는다. 한쪽이 안 쓴다고 지우면 다른 쪽이 나중에 필요해질 때 다시
     발명해야 한다(KEY-307, 2heej·iljun-sys 리뷰). */
  document.addEventListener("guide:modal-close", function () {
    closeModal();
  });

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

  /* 최종 승인 결과만 표시한다. 실제 환자 링크는 문자 발송 직전에 생성된다. */
  function approvedModal(result) {
    return approvedModalHtml({
      scheduledAt: result && result.scheduled_at,
      name: (visit && visit.name) || "",
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
    /* 앞 환자에게 고친 문구가 남으면 남의 문자로 보낸 것이 된다 */
    guide = null;
    smsForget();
    /* 저장 안내·불러오기 상태도 환자마다 새로 잰다 — KEY-353 2차 리뷰(유가은
       님). 안 지우면 A 환자에서 「저장했습니다」를 본 뒤 B 로 넘어가도 B 가
       저장한 적 없는데 같은 문구가 남는다. */
    smsSaying = "";
    smsPlanState = "loading";
    smsSaving = false;
    closeModal();
    renderHead();
    renderRole();

    el("panel").innerHTML = '<p class="block__hint">불러오는 중…</p>';

    doctorApi
      .guide(visit.visit_id)
      .then(function (data) {
        if (mine !== loadSeq) return;
        guide = data;
        section = "medication";
        renderHead();
        renderTabs();
        renderPanel();
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

    /* 문자 설정은 **따로 불러온다** — `visit-guide.js` 와 같은 이유다. 안내문
       요청에 묶으면 한쪽이 실패할 때 둘 다 못 보고, 설정이 없어도 안내문은
       보여야 한다. KEY-353 1차 리뷰(유가은 님) 전에는 이 호출 자체가 없어서
       의사 화면은 늘 화면 기본값(월요일 10시)만 보여 주고 있었다.

       `guide` 가 아직 안 왔으면 `renderPanel()` 을 부르지 않는다 —
       `currentSection()` 이 `guide.sections` 를 읽어서, 안내문보다 이 응답이
       먼저 오면 그 자리에서 죽는다. 값은 `smsAdopt` 로 미리 받아 두고, 안내문
       쪽 `.then()` 이 곧 다시 그린다. */
    doctorApi
      .messagePlan(visit.visit_id)
      .then(function (data) {
        if (mine !== loadSeq) return;
        smsPlanState = "ready";
        smsAdopt(data);
        if (guide) renderPanel();
      })
      .catch(function () {
        /* 2차 리뷰(유가은 님) 전에는 여기서 조용히 화면 기본값으로 두고
           `canSave` 를 그대로 열어 뒀다 — 못 받아 온 서버 값을 기본값으로
           알고 「이 환자만 적용」이 그 기본값으로 덮어쓸 수 있었다. 이제는
           잠그고 이유를 말한다. */
        if (mine !== loadSeq) return;
        smsPlanState = "failed";
        if (guide) renderPanel();
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

    if (target.closest("[data-close]")) {
      return closeModal();
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
        .then(function (result) {
          /* 승인 쪽(`guide = result`)과 같은 이유다 — KEY-353 리뷰(유가은 님).
             `markDone` 은 목록 줄만 고치고 `renderRole()` 을 부르는데,
             전역 `guide.status` 를 그대로 두면 여전히 `APPROVAL_PENDING` 으로
             읽혀 되돌린 뒤에도 승인·반려 버튼이 풀린 채로 남는다. */
          if (visit && visit.visit_id === returningId) guide = result;
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
  /* 문자 설정도 스탭 화면과 같은 배선을 쓴다.
   *
   * `save` 가 빠져 있으면 카드는 저장 가능한 것처럼(`canSave`) 그려지는데
   * 「이 환자만 적용」을 눌러도 `wireSmsSettings` 가 `opts.save` 가 함수인지
   * 먼저 확인하고 아니면 조용히 돌아간다(`js/guide-view.js`) — 원장님은
   * 저장됐다고 믿고 넘어간다. KEY-353 리뷰(유가은 님)가 짚었다. */
  wireSmsSettings({
    reRender: function () {
      renderPanel();
    },
    say: function (text) {
      var box = el("say");
      if (box) box.textContent = text;
    },
    save: function (plan) {
      var wantedId = visit && visit.visit_id;
      if (!wantedId) return;
      /* **환자 번호만으로는 못 가른다** — KEY-353 3차 리뷰(유가은 님).
       *
       * A 에서 저장 → B 로 옮김 → A 로 돌아와 다시 저장, 이 순서에서 두
       * 요청은 `wantedId` 가 똑같이 A 다. 응답이 뒤집혀 오면(먼저 보낸 것이
       * 나중에 옴) `visit.visit_id === wantedId` 만 보는 판정은 **오래된
       * 응답도 지금 화면과 같은 환자라 통과시켜**, 방금 저장한 값을 그 전
       * 값으로 덮는다.
       *
       * `load()` 는 환자를 새로 열 때마다(같은 환자를 다시 열어도) `loadSeq`
       * 를 올린다 — 그래서 이 값을 저장 시점에 잡아 두면 「그 사이 이 환자를
       * 다시 열었는가」까지 가른다. `mine !== loadSeq`(불러오기)와 같은
       * 손잡이를 저장에도 그대로 쓴다. */
      var wantedSeq = loadSeq;
      /* `smsSaving` 이 `guideSmsPlan().canSave` 를 끄므로, 아래 `renderPanel()`
         이 새로 그리는 버튼도 눌린 채로 선다 — KEY-353 2차 리뷰(유가은 님).
         이게 없으면 `wireSmsSettings` 가 disabled 로 바꾼 버튼 DOM 이 이
         `renderPanel()` 로 버려지고, 새 버튼은 `guide.status` 만 보고 다시
         눌리게 열려 두 번째 클릭이 첫 요청 위에 겹쳐 나간다. */
      smsSaving = true;
      smsSaying = "저장하는 중…";
      renderPanel();

      doctorApi
        .saveMessagePlan(wantedId, plan)
        .then(function (data) {
          if (!visit || visit.visit_id !== wantedId || loadSeq !== wantedSeq) return;
          smsSaving = false;
          /* **서버가 돌려준 것을 화면 상태로 삼는다** — `visit-guide.js` 와
             같은 이유다. 보낸 것을 그대로 두면 서버가 고쳐 준 값이 안 보인다. */
          smsAdopt(data);
          smsSaying = "저장했습니다";
          renderPanel();
        })
        .catch(function (err) {
          if (!visit || visit.visit_id !== wantedId || loadSeq !== wantedSeq) return;
          smsSaving = false;
          smsSaying =
            err && err.code === "GUIDE_NOT_PENDING"
              ? "승인된 뒤에는 고칠 수 없습니다 — 현황에서 승인을 거두고 고쳐 주세요"
              : "저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요";
          renderPanel();
        });
    },
  });

  /* 링크 블록도 스탭 화면과 **같은 배선**을 쓴다 (KEY-275).
     안 걸면 블록의 단추가 눌러도 아무 일 없는 단추가 된다 — 이 화면에도
     블록이 서기 때문이다(`guide-view.js` 를 두 HTML 이 싣는다).

     `#224` 의 발급 모달과 겹치지 않는다. 모달은 **첫 발급**을 맡고, 블록은
     이미 있는 링크의 상태와 교체를 맡는다. 둘 다 서버를 다시 읽으므로 어느
     쪽으로 만들든 다음 그림에서 같은 값이 선다. */
  /* 로드와 배선이 **같은 옵션**을 쓴다 — 「지금 어느 진료인가」와 「어떻게 다시
     그리는가」가 두 곳에서 갈리면 늦게 온 답의 판정이 서로 달라진다. */
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

  function acceptSession(who) {
    me = who;
    if (guide) return renderRole();
    /* 목록이 그려지면 맨 위 줄이 이미 골라져 있다(shell.js). 그런데 「고름」은
       클릭으로만 알려지므로, 처음 들어왔을 때는 오른쪽이 빈 채로 남는다 —
       원장님이 한 번 더 눌러야 한다. 골라져 있는 것을 그대로 연다. */
    var first = selectedVisit();
    if (first) load(first);
  }

  document.addEventListener("session:ready", function (event) {
    acceptSession(event.detail);
  });

  /* `shell.js` 가 아주 빠른 `/auth/me` 응답을 이미 받았다면 이벤트는 지나갔다.
     저장된 현재 사용자를 즉시 받아 상단과 본문의 역할 판단이 갈리지 않게 한다. */
  if (session.current) acceptSession(session.current);

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
