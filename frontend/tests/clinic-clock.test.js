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

test("관리 화면의 **규칙 파일**이 브라우저 시계로 읽지 않는다", () => {
  /* 이 검사가 `manage.js` 와 `history-rules.js` 둘만 훑고 있었다. 그래서
     `schedule-rules.js` 의 `sameDay` 가 `new Date(iso).getFullYear()` 로
     날짜를 비교하는 것을 아무도 못 봤다 — S2-3 「오늘」 거르개가 보는 사람의
     시간대로 셈해지고 있었다. 2heej 님이 `#183` 리뷰에서 찾아 주셨다.

     **목록을 손으로 적으면 새로 싣는 파일이 계속 빠진다.** 화면이 싣는
     것에서 뽑되, 두 갈래를 뺀다.

       `clinic-clock.js`   시계 자신이다. 며칠 전/후를 셈하려면 `setDate`·
                           `getDate` 가 필요하고, 그 자리는 `Asia/Seoul` 로
                           다시 찍어 돌려준다.
       `*-api.js`·`api.js` 서버를 부르는 자리와 **목업**이다. 화면이 「오늘」을
                           정하는 곳이 아니고, 목업의 나이 셈은 시간대가
                           아니라 산수다.

     다만 `api.js` 의 `toIsoDate` 는 **진짜 못 고친 자리다** — 브라우저
     시간대로 찍는데 `shell.js`·`patients.js`·`detail.js` 열 곳이 쓰고,
     `api.js` 를 싣는 화면 여덟이 `clinic-clock.js` 를 안 싣는다. 옮기려면
     적재 순서를 다 손봐야 해서 별도 일감이다. 이 검사가 안 잡는다. */
  const markup = read("manage.html");
  const loaded = [...markup.matchAll(/<script src="\/js\/([\w-]+\.js)"/g)].map((m) => m[1]);

  assert.ok(loaded.length >= 5, `관리 화면이 싣는 파일을 못 읽었다: ${loaded}`);
  assert.ok(loaded.includes("schedule-rules.js"), "발송 예정 규칙이 목록에 없다");

  const rules = loaded.filter((f) => f !== "clinic-clock.js" && !/api\.js$/.test(f));
  assert.ok(rules.length >= 3, `규칙 파일이 하나도 안 남았다: ${loaded}`);

  for (const file of rules) {
    const code = codeOnly(read("js/" + file));
    for (const local of ["getHours()", "getMinutes()", "getMonth()", "getDate()", "getFullYear()"]) {
      assert.ok(
        code.indexOf(local) === -1,
        `js/${file} 가 ${local} 로 읽는다 — 보는 사람의 시간대로 옮겨진다. js/clinic-clock.js 것을 쓴다`,
      );
    }
  }
});

test("기간도 의원의 오늘에서 센다", () => {
  const code = codeOnly(read("js/history-rules.js"));

  assert.ok(code.indexOf("clinicToday(") !== -1);
  assert.ok(code.indexOf("clinicDayShift(") !== -1);
});

test("「오늘 예정」도 의원의 오늘이다", () => {
  const code = codeOnly(read("js/schedule-rules.js"));

  assert.ok(code.indexOf("isClinicToday(") !== -1, "의원 시계를 안 쓴다");
});

test("관리 화면이 시계 파일을 싣는다", () => {
  const markup = read("manage.html");

  assert.ok(markup.indexOf("clinic-clock.js") !== -1);
});
