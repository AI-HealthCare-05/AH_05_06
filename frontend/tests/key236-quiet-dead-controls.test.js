/* KEY-236 — 눌리는 척하는 자리를 없앤다.
 *
 * 정적 버튼은 `action-buttons.test.js` 가 분류표와 대조한다. 여기는 그 검사가
 * **원리상 못 보는 넷**을 잰다.
 *
 *   ① 화면마다 살고 죽는 버튼   같은 목록을 세 화면이 쓰는데 손은 한 화면에만 있었다
 *   ② 역할이 정하는 잠금        admin.js 가 세 탭 중 둘만 잠갔다
 *   ③ patient_wireframe 아래   그 검사는 frontend 최상위 *.html 만 훑는다
 *   ④ 자바스크립트가 만드는 버튼  마크업에 없으니 태그 스캔에 안 걸린다
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { read, codeOnly } = require("./source.js");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");

test("① 등록할 수 없는 화면에서는 등록을 권하지 않는다", () => {
  /* 같은 빈 목록을 세 화면이 쓴다. 그런데 「+ 「이름」 등록하기」를 듣는 곳은
     `patients.js` 하나뿐이고, 의사·판독 화면은 그 파일을 안 싣는다 — 거기서는
     **눌러도 아무 일이 없었다.**

     이어 주는 것으로는 못 고친다. 그 두 화면의 `#view-register` 는 내용이 없는
     빈 껍데기라, 보여 줘도 빈 판이 뜬다. */
  const box = load("api", "session", "patients-api", "shell");
  box.listQuery = "김서연";

  const offered = box.blankHtml(true);
  const plain = box.blankHtml(false);

  assert.match(offered, /data-register-with="김서연"/, "등록 판이 있는 화면에서 권유가 사라졌다");
  assert.doesNotMatch(plain, /data-register-with/, "등록할 수 없는 화면에 등록 버튼이 그대로다");
  assert.match(plain, /오늘 등록된 환자가 없습니다/, "왜 비었는지까지 사라지면 안 된다");
});

test("① 등록 판이 있는지로 가른다 — 빈 껍데기와 구별한다", () => {
  const code = codeOnly(read("js/shell.js"));
  assert.match(
    code,
    /blankHtml\(!!document\.getElementById\("reg-submit"\)\)/,
    "무엇으로 가르는지가 바뀌었다 — `#view-register` 는 세 화면에 다 있어서 기준이 못 된다",
  );

  const withForm = fs.readFileSync(path.join(ROOT, "patients.html"), "utf8");
  assert.match(withForm, /id="reg-submit"/, "환자 화면에 등록 폼이 없다");
  for (const page of ["doctor.html", "ocr-review.html"]) {
    const html = fs.readFileSync(path.join(ROOT, page), "utf8");
    assert.doesNotMatch(html, /id="reg-submit"/, `${page} 에 등록 폼이 생겼다면 이 검사를 다시 정해야 한다`);
    assert.match(html, /id="view-register"[^>]*>\s*<\/section>/, `${page} 의 등록 판이 더는 빈 껍데기가 아니다`);
  }
});

test("② 갈 곳 없는 상단바 탭 셋을 모두 잠근다", () => {
  /* 「현황」과 「설정」은 잠그면서 「관리」만 빠져 있었다. 그 파일 스스로
     「403 을 받는 링크가 가장 나쁘다」고 적어 두었다. */
  const code = codeOnly(read("js/admin.js"));
  for (const id of ["to-work", "to-manage", "to-settings"]) {
    assert.match(code, new RegExp('park\\("' + id + '"'), `${id} 가 갈 곳 없을 때 잠기지 않는다`);
  }
  assert.match(code, /off\.setAttribute\("aria-disabled", "true"\)/, "잠근 자리를 낭독기가 못 알아본다");
  assert.match(code, /off\.title = why/, "왜 못 가는지를 말하지 않는다");
});

test("③ 환자 인증 화면의 「번호가 바뀌셨나요?」는 숨어 있다", () => {
  /* 이 버튼을 듣는 코드가 저장소에 없고 번호를 고치는 종점도 없다(P1-3).
     환자 화면이라 잠근 단추를 보여 줘도 손쓸 방법이 없다 — 그래서 숨긴다. */
  const html = fs.readFileSync(path.join(ROOT, "patient_wireframe/html/otp.html"), "utf8");
  const tag = html.match(/<button[^>]*class="otp-change"[^>]*>/);
  assert.ok(tag, "otp-change 버튼을 못 찾았다");
  assert.match(tag[0], /\bhidden\b/, "번호를 바꿀 길이 없는데 버튼이 아직 보인다");

  const wired = fs.readFileSync(path.join(ROOT, "patient_wireframe/html/otp.html"), "utf8");
  assert.doesNotMatch(wired, /otp-change[^]{0,400}addEventListener/, "손이 붙었으면 숨길 것이 아니라 살릴 것이다");
});

test("④ 챗봇 「문의하기」는 눌러 보기 전에 말한다", () => {
  /* 여태 멀쩡한 모양으로 답변마다 붙어 있다가, 누르면 「문의 창구는 병원
     설정에서 연결됩니다」를 띄웠다. `admin.js` 가 말한 「눌러 보고서야 아는
     꼴」이 바로 이것이다. */
  const code = codeOnly(read("patient_wireframe/js/chat.js"));
  const at = code.indexOf("chat-contact");
  assert.notEqual(at, -1, "문의하기 버튼이 사라졌다");
  const around = code.slice(at, at + 700);

  assert.match(around, /setAttribute\('aria-disabled', 'true'\)/, "문의하기가 아직 멀쩡한 모양이다");
  assert.match(around, /contact\.title = '[^']{10,}'/, "왜 아직 못 쓰는지를 안 말한다");
  assert.doesNotMatch(around, /contact\.addEventListener/, "눌러 보고서야 아는 꼴이 그대로다");
  assert.doesNotMatch(code, /alert\('문의 창구는/, "누른 뒤에 알리는 경고가 남아 있다");
});

test("④ 잠근 문의하기는 손이 올라가도 반응하지 않는다", () => {
  /* 마지막까지 눌리는 척하는 자리가 호버다 — 색이 변하면 눌러 본다. */
  const css = fs.readFileSync(path.join(ROOT, "patient_wireframe/css/chat.css"), "utf8");
  assert.match(css, /\.chat-contact\[aria-disabled="true"\][^{]*\{[^}]*cursor:\s*default/, "손 모양이 그대로다");
  assert.match(css, /\.chat-contact\[aria-disabled="true"\]:hover[^{]*\{[^}]*background:\s*transparent/, "호버가 반응한다");
});
