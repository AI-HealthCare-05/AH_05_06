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

test("② 설정 화면 로그아웃은 단추가 없어도 초기화를 멈추지 않는다", () => {
  /* `settings.js` 는 KEY-158 대로 뿌리(`#rail`)가 없으면 조용히 돌아간다. 그런데
     뿌리는 있는데 `#logout` 만 이름이 바뀌면 이야기가 다르다 — 그 줄은
     `requireSession()` **앞**의 최상위라, 거기서 터지면 세션 확인도 폼 배선도
     시작을 못 하고 설정 화면이 통째로 죽는다 (#237 이희진).

     이 파일의 다른 무가드 `el()` 열일곱 곳은 다 함수 안이라 기능 하나가 죽고
     만다. 그래서 여기 한 자리만 잰다.

     **꺼내는 모양은 안 잰다** — `el("logout").addEventListener` 라는 글자를 그대로
     못 박았던 앞선 검사가, 널 가드를 다는 것만으로 울었다. 재는 것은 「쓰기 전에
     확인하는가」다. */
  const code = codeOnly(read("js/settings.js"));
  const at = code.indexOf('el("logout")');
  assert.notEqual(at, -1, "설정 화면이 로그아웃 단추를 안 찾는다");

  const around = code.slice(Math.max(0, at - 40), at + 220);
  assert.match(
    around,
    /(if\s*\(\s*\w+\s*\)|\w+\s*&&|\?\.)\s*[\s\S]{0,60}addEventListener/,
    "로그아웃을 확인 없이 곧장 만진다 — 단추가 사라지면 설정 화면 전체가 죽는다",
  );
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

test("④ 챗봇에 「문의하기」 가짜 단추가 남아 있지 않다", () => {
  /* 여태 멀쩡한 모양으로 답변마다 붙어 있다가, 누르면 「문의 창구는 병원
     설정에서 연결됩니다」를 띄웠다. `admin.js` 가 말한 「눌러 보고서야 아는
     꼴」이 바로 이것이다.

     처음 고칠 때는 잠그고 `title` 로 사정을 적었는데, **이 화면은 휴대폰이라
     툴팁이 안 뜬다**(#237 이희진). 그래서 단추 자체를 없앴다. */
  const code = codeOnly(read("patient_wireframe/js/chat.js"));

  assert.doesNotMatch(code, /chat-contact/, "잠근 단추가 그대로 남아 있다");
  assert.doesNotMatch(code, /alert\('문의 창구는/, "누른 뒤에 알리는 경고가 남아 있다");
});

test("④ 문의 사정은 툴팁이 아니라 보이는 글로 있다", () => {
  /* **손가락에게는 호버가 없다.** `title` 로 적은 사정은 휴대폰에서 한 글자도
     안 보이므로, 환자는 회색 자리를 눌러 보고도 아무 답을 못 받는다.
     그리고 이 줄은 환자 화면에서 **병원에 닿는 길을 알려 주는 유일한 자리**다. */
  const html = fs.readFileSync(path.join(ROOT, "guide.html"), "utf8");
  const at = html.indexOf('class="chat-note"');
  assert.notEqual(at, -1, "안내가 사라졌다 — 환자가 병원에 닿을 길이 없다");

  /* **그 문단 안까지만 본다** — 고정 길이로 자르면 바로 아래 입력 영역의
     보내기·중단 단추까지 삼켜서, 엉뚱한 것을 보고 우는 검사가 된다. */
  const closeAt = html.indexOf("</p>", at);
  assert.notEqual(closeAt, -1, "안내 문단이 닫히지 않았다");
  const note = html.slice(at, closeAt);
  assert.match(note, /병원으로 전화/, "어디로 연락하라는 말이 없다");
  assert.doesNotMatch(note, /title=/, "사정을 다시 툴팁에 숨겼다");
  assert.doesNotMatch(note, /<button/, "읽는 글 자리에 누르는 것이 다시 들어왔다");

  /* **챗봇 패널 안에 있어야 읽힌다** — 패널 밖으로 새면 상담을 여는 사람에게는
     안 보인다.

     「패널 시작보다 뒤」만 재면 부족하다. 패널을 일찍 닫아 버려도 글자 위치는
     그대로라 그 검사는 통과한다. 그래서 **`div` 균형**을 센다 — 여는 것보다
     닫는 것이 많아지는 순간 그 자리는 이미 패널 밖이다. */
  const panelAt = html.indexOf('id="chat-panel"');
  assert.notEqual(panelAt, -1, "챗봇 패널이 없다");
  assert.ok(at > panelAt, "안내가 챗봇 패널보다 앞에 있다");

  const between = html.slice(panelAt, at);
  const depth = (between.match(/<div\b/g) || []).length - (between.match(/<\/div>/g) || []).length;
  assert.ok(depth >= 0, `안내가 챗봇 패널 밖으로 나왔다 — 패널이 ${-depth}겹 먼저 닫혔다`);
});

test("④ 안내 줄은 단추 꼴을 흉내 내지 않는다", () => {
  /* 테두리와 알약 모양이 남아 있으면 읽으라고 둔 글을 눌러 본다. */
  /* 주석은 지우고 본다 — 없앤 까닭을 적어 둔 글까지 「남아 있다」로 읽으면
     기록을 지워야 검사가 통과하는 꼴이 된다. */
  const css = codeOnly(fs.readFileSync(path.join(ROOT, "patient_wireframe/css/chat.css"), "utf8"));
  assert.doesNotMatch(css, /\.chat-contact/, "잠근 단추 스타일이 그대로 남아 있다");

  const at = css.indexOf(".chat-note {");
  assert.notEqual(at, -1, "안내 줄 스타일이 없다");
  const rule = css.slice(at, css.indexOf("}", at));
  assert.doesNotMatch(rule, /cursor:\s*pointer/, "손 모양이 붙어 눌러 보게 생겼다");
  assert.doesNotMatch(rule, /border(?!-)/, "테두리가 있어 단추로 보인다");
});
