/* 이번 진료 이력 — S1-4 (KEY-242)
 *
 * `GET /visits/{id}/timeline` 을 화면이 계약대로 부르고, 목업이 서버보다
 * 관대하지 않은가만 잰다. 그리는 것(`renderTimeline`)은 브라우저에서 눈으로
 * 확인한다 — 이 껍데기는 순수 함수와 API 층만 위한 것이다.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
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
