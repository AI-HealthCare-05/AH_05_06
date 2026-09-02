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

/* renderTimeline 은 브라우저에서 눈으로 본다. 아래는 그 옆의 **순수 규칙** —
   IIFE 밖으로 옮겨 둔(KEY-158) 이름표·되돌림·시각 함수만 잰다. 서버가
   TimelineEvent 를 늘렸을 때 이름표가 빠지면 화면에 코드가 그대로 뜨므로,
   여기서 어휘를 못박는다. */
const detail = load("api", "session", "patients-api", "shell", "patients", "detail");

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

test("timelineWhen — ISO 앞부분(분까지)만, 못 읽으면 원문", () => {
  assert.equal(detail.timelineWhen("2026-08-20T01:05:00+09:00"), "2026-08-20 01:05");
  assert.equal(detail.timelineWhen("2026-08-20T01:05:00Z"), "2026-08-20 01:05");
  assert.equal(detail.timelineWhen(""), "");
  assert.equal(detail.timelineWhen("nonsense"), "nonsense");
});

test("이력 이름표가 서버 사건 어휘(TimelineEvent)를 다 덮는다", () => {
  // app/dtos/visits.py 의 TimelineEvent 와 같은 목록 — 한쪽이 늘면 여기도 는다.
  const EVENTS = [
    "DOCUMENT_UPLOADED",
    "OCR_STARTED",
    "OCR_COMPLETED",
    "OCR_FAILED",
    "OCR_CONFIRMED",
    "GUIDE_GENERATED",
    "GUIDE_EDITED",
    "GUIDE_APPROVED",
    "GUIDE_RETURNED",
    "CHECK_IN_SUBMITTED",
  ];
  for (const e of EVENTS) {
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
