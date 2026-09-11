/* 어드민 — 직원 목록(A1-1)과 직원 추가(A1-2). KEY-321.
 *
 * 이 화면은 오래 골격만이었다. `Staff` 모델과 역할 조합은 있는데 **읽고 쓰는
 * 길이 없어서**(`GET /staffs` 도 `POST /staffs` 도 없었다) 본문이 「무엇이
 * 있어야 되는지」만 말했다 (KEY-176 · KEY-234).
 *
 * **그리는 함수와 부르는 함수를 나눠 둔다.** 아래 `…Html` 들은 값을 받아
 * 문자열을 돌려주는 순수 함수라 검사가 그대로 부를 수 있다. DOM 을 만지는
 * 것은 `admin.js` 가 한다 — 검사 껍데기(`tests/browser-shim.js`)는 일부러
 * 그리기를 막아 두었고, 그 선을 넘으면 「검사에서는 되는데 브라우저에서는
 * 안 되는」 거리가 벌어진다.
 */

/* 화면에 쓰는 역할 이름. 서버는 `doctor`·`staff`·`admin` 을 그대로 준다 —
   화면에 영문이 그대로 뜨는 것은 A1-1 이 예전에 고쳤던 자리다. */
var STAFF_ROLE_LABEL = { doctor: "의사", staff: "스탭", admin: "어드민" };

/* **고를 수 있는 조합은 다섯뿐이다** — `app/core/rbac.py` 의
   `VALID_ROLE_COMBINATIONS` 와 같다. 체크상자 셋을 두고 마음대로 조합하게
   하면 화면은 `의사+스탭` 을 만들 수 있는 것처럼 보이는데 서버가 400 을 준다 —
   **누를 수 있는데 안 되는 것**이 이 저장소가 없애 온 모양이다. 고를 수 없게
   두면 그 400 은 화면에서 아예 안 생긴다. */
var STAFF_ROLE_CHOICES = [
  { key: "staff", roles: ["staff"], label: "스탭" },
  { key: "doctor", roles: ["doctor"], label: "의사" },
  { key: "admin", roles: ["admin"], label: "어드민" },
  { key: "staff+admin", roles: ["staff", "admin"], label: "스탭 + 어드민" },
  { key: "doctor+admin", roles: ["doctor", "admin"], label: "의사 + 어드민" },
];

function staffRolesFor(key) {
  for (var i = 0; i < STAFF_ROLE_CHOICES.length; i++) {
    if (STAFF_ROLE_CHOICES[i].key === key) return STAFF_ROLE_CHOICES[i].roles.slice();
  }
  return [];
}

function staffRolesLabel(roles) {
  var out = [];
  for (var i = 0; i < (roles || []).length; i++) {
    out.push(STAFF_ROLE_LABEL[roles[i]] || roles[i]);
  }
  return out.join(" · ");
}

/* 첫 로그인 전인지 · 그만뒀는지. **둘 다 보인다.**
   퇴사자를 목록에서 지우면 「그만둔 사람이 만든 안내문」의 작성자가 화면에서
   사라진다 — 지난 기록이 그 이름을 가리키고 있다. */
function staffStateLabel(row) {
  if (row.status === "left") return "퇴사";
  if (row.must_change_password) return "첫 로그인 전";
  return "";
}

function staffRowHtml(row) {
  var state = staffStateLabel(row);
  return (
    '<tr class="staffs__row' +
    (row.status === "left" ? " staffs__row--left" : "") +
    '">' +
    "<td>" +
    esc(row.name) +
    "</td>" +
    "<td>" +
    esc(row.login_id) +
    "</td>" +
    "<td>" +
    esc(staffRolesLabel(row.roles)) +
    "</td>" +
    "<td>" +
    (state ? '<span class="staffs__state">' + esc(state) + "</span>" : "") +
    "</td>" +
    '<td class="staffs__act"><button class="button-ghost button-ghost--sm" type="button" data-edit-staff="' +
    esc(row.staff_id) +
    '">수정</button></td>' +
    "</tr>" +
    (open === row.staff_id ? staffEditHtml(row) : "")
  );
}

/* **고른 조합의 이름**을 돌려준다 — 저장된 역할로 고름칸의 기본값을 잡는다.
   모르는 조합(옛 자료·직접 넣은 값)이면 빈 값이라, 고름칸이 아무것도 안 고른
   채로 서고 관리자가 새로 고르게 된다 — 지어내서 엉뚱한 역할로 덮지 않는다. */
function staffRoleKeyOf(roles) {
  var want = (roles || []).slice().sort().join(",");
  for (var i = 0; i < STAFF_ROLE_CHOICES.length; i++) {
    if (STAFF_ROLE_CHOICES[i].roles.slice().sort().join(",") === want) return STAFF_ROLE_CHOICES[i].key;
  }
  return "";
}

/* 줄 아래로 펼쳐지는 수정 판 — A1-3 (KEY-330).
 *
 * **모달이 아니라 그 줄 아래다.** 누구를 고치는지가 위에 그대로 보여야 한다 —
 * 관리자 화면에서 엉뚱한 사람의 역할을 바꾸는 것이 제일 나쁜 사고다.
 *
 * 비밀번호 칸은 **비워 두면 안 바뀐다.** 셋을 한 판에 두고 「준 것만 바꾼다」는
 * 서버 규칙을 그대로 보인다. */
function staffEditHtml(row) {
  var options = "";
  var now = staffRoleKeyOf(row.roles);
  /* **모르는 조합이면 빈 자리를 먼저 세운다** (이희진 님 #294 리뷰).
     `selected` 를 아무 데도 안 붙이면 브라우저가 **첫 옵션을 고른 것처럼**
     보여 준다. 관리자가 손도 안 댄 채 저장을 누르면 목록 맨 위 조합으로
     조용히 덮인다 — 「지어내서 덮지 않는다」는 규칙이 화면에서 뒤집힌다.
     `disabled` 라 다시 고를 수 없고, 값이 비어 있어 저장도 막힌다. */
  if (!now) {
    options += '<option value="" disabled selected>역할을 고르세요</option>';
  }
  for (var i = 0; i < STAFF_ROLE_CHOICES.length; i++) {
    var choice = STAFF_ROLE_CHOICES[i];
    options +=
      '<option value="' + esc(choice.key) + '"' + (choice.key === now ? " selected" : "") + ">" +
      esc(choice.label) +
      "</option>";
  }
  var left = row.status === "left";
  return (
    '<tr class="staffs__editrow"><td colspan="5"><form class="staffedit" id="staff-edit">' +
    '<p class="staffedit__who">' +
    esc(row.name) +
    " · " +
    esc(row.login_id) +
    "</p>" +
    '<div class="staff-add__fields">' +
    '<label class="staff-add__field"><span class="staff-add__label">역할</span>' +
    '<select class="staff-add__input" id="staff-edit-roles">' +
    options +
    "</select></label>" +
    '<label class="staff-add__field"><span class="staff-add__label">재직</span>' +
    '<select class="staff-add__input" id="staff-edit-status">' +
    '<option value="active"' + (left ? "" : " selected") + ">재직</option>" +
    '<option value="left"' + (left ? " selected" : "") + ">퇴사</option>" +
    "</select></label>" +
    '<label class="staff-add__field"><span class="staff-add__label">새 비밀번호</span>' +
    '<input class="staff-add__input" id="staff-edit-password" type="text" autocomplete="off" />' +
    '<span class="staff-add__hint">비워 두면 안 바뀝니다 · 주면 첫 로그인에서 본인이 바꿉니다</span></label>' +
    "</div>" +
    '<p class="staffedit__say" id="staff-edit-say"></p>' +
    '<div class="staffedit__acts">' +
    '<button class="button-ghost button-ghost--sm" type="button" data-edit-staff-close>닫기</button>' +
    '<button class="button-primary" type="submit" id="staff-edit-go">저장</button>' +
    "</div></form></td></tr>"
  );
}

/* 지금 펼쳐 놓은 줄. **한 번에 하나만** 연다 — 여럿을 열어 두면 어느 판의
   「저장」인지가 흐려진다. */
var open = null;

function staffListOpen(staffId) {
  open = staffId;
}

function staffOpenNow() {
  return open;
}

function staffListHtml(staffs) {
  if (!staffs || !staffs.length) {
    /* 이 자리는 실제로 안 온다 — 목록을 보려면 로그인한 관리자가 있어야 하고
       그 계정이 이미 한 줄이다. 그래도 「비어 있다」와 「못 불러왔다」는 다른
       말이라 갈라 둔다. */
    return '<section class="staff-card"><h2 class="staff-card__title">직원 목록</h2>' +
      '<p class="pane__lead">등록된 직원이 없습니다.</p></section>';
  }
  var rows = "";
  for (var i = 0; i < staffs.length; i++) rows += staffRowHtml(staffs[i]);
  /* **아래 「직원 추가」와 같은 카드에 담는다.** 표만 바탕에 그대로 두면 한
     화면 안에서 담긴 것과 안 담긴 것이 섞여 눈이 자리를 새로 찾는다. */
  return (
    '<section class="staff-card"><h2 class="staff-card__title">직원 목록</h2>' +
    '<table class="staffs">' +
    "<thead><tr><th>이름</th><th>아이디</th><th>역할</th><th>상태</th><th></th></tr></thead>" +
    "<tbody>" +
    rows +
    "</tbody>" +
    "</table></section>"
  );
}

function staffFormHtml() {
  var options = "";
  for (var i = 0; i < STAFF_ROLE_CHOICES.length; i++) {
    var choice = STAFF_ROLE_CHOICES[i];
    options += '<option value="' + esc(choice.key) + '">' + esc(choice.label) + "</option>";
  }
  /* **`.field` 계열을 안 쓴다.** 그 이름은 `auth.css` · `patients.css` ·
     `ocr-review.css` 에 각각 있는데 어드민 화면은 셋 다 안 싣는다 — 그대로
     쓰면 모양 없이 뜬다(실측). 네 번째 사본을 만드는 대신 이 화면 이름으로
     짓고 `admin.css` 가 갖는다. */
  return (
    '<form class="staff-add" id="staff-add">' +
    '<h2 class="staff-add__title">직원 추가</h2>' +
    '<div class="staff-add__fields">' +
    '<label class="staff-add__field"><span class="staff-add__label">이름</span>' +
    '<input class="staff-add__input" id="staff-name" name="name" maxlength="50" required />' +
    '<span class="staff-add__hint">&nbsp;</span></label>' +
    '<label class="staff-add__field"><span class="staff-add__label">아이디</span>' +
    '<input class="staff-add__input" id="staff-login-id" name="login_id" maxlength="50" ' +
    'autocomplete="off" inputmode="latin" required />' +
    '<span class="staff-add__hint">영문 소문자와 숫자만, 네 자 이상 · 만든 뒤에는 못 바꿉니다</span></label>' +
    '<label class="staff-add__field"><span class="staff-add__label">초기 비밀번호</span>' +
    '<input class="staff-add__input" id="staff-password" name="password" type="password" ' +
    'autocomplete="new-password" required />' +
    '<span class="staff-add__hint">영문 · 숫자 · 기호를 섞어 8자 이상 · 첫 로그인에서 본인이 바꿉니다</span></label>' +
    '<label class="staff-add__field"><span class="staff-add__label">역할</span>' +
    '<select class="staff-add__input" id="staff-roles" name="roles">' +
    options +
    "</select>" +
    '<span class="staff-add__hint">&nbsp;</span></label>' +
    "</div>" +
    '<div class="staff-add__foot">' +
    '<p class="staff-add__say" id="staff-say" role="status" aria-live="polite"></p>' +
    '<button class="button-primary" type="submit" id="staff-add-go">추가</button>' +
    "</div>" +
    "</form>"
  );
}


/* 서버가 준 오류 하나를 사람 말 한 줄로 — `errorMessage` 규칙을 쓴다.
   좁은 것을 먼저 적는다. */
function staffCreateSaying(error) {
  return errorMessage(
    error,
    [
      { code: "LOGIN_ID_TAKEN", say: "이미 쓰고 있는 아이디입니다. 다른 아이디로 해 주세요." },
      { code: "INVALID_ROLE_COMBINATION", say: "고를 수 없는 역할 조합입니다." },
      { code: "INVALID_REQUEST", say: "적어 주신 값 중에 규칙에 안 맞는 것이 있습니다." },
      { status: 403, say: "직원 계정을 관리할 권한이 없습니다." },
    ],
    "직원을 추가하지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
  );
}

function listStaffs() {
  return request("/admin/staffs");
}

function updateStaff(staffId, body) {
  return request("/admin/staffs/" + encodeURIComponent(staffId), { method: "PATCH", body: body });
}

function staffEditSaying(error) {
  return errorMessage(
    error,
    [
      /* **이 의원에 관리자가 없어지는 것**을 서버가 막는다. 되돌릴 길이 화면에
         없어서, 왜 막혔는지와 무엇을 먼저 해야 하는지를 같이 말한다. */
      { code: "LAST_ADMIN", say: "이 의원의 마지막 관리자입니다 — 다른 분에게 어드민을 먼저 주세요." },
      { code: "INVALID_ROLE_COMBINATION", say: "고를 수 없는 역할 조합입니다." },
      { code: "INVALID_REQUEST", say: "바꿀 것을 하나는 골라 주세요 — 역할 · 재직 · 비밀번호." },
      { status: 404, say: "그 직원을 찾을 수 없습니다. 목록을 다시 불러와 주세요." },
      { status: 403, say: "직원 계정을 관리할 권한이 없습니다." },
    ],
    "저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
  );
}

function createStaff(body) {
  return request("/admin/staffs", { method: "POST", body: body });
}
