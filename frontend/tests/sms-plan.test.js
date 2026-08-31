/* **문자 설정** — 와이어프레임 S1-14.
 *
 * 확인 문자 회차 · 소진 임박 · 재진 안내를 한 자리에 모은다. 스탭이 S2-1 에서
 * 이탈 환자를 발견하면 곧바로 조치할 수 있게 하려는 것이다.
 *
 * 여기서 재는 것은 **셈**이다: 언제 갈 것인가, 몇 바이트인가, 무엇이 치환되나.
 * 이 셋이 틀리면 환자가 엉뚱한 날 문자를 받거나, 장문 요금이 나가거나,
 * 「{환자명}님」이 그대로 나간다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function box() {
  return load("sms-plan");
}

/* ── 언제 가나 ──────────────────────────────────────────────────────── */

test("**와이어프레임의 그 날짜가 나온다** — 08-13 진료 기준", () => {
  const { smsDateAfter, smsWhen } = box();

  /* 원문: ☑ 일주일 뒤 → 08-20 (목) · ☑ 보름 뒤 → 08-28 (금) ·
     ☐ 한 달 뒤 → 켜면 09-12 (토) */
  assert.equal(smsWhen(smsDateAfter("2026-08-13", 7)), "08-20 (목)");
  assert.equal(smsWhen(smsDateAfter("2026-08-13", 15)), "08-28 (금)");
  assert.equal(smsWhen(smsDateAfter("2026-08-13", 30)), "09-12 (토)");
});

test("**소진 임박은 소진일보다 앞이다** — 뒤로 세면 약이 떨어진 뒤에 간다", () => {
  const { smsRunOutNotice, smsWhen } = box();

  /* 원문: ☑ 소진 3일 전 → 11-02 (월) 예정 · 소진 11-05 */
  assert.equal(smsWhen(smsRunOutNotice("2026-11-05", 3)), "11-02 (월)");

  assert.equal(smsRunOutNotice("2026-11-05", 0), "", "0일 전은 소진일 당일이라 임박이 아니다");
  assert.equal(smsRunOutNotice("", 3), "", "소진일을 모르면 셈하지 않는다");
});

test("**날짜를 `new Date(문자열)` 로 읽지 않는다** — 시간대에 따라 하루 밀린다", () => {
  /* `new Date("2026-08-13")` 은 UTC 자정이라 미국에서는 전날이 된다.
     이 함정에 이미 걸렸다(`ocr-groups.js` 의 `runOutDate`). 우리 시간대에서는
     값이 같아 못 잡으므로 **원문으로 박는다.** */
  const code = codeOnly(read("js/sms-plan.js"));

  assert.ok(
    !/new Date\(\s*[A-Za-z_$][\w$]*\s*\)/.test(code),
    "날짜 문자열을 그대로 `new Date()` 에 넣는 자리가 있다",
  );
  assert.ok(code.includes("new Date(Number("), "숫자로 뜯어 만드는 자리가 없다 — 검사가 헛돈다");
});

test("해를 넘기고 윤년도 센다", () => {
  const { smsDateAfter } = box();
  assert.equal(smsDateAfter("2026-12-25", 15), "2027-01-09");
  assert.equal(smsDateAfter("2028-02-20", 15), "2028-03-06");
});

/* ── 일주일 뒤는 끌 수 없다 ─────────────────────────────────────────── */

test("**일주일 뒤는 고정이다** — 「필요하면 켜세요」로 두면 아무도 안 켠다", () => {
  const { SMS_ROUNDS } = box();

  const byKey = Object.fromEntries(SMS_ROUNDS.map((r) => [r.key, r]));
  assert.equal(byKey.d7.fixed, true, "일주일 뒤를 끌 수 있다 — 가장 잘 끊기는 구간이다");
  assert.equal(byKey.d15.fixed, false);
  assert.equal(byKey.d30.fixed, false);

  assert.deepEqual(SMS_ROUNDS.map((r) => r.days), [7, 15, 30], "회차가 와이어프레임과 다르다");
});

/* ── 몇 바이트인가 ──────────────────────────────────────────────────── */

test("**한글은 2바이트, 영숫자는 1바이트** — 통신사 과금이 90에서 갈린다", () => {
  const { smsBytes, SMS_SHORT_MAX } = box();

  assert.equal(SMS_SHORT_MAX, 90);
  assert.equal(smsBytes("가"), 2);
  assert.equal(smsBytes("a"), 1);
  assert.equal(smsBytes("1"), 1);
  assert.equal(smsBytes(" "), 1);
  assert.equal(smsBytes("가a1"), 4);
  assert.equal(smsBytes(""), 0);
  assert.equal(smsBytes(null), 0);
});

test("**90을 넘으면 장문이다** — 경계에서 값이 갈린다", () => {
  const { smsKind } = box();

  const short = "가".repeat(45); // 90 바이트
  assert.equal(smsKind(short).bytes, 90);
  assert.equal(smsKind(short).long, false, "90은 아직 단문이다");
  assert.match(smsKind(short).label, /단문/);

  const long = short + "a"; // 91
  assert.equal(smsKind(long).long, true, "91인데 단문이라 한다 — 장문 요금이 조용히 나간다");
  assert.match(smsKind(long).label, /장문/);
});

/* ── 무엇이 치환되나 ────────────────────────────────────────────────── */

test("**미리보기는 치환된 실제 발송본이다** — 안 그러면 무엇이 나갈지 모른다", () => {
  const { smsFill } = box();

  const tpl = "{환자명}님, 복약 {일차}일째 확인입니다. 잘 드시고 계신가요? {링크}";
  const out = smsFill(tpl, { 환자명: "김서연", 일차: 7, 링크: "mg.kr/a3F9x2" });

  assert.equal(out, "김서연님, 복약 7일째 확인입니다. 잘 드시고 계신가요? mg.kr/a3F9x2");
});

test("**모르는 변수는 그대로 둔다** — 지우면 빠진 줄 모르고 나간다", () => {
  const { smsFill } = box();

  const out = smsFill("{환자명}님 {의원명}", { 환자명: "김서연" });
  assert.equal(out, "김서연님 {의원명}", "값이 없는 변수를 지웠다");
});

test("**`{링크}` 는 지울 수 없다** — 없으면 환자가 안내문을 열 수 없다", () => {
  const { smsHasLink, smsLinkMissingSaying } = box();

  assert.equal(smsHasLink("안녕하세요 {링크}"), true);
  assert.equal(smsHasLink("안녕하세요"), false);

  assert.equal(smsLinkMissingSaying("안녕 {링크}"), "");
  assert.match(smsLinkMissingSaying("안녕"), /열 수 없습니다/, "왜 필요한지 안 말한다");
});

/* ── 와이어프레임 숫자와 다르다는 것 ────────────────────────────────── */

test("**바이트 규칙을 와이어프레임 숫자에 맞추려 비틀지 않았다**", () => {
  /* 원문은 같은 문구에 78·76 바이트라 적는데, 그 문자열은 EUC-KR 로 66·65,
     UTF-8 로 91·86 이라 **어느 쪽과도 안 맞는다.** 예시로 적어 둔 값으로
     보인다 — 맞지 않는 숫자를 따라가느라 규칙을 비틀면, 실제 발송에서
     장문 경계를 놓친다. 그 판단을 코드에 적어 두었는지 본다. */
  const source = read("js/sms-plan.js");
  assert.match(source, /와이어프레임의 숫자와는 다르다/, "왜 다른지가 안 적혀 있다 — 다음 사람이 「버그」로 고친다");

  const { smsBytes } = box();
  assert.equal(smsBytes("{환자명}님, 복약 {일차}일째 확인입니다. 잘 드시고 계신가요? {링크}"), 66);
});
