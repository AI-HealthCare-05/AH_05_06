/* 의원 시계 — KEY-234.
 *
 * **화면에 뜨는 시각은 의원 시각이다. 보는 사람의 노트북 시각이 아니다.**
 *
 * 서버는 `2026-09-01T18:00:00+09:00` 처럼 시간대를 붙여 준다. 그것을
 * `new Date(...)` 로 감싸 `getHours()` 를 부르면 보는 사람의 시간대로
 * 옮겨진다 — 서울에서 18:00 인 진료가 다른 시간대 노트북에서는 다른 시각으로
 * 뜬다. 같은 진료가 사람마다 다르게 보이면 「몇 시에 오셨죠」에 답할 수 없다.
 *
 * **이 검사는 시간대를 바꿔 가며 두 번 잰다.** 서울에서만 돌리면 두 방법이
 * 같은 답을 내어 아무것도 못 본다 — 실제로 그래서 못 잡고 있었다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { execFileSync } = require("node:child_process");
const path = require("node:path");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function clock() {
  return load("api", "clinic-clock");
}

const SIX_PM = "2026-09-01T18:00:00+09:00";

/* ── 글자에서 읽는다 ──────────────────────────────────────────────────── */

test("서버가 적어 보낸 의원 시각을 그대로 떼어 쓴다", () => {
  const { clinicDay, clinicMonthDay, clinicTime, clinicStamp } = clock();

  assert.strictEqual(clinicDay(SIX_PM), "2026-09-01");
  assert.strictEqual(clinicMonthDay(SIX_PM), "09-01");
  assert.strictEqual(clinicTime(SIX_PM), "18:00");
  assert.strictEqual(clinicStamp(SIX_PM), "09-01 18:00");
});

test("모르는 값에는 지어내지 않는다", () => {
  const { clinicDay, clinicTime, clinicStamp } = clock();

  for (const bad of [null, undefined, "", "언젠가"]) {
    assert.strictEqual(clinicDay(bad), "");
    assert.strictEqual(clinicTime(bad), "");
    assert.strictEqual(clinicStamp(bad), "");
  }
});

test("날짜만 온 값도 읽는다 — 생년월일이 그렇다", () => {
  const { clinicDay, clinicTime } = clock();

  assert.strictEqual(clinicDay("1990-01-01"), "1990-01-01");
  assert.strictEqual(clinicTime("1990-01-01"), "", "시각이 없으면 없다고 한다");
});

/* ── 보는 사람의 시간대가 달라도 같아야 한다 ─────────────────────────── */

/** 다른 시간대에서 같은 파일을 돌려 답을 받아 온다. */
function inZone(zone, expression) {
  const shim = path.join(__dirname, "browser-shim.js");
  const script = `
    const { load } = require(${JSON.stringify(shim)});
    const box = load("api", "clinic-clock", "message-words", "schedule-rules", "history-rules");
    console.log(String(${expression}));
  `;
  return execFileSync(process.execPath, ["-e", script], {
    env: { ...process.env, TZ: zone },
    encoding: "utf8",
  }).trim();
}

test("어느 시간대에서 봐도 같은 시각이 뜬다", () => {
  const seoul = inZone("Asia/Seoul", `box.clinicTime(${JSON.stringify(SIX_PM)})`);
  const utc = inZone("UTC", `box.clinicTime(${JSON.stringify(SIX_PM)})`);
  const la = inZone("America/Los_Angeles", `box.clinicTime(${JSON.stringify(SIX_PM)})`);

  assert.strictEqual(seoul, "18:00");
  assert.strictEqual(utc, "18:00", "UTC 노트북에서 09:00 으로 뜨면 안 된다");
  assert.strictEqual(la, "18:00", "로스앤젤레스에서 02:00 으로 뜨면 안 된다");
});

test("`new Date` 로 읽으면 어긋난다 — 그래서 안 쓴다", () => {
  const local = inZone("UTC", `new Date(${JSON.stringify(SIX_PM)}).getHours()`);

  assert.strictEqual(local, "9", "이 값이 바로 우리가 피하려는 것이다");
});

test("의원의 오늘은 보는 사람의 오늘이 아니다", () => {
  const { clinicToday } = clock();
  /* 서울은 이미 다음 날이고 UTC 는 아직 전날인 순간 */
  const midnightish = new Date("2026-09-01T16:00:00Z");

  assert.strictEqual(clinicToday(midnightish), "2026-09-02", "서울은 새벽 1시다");
});

test("며칠 전도 의원 기준이다", () => {
  const { clinicDayShift } = clock();
  const at = new Date("2026-09-01T16:00:00Z"); // 서울 09-02 01:00

  assert.strictEqual(clinicDayShift(0, at), "2026-09-02");
  assert.strictEqual(clinicDayShift(-6, at), "2026-08-27", "이레면 오늘까지 이레다");
});

/* ── 화면이 실제로 그것을 쓰는가 ─────────────────────────────────────── */

test("관리 화면이 브라우저 시계로 읽지 않는다", () => {
  const code = codeOnly(read("js/manage.js"));

  for (const local of ["getHours()", "getMinutes()", "getMonth()", "getDate()", "getFullYear()"]) {
    assert.ok(
      code.indexOf(local) === -1,
      `${local} 로 읽으면 보는 사람의 시간대로 옮겨진다 — js/clinic-clock.js 것을 쓴다`,
    );
  }
});

test("기간도 의원의 오늘에서 센다", () => {
  const code = codeOnly(read("js/history-rules.js"));

  assert.ok(code.indexOf("clinicToday(") !== -1);
  assert.ok(code.indexOf("clinicDayShift(") !== -1);
  assert.ok(
    code.indexOf("getDate()") === -1,
    "자정 전후에 하루가 어긋나 「오늘 나간 문자」가 안 보인다",
  );
});

test("관리 화면이 시계 파일을 싣는다", () => {
  const markup = read("manage.html");

  assert.ok(markup.indexOf("clinic-clock.js") !== -1);
});
