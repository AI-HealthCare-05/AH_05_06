/* **문자 설정이 서버에 담긴다** — 와이어프레임 S1-14.
 *
 * 회차를 켜고 끈 것도, 고친 문구도, 확인 문자 시각도 화면 안에만 있었다.
 * 새로고침하면 사라졌고, 승인이 예약을 잡을 때는 코드에 박힌 값을 썼다 —
 * **고른 것과 나가는 것이 갈렸다.**
 *
 * 여기서 재는 것은 화면과 서버가 **같은 것을 말하는가**다. 이름이 서로
 * 다르므로(`d7` ↔ `CHECK_D7`) 옮기는 자리에서 틀리면 조용히 어긋난다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function box() {
  return load("api", "session", "sms-plan", "guide-view");
}

const FROM_SERVER = {
  check_hour: 14,
  rounds: [
    { kind: "CHECK_D7", enabled: true, body: null, days_before: null, fixed: true },
    { kind: "CHECK_D15", enabled: false, body: null, days_before: null, fixed: false },
    { kind: "CHECK_D30", enabled: true, body: "{환자명}님, 한 달째. {링크}", days_before: null, fixed: false },
    { kind: "RUN_OUT", enabled: true, body: null, days_before: 5, fixed: false },
  ],
};

/* ── 서버 → 화면 ────────────────────────────────────────────────────── */

test("**서버가 준 것을 화면이 그대로 읽는다**", () => {
  const { smsPlanFromServer } = box();
  const st = smsPlanFromServer(FROM_SERVER);

  assert.equal(st.at, "14:00", "시각이 안 왔다");
  assert.equal(st.on.d15, false, "보름 뒤가 꺼진 것이 안 왔다");
  assert.equal(st.on.d30, true, "한 달 뒤가 켜진 것이 안 왔다");
  assert.equal(st.texts.d30, "{환자명}님, 한 달째. {링크}", "고친 문구가 안 왔다");
  assert.equal(st.runOutBefore, 5, "소진 며칠 전이 안 왔다");
  assert.equal(st.runOutOn, true);
});

test("**소진 임박은 회차 목록에 섞지 않는다**", () => {
  /* `on` 에 넣으면 왼쪽 회차 목록에 「소진」이 한 줄 더 생긴다 — 그건 아래
     따로 있는 칸이다. */
  const { smsPlanFromServer } = box();
  const st = smsPlanFromServer(FROM_SERVER);
  assert.equal(st.on.runOut, undefined, "소진이 회차로 섞였다");
});

test("일주일 뒤는 `on` 에 담지 않는다 — 고정이지 켜 둔 것이 아니다", () => {
  const { smsPlanFromServer, smsRoundOn } = box();
  const st = smsPlanFromServer(FROM_SERVER);

  assert.equal(st.on.d7, undefined, "고정 회차를 켜 둔 것으로 담았다");
  assert.equal(smsRoundOn({ on: st.on }, "d7"), true, "그래도 켜져 있어야 한다");
});

test("시각이 이상하면 기본으로 — 새벽에 문자가 가지 않는다", () => {
  const { smsHourText } = box();
  assert.equal(smsHourText(9), "09:00");
  assert.equal(smsHourText(18), "18:00");
  assert.equal(smsHourText(null), "10:00");
  assert.equal(smsHourText(99), "10:00");
});

/* ── 화면 → 서버 ────────────────────────────────────────────────────── */

test("**보낸 것을 서버가 알아듣는 이름으로 바꾼다**", () => {
  const { smsPlanToServer } = box();
  const body = smsPlanToServer({ at: "14:00", on: { d30: true }, texts: {}, runOutOn: true, runOutBefore: 5 });

  assert.equal(body.check_hour, 14, "시각이 숫자로 안 갔다");

  const by = {};
  body.rounds.forEach((r) => (by[r.kind] = r));
  assert.equal(by.CHECK_D7.enabled, true, "일주일 뒤가 꺼진 채 갔다");
  assert.equal(by.CHECK_D15.enabled, false, "안 켠 회차가 켜진 채 갔다");
  assert.equal(by.CHECK_D30.enabled, true, "켠 회차가 꺼진 채 갔다");
  assert.equal(by.RUN_OUT.days_before, 5, "소진 며칠 전이 안 갔다");
  assert.equal(by.RUN_OUT.enabled, true);
});

test("**기본 문구 그대로면 보내지 않는다**", () => {
  /* 보내면 「이 환자만 적용」이 아닌데도 고친 것으로 담기고, 나중에 기본
     문구가 바뀌어도 이 환자만 안 따라온다. */
  const { smsPlanToServer, smsDefaultText } = box();
  const body = smsPlanToServer({ at: "10:00", on: {}, texts: { d7: smsDefaultText("d7") } });

  const d7 = body.rounds.filter((r) => r.kind === "CHECK_D7")[0];
  assert.equal(d7.body, null, "안 고친 문구가 저장된다");
});

test("고친 문구는 보낸다", () => {
  const { smsPlanToServer } = box();
  const body = smsPlanToServer({ at: "10:00", on: {}, texts: { d7: "내가 고친 문구 {링크}" } });
  const d7 = body.rounds.filter((r) => r.kind === "CHECK_D7")[0];
  assert.equal(d7.body, "내가 고친 문구 {링크}", "고친 문구가 안 간다");
});

test("소진 임박을 끄면 꺼진 채 간다", () => {
  const { smsPlanToServer } = box();
  const body = smsPlanToServer({ at: "10:00", on: {}, texts: {}, runOutOn: false, runOutBefore: 3 });
  const out = body.rounds.filter((r) => r.kind === "RUN_OUT")[0];
  assert.equal(out.enabled, false, "껐는데 켜진 채 간다");
});

test("**갔다가 돌아와도 같은 것이다**", () => {
  const { smsPlanToServer, smsPlanFromServer } = box();
  const first = smsPlanFromServer(FROM_SERVER);
  const round = smsPlanFromServer({ check_hour: 14, rounds: smsPlanToServer(first).rounds });

  assert.deepEqual(round.on, first.on, "회차가 달라졌다");
  assert.equal(round.at, first.at, "시각이 달라졌다");
  assert.equal(round.runOutBefore, first.runOutBefore, "소진 며칠 전이 달라졌다");
  assert.deepEqual(round.texts, first.texts, "문구가 달라졌다");
});

/* ── 화면에 붙어 있는가 ─────────────────────────────────────────────── */

test("**저장 단추가 있고 실제로 보낸다**", () => {
  const { smsRightHtml } = box();
  const html = smsRightHtml({ startIso: "2026-08-13", picked: "d7", text: "{링크}", canSave: true });
  assert.ok(html.includes("data-sms-save"), "저장 단추가 없다");
  assert.ok(html.includes("이 환자만 적용"), "단추에 이름이 없다");

  const code = codeOnly(read("js/guide-view.js"));
  const at = code.indexOf("[data-sms-save]");
  assert.notEqual(at, -1, "누름을 받는 자리가 없다");
  const around = code.slice(at, at + 400);
  assert.match(around, /opts\.save\(/, "받아서 아무 데도 안 보낸다");
  assert.match(around, /smsPlanToServer\(/, "서버 모양으로 안 바꾼다");
});

test("고칠 수 없는 때는 저장 단추가 잠긴다", () => {
  const { smsRightHtml } = box();
  const locked = smsRightHtml({
    startIso: "2026-08-13",
    picked: "d7",
    text: "{링크}",
    canSave: false,
    lockedSaying: "승인된 뒤에는 고칠 수 없습니다",
  });
  assert.match(locked, /data-sms-save disabled/, "승인된 뒤에도 눌린다");
  assert.ok(locked.includes("승인된 뒤에는 고칠 수 없습니다"), "왜 안 되는지 안 말한다");
});

test("**소진 임박을 끌 수 있다** — 늘 ☑ 로 그려 둔 글자였다", () => {
  const { smsLeftHtml } = box();
  const on = smsLeftHtml({ startIso: "2026-08-13", picked: "d7", on: {}, runOutOn: true });
  const off = smsLeftHtml({ startIso: "2026-08-13", picked: "d7", on: {}, runOutOn: false });

  assert.ok(on.includes("data-sms-runout"), "끌 자리가 없다");

  /* **그 단추만 본다.** 회차 목록에도 ☑ · ☐ 가 있어서, 화면 전체에서 찾으면
     소진 단추가 늘 ☑ 여도 통과한다 — 실제로 그렇게 헛돌았다. */
  function mark(html) {
    const at = html.indexOf("data-sms-runout");
    const from = html.indexOf(">", at) + 1;
    return html.slice(from, html.indexOf("</button>", from));
  }
  assert.equal(mark(on), "☑", "켜졌는데 안 켜져 보인다");
  assert.equal(mark(off), "☐", "껐는데 켜져 보인다");

  /* 화면낭독기가 읽는 값도 그 단추 안에서 본다 — 회차 단추에도 같은 낱말이 있다 */
  function pressed(html) {
    const at = html.indexOf("data-sms-runout");
    const m = /aria-pressed="(true|false)"/.exec(html.slice(at, html.indexOf(">", at)));
    return m && m[1];
  }
  assert.equal(pressed(on), "true", "화면낭독기에 켜짐이 안 간다");
  assert.equal(pressed(off), "false", "화면낭독기에 꺼짐이 안 간다");

  const code = codeOnly(read("js/guide-view.js"));
  assert.match(code, /\[data-sms-runout\]/, "누름을 받는 자리가 없다");
});

test("**화면이 설정을 불러온다**", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  const at = code.indexOf("messagePlan(");
  assert.notEqual(at, -1, "설정을 안 불러온다 — 새로고침하면 기본값으로 돌아간다");

  /* **그 요청의 손잡이 안만 본다.** 넉넉히 자르면 옆에 있는 안내문 요청의
     차례 확인이 걸려서, 이쪽이 없어도 통과한다 — 실제로 그렇게 헛돌았다. */
  const stop = code.indexOf(".catch(", at);
  const around = code.slice(at, stop === -1 ? at + 400 : stop);
  assert.match(around, /smsAdopt\(/, "받아서 화면에 안 넣는다");
  assert.match(around, /mySeq !== loadSeq/, "늦게 온 답이 다른 환자 화면에 붙는다");
});

test("**저장 뒤에는 서버가 돌려준 것을 쓴다**", () => {
  /* 보낸 것을 그대로 두면 서버가 고쳐 준 값(일주일 뒤는 켜짐으로 되돌림)이
     화면에 안 보인다 — 껐다고 믿은 채로 문자가 나간다. */
  const code = codeOnly(read("js/visit-guide.js"));
  const at = code.indexOf("saveMessagePlan(");
  assert.notEqual(at, -1, "저장을 서버에 안 보낸다");

  const stop = code.indexOf("\n    },", at);
  const around = code.slice(at, stop === -1 ? at + 900 : stop);
  assert.match(around, /smsAdopt\(\s*data\s*\)/, "서버가 돌려준 것을 안 쓴다");
  assert.match(around, /GUIDE_NOT_PENDING/, "왜 막혔는지 안 말한다");
});

test("목업과 서버의 기본값이 같다", () => {
  /* 다르면 목업에서만 보이는 화면이 생긴다 — 개발 중에 「되는데」가 된다. */
  const api = codeOnly(read("js/doctor-api.js"));
  const at = api.indexOf("MOCK_PLAN_DEFAULT");
  assert.notEqual(at, -1, "목업에 설정 기본값이 없다");
  const mock = api.slice(at, api.indexOf("];", at));

  const service = read("../app/services/guides.py");
  const py = service.slice(service.indexOf("_DEFAULT_ON"), service.indexOf("FIXED_ON"));

  [
    ["CHECK_D7", "GuideMessageKind.CHECK_D7: True"],
    ["CHECK_D15", "GuideMessageKind.CHECK_D15: True"],
    ["CHECK_D30", "GuideMessageKind.CHECK_D30: False"],
    ["RUN_OUT", "GuideMessageKind.RUN_OUT: True"],
  ].forEach(([kind, line]) => {
    const wantOn = /True/.test(line);
    const row = new RegExp(`kind: "${kind}",\\s*enabled: (true|false)`).exec(mock);
    assert.ok(row, `목업에 ${kind} 이 없다`);
    assert.equal(row[1] === "true", wantOn, `${kind} 기본값이 서버와 다르다`);
    assert.ok(py.includes(line), `서버 기본값이 바뀌었다 — 목업도 함께 고쳐야 한다 (${kind})`);
  });
});
