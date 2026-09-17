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
  send_hour: 18,
  check_hour: 14,
  rounds: [
    { kind: "GUIDE", enabled: true, body: null, days_before: null, fixed: true },
    { kind: "CHECK_D7", enabled: true, body: null, days_before: null, fixed: false },
    { kind: "CHECK_D15", enabled: false, body: null, days_before: null, fixed: false },
    { kind: "CHECK_D30", enabled: true, body: "{환자명}님, 한 달째. {링크}", days_before: null, fixed: false },
    { kind: "RUN_OUT", enabled: true, body: null, days_before: 5, fixed: false },
  ],
};

/* ── 서버 → 화면 ────────────────────────────────────────────────────── */

test("**서버가 준 것을 화면이 그대로 읽는다**", () => {
  const { smsPlanFromServer } = box();
  const st = smsPlanFromServer(FROM_SERVER);

  assert.equal(st.sendAt, "18:00", "당일 안내문 시각을 못 읽었다");
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

test("진료 당일 안내문만 `on` 에 담지 않는다 — 고정 회차다", () => {
  const { smsPlanFromServer, smsRoundOn } = box();
  const st = smsPlanFromServer(FROM_SERVER);

  assert.equal(st.on.guide, undefined, "고정 회차를 켜 둔 것으로 담았다");
  assert.equal(smsRoundOn({ on: st.on }, "guide"), true, "그래도 켜져 있어야 한다");
  assert.equal(st.on.d7, true, "일주일 뒤 설정을 읽지 못했다");
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
  const body = smsPlanToServer({ sendAt: "18:00", at: "14:00", on: { d7: true, d30: true }, texts: {}, runOutOn: true, runOutBefore: 5 });

  assert.equal(body.send_hour, 18, "당일 안내문 시각을 숫자로 못 보냈다");
  assert.equal(body.check_hour, 14, "시각이 숫자로 안 갔다");

  const by = {};
  body.rounds.forEach((r) => (by[r.kind] = r));
  assert.equal(by.GUIDE.enabled, true, "당일 안내문이 꺼진 채 갔다");
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
  const round = smsPlanFromServer({ send_hour: 18, check_hour: 14, rounds: smsPlanToServer(first).rounds });

  assert.deepEqual(round.on, first.on, "회차가 달라졌다");
  assert.equal(round.at, first.at, "시각이 달라졌다");
  assert.equal(round.sendAt, first.sendAt, "당일 안내문 시각이 달라졌다");
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
    ["GUIDE", "GuideMessageKind.GUIDE: True"],
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

/* ── 스탭 화면의 같은 세 결함 — KEY-353 2차 리뷰(유가은 님)가 doctor.js 에서
 * 잡은 것과 같은 배선(`wireSmsSettings`)을 visit-guide.js 도 쓴다. 못 받은
 * 서버 값을 기본값으로 덮어쓰거나, 저장이 도는 중에도 버튼이 다시 열리거나,
 * 환자를 바꿔도 앞 환자의 저장 안내가 남는 것 — 세 가지를 여기서도 고쳤다.
 *
 * 「smsPlanState·smsSaving → canSave」 판정 자체는 두 화면이 함께 쓰는
 * `smsSaveLock`(guide-view.js) 으로 뺐다(iljun-sys 님 리뷰) — 그 동작은
 * 바로 아래 "smsSaveLock —" 시험들이 실제로 불러서 잰다. 여기서는
 * visit-guide.js 가 그 함수에 무엇을 넘기는지만 원문으로 고정한다. */
test("스탭 화면도 문자 설정을 실제로 받기 전(로딩·실패)에는 저장을 잠근다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.match(code, /var smsPlanState = "loading"/, "환자마다 불러오기 상태를 loading 으로 시작해야 한다");
  assert.match(
    code,
    /var lock = smsSaveLock\(\s*roleEditable,\s*smsPlanState,\s*smsSaving,/,
    "guideSmsPlan 이 smsSaveLock 에 roleEditable·smsPlanState·smsSaving 을 그대로 넘겨야 한다",
  );

  const messagePlanBlock = code.slice(code.indexOf(".messagePlan("));
  assert.match(
    messagePlanBlock,
    /\.messagePlan\([\s\S]{0,20}\)\s*\.then\(function \(data\) \{[\s\S]{0,80}?smsPlanState = "ready"/,
    "messagePlan 응답이 와야 ready 로 열린다",
  );
  assert.match(
    messagePlanBlock,
    /\.catch\(function \(\) \{[\s\S]{0,600}?smsPlanState = "failed"/,
    "messagePlan 이 실패하면 failed 로 남아 저장이 잠긴 채여야 한다",
  );
});

test("스탭 화면도 저장이 도는 동안에는 재렌더링돼도 버튼이 다시 활성화되지 않는다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.match(
    code,
    /save:\s*function\s*\(plan\)\s*\{[\s\S]{0,1200}?smsSaving = true;[\s\S]{0,120}?renderAll\(\);/,
    "save 콜백이 smsSaving 을 켠 뒤에 renderAll() 을 불러야 새로 그려진 버튼도 잠긴다",
  );
  assert.match(code, /smsSaving = false;[\s\S]{0,300}?smsAdopt\(data\)/, "성공하면 smsSaving 을 풀어야 다음 저장이 된다");
  assert.match(code, /smsSaving = false;[\s\S]{0,300}?저장하지 못했습니다/, "실패해도 smsSaving 을 풀어야 다시 시도할 수 있다");
});

/* 3차 리뷰(유가은 님, 34c2b683 기준)에서 잡힌 것 — 스탭 화면도 doctor.js 와
 * 같은 경합이 있었다. 같은 환자를 다시 열어도 `wantedId` 는 똑같아서, A
 * 저장 → B 로 이동 → A 로 복귀 → 재저장 순서에서 응답이 뒤집히면 오래된
 * 응답이 새 값을 덮을 수 있었다. */
test("스탭 화면도 환자를 다시 열면 그 전 저장 요청의 응답은 지금 화면을 건드리지 못한다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.match(
    code,
    /save:\s*function\s*\(plan\)[\s\S]{0,40}?var wantedId[\s\S]{0,600}?var wantedSeq = loadSeq;/,
    "save 가 저장 시점의 loadSeq 를 잡아 둬야 그 사이 같은 환자를 다시 열었는지 가릴 수 있다",
  );
  assert.match(
    code,
    /\.then\(function \(data\) \{\s*if \(visitId !== wantedId \|\| loadSeq !== wantedSeq\) return;/,
    "성공 콜백이 loadSeq 도 같이 봐야 오래된 응답이 smsAdopt 로 최신 값을 덮지 않는다",
  );
  assert.match(
    code,
    /\.catch\(function \(err\) \{\s*if \(visitId !== wantedId \|\| loadSeq !== wantedSeq\) return;/,
    "실패 콜백도 loadSeq 를 봐야 오래된 실패가 새 저장의 smsSaving 을 잘못 풀지 않는다",
  );
});

/* ── smsSaveLock — 실제로 불러서 잰다 ─────────────────────────────────
 *
 * iljun-sys 님 리뷰: 위 같은 원문 패턴 시험은 「글자가 남아 있으면」 통과하지,
 * `smsSaving = true` 바로 뒤에 `smsSaving = false` 를 적어도 잡지 못한다.
 * 판정 자체(`smsSaveLock`)는 IIFE 밖의 순수 함수라 `doctorApprovalState` 처럼
 * 실제로 호출해서 결과를 볼 수 있다 — 이 네 시험은 동작을 잰다. */
test("smsSaveLock — 역할이 닫혀 있으면 그 이유만 돌려주고 저장을 잠근다", () => {
  const { smsSaveLock } = box();

  assert.deepEqual(smsSaveLock(false, "ready", false, "의사 권한이 필요합니다"), {
    canSave: false,
    lockedSaying: "의사 권한이 필요합니다",
  });
  /* 역할이 닫혀 있으면 조회 상태·저장 중 여부는 안 본다 — 이유는 하나뿐이다 */
  assert.equal(smsSaveLock(false, "ready", true, "x").canSave, false);
});

test("smsSaveLock — 역할이 열려도 서버 값을 못 받았으면 잠근다", () => {
  const { smsSaveLock } = box();

  const loading = smsSaveLock(true, "loading", false, "x");
  assert.equal(loading.canSave, false);
  assert.match(loading.lockedSaying, /불러오는 중/);

  const failed = smsSaveLock(true, "failed", false, "x");
  assert.equal(failed.canSave, false);
  assert.match(failed.lockedSaying, /불러오지 못했습니다/);
});

test("smsSaveLock — 서버 값은 받았어도 저장이 도는 중이면 잠근다", () => {
  const { smsSaveLock } = box();
  const saving = smsSaveLock(true, "ready", true, "x");
  assert.equal(saving.canSave, false);
  /* 자체 재검토 — 여기서 빈 문자열을 주면 각주(`ⓘ ...`)가
     `lockedSaying || SMS_NO_TEMPLATE` 로 읽어 저장 가능할 때와 같은 문구로
     떨어진다. 버튼은 잠겼는데 각주는 "저장할 수 있다"고 말하는 자리라, 빈
     문자열이 아닌 이유를 준다. */
  assert.notEqual(saving.lockedSaying, "", "저장 중에는 빈 문자열이 아닌 이유를 줘야 각주가 엉뚱한 기본 문구로 떨어지지 않는다");
});

test("smsSaveLock — 역할·조회·저장이 모두 열려야 저장할 수 있다", () => {
  const { smsSaveLock } = box();
  assert.deepEqual(smsSaveLock(true, "ready", false, "x"), { canSave: true, lockedSaying: "" });
});

test("스탭 화면도 환자를 바꾸면(loadGuide) 저장 안내·불러오기 상태를 새로 잰다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.match(
    code,
    /smsPlanState = "loading";[\s\S]{0,40}?smsSaving = false;[\s\S]{0,40}?smsSaying = "";[\s\S]{0,80}?\.messagePlan\(/,
    "loadGuide() 가 messagePlan 을 다시 부르기 전에 smsPlanState·smsSaving·smsSaying 을 모두 초기화해야 앞 환자의 안내가 안 남는다",
  );
});

/* 자체 재검토 — `say()` 는 안내문 편집·문자 설정 저장 결과를 함께 쓰는 알림
 * 줄이다. 위 시험이 잡는 `smsSaying` 과 같은 이유로, 환자 전환 시 이것도
 * 비워야 한다. */
test("스탭 화면도 환자를 바꾸면(loadGuide) 편집·문자 설정의 결과 알림 줄도 비운다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.match(
    code,
    /guide = null;[\s\S]{0,300}?say\(""\);[\s\S]{0,60}?renderAll\(\);/,
    'loadGuide() 가 guide 를 비운 뒤 say("") 로 알림 줄도 비워야 앞 환자의 "고쳤습니다"가 안 남는다',
  );
});

/* 4차 점검(2heej 님 요청, 원 리뷰어 부재 시 자체 재검토) — doctor.js 와 같은
 * 이유. 저장이 GUIDE_NOT_PENDING 으로 막혀도 `guide` 를 갱신하지 않으면
 * `roleEditable` 이 옛 상태를 본 채 열려 있어, 스탭이 같은 충돌에 몇 번이고
 * 다시 걸린다. */
test("스탭 화면도 저장이 GUIDE_NOT_PENDING 으로 막히면 안내문을 다시 읽어 실제 상태로 되돌린다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.match(
    code,
    /var isConflict = err && err\.code === "GUIDE_NOT_PENDING";[\s\S]{0,1000}?doctorApi\s*\n?\s*\.guide\(wantedId\)\s*\.then\(function \(fresh\) \{[\s\S]{0,200}?guide = fresh;/,
    "GUIDE_NOT_PENDING 실패 뒤에 doctorApi.guide 를 다시 불러 전역 guide 를 서버 응답으로 갱신해야 한다",
  );
});

/* 자체 재검토 — doctor.js 와 같은 이유. 재조회가 끝나기 전에 `smsSaving` 을
 * 풀면 「승인된 뒤에는 고칠 수 없습니다」 문구 옆에서 저장 버튼이 다시 눌리는
 * 채로 선다. 목록 줄도 다른 곳에서 이미 승인·반려됐다는 뜻이니 `visit:changed`
 * 로 다시 물어야 한다. */
test("스탭 화면도 GUIDE_NOT_PENDING 재조회가 끝나기 전에는 저장 잠금을 풀지 않고, 끝나면 목록도 다시 묻는다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.match(
    code,
    /if \(!isConflict\) smsSaving = false;/,
    "충돌이 아닌 일반 실패만 즉시 smsSaving 을 풀어야 한다",
  );
  assert.match(
    code,
    /\.guide\(wantedId\)\s*\.then\(function \(fresh\) \{[\s\S]{0,300}?guide = fresh;[\s\S]{0,120}?smsSaving = false;[\s\S]{0,500}?visit:changed/,
    "재조회 성공 뒤에 smsSaving 을 풀고 목록에도 visit:changed 로 다시 물어야 한다",
  );
  assert.match(
    code,
    /\.guide\(wantedId\)[\s\S]{0,800}?\.catch\(function \(\) \{[\s\S]{0,400}?smsSaving = false;/,
    "재조회 자체가 실패해도 smsSaving 을 풀어야 다음 시도가 막히지 않는다",
  );
});
