/* 문자 수신 동의 시각은 **의원 시각 짧은 꼴**로 — KEY-344.
 *
 * 환자 상세의 「문자 수신」 칸에 API 가 준 ISO 가 그대로 떴다.
 *
 *     동의 · 2026-09-07T14:04:36.032629+09:00
 *
 * 초·마이크로초·`+09:00` 까지 나와 한 줄이 길어지고 읽기 어려웠다. 목록
 * (`roster-rules.js`)은 이미 `동의 · 07-28` 로 줄여 쓰고 있었고 **상세만**
 * 남아 있었다.
 *
 * 여기서 재는 것 셋이다.
 *
 *   ① 꼴이 맞는가 — `동의 · 09-07 14:04`
 *   ② 시각이 없거나 못 읽으면 **지어내지 않는가**
 *   ③ **보는 사람의 시간대를 안 타는가** ← 이게 이 화면의 오랜 함정이다
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const path = require("node:path");
const { load } = require("./browser-shim");

const screen = load("api", "session", "clinic-clock", "patients-api", "shell", "patients", "detail");

/* 합성 값이다 — 실제 환자 시각을 쓰지 않는다. */
const CONSENTED = "2026-09-07T14:04:36.032629+09:00";
const OPTED_OUT = "2026-07-28T09:30:00+09:00";

test("동의 시각이 짧은 의원 시각으로 붙는다", () => {
  assert.equal(screen.consentWhen(CONSENTED), " · 09-07 14:04");
});

test("ISO 의 초·마이크로초·시간대는 안 보인다", () => {
  const said = "동의" + screen.consentWhen(CONSENTED);

  assert.equal(said, "동의 · 09-07 14:04");
  for (const raw of ["T", ":36", "032629", "+09:00", "2026-"]) {
    assert.ok(!said.includes(raw), `원시 ISO 조각 \`${raw}\` 이 화면에 남았다 — ${said}`);
  }
});

test("시각을 모르면 지어내지 않는다", () => {
  for (const missing of [null, undefined, ""]) {
    assert.equal(screen.consentWhen(missing), "", `${String(missing)} 에 무언가를 붙였다`);
    assert.equal("동의" + screen.consentWhen(missing), "동의");
    assert.equal("거부" + screen.consentWhen(missing), "거부");
  }
});

test("못 읽는 값에도 꼬리만 남기지 않는다", () => {
  /* 「동의 · 」처럼 구분점만 남으면 화면이 깨져 보인다. 날짜만 있고 시각이
     없는 값도 여기로 온다 — `clinicStamp` 는 그때 날짜만 준다. */
  assert.equal(screen.consentWhen("어제"), "");
  assert.equal(screen.consentWhen("2026-09-07"), " · 09-07", "날짜만 있으면 날짜만 붙인다");
});

test("거부에도 같은 규칙이 쓰인다", () => {
  assert.equal("거부" + screen.consentWhen(OPTED_OUT), "거부 · 07-28 09:30");
});

test("**보는 사람의 시간대를 안 탄다** — 다른 시간대에서 돌려 본다", () => {
  /* 글자에서 읽는지 `Date` 로 옮기는지는 **다른 시간대에서 돌려 봐야** 갈린다.
     소스를 문자열로 대조하면 엉뚱한 것을 재게 된다 — 실제로 프로세스를 띄운다.

     서울에서 14:04 인 값은 뉴욕 시간대의 브라우저에서 01:04 로 보일 수 있다.
     그러면 같은 진료가 사람마다 다른 시각으로 보이고 「몇 시에 동의하셨죠」에
     답할 수 없다. */
  const probe = [
    'const { load } = require("./browser-shim");',
    'const s = load("api", "session", "clinic-clock", "patients-api", "shell", "patients", "detail");',
    `process.stdout.write(s.consentWhen(${JSON.stringify(CONSENTED)}));`,
  ].join("\n");

  const say = (zone) =>
    execFileSync(process.execPath, ["-e", probe], {
      cwd: __dirname,
      env: { ...process.env, TZ: zone },
      encoding: "utf8",
    });

  const seoul = say("Asia/Seoul");
  const newYork = say("America/New_York");
  const auckland = say("Pacific/Auckland");

  assert.equal(seoul, " · 09-07 14:04");
  assert.equal(newYork, seoul, "뉴욕 시간대에서 다른 시각이 보인다 — 글자가 아니라 Date 로 읽고 있다");
  assert.equal(auckland, seoul, "오클랜드 시간대에서 다른 시각이 보인다");
});

test("환자를 고쳐 다시 그려도 같은 꼴이다", () => {
  /* 수정 뒤 `renderPatient` 가 다시 도는데, 그때 원시 ISO 로 되돌아가면
     화면을 새로 고칠 때까지 아무도 모른다. 같은 입력에 같은 출력인지 본다. */
  const first = screen.consentWhen(CONSENTED);
  const again = screen.consentWhen(CONSENTED);

  assert.equal(again, first);
  assert.equal(again, " · 09-07 14:04");
});

test("목록과 상세가 같은 사건을 같은 날짜로 말한다", () => {
  /* 목록은 `동의 · 09-07`, 상세는 `동의 · 09-07 14:04` 로 **길이만 다르다.**
     날짜까지 어긋나면 같은 환자를 두 화면에서 보는 사람이 헷갈린다. */
  const roster = load("api", "session", "clinic-clock", "patients-api", "roster-rules");
  const listed = roster.consentSaying({ sms_consent: true, sms_consented_at: CONSENTED });
  const detailed = "동의" + screen.consentWhen(CONSENTED);

  assert.equal(listed, "동의 · 09-07");
  assert.ok(detailed.startsWith(listed), `목록 \`${listed}\` 과 상세 \`${detailed}\` 의 날짜가 어긋난다`);
});
