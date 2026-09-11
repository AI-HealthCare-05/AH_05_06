/* **의원 정보 (A1-4)** — KEY-331.
 *
 * 이 칸이 골격만인 동안 그 빈자리가 환자에게 나갔다: 소진·재진 문자의
 * `{예약링크}` 를 채울 데가 없어서 발송 코드가 그 환자의 안내문 링크를 대신
 * 넣었다. 서버 쪽은 `app/tests/messages/test_key331_booking_link.py` 가 잰다.
 *
 * 여기서 재는 것 넷.
 *
 *   못 바꾸는 것   의원 이름은 칸이 없다 — 없는 칸은 못 보낸다
 *   지움          빈칸은 `null` 로 나간다. 「안 보냄」과 헷갈리지 않게
 *   미리 말하기    예약 링크가 비면 문자가 보류된다는 것을 **적는 자리**에서 말한다
 *   화면과 서버    고칠 수 있는 칸 목록이 서버 `EDITABLE` 과 같다
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function box() {
  return load("api", "session", "admin-clinic");
}

const FILLED = {
  hospital_id: 1,
  name: "도로시여성의원",
  phone: "02-123-4567",
  address: "서울시 강남구 어딘가 1층",
  booking_url: "https://booking.example.com/dorothy",
};

const EMPTY = { hospital_id: 1, name: "도로시여성의원", phone: null, address: null, booking_url: null };

/* ── 고칠 수 있는 칸 ────────────────────────────────────────────────── */

test("**화면이 고치는 칸이 서버가 고치는 칸과 같다**", () => {
  const { CLINIC_FIELDS } = box();
  const keys = CLINIC_FIELDS.map((one) => one.key).sort();
  assert.deepEqual(keys, ["address", "booking_url", "name", "phone"]);

  /* 서버가 못박은 목록(`EDITABLE`)과 견준다 — 한쪽만 늘면 화면이 보낸 칸을
     서버가 조용히 버리거나, 화면에 없는 칸이 서버에만 생긴다. */
  const service = read("../app/services/admin_hospital.py");
  const listed = service.slice(service.indexOf("EDITABLE = ("), service.indexOf(")", service.indexOf("EDITABLE = (")));
  for (const key of keys) assert.ok(listed.includes(`"${key}"`), `서버 EDITABLE 에 ${key} 가 없다`);
});

test("**의원 이름도 여기서 고친다** — KEY-319 인수조건", () => {
  /* 처음에는 「배포 한 판의 정체」라 칸을 안 두었는데, 이미 나간 문자는
     `sent_body` 에 보낸 그대로 남아 앞뒤가 갈리지 않는다 (이희진 님 #295 리뷰). */
  const { CLINIC_FIELDS, clinicFormHtml } = box();
  assert.ok(CLINIC_FIELDS.some((one) => one.key === "name"), "이름 칸이 없다");

  const html = clinicFormHtml(FILLED);
  assert.ok(html.includes("도로시여성의원"), "의원 이름이 어디에도 안 보인다");
  assert.match(html, /name="name"[^>]*value="도로시여성의원"/, "저장된 이름이 칸에 안 들어 있다");
});

test("**칸마다 제 길이로 막는다** — 서버 검사와 같은 수다", () => {
  const { CLINIC_FIELDS, clinicFormHtml } = box();
  const byKey = {};
  for (const one of CLINIC_FIELDS) byKey[one.key] = one.max;

  assert.deepEqual(byKey, { name: 100, phone: 20, address: 200, booking_url: 500 });

  const html = clinicFormHtml(FILLED);
  assert.match(html, /name="name"[^>]*maxlength="100"/, "이름 칸이 100자에서 안 막힌다");
});

test("**이름은 비울 수 없다** — 다른 셋과 다른 자리다", () => {
  /* 빈칸을 `null` 로 접어 보내면 서버가 400 으로 막는다. 막히는 것은 맞지만
     무엇을 해야 하는지는 화면이 먼저 말해야 한다. */
  const { clinicNameProblem, clinicPayload } = box();

  assert.ok(clinicNameProblem({ name: "   " }), "비었는데 아무 말도 안 한다");
  assert.ok(clinicNameProblem({ name: "가".repeat(101) }), "100자를 넘겼는데 통과한다");
  assert.equal(clinicNameProblem({ name: "도로시여성의원" }), "");

  /* 접지 않는다 — `null` 은 「지운다」인데 이름에는 그런 뜻이 없다. */
  assert.strictEqual(clinicPayload({ name: "" }).name, "");
});

/* ── 보내는 몸 ──────────────────────────────────────────────────────── */

test("**빈칸은 `null` 로 나간다** — 「지웠다」와 「안 보냈다」를 가른다", () => {
  const { clinicPayload } = box();
  const body = clinicPayload({ phone: "02-123-4567", address: "", booking_url: "   " });

  assert.equal(body.phone, "02-123-4567");
  assert.strictEqual(body.address, null);
  assert.strictEqual(body.booking_url, null, "공백만 적은 것이 값으로 나갔다");
});

test("**넷을 늘 함께 보낸다** — 한 폼에 있는 것이 곧 보내려는 전부다", () => {
  const { clinicPayload } = box();
  const body = clinicPayload({ phone: "02-123-4567" });

  assert.deepEqual(Object.keys(body).sort(), ["address", "booking_url", "name", "phone"]);
});

test("앞뒤 공백을 걷어서 보낸다 — 서버가 접기 전에 화면이 먼저 접는다", () => {
  const { clinicPayload } = box();
  assert.equal(clinicPayload({ booking_url: "  https://a.example/b  " }).booking_url, "https://a.example/b");
});

/* ── 적는 자리에서 미리 말한다 ──────────────────────────────────────── */

test("**예약 링크가 비면 문자가 보류된다고 적는 자리에서 말한다**", () => {
  const { clinicBookingWarning } = box();
  const said = clinicBookingWarning(EMPTY);

  assert.ok(said, "비어 있는데 아무 말도 안 한다");
  assert.ok(said.includes("보류"), "무슨 일이 생기는지 안 말한다");
});

test("채워져 있으면 경고하지 않는다 — 늘 뜨는 경고는 안 읽힌다", () => {
  const { clinicBookingWarning } = box();
  assert.equal(clinicBookingWarning(FILLED), "");
});

test("아직 못 불러온 상태를 「비었다」로 읽지 않는다", () => {
  const { clinicBookingWarning } = box();
  /* `null`·`undefined` 는 「의원 정보가 없다」가 아니라 「아직 모른다」인데,
     이 함수는 그 둘을 가르지 않는다 — 가르는 것은 화면이다(`admin.js` 가
     실패하면 폼 자체를 안 그린다). 여기서는 죽지 않는 것만 잰다. */
  assert.doesNotThrow(() => clinicBookingWarning(null));
  assert.doesNotThrow(() => clinicBookingWarning(undefined));
});

/* ── 그리는 것 ──────────────────────────────────────────────────────── */

test("저장된 값이 칸에 들어가 있다 — 고치러 왔는데 빈칸이면 지우게 된다", () => {
  const { clinicFormHtml } = box();
  const html = clinicFormHtml(FILLED);

  assert.ok(html.includes('value="02-123-4567"'));
  assert.ok(html.includes('value="https://booking.example.com/dorothy"'));
});

test("`null` 인 칸은 빈 값으로 뜬다 — 「null」이라는 글자가 뜨지 않는다", () => {
  const { clinicFormHtml } = box();
  const html = clinicFormHtml(EMPTY);

  assert.ok(!html.includes("null"), "null 이 화면에 글자로 떴다");
  assert.ok(html.includes('value=""'));
});

test("**따옴표가 든 값이 마크업을 깨지 않는다**", () => {
  const { clinicFormHtml } = box();
  const html = clinicFormHtml({ ...FILLED, address: '서울시 "큰"따옴표 <b>구</b>' });

  assert.ok(!html.includes("<b>구</b>"), "태그가 그대로 들어갔다");
  assert.ok(html.includes("&quot;"), "따옴표가 안 걸러졌다");
});

/* ── 실패를 사람 말로 ───────────────────────────────────────────────── */

test("서버가 준 오류를 사람 말 한 줄로 바꾼다", () => {
  const { clinicSaveSaying, clinicLoadSaying } = box();

  assert.ok(clinicSaveSaying({ code: "INVALID_REQUEST" }).includes("예약 링크"));
  assert.ok(clinicSaveSaying({ status: 403 }).includes("권한"));
  assert.ok(clinicLoadSaying({ status: 403 }).includes("권한"));
  /* 모르는 오류도 코드를 그대로 보이지 않는다 */
  assert.ok(!clinicSaveSaying({ code: "WAT" }).includes("WAT"));
});

/* ── 화면이 그 길을 실제로 부르는가 ─────────────────────────────────── */

test("**어드민 화면이 의원 정보 칸을 그린다** — 메뉴만 있고 본문이 없으면 안 된다", () => {
  const admin = codeOnly(read("../frontend/js/admin.js"));

  assert.ok(admin.includes('current === "clinic"'), "「의원 정보」 칸이 프레임 카드 그대로다");
  assert.ok(admin.includes("clinicFormHtml("), "폼을 그리지 않는다");
  assert.ok(admin.includes("updateHospital("), "저장하는 길이 없다");
});

test("저장에 성공하면 **서버가 돌려준 값으로 다시 그린다**", () => {
  /* 서버가 접은 값(공백 → 빈칸)이 화면에 남아 있으면 다음에 누른 사람이 그
     공백을 다시 보낸다. 경고 문구도 그때 새로 서야 한다. */
  const admin = codeOnly(read("../frontend/js/admin.js"));
  const save = admin.slice(admin.indexOf("function saveClinic"), admin.indexOf("function renderBody"));

  assert.ok(save.includes("clinicFormHtml(info)"), "응답으로 다시 그리지 않는다");
});

test("저장하는 동안 단추를 잠근다 — 두 번 눌리는 자리다", () => {
  const admin = codeOnly(read("../frontend/js/admin.js"));
  const save = admin.slice(admin.indexOf("function saveClinic"), admin.indexOf("function renderBody"));

  assert.ok(save.includes("go.disabled = true"), "저장 중에 단추가 열려 있다");
  assert.ok(save.includes("go.disabled = false"), "실패한 뒤 단추가 잠긴 채로 남는다");
});

test("**못 불러왔을 때 빈 폼을 그리지 않는다**", () => {
  /* 못 불러온 것을 「아직 안 적었다」로 보이면, 관리자는 이미 적어 둔 값 위에
     빈칸을 저장한다 — 그 순간 소진·재진 문자가 전부 보류된다. */
  const admin = codeOnly(read("../frontend/js/admin.js"));
  const render = admin.slice(admin.indexOf("function renderClinicBody"), admin.indexOf("function wireClinicForm"));
  const failed = render.slice(render.indexOf(".catch("));

  assert.ok(failed.includes("clinicLoadSaying"), "실패를 사람 말로 안 적는다");
  assert.ok(!failed.includes("clinicFormHtml"), "못 불러왔는데 폼을 그린다");
});

/* ── 목업도 같은 규칙을 지키는가 ────────────────────────────────────── */

/* 목업이 무엇이든 받아 주면 화면이 그 무엇이든 보내게 되고, 그 차이는
   실서버에서만 400 으로 드러난다 — 시연에서는 되는데 배포하면 안 되는 모양이다. */
function mockBox() {
  return load("api", "session", "admin-clinic", { search: "?mock=1" });
}

test("**목업도 빈 예약 링크로 시작한다** — 경고를 보고 채우는 것이 이 화면이다", async () => {
  const { getHospital } = mockBox();
  const info = await getHospital();

  assert.strictEqual(info.booking_url, null);
  assert.ok(info.name, "의원 이름이 없다");
});

test("목업이 저장한 값을 다시 준다", async () => {
  const { getHospital, updateHospital } = mockBox();
  await updateHospital({ phone: "02-123-4567", address: null, booking_url: "https://a.example/b" });
  const info = await getHospital();

  assert.equal(info.phone, "02-123-4567");
  assert.equal(info.booking_url, "https://a.example/b");
});

test("**목업도 `javascript:` 를 거절한다** — 실서버에서만 막히면 시연에서 안 드러난다", async () => {
  const { updateHospital } = mockBox();
  await assert.rejects(() => updateHospital({ booking_url: "javascript:alert(1)" }), (error) => {
    assert.equal(error.status, 400);
    return true;
  });
});

test("목업도 빈 몸과 모르는 칸을 거절한다", async () => {
  const { updateHospital } = mockBox();
  await assert.rejects(() => updateHospital({}), (e) => e.status === 400);
  await assert.rejects(() => updateHospital({ name: "다른의원" }), (e) => e.status === 400);
});

test("목업도 안 보낸 칸을 안 지운다", async () => {
  const { getHospital, updateHospital } = mockBox();
  await updateHospital({ phone: "02-123-4567", address: null, booking_url: "https://a.example/b" });
  await updateHospital({ phone: "02-999-8888" });
  const info = await getHospital();

  assert.equal(info.booking_url, "https://a.example/b", "안 보낸 칸이 지워졌다");
});
