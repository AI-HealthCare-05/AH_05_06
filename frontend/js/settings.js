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
    return String(text === null || text === undefined ? "" : text).replace(
      /[&<>"']/g,
      function (c) {
        return {
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        }[c];
      },
    );
  };

  var sets = [];
  var picked = null; // 고른 세트의 상세
  var pickedId = null;
  var canEdit = false;
  var saying = "";
  var loadSeq = 0;

  /* **오른쪽에 설 수 있는 것이 둘이다** — 고른 처방(D2-3)이거나 「그 밖에」의
     한 묶음(지금은 문자 문구 D2-5 하나). 처방 번호와 묶음 이름을 한 변수에
     섞지 않는다: 섞으면 「3 번 처방」과 「sms」가 같은 칸에 들어가 어느
     쪽인지 매번 되물어야 한다. */
  var group = null; // null 이면 처방을 보고 있다
  var templates = null; // 문자 문구 판
  var drafts = {}; // 아직 저장 안 한 문구 — 다시 그려도 친 값이 남아야 한다

  /* ── 왼쪽 레일 ─────────────────────────────────────────────────── */

  /* 갈래 머리 — 원문 레일의 큰 글씨. 갈래가 셋뿐이라 눈이 먼저 여기 걸려야
     「무엇을 고르는 화면인지」가 보인다. */
  function sectionHtml(title, count) {
    return (
      '<div class="rail__section"><span class="rail__section-name">' +
      esc(title) +
      "</span>" +
      (count == null ? "" : '<span class="rail__count">' + count + "</span>") +
      "</div>"
    );
  }

  function groupRowHtml(row) {
    /* **만든 묶음만 눌린다.** 아직 없는 것은 자리를 세우되 눌리지 않게 둔다 —
       눌러도 아무 일 없는 줄은 「된다」고 말한다. */
    if (!RAIL_GROUP_READY[row.key]) {
      return (
        '<div class="rail__soon"><span class="rail__name">' +
        esc(row.title) +
        '</span><span class="rail__note">' +
        esc(row.note) +
        "</span></div>"
      );
    }
    return (
      '<button class="rail__row' +
      (group === row.key ? " is-on" : "") +
      '" type="button" data-group="' +
      esc(row.key) +
      '"><span class="rail__name">' +
      esc(row.title) +
      "</span></button>"
    );
  }

  function railHtml() {
    /* **거르개를 두지 않는다.** 처방이 아홉이라 한 화면에 다 서고, 검색칸이
       있으면 「검색해야 보이나」로 읽힌다. 환자 목록과는 다른 자리다. */
    var rx = setsByDisease(sets)
      .map(function (block) {
        return (
          '<div class="rail__disease"><span class="rail__name">' +
          esc(block.title) +
          '</span><span class="rail__count">' +
          block.sets.length +
          "</span></div>" +
          block.sets
            .map(function (row) {
              return (
                '<button class="rail__row' +
                (row.prescription_set_id === pickedId ? " is-on" : "") +
                '" type="button" data-set="' +
                row.prescription_set_id +
                '"><span class="rail__name">' +
                esc(row.name) +
                "</span></button>"
              );
            })
            .join("")
        );
      })
      .join("");

    return (
      sectionHtml("안내문") +
      groupsIn("guide").map(groupRowHtml).join("") +
      sectionHtml("처방", sets.length) +
      (rx || '<p class="rail__none">처방이 없습니다</p>') +
      sectionHtml("기타") +
      groupsIn("rest").map(groupRowHtml).join("")
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
            '" aria-label="삭제"' +
            (canEdit ? "" : " disabled") +
            ">✕</button>" +
            "</div>"
          );
        })
        .join("") +
      (rows.length ? "" : '<p class="fld__hint">등록된 약이 없습니다</p>') +
      '<button class="button-ghost button-ghost--sm" type="button" id="drug-add"' +
      (canEdit ? "" : " disabled") +
      ">+ 약 추가</button>"
    );
  }

  /* 문자 문구 한 칸 — 원문 D2-5 의 블록 하나.
     「진료 안내문 (링크) / 단문 · 84바이트 / 원본으로 되돌리기」 */
  function templateCardHtml(item) {
    var body = drafts[item.kind] != null ? drafts[item.kind] : item.body;
    var len = smsLength(body);
    var problem = templateProblem(item, body, templates.known_variables);
    var note = TEMPLATE_NOTE[item.kind];
    return (
      '<section class="box"><div class="box__head"><h2 class="box__title">' +
      esc(templateSaying(item.kind)) +
      '</h2><span class="grow"></span><span class="box__note' +
      (len.long ? " box__note--warn" : "") +
      '">' +
      esc(len.say) +
      "</span>" +
      (item.is_default
        ? ""
        : '<button class="button-ghost button-ghost--sm" type="button" data-revert="' +
          esc(item.kind) +
          '"' +
          (canEdit ? "" : " disabled") +
          ">원본으로 되돌리기</button>") +
      "</div>" +
      '<textarea class="modal__input sms__body" rows="2" data-body="' +
      esc(item.kind) +
      '"' +
      (canEdit ? "" : " disabled") +
      ">" +
      esc(body) +
      "</textarea>" +
      (problem ? '<p class="sms__problem">' + esc(problem) + "</p>" : "") +
      (note ? '<p class="note">ⓘ ' + esc(note) + "</p>" : "") +
      "</section>"
    );
  }

  function templatesHtml() {
    if (!templates) return '<p class="note">불러오는 중…</p>';
    return (
      '<div class="patient-head"><span class="patient-head__name">문자 문구</span>' +
      '<span class="grow"></span>' +
      (saying ? '<span class="box__note">' + esc(saying) + "</span>" : "") +
      (canEdit
        ? ""
        : '<span class="box__note">의사 계정만 수정할 수 있습니다</span>') +
      '<button class="button-primary button-primary--sm" type="button" id="sms-save"' +
      (canEdit ? "" : " disabled") +
      ">저장</button></div>" +
      '<p class="note">ⓘ {변수}는 발송 시 치환됩니다 · ' +
      SMS_LIMIT +
      "바이트를 넘으면 장문(LMS)으로 단가가 오릅니다</p>" +
      templates.items.map(templateCardHtml).join("") +
      /* 고칠 수 없는 문자도 보인다 — 무엇이 나가는지는 알아야 한다. */
      '<section class="box"><div class="box__head"><h2 class="box__title">인증번호</h2>' +
      '<span class="grow"></span><span class="box__note">수정 불가 · 시스템</span></div>' +
      '<p class="sms__fixed">' +
      esc(templates.system_body) +
      "</p></section>" +
      '<p class="note">ⓘ 바뀐 문구는 다음 발송부터 적용됩니다</p>'
    );
  }

  function detailHtml() {
    if (group === "sms") return templatesHtml();
    if (!picked) {
      return '<p class="note">처방을 선택하면 상세 설정이 표시됩니다</p>';
    }

    return (
      '<div class="patient-head"><span class="patient-head__name">' +
      esc(picked.name) +
      "</span>" +
      '<span class="grow"></span>' +
      (saying ? '<span class="box__note">' + esc(saying) + "</span>" : "") +
      (canEdit
        ? ""
        : '<span class="box__note">의사 계정만 수정할 수 있습니다</span>') +
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
        "표기 방식",
        [
          ["PACK", DAYS_MODE_LABELS.PACK],
          ["DAYS", DAYS_MODE_LABELS.DAYS],
        ],
        picked.days_mode,
      ) +
      (picked.days_mode === "PACK"
        ? textHtml(
            "f-days-per-pack",
            "1통 기준 일수",
            picked.days_per_pack,
            "이 값으로 총 처방일수를 계산합니다",
          )
        : "") +
      "</div>" +
      '<p class="fld__hint">ⓘ 소진 예정일과 소진 임박 문자가 이 값으로 계산됩니다</p></section>' +
      /* ③ 확인 항목 — 판독 화면에 그대로 뜬다 */
      '<section class="box"><div class="box__head"><h2 class="box__title">확인 항목</h2></div>' +
      '<div class="checks-grid">' +
      CHECK_ITEMS.map(function (key) {
        return checkHtml(
          "f-check-" + key,
          checkItemLabel(key),
          (picked.check_items || []).indexOf(key) !== -1,
        );
      }).join("") +
      "</div>" +
      '<p class="fld__hint">ⓘ 판독 결과 확인 화면에 체크 목록으로 표시됩니다 · 선택 시 해당 주의 문구가 안내문에 추가됩니다</p></section>' +
      /* ④ 자동 발송 기본값 */
      '<section class="box"><div class="box__head"><h2 class="box__title">자동 발송 기본값</h2></div>' +
      '<div class="checks-grid">' +
      '<label class="chk"><input type="checkbox" checked disabled />일주일 뒤 <span class="fld__hint">(고정)</span></label>' +
      checkHtml("f-d15", "보름 뒤", picked.check_d15_on) +
      checkHtml("f-d30", "한 달 뒤", picked.check_d30_on) +
      checkHtml("f-runout", "소진 임박 안내", picked.run_out_on) +
      "</div>" +
      (picked.run_out_on
        ? textHtml("f-runout-days", "소진 N일 전", picked.run_out_before_days)
        : "") +
      '<p class="fld__hint">ⓘ 이 처방 선택 시 기본값으로 적용됩니다 · 환자별 설정은 문자 설정에서 변경합니다</p></section>' +
      /* ⑤ 그 밖에 */
      '<section class="box"><div class="box__head"><h2 class="box__title">그 밖에</h2></div>' +
      '<div class="cols2">' +
      textHtml(
        "f-emr",
        "EMR 표시 코드",
        picked.emr_code,
        "이 코드가 기록된 진료를 안내 대상으로 인식합니다",
      ) +
      textHtml(
        "f-revisit",
        "재진 안내",
        picked.revisit_note,
        "진료기록 소견에 다른 조건이 기재된 경우 해당 조건을 우선 적용합니다",
      ) +
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
        el("rail").innerHTML =
          '<p class="rail__none">처방 목록을 불러오지 못했습니다</p>';
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
        el("detail").innerHTML =
          '<p class="note">처방을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</p>';
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
      run_out_before_days: el("f-runout-days")
        ? Number(el("f-runout-days").value) || 3
        : 3,
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
        saying = "저장되었습니다";
        render();
        loadSets(); // 이름이 바뀌었으면 레일도 따라간다
      })
      .catch(function (err) {
        if (pickedId !== wanted) return;
        saying =
          err && err.code === "DAYS_PER_PACK_REQUIRED"
            ? "1통 기준 일수를 입력해 주세요"
            : err && err.status === 403
              ? "의사 계정만 수정할 수 있습니다"
              : "저장하지 못했습니다. 잠시 후 다시 시도해 주세요";
        render();
      });
  }

  /* ── 문자 문구 (D2-5) ──────────────────────────────────────────── */

  function openTemplates() {
    group = "sms";
    pickedId = null;
    picked = null;
    saying = "";
    drafts = {};
    render();
    return catalogApi
      .templates()
      .then(function (data) {
        if (group !== "sms") return; // 그 사이 처방으로 옮겨 갔으면 붙이지 않는다
        templates = data;
        render();
      })
      .catch(function () {
        if (group !== "sms") return;
        el("detail").innerHTML =
          '<p class="note">문자 문구를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</p>';
      });
  }

  /* 화면에 적힌 것을 거둔다. **다시 그리기 전에 부른다** — 안 그러면 치던
     값이 날아간다(처방 저장에서 한 번 겪은 자리다). */
  function draftsNow() {
    var found = {};
    var boxes = document.querySelectorAll("[data-body]");
    for (var i = 0; i < boxes.length; i++) {
      found[boxes[i].getAttribute("data-body")] = boxes[i].value;
    }
    return found;
  }

  function saveTemplates() {
    drafts = draftsNow();
    /* **하나라도 막히면 아무것도 안 보낸다.** 반만 저장되면 어느 것이
       들어갔는지 화면이 말할 수 없다. */
    for (var i = 0; i < templates.items.length; i++) {
      var item = templates.items[i];
      var problem = templateProblem(
        item,
        drafts[item.kind],
        templates.known_variables,
      );
      if (problem) {
        saying = problem;
        return render();
      }
    }

    var changed = templates.items.filter(function (item) {
      return (
        drafts[item.kind] != null && drafts[item.kind].trim() !== item.body
      );
    });
    if (!changed.length) {
      saying = "바뀐 문구가 없습니다";
      return render();
    }

    saying = "저장하는 중…";
    render();
    var one = function (index) {
      if (index >= changed.length) {
        drafts = {};
        saying = "저장되었습니다";
        return render();
      }
      return catalogApi
        .saveTemplate(changed[index].kind, drafts[changed[index].kind].trim())
        .then(function (data) {
          templates = data;
          return one(index + 1);
        });
    };
    one(0).catch(function (err) {
      saying =
        err && err.status === 403
          ? "의사 계정만 수정할 수 있습니다"
          : "저장하지 못했습니다. 잠시 후 다시 시도해 주세요";
      render();
    });
  }

  function revertTemplate(kind) {
    drafts = draftsNow();
    delete drafts[kind];
    saying = "";
    render();
    catalogApi
      .resetTemplate(kind)
      .then(function (data) {
        templates = data;
        render();
      })
      .catch(function () {
        saying = "되돌리지 못했습니다. 잠시 후 다시 시도해 주세요";
        render();
      });
  }

  /* ── 손짓 ──────────────────────────────────────────────────────── */

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target.closest) return;

    var row = target.closest("[data-set]");
    if (row) {
      group = null;
      templates = null;
      return loadSet(Number(row.getAttribute("data-set")));
    }

    var chosenGroup = target.closest("[data-group]");
    if (chosenGroup && chosenGroup.getAttribute("data-group") === "sms")
      return openTemplates();

    if (target.closest("#sms-save")) return saveTemplates();
    var revert = target.closest("[data-revert]");
    if (revert) return revertTemplate(revert.getAttribute("data-revert"));

    if (target.closest("#set-save")) return save();

    if (target.closest("#drug-add")) {
      picked.drugs = (picked.drugs || []).concat([
        { name: "", frequency: "", note: "" },
      ]);
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

  /* 치는 동안 바이트 수와 막는 까닭이 따라 움직인다 — 다 치고 저장을 눌러야
     아는 것보다 낫다. 커서가 튀지 않게 **그 칸만 두고** 나머지를 다시 그린다. */
  document.addEventListener("input", function (event) {
    if (!event.target.hasAttribute || !event.target.hasAttribute("data-body"))
      return;
    var kind = event.target.getAttribute("data-body");
    drafts[kind] = event.target.value;
    var card = event.target.closest(".box");
    var item = templates.items.filter(function (row) {
      return row.kind === kind;
    })[0];
    var len = smsLength(event.target.value);
    var mark = card.querySelector(".box__note");
    if (mark) {
      mark.textContent = len.say;
      mark.className = "box__note" + (len.long ? " box__note--warn" : "");
    }
    var problem = templateProblem(
      item,
      event.target.value,
      templates.known_variables,
    );
    var said = card.querySelector(".sms__problem");
    if (problem && !said) {
      said = document.createElement("p");
      said.className = "sms__problem";
      event.target.parentNode.insertBefore(said, event.target.nextSibling);
    }
    if (said) {
      said.textContent = problem;
      said.hidden = !problem;
    }
  });

  requireSession().then(function (who) {
    el("who-name").textContent = who.name;
    el("who-roles").textContent = roleLabel(who.roles);
    canEdit = (who.roles || []).indexOf("doctor") !== -1;
    return loadSets();
  });
})();
