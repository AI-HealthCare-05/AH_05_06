/* 문자 문구 (D2-5) — KEY-234.
 *
 * 원문 부제: 「문자 본문 템플릿 — 안내문(링크 콘텐츠)과 층이 다르다」.
 *
 * **바이트 셈이 서버와 갈리면 안 된다.** 화면이 「단문」이라 했는데 서버가
 * 장문으로 셈해 단가가 오르면, 의원이 모르는 채 돈을 더 낸다. 그래서 같은
 * 글을 양쪽에서 재고(`app/tests/message_templates/`), 여기 적힌 수와 저기
 * 적힌 수가 같아야 한다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

function rules() {
  return load("api", "message-words", "sms-template-rules");
}

/* **서버 검사와 같은 표다.** 한쪽만 고치면 그쪽이 운다. */
const SAME_AS_SERVER = [
  ["가", 2],
  ["a", 1],
  ["가a", 3],
  ["", 0],
  ["안녕하세요안녕하세요안녕하세요안녕하세요안녕하세요안녕하세요안녕하세요안녕하세요안녕하세요안녕하세요", 100],
];

test("바이트 셈이 서버와 같다 — EUC-KR 기준", () => {
  const { smsBytes } = rules();

  for (const [text, bytes] of SAME_AS_SERVER) {
    assert.strictEqual(smsBytes(text), bytes, `「${text.slice(0, 8)}」`);
  }
});

test("UTF-8 로 세면 보낼 수 있는 문구를 못 보낸다고 한다", () => {
  const { smsBytes, SMS_LIMIT } = rules();
  const forty = "안녕하세요".repeat(8); // 40자

  assert.strictEqual(smsBytes(forty), 80);
  assert.ok(smsBytes(forty) <= SMS_LIMIT, "EUC-KR 로는 단문이다");
  assert.ok(Buffer.byteLength(forty, "utf8") > SMS_LIMIT, "UTF-8 로 세면 장문이라 잘못 말한다");
});

test("90바이트에서 단문과 장문이 갈린다", () => {
  const { smsLength, SMS_LIMIT } = rules();

  assert.strictEqual(SMS_LIMIT, 90);
  assert.strictEqual(smsLength("가".repeat(45)).long, false, "딱 90은 아직 단문이다");
  assert.strictEqual(smsLength("가".repeat(46)).long, true);
  assert.strictEqual(smsLength("가".repeat(45)).say, "단문 · 90바이트");
  assert.strictEqual(smsLength("가".repeat(46)).say, "⚠ 장문(LMS) · 92바이트");
});

/* ── 변수 ───────────────────────────────────────────────────────────── */

test("변수를 이름으로 찾는다", () => {
  const { templateVariables } = rules();

  assert.deepStrictEqual(templateVariables("[{의원명}] {환자명}님 {링크}").join(), "의원명,환자명,링크");
  assert.deepStrictEqual(templateVariables("변수 없음").join(), "");
  assert.deepStrictEqual(templateVariables(null).join(), "");
});

test("링크는 지울 수 없다", () => {
  const { templateProblem } = rules();
  const item = { kind: "CHECK_D7", required_variables: ["링크"] };

  const said = templateProblem(item, "{환자명}님, 오늘 어떠세요?", ["환자명", "링크"]);

  assert.ok(said.indexOf("{링크}") === 0, "원문: 「{링크}는 지울 수 없다」");
  assert.ok(said.indexOf("열 곳이 없어집니다") !== -1, "왜 막는지 적지 않으면 고장으로 읽힌다");
});

test("채울 수 없는 변수를 막는다", () => {
  const { templateProblem } = rules();
  const item = { kind: "CHECK_D7", required_variables: ["링크"] };

  const said = templateProblem(item, "{휴대폰}님 {링크}", ["환자명", "링크"]);

  assert.ok(said.indexOf("{휴대폰}") === 0, "채울 데가 없으면 그 글자가 그대로 환자에게 간다");
});

test("빈 문구를 막는다", () => {
  const { templateProblem } = rules();

  assert.ok(templateProblem({ required_variables: [] }, "   ", []));
});

test("멀쩡한 문구는 막지 않는다", () => {
  const { templateProblem } = rules();
  const item = { kind: "CHECK_D7", required_variables: ["링크"] };

  assert.strictEqual(templateProblem(item, "{환자명}님 잘 지내세요? {링크}", ["환자명", "링크"]), "");
});

/* ── 이름 ───────────────────────────────────────────────────────────── */

test("회차 이름을 다시 짓지 않는다", () => {
  const { templateSaying } = rules();

  assert.strictEqual(templateSaying("CHECK_D7"), "일주일 뒤 확인", "js/message-words.js 것을 쓴다");
  assert.strictEqual(templateSaying("RUN_OUT"), "소진 임박");
  assert.strictEqual(templateSaying("REVISIT"), "재진 안내", "회차가 아니라 그 표에 없다");
  assert.strictEqual(templateSaying("OTP"), "인증번호", "고칠 수 없어 그 표에 없다");
});

test("문자 어휘를 여기서 베끼지 않는다", () => {
  const code = codeOnly(read("js/sms-template-rules.js"));

  for (const word of ["진료 안내문", "소진 임박", "보름 뒤", "한 달 뒤"]) {
    assert.ok(code.indexOf(word) === -1, `「${word}」를 여기 다시 적었다 — js/message-words.js 것을 쓴다`);
  }
});

/* ── 목업이 서버와 같은가 ───────────────────────────────────────────── */

test("목업 기본 문구가 서버와 같은 글이다", async () => {
  const api = load("api", "message-words", "sms-template-rules", "field-labels", "catalog-api");
  api.MOCK = true;

  const page = await api.catalogApi.templates();

  assert.strictEqual(page.sms_limit, 90);
  assert.strictEqual(page.items.length, 6, "인증번호는 고칠 수 없어 칸이 없다");
  assert.ok(page.items.every((row) => row.is_default), "안 고쳤으면 전부 기본값이다");
  const guide = page.items.filter((row) => row.kind === "GUIDE")[0];
  assert.strictEqual(
    guide.body,
    "[{의원명}] {환자명}님, 오늘 진료 안내입니다. {만료일}까지 보실 수 있어요: {링크}",
  );
});

test("원문이 장문이라 한 것만 장문이다", async () => {
  const api = load("api", "message-words", "sms-template-rules", "field-labels", "catalog-api");
  api.MOCK = true;

  const page = await api.catalogApi.templates();
  const long = page.items.filter((row) => api.smsLength(row.body).long).map((row) => row.kind);

  assert.deepStrictEqual(long.join(), "REVISIT", "원문이 재진 안내 하나만 ⚠ 장문(LMS)으로 표시한다");
});

test("고치면 기본값이 아니게 되고 되돌리면 돌아온다", async () => {
  const api = load("api", "message-words", "sms-template-rules", "field-labels", "catalog-api");
  api.MOCK = true;

  const before = (await api.catalogApi.templates()).items.filter((r) => r.kind === "CHECK_D7")[0];
  const after = (await api.catalogApi.saveTemplate("CHECK_D7", "{환자명}님 {링크}")).items.filter(
    (r) => r.kind === "CHECK_D7",
  )[0];
  const back = (await api.catalogApi.resetTemplate("CHECK_D7")).items.filter((r) => r.kind === "CHECK_D7")[0];

  assert.strictEqual(before.is_default, true);
  assert.strictEqual(after.is_default, false);
  assert.strictEqual(after.body, "{환자명}님 {링크}");
  assert.strictEqual(back.is_default, true);
  assert.strictEqual(back.body, before.body, "되돌리면 기본 문구로 간다");
});

/* ── 화면이 그 규칙을 쓰는가 ────────────────────────────────────────── */

test("저장 전에 화면이 먼저 잰다", () => {
  const code = codeOnly(read("js/settings.js"));
  const save = code.slice(code.indexOf("function saveTemplates"), code.indexOf("function revertTemplate"));

  assert.ok(save.indexOf("templateProblem(") !== -1, "눌러 보고서야 아는 것보다 낫다");
  assert.ok(save.indexOf("return render()") !== -1, "막혔으면 보내지 않는다");
});

test("하나라도 막히면 아무것도 안 보낸다", () => {
  const code = codeOnly(read("js/settings.js"));
  const save = code.slice(code.indexOf("function saveTemplates"), code.indexOf("function revertTemplate"));

  const checkAt = save.indexOf("templateProblem(");
  const sendAt = save.indexOf("catalogApi");
  assert.ok(checkAt !== -1 && sendAt !== -1 && checkAt < sendAt, "반만 저장되면 어느 것이 들어갔는지 모른다");
});

test("다시 그리기 전에 친 값을 거둔다", () => {
  const code = codeOnly(read("js/settings.js"));

  assert.ok(code.indexOf("function draftsNow") !== -1);
  const save = code.slice(code.indexOf("function saveTemplates"), code.indexOf("function revertTemplate"));
  assert.ok(
    save.indexOf("drafts = draftsNow()") < save.indexOf("render()"),
    "고치라는데 고칠 것이 사라지면 안 된다 — 처방 저장에서 한 번 겪은 자리다",
  );
});

test("고칠 수 없는 문자도 보인다", () => {
  const code = codeOnly(read("js/settings.js"));
  const panel = code.slice(code.indexOf("function templatesHtml"), code.indexOf("function detailHtml"));

  assert.ok(panel.indexOf("system_body") !== -1, "무엇이 나가는지는 알아야 한다");
  assert.ok(panel.indexOf("수정 불가") !== -1);
  assert.ok(panel.indexOf("sms__fixed") !== -1, "읽는 자리가 입력칸처럼 보이면 안 된다");
});

test("만든 묶음만 눌린다", () => {
  const rail = load("api", "settings-rail");

  assert.strictEqual(rail.RAIL_GROUP_READY.sms, true);
  assert.ok(!rail.RAIL_GROUP_READY.guide, "안내문(D2-1·D2-2)은 아직 없다");
  assert.strictEqual(rail.RAIL_GROUP_READY.baseline, true, "검사 기준선(D2-4)도 열린다");
});

test("설정 화면이 규칙 파일을 싣는다", () => {
  const markup = markupOnly(read("settings.html"));

  assert.ok(markup.indexOf("sms-template-rules.js") !== -1);
  assert.ok(markup.indexOf("message-words.js") !== -1, "회차 이름이 거기서 온다");
});
