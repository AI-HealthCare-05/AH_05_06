/* 설정 화면 — 와이어프레임 D2-3 「처방」.
 *
 * 왼쪽 레일에서 처방을 고르면 오른쪽에 그 세트가 펼쳐진다. 고치는 것은 **의사만**
 * 이다(D2-2 원문은 「의사 계정만」이었으나 2026-09-02 회의로 스탭도 고친다) —
 * 이 값이 안내문과 문자
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
  /* 새 처방을 만드는 중인가. `null` 이면 아니다.
     **이름과 진단을 한 자리에서 정한다.** 이름은 만들고 나면 못 바꾸므로
     (지난 진료기록이 그 이름으로 이 처방을 가리킨다) 만들기 전에 다 보여
     주고 한 번에 받는다. */
  var making = null;

  /* 보내는 중. **다시 그려도 살아남아야 한다** — DOM 의 `disabled` 는
     `render()` 가 판을 통째로 갈아치우면서 지워진다. */
  var busy = false;

  /* 만들다 말고 딴 데 갔을 때 들고 있는 판. 다시 「+ 새 처방」을 누르면
     되살린다 — 잘못 눌러 나갔다고 다시 치게 하면 안 된다. */
  var draft = null;
  var pickedId = null;
  var canEdit = false;



  /* 지금 고치는 중인 문구 칸 하나. `null` 이면 전부 잠겨 있다.
     **한 번에 하나만 연다** — 여럿을 열어 두면 어느 것을 저장하는지
     헷갈리고, 저장 실패 문구가 어느 칸 것인지도 알 수 없다. */
  var copyOpen = null;

  function copyKey(row, section) {
    return row.prescription_set_id + "|" + section.section_key;
  }
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
  var drugs = null; // 약 목록 판 — 의원이 쓰는 약

  /* **제작 중인가.** 서버가 목록 응답에 실어 준다(`draft`). 받기 전에는
     잠근 쪽으로 둔다 — 열어 두었다가 잠긴 서버에 보내면 409 가 난다.
     열어 두는 쪽이 안전한 기본값이 아니다. */
  var DRAFT = false;
  /* **펼친 묶음은 여럿일 수 있다.**
   *
   * 한동안 하나만 열리게 두었다. 원문 D2-3 주석이 「9개가 늘 다 펼쳐져 있으면
   * 왼쪽이 길어져 「그 밖에」가 화면 밖으로 밀린다」고 적었고, 재 보니 묶음
   * 넷을 다 펼치면 937px 인데 보이는 높이가 689px 이라 「기타」 세 줄이
   * 밀려났기 때문이다.
   *
   * **그 셈의 전제가 바뀌었다.** 안내문 묶음을 처방 안으로 넣으면서 나무가
   * 하나가 됐다 — 묶음이 넷에서 둘로 줄었고 줄은 여덟이다. 둘 다 펴도
   * 「기타」가 안 밀린다.
   *
   * 그리고 하나만 열리는 것이 실제로 걸리적거렸다: 다낭성을 펴는 순간
   * 자궁내막증이 닫혀서, 두 묶음을 견주려면 접었다 폈다를 되풀이해야 했다.
   *
   * 열쇠에 갈래를 함께 담는다(`"guide|ENDOMETRIOSIS"`). 갈래별로 통을 나눠
   * 두었던 것은 두 갈래에 같은 질환이 있어 한 통에 담으면 같이 접히기
   * 때문인데, 열쇠에 갈래가 들어 있으면 그 일이 안 난다. */
  var opened = {};
  var who = null; // 로그인한 사람 — 문구가 누구 이름으로 나가는지 적는다
  var whose = null; // 누구 기준 — 비면 의원 공통
  var drafts = {}; // 아직 저장 안 한 문구 — 다시 그려도 친 값이 남아야 한다

  /* ── 왼쪽 레일 ─────────────────────────────────────────────────── */

  /* 갈래 머리 — **눌리지 않는 이름표다.** 개수를 이름 바로 옆에 붙인다:
     오른쪽 끝으로 밀면 「오른쪽에 표시를 단 줄」이 되어, 아무 일도 안 하는
     것이 화면에서 제일 눌러 보고 싶게 생긴다. */
  /** 묶음 머리. `add` 를 주면 오른쪽 끝에 더하기 단추가 붙는다.
   *
   * **더하는 자리는 머리다.** 목록 아래 한 줄로 두었더니 눈에 안 걸렸다 —
   * 여덟 줄을 지나 접힌 묶음 밑까지 내려가야 보이고, 거기서는 「목록의
   * 마지막 항목」처럼 읽힌다. 머리에 두면 그 묶음에 더한다는 것이 자리로
   * 말해진다. */
  function sectionHtml(title, count, add) {
    return (
      '<div class="rail__section"><span class="rail__section-name">' +
      esc(title) +
      "</span>" +
      (count == null
        ? ""
        : '<span class="rail__section-count">' + esc(count) + "</span>") +
      (add
        ? '<button class="rail__plus" type="button" id="' +
          add +
          '" title="새 대표 처방 만들기" aria-label="새 대표 처방 만들기">+</button>'
        : "") +
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
    var open = !!opened[key];
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
  /** 처방 한 줄. **문구 확인 상태를 함께 단다.**
   *
   * 안내문 묶음이 따로 있던 때는 그쪽 줄이 「확인 전 / ✓」를 달았다. 묶음을
   * 걷으면서 그 표시를 여기로 가져온다 — 어느 처방의 문구를 아직 안 봤는지는
   * 레일에서 보여야 하고, 그것 때문에 나무를 둘로 세울 이유는 없다. */
  function setRailRow(row, block) {
    var on = row.prescription_set_id === pickedId;
    var mark = copyRailMark(copy, row.prescription_set_id);
    return (
      '<button class="rail__row' +
      (on ? " is-on" : "") +
      (row.hidden ? " rail__row--hidden" : "") +
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
      (row.hidden ? " (숨김)" : "") +
      '</span><span class="rail__note' +
      (mark.done ? " rail__note--done" : mark.say ? " rail__note--todo" : "") +
      '">' +
      esc(mark.say) +
      "</span></button>"
    );
  }

  /** 레일은 **처방 하나로 선다.**
   *
   * 안내문 묶음이 따로 있었다. 같은 처방을 두 번 오가야 했다 — 왼쪽에서
   * 「비잔 (계속)」을 고르고 약을 보다가, 그 처방의 문구를 고치려면 위쪽
   * 안내문 묶음에서 「비잔 (계속)」을 **다시** 찾아 눌러야 했다.
   *
   * **둘의 열쇠가 같은 처방 세트다.** 안내문은 처방과 처방일수로 만들어지므로
   * 처방이 기준이고, 문구는 그 처방의 한 속성이다. 나무를 둘로 세우면 같은
   * 것을 두 번 세운 셈이 된다.
   *
   * 묶음 머리의 진도(`2/5`)는 남긴다 — 어느 질환에 확인 안 한 문구가 몇 개
   * 남았는지는 접혀 있을 때도 알아야 한다. */
  function railHtml() {
    var blocks = setsByDisease(sets);
    var progress = copy ? copyProgress(copy.items) : null;

    var rx = blocks
      .map(function (block) {
        return railGroupHtml("sets", block, setRailRow, copyBlockMark(copy, block.sets));
      })
      .join("");

    return (
      /* **지우는 단추는 없다.** 의료 데이터라 삭제가 금지되고, 지난
         진료기록이 이 이름으로 이 처방을 가리킨다. 잘못 지은 이름은
         상세에서 숨기고 여기 머리의 「+」로 새로 만든다. */
      sectionHtml("대표 처방", progress ? progress.say : sets.length, "set-new") +
      (rx || '<p class="rail__none">대표 처방이 없습니다</p>') +
      /* **처방(약 목록)은 대표 처방 바로 아래다.** 대표 처방에 약을 적을 때
         여기서 고르므로, 둘이 붙어 있어야 눈이 오가지 않는다. */
      sectionHtml("처방", drugs ? drugs.length : null) +
      groupsIn("drugs").map(groupRowHtml).join("") +
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

  /* `locked` 는 `disabled` 와 **뜻이 다르다.** 이 화면에서 `disabled` 는
     「당신에게 권한이 없다」(`canEdit`)는 뜻이라, 누구에게도 안 열리는 칸에
     그것을 쓰면 「의사면 되나」로 읽힌다. `readonly` 로 두고 까닭을 적는다. */
  function textHtml(id, label, value, hint, locked) {
    return (
      '<label class="fld"><span class="fld__label">' +
      esc(label) +
      '</span><input class="fld__input" type="text" id="' +
      id +
      '" value="' +
      esc(value || "") +
      '"' +
      (locked ? " readonly" : canEdit ? "" : " disabled") +
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
            '" placeholder="비잔정 2mg" aria-label="약 이름" list="drug-names"' +
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
        : "") +
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
        : "") +
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
        ? '<p class="cp__label">고친 문구</p>' +
          '<textarea class="modal__input cp__body" rows="3" data-copy="' +
          esc(row.prescription_set_id) +
          "|" +
          esc(section.section_key) +
          '"' +
          (canEdit && copyOpen === copyKey(row, section) ? "" : " readonly") +
          ">" +
          esc(mine ? section.body : "") +
          "</textarea>" +
          /* **누르기 전에는 안 열린다.** 환자에게 나가는 의료 문구라, 스치듯
             친 글자가 그대로 저장되면 안 된다. 설정 수정이 스탭에게까지
             열리면서(2026-09-02) 이 화면을 여는 사람이 늘었다. */
          (canEdit
            ? '<div class="cp__acts">' +
              (copyOpen === copyKey(row, section)
                ? '<button class="button-ghost button-ghost--sm" type="button" data-cancel-copy="1">취소</button>' +
                  '<button class="button-primary button-primary--sm" type="button" data-save-copy="' +
                  esc(row.prescription_set_id) +
                  "|" +
                  esc(section.section_key) +
                  '">저장</button>'
                : '<button class="button-ghost button-ghost--sm" type="button" data-edit-copy="' +
                  esc(row.prescription_set_id) +
                  "|" +
                  esc(section.section_key) +
                  '">수정</button>') +
              "</div>"
            : "") +
          '<p class="note">ⓘ 표현만 수정해 주세요 — 새로운 의학 정보를 추가할 수 없습니다</p>' +
          /* **누구에게 나가는지 정확히 적는다.** 전에는 「○○ 원장님 담당
             환자에게만」이었는데, 스탭도 고치게 되면서 틀린 말이 됐다 —
             스탭에게는 담당 환자가 없다. 서버가 실제로 고르는 차례를 적는다
             (`app/services/guides.py` 의 `_doctor_copy`). */
          '<p class="note">ⓘ 담당 의사가 고친 문구가 먼저 쓰이고, 없으면 안내문을 만든 사람의 문구가 쓰입니다</p>'
        : '<p class="note">ⓘ 안전을 위해 모든 안내문에 포함됩니다</p>') +
      "</div>"
    );
  }

  /** 이 문구의 주인. **직함을 붙이지 않는다.**
   *
   * 「원장님」을 늘 붙이고 있었다 — 로그인한 사람이 스탭이어도 「한소영
   * 원장님」이 됐다. 설정 수정이 스탭에게 열리면서(2026-09-02 회의) 그 오기가
   * 더 자주 보인다.
   *
   * 직함을 역할에서 지어내지도 않는다. 「원장」인지 「과장」인지는 이 저장소가
   * 모르는 것이고, 모르는 것을 화면이 지어내면 그것도 오기다. */
  function whoseName() {
    return who && who.name ? who.name : "내";
  }

  /* 한 장 — 왼쪽에서 고른 것 하나만 선다. 여덟이 한꺼번에 펼쳐져 있으면
     어느 것을 보고 있는지 스크롤로 세어야 한다. */

  /** 약 목록 판 — 의원이 쓰는 약을 등록한다.
   *
   * **대표 처방에 약을 적을 때 여기서 고르라고 둔다.** 약 넷이 여덟 세트에
   * 열세 번 되풀이되고, 손으로 치면 표기가 갈린다 — 이미 갈려 있다
   * (검사·주석은 「비잔정 2mg」, 판독·CSV 는 「비잔정(디에노게스트) 2mg」).
   *
   * **이 목록을 읽는 것은 아직 설정 화면뿐이다.** 안내문·환자 화면·챗봇은 안
   * 읽는다. 그것들이 읽으려면 판독 확정이 진료에 처방을 붙이는 다리가 먼저
   * 서야 한다(KEY-66).
   */
  function textCell(kind, at, hint, value, locked) {
    return (
      '<input class="fld__input ' +
      kind +
      '" type="text" data-' +
      kind +
      '="' +
      at +
      '" value="' +
      esc(value || "") +
      '" placeholder="' +
      esc(hint) +
      '" aria-label="' +
      esc(hint) +
      '"' +
      (locked ? " readonly" : canEdit ? "" : " disabled") +
      " />"
    );
  }

  /** 대표 처방의 약 이름 칸이 쓰는 자동완성 목록. **감춘 약은 뺀다** —
   *  새로 고르는 자리이기 때문이다. 이미 저장된 이름은 그대로 남는다. */
  function drugListHtml() {
    if (!drugs || !drugs.length) return "";
    return (
      '<datalist id="drug-names">' +
      drugs
        .filter(function (row) {
          /* 감춘 것과 **아직 이름 없는 줄**을 뺀다 — 빈 항목이 목록에
             섞이면 고를 것이 없는 줄이 하나 뜬다. */
          return !row.hidden && row.name;
        })
        .map(function (row) {
          return '<option value="' + esc(row.name) + '"></option>';
        })
        .join("") +
      "</datalist>"
    );
  }

  function drugsPanelHtml() {
    if (!drugs) {
      return '<p class="note">약 목록을 불러오는 중…</p>';
    }

    var rows = drugs
      .map(function (row, i) {
        return (
          '<div class="drug' +
          (row.hidden ? " drug--hidden" : "") +
          '" data-drug-row="' +
          i +
          '">' +
          textCell("dg-name", i, "약 이름", row.name, !DRAFT) +
          textCell("dg-freq", i, "1일 1회", row.frequency) +
          textCell("dg-note", i, "매일 같은 시간", row.note) +
          '<button class="drug__drop" type="button" data-drug-hide="' +
          i +
          '" title="' +
          (row.hidden ? "되살리기" : "감추기") +
          '" aria-label="' +
          (row.hidden ? "되살리기" : "감추기") +
          '"' +
          (canEdit ? "" : " disabled") +
          ">" +
          (row.hidden ? "↩" : "✕") +
          "</button></div>"
        );
      })
      .join("");

    return (
      '<div class="patient-head"><span class="patient-head__name">약 목록</span>' +
      '<span class="grow"></span>' +
      (saying ? '<span class="box__note">' + esc(saying) + "</span>" : "") +
      '<button class="button-primary button-primary--sm" type="button" id="dg-save"' +
      (canEdit && !busy ? "" : " disabled") +
      ">저장</button></div>" +
      '<section class="box"><div class="box__head">' +
      '<h2 class="box__title">처방</h2>' +
      '<span class="box__note">대표 처방에서 고를 수 있습니다</span></div>' +
      '<div class="drugs">' +
      (rows || '<p class="fld__hint">등록된 약이 없습니다</p>') +
      '<button class="button-ghost button-ghost--sm" type="button" id="dg-add"' +
      (canEdit ? "" : " disabled") +
      ">+ 약 등록</button></div>" +
      /* **지우는 단추는 없다.** 감추면 새로 고를 목록에서만 빠지고, 이미 그
         이름으로 저장된 대표 처방은 그대로다. */
      '<p class="note">ⓘ 등록한 약은 지우지 않고 감춥니다 — 이미 그 이름으로 저장된 대표 처방이 있기 때문입니다</p>' +
      (DRAFT
        ? '<p class="note">ⓘ 지금은 제작 중이라 이름을 고칠 수 있습니다 — 배포 전에 잠깁니다</p>'
        : "") +
      "</section>"
    );
  }

  function detailHtml() {
    if (group === "drugs") return drugsPanelHtml();
    if (group === "baseline") return baselinesHtml();
    if (group === "sms") return templatesHtml();
    if (!picked) {
      return '<p class="note">대표 처방을 선택하면 상세 설정이 표시됩니다</p>';
    }

    return (
      '<div class="patient-head"><span class="patient-head__name">' +
      esc(making ? "새 대표 처방" : picked.name) +
      "</span>" +
      '<span class="grow"></span>' +
      (saying ? '<span class="box__note">' + esc(saying) + "</span>" : "") +
      /* **지우는 단추는 없다.** 의료 데이터라 삭제가 금지되고, 지난
         진료기록이 이 이름으로 이 처방을 가리킨다 — 행이 사라지면 그
         진료들의 안내문 문구가 조용히 떨어진다. 숨기면 새로 고를 수만
         없어지고, 지난 진료기록에는 그대로 붙는다. */
      (canEdit && !making
        ? '<button class="button-ghost button-ghost--sm" type="button" id="set-hide">' +
          (picked.hidden ? "되살리기" : "숨기기") +
          "</button>"
        : "") +
      (making
        ? '<button class="button-ghost button-ghost--sm" type="button" id="make-cancel">취소</button>'
        : "") +
      '<button class="button-primary button-primary--sm" type="button" id="set-save"' +
      (canEdit && !busy ? "" : " disabled") +
      ">" +
      (making ? "만들기" : "저장") +
      "</button></div>" +
      (picked.hidden
        ? '<p class="fld__hint">숨긴 대표 처방입니다 — 새 진료에서 고를 수 없습니다 · ' +
          "이미 이 대표 처방으로 나간 안내문은 그대로입니다</p>"
        : "") +
      /* ① 무엇인가 */
      /* **현황·진료기록이 부르는 말을 그대로 쓴다** — 거기서 이 한 쌍을
         「진단 · 처방」이라 부른다. 화면마다 다른 말을 쓰면 같은 것을 두 가지로
         배우게 된다. */
      '<section class="box"><div class="box__head">' +
      '<h2 class="box__title">진단 · 대표 처방</h2></div>' +
      '<div class="cols2">' +
      /* **화면이 부르는 이름을 쓴다.** 「이름」·「질환」이라 적혀 있었는데,
         이 화면을 여는 사람이 셈하는 것은 「어느 진단에 어느 처방인가」다.
         「이름」은 무엇의 이름인지 안 말하고, 「질환」은 진료기록·판독 화면이
         쓰는 말(「진단」)과 갈린다 — 같은 것을 두 말로 부르면 안 된다. */
      /* **칸을 없애지 않는다.** 무엇을 고치는 중인지 보여야 하고,
         `keepScreen()` 이 이 칸을 「처방 판이 떠 있나」의 탐침으로 쓴다.
         없애면 조용히 no-op 이 되어 값 유실 버그가 되살아난다. */
      /* **진단이 앞이다.** 진단이 처방을 고르는 기준이지 그 반대가
         아니다 — 진료기록도 그 차례로 읽는다. */
      pickHtml(
        "f-disease",
        "진단",
        [
          ["ENDOMETRIOSIS", diseaseLabel("ENDOMETRIOSIS")],
          ["PCOS", diseaseLabel("PCOS")],
        ],
        picked.disease,
      ) +
      textHtml(
        "f-name",
        "대표 처방",
        picked.name,
        making
          ? "진료기록이 이 이름으로 이 대표 처방을 가리키게 됩니다 · 나중에 바꿀 수 없습니다"
          : "지난 진료기록이 이 이름으로 이 대표 처방을 가리킵니다 · 바꾸는 대신 숨기고 새로 만듭니다",
        !making,
      ) +
      "</div>" +
      '<div class="drugs">' +
      '<span class="fld__label">처방</span>' +
      drugsHtml() +
      /* **등록된 약에서 고른다.** `<datalist>` 는 목록 밖 값을 막지 않는다 —
         막으면 이미 저장된 「비잔정 2mg」이 목록(「비잔정(디에노게스트) 2mg」)에
         없어서, 다른 칸만 고치고 저장해도 약 이름이 빈칸으로 떨어진다. */
      drugListHtml() +
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
      '<p class="fld__hint">ⓘ 이 대표 처방 선택 시 기본값으로 적용됩니다 · 환자별 설정은 문자 설정에서 변경합니다</p></section>' +
      /* ⑤ 「그 밖에」 — **화면에서 걷었다.**
         「EMR 표시 코드」와 「재진 안내」 두 칸은 저장되고 되읽힐 뿐,
         **읽어서 쓰는 데가 한 곳도 없었다.** 안내문 생성도 문자 예약도
         OCR 대조도 안 본다. 와이어프레임 2.3.1·3.0.0 어디에도 없다
         (2.3.1 의 「재진 안내」는 S1-14 문자 발송으로 다른 것이다).
         도움말은 「이 코드가 기록된 진료를 안내 대상으로 인식합니다」라며
         **아직 없는 기능을 설명하고 있었다** — 적어 넣은 사람은 무언가
         달라질 줄 알았을 것이다. 값과 컬럼은 그대로 두었다(2026-09-02 결정).
         EMR 코드 대조를 만들 때 이 자리를 되살리면 된다. */
      /* ⑥ 안내문 문구 — **같은 처방의 한 속성이다.**
         묶음을 따로 두던 때는 여기까지 보고 나서 왼쪽 위로 올라가 같은 처방을
         다시 찾아야 했다. 안내문은 이 처방과 처방일수로 만들어지므로, 약과
         확인 항목을 정한 자리에서 그 문구까지 본다. */
      copySectionsHtml(picked.prescription_set_id)
    );
  }

  /** 이 처방의 안내문 문구 묶음. 처방 상세 맨 아래에 붙는다.
   *
   * 문구는 처방 설정(`sets`)과 **다른 API** 로 온다(`guide-copy`) — 원본은
   * 의원 공통이고 고친 글은 사람마다라, 한 응답에 담기지 않는다. 그래서 아직
   * 안 왔을 수 있고, 그때는 자리만 비워 둔다. */
  /** 아직 만들지 않은 처방의 안내문 절 — **기본 문구를 보이되 못 고친다.**
   *
   * 고칠 수 있게 하면 저장할 데가 없다: 문구는 세트 번호로 저장되는데
   * (`PUT /guide-copy/{id}/{section}`) 그 번호가 아직 없다. 만들기가 막히면
   * 친 문구가 그 자리에서 사라진다.
   *
   * 안 보이면 안 되는 이유는 그 반대다 — 무슨 글이 나갈지 모르고 만들게 된다.
   */
  function draftCopyHtml() {
    if (!copy || !copy.defaults) return "";
    return (
      '<section class="box"><div class="box__head">' +
      '<h2 class="box__title">안내문 문구</h2>' +
      '<span class="box__note">만든 뒤 고칠 수 있습니다</span></div>' +
      '<p class="note">ⓘ 이 문구로 시작합니다 — 의원이 함께 쓰는 기본 글입니다</p>' +
      copy.defaults
        .map(function (part) {
          return (
            '<div class="cp"><div class="cp__head"><span class="cp__name">' +
            esc(copySectionSaying(part.section_key)) +
            "</span>" +
            (part.editable ? "" : '<span class="cp__lock">수정 불가</span>') +
            "</div>" +
            '<p class="cp__origin">' +
            esc(part.body) +
            "</p></div>"
          );
        })
        .join("") +
      '<p class="note">ⓘ 판독값(약 이름 · 용법 · 처방일수)은 환자마다 채워집니다 — 여기서는 그 값이 들어갈 문장을 정합니다</p>' +
      "</section>"
    );
  }

  function copySectionsHtml(setId) {
    if (making) return draftCopyHtml();
    if (!copy) return '<section class="box"><p class="note">안내문 문구를 불러오는 중…</p></section>';
    var row = copy.items.filter(function (item) {
      return item.prescription_set_id === setId;
    })[0];
    if (!row) return "";
    return (
      '<section class="box"><div class="box__head">' +
      '<h2 class="box__title">안내문 문구</h2>' +
      '<span class="cp__mark' +
      (row.reviewed ? " cp__mark--done" : "") +
      '">' +
      esc(copyMark(row)) +
      "</span>" +
      '<span class="grow"></span>' +
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
      '<p class="note">ⓘ 판독값(약 이름 · 용법 · 처방일수)은 환자마다 채워집니다 — 여기서는 그 값이 들어갈 문장을 정합니다</p>' +
      "</section>"
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
      var on = !!opened[head.getAttribute("data-fold")];
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
          '<p class="rail__none">대표 처방 목록을 불러오지 못했습니다</p>';
      });
  }

  function loadSet(id) {
    var mine = ++loadSeq;
    pickedId = id;
    picked = null;
    saying = "";
    copyOpen = null;
    render();

    /* **문구도 함께 받아 둔다.** 처방 상세 맨 아래에 그 처방의 안내문 문구가
       붙으므로, 처방만 받아 오면 그 자리가 계속 「불러오는 중」이다.
       한 번 받으면 다른 처방을 눌러도 그대로 쓴다(응답이 전 처방 것을 담는다). */
    if (!copy) loadCopy();

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
      /* 이름은 안 보낸다 — 서버가 아예 안 받는다(400 INVALID_REQUEST).
         담아 보내면 저장 전체가 죽는다. */
      disease: el("f-disease").value,
      /* **화면에서 걷었지만 값은 그대로 싣는다.** 「적용 시점」은 처방
         이름이 이미 담고 있어(「비잔 (처음)」·「(계속)」) 칸을 없앴다. 그런데
         서버 계약에는 남아 있고, 안 보내면 저장이 막힌다. 있던 값을 그대로
         돌려보내 **저장할 때마다 조용히 기본값으로 되돌아가는 것**을 막는다. */
      phase: picked.phase,
      days_mode: mode,
      days_per_pack: mode === "PACK" && per ? Number(per.value) || null : null,
      /* 화면에서 걷은 두 칸 — 「적용 시점」과 같다. 안 보내면 저장이 막히고,
         빈 값을 보내면 적어 둔 것이 조용히 지워진다. */
      emr_code: picked.emr_code,
      revisit_note: picked.revisit_note,
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

  /* **다시 그리기 전에 화면에 적힌 것을 거둔다.**
     `render()` 는 판을 `picked` 로 되돌려 그린다. 그래서 아직 저장하지 않은
     값은 거두지 않으면 **그 자리에서 소리 없이 사라진다** — 약을 한 줄 적고
     「+ 약 추가」를 누르면 적은 것이 날아가던 것이 이것이었다.
     삭제(`data-drop`)에만 이 방어가 있었고 나머지 셋에는 없었다. */
  /** 아직 서버에 없는 처방 한 판. **서버가 갓 만든 세트와 같은 기본값**이다
   *  (`app/models/catalog.py` 의 필드 기본값). 지어내면 만들자마자 화면이
   *  달라 보인다. */
  function draftSet() {
    return {
      prescription_set_id: null,
      name: "",
      hidden: false,
      disease: "ENDOMETRIOSIS",
      phase: "CONTINUE",
      days_mode: "DAYS",
      days_per_pack: null,
      emr_code: null,
      revisit_note: null,
      check_d15_on: true,
      check_d30_on: false,
      run_out_on: true,
      run_out_before_days: 3,
      drugs: [],
      check_items: [],
    };
  }

  function keepScreen() {
    if (!picked || !canEdit || !el("f-name")) return;
    var kept = planNow();
    /* **초안일 때는 이름도 거둔다.** `planNow()` 는 이름을 안 담는다 — 저장
       계약이 안 받기 때문이다. 그런데 `textHtml` 은 값을 모델에서만 그리므로,
       거두지 않으면 다시 그릴 때마다 친 이름이 빈칸으로 되돌아간다.
       「+ 약 추가」 한 번에 이름이 사라지던 그 함정이다. */
    if (making) kept.name = el("f-name").value;
    picked = Object.assign({}, picked, kept);
  }

  /* **지우지 않고 감춘다.** 지난 진료기록이 이 이름으로 이 처방을 가리키므로
     행이 사라지면 그 진료들의 안내문 문구가 조용히 떨어진다. */
  function hideSet() {
    if (!picked || !canEdit || making) return;
    var to = !picked.hidden;
    saying = to ? "숨기는 중…" : "되살리는 중…";
    render();
    return catalogApi
      .hideSet(picked.prescription_set_id, to)
      .then(function (data) {
        picked = data;
        saying = to ? "숨겼습니다" : "되살렸습니다";
        render();
        return loadSets();
      })
      .catch(function () {
        saying = "바꾸지 못했습니다. 잠시 후 다시 시도해 주세요.";
        render();
      });
  }

  /** 만들기 판을 연다.
   *
   * 초안을 `picked` 에 넣는다 — 본문이 스물세 곳에서 `picked` 를 읽으므로,
   * 따로 모델을 두면 그 전부에 배관을 새로 놔야 한다. `making` 은 「이 판이
   * 아직 서버에 없다」는 깃발로만 남는다.
   */
  function newSet() {
    if (!canEdit) return;
    /* **두 번 누르면 친 것이 전멸한다.** 단추는 만드는 중에도 레일에 서 있다. */
    if (making) return;

    keepScreen(); // 보던 처방에 친 것을 잃지 않는다
    making = true;
    pickedId = null;
    picked = draft || draftSet();
    saying = "";
    render();
    var box = el("f-name");
    if (box) box.focus();
  }

  /** 만들기 판을 닫는다. **친 것은 버리지 않고 들고 있는다** — 잘못 눌러
   *  나갔다가 돌아왔을 때 다시 치게 하면 안 된다. 버리는 길은 「취소」뿐이다. */
  function closeMaking() {
    if (!making) return;
    keepScreen();
    draft = picked;
    making = false;
  }

  /** 저장. **만들기면 두 번 부른다** — 서버가 이름·진단으로 만들고(POST),
   *  나머지 한 판을 얹는다(PUT). 세트 번호가 있어야 나머지를 보낼 수 있다.
   *
   * 실패해도 친 것을 잃지 않는 것이 이 함수의 첫째 일이다. 이름은 만들고
   * 나면 못 바꾸고 세트는 못 지우므로, 반쪽만 만들어지면 되돌릴 길이 없다.
   */
  function save() {
    var createdNew = false;
    if (!picked || !canEdit || busy) return;

    keepScreen();
    var plan = planNow();

    /* **보내기 전에 막는다.** 세트를 만든 뒤에 막히면 이름이 이미 타 버린다.
       `Number("28일")` 은 `NaN` 이라 「빈 값」 검사로는 안 걸린다. */
    if (plan.days_mode === "PACK" && !(plan.days_per_pack > 0)) {
      saying = "한 통이 며칠치인지 적어 주세요";
      return render();
    }
    if (making && !picked.name.trim()) {
      saying = "대표 처방 이름을 적어 주세요";
      return render();
    }

    busy = true;
    saying = making ? "만드는 중…" : "저장 중…";
    render();

    var first = making
      ? catalogApi.createSet(picked.name, plan.disease)
      : Promise.resolve({ prescription_set_id: pickedId });

    return first
      .then(function (made) {
        /* **여기서부터는 세트가 이미 있다.** 뒤가 막혀도 「저장」으로 이어
           한다 — 되돌리기가 아니라 이어 하기다. */
        if (making) {
          createdNew = true;
          making = false;
          draft = null;
          pickedId = made.prescription_set_id;
        }
        return catalogApi.saveSet(pickedId, plan);
      })
      .then(function (data) {
        busy = false;
        picked = data;
        saying = "저장되었습니다";
        render();
        /* **새로 만들었을 때만 다시 받는다.**

           새 처방은 레일 목록에도 문구 판에도 없으니 받아야 한다. 그런데
           그냥 고친 것뿐이면 받을 것이 없다 — 서버가 돌려준 것을 위에서
           이미 `picked` 로 삼았고, 이름은 잠겨 있어 레일 줄도 그대로이며,
           안내문 문구는 이 종점이 손대지 않는다(`saveCopy` 가 따로 있다).

           예전에는 저장할 때마다 둘을 무조건 다시 받았다 — 칸 하나 고칠
           때마다 세트 전체와 문구 전체가 다시 왔다 (`#192` 리뷰 ⑥, 2heej). */
        if (!createdNew) return;
        return Promise.all([loadSets(), loadCopy()]);
      })
      .catch(function (err) {
        busy = false;
        var code = err && err.code;
        if (making) {
          /* 아직 안 만들어졌다 — 친 것이 그대로 있다. */
          saying =
            code === "PRESCRIPTION_SET_EXISTS"
              ? "같은 이름의 대표 처방이 이미 있습니다 (숨긴 것도 포함)"
              : code === "NAME_REQUIRED"
                ? "대표 처방 이름을 적어 주세요"
                : code === "INVALID_REQUEST"
                  ? "적으신 값이 너무 길거나 범위를 벗어났습니다"
                  : "만들지 못했습니다. 잠시 후 다시 시도해 주세요.";
          return render();
        }
        /* **만들어졌는데 나머지가 안 들어갔다.** 이름은 이미 정해졌으니
           「저장」을 다시 누르면 이어진다. 어느 칸이 문제인지 말해 준다 —
           「잠시 후 다시」만 적으면 몇 번을 눌러도 같은 실패가 난다. */
        saying =
          code === "DAYS_PER_PACK_REQUIRED"
            ? "한 통이 며칠치인지 적어 주세요"
            : code === "INVALID_REQUEST"
              ? "적으신 값이 너무 길거나 범위를 벗어났습니다 — 고치고 저장해 주세요"
              : "저장하지 못했습니다. 잠시 후 다시 시도해 주세요.";
        render();
        return loadSets();
      });
  }

  /* ── 문자 문구 (D2-5) ──────────────────────────────────────────── */

  /** 다른 판으로 옮긴다. **치우는 것을 한 곳에 모은다** — 판마다 「무엇을
   *  비울까」를 따로 적으면 판이 늘 때마다 그 목록이 제곱으로 자라고, 하나
   *  빠뜨리면 옛 판의 값이 새 판에 비쳐 보인다. */
  function goGroup(key) {
    closeMaking();
    group = key;
    pickedId = null;
    picked = null;
    templates = null;
    baselines = null;
    saying = "";
    drafts = {};
  }

  function openDrugs() {
    goGroup("drugs");
    render();
    return loadDrugs();
  }

  /** 목록만 다시 받는다. **`goGroup` 을 안 지난다** — 그것이 `saying` 을
   *  지우기 때문이다. 저장 뒤에 이걸 부르면서 판을 여는 함수를 쓰면
   *  「이미 등록돼 있습니다」가 그 자리에서 사라져, 막혔는데 화면이 아무 말도
   *  안 하게 된다. */
  function loadDrugs() {
    return catalogApi
      .drugs()
      .then(function (page) {
        /* 서버가 `{draft, items}` 로 준다 — 제작 중인지도 함께 온다. */
        DRAFT = !!(page && page.draft);
        drugs = (page && page.items) || [];
        render();
      })
      .catch(function () {
        drugs = null;
        saying = "약 목록을 불러오지 못했습니다";
        render();
      });
  }

  /** 판에 적힌 것을 거둔다. `keepScreen()` 과 같은 까닭 — 다시 그리면
   *  `drugs` 로 되돌아가므로, 거두지 않으면 친 것이 그 자리에서 날아간다. */
  function drugsNow() {
    if (!drugs) return [];
    return drugs.map(function (row, i) {
      var name = el2("dg-name", i);
      var freq = el2("dg-freq", i);
      var note = el2("dg-note", i);
      return {
        drug_catalog_id: row.drug_catalog_id,
        name: name ? name.value : row.name,
        frequency: freq ? freq.value : row.frequency,
        note: note ? note.value : row.note,
        hidden: row.hidden,
      };
    });
  }

  function el2(kind, at) {
    return document.querySelector("[data-" + kind + '="' + at + '"]');
  }

  /** 빈 줄을 하나 더한다. **화면에 적힌 것을 먼저 거둔다** — 안 거두면
   *  다시 그릴 때 친 것이 날아간다(대표 처방에서 났던 그 일). */
  function addDrug() {
    if (!canEdit) return;
    drugs = drugsNow().concat([
      { drug_catalog_id: null, name: "", frequency: "", note: "", hidden: false },
    ]);
    saying = "";
    render();
    var box = el2("dg-name", drugs.length - 1);
    if (box) box.focus();
  }

  /** 판을 통째로 저장한다. 새 줄은 등록, 있던 줄은 수정.
   *
   * **줄마다 따로 보낸다** — 한 판을 통째로 받는 종점이 없고, 이름이 겹치면
   * 그 줄만 막혀야지 다른 줄까지 되돌릴 이유가 없다. 다만 어느 줄이 막혔는지
   * 말해 준다: 「저장하지 못했습니다」만 적으면 어디를 고쳐야 할지 모른다.
   */
  function saveDrugs() {
    if (!canEdit || busy) return;
    var plan = drugsNow();
    var blank = plan.filter(function (row) {
      return !row.name.trim();
    });
    if (blank.length) {
      saying = "약 이름을 적어 주세요";
      return render();
    }

    busy = true;
    saying = "저장 중…";
    render();

    return Promise.all(
      plan.map(function (row) {
        return row.drug_catalog_id === null
          ? catalogApi.addDrug(row).catch(function (err) {
              return { failed: row.name, code: err && err.code };
            })
          : catalogApi.saveDrug(row.drug_catalog_id, row).catch(function (err) {
              return { failed: row.name, code: err && err.code };
            });
      }),
    ).then(function (answers) {
      busy = false;
      var bad = answers.filter(function (row) {
        return row && row.failed;
      });
      saying = bad.length
        ? bad[0].code === "DRUG_EXISTS"
          ? "「" + bad[0].failed + "」는 이미 등록돼 있습니다"
          : "「" + bad[0].failed + "」를 저장하지 못했습니다"
        : "저장되었습니다";
      /* 판을 여는 함수가 아니라 **받아 오기만** 부른다 — 위 `saying` 이
         지워지면 안 된다. */
      var told = saying;
      return loadDrugs().then(function () {
        saying = told;
        render();
      });
    });
  }

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
          ? "다른 사람의 것은 수정할 수 없습니다"
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
            ? "다른 사람의 것은 수정할 수 없습니다"
            : "저장하지 못했습니다. 잠시 후 다시 시도해 주세요";
        render();
      });
  }

  /* ── 안내문 문구 (D2-1 · D2-2) ───────────────────────────────────
   *
   * 묶음이 따로 없다. 문구는 처방 상세 맨 아래에 붙는다(`copySectionsHtml`) —
   * 안내문이 그 처방과 처방일수로 만들어지기 때문이다. `openCopy` 와
   * `copyHtml` · `copyPick` 이 여기 있었는데, 레일에서 들어갈 길이 없어져
   * 함께 걷었다. */

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
        /* **저장했으면 닫는다.** 열어 둔 채로 두면 「저장되었습니다」가 뜬
           칸이 아직 고칠 수 있는 상태라, 한 번 더 친 글자가 저장된 줄로
           읽힌다. 실패하면 **열어 둔다** — 친 것을 잃지 않아야 한다. */
        copyOpen = null;
        saying = "저장되었습니다";
        render();
      })
      .catch(function (err) {
        saying =
          err && err.status === 403
            ? "다른 사람의 것은 수정할 수 없습니다"
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
      /* 다른 처방을 고르면 만들기 판을 닫되 **친 것은 들고 간다.** */
      closeMaking();
      group = null;
      templates = null;
      baselines = null;
      var chose = railGroupKey(sets, Number(row.getAttribute("data-set")));
      if (chose) opened[railFoldKey("sets", chose)] = true;
      return loadSet(Number(row.getAttribute("data-set")));
    }

    /* 기타 묶음(기준선·문자 문구)으로 옮길 때도 닫되 친 것은 들고 간다 */
    var chosenGroup = target.closest("[data-group]");
    if (chosenGroup) closeMaking();
    if (chosenGroup && chosenGroup.getAttribute("data-group") === "drugs")
      return openDrugs();
    if (chosenGroup && chosenGroup.getAttribute("data-group") === "sms")
      return openTemplates();
    if (chosenGroup && chosenGroup.getAttribute("data-group") === "baseline")
      return openBaselines();

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
      /* **다른 묶음은 건드리지 않는다.** 누른 것만 뒤집는다. */
      if (opened[key]) delete opened[key];
      else opened[key] = true;
      return showOpen();
    }

    if (target.closest("#set-save")) return save();
    if (target.closest("#set-hide")) return hideSet();
    if (target.closest("#set-new")) return newSet();
    if (target.closest("#dg-add")) return addDrug();
    if (target.closest("#dg-save")) return saveDrugs();
    var hideAt = target.closest("[data-drug-hide]");
    if (hideAt) {
      var at = Number(hideAt.getAttribute("data-drug-hide"));
      drugs = drugsNow();
      drugs[at].hidden = !drugs[at].hidden;
      return render();
    }
    if (target.closest("#make-cancel")) {
      /* **버리는 유일한 길이다.** 나머지는 전부 들고 있는다. */
      making = false;
      draft = null;
      picked = null;
      pickedId = null;
      saying = "";
      return render();
    }

    var editCopyAt = target.closest("[data-edit-copy]");
    if (editCopyAt) {
      keepScreen();
      copyOpen = editCopyAt.getAttribute("data-edit-copy");
      saying = "";
      render();
      /* 열자마자 커서를 넣는다 — 누르고 또 눌러야 하면 두 번 일이다 */
      var box = document.querySelector('[data-copy="' + copyOpen + '"]');
      if (box) box.focus();
      return;
    }
    if (target.closest("[data-cancel-copy]")) {
      /* **문구에 친 것만 버린다.** 다시 그리면 서버에서 받은 값으로 돌아간다 —
         「취소」가 취소가 아니면 안 된다. 다만 무르는 것은 문구뿐이라,
         처방 칸에 적어 둔 것은 거두어 들고 간다. */
      keepScreen();
      copyOpen = null;
      saying = "";
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
      keepScreen();
      picked.drugs = (picked.drugs || []).concat([
        { name: "", frequency: "", note: "" },
      ]);
      return render();
    }

    var drop = target.closest("[data-drop]");
    if (drop) {
      keepScreen();
      picked.drugs.splice(Number(drop.getAttribute("data-drop")), 1);
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
    keepScreen();
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
    /* **설정은 스탭도 고친다** (2026-09-02 회의). 원문 D2-2 의 「의사 계정만」이
       여기였다. 남는 규칙은 「남의 것을 고치지 않는다」 하나이고 그것은
       서버가 소유권으로 막는다 — 화면이 아니라 서버가 판정한다.

       **안내문 승인은 여전히 의사만이다.** 그건 설정이 아니라 진료 판단이라
       `guides.py` 가 따로 막는다. */
    canEdit = (me.roles || []).some(function (role) {
      return role === "doctor" || role === "staff";
    });
    /* 안내문 목록도 같이 — 레일이 처음부터 진도를 보여 준다 */
    return Promise.all([loadSets(), loadCopy()]);
  });
})();
