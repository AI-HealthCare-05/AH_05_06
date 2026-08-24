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

(function () {
  var el = function (id) {
    return document.getElementById(id);
  };

  var guide = null;
  var visit = null;
  var me = null;
  var section = "medication";
  var loadSeq = 0;

  function isDoctor() {
    return !!(me && (me.roles || []).indexOf("doctor") !== -1);
  }

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }

  /* 서버는 `key` 와 `gender` 를 계약대로 주고, **한국어로 옮기는 것은 화면
     몫이다.** 서버가 한국어를 주면 화면마다 다른 말이 섞이고, 나중에 문구를
     바꿀 때 서버와 화면 두 곳을 고쳐야 한다. */
  var SECTION_LABEL = {
    medication: "복약지도",
    caution: "주의사항",
    emergency: "🚨 바로 병원에 연락하세요",
    life: "생활 안내",
    messages: "문자 설정",
  };

  /* **응급 문장은 탭을 갖지 않는다.** 서버가 주는 다섯 갈래 중 `emergency` 만
     탭에서 빼고, 「주의사항」 탭 본문 안에 이어 붙인다(와이어프레임 D1-2).

     따로 탭을 만들면 원장님이 그 탭을 안 열고 승인할 수 있다. 열지 않아도
     되는 문장이 아니다 — 일반 주의 문구를 읽으러 들어온 자리에서 함께 보인다.

     서버에서 나눈 까닭은 **잠금 단위**다. `locked` 는 섹션 단위라, 한 칸에
     두면 응급 문장을 지키려다 일반 문구까지 잠긴다 (KEY-161). */
  var TUCKED_UNDER = { emergency: "caution" };

  function tabSections() {
    return guide.sections.filter(function (s) {
      return !TUCKED_UNDER[s.key];
    });
  }

  /* 이 탭에서 함께 보여 줄 섹션들 — 차례는 서버가 준 그대로다. */
  function sectionsOf(key) {
    return guide.sections.filter(function (s) {
      return s.key === key || TUCKED_UNDER[s.key] === key;
    });
  }

  var GENDER_LABEL = { FEMALE: "여", MALE: "남", OTHER: "기타", UNKNOWN: "—" };

  /* **아직 받아 줄 서버가 없는 섹션.**

     `messages` 는 본문 자체는 서버가 주지만, 회차·문구를 **저장할 자리가
     없다**(구조화된 문자 설정은 `GuideResponse` 에 없고 `S1-14` 후속 계약이다).
     그래서 [수정] 을 열지 않는다 — 이 저장소가 「고칠 수 있어 보이는데 저장이
     안 되는 칸이 제일 나쁘다」로 정해 둔 자리다.

     `locked` 로 표현하지 않는다. `locked` 는 「식약처 기준 문장이라 사람이
     고칠 자리가 아니다」라는 뜻이고, 여기는 「아직 안 만들었다」라서 이유가
     다르다. 섞으면 나중에 문자 설정이 붙었을 때 무엇을 풀어야 하는지 알 수
     없다 (`KEY-160`). */
  var NOT_IMPLEMENTED = { messages: "회차·문구를 저장할 자리가 아직 없습니다 — S1-14 후속 계약입니다" };

  /* ── 안내문 ──────────────────────────────────────────── */

  function currentSection() {
    var tabs = tabSections();
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].key === section) return tabs[i];
    }
    return tabs[0];
  }

  function renderTabs() {
    var tabs = tabSections()
      .map(function (s) {
        return (
          '<button class="vtab' +
          (s.key === section ? " is-on" : "") +
          '" type="button" data-section="' +
          s.key +
          '">' +
          esc(SECTION_LABEL[s.key] || s.key) +
          (s.warn ? ' <span class="vtab__warn">⚠</span>' : "") +
          "</button>"
        );
      })
      .join("");
    /* 예전에는 「문자 설정」을 화면이 따로 붙였다. 서버의 `GuideSectionKey` 에
       `messages` 가 있으므로 그것도 섹션 하나다 — 화면이 목록을 만들지 않는다. */
    el("vtabs").innerHTML = tabs;
  }

  /* 서버는 섹션마다 **본문 한 덩이**(`body`)를 준다. 예전 목업은 제목·표·목록으로
     쪼갠 `blocks` 를 그렸는데, 그건 렌더 편의로 만든 모양이지 계약이 아니었다.

     8/27 여정에서 안내문은 고정 텍스트다(KEY-150 — 「확정 OCR→고정 안내→의사
     승인」). 채울 것이 없는 표 구조를 먼저 굳히지 않는다. 실제 생성이 붙을 때
     「어느 확정값이 어느 칸에 들어갔는가」와 함께 다시 정한다. */
  function sectionHtml(s) {
    var title = SECTION_LABEL[s.key] || s.key;

    /* 잠긴 섹션은 왜 잠겼는지를 함께 적는다. 이유 없이 안 눌리는 버튼은
       「고장났다」로 읽히고, 원장님은 그것을 확인하느라 시간을 쓴다. */
    var pending = NOT_IMPLEMENTED[s.key];
    var tail = s.locked
      ? '<p class="block__locked">🔒 식약처 기준 문장이라 고칠 수 없습니다 — 약이 바뀌면 문장도 바뀝니다</p>'
      : pending
        ? '<p class="block__locked">[demo] ' + esc(pending) + "</p>"
        : '<button class="block__edit" type="button" data-edit="' + esc(title) + '">수정</button>';

    return (
      '<section class="block' +
      (s.warn ? " block--warn" : "") +
      (s.locked ? " block--locked" : "") +
      '">' +
      '<h3 class="block__title">' +
      esc(title) +
      "</h3>" +
      (s.warn ? '<p class="block__warnline">⚠ ' + esc(s.warn) + "</p>" : "") +
      '<p class="block__body">' +
      esc(s.body) +
      "</p>" +
      (s.edited ? '<p class="block__hint">이 항목은 수정되었습니다</p>' : "") +
      tail +
      "</section>"
    );
  }

  /* 「문자 설정」도 서버가 주는 섹션 하나라, 다른 셋과 같은 길로 그린다.

     예전에는 이 탭만 체크박스·미리보기가 붙은 별도 화면이었는데 **그것을 받아
     주는 서버가 없었다.** 목업을 끄면 눌러도 저장되지 않는 칸이 되는데, 이
     저장소가 「고칠 수 있어 보이는데 저장이 안 되는 칸이 제일 나쁘다」로 정해
     둔 그것이다. 알림 일정 계약은 KEY-138 에서 정한 뒤 다시 붙인다. */
  function renderPanel() {
    el("panel").innerHTML = sectionsOf(currentSection().key).map(sectionHtml).join("");
  }

  function warnCount() {
    return guide.sections.filter(function (s) {
      return !!s.warn;
    }).length;
  }

  /* 위에 몇 개를 봐야 하는지 먼저 말한다. 없으면 「없다」고 분명히 말한다 —
     그래야 읽지 않고 승인해도 된다는 것이 전해진다. */
  function renderSummary() {
    var n = warnCount();
    el("warn-line").className = "warnline" + (n ? " warnline--warn" : " warnline--ok");
    el("warn-line").textContent = n
      ? "확인 부탁드리는 곳 " + n + "군데 — ⚠ 표시만 보시면 됩니다"
      : "확인 부탁드릴 곳이 없습니다 — 그대로 승인하셔도 됩니다";
  }

  /* 안내문이 없으면 **앞 환자의 이름을 지운다.** 안내문을 불러오는 동안 이름만
     남아 있으면, 화면은 앞 사람을 말하는데 `visit` 은 뒷사람이라 원장님이 읽는
     대상과 누를 대상이 어긋난다. 환자 식별이 걸린 자리라 비워 두는 편이 낫다. */
  function renderHead() {
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

  /* ── 권한 ───────────────────────────────────────────── */

  /* 이미 승인한 진료는 다시 승인하지 않는다.

     예전에는 승인 직후에만 버튼을 잠갔는데(`target.disabled = true`), 다른 줄에
     갔다 돌아오면 `renderRole()` 이 되살려서 **같은 진료를 두 번 승인할 수
     있었다.** 환자에게 문자가 나가는 자리라 두 번 승인은 두 번 발송이 된다.

     화면 상태가 아니라 **그 진료의 상태**를 본다 — 목록 줄이 곧 사실이다. */
  function alreadyDone() {
    return !!(visit && visit.work_category && visit.work_category !== "APPROVAL_REQUESTED");
  }

  /* `guide` 가 조건에 들어간 이유.

     `load()` 는 `visit` 을 **즉시** 새 환자로 바꾸는데 안내문은 응답이 와야
     온다. 그 사이 버튼이 살아 있으면 이렇게 된다.

         화면에 보이는 것   앞 환자의 안내문
         approve() 가 보내는 것   뒷 환자의 visit_id

     원장님은 **읽지 않은 안내문을 승인**하게 되고, 승인은 곧 환자에게 발송이다.
     그래서 「안내문이 화면에 있는가」를 최상위 조건으로 둔다 — 없으면 승인할
     대상도 없다. 실패했을 때도 `guide` 가 `null` 이라 그대로 잠긴다. */
  function renderRole() {
    var can = isDoctor() && !alreadyDone() && guide !== null;
    el("approve").disabled = !can;
    el("return").disabled = !can;
    el("role-note").hidden = isDoctor();
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
      '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>'
    );
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
      })
      .catch(function () {
        if (mine !== loadSeq) return;
        el("panel").innerHTML = '<p class="block__hint">안내문을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.</p>';
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

    /* 항목 수정은 서버가 붙은 뒤다(KEY-111) — 지금은 어디까지 됐는지 말한다. */
    var edit = target.closest("[data-edit]");
    if (edit) {
      openModal(
        '<h2 class="modal__title">' +
          esc(edit.getAttribute("data-edit")) +
          " 수정</h2>" +
          '<p class="modal__lead">항목 편집은 승인 API 가 붙은 뒤입니다 (KEY-111).</p>' +
          '<p class="modal__note">지금은 읽고 승인하거나 되돌리는 것까지 됩니다.</p>' +
          '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>',
      );
    }
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
})();
