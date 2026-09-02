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

  /* **처방 설정(D2-3)은 지금 읽기 전용이다.**
   *
   * `prescription_set` 표에는 `hospital_id` 가 없다 — 여덟 처방 유형을 **전
   * 의원이 함께 쓴다**(`app/models/catalog.py`). 그래서 여기서 저장을 열면
   * 어느 의원 의사든 다른 모든 의원의 질환 분류 · 총투 해석 · 소진 예정일
   * 셈법을 바꾸게 된다. 그 값들이 안내문 문구와 문자 발송일을 정한다.
   *
   * 2heej 님이 `#183` 리뷰에서 찾아 주셨다. 표를 의원별로 가르는 것이 옳은
   * 해결인데 씨앗 데이터 · 이름 unique · 기존 참조를 다 손봐야 해서 별도
   * 일감으로 뺀다. **그때까지는 열지 않는다** — 고칠 수 있는 것처럼 보이는
   * 화면이 조용히 남의 의원 것을 바꾸는 것보다, 못 고치는 편이 낫다.
   *
   * 나머지 설정(D2-4 기준선 · D2-5 문자 문구 · 안내 문구)은 의원별로 갈려
   * 있어 그대로 고칠 수 있다. 그래서 `canEdit` 과 따로 둔다.
   */
  var canEditSet = false;
  var saying = "";
  var loadSeq = 0;

  /* **오른쪽에 설 수 있는 것이 둘이다** — 고른 처방(D2-3)이거나 「그 밖에」의
     한 묶음(지금은 문자 문구 D2-5 하나). 처방 번호와 묶음 이름을 한 변수에
     섞지 않는다: 섞으면 「3 번 처방」과 「sms」가 같은 칸에 들어가 어느
     쪽인지 매번 되물어야 한다. */
  var group = null; // null 이면 처방을 보고 있다
  var templates = null; // 문자 문구 판
  var baselines = null; // 검사 기준선 판
  var copy = null; // 안내문 문구 판
  var copyPick = null; // 안내문에서 고른 한 장
  /* **펼친 묶음은 늘 하나다.**
   *
   * 원문 D2-3 주석: 「9개가 늘 다 펼쳐져 있으면 왼쪽이 길어져 「그 밖에」가
   * 화면 밖으로 밀린다」. 실제로 재 봤다 — 넷 다 펼치면 내용이 937px 이고
   * 보이는 높이는 689px 이라 「기타」 세 줄이 통째로 밀려난다. 한 묶음만
   * 펼치면 546.5px 로 다 보인다. 원문 다섯 프레임이 전부 그 상태다.
   *
   * 열쇠에 갈래를 함께 담는다(`"guide|ENDOMETRIOSIS"`). 갈래별로 통을 나눠
   * 두었던 것은 두 갈래에 같은 질환이 있어 한 통에 담으면 같이 접히기
   * 때문인데, 열쇠에 갈래가 들어 있으면 그 일이 안 난다. */
  var opened = null;
  var who = null; // 로그인한 사람 — 문구가 누구 이름으로 나가는지 적는다
  var whose = null; // 누구 기준 — 비면 의원 공통
  var drafts = {}; // 아직 저장 안 한 문구 — 다시 그려도 친 값이 남아야 한다

  /* ── 왼쪽 레일 ─────────────────────────────────────────────────── */

  /* 갈래 머리 — **눌리지 않는 이름표다.** 개수를 이름 바로 옆에 붙인다:
     오른쪽 끝으로 밀면 「오른쪽에 표시를 단 줄」이 되어, 아무 일도 안 하는
     것이 화면에서 제일 눌러 보고 싶게 생긴다. */
  function sectionHtml(title, count) {
    return (
      '<div class="rail__section"><span class="rail__section-name">' +
      esc(title) +
      "</span>" +
      (count == null
        ? ""
        : '<span class="rail__section-count">' + esc(count) + "</span>") +
      "</div>"
    );
  }

  /* **모든 줄이 화살표 칸을 하나씩 갖는다.** 원문 D2-3 은 자식 줄에도 기타
     줄에도 `width:10px` 칸을 달아 두었다 — 칸이 없는 줄만 이름이 한 단 왼쪽
     으로 나가서 나무가 평평해진다. 나중에 줄에 표시를 넣을 자리이기도 하다. */
  var RAIL_MARK = '<span class="rail__mark" aria-hidden="true"></span>';

  function groupRowHtml(row) {
    /* **만든 묶음만 눌린다.** 아직 없는 것은 자리를 세우되 눌리지 않게 둔다 —
       눌러도 아무 일 없는 줄은 「된다」고 말한다. 글자색 한 단만으로는 옆줄과
       훑어서 구별이 안 돼서, 어디로 가야 하는지를 점선 칩으로 적는다. */
    if (!RAIL_GROUP_READY[row.key]) {
      return (
        '<div class="rail__soon">' +
        RAIL_MARK +
        '<span class="rail__name">' +
        esc(row.title) +
        '</span><span class="rail__note rail__note--soon">' +
        esc(row.note) +
        "</span></div>"
      );
    }
    var on = group === row.key;
    return (
      '<button class="rail__row' +
      (on ? " is-on" : "") +
      '" type="button"' +
      /* 고름을 낭독기에도 알린다 — 지금까지 CSS 클래스뿐이라 눈으로만 보였다.
         환자 목록(`shell.js` 의 `rowHtml`)·어드민은 이미 붙인다. */
      (on ? ' aria-current="true"' : "") +
      ' data-group="' +
      esc(row.key) +
      '">' +
      RAIL_MARK +
      '<span class="rail__name">' +
      esc(row.title) +
      "</span></button>"
    );
  }

  /* 묶음 한 덩이 — 머리 + 자식 통.
   *
   * **접힌 자식을 지우지 않고 감춘다.** 지금은 `open ? … : ""` 로 존재 자체를
   * 없앤다 — 그러면 `aria-controls` 가 가리킬 것이 없고, 화살표가 매번 새
   * 노드라 회전이 한 프레임도 안 보이고, 다시 그릴 때 초점이 <body> 로
   * 떨어진다. `[hidden]` 은 `style.css` 가 `display:none !important` 로 못박아
   * 두었으므로 Tab 차례에서도 빠진다. 늘 그려도 여덟 줄이다.
   *
   * 판독 화면의 「그 자리에서 올리기」 판(`ocr-review.js` 의 `openPanel`)이
   * 쓰는 짝을 그대로 따른다: `aria-expanded` + `aria-controls` + `hidden`.
   */
  function railGroupHtml(section, block, drawRow, count) {
    var key = railFoldKey(section, block.key);
    var open = opened === key;
    /* 갈래를 id 에도 넣는다 — 안내문과 처방에 같은 질환이 있어서 묶음 열쇠만
       으로는 id 가 겹친다. */
    var kids = "rail-kids-" + section + "-" + block.key;

    return (
      '<div class="rail__branch' +
      (open ? " is-open" : "") +
      '"><button class="rail__disease" type="button" data-fold="' +
      esc(key) +
      '" aria-expanded="' +
      (open ? "true" : "false") +
      '" aria-controls="' +
      esc(kids) +
      '">' +
      /* 화살표는 모양이지 뜻이 아니다 — 상태는 `aria-expanded` 가 말한다.
         숨기지 않으면 「검은 오른쪽 삼각형, 자궁내막증, 3, 접힘, 버튼」으로
         두 번 읽힌다. */
      '<span class="rail__mark" aria-hidden="true">▶</span>' +
      '<span class="rail__name">' +
      esc(block.title) +
      '</span><span class="rail__count' +
      (count.done ? " rail__count--done" : "") +
      '">' +
      esc(count.say) +
      "</span></button>" +
      '<div class="rail__kids" id="' +
      esc(kids) +
      '"' +
      (open ? "" : " hidden") +
      ">" +
      block.sets
        .map(function (row) {
          /* **`.map(drawRow)` 로 넘기지 않는다** — 그러면 둘째 인자로 차례
             번호가 들어가서, 받는 쪽이 묶음인 줄 알고 이름을 못 줄인다. */
          return drawRow(row, block);
        })
        .join("") +
      "</div></div>"
    );
  }

  /* 안내문 한 장. 이름은 **보이는 것만** 줄인다(§4). 전체 이름은 `title` 에
     남긴다 — 320px 에서 잘렸을 때 확인할 곳이 필요하다. */
  function copyRailRow(row, block) {
    var mark = copyRailMark(copy, row.prescription_set_id);
    var on = row.prescription_set_id === copyPick;
    return (
      '<button class="rail__row' +
      (on ? " is-on" : "") +
      '" type="button"' +
      (on ? ' aria-current="true"' : "") +
      ' data-copy-set="' +
      row.prescription_set_id +
      '" title="' +
      esc(row.name) +
      '">' +
      RAIL_MARK +
      '<span class="rail__name">' +
      esc(railSetName(block, row.name)) +
      '</span><span class="rail__note' +
      (mark.done ? " rail__note--done" : mark.say ? " rail__note--todo" : "") +
      '">' +
      esc(mark.say) +
      "</span></button>"
    );
  }

  function setRailRow(row, block) {
    var on = row.prescription_set_id === pickedId;
    return (
      '<button class="rail__row' +
      (on ? " is-on" : "") +
      '" type="button"' +
      (on ? ' aria-current="true"' : "") +
      ' data-set="' +
      row.prescription_set_id +
      '" title="' +
      esc(row.name) +
      '">' +
      RAIL_MARK +
      '<span class="rail__name">' +
      esc(railSetName(block, row.name)) +
      "</span></button>"
    );
  }

  function railHtml() {
    var blocks = setsByDisease(sets);
    var progress = copy ? copyProgress(copy.items) : null;

    /* **안내문 묶음은 진도를 단다(`1/3`), 처방 묶음은 개수를 단다(`3`).**
         접두사를 떼고 나면 두 갈래가 글자까지 똑같은 나무 두 그루가 된다 —
         가르는 것이 갈래 머리 하나뿐이면 스크롤 중에 어느 갈래인지 잃는다.
         숫자의 뜻이 다르면 접혀 있을 때도 두 갈래가 다르게 읽히고, 이건
         꾸밈이 아니라 볼 사람이 실제로 알고 싶은 값이다. */
    var guide = blocks
      .map(function (block) {
        return railGroupHtml(
          "guide",
          block,
          copyRailRow,
          copyBlockMark(copy, block.sets),
        );
      })
      .join("");
    var rx = blocks
      .map(function (block) {
        return railGroupHtml("sets", block, setRailRow, {
          say: String(block.sets.length),
          done: false,
        });
      })
      .join("");

    return (
      sectionHtml("안내문", progress ? progress.say : null) +
      (guide || '<p class="rail__none">안내문이 없습니다</p>') +
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
      (canEditSet ? "" : " disabled") +
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
      (canEditSet ? "" : " disabled") +
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
      (canEditSet ? "" : " disabled") +
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
            (canEditSet ? "" : " disabled") +
            " />" +
            '<input class="fld__input drug__freq" type="text" value="' +
            esc(drug.frequency) +
            '" placeholder="1일 1회" aria-label="복용 횟수"' +
            (canEditSet ? "" : " disabled") +
            " />" +
            '<input class="fld__input drug__note" type="text" value="' +
            esc(drug.note) +
            '" placeholder="매일 같은 시간" aria-label="복용 방법"' +
            (canEditSet ? "" : " disabled") +
            " />" +
            '<button class="drug__drop" type="button" data-drop="' +
            i +
            '" aria-label="삭제"' +
            (canEditSet ? "" : " disabled") +
            ">✕</button>" +
            "</div>"
          );
        })
        .join("") +
      (rows.length ? "" : '<p class="fld__hint">등록된 약이 없습니다</p>') +
      '<button class="button-ghost button-ghost--sm" type="button" id="drug-add"' +
      (canEditSet ? "" : " disabled") +
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

  /* 검사 기준선 한 줄 — 원문 D2-4 의 표 한 행. */
  function baselineRowHtml(row, index) {
    return (
      /* **줄이 제 질환을 들고 있어야 한다.** `data-row` 는 그린 차례이고
         `baselines.items` 는 배열 차례인데, 질환으로 묶어 그리므로 새로 더한
         줄에서 둘이 어긋난다 — 배열을 되짚지 않고 여기서 읽는다. */
      '<tr data-row="' +
      index +
      '" data-disease="' +
      esc(row.disease) +
      '">' +
      '<td><input class="fld__input bl__name" value="' +
      esc(row.name) +
      '"' +
      (canEdit ? "" : " disabled") +
      " /></td>" +
      "<td>" +
      BASELINE_DIRECTIONS.map(function (option) {
        return (
          '<label class="bl__dir"><input type="radio" name="dir' +
          index +
          '" value="' +
          esc(option.key) +
          '"' +
          (option.key === row.direction ? " checked" : "") +
          (canEdit ? "" : " disabled") +
          " />" +
          esc(option.say) +
          "</label>"
        );
      }).join("") +
      "</td>" +
      '<td class="bl__range">' +
      '<input class="fld__input bl__num" value="' +
      esc(trimNumber(row.low)) +
      '" placeholder="아래"' +
      (row.by_age || !canEdit ? " disabled" : "") +
      " />" +
      '<span class="bl__tilde">~</span>' +
      '<input class="fld__input bl__num" value="' +
      esc(trimNumber(row.high)) +
      '" placeholder="위"' +
      (row.by_age || !canEdit ? " disabled" : "") +
      " />" +
      '<label class="bl__age"><input type="checkbox" class="bl__byage"' +
      (row.by_age ? " checked" : "") +
      (canEdit ? "" : " disabled") +
      " />나이별</label>" +
      "</td>" +
      '<td><input class="fld__input bl__keys" value="' +
      esc(row.keywords) +
      '"' +
      (canEdit ? "" : " disabled") +
      " /></td>" +
      '<td><input class="fld__input bl__unit" value="' +
      esc(row.unit) +
      '"' +
      (canEdit ? "" : " disabled") +
      " /></td>" +
      '<td class="bl__center"><input type="checkbox" class="bl__shown"' +
      (row.always_shown ? " checked" : "") +
      (canEdit ? "" : " disabled") +
      " /></td>" +
      '<td class="bl__center">' +
      (canEdit
        ? '<button class="button-ghost button-ghost--sm" type="button" data-drop-baseline="' +
          index +
          '">삭제</button>'
        : "") +
      "</td></tr>"
    );
  }

  function baselinesHtml() {
    if (!baselines) return '<p class="note">불러오는 중…</p>';
    var index = -1;
    var blocks = baselinesByDisease(baselines.items)
      .map(function (block) {
        return (
          '<section class="box"><div class="box__head"><h2 class="box__title">' +
          esc(block.title) +
          "</h2></div>" +
          '<div class="table-wrap"><table class="past bl"><thead><tr>' +
          [
            "검사 항목",
            "방향",
            "기준선",
            "판독 키워드",
            "단위",
            "항상 표시",
            "",
          ]
            .map(function (head) {
              return "<th>" + esc(head) + "</th>";
            })
            .join("") +
          "</tr></thead><tbody>" +
          block.rows
            .map(function (row) {
              index += 1;
              return baselineRowHtml(row, index);
            })
            .join("") +
          "</tbody></table></div>" +
          (canEdit
            ? '<button class="button-ghost button-ghost--sm" type="button" data-add-baseline="' +
              esc(block.disease) +
              '">+ 검사 항목 추가</button>'
            : "") +
          "</section>"
        );
      })
      .join("");

    return (
      '<div class="patient-head"><span class="patient-head__name">검사 기준선</span>' +
      (showsWhosePicker(baselines.doctors)
        ? '<label class="bl__whose">누구 기준 <select class="fld__input" id="bl-whose">' +
          '<option value=""' +
          (whose ? "" : " selected") +
          ">의원 공통</option>" +
          baselines.doctors
            .map(function (doctor) {
              return (
                '<option value="' +
                esc(doctor.doctor_id) +
                '"' +
                (String(whose) === String(doctor.doctor_id)
                  ? " selected"
                  : "") +
                ">" +
                esc(doctor.name) +
                " 원장</option>"
              );
            })
            .join("") +
          "</select></label>"
        : "") +
      '<span class="grow"></span>' +
      (saying ? '<span class="box__note">' + esc(saying) + "</span>" : "") +
      (canEdit
        ? ""
        : '<span class="box__note">의사 계정만 수정할 수 있습니다</span>') +
      '<button class="button-primary button-primary--sm" type="button" id="bl-save"' +
      (canEdit ? "" : " disabled") +
      ">저장</button></div>" +
      blocks +
      '<p class="note note--warn">⚠ 기준선은 검사기관 · 연령에 따라 다릅니다 · 비워 두면 값과 추이만 표시하고 목표 대비 수치는 계산하지 않습니다</p>' +
      '<p class="note">ⓘ 「항상 표시」를 해제하면 판독 결과 확인 화면의 「＋ 항목 추가」에서 선택합니다</p>' +
      '<p class="note">ⓘ 판독 키워드는 EMR 표기를 그대로 적어 주세요 — 판독이 진료기록에서 그 항목을 찾는 데 씁니다</p>'
    );
  }

  /* 한 구역 — 원문 D2-2 의 「원본 / 박연 원장님 문구」 두 층. */
  function copySectionHtml(row, section) {
    var mine = copyIsMine(section);
    return (
      '<div class="cp"><div class="cp__head"><h3 class="cp__title">' +
      esc(copySectionSaying(section.section_key)) +
      '</h3><span class="grow"></span>' +
      (section.editable
        ? mine
          ? '<button class="button-ghost button-ghost--sm" type="button" data-revert-copy="' +
            esc(row.prescription_set_id) +
            "|" +
            esc(section.section_key) +
            '">원본으로 되돌리기</button>'
          : ""
        : '<span class="box__note">수정 불가</span>') +
      "</div>" +
      /* **원본이 위에 있다** — 원문 「무엇이 사실이고 무엇이 표현인지 보이게
         한다」. 고친 뒤에도 지워지지 않으므로 언제든 되돌아간다. */
      '<p class="cp__label">원본</p><p class="cp__origin">' +
      esc(section.origin || "승인된 원본 문구가 아직 없습니다") +
      "</p>" +
      (section.editable
        ? '<p class="cp__label">' +
          esc(whoseName()) +
          " 문구</p>" +
          '<textarea class="modal__input cp__body" rows="3" data-copy="' +
          esc(row.prescription_set_id) +
          "|" +
          esc(section.section_key) +
          '"' +
          (canEdit ? "" : " disabled") +
          ">" +
          esc(mine ? section.body : "") +
          "</textarea>" +
          (canEdit
            ? '<div class="cp__acts"><button class="button-primary button-primary--sm" type="button" data-save-copy="' +
              esc(row.prescription_set_id) +
              "|" +
              esc(section.section_key) +
              '">저장</button></div>'
            : "") +
          '<p class="note">ⓘ 표현만 수정해 주세요 — 새로운 의학 정보를 추가할 수 없습니다</p>' +
          '<p class="note">ⓘ 이 문구는 ' +
          esc(whoseName()) +
          " 담당 환자에게만 발송됩니다</p>"
        : '<p class="note">ⓘ 안전을 위해 모든 안내문에 포함됩니다</p>') +
      "</div>"
    );
  }

  function whoseName() {
    return who && who.name ? who.name + " 원장님" : "원장님";
  }

  /* 한 장 — 왼쪽에서 고른 것 하나만 선다. 여덟이 한꺼번에 펼쳐져 있으면
     어느 것을 보고 있는지 스크롤로 세어야 한다. */
  function copySetHtml(row) {
    return (
      '<div class="patient-head"><span class="patient-head__name">' +
      esc(row.name) +
      '</span><span class="cp__mark' +
      (row.reviewed ? " cp__mark--done" : "") +
      '">' +
      esc(copyMark(row)) +
      '</span><span class="grow"></span>' +
      (saying ? '<span class="box__note">' + esc(saying) + "</span>" : "") +
      (canEdit
        ? ""
        : '<span class="box__note">의사 계정만 수정할 수 있습니다</span>') +
      (canEdit
        ? '<button class="button-primary button-primary--sm" type="button" data-review-copy="' +
          esc(row.prescription_set_id) +
          '"' +
          (row.reviewed ? " disabled" : "") +
          ">확인 완료</button>"
        : "") +
      "</div>" +
      '<p class="note">ⓘ 원본은 지워지지 않습니다 — 언제든 되돌아갈 수 있습니다</p>' +
      row.sections
        .map(function (part) {
          return copySectionHtml(row, part);
        })
        .join("") +
      '<p class="note">ⓘ 「이 약을 왜 드시나요」와 「먹는 방법」은 환자마다 판독값으로 만들어집니다 — 여기서 고칠 문구가 없습니다</p>'
    );
  }

  function copyHtml() {
    if (!copy) return '<p class="note">불러오는 중…</p>';
    var row = copy.items.filter(function (item) {
      return item.prescription_set_id === copyPick;
    })[0];
    if (!row)
      return '<p class="note">왼쪽에서 안내문을 선택하면 원본과 문구가 표시됩니다</p>';
    return copySetHtml(row);
  }

  function detailHtml() {
    if (group === "guide") return copyHtml();
    if (group === "baseline") return baselinesHtml();
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
      (canEditSet
        ? ""
        : '<span class="box__note">처방 설정은 모든 의원이 함께 쓰는 값이라 아직 고칠 수 없습니다</span>') +
      '<button class="button-primary button-primary--sm" type="button" id="set-save"' +
      (canEditSet ? "" : " disabled") +
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

  /* 펼친 묶음이 하나뿐이라 **전부를 훑어 맞춘다** — 방금 연 것과 방금 닫힌
     것 둘을 따로 찾을 것 없이, 열쇠 하나와 대 보면 된다.
     만지는 것은 셋뿐이다: 낭독기가 읽는 것(`aria-expanded`), 눈이 보는 것
     (`is-open`), 자리를 차지하느냐(`hidden`). */
  function showOpen() {
    var heads = el("rail").querySelectorAll("[data-fold]");
    for (var i = 0; i < heads.length; i++) {
      var head = heads[i];
      var on = head.getAttribute("data-fold") === opened;
      var kids = el(head.getAttribute("aria-controls"));
      head.setAttribute("aria-expanded", on ? "true" : "false");
      head.parentNode.classList.toggle("is-open", on);
      if (kids) kids.hidden = !on;
    }
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

  /* 처방 설정을 저장하던 `save()` 가 여기 있었다. 걷었다 — `canEditSet` 주석
     참고. 서버 쪽 `PUT /prescription-sets/{id}` 도 함께 걷었으므로 부를 곳이
     없다. 표를 의원별로 가르는 일감에서 둘을 함께 되살린다. */

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

  /* ── 검사 기준선 (D2-4) ────────────────────────────────────────── */

  function openBaselines() {
    group = "baseline";
    pickedId = null;
    picked = null;
    templates = null;
    saying = "";
    render();
    return loadBaselines();
  }

  function loadBaselines() {
    return catalogApi
      .baselines(whose)
      .then(function (data) {
        if (group !== "baseline") return; // 그 사이 다른 데로 갔으면 붙이지 않는다
        baselines = data;
        render();
      })
      .catch(function () {
        if (group !== "baseline") return;
        el("detail").innerHTML =
          '<p class="note">검사 기준선을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</p>';
      });
  }

  /* 화면에 적힌 것을 거둔다. **다시 그리기 전에 부른다** — 안 그러면 치던
     값이 날아간다. */
  function baselinesNow() {
    var rows = [];
    var trs = document.querySelectorAll("#detail [data-row]");
    for (var i = 0; i < trs.length; i++) {
      var tr = trs[i];
      var nums = tr.querySelectorAll(".bl__num");
      var dir = tr.querySelector("input[type=radio]:checked");
      rows.push({
        disease: tr.getAttribute("data-disease"),
        name: tr.querySelector(".bl__name").value,
        direction: dir ? dir.value : "KEEP",
        low: nums[0].value,
        high: nums[1].value,
        by_age: tr.querySelector(".bl__byage").checked,
        keywords: tr.querySelector(".bl__keys").value,
        unit: tr.querySelector(".bl__unit").value,
        always_shown: tr.querySelector(".bl__shown").checked,
      });
    }
    return rows;
  }

  function saveBaselines() {
    var rows = baselinesNow();
    baselines = Object.assign({}, baselines, { items: rows });
    /* **하나라도 막히면 아무것도 안 보낸다.** 반만 저장되면 어느 것이
       들어갔는지 화면이 말할 수 없다. */
    for (var i = 0; i < rows.length; i++) {
      var problem = baselineProblem(rows[i]);
      if (problem) {
        saying = problem;
        return render();
      }
    }
    var twice = duplicateBaselines(rows);
    if (twice.length) {
      saying = "같은 질환에 「" + twice[0] + "」가 둘입니다";
      return render();
    }

    saying = "저장하는 중…";
    render();
    catalogApi
      .saveBaselines(whose, rows)
      .then(function (data) {
        /* **서버가 돌려준 것을 화면으로 삼는다** — 나이별을 켜면 서버가 숫자를
           비우는데, 그것이 화면에 안 보이면 안 된다. */
        baselines = data;
        saying = "저장되었습니다";
        render();
      })
      .catch(function (err) {
        saying =
          err && err.status === 403
            ? "의사 계정만 수정할 수 있습니다"
            : "저장하지 못했습니다. 잠시 후 다시 시도해 주세요";
        render();
      });
  }

  /* ── 안내문 문구 (D2-1 · D2-2) ─────────────────────────────────── */

  function openCopy() {
    group = "guide";
    /* 고른 장이 든 묶음은 펴 둔다 — 접힌 채로 두면 방금 고른 것이 안 보인다 */
    var mine = copyPick ? railGroupKey(sets, copyPick) : null;
    if (mine) opened = railFoldKey("guide", mine);
    pickedId = null;
    picked = null;
    templates = null;
    baselines = null;
    saying = "";
    render();
    return loadCopy();
  }

  /* **레일이 늘 쓴다.** 안내문 목록은 왼쪽에 상시 서 있고 진도(「1/8」)와 ✓ 가
     거기서 나오므로, 안내문 갈래를 열지 않아도 한 번 받아 둔다. 그래서 값을
     붙일 때 「지금 안내문을 보고 있는가」로 막지 않는다 — 막으면 처방을 보는
     동안 레일의 표시가 통째로 사라진다. */
  function loadCopy() {
    return catalogApi
      .guideCopy()
      .then(function (data) {
        copy = data;
        render();
      })
      .catch(function () {
        /* 오른쪽에 적는 것은 안내문을 보고 있을 때만 — 처방을 보는 중에
           남의 자리에 실패를 적을 수는 없다. 레일은 표시 없이 선다. */
        if (group !== "guide") return;
        el("detail").innerHTML =
          '<p class="note">안내문 문구를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</p>';
      });
  }

  function sectionOf(setId, sectionKey) {
    var row = ((copy && copy.items) || []).filter(function (item) {
      return String(item.prescription_set_id) === String(setId);
    })[0];
    if (!row) return null;
    return row.sections.filter(function (part) {
      return part.section_key === sectionKey;
    })[0];
  }

  function saveCopy(key) {
    var parts = key.split("|");
    var box = document.querySelector('[data-copy="' + key + '"]');
    var problem = copyProblem(
      sectionOf(parts[0], parts[1]),
      box ? box.value : "",
    );
    if (problem) {
      saying = problem;
      return render();
    }
    saying = "저장하는 중…";
    catalogApi
      .saveCopy(parts[0], parts[1], box.value.trim())
      .then(function (data) {
        /* **서버가 돌려준 것을 화면으로 삼는다** — 고치면 확인이 풀리는데,
           그것이 화면에 안 보이면 안 된다. */
        copy = data;
        saying = "저장되었습니다";
        render();
      })
      .catch(function (err) {
        saying =
          err && err.status === 403
            ? "의사 계정만 수정할 수 있습니다"
            : "저장하지 못했습니다. 잠시 후 다시 시도해 주세요";
        render();
      });
  }

  function revertCopy(key) {
    var parts = key.split("|");
    saying = "";
    catalogApi
      .revertCopy(parts[0], parts[1])
      .then(function (data) {
        copy = data;
        render();
      })
      .catch(function () {
        saying = "되돌리지 못했습니다. 잠시 후 다시 시도해 주세요";
        render();
      });
  }

  function reviewCopy(setId) {
    saying = "";
    catalogApi
      .reviewCopy(setId)
      .then(function (data) {
        copy = data;
        render();
      })
      .catch(function () {
        saying = "확인을 남기지 못했습니다. 잠시 후 다시 시도해 주세요";
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
      baselines = null;
      /* **안내문 고름을 놓는다.** 오른쪽이 처방을 보고 있는데 안내문 줄이 굵게
         남아 있으면 화면이 두 곳을 동시에 가리킨다. 목록(`copy`)은 그대로 둔다 —
         레일의 진도와 ✓ 는 어느 갈래를 보고 있든 서 있어야 한다. */
      copyPick = null;
      var chose = railGroupKey(sets, Number(row.getAttribute("data-set")));
      if (chose) opened = railFoldKey("sets", chose);
      return loadSet(Number(row.getAttribute("data-set")));
    }

    var chosenGroup = target.closest("[data-group]");
    if (chosenGroup && chosenGroup.getAttribute("data-group") === "sms")
      return openTemplates();
    if (chosenGroup && chosenGroup.getAttribute("data-group") === "baseline")
      return openBaselines();
    if (chosenGroup && chosenGroup.getAttribute("data-group") === "guide")
      return openCopy();

    /* 묶음 머리 — 그 자리에서 여닫는다. **다시 그리지 않는다.**
     *
     * `render()` 는 `el("rail").innerHTML` 로 레일을 통째로 갈아치운다. 그러면
     * 방금 누른 버튼 노드가 사라져 (1) 화살표가 새 노드라 회전이 한 프레임도
     * 안 보이고 (2) 키보드 초점이 <body> 로 떨어져 묶음 하나를 펼치면 다음
     * Tab 이 화면 맨 위에서 다시 시작한다.
     *
     * 여기서 바뀌는 것은 **보이고 안 보이고**뿐이다. 데이터가 안 변하는 일에
     * 화면을 새로 그릴 이유가 없다. */
    var fold = target.closest("[data-fold]");
    if (fold) {
      var key = fold.getAttribute("data-fold");
      opened = opened === key ? null : key;
      return showOpen();
    }

    /* 안내문 한 장 고르기 */
    var pickedCopy = target.closest("[data-copy-set]");
    if (pickedCopy) {
      copyPick = Number(pickedCopy.getAttribute("data-copy-set"));
      saying = "";
      if (group !== "guide") return openCopy();
      return render();
    }

    var saveCopyAt = target.closest("[data-save-copy]");
    if (saveCopyAt) return saveCopy(saveCopyAt.getAttribute("data-save-copy"));

    var revertCopyAt = target.closest("[data-revert-copy]");
    if (revertCopyAt)
      return revertCopy(revertCopyAt.getAttribute("data-revert-copy"));

    var reviewAt = target.closest("[data-review-copy]");
    if (reviewAt)
      return reviewCopy(Number(reviewAt.getAttribute("data-review-copy")));

    if (target.closest("#bl-save")) return saveBaselines();

    var addBaseline = target.closest("[data-add-baseline]");
    if (addBaseline) {
      var added = baselinesNow();
      added.push({
        disease: addBaseline.getAttribute("data-add-baseline"),
        name: "",
        direction: "KEEP",
        low: "",
        high: "",
        by_age: false,
        keywords: "",
        unit: "",
        always_shown: true,
      });
      baselines = Object.assign({}, baselines, { items: added });
      saying = "";
      return render();
    }

    var dropBaseline = target.closest("[data-drop-baseline]");
    if (dropBaseline) {
      /* 지우기 전에 화면에 적힌 것을 거둔다 — 안 그러면 치던 값이 날아간다 */
      var kept = baselinesNow();
      kept.splice(Number(dropBaseline.getAttribute("data-drop-baseline")), 1);
      baselines = Object.assign({}, baselines, { items: kept });
      saying = "";
      return render();
    }

    if (target.closest("#sms-save")) return saveTemplates();
    var revert = target.closest("[data-revert]");
    if (revert) return revertTemplate(revert.getAttribute("data-revert"));


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

  document.addEventListener("change", function (event) {
    /* 나이별을 켜면 숫자칸이 잠긴다 — 숫자 하나로 못 적는 값이라, 남겨 두면
       어느 쪽으로 셈할지 알 수 없다. 서버도 같은 이유로 지운다. */
    if (
      event.target.classList &&
      event.target.classList.contains("bl__byage")
    ) {
      baselines = Object.assign({}, baselines, { items: baselinesNow() });
      return render();
    }
    /* 누구 기준을 바꾸면 그 판을 다시 읽는다. */
    if (event.target.id === "bl-whose") {
      whose = event.target.value ? Number(event.target.value) : null;
      baselines = null;
      saying = "";
      render();
      return loadBaselines();
    }

    /* 세는 방법과 소진 임박은 **켜면 칸이 따라 나온다** — 다시 그려야 보인다 */
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

  /* 좌측 접기는 다른 의료진 화면과 같은 것을 쓴다 (js/list-fold.js) —
     화면은 파일을 싣고 있었는데 손을 안 붙여서 아이콘이 안 눌렸다. */
  wireFold(false);

  requireSession().then(function (me) {
    who = me;
    el("who-name").textContent = me.name;
    el("who-roles").textContent = roleLabel(me.roles);
    canEdit = (me.roles || []).indexOf("doctor") !== -1;
    /* 안내문 목록도 같이 — 레일이 처음부터 진도를 보여 준다 */
    return Promise.all([loadSets(), loadCopy()]);
  });
})();
