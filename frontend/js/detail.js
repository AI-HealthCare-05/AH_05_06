/* 환자 카드 — S1-4 기본정보 · 수정 · 지난 방문 (KEY-50)
 *
 * 줄을 누르면 먼저 「이 사람이 누구인가」가 뜬다 — 번호가 맞는지, 지난번에
 * 무슨 약을 드셨는지가 여기서 확인된다. 지난 방문을 환자 카드 안에 두는 것은
 * 「전에 뭐라고 안내했지?」를 매번 관리 화면에서 찾지 않게 하려는 것이다.
 *
 * 수정은 계약이 정한 칸만 연다(KEY-26 §6).
 *   환자 — name · birth_date · gender · phone · sms_consent
 *   진료 — doctor_id · department_id · visited_at · status · planned_stop
 * 차트번호는 생성 후 변경 불가라 폼에 넣지 않는다. 「고칠 수 있어 보이는데
 * 저장이 안 되는 칸」이 제일 나쁘다.
 *
 * **목록 줄과 진료 상세는 다른 계약이다.** 오늘 목록(§6 S1-1)은 「무엇을 해야
 * 하는가」만 준다 — 이름 · 진단명 · 담당의 · 업무 상태. 진료과 스냅샷 ·
 * `status` · `planned_stop` 은 `GET /visits/{visit_id}` 에만 있다. 그래서 줄을
 * 누르면 그 리소스를 따로 불러온다. 줄 하나로 상세를 그리면 목업에서는 돌고
 * 서버가 붙는 날 빈칸이 된다.
 */

/* 「2026-08-19 (오늘)」 — 오늘인지가 붙어야 지난 진료를 보고 있다는 것을 안다 */
function dayLabel(isoDatetime) {
  if (!isoDatetime) return "";
  var day = isoDatetime.slice(0, 10);
  return day + (day === toIsoDate(new Date()) ? " (오늘)" : "");
}

/* **지난 방문에는 날짜만 쓴다.** 서버는 `2026-05-20T14:32:00+09:00` 을 주는데
   그대로 찍으면 한 칸이 서른 자가 되어 표가 밀린다. 지난 진료에서 궁금한 것은
   「언제 왔었나」이지 몇 시였는지가 아니다 — 시각이 필요한 자리는 오늘 진료
   쪽이고 거기는 따로 적는다 (와이어프레임 S1-4 의 지난 방문도 `2026-05-20` 다). */
function visitDay(isoDatetime) {
  var m = /^(\d{4}-\d{2}-\d{2})/.exec(String(isoDatetime || ""));
  return m ? m[1] : "";
}

function timeLabel(isoDatetime) {
  var m = String(isoDatetime || "").match(/T(\d{2}:\d{2})/);
  return m ? m[1] + " 등록" : "";
}

/* 이번 진료의 시간순 이력(S1-4). 서버가 문서·판독·안내문·D+7 사건을 하나로
   모아 준다 — 화면은 사건 이름을 사람이 읽을 문구로만 바꾼다.
   문자 발송 사건은 아직 이 목록에 없다(발송 이력 모델이 Sprint 5).

   위 `timeLabel` 처럼 IIFE 밖에 둔다 — 되돌림 표와 이름표는 순수 규칙이라
   다른 파일도, 검사도 부를 수 있다 (KEY-158). 서버가 `TimelineEvent` 를
   늘렸을 때 이름표가 빠지면 검사가 잡는다. */
var TIMELINE_EVENT_LABEL = {
  VISIT_CREATED: "진료 등록",
  DOCUMENT_UPLOADED: "진료기록 업로드",
  OCR_STARTED: "판독 시작",
  OCR_COMPLETED: "판독 완료",
  OCR_FAILED: "판독 실패",
  OCR_CONFIRMED: "판독 확정",
  GUIDE_GENERATED: "안내문 생성",
  GUIDE_EDITED: "안내문 수정",
  GUIDE_SUBMITTED: "스탭 확인 완료 · 승인 요청",
  GUIDE_APPROVED: "안내문 승인",
  GUIDE_UNAPPROVED: "안내문 승인 철회",
  GUIDE_RETURNED: "안내문 반려",
  GUIDE_REGENERATED: "안내문 다시 생성",
  CHECK_IN_SUBMITTED: "D+7 복약·통증 응답",
  GUIDE_VIEWED: "환자가 안내문 열람",
  CHATBOT_ANSWERED: "환자가 챗봇에 질문",
};
var TIMELINE_DOC_LABEL = { EMR: "EMR", PRESCRIPTION: "처방전", LAB_RESULT: "검사결과지" };
var TIMELINE_SECTION_LABEL = {
  medication: "복약",
  caution: "주의사항",
  emergency: "응급 문구",
  life: "생활관리",
  messages: "문자 설정",
};

/* 갈래마다 왼쪽 색 띠 하나. **화면이 아는 값만 수식어로 옮긴다** — 모르는
   값은 기본 띠로 두어, 서버가 category 를 늘려도 붙임표 없는 클래스나
   대응 규칙 없는 수식어가 새로 생기지 않게 한다. `detail.css` 와 짝. */
var TIMELINE_CATEGORY_MODIFIER = {
  VISIT: "visit",
  DOCUMENT: "document",
  OCR: "ocr",
  GUIDE: "guide",
  CHECK_IN: "check-in",
  PATIENT: "patient",
};

/* 이력 줄의 시각. **의원 시각을 글자에서 그대로 읽는다** — 서버가 이미
   `+09:00` 을 붙여 의원 시각으로 보내므로 `new Date()` 로 감싸 옮기면 보는
   사람의 시간대로 어긋난다(이 저장소가 정확히 이 부류로 크게 데었다). 규칙은
   `js/clinic-clock.js` 가 갖는다 — 직렬화가 `Z` 로 바뀌는 날 고칠 자리도
   거기 한 곳이고, 시간대를 바꿔 가며 재는 검사도 그쪽에 있다 (#182 리뷰 9). */
function timelineWhen(iso) {
  var day = clinicDay(iso);
  var time = clinicTime(iso);
  return day && time ? day + " " + time : String(iso || "");
}

/* 사건마다 붙는 한 조각 부연 — 어떤 문서였나, 어느 갈래를 고쳤나, 왜 반려됐나.
   반려 사유·실패 코드는 스탭이 다음에 할 일을 정하는 문장이라 그대로 보인다. */
function timelineDetail(entry) {
  if (entry.event === "DOCUMENT_UPLOADED") return TIMELINE_DOC_LABEL[entry.document_type] || entry.document_type || "";
  if (entry.event === "GUIDE_EDITED" || entry.event === "GUIDE_VIEWED")
    return TIMELINE_SECTION_LABEL[entry.section_key] || entry.section_key || "";
  return entry.note || "";
}

/* 공용 단계 모듈이 만든 결과를 실제 환자 화면의 탭 자리에 넣는 한 통로.
   화면 껍데기 없이도 이 연결 자체를 검사할 수 있게 순수하게 둔다. */
function renderVisitSteps(tabs, current, visitId) {
  tabs.innerHTML = stepsHtml(current, "/patients.html", visitId);
}

(function () {
  /* **자기 칸이 없는 페이지에서는 아무것도 하지 않는다.**
     이 파일은 `patients.html` 의 오른쪽 상세 칸에만 실린다. 뿌리가 없으면 조용히 돌아간다 —
     위 순수 규칙은 그대로 남아서 다른 파일도, 검사도 부를 수 있다 (KEY-158). */
  if (!document.getElementById("patient-facts")) return;

  /* **다섯 탭이 다 열려 있다.** 안내문 · 최종 확인 · 현황은 `js/visit-guide.js`
     가 채운다. 와이어프레임에서 의사 화면(D1)은 별도 페이지가 아니라 이 탭의
     뒷칸이라, 스탭도 의사도 같은 다섯 칸을 본다 — 가르는 것은 버튼이다. */
/* **「진료기록」은 이 화면에 판이 없다.** 판독 화면(`/ocr-review.html`)이
   그 칸이다 — 와이어프레임 S1-6·S1-7.

   전에는 여기에도 업로드 판이 하나 더 있어서 같은 칸에 두 화면이었다.
   판독이 끝난 환자를 눌러도 빈 업로드 판이 떴고, 판독을 보려면 그 판 안의
   「판독 결과 확인」을 한 번 더 눌러야 했다. 올리는 일도 판독 화면 머리의
   「OCR 업로드」가 한다. */
  var TABS = VISIT_STEPS.filter(function (step) {
    return step.page === "/patients.html";
  }).map(function (step) {
    return step.key;
  });

  /* 늦게 온 응답이 지금 보고 있는 환자를 덮어쓰지 않게 하는 번호.
     `visit_id` 를 쓰면 같은 환자를 빠르게 다시 고를 때(A→B→A) 값이 그대로라
     구분이 안 된다. `patients.js` 의 `lookupSeq` 와 같은 방식이다. */
  var loadSeq = 0;

  var row = null; // 오늘 목록에서 고른 줄 (front-desk 읽기 모델)
  var visit = null; // 그 줄의 진료 상세 (GET /visits/{id})
  var patient = null; // 그 진료 건의 환자
  var history = []; // 지난 방문
  var timeline = []; // 이번 진료의 시간순 이력 (GET /visits/{id}/timeline)

  function el(id) {
    return document.getElementById(id);
  }

  /* ── 탭 ─────────────────────────────────────────────── */

  function showTab(name) {
    if (TABS.indexOf(name) === -1) return; // 모르는 이름이면 아무것도 하지 않는다
    TABS.forEach(function (t) {
      el("panel-" + t).hidden = t !== name;
    });
    document.querySelectorAll(".tab").forEach(function (tab) {
      var on = tab.dataset.tab === name;
      tab.setAttribute("aria-selected", String(on));
      /* 지나온 칸은 ✓, 지금은 ●, 아직은 ○ — 와이어프레임 S1-4·S1-6 의 표시다.
         규칙은 `js/step-nav.js` 가 갖는다. 판독 화면도 같은 것을 쓰므로 두
         화면에서 표시가 갈리지 않는다. */
      tab.querySelector(".tab__mark").textContent =
        typeof stepMark === "function" ? stepMark(tab.dataset.tab, name) : on ? "●" : "○";
    });
  }

  el("tabs").addEventListener("click", function (event) {
    var tab = event.target.closest(".tab");
    if (!tab) return;
    if (tab.getAttribute("aria-disabled") === "true") return;
    /* 다른 화면에 사는 단계의 주소는 공용 모듈이 `data-href`로 정한다.
       화면마다 별도의 이동표를 두면 단계 정의와 실제 이동이 다시 갈린다. */
    var href = tab.getAttribute("data-href");
    if (href) {
      location.href = href;
      return;
    }
    showTab(tab.dataset.tab);
  });

  /* ── 머리 ────────────────────────────────────────────
     누구의 기록을 다루는 중인지 늘 붙어 있어야 다른 환자에게 잘못 넣지 않는다.
     탭을 옮겨도 이 줄은 그대로 있다. */
  function renderHead() {
    el("p-name").textContent = row.name;
    el("p-id").textContent = "차트 " + row.hospital_patient_no + (patient ? " · " + patient.birth_date : "");

    /* 배지는 목록 줄이 준 상태 그대로다 — 화면이 파생하지 않는다(계약 §6).
       색은 한글 문구가 아니라 업무 카테고리로 정한다. */
    var state = el("p-state");
    state.hidden = !row.detail_status;
    state.textContent = statusLabel(row.detail_status);
    state.className = stateClass(row.work_category);

    /* 진료과는 상세를 받아야 안다 — 그때까지는 담당의와 날짜만 붙인다. */
    el("p-visit").textContent = [visit && visit.department, doctorName(), dayLabel(row.visited_at) + " 진료"]
      .filter(Boolean)
      .join(" · ");
  }

  /* 상세는 `doctor_id` 만 준다. 이름은 목록 줄이 들고 온 것을 쓰고, 수정으로
     바뀐 뒤에는 DOCTORS 에서 찾는다.
     TODO(KEY-33) 직원 API 가 생기면 이름을 거기서 받는다. */
  function doctorName() {
    if (visit && visit.doctor_id) {
      var found = DOCTORS.find(function (d) {
        return d.doctor_id === visit.doctor_id;
      });
      if (found) return found.name;
    }
    return row.doctor ? row.doctor.name : "";
  }



  /* ── 보여 주기 ───────────────────────────────────────── */

  function facts(rows) {
    return rows
      .map(function (r) {
        return (
          "<dt>" +
          esc(r[0]) +
          "</dt><dd>" +
          esc(r[1] || "—") +
          (r[2] ? '<span class="facts__note">' + esc(r[2]) + "</span>" : "") +
          "</dd>"
        );
      })
      .join("");
  }

  function renderPatient() {
    var consent = patient.sms_consent
      ? "동의" + (patient.sms_consented_at ? " · " + patient.sms_consented_at : "")
      : "거부" + (patient.sms_opted_out_at ? " · " + patient.sms_opted_out_at : "");

    el("patient-facts").innerHTML = facts([
      ["이름", patient.name],
      ["차트번호", patient.hospital_patient_no],
      ["생년월일", patient.birth_date + " (" + ageOf(patient.birth_date) + "세)"],
      ["휴대폰", formatPhone(patient.phone), "이 번호로 안내 문자가 발송됩니다"],
      ["문자 수신", consent],
    ]);
  }

  function renderVisit() {
    el("visit-facts").innerHTML = facts(
      [
        ["진료과 · 담당", [visit.department, doctorName()].filter(Boolean).join(" · ")],
        ["진료일", [dayLabel(visit.visited_at), timeLabel(visit.visited_at)].filter(Boolean).join(" · ")],
        ["현재 상태", statusLabel(row.detail_status)],
        /* 계획 중단은 문자를 멈추는 스위치다(계약 §4). 켜져 있으면 그 사실이 보여야
         「왜 안내가 안 나가지」를 다른 데서 찾지 않는다. */
        visit.planned_stop ? ["계획 중단", "켜짐", "확인 · 소진 · 재진 문자를 보내지 않습니다"] : null,
      ].filter(Boolean),
    );
  }

  function renderHistory() {
    if (!history.length) {
      el("past").innerHTML = '<tr><td colspan="4" class="past__blank">이번이 첫 방문입니다</td></tr>';
      return;
    }
    el("past").innerHTML = history
      .map(function (v) {
        return (
          "<tr><td>" +
          esc(visitDay(v.visited_at)) +
          "</td><td>" +
          esc(v.diagnosis_name) +
          "</td><td>" +
          /* `v.days` 가 0 이면 falsy 라 「아직 못 가져왔다」와 같아진다.
             단회 처방(0일)이 오기 시작하면 둘을 구분할 수 없다. */
          esc([v.drug, v.days == null ? "" : v.days + "일"].filter(Boolean).join(" · ")) +
          "</td><td>" +
          /* TODO(KEY-75) 안내문 화면이 생기면 여기서 그 안내문으로 간다 */
          (v.has_guide
            ? '<span class="past__guide">안내문 있음</span>'
            : '<span class="past__none">안내문 없음</span>') +
          "</td></tr>"
        );
      })
      .join("");
  }

  /* 이력 이름표·되돌림·시각 함수는 IIFE 밖으로 옮겼다 (KEY-158) — 위쪽 참고.
     여기서 그리기만 한다. */
  function renderTimeline() {
    var list = el("visit-timeline");
    var note = el("visit-timeline-note");
    if (!timeline.length) {
      list.innerHTML = "";
      note.textContent = "이 진료의 기록이 아직 없습니다";
      note.hidden = false;
      return;
    }
    note.hidden = true;
    list.innerHTML = timeline
      .map(function (entry) {
        var detail = timelineDetail(entry);
        /* 수식어는 아는 값만 붙인다 — 목록이 정한 것이라 esc 를 거치지 않는다. */
        var mod = TIMELINE_CATEGORY_MODIFIER[entry.category];
        return (
          '<li class="timeline__row' +
          (mod ? " timeline__row--" + mod : "") +
          '"><span class="timeline__when">' +
          esc(timelineWhen(entry.at)) +
          '</span><span class="timeline__what">' +
          esc(TIMELINE_EVENT_LABEL[entry.event] || entry.event) +
          (detail ? ' <span class="timeline__detail">' + esc(detail) + "</span>" : "") +
          "</span></li>"
        );
      })
      .join("");
  }

  /* ── 수정 ────────────────────────────────────────────── */

  function field(name, label, value, type, hint) {
    return (
      '<label class="field"><span class="field__label">' +
      esc(label) +
      '</span><input class="field__input" type="' +
      (type || "text") +
      '" name="' +
      name +
      '" value="' +
      esc(value == null ? "" : value) +
      '" autocomplete="off" />' +
      (hint ? '<span class="field__hint">' + esc(hint) + "</span>" : "") +
      "</label>"
    );
  }

  function lockedField(label, value, hint) {
    return (
      '<label class="field field--locked"><span class="field__label">' +
      esc(label) +
      '</span><input class="field__input" type="text" value="' +
      esc(value == null ? "" : value) +
      '" readonly />' +
      '<span class="field__hint">' +
      esc(hint) +
      "</span></label>"
    );
  }

  /* 값은 id, 보이는 것은 이름이다 — 계약이 `department_id` · `doctor_id` 를 받고,
     이름을 보내면 폐지된 진료과인지 그 의사가 거기 소속인지 서버가 볼 수 없다.
     사람에게 id 를 보일 이유는 없으므로 두 층을 갈라 둔다. */
  function select(name, label, selectedId, options, idKey, hint) {
    return (
      '<label class="field"><span class="field__label">' +
      esc(label) +
      '</span><select class="field__input" name="' +
      name +
      '">' +
      options
        .map(function (o) {
          return (
            '<option value="' +
            esc(o[idKey]) +
            '"' +
            (o[idKey] === selectedId ? " selected" : "") +
            ">" +
            esc(o.name) +
            "</option>"
          );
        })
        .join("") +
      "</select>" +
      (hint ? '<span class="field__hint">' + esc(hint) + "</span>" : "") +
      "</label>"
    );
  }

  function openPatientEdit() {
    el("patient-edit").innerHTML =
      '<div class="grid2">' +
      field("name", "이름 *", patient.name) +
      /* 차트번호는 고칠 수 없다 — 계약이 생성 후 변경 불가로 정했다.
         왜 못 고치는지는 적어 둔다. 안 그러면 「고장났다」로 읽힌다.

         등록 화면(`patients.js`)이 쓰는 `.field--locked` 를 그대로 쓴다.
         같은 화면 안에 「잠긴 칸」이 두 모양으로 있으면 어느 쪽이 맞는지
         다음 사람이 고르게 된다. `<label>` 이라 이름과 값도 이어진다. */
      lockedField("차트번호", patient.hospital_patient_no, "차트번호는 등록 후 바꿀 수 없습니다 — 잘못 등록되었다면 관리자에게 알려 주세요") +
      field("birth_date", "생년월일 *", patient.birth_date, "text", "1994-07-22 처럼 적어 주세요") +
      field("phone", "휴대폰 *", formatPhone(patient.phone), "text", "이 번호로 안내 문자가 발송됩니다") +
      "</div>" +
      '<label class="check"><input type="checkbox" name="sms_consent"' +
      (patient.sms_consent ? " checked" : "") +
      " /><span>안내 문자 수신에 동의하셨습니다</span></label>" +
      '<p class="field__hint" data-error hidden></p>' +
      '<div class="actions"><button class="button-ghost" type="button" data-cancel>취소</button>' +
      '<span class="grow"></span><button class="button-primary" type="submit">저장</button></div>';

    el("patient-facts").hidden = true;
    el("patient-edit").hidden = false;
    el("edit-patient").hidden = true;
    el("patient-edit").querySelector("[name=name]").focus();
  }

  /* 상세가 주는 것은 진료과 **이름 스냅샷**이다(계약 §4) — id 는 명령 필드라
     응답에 없다. 고르는 칸을 채우려면 이름으로 되찾는 수밖에 없다.
     TODO(KEY-33) 진료과 API 가 생기면 그 목록에서 찾는다. */
  function currentDepartmentId() {
    var found = DEPARTMENTS.find(function (d) {
      return d.name === visit.department;
    });
    return found ? found.department_id : DEPARTMENTS[0].department_id;
  }

  function openVisitEdit() {
    el("visit-edit").innerHTML =
      '<div class="grid2">' +
      select("department_id", "진료과 *", currentDepartmentId(), DEPARTMENTS, "department_id") +
      select("doctor_id", "담당의사 *", visit.doctor_id, DOCTORS, "doctor_id", "해당 의사에게 승인 요청이 전달됩니다") +
      "</div>" +
      '<label class="check"><input type="checkbox" name="planned_stop"' +
      (visit.planned_stop ? " checked" : "") +
      " /><span>계획 중단 — 확인 · 소진 · 재진 문자를 보내지 않습니다</span></label>" +
      '<p class="field__hint">임신 계획 등으로 원장님이 복용을 멈추신 경우입니다. 켜 두면 이 환자에게 안내 문자가 나가지 않습니다.</p>' +
      '<p class="field__hint" data-error hidden></p>' +
      '<div class="actions"><button class="button-ghost" type="button" data-cancel>취소</button>' +
      '<span class="grow"></span><button class="button-primary" type="submit">저장</button></div>';

    el("visit-facts").hidden = true;
    el("visit-edit").hidden = false;
    el("edit-visit").hidden = true;
  }

  function closeEdit(which) {
    el(which + "-edit").hidden = true;
    el(which + "-facts").hidden = false;
    el("edit-" + which).hidden = false;
  }

  function showError(form, text) {
    var line = form.querySelector("[data-error]");
    line.textContent = text;
    line.classList.add("field__hint--bad");
    line.hidden = false;
  }

  /* 서버가 코드로 답한다. 화면 문구는 코드마다 다르다 — 사용자가 해야 할 일이
     다르기 때문이다(다시 입력할 것인가, 사람을 부를 것인가). */
  /* 규칙은 **적은 순서대로** 본다 — 좁은 것을 먼저. 문장을 고르는 방식은
     `api.js` 의 `errorMessage()` 가 갖는다. 같은 모양을 세 파일이 각자 적고
     있어서 기본 문구를 바꿀 때 세 곳을 고쳐야 했다 (이희진 님 `#121` 리뷰). */
  var SAVE_SAYINGS = [
    { status: 403, say: "이 환자를 수정할 권한이 없습니다 — 스탭 또는 의사 계정으로 로그인해 주세요." },
    { status: 404, say: "이 환자를 찾을 수 없습니다. 목록을 새로 고쳐 주세요." },
    { code: "EMPTY_UPDATE_FIELDS", say: "바뀐 내용이 없습니다." },
    /* 진료과·의사는 서버가 검증한다(계약 §7). 「입력을 다시 보라」로 뭉뜽그리면
       고를 수 있는 것만 고른 사람은 무엇을 고쳐야 할지 알 수 없다. */
    { code: "INVALID_DEPARTMENT", say: "선택한 진료과를 쓸 수 없습니다 — 목록을 새로 고쳐 주세요." },
    { code: "DOCTOR_DEPARTMENT_MISMATCH", say: "그 의사는 선택한 진료과 소속이 아닙니다." },
    /* 판독·안내가 이미 붙은 뒤에는 담당을 못 바꾼다. 「저장 실패」로 두면
       될 때까지 다시 누른다 — 왜 잠겼는지와 누구를 불러야 하는지를 적는다. */
    { code: "VISIT_LOCKED", say: "안내문 작업이 시작되어 담당을 바꿀 수 없습니다 — 관리자에게 알려 주세요." },
    { code: "INVALID_REQUEST", say: "입력한 값을 다시 확인해 주세요." },
  ];

  function messageFor(error) {
    return errorMessage(error, SAVE_SAYINGS, "저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
  }

  /* 바뀐 것만 보낸다 — 계약의 PATCH 는 부분 수정이고, 안 바뀐 값을 같이 보내면
     그 사이 다른 사람이 고친 것을 덮어쓴다. */
  function changed(before, after) {
    var patch = {};
    Object.keys(after).forEach(function (k) {
      if (String(after[k]) !== String(before[k])) patch[k] = after[k];
    });
    return patch;
  }

  el("edit-patient").addEventListener("click", openPatientEdit);
  el("edit-visit").addEventListener("click", openVisitEdit);

  el("patient-edit").addEventListener("click", function (event) {
    if (event.target.closest("[data-cancel]")) closeEdit("patient");
  });
  el("visit-edit").addEventListener("click", function (event) {
    if (event.target.closest("[data-cancel]")) closeEdit("visit");
  });

  el("patient-edit").addEventListener("submit", function (event) {
    event.preventDefault();
    var form = this;
    var next = {
      name: form.name.value.trim(),
      birth_date: form.birth_date.value.trim(),
      phone: form.phone.value.replace(/\D/g, ""),
      sms_consent: form.sms_consent.checked,
    };
    if (!next.name) return showError(form, "이름을 입력해 주세요.");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(next.birth_date)) return showError(form, "생년월일은 1994-07-22 처럼 적어 주세요.");
    if (!/^01\d{8,9}$/.test(next.phone)) return showError(form, "휴대폰 번호를 다시 확인해 주세요.");

    var patch = changed(patient, next);
    if (!Object.keys(patch).length) return closeEdit("patient");

    form.querySelector("[type=submit]").disabled = true;
    /* 저장이 도는 사이 다른 환자로 넘어갈 수 있다. 그때 이 응답을 그대로
       적용하면 **지금 보고 있는 환자에게 앞사람 값이 덮어써진다.** */
    var mine = loadSeq;
    patientsApi
      .update(patient.patient_id, patch)
      .then(function (saved) {
        if (mine !== loadSeq) return;
        patient = saved;
        /* 이름이 바뀌면 목록 줄과 머리도 같이 바뀌어야 한다 — 한 화면 안에서
           같은 사람이 두 이름으로 보이면 그때부터 아무것도 못 믿는다. */
        row.name = saved.name;
        renderPatient();
        renderHead();
        refreshRow();
        closeEdit("patient");
      })
      .catch(function (error) {
        if (mine !== loadSeq) return;
        form.querySelector("[type=submit]").disabled = false;
        showError(form, messageFor(error));
      });
  });

  el("visit-edit").addEventListener("submit", function (event) {
    event.preventDefault();
    var form = this;
    var patch = changed(
      { department_id: currentDepartmentId(), doctor_id: visit.doctor_id, planned_stop: visit.planned_stop },
      {
        department_id: Number(form.department_id.value),
        doctor_id: Number(form.doctor_id.value),
        planned_stop: form.planned_stop.checked,
      },
    );
    if (!Object.keys(patch).length) return closeEdit("visit");

    form.querySelector("[type=submit]").disabled = true;
    /* 진료 쪽은 더 위험하다 — 계획 중단은 문자를 멈추는 스위치라,
       엉뚱한 환자에게 켜진 것으로 보이면 안내가 왜 안 나가는지 못 찾는다. */
    var mine = loadSeq;
    patientsApi
      .updateVisit(visit.visit_id, patch)
      .then(function (saved) {
        if (mine !== loadSeq) return;
        visit = saved;
        renderVisit();
        renderHead();
        refreshRow();
        closeEdit("visit");
      })
      .catch(function (error) {
        if (mine !== loadSeq) return;
        form.querySelector("[type=submit]").disabled = false;
        showError(form, messageFor(error));
      });
  });

  /* 목록 줄도 같이 고친다.
     `rows` 를 직접 뒤지지 않고 `shell.js` 가 낸 `updateRow()` 로 간다 —
     목록의 원본은 그 파일이 갖는다는 원칙이 코드에 적혀 있는데 여기서만
     어기고 있었다. 그 함수가 그 줄 하나만 다시 그린다.

     **다섯 칸을 다 넘긴다.** 예전에는 이름과 담당만 넘겨서 진료과와 계획
     중단이 목록에 안 남았다. 지금은 목업이 같은 객체를 가리켜 우연히 맞아
     보이지만, 서버가 붙어 응답이 독립된 객체로 오면 이 환자에서 나갔다
     돌아왔을 때 저장 전 값이 보인다. */
  function refreshRow() {
    if (!visit) return;
    updateRow(row.visit_id, {
      name: row.name,
      /* 줄은 front-desk 모델이라 담당의가 객체다. 상세는 id 만 주므로
         이름을 붙여 넣어야 목록 줄이 옛 이름으로 남지 않는다. */
      doctor: { doctor_id: visit.doctor_id, name: doctorName() },
      department: visit.department,
      planned_stop: visit.planned_stop,
    });
  }

  /* 불러오는 동안에는 수정을 열 수 없다. 숨기지 않고 **끈다** —
     사라졌다 나타나면 화면이 흔들리고, 눌러 보고서야 안 되는 것을 안다. */
  function setEditable(on) {
    ["edit-patient", "edit-visit"].forEach(function (id) {
      el(id).disabled = !on;
    });
  }

  /* `formatPhone` 은 `patients-api.js` 것을 쓴다 — 여기 한 벌 더 두었더니
     글자까지 같은 복사본이 되어, 한쪽만 고치면 화면마다 번호 모양이 갈린다. */

  /* ── 들어오기 ────────────────────────────────────────── */

  function load(next) {
    row = next;
    visit = null;
    patient = null;
    history = [];
    timeline = [];

    closeEdit("patient");
    closeEdit("visit");
    /* 아직 값이 없다. 이 사이에 [수정]을 누르면 `patient.name` 에서 죽는다 —
       `visit` 은 줄에서 바로 오지만 `patient` 은 응답을 기다려야 하기 때문이다. */
    setEditable(false);
    renderHead();
    /* 불러오는 중에 앞사람 값이 남아 있으면 안 된다 — 잠깐이라도 다른 사람의
       생년월일이 이 이름 아래 붙는다. */
    el("patient-facts").innerHTML = "<dt>불러오는 중…</dt><dd></dd>";
    el("visit-facts").innerHTML = "";
    el("past").innerHTML = "";
    /* 이력은 아직 안 왔다 — 빈 목록("기록 없음")을 여기서 그리면 불러오는 동안
       그 문구가 잠깐 뜬다. `past` 처럼 비워만 둔다. */
    el("visit-timeline").innerHTML = "";
    el("visit-timeline-note").hidden = true;

    var mine = ++loadSeq;

    Promise.all([
      patientsApi.get(row.patient_id),
      patientsApi.visits(row.patient_id),
      patientsApi.getVisit(row.visit_id),
    ])
      .then(function (all) {
        if (mine !== loadSeq) return;
        patient = all[0];
        history = all[1].items.filter(function (v) {
          return v.visit_id !== row.visit_id; // 오늘 것은 위 칸에 이미 있다
        });
        visit = all[2];
        setEditable(true);
        renderPatient();
        renderVisit();
        renderHistory();
        renderHead(); // 생년월일과 진료과는 응답을 받은 뒤에야 머리에 붙는다
      })
      .catch(function (error) {
        if (mine !== loadSeq) return;
        el("patient-facts").innerHTML = "<dt>—</dt><dd>" + esc(messageFor(error)) + "</dd>";
      });

    /* 이력은 곁다리 패널이다 — 따로 불러서, 여기서 실패해도 환자 카드 전체가
       빈칸이 되지 않게 한다. */
    patientsApi
      .timeline(row.visit_id)
      .then(function (body) {
        if (mine !== loadSeq) return;
        timeline = (body && body.entries) || [];
        renderTimeline();
      })
      .catch(function () {
        if (mine !== loadSeq) return;
        timeline = [];
        el("visit-timeline").innerHTML = "";
        var note = el("visit-timeline-note");
        note.textContent = "진료 이력을 불러오지 못했습니다";
        note.hidden = false;
      });
  }

  document.addEventListener("visit:selected", function (event) {
    var current = event.detail.open_tab || "basic";
    /* 단계 버튼은 HTML에 복사해 두지 않고 공용 모듈에서 매번 만든다. 그래야
       이름·순서·이동 규칙이 판독·의사 화면과 갈리지 않는다 (KEY-233). */
    renderVisitSteps(el("tabs"), current, event.detail.visit_id);
    load(event.detail);
    showTab(current);
  });

  /* **같은 사람인데 줄 값만 새로 왔다** — 상태 탭을 켜고 끄거나, 승인 뒤에
     목록을 다시 읽었을 때다. 머리의 상태 배지만 고친다.
     `load()` 를 부르면 열어 둔 칸이 기본정보로 되감기고 받아 둔 것이 날아간다. */
  document.addEventListener("visit:refreshed", function (event) {
    if (!row || !event.detail || row.visit_id !== event.detail.visit_id) return;
    row = event.detail;
    renderHead();
  });
})();
