/* 설정 화면 — 와이어프레임 D2-3 「처방」.
 *
 * 왼쪽 레일에서 처방을 고르면 오른쪽에 그 세트가 펼쳐진다. 고치는 것은 **의사만**
 * 이다(D2-2 「의사 계정만 · 스탭은 볼 수만 있다」) — 이 값이 안내문과 문자
 * 발송일을 정하므로 의료 판단에 걸린다. 화면에서 잠그는 것은 편의일 뿐이고
 * 실제 차단은 서버가 한다.
 *
 * 순수 규칙은 `js/settings-rail.js` 가 갖는다 — 검사가 부를 수 있게.
 */
(function () {
  /* **자기 칸이 없는 화면에서는 아무것도 하지 않는다.** */
  if (!document.getElementById("rail")) return;

  var el = function (id) {
    return document.getElementById(id);
  };
  var esc = function (text) {
    return String(text === null || text === undefined ? "" : text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  var sets = [];
  var picked = null; // 고른 세트의 상세
  var pickedId = null;
  var canEdit = false;
  var saying = "";
  var query = "";
  var loadSeq = 0;

  /* ── 왼쪽 레일 ─────────────────────────────────────────────────── */

  function railHtml() {
    var shown = filterSets(sets, query);

    var rx = setsByDisease(shown)
      .map(function (group) {
        return (
          '<div class="rail__group"><span class="rail__name">' +
          esc(group.title) +
          '</span><span class="rail__count">' +
          group.sets.length +
          "</span></div>" +
          group.sets
            .map(function (row) {
              return (
                '<button class="rail__row' +
                (row.prescription_set_id === pickedId ? " is-on" : "") +
                '" type="button" data-set="' +
                row.prescription_set_id +
                '">' +
                esc(row.name) +
                "</button>"
              );
            })
            .join("")
        );
      })
      .join("");

    return (
      '<div class="rail__head"><span class="rail__name">처방</span>' +
      '<span class="rail__count">' +
      shown.length +
      "</span></div>" +
      (rx || '<p class="rail__none">찾는 처방이 없습니다</p>') +
      /* 아직 없는 묶음. **자리는 세우고 없다고 적는다** — 빈 채로 두면 다음
         사람이 무엇을 만들어야 하는지 모르고, 채워 두면 되는 것처럼 보인다. */
      '<div class="rail__head rail__head--rest"><span class="rail__name">그 밖에</span></div>' +
      RAIL_GROUPS.map(function (group) {
        return (
          '<div class="rail__soon"><span class="rail__name">' +
          esc(group.title) +
          '</span><span class="rail__note">' +
          esc(group.note) +
          "</span></div>"
        );
      }).join("")
    );
  }

  /* ── 오른쪽 상세 ───────────────────────────────────────────────── */

  function pickHtml(id, label, options, value) {
    return (
      '<label class="fld"><span class="fld__label">' +
      esc(label) +
      '</span><select class="fld__input" id="' +
      id +
      '"' +
      (canEdit ? "" : " disabled") +
      ">" +
      options
        .map(function (opt) {
          return (
            '<option value="' +
            esc(opt[0]) +
            '"' +
            (opt[0] === value ? " selected" : "") +
            ">" +
            esc(opt[1]) +
            "</option>"
          );
        })
        .join("") +
      "</select></label>"
    );
  }

  function textHtml(id, label, value, hint) {
    return (
      '<label class="fld"><span class="fld__label">' +
      esc(label) +
      '</span><input class="fld__input" type="text" id="' +
      id +
      '" value="' +
      esc(value || "") +
      '"' +
      (canEdit ? "" : " disabled") +
      " />" +
      (hint ? '<span class="fld__hint">' + esc(hint) + "</span>" : "") +
      "</label>"
    );
  }

  function checkHtml(id, label, on) {
    return (
      '<label class="chk"><input type="checkbox" id="' +
      id +
      '"' +
      (on ? " checked" : "") +
      (canEdit ? "" : " disabled") +
      " />" +
      esc(label) +
      "</label>"
    );
  }

  function drugsHtml() {
    var rows = picked.drugs || [];
    return (
      rows
        .map(function (drug, i) {
          return (
            '<div class="drug" data-drug="' +
            i +
            '">' +
            '<input class="fld__input drug__name" type="text" value="' +
            esc(drug.name) +
            '" placeholder="비잔정 2mg" aria-label="약 이름"' +
            (canEdit ? "" : " disabled") +
            " />" +
            '<input class="fld__input drug__freq" type="text" value="' +
            esc(drug.frequency) +
            '" placeholder="1일 1회" aria-label="복용 횟수"' +
            (canEdit ? "" : " disabled") +
            " />" +
            '<input class="fld__input drug__note" type="text" value="' +
            esc(drug.note) +
            '" placeholder="매일 같은 시간" aria-label="복용 방법"' +
            (canEdit ? "" : " disabled") +
            " />" +
            '<button class="drug__drop" type="button" data-drop="' +
            i +
            '" aria-label="이 약 빼기"' +
            (canEdit ? "" : " disabled") +
            ">✕</button>" +
            "</div>"
          );
        })
        .join("") +
      (rows.length ? "" : '<p class="fld__hint">아직 적힌 약이 없습니다</p>') +
      '<button class="button-ghost button-ghost--sm" type="button" id="drug-add"' +
      (canEdit ? "" : " disabled") +
      ">+ 약 추가</button>"
    );
  }

  function detailHtml() {
    if (!picked) {
      return '<p class="note">왼쪽에서 처방을 고르면 그 처방의 설정이 여기에 펼쳐집니다</p>';
    }

    return (
      '<div class="patient-head"><span class="patient-head__name">' +
      esc(picked.name) +
      "</span>" +
      '<span class="grow"></span>' +
      (saying ? '<span class="box__note">' + esc(saying) + "</span>" : "") +
      (canEdit ? "" : '<span class="box__note">의사 계정만 고칠 수 있습니다</span>') +
      '<button class="button-primary button-primary--sm" type="button" id="set-save"' +
      (canEdit ? "" : " disabled") +
      ">저장</button></div>" +
      /* ① 무엇인가 */
      '<section class="box"><div class="box__head"><h2 class="box__title">처방</h2></div>' +
      '<div class="cols2">' +
      textHtml("f-name", "이름", picked.name) +
      pickHtml(
        "f-disease",
        "질환",
        [
          ["ENDOMETRIOSIS", diseaseLabel("ENDOMETRIOSIS")],
          ["PCOS", diseaseLabel("PCOS")],
        ],
        picked.disease,
      ) +
      pickHtml(
        "f-phase",
        "적용 시점",
        [
          ["FIRST", phaseLabel("FIRST")],
          ["CONTINUE", phaseLabel("CONTINUE")],
          ["REST", phaseLabel("REST")],
        ],
        picked.phase,
      ) +
      "</div>" +
      '<div class="drugs">' +
      '<span class="fld__label">처방 약</span>' +
      drugsHtml() +
      "</div></section>" +
      /* ② 처방 일수 — 소진 예정일이 이 값으로 셈해진다 */
      '<section class="box"><div class="box__head">' +
      '<h2 class="box__title">처방 일수 표기 방식</h2>' +
      '<span class="box__note">EMR 「총투」 칸의 의미</span></div>' +
      '<div class="cols2">' +
      pickHtml(
        "f-days-mode",
        "세는 방법",
        [
          ["PACK", DAYS_MODE_LABELS.PACK],
          ["DAYS", DAYS_MODE_LABELS.DAYS],
        ],
        picked.days_mode,
      ) +
      (picked.days_mode === "PACK"
        ? textHtml("f-days-per-pack", "1통 = 며칠", picked.days_per_pack, "이 값을 곱해 처방일수를 셈합니다")
        : "") +
      "</div>" +
      '<p class="fld__hint">ⓘ 소진 예정일과 소진 임박 문자가 이 값으로 계산됩니다</p></section>' +
      /* ③ 확인 항목 — 판독 화면에 그대로 뜬다 */
      '<section class="box"><div class="box__head"><h2 class="box__title">확인 항목</h2></div>' +
      '<div class="checks-grid">' +
      CHECK_ITEMS.map(function (key) {
        return checkHtml("f-check-" + key, checkItemLabel(key), (picked.check_items || []).indexOf(key) !== -1);
      }).join("") +
      "</div>" +
      '<p class="fld__hint">ⓘ 판독 결과 확인 화면(S1-6)에 체크 목록으로 뜹니다</p></section>' +
      /* ④ 자동 발송 기본값 */
      '<section class="box"><div class="box__head"><h2 class="box__title">자동 발송 기본값</h2></div>' +
      '<div class="checks-grid">' +
      '<label class="chk"><input type="checkbox" checked disabled />일주일 뒤 <span class="fld__hint">(고정)</span></label>' +
      checkHtml("f-d15", "보름 뒤", picked.check_d15_on) +
      checkHtml("f-d30", "한 달 뒤", picked.check_d30_on) +
      checkHtml("f-runout", "소진 임박 안내", picked.run_out_on) +
      "</div>" +
      (picked.run_out_on
        ? textHtml("f-runout-days", "소진 며칠 전", picked.run_out_before_days)
        : "") +
      '<p class="fld__hint">ⓘ 이 처방을 고르면 기본값으로 적용됩니다 · 환자별로는 S1-14 에서 바꿉니다</p></section>' +
      /* ⑤ 그 밖에 */
      '<section class="box"><div class="box__head"><h2 class="box__title">그 밖에</h2></div>' +
      '<div class="cols2">' +
      textHtml("f-emr", "EMR 표시 코드", picked.emr_code, "이 코드가 적힌 진료를 안내 대상으로 봅니다") +
      textHtml("f-revisit", "재진 안내", picked.revisit_note, "소견에 다른 조건이 있으면 그쪽이 우선합니다") +
      "</div></section>"
    );
  }

  function render() {
    el("rail").innerHTML = railHtml();
    el("detail").innerHTML = detailHtml();
  }

  /* ── 읽고 쓰기 ─────────────────────────────────────────────────── */

  function loadSets() {
    return catalogApi
      .sets()
      .then(function (rows) {
        sets = rows || [];
        render();
      })
      .catch(function () {
        sets = [];
        el("rail").innerHTML = '<p class="rail__none">처방 목록을 불러오지 못했습니다</p>';
      });
  }

  function loadSet(id) {
    var mine = ++loadSeq;
    pickedId = id;
    picked = null;
    saying = "";
    render();

    catalogApi
      .set(id)
      .then(function (data) {
        if (mine !== loadSeq) return; // 늦게 온 답이 다른 처방 화면에 붙으면 안 된다
        picked = data;
        render();
      })
      .catch(function () {
        if (mine !== loadSeq) return;
        el("detail").innerHTML = '<p class="note">처방을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.</p>';
      });
  }

  /** 화면에 적힌 것을 서버가 받는 모양으로. **한 판을 통째로** 보낸다. */
  function planNow() {
    var drugs = [];
    document.querySelectorAll("[data-drug]").forEach(function (row) {
      drugs.push({
        name: row.querySelector(".drug__name").value,
        frequency: row.querySelector(".drug__freq").value,
        note: row.querySelector(".drug__note").value,
      });
    });

    var items = [];
    CHECK_ITEMS.forEach(function (key) {
      var box = el("f-check-" + key);
      if (box && box.checked) items.push(key);
    });

    var mode = el("f-days-mode").value;
    var per = el("f-days-per-pack");

    return {
      name: el("f-name").value.trim(),
      disease: el("f-disease").value,
      phase: el("f-phase").value,
      days_mode: mode,
      days_per_pack: mode === "PACK" && per ? Number(per.value) || null : null,
      emr_code: el("f-emr").value,
      revisit_note: el("f-revisit").value,
      check_d15_on: el("f-d15").checked,
      check_d30_on: el("f-d30").checked,
      run_out_on: el("f-runout").checked,
      run_out_before_days: el("f-runout-days") ? Number(el("f-runout-days").value) || 3 : 3,
      drugs: drugs,
      check_items: items,
    };
  }

  function save() {
    if (!picked || !canEdit) return;
    var wanted = pickedId;

    /* **화면에 적힌 것을 먼저 거둔다.** 다시 그리면 `picked` 로 되돌아가는데,
       저장이 막히면(한 통이 며칠인지 안 적었을 때) 방금 친 값이 통째로
       날아간다 — 고치라는 말을 듣고 보니 고칠 것이 사라진 꼴이다. */
    var plan = planNow();
    picked = Object.assign({}, picked, plan);

    saying = "저장하는 중…";
    render();

    catalogApi
      .saveSet(wanted, plan)
      .then(function (data) {
        if (pickedId !== wanted) return;
        /* **서버가 돌려준 것을 화면으로 삼는다** — 서버가 고쳐 준 값(일수로
           바꾸면 통 크기를 비운다)이 화면에 안 보이면 안 된다. */
        picked = data;
        saying = "저장했습니다";
        render();
        loadSets(); // 이름이 바뀌었으면 레일도 따라간다
      })
      .catch(function (err) {
        if (pickedId !== wanted) return;
        saying =
          err && err.code === "DAYS_PER_PACK_REQUIRED"
            ? "한 통이 며칠치인지 적어 주세요"
            : err && err.status === 403
              ? "의사 계정만 고칠 수 있습니다"
              : "저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요";
        render();
      });
  }

  /* ── 손짓 ──────────────────────────────────────────────────────── */

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target.closest) return;

    var row = target.closest("[data-set]");
    if (row) return loadSet(Number(row.getAttribute("data-set")));

    if (target.closest("#set-save")) return save();

    if (target.closest("#drug-add")) {
      picked.drugs = (picked.drugs || []).concat([{ name: "", frequency: "", note: "" }]);
      return render();
    }

    var drop = target.closest("[data-drop]");
    if (drop) {
      /* 지우기 전에 화면에 적힌 것을 거둔다 — 안 그러면 치던 값이 날아간다 */
      var kept = planNow();
      kept.drugs.splice(Number(drop.getAttribute("data-drop")), 1);
      picked = Object.assign({}, picked, kept);
      return render();
    }
  });

  /* 세는 방법과 소진 임박은 **켜면 칸이 따라 나온다** — 다시 그려야 보인다 */
  document.addEventListener("change", function (event) {
    var id = event.target.id;
    if (id !== "f-days-mode" && id !== "f-runout") return;
    picked = Object.assign({}, picked, planNow());
    render();
  });

  el("set-search").addEventListener("input", function () {
    query = this.value;
    el("rail").innerHTML = railHtml();
  });

  requireSession().then(function (who) {
    el("who-name").textContent = who.name;
    el("who-roles").textContent = roleLabel(who.roles);
    canEdit = (who.roles || []).indexOf("doctor") !== -1;
    return loadSets();
  });
})();
