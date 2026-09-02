/* 이번 진료 이력 — S1-4 (KEY-242)
 *
 * `GET /visits/{id}/timeline` 을 화면이 계약대로 부르고, 목업이 서버보다
 * 관대하지 않은가만 잰다. 그리는 것(`renderTimeline`)은 브라우저에서 눈으로
 * 확인한다 — 이 껍데기는 순수 함수와 API 층만 위한 것이다.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim");

const plain = (v) => structuredClone(v);
const api = load("api", "session", "patients-api");

/* **날짜를 박아 두지 않는다.** 목업이 진료를 늘 「오늘」로 옮겨 놓기 때문에
   («2026-08-20» 처럼) 적어 두면 그날이 지나는 순간 목록이 빈다. 실제로 그렇게
   깨져 있었다 — develop 이 목업을 바꾸면서 이 파일 셋이 한꺼번에 죽었다. */
const TODAY = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });

async function visitsToday() {
  return (await api.patientsApi.onDay(TODAY, [])).items;
}

/* 이력이 여럿인 진료 하나. 상태 이름(`APPROVAL_PENDING` → `APPROVAL_REQUESTED`)
   으로 고르면 그 이름이 바뀔 때 또 죽는다. **재는 것으로 고른다.** */
async function aVisitWithHistory() {
  for (const row of await visitsToday()) {
    const body = await api.patientsApi.timeline(row.visit_id);
    if (body.entries.length > 1) return body;
  }
  return null;
}

/* `actor`(사람 이름)와 `messages`(나갈 문자)는 `#176` 을 합치며 들어왔다.
   화면이 번호를 받아 다시 물으면 같은 왕복이 브라우저에서 일어난다. */
const ENTRY_KEYS = ["actor", "actor_id", "at", "category", "document_type", "event", "note", "section_key"];

test("timeline 응답이 계약의 봉투를 갖춘다 — visit_id 와 entries", async () => {
  const body = await aVisitWithHistory();

  assert.ok(body, "이력이 여럿인 진료가 목업에 하나는 있어야 한다");
  assert.deepEqual(plain(Object.keys(body).sort()), ["entries", "messages", "visit_id"]);
  for (const entry of body.entries) {
    assert.deepEqual(plain(Object.keys(entry).sort()), ENTRY_KEYS, `이력 항목 칸이 계약과 다르다: ${Object.keys(entry)}`);
  }
});

test("이력은 오래된 것이 먼저다 — 진료 → 문서 → 판독 → 안내문 차례", async () => {
  const { entries } = await aVisitWithHistory();
  const times = entries.map((e) => e.at);

  assert.deepEqual(plain(times), plain([...times].sort()), "오름차순이 아니다");
  /* **진료가 열린 것이 첫 줄이다.** 문서 업로드부터 시작하면, 등록만 하고
     아무것도 안 한 진료의 화면이 통째로 빈다. */
  assert.equal(entries[0].category, "VISIT", "첫 사건은 진료가 열린 것이어야 한다");
  assert.equal(entries[1].category, "DOCUMENT", "그다음이 문서 업로드다");
});

test("아무 일도 안 한 진료도 시작은 있다", async () => {
  /* 전에는 빈 목록이었다. 등록만 하고 아무것도 안 한 환자를 열면 「이력
     없음」이 뜨는데, 스탭이 보기에 그것은 「기록이 안 남았다」로도 읽힌다.
     진료가 열린 것 자체가 첫 사건이라 그 줄을 준다. */
  let bare = null;
  for (const row of await visitsToday()) {
    const body = await api.patientsApi.timeline(row.visit_id);
    if (body.entries.length === 1) {
      bare = body;
      break;
    }
  }
  assert.ok(bare, "아직 아무 일도 안 한 진료가 목업에 하나는 있어야 한다");
  assert.deepEqual(plain(Object.keys(bare).sort()), ["entries", "messages", "visit_id"]);
  assert.equal(bare.entries[0].event, "VISIT_CREATED");
  assert.deepEqual(plain(bare.messages), [], "승인 전에는 나갈 문자가 없다");
});

test("없는 진료의 이력은 404 — 목업이 `GET /visits/{id}` 보다 관대하지 않다", async () => {
  await assert.rejects(
    () => api.patientsApi.timeline(999999),
    (err) => err.code === "VISIT_NOT_FOUND" && err.status === 404,
  );
});

test("문자 발송 사건은 아직 이력에 없다 — 발송 이력 모델이 Sprint 5", async () => {
  for (const row of await visitsToday()) {
    const { entries } = await api.patientsApi.timeline(row.visit_id);
    const categories = new Set(entries.map((e) => e.category));
    assert.ok(!categories.has("SEND"), "발송 사건이 계약보다 앞서 들어왔다");
  }
});

/* renderTimeline 은 브라우저에서 눈으로 본다. 아래는 그 옆의 **순수 규칙** —
   IIFE 밖으로 옮겨 둔(KEY-158) 이름표·되돌림·시각 함수만 잰다. 서버가
   TimelineEvent 를 늘렸을 때 이름표가 빠지면 화면에 코드가 그대로 뜨므로,
   여기서 어휘를 못박는다. */
const detail = load("api", "session", "clinic-clock", "patients-api", "shell", "patients", "detail");

test("timelineDetail — 문서 업로드는 종류 이름표, 모르면 원값·빈값", () => {
  assert.equal(detail.timelineDetail({ event: "DOCUMENT_UPLOADED", document_type: "PRESCRIPTION" }), "처방전");
  assert.equal(detail.timelineDetail({ event: "DOCUMENT_UPLOADED", document_type: "EMR" }), "EMR");
  assert.equal(detail.timelineDetail({ event: "DOCUMENT_UPLOADED", document_type: "MYSTERY" }), "MYSTERY");
  assert.equal(detail.timelineDetail({ event: "DOCUMENT_UPLOADED" }), "");
});

test("timelineDetail — 안내문 수정은 갈래 이름표, 그 밖은 note 그대로", () => {
  assert.equal(detail.timelineDetail({ event: "GUIDE_EDITED", section_key: "caution" }), "주의사항");
  assert.equal(detail.timelineDetail({ event: "GUIDE_EDITED", section_key: "messages" }), "문자 설정");
  assert.equal(detail.timelineDetail({ event: "GUIDE_EDITED", section_key: "unknown" }), "unknown");
  assert.equal(detail.timelineDetail({ event: "GUIDE_RETURNED", note: "처방일수를 확인해 주세요" }), "처방일수를 확인해 주세요");
  assert.equal(detail.timelineDetail({ event: "OCR_FAILED", note: "TIMEOUT" }), "TIMEOUT");
  assert.equal(detail.timelineDetail({ event: "OCR_STARTED" }), "");
});

test("timelineWhen — 글자에서 의원 시각을 읽는다, 옵셋으로 옮기지 않는다 (#182 리뷰 9)", () => {
  assert.equal(detail.timelineWhen("2026-08-20T01:05:00+09:00"), "2026-08-20 01:05");
  /* `Z`·다른 옵셋이 와도 글자 그대로 읽는다 — `new Date()` 로 감싸 보는 사람의
     시간대로 옮기면 같은 진료가 사람마다 다른 시각으로 보인다. clinic-clock 규칙. */
  assert.equal(detail.timelineWhen("2026-08-20T01:05:00Z"), "2026-08-20 01:05");
  assert.equal(detail.timelineWhen("2026-08-20T01:05:00-05:00"), "2026-08-20 01:05");
  assert.equal(detail.timelineWhen(""), "");
  assert.equal(detail.timelineWhen("nonsense"), "nonsense");
});

test("이력 이름표가 서버 사건 어휘(TimelineEvent)를 다 덮는다", () => {
  /* **목록을 손으로 옮기지 않는다** — 한 번 드리프트했다(#182 리뷰 3). 서버의
     `TimelineEvent` 를 그대로 읽어, 값이 늘었는데 이름표를 안 더한 자리가 여기서
     걸리게 한다. 이름표가 빠지면 화면에 `GUIDE_UNAPPROVED` 같은 코드가 그대로 뜬다. */
  const py = fs.readFileSync(path.join(__dirname, "..", "..", "app", "dtos", "visits.py"), "utf8");
  const enumBody = py.slice(
    py.indexOf("class TimelineEvent(StrEnum):"),
    py.indexOf("\nclass ", py.indexOf("class TimelineEvent(StrEnum):") + 1),
  );
  const events = [...enumBody.matchAll(/^ {4}([A-Z_]+) = "([A-Z_]+)"$/gm)].map((m) => m[2]);
  assert.ok(events.length >= 15, `TimelineEvent 를 못 읽었다 — ${events.length}개`);

  for (const e of events) {
    assert.equal(typeof detail.TIMELINE_EVENT_LABEL[e], "string", `${e} 이름표가 없다`);
    assert.ok(detail.TIMELINE_EVENT_LABEL[e].length > 0, `${e} 이름표가 비었다`);
  }
});

test("갈래 수식어는 붙임표만 쓴다 — 저장소 관례(--sm·--done)", () => {
  const mods = Object.values(detail.TIMELINE_CATEGORY_MODIFIER);
  assert.ok(mods.length > 0);
  for (const m of mods) {
    assert.doesNotMatch(m, /_/, `수식어에 밑줄이 있다: ${m}`);
    assert.match(m, /^[a-z][a-z-]*$/, `수식어 모양이 관례와 다르다: ${m}`);
  }
});
