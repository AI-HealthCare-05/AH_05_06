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
    "</tr>"
  );
}

function staffListHtml(staffs) {
  if (!staffs || !staffs.length) {
    /* 이 자리는 실제로 안 온다 — 목록을 보려면 로그인한 관리자가 있어야 하고
       그 계정이 이미 한 줄이다. 그래도 「비어 있다」와 「못 불러왔다」는 다른
       말이라 갈라 둔다. */
    return '<p class="pane__lead">등록된 직원이 없습니다.</p>';
  }
  var rows = "";
  for (var i = 0; i < staffs.length; i++) rows += staffRowHtml(staffs[i]);
  return (
    '<table class="staffs">' +
    "<thead><tr><th>이름</th><th>아이디</th><th>역할</th><th>상태</th></tr></thead>" +
    "<tbody>" +
    rows +
    "</tbody>" +
    "</table>"
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

function createStaff(body) {
  return request("/admin/staffs", { method: "POST", body: body });
}
