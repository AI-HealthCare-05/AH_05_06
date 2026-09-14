/* 직원을 **고치는 판** — A1-3 (KEY-330).
 *
 * 화면이 지키는 것 둘.
 *
 *   ① **고를 수 없는 조합을 못 고르게 한다** — 만들 때와 같은 다섯뿐이다.
 *      체크상자 셋을 두면 `의사+스탭` 을 만들 수 있는 것처럼 보이는데 서버가
 *      400 을 준다. 「누를 수 있는데 안 되는 것」이 이 저장소가 없애 온 모양이다.
 *   ② **비워 둔 비밀번호는 안 보낸다** — 빈 글자를 보내면 형식 검사에 막히는데,
 *      관리자가 뜻한 것은 「그대로 두기」다.
 *
 * 그리고 막힌 이유가 **그 자리에 말이 되어** 떠야 한다. 마지막 관리자는
 * 되돌릴 길이 화면에 없어서, 왜 막혔는지와 무엇을 먼저 할지를 같이 말한다.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { load } = require("./browser-shim");
const { read, bareCode, codeOnly } = require("./source");

function box() {
  return load("api", "admin-staff");
}

const A_STAFF = {
  staff_id: 7,
  login_id: "doctor01",
  name: "박연",
  roles: ["doctor"],
  status: "active",
  must_change_password: false,
};

test("수정 판이 지금 값으로 서 있다", () => {
  const admin = box();

  const html = admin.staffEditHtml(A_STAFF);

  assert.match(html, /박연 · doctor01/, "누구를 고치는지가 안 보인다");
  assert.match(html, /<option value="doctor" selected>/, "지금 역할이 안 골라져 있다");
  assert.match(html, /<option value="active" selected>재직<\/option>/);
});

test("고를 수 있는 조합은 **만들 때와 같은 다섯**뿐이다", () => {
  const admin = box();

  const html = admin.staffEditHtml(A_STAFF);
  const offered = [...html.matchAll(/<option value="([a-z+]+)"/g)].map((m) => m[1]);
  const roles = offered.filter((key) => key !== "active" && key !== "left");

  assert.deepEqual(
    roles.join(","),
    admin.STAFF_ROLE_CHOICES.map((choice) => choice.key).join(","),
    "수정 판이 추가 판과 다른 조합을 준다",
  );
  assert.ok(!roles.includes("doctor+staff"), "만들 수 없는 조합을 고를 수 있다");
});

test("모르는 조합이면 **아무것도 안 골라 둔다** — 지어내서 덮지 않는다", () => {
  /* 옛 자료나 직접 넣은 값이 올 수 있다. 가장 비슷한 것을 골라 두면 관리자가
     그대로 저장해 엉뚱한 역할로 덮는다. */
  const admin = box();

  assert.equal(admin.staffRoleKeyOf(["doctor", "staff"]), "");
  assert.equal(admin.staffRoleKeyOf(["admin", "staff"]), "staff+admin", "차례가 달라도 같은 조합이다");
});

test("모르는 조합이면 **빈 자리가 서 있다** — 첫 옵션이 골라진 것처럼 보이면 안 된다", () => {
  /* `selected` 를 아무 데도 안 붙이면 브라우저는 **첫 옵션을 고른 것처럼**
     그린다. 관리자가 손도 안 대고 저장을 누르면 목록 맨 위 조합(`doctor`)으로
     조용히 덮인다 — 「지어내서 덮지 않는다」가 화면에서 뒤집히는 자리다
     (이희진 님 #294 리뷰). */
  const admin = box();

  const html = admin.staffEditHtml({ ...A_STAFF, roles: ["doctor", "staff"] });

  assert.match(html, /<option value="" disabled selected>역할을 고르세요<\/option>/, "빈 자리가 없다");
  assert.doesNotMatch(
    html,
    /<option value="(doctor|staff|admin)[^"]*" selected>/,
    "모르는 조합인데 역할 하나가 골라져 있다",
  );
});

test("역할을 안 고르면 **저장을 안 보낸다**", () => {
  /* 빈 역할을 그대로 보내면 서버가 422 로 막는다. 막히는 것은 맞지만, 무엇을
     해야 하는지는 화면이 먼저 말해야 한다. */
  const code = codeOnly(read("js/admin.js"));
  const at = code.indexOf("function saveStaffEdit");
  assert.notEqual(at, -1, "저장 함수가 없다 — 검사가 헛돈다");

  const body = code.slice(at);
  assert.match(body, /if \(!chosen\)/, "빈 역할을 그대로 보낸다");
  assert.match(body, /역할을 먼저 골라 주세요/, "왜 막혔는지를 안 말한다");

  const gate = body.indexOf("if (!chosen)");
  const sent = body.indexOf("updateStaff(");
  assert.notEqual(sent, -1, "저장을 보내는 자리를 못 찾았다 — 검사가 헛돈다");
  assert.ok(gate < sent, "보낸 뒤에 막는다 — 그때는 이미 갔다");
});

test("퇴사자는 판이 퇴사로 서 있다", () => {
  const admin = box();

  const html = admin.staffEditHtml({ ...A_STAFF, status: "left" });

  assert.match(html, /<option value="left" selected>퇴사<\/option>/);
});

test("줄마다 [수정] 이 있고 한 번에 하나만 펼친다", () => {
  const admin = box();

  admin.staffListOpen(null);
  const closed = admin.staffListHtml([A_STAFF]);
  assert.match(closed, /data-edit-staff="7"/);
  assert.ok(!/staffs__editrow/.test(closed), "안 눌렀는데 판이 펼쳐져 있다");

  admin.staffListOpen(7);
  const opened = admin.staffListHtml([A_STAFF, { ...A_STAFF, staff_id: 8, login_id: "staff01" }]);
  assert.equal((opened.match(/staffs__editrow/g) || []).length, 1, "판이 둘 열렸다");
});

test("비워 둔 비밀번호는 **안 보낸다**", () => {
  /* 빈 글자를 보내면 서버 형식 검사가 막는데, 관리자가 뜻한 것은 그대로 두기다. */
  const code = bareCode(read("js/admin.js"));

  assert.match(code, /if \(password\) body\.password = password;/);
});

test("마지막 관리자가 막히면 **무엇을 먼저 할지**까지 말한다", () => {
  const admin = box();

  const said = admin.staffEditSaying({ code: "LAST_ADMIN", status: 409 });

  assert.match(said, /마지막 관리자/);
  assert.match(said, /먼저/, "왜 막혔는지만 말하고 어떻게 풀지를 안 말한다");
});

test("고칠 때 부르는 곳은 그 직원 한 줄이다", () => {
  const code = codeOnly(read("js/admin-staff.js"));

  assert.match(code, /"\/admin\/staffs\/" \+ encodeURIComponent\(staffId\)/);
  assert.match(code, /method: "PATCH"/);
});

test("A1-3 이 이제 「화면 없음」 카드가 아니다", () => {
  /* 화면이 제 상태를 적어 두는 자리다 — 붙여 놓고 카드를 안 걷으면
     「아직 없다」고 스스로 말하는 화면이 된다. */
  const code = codeOnly(read("js/admin.js"));

  assert.ok(!/remainingFrameCards\(\["A1-3"\]\)/.test(code), "직원 칸이 아직 A1-3 을 못 한다고 말한다");
});

test("목록도 **추가와 같은 카드**에 담긴다", () => {
  /* 하나만 담기면 한 화면 안에서 담긴 것과 안 담긴 것이 섞여 눈이 자리를
     새로 찾는다 — 표가 바탕 위에 그냥 떠 있었다. */
  const admin = box();

  const filled = admin.staffListHtml([A_STAFF]);
  const empty = admin.staffListHtml([]);

  assert.match(filled, /class="staff-card"/, "목록이 카드 밖에 있다");
  assert.match(empty, /class="staff-card"/, "비었을 때만 카드 밖으로 나간다");
});

test("불러오는 중에도 카드가 서 있다", () => {
  /* 담겼다 안 담겼다 하면 목록이 도착하는 순간 화면이 한 번 튄다. */
  const code = codeOnly(read("js/admin.js"));
  const first = code.slice(code.indexOf("function renderStaffBody"), code.indexOf("wireStaffForm()"));

  assert.match(first, /staff-card/, "불러오는 동안에는 카드가 없다");
});
