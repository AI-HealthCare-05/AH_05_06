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

const ENTRY_KEYS = ["actor_id", "at", "category", "document_type", "event", "note", "section_key"];

test("timeline 응답이 계약의 봉투를 갖춘다 — visit_id 와 entries", async () => {
  const today = await api.patientsApi.onDay("2026-08-20", []);
  const withHistory = today.items.find((v) => v.detail_status === "APPROVAL_PENDING");

  const body = await api.patientsApi.timeline(withHistory.visit_id);

  assert.deepEqual(plain(Object.keys(body).sort()), ["entries", "visit_id"]);
  assert.equal(body.visit_id, withHistory.visit_id);
  assert.ok(body.entries.length > 0, "이 진료는 목업에 이력이 있어야 한다");
  for (const entry of body.entries) {
    assert.deepEqual(plain(Object.keys(entry).sort()), ENTRY_KEYS, `이력 항목 칸이 계약과 다르다: ${Object.keys(entry)}`);
  }
});

test("이력은 오래된 것이 먼저다 — 문서 → 판독 → 안내문 차례", async () => {
  const today = await api.patientsApi.onDay("2026-08-20", []);
  const withHistory = today.items.find((v) => v.detail_status === "APPROVAL_PENDING");

  const { entries } = await api.patientsApi.timeline(withHistory.visit_id);
  const times = entries.map((e) => e.at);

  assert.deepEqual(plain(times), plain([...times].sort()), "오름차순이 아니다");
  assert.equal(entries[0].category, "DOCUMENT", "첫 사건은 문서 업로드여야 한다");
});

test("사건이 없는 진료는 오류가 아니라 빈 목록이다", async () => {
  // 오늘 목록에는 있지만 아직 아무 일도 안 한 진료를 하나 찾는다.
  const today = await api.patientsApi.onDay("2026-08-20", []);
  let empty = null;
  for (const row of today.items) {
    const body = await api.patientsApi.timeline(row.visit_id);
    if (body.entries.length === 0) {
      empty = body;
      break;
    }
  }
  assert.ok(empty, "이력이 빈 진료가 목업에 하나는 있어야 한다");
  assert.deepEqual(plain(Object.keys(empty).sort()), ["entries", "visit_id"]);
  assert.deepEqual(plain(empty.entries), []);
});

test("없는 진료의 이력은 404 — 목업이 `GET /visits/{id}` 보다 관대하지 않다", async () => {
  await assert.rejects(
    () => api.patientsApi.timeline(999999),
    (err) => err.code === "VISIT_NOT_FOUND" && err.status === 404,
  );
});

test("문자 발송 사건은 아직 이력에 없다 — 발송 이력 모델이 Sprint 5", async () => {
  const today = await api.patientsApi.onDay("2026-08-20", []);
  for (const row of today.items) {
    const { entries } = await api.patientsApi.timeline(row.visit_id);
    const categories = new Set(entries.map((e) => e.category));
    assert.ok(!categories.has("SEND"), "발송 사건이 계약보다 앞서 들어왔다");
  }
});
