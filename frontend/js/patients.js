/* 환자 등록 — S1-2 · S1-3 (KEY-35)
 *
 * 두 화면이 아니라 **한 화면의 두 상태**다. 「신규냐 기존이냐」를 미리 묻지 않는다 —
 * 스탭은 그 환자가 이 프로그램에 등록돼 있는지 알 수 없다. EMR 에 있어도 여기엔
 * 없을 수 있고, 도입 초기에는 전부 신규다. 그래서 검색 하나로 시작하고
 * **결과가 곧 분기가 된다.**
 *
 * ② 환자 정보는 두 상태가 같은 자리에 있다 — 고르면 채워지고 잠기며,
 * 고르지 않으면 빈 채로 열려 있다. 따로 「새 환자」 버튼을 두지 않아도
 * 신규로 가는 길이 닫히지 않는다. 같은 이름이어도 다른 분일 수 있기 때문이다.
 */

/* 결과 안에서 생년월일이 겹치는 값들 */
function tiedBirthDates(items) {
  var seen = {};
  var tied = {};
  items.forEach(function (p) {
    if (seen[p.birth_date]) tied[p.birth_date] = true;
    seen[p.birth_date] = true;
  });
  return Object.keys(tied);
}

(function () {
  /* **자기 칸이 없는 페이지에서는 아무것도 하지 않는다.**
     이 파일은 `patients.html` 에만 실린다. 뿌리가 없으면 조용히 돌아간다 —
     위 순수 규칙은 그대로 남아서 다른 파일도, 검사도 부를 수 있다 (KEY-158). */
  if (!document.getElementById("find-form")) return;

  var view = document.getElementById("view-register");
  var findForm = document.getElementById("find-form");
  var findQ = document.getElementById("find-q");
  var found = document.getElementById("found");
  var hitsWrap = document.getElementById("hits-wrap");
  var hits = document.getElementById("hits");
  var submit = document.getElementById("reg-submit");
  var lockedNote = document.getElementById("locked-note");
  var consent = document.getElementById("f-consent");
  var consentLabel = document.getElementById("consent-label");

  var FIELDS = ["f-name", "f-chart", "f-birth", "f-phone"];
  var HINTS = {
    "f-name": "위에서 찾은 이름이 그대로 넘어옵니다",
    "f-chart": "EMR 차트번호와 동일하게",
    "f-birth": "환자 본인확인에 사용합니다",
    "f-phone": "이 번호로 안내 문자가 발송됩니다",
  };

  /* picked 가 있으면 기존 환자, 없으면 신규다. 이 하나가 화면 전체의 분기다. */
  var picked = null;
  var searched = false; // 한 번이라도 찾아 봤는가 — 안내 문구를 언제 띄울지 가른다
  var dupChart = null; // 같은 차트번호를 쓰는 기존 환자
  var dupPhone = null; // 같은 번호를 쓰는 기존 환자 — 막지 않고 알리기만 한다
  var tiedDates = []; // 이번 결과에서 생년월일이 겹친 값들
  var checking = false; // 중복을 서버에 묻는 중
  var lookupTimer = null;
  /* 보낸 순서와 도착 순서는 다르다. 「1」로 보낸 답이 「123」으로 보낸 답보다
     늦게 오면, 최신 입력에 대한 판정이 옛 판정으로 되돌아간다 — 중복인데
     경고가 사라지거나 그 반대가 된다. 마지막으로 보낸 것의 답만 받는다. */
  var lookupSeq = 0;

  function el(id) {
    return document.getElementById(id);
  }

  function value(id) {
    return el(id).value.trim();
  }

  /* 고른 항목의 보이는 글자. select 의 value 는 id 라 그대로 쓰면 숫자가 뜬다. */
  function chosenName(id) {
    var select = el(id);
    var option = select.options[select.selectedIndex];
    return option ? option.textContent : "";
  }

  /* 「2026-08-20T10:32:00+09:00」 — 계약이 받는 모양.
     Z(UTC)로 보내면 서버가 Asia/Seoul 로 옮길 때 자정 근처에서 날이 갈린다. */
  function nowWithOffset() {
    var now = new Date();
    var offset = -now.getTimezoneOffset();
    var sign = offset >= 0 ? "+" : "-";
    var pad = function (n) {
      return String(Math.floor(Math.abs(n))).padStart(2, "0");
    };
    return (
      toIsoDate(now) +
      "T" +
      pad(now.getHours()) +
      ":" +
      pad(now.getMinutes()) +
      ":" +
      pad(now.getSeconds()) +
      sign +
      pad(offset / 60) +
      ":" +
      pad(offset % 60)
    );
  }

  /* ── 열고 닫기 ───────────────────────────────────────── */

  function open(prefill) {
    /* 등록은 오늘 하는 일이다. 지난 날짜를 보고 있었다면 오늘로 되돌린 뒤 시작한다 —
       그래야 「진료일 = 오늘」과 목록에 서는 자리가 어긋나지 않는다. */
    if (toIsoDate(listDay) !== toIsoDate(new Date())) {
      listDay = new Date();
      renderDay();
      loadDay();
    }

    reset();
    showView("view-register");

    if (prefill) {
      findQ.value = prefill;
      runFind();
    } else {
      findQ.focus();
    }
  }

  function clearForm() {
    FIELDS.forEach(function (id) {
      el(id).value = "";
    });
    dupChart = null;
    dupPhone = null;
    consent.checked = false;
  }

  function reset() {
    picked = null;
    searched = false;
    tiedDates = [];
    findQ.value = "";
    found.hidden = true;
    hitsWrap.hidden = true;
    hits.innerHTML = "";
    clearForm();
    el("f-dept").value = DEPARTMENTS[0].department_id;
    el("f-doctor").value = DOCTORS[0].doctor_id;
    unlock();
    render();
  }

  function close() {
    reset();
    /* syncPane 은 등록 화면이 서 있으면 그냥 되돌아간다 — 탭을 켜고 끌 때
       쓰던 화면을 빼앗지 않으려는 가드다. 스스로 닫을 때는 그 가드를 넘어야
       한다. 안 그러면 취소를 눌러도 등록 화면에 그대로 머문다. */
    syncPane(true);
  }

  /* 등록 도중이라도 아직 아무것도 안 건드렸으면 되물을 것이 없다 */
  function dirty() {
    if (view.hidden) return false;
    if (picked) return true;
    if (findQ.value.trim()) return true;
    return FIELDS.some(function (id) {
      return value(id);
    });
  }

  /* ── ① 환자 찾기 ─────────────────────────────────────── */

  function runFind() {
    var q = findQ.value.trim();
    if (!q) return;

    return patientsApi.search(q).then(function (page) {
      searched = true;
      /* 고른 것을 놓는 순간 ② 도 비운다. 남겨 두면 앞사람의 생년월일 · 번호로
         새 환자가 등록된다 — 안내 문자가 엉뚱한 사람에게 간다. */
      picked = null;
      clearForm();
      unlock();

      if (!page.items.length) {
        /* S1-3 — 없으면 그 자리에서 새로 만든다. 친 것이 그대로 넘어와 다시 치지 않는다.
           숫자를 쳤으면 이름이 아니라 차트번호 칸으로 들어간다. */
        hitsWrap.hidden = true;
        hits.innerHTML = "";
        found.className = "found found--none";
        found.innerHTML =
          "「<b>" +
          esc(q) +
          "</b>」로 <b>등록된 환자가 없습니다.</b><br>이 프로그램을 처음 쓰시는 분입니다 — 아래에서 새로 등록합니다.";
        found.hidden = false;

        if (/^\d+$/.test(q)) {
          el("f-chart").value = q;
          el("f-name").value = "";
          el("f-name").focus();
        } else {
          el("f-name").value = q;
          el("f-chart").value = "";
          el("f-chart").focus();
        }
        lookupDuplicates();
        return render();
      }

      /* S1-2 — 같은 이름이 여럿이면 생년월일 · 폰 뒤 4자리 · 지난 방문일로 가른다.
         생년월일까지 같은 분이 섞여 있으면 「생년월일로 확인하세요」가 거짓말이 된다.
         무엇으로 갈라야 하는지가 결과마다 다르므로 안내도 결과를 보고 정한다 —
         잘못 고르면 다른 분의 진료에 오늘 기록이 붙는다. */
      tiedDates = tiedBirthDates(page.items);
      found.className = "found";
      found.innerHTML =
        "등록된 환자 <b>" +
        page.items.length +
        "명</b>을 찾았습니다 — " +
        (tiedDates.length
          ? "<b>생년월일이 같은 분이 있습니다.</b> 휴대폰 뒤 4자리로 확인"
          : "<b>생년월일로 본인을 확인</b>") +
        "한 뒤 고르세요.";
      found.hidden = false;
      renderHits(page.items, tiedDates);
      render();
    });
  }


  function renderHits(items, tied) {
    hits.innerHTML = items
      .map(function (p) {
        /* 갈라 주지 못하는 칸은 흐리게, 갈라 주는 칸은 진하게.
           눈이 가야 할 칸이 줄마다 다르므로 줄마다 표시한다. */
        var same = tied.indexOf(p.birth_date) !== -1;
        /* 줄 전체가 눌리되(마우스), 고르는 것은 진짜 버튼이다(키보드 · 화면낭독기).
           tr 에 role="button" 을 씌우면 표가 표로 읽히지 않아 어느 칸이 생년월일인지
           들리지 않는다 — 그 칸으로 사람을 가르는 화면에서 그건 치명적이다. */
        return (
          '<tr class="hit" data-patient=\'' +
          esc(JSON.stringify(p)) +
          "'>" +
          '<td><button class="hit__pick" type="button" aria-pressed="false">' +
          esc(p.name) +
          '</button></td><td class="' +
          (same ? "hit__tied" : "hit__key") +
          '">' +
          esc(p.birth_date) +
          '</td><td class="' +
          (same ? "hit__key" : "") +
          '">' +
          esc(formatPhone(p.phone)) +
          "</td><td>" +
          esc(p.hospital_patient_no) +
          "</td><td>" +
          esc(p.last_visited_on || "—") +
          "</td></tr>"
        );
      })
      .join("");
    hitsWrap.hidden = false;
  }

  /* 고른 줄은 검게 남긴다 — 무엇을 골랐는지 눈에서 사라지지 않게 */
  function pick(row) {
    picked = JSON.parse(row.dataset.patient);
    hits.querySelectorAll(".hit").forEach(function (r) {
      r.classList.toggle("hit--on", r === row);
      r.querySelector(".hit__pick").setAttribute("aria-pressed", String(r === row));
    });

    el("f-name").value = picked.name;
    el("f-chart").value = picked.hospital_patient_no;
    el("f-birth").value = picked.birth_date;
    el("f-phone").value = formatPhone(picked.phone);
    lock();
    render();
  }

  /* ── ② 환자 정보 잠금 ────────────────────────────────── */

  function lock() {
    FIELDS.forEach(function (id) {
      var input = el(id);
      input.readOnly = true;
      input.parentElement.classList.add("field--locked");
      var hint = el("h" + id.slice(1));
      if (hint) hint.hidden = true;
    });
    /* 기존 환자는 동의를 다시 받지 않는다 — 이미 받은 것을 그대로 쓴다 */
    consent.checked = true;
    consent.disabled = true;
    consentLabel.innerHTML = '안내 문자 수신에 동의하셨습니다 * <span class="check__note">기존 동의 유지 · 🔒</span>';
    lockedNote.hidden = false;
    /* TODO(KEY-50) 잠긴 값이 틀렸을 때 가는 [ 정보 수정 ] 버튼은 환자 카드 화면이
       생기면 여기에 붙인다. 지금은 갈 곳이 없어 문구로만 알린다. */
  }

  function unlock() {
    FIELDS.forEach(function (id) {
      var input = el(id);
      input.readOnly = false;
      input.parentElement.classList.remove("field--locked");
      var hint = el("h" + id.slice(1));
      if (hint) {
        hint.hidden = false;
        hint.textContent = HINTS[id];
        hint.classList.remove("field__hint--bad");
      }
    });
    consent.disabled = false;
    consentLabel.textContent = "안내 문자 수신에 동의하셨습니다 *";
    lockedNote.hidden = true;
  }

  /* 차트번호는 병원 내 유일하다. 이미 있으면 등록을 **시작에서** 막고
     위에서 그 환자를 고르라고 안내한다 — 중복 등록을 화면 끝에서 잡으면 늦다.
     휴대폰이 겹치는 것은 경고만 한다 — 가족이 한 번호를 함께 쓸 수 있다. */
  function lookupDuplicates() {
    clearTimeout(lookupTimer);
    if (picked) {
      dupChart = null;
      dupPhone = null;
      checking = false;
      return render();
    }

    /* 묻기 전에는 「없습니다」라고 못 한다. 아직 모르는 것을 ✓ 로 적어 두면
       빨리 치는 사람은 확인이 끝나기 전에 눌러 버린다 — 중복 등록이 그렇게 난다. */
    checking = !!value("f-chart");
    render();

    lookupTimer = setTimeout(function () {
      var mine = ++lookupSeq;
      var chart = value("f-chart");
      var phone = value("f-phone").replace(/\D/g, "");

      var jobs = [
        chart ? patientsApi.search(chart) : Promise.resolve({ items: [] }),
        phone.length >= 10 ? patientsApi.search(phone) : Promise.resolve({ items: [] }),
      ];

      Promise.all(jobs)
        .then(function (pages) {
          if (mine !== lookupSeq) return; // 늦게 온 옛 답은 버린다
          dupChart =
            pages[0].items.find(function (p) {
              return p.hospital_patient_no === chart;
            }) || null;
          dupPhone =
            pages[1].items.find(function (p) {
              return p.phone === phone;
            }) || null;
          checking = false;
          render();
        })
        .catch(function () {
          if (mine !== lookupSeq) return;
          /* 확인하지 못했으면 막지 않는다. 최종 판정은 서버가 한다(409). */
          dupChart = null;
          dupPhone = null;
          checking = false;
          render();
        });
    }, 250);
  }

  /* ── 등록 전 확인 ────────────────────────────────────── */

  function isoDateOk(text) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
    var d = new Date(text + "T00:00:00");
    if (isNaN(d.getTime())) return false;
    return toIsoDate(d) === text && d <= new Date();
  }

  function phoneOk(text) {
    /* 고른 환자의 잠긴 칸에도 이제 **진짜 번호**가 들어간다(전에는 가려진 값이라
       이 검사를 지나칠 수 없었다). 그래서 잠겼든 아니든 같은 규칙으로 잰다. */
    return /^01\d{8,9}$/.test(text.replace(/\D/g, ""));
  }

  /* 오늘 이미 서 있는 줄인가. 있으면 또 만들지 않고 그 줄로 보낸다. */
  function todayVisit() {
    if (!picked) return null;
    return visitToday(picked.patient_id);
  }

  function problems() {
    var out = [];

    if (picked) {
      var already = todayVisit();
      if (already)
        out.push({ ok: false, block: true, text: "오늘 이미 등록되어 있습니다 — 왼쪽 목록에서 그 줄을 고르세요" });
      else out.push({ ok: true, text: "오늘 이미 등록된 기록은 없습니다" });

      /* 생년월일까지 같은 분이 결과에 있었다면 「동명이인이 아닙니다」는 거짓이다.
         마지막으로 훑는 칸에서 단언해 버리면 잘못 고른 것을 잡을 기회가 사라진다. */
      if (tiedDates.indexOf(picked.birth_date) !== -1) {
        out.unshift({
          ok: false,
          block: false,
          text:
            "생년월일이 같은 분이 또 있습니다 — 휴대폰 " + formatPhone(picked.phone) + " 가 맞는지 확인하세요",
        });
      } else {
        out.unshift({ ok: true, text: "생년월일 일치 — 동명이인이 아닙니다" });
      }
      if (picked.last_visited_on) {
        out.splice(1, 0, {
          ok: true,
          text:
            "지난 방문 " +
            picked.last_visited_on +
            (picked.last_dx ? " · " + picked.last_dx : "") +
            (picked.last_drug ? " · " + picked.last_drug + " (계속)" : ""),
        });
      }
      return out;
    }

    /* 신규 — 빈 칸은 「아직」이지 「틀림」이 아니다. 다 채우기 전에는 조용히 둔다. */
    var chart = value("f-chart");
    var birth = value("f-birth");
    var phone = value("f-phone");

    if (!value("f-name")) out.push({ ok: false, block: true, quiet: true, text: "이름을 입력해 주세요" });

    if (!chart) out.push({ ok: false, block: true, quiet: true, text: "차트번호를 입력해 주세요" });
    else if (checking)
      out.push({ ok: false, block: true, wait: true, text: "차트번호가 이미 있는지 확인하는 중입니다" });
    else if (dupChart)
      out.push({
        ok: false,
        block: true,
        text: "차트번호 " + dupChart.hospital_patient_no + " 는 이미 등록되어 있습니다 — 위에서 그 환자를 고르세요",
      });
    else out.push({ ok: true, text: "같은 차트번호로 등록된 환자가 없습니다" });

    if (!birth) out.push({ ok: false, block: true, quiet: true, text: "생년월일을 입력해 주세요" });
    else if (!isoDateOk(birth)) out.push({ ok: false, block: true, text: "생년월일은 1994-07-22 처럼 적어 주세요" });

    if (!phone) out.push({ ok: false, block: true, quiet: true, text: "휴대폰 번호를 입력해 주세요" });
    else if (!phoneOk(phone)) out.push({ ok: false, block: true, text: "휴대폰 번호를 다시 확인해 주세요" });
    else if (dupPhone)
      out.push({
        ok: false,
        block: false,
        text: "같은 번호로 " + dupPhone.name + " 님이 등록되어 있습니다 — 가족이 함께 쓰는 번호일 수 있습니다",
      });

    if (!consent.checked)
      out.push({ ok: false, block: true, text: "문자 수신 동의가 체크되지 않았습니다 — 동의해야 등록됩니다" });

    return out;
  }

  function render() {
    var list = problems();

    document.getElementById("recap").innerHTML = [
      ["이름", value("f-name")],
      ["차트번호", value("f-chart")],
      ["생년월일", value("f-birth")],
      /* 고른 환자의 칸에는 이미 가려진 값이 들어 있다. 신규는 스탭이 방금 친
         실제 번호라 **가리지 않는다** — 가릴 대상이 없고, 등록 직전 마지막으로
         자릿수 오타를 눈으로 잡을 자리를 없앤다. 안내 문자가 갈 번호다. */
      ["휴대폰", value("f-phone")],
      /* 확인 화면에는 **사람이 읽는 이름**이 떠야 한다. 칸의 값은 id 다. */
      ["진료과 · 담당", chosenName("f-dept") + " · " + chosenName("f-doctor")],
      ["진료일", toIsoDate(new Date()) + " (오늘)"],
    ]
      .map(function (pair) {
        return "<dt>" + esc(pair[0]) + "</dt><dd>" + (pair[1] ? esc(pair[1]) : "—") + "</dd>";
      })
      .join("");

    document.getElementById("checks").innerHTML = list
      .filter(function (p) {
        return !p.quiet;
      })
      .map(function (p) {
        return (
          '<li class="check-line ' +
          (p.wait ? "check-line--wait" : p.ok ? "check-line--ok" : p.block ? "check-line--block" : "check-line--warn") +
          '"><span class="check-line__mark" aria-hidden="true">' +
          (p.wait ? "⋯" : p.ok ? "✓" : "⚠") +
          "</span>" +
          esc(p.text) +
          "</li>"
        );
      })
      .join("");

    var blocked = list.some(function (p) {
      return p.block;
    });
    submit.disabled = blocked || (!picked && !searched);
    submit.textContent = picked ? "오늘 환자로 등록" : "환자 등록";
  }

  /* ── 등록 ────────────────────────────────────────────── */

  function register() {
    submit.disabled = true;

    var makeVisit = function (patientId) {
      return patientsApi.createVisit(patientId, {
        department_id: null, // 진료과 검증 테이블 미구현 — KEY-33 이후 연결
        doctor_id: Number(el("f-doctor").value),
        /* 계약은 datetime 을 받는다. 오프셋을 붙여 보내야 서버가 어느 날의
           진료인지 시간대를 헤아리지 않아도 된다. */
        visited_at: nowWithOffset(),
      });
    };

    var chain = picked
      ? makeVisit(picked.patient_id)
      : patientsApi
          .create({
            name: value("f-name"),
            hospital_patient_no: value("f-chart"),
            birth_date: value("f-birth"),
            phone: value("f-phone").replace(/\D/g, ""),
            sms_consent: consent.checked,
          })
          .then(function (created) {
            return makeVisit(created.patient_id);
          });

    chain
      .then(function (visit) {
        reset();
        /* **돌려준다.** 목록을 서버에서 다시 받아 오므로 그 사이의 실패도
           아래 catch 로 와야 한다 — 안 그러면 등록은 됐는데 목록이 안 서고
           아무 말도 없이 끝난다. */
        return addVisit(visit); // 목록 「작성 중 · 진료기록 없음」에 서고 S1-5 로 넘어간다
      })
      .catch(function (error) {
        /* 화면에서 막는 것은 편의일 뿐이고 판정은 서버가 한다.
           그래서 화면이 통과시킨 뒤에도 409 가 올 수 있다 — 그때도 갈 곳을 알려 준다. */
        if (error && error.code === "DUPLICATE_HOSPITAL_PATIENT_NO") {
          dupChart = { hospital_patient_no: value("f-chart") };
          render();
          return;
        }
        alert("등록하지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
        render();
      });
  }

  /* ── 손짓 ────────────────────────────────────────────── */

  document.getElementById("add-patient").addEventListener("click", function () {
    open(document.getElementById("quick-search").value.trim());
  });
  document.getElementById("blank-add").addEventListener("click", function () {
    open("");
  });

  /* 목록이 「오늘 없음」을 보여 줄 때 그 자리에서 바로 등록으로 간다 */
  document.getElementById("rows").addEventListener("click", function (event) {
    var go = event.target.closest("[data-register-with]");
    if (go) open(go.dataset.registerWith);
  });

  findForm.addEventListener("submit", function (event) {
    event.preventDefault();
    runFind();
  });

  /* 버튼의 클릭도 여기로 올라온다 — Enter · Space 는 버튼이 알아서 클릭으로 바꾼다 */
  hits.addEventListener("click", function (event) {
    var row = event.target.closest(".hit");
    if (row) pick(row);
  });

  FIELDS.forEach(function (id) {
    el(id).addEventListener("input", function () {
      if (id === "f-chart" || id === "f-phone") lookupDuplicates();
      else render();
    });
  });
  consent.addEventListener("change", render);
  el("f-dept").addEventListener("change", render);
  el("f-doctor").addEventListener("change", render);

  submit.addEventListener("click", register);
  document.getElementById("reg-cancel").addEventListener("click", close);
  document.getElementById("reg-cancel-top").addEventListener("click", close);

  /* 등록 도중에 목록을 눌러도 잃는 것이 없어야 한다 */
  document.addEventListener("visit:selecting", function (event) {
    if (!dirty()) return;
    var ok = confirm("아직 저장하지 않았습니다. 그만두고 " + event.detail.name + " 님으로 가시겠습니까?");
    if (ok) return reset();
    event.preventDefault();
  });

  document.addEventListener("session:ready", function () {
    /* 사람에게는 이름을 보이고 서버에는 id 를 보낸다.
       계약이 `department_id` · `doctor_id` 를 받는다 — 이름을 보내면 폐지된
       진료과인지, 그 의사가 거기 소속인지 서버가 볼 수 없다. */
    el("f-dept").innerHTML = DEPARTMENTS.map(function (d) {
      return '<option value="' + d.department_id + '">' + esc(d.name) + "</option>";
    }).join("");
    el("f-doctor").innerHTML = DOCTORS.map(function (d) {
      return '<option value="' + d.doctor_id + '">' + esc(d.name) + "</option>";
    }).join("");

    /* 문자가 나가지 않는 상태면 목록 위에 붙인다. 등록은 되지만 발송이 밀린다.
       TODO(KEY-57) 설정 API 가 생기면 GET /api/v1/settings/sender 로 갈아 끼운다.
       지금은 ?sender=none 으로 그 상태를 볼 수 있다. */
    var sender = new URLSearchParams(location.search).get("sender");
    if (sender !== null) sessionStorage.setItem("mockSender", sender);
    document.getElementById("sender-banner").hidden = sessionStorage.getItem("mockSender") !== "none";
  });
})();
