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

(function () {
  var TABS = ["basic", "record"];

  var row = null; // 오늘 목록에서 고른 줄 (front-desk 읽기 모델)
  var visit = null; // 그 줄의 진료 상세 (GET /visits/{id})
  var patient = null; // 그 진료 건의 환자
  var history = []; // 지난 방문

  function el(id) {
    return document.getElementById(id);
  }

  /* ── 탭 ─────────────────────────────────────────────── */

  function showTab(name) {
    if (TABS.indexOf(name) === -1) return; // 안내문 · 최종 확인 · 현황은 아직 없다
    TABS.forEach(function (t) {
      el("panel-" + t).hidden = t !== name;
    });
    document.querySelectorAll(".tab").forEach(function (tab) {
      var on = tab.dataset.tab === name;
      tab.setAttribute("aria-selected", String(on));
      tab.querySelector(".tab__mark").textContent = on ? "●" : "○";
    });
  }

  el("tabs").addEventListener("click", function (event) {
    var tab = event.target.closest(".tab");
    if (!tab) return;
    if (tab.getAttribute("aria-disabled") === "true") return;
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

  /* 「2026-08-19 (오늘)」 — 오늘인지가 붙어야 지난 진료를 보고 있다는 것을 안다 */
  function dayLabel(isoDatetime) {
    if (!isoDatetime) return "";
    var day = isoDatetime.slice(0, 10);
    return day + (day === toIsoDate(new Date()) ? " (오늘)" : "");
  }

  function timeLabel(isoDatetime) {
    var m = String(isoDatetime || "").match(/T(\d{2}:\d{2})/);
    return m ? m[1] + " 등록" : "";
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
      ["휴대폰", maskPhone(patient.phone), "이 번호로 안내 문자가 발송됩니다"],
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
          esc(v.visited_at) +
          "</td><td>" +
          esc(v.diagnosis_name) +
          "</td><td>" +
          esc([v.drug, v.days ? v.days + "일" : ""].filter(Boolean).join(" · ")) +
          "</td><td>" +
          /* TODO(KEY-64) 안내문 화면이 생기면 여기서 그 안내문으로 간다 */
          (v.has_guide
            ? '<span class="past__guide">안내문 있음</span>'
            : '<span class="past__none">안내문 없음</span>') +
          "</td></tr>"
        );
      })
      .join("");
  }

  /* 발송 이력은 안내·발송 도메인 소유다. 그 API 가 아직 없다.
     빈 줄을 두는 대신 「없다」와 「아직 못 가져온다」를 갈라 적는다 —
     둘을 같게 보이면 발송이 안 된 것으로 읽힌다. */
  function renderSends() {
    el("sends").textContent = "발송 이력은 안내·발송 기능이 붙으면 여기에 표시됩니다 (준비 중)";
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
      /* 차트번호는 폼에 넣지 않는다 — 계약이 생성 후 변경 불가로 정했다.
         왜 못 고치는지는 적어 둔다. 안 그러면 「고장났다」로 읽힌다. */
      '<div class="field"><span class="field__label">차트번호</span>' +
      '<div class="field__locked-value">' +
      esc(patient.hospital_patient_no) +
      " 🔒</div>" +
      '<span class="field__hint">차트번호는 등록 후 바꿀 수 없습니다 — 잘못 등록되었다면 관리자에게 알려 주세요</span></div>' +
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
  function messageFor(error) {
    if (!error) return "저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.";
    if (error.status === 403) return "이 환자를 수정할 권한이 없습니다 — 스탭 또는 의사 계정으로 로그인해 주세요.";
    if (error.status === 404) return "이 환자를 찾을 수 없습니다. 목록을 새로 고쳐 주세요.";
    if (error.code === "EMPTY_UPDATE_FIELDS") return "바뀐 내용이 없습니다.";
    /* 진료과·의사는 서버가 검증한다(계약 §7). 「입력을 다시 보라」로 뭉뜽그리면
       고를 수 있는 것만 고른 사람은 무엇을 고쳐야 할지 알 수 없다. */
    if (error.code === "INVALID_DEPARTMENT") return "선택한 진료과를 쓸 수 없습니다 — 목록을 새로 고쳐 주세요.";
    if (error.code === "DOCTOR_DEPARTMENT_MISMATCH") return "그 의사는 선택한 진료과 소속이 아닙니다.";
    /* 판독·안내가 이미 붙은 뒤에는 담당을 못 바꾼다. 「저장 실패」로 두면
       될 때까지 다시 누른다 — 왜 잠겼는지와 누구를 불러야 하는지를 적는다. */
    if (error.code === "VISIT_LOCKED")
      return "안내문 작업이 시작되어 담당을 바꿀 수 없습니다 — 관리자에게 알려 주세요.";
    if (error.code === "INVALID_REQUEST") return "입력한 값을 다시 확인해 주세요.";
    return "저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.";
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
    patientsApi
      .update(patient.patient_id, patch)
      .then(function (saved) {
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
    patientsApi
      .updateVisit(visit.visit_id, patch)
      .then(function (saved) {
        visit = saved;
        renderVisit();
        renderHead();
        refreshRow();
        closeEdit("visit");
      })
      .catch(function (error) {
        form.querySelector("[type=submit]").disabled = false;
        showError(form, messageFor(error));
      });
  });

  /* 목록 줄도 같이 고친다. 다시 불러오면 고른 줄과 스크롤이 튀므로 그 줄만 손본다. */
  function refreshRow() {
    var listed = rows.find(function (r) {
      return r.visit_id === row.visit_id;
    });
    if (!listed) return;
    listed.name = row.name;
    /* 줄은 front-desk 모델이라 담당의가 객체다. 상세는 id 만 주므로
       이름을 붙여 넣어야 목록 줄이 옛 이름으로 남지 않는다. */
    listed.doctor = { doctor_id: visit.doctor_id, name: doctorName() };
    renderRows(row.visit_id);
  }

  function formatPhone(digits) {
    var d = (digits || "").replace(/\D/g, "");
    if (d.length === 11) return d.slice(0, 3) + "-" + d.slice(3, 7) + "-" + d.slice(7);
    if (d.length === 10) return d.slice(0, 3) + "-" + d.slice(3, 6) + "-" + d.slice(6);
    return d;
  }

  /* ── 들어오기 ────────────────────────────────────────── */

  function load(next) {
    row = next;
    visit = null;
    patient = null;
    history = [];

    closeEdit("patient");
    closeEdit("visit");
    renderHead();
    /* 불러오는 중에 앞사람 값이 남아 있으면 안 된다 — 잠깐이라도 다른 사람의
       생년월일이 이 이름 아래 붙는다. */
    el("patient-facts").innerHTML = "<dt>불러오는 중…</dt><dd></dd>";
    el("visit-facts").innerHTML = "";
    el("past").innerHTML = "";
    renderSends();

    var mine = row.visit_id; // 늦게 온 응답이 새 환자를 덮어쓰지 않게 한다

    Promise.all([
      patientsApi.get(row.patient_id),
      patientsApi.visits(row.patient_id),
      patientsApi.getVisit(row.visit_id),
    ])
      .then(function (all) {
        if (mine !== row.visit_id) return;
        patient = all[0];
        history = all[1].items.filter(function (v) {
          return v.visit_id !== row.visit_id; // 오늘 것은 위 칸에 이미 있다
        });
        visit = all[2];
        renderPatient();
        renderVisit();
        renderHistory();
        renderHead(); // 생년월일과 진료과는 응답을 받은 뒤에야 머리에 붙는다
      })
      .catch(function (error) {
        if (mine !== row.visit_id) return;
        el("patient-facts").innerHTML = "<dt>—</dt><dd>" + esc(messageFor(error)) + "</dd>";
      });
  }

  document.addEventListener("visit:selected", function (event) {
    load(event.detail);
    showTab(event.detail.open_tab || "basic");
  });
})();
