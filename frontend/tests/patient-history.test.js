/* 환자 이력 모달 (S2-2) — KEY-234.
 *
 * 원문 캡션: 「★ 신설 · S2-1 위에 뜬다 · 스탭 · 의사 공통」.
 *
 * **담지 않는 것이 이 화면의 요점 절반이다.** 원문 주석 — 관리에 필요한
 * 만큼(발송 · 열람 · 응답)은 이 모달로 스탭 · 의사 모두에게, 감사 수준(누가
 * 열어봤나 · 토큰 · 버전 이력)은 A1-7 로 관리자에게만.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

function rules() {
  return load("api", "session", "message-words", "checkin-words", "patients-api", "history-modal");
}

function a_block(over) {
  return Object.assign(
    {
      visit_id: 9101,
      visited_at: "2026-05-20T10:00:00+09:00",
      prescription_set: "비잔 (계속)",
      course_days: 84,
      guide_sent_at: "2026-05-20T18:00:00+09:00",
      guide_viewed_at: "2026-05-27T09:00:00+09:00",
      checks: [],
      runs_out_on: "2026-08-12",
      revisited: false,
    },
    over || {},
  );
}

function a_check(over) {
  return Object.assign(
    { kind: "CHECK_D7", at: "2026-05-27T10:00:00+09:00", sent: true, viewed_at: null, answer: null },
    over || {},
  );
}

/* ── 블록 머리 ──────────────────────────────────────────────────────── */

test("한 줄이 원문대로 읽힌다", () => {
  const { courseSaying } = rules();

  assert.strictEqual(courseSaying(a_block()), "2026-05-20 진료 · 비잔 (계속) · 84일");
});

test("모르는 것은 마디째 뺀다", () => {
  const { courseSaying } = rules();

  assert.strictEqual(
    courseSaying(a_block({ prescription_set: null, course_days: null })),
    "2026-05-20 진료",
    "「· null일」이라 적느니 빼는 편이 낫다",
  );
});

/* ── 안내문 줄 ──────────────────────────────────────────────────────── */

test("발송과 열람을 한 줄로 적는다", () => {
  const { guideSaying } = rules();

  assert.strictEqual(guideSaying(a_block()), "진료 안내문 — 발송 05-20 18:00 · 열람 05-27");
});

test("안 열었으면 안 열었다고 적는다", () => {
  const { guideSaying } = rules();

  assert.strictEqual(
    guideSaying(a_block({ guide_viewed_at: null })),
    "진료 안내문 — 발송 05-20 18:00 · 미열람",
  );
});

test("안 나갔으면 발송 시각을 적지 않는다", () => {
  const { guideSaying } = rules();

  assert.strictEqual(
    guideSaying(a_block({ guide_sent_at: null })),
    "진료 안내문 — 아직 발송되지 않았습니다",
  );
});

test("몇 장까지 읽었는지는 적지 않는다", () => {
  /* 원문에는 「(5장 중 3장)」이 있지만 열람 이벤트에 어느 장인지가 남지
     않는다. **지어낸 분수를 적느니 빼는 편이 낫다.** */
  const code = codeOnly(read("js/history-modal.js"));

  assert.ok(code.indexOf("장 중") === -1 && code.indexOf("sections") === -1);
});

/* ── 확인 문자 줄 ───────────────────────────────────────────────────── */

test("회차와 날짜와 결과를 나란히 적는다", () => {
  const { checksSaying } = rules();

  const said = checksSaying(
    a_block({
      checks: [
        a_check(),
        a_check({ kind: "CHECK_D15", at: "2026-06-04T10:00:00+09:00" }),
        a_check({ kind: "CHECK_D30", at: "2026-06-19T10:00:00+09:00" }),
      ],
    }),
  );

  assert.strictEqual(said, "확인 문자 — 일주일 뒤 05-27 미열람 · 보름 뒤 06-04 미열람 · 한 달 뒤 06-19 미열람");
});

test("회차 이름에서 「확인」이 겹치지 않는다", () => {
  const { roundSaying, checksSaying } = rules();

  assert.strictEqual(roundSaying("CHECK_D7"), "일주일 뒤", "앞머리가 이미 「확인 문자 —」다");
  assert.ok(checksSaying(a_block({ checks: [a_check()] })).indexOf("뒤 확인 ") === -1);
});

test("응답이 있으면 그 말을 그대로 적는다", () => {
  const { checksSaying } = rules();

  assert.strictEqual(
    checksSaying(a_block({ checks: [a_check({ answer: "uncomfortable" })] })),
    "확인 문자 — 일주일 뒤 05-27 응답 「먹고 있는데 불편해요」",
  );
});

test("환자가 고른 말과 같은 말을 쓴다", () => {
  const { answerSaying } = rules();

  assert.strictEqual(answerSaying("taking"), "잘 먹고 있어요");
  assert.strictEqual(answerSaying("stopped_improved"), "증상이 좋아져서 그만뒀어요");
  assert.strictEqual(answerSaying("무언가새로운답"), "", "모르는 답을 코드로 보이면 사람 말이 아니다");
});

test("아직 안 나간 회차는 그렇게 적는다", () => {
  const { checksSaying } = rules();

  assert.strictEqual(
    checksSaying(a_block({ checks: [a_check({ sent: false })] })),
    "확인 문자 — 일주일 뒤 05-27 발송 예정",
  );
});

test("확인 문자가 없으면 줄 자체가 없다", () => {
  const { checksSaying } = rules();

  assert.strictEqual(checksSaying(a_block()), "");
});

/* ── 코스 끝 ────────────────────────────────────────────────────────── */

test("소진일과 재진 여부를 적는다", () => {
  const { courseEndSaying } = rules();

  assert.strictEqual(courseEndSaying(a_block()), "소진 08-12 · 재진 예약 없음");
});

test("다시 왔으면 재진을 채근하지 않는다", () => {
  const { courseEndSaying } = rules();

  assert.strictEqual(courseEndSaying(a_block({ revisited: true })), "소진 08-12");
});

test("처방일수를 모르면 소진일을 적지 않는다", () => {
  const { courseEndSaying } = rules();

  assert.strictEqual(
    courseEndSaying(a_block({ runs_out_on: null })),
    "재진 예약 없음",
    "지어낸 날짜가 제일 나쁘다",
  );
});

/* ── 아래 한 줄 ─────────────────────────────────────────────────────── */

test("몇 건 중 몇 건인지 말한다", () => {
  const { historyCountSaying } = rules();

  assert.strictEqual(historyCountSaying({ visits: [1, 2, 3], total: 4 }), "지난 진료 4건 중 3건");
});

test("다 보이면 「중」이라 하지 않는다", () => {
  const { historyCountSaying } = rules();

  assert.strictEqual(historyCountSaying({ visits: [1, 2], total: 2 }), "지난 진료 2건");
  assert.strictEqual(historyCountSaying({ visits: [], total: 0 }), "지난 진료 없음");
});

/* ── 목업 ───────────────────────────────────────────────────────────── */

test("목업이 원문의 세 블록을 그대로 담는다", async () => {
  const api = rules();
  api.MOCK = true;

  const body = await api.patientsApi.history(2001, 3);

  assert.strictEqual(body.name, "유지수");
  assert.strictEqual(body.total, 4, "원문 「4건 중 3건」");
  assert.strictEqual(body.visits.length, 3);
  assert.strictEqual(body.visits[0].checks.length, 3, "3회 연속 미열람인 코스");
  assert.ok(body.visits[0].checks.every((row) => row.viewed_at === null));
  assert.strictEqual(body.visits[2].checks[0].answer, "uncomfortable");
});

test("이력이 없는 환자도 모달이 열린다", async () => {
  const api = rules();
  api.MOCK = true;

  const body = await api.patientsApi.history(2005, 3);

  assert.strictEqual(body.visits.length, 0, "이력이 없는 것도 답이다");
  assert.strictEqual(body.name, "한소영");
});

test("없는 환자는 없다고 한다", async () => {
  const api = rules();
  api.MOCK = true;

  await assert.rejects(() => api.patientsApi.history(999999, 3));
});

/* ── 담지 않는 것 ───────────────────────────────────────────────────── */

test("직원 열람 기록과 토큰 이력을 담지 않는다", () => {
  const code = codeOnly(read("js/history-modal.js")) + codeOnly(read("js/manage.js"));

  for (const word of ["token", "viewer", "staff_id", "actor"]) {
    assert.ok(code.indexOf(word) === -1, `${word} 가 이력 모달에 들어 있다 — 그건 어드민 A1-7 몫이다`);
  }
});

/* ── 화면 ───────────────────────────────────────────────────────────── */

test("모달이 관리 화면에 서 있다", () => {
  const markup = markupOnly(read("manage.html"));

  assert.ok(markup.indexOf('id="modal"') !== -1);
  assert.ok(markup.indexOf('aria-modal="true"') !== -1, "화면낭독기도 창인 줄 알아야 한다");
  assert.ok(/id="modal"[^>]*hidden/.test(markup), "처음부터 떠 있으면 안 된다");
});

test("배경과 ESC 로도 닫힌다", () => {
  const code = codeOnly(read("js/manage.js"));

  assert.ok(code.indexOf("Escape") !== -1, "창을 여는 길만 있고 나가는 길이 없으면 갇힌다");
  assert.ok(
    code.indexOf('event.target === el("modal")') !== -1,
    "원문: 「배경 클릭도 닫기」",
  );
});

test("이력 버튼이 카드 안에 선다", () => {
  const code = codeOnly(read("js/manage.js"));
  const card = code.slice(code.indexOf("function cardHtml"), code.indexOf("var HEADS"));

  assert.ok(card.indexOf("data-history") !== -1, "원문 「전체 이력 보기」");
  assert.ok(card.indexOf("전체 이력 보기") !== -1);
});
