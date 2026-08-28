/* 목업으로 안내문 생성의 네 갈래를 실제로 볼 수 있는가 — KEY-204 / `#162` 1번(이희진).
 *
 * **예전에는 무엇을 눌러도 「됐다」가 떴다.**
 *
 * `mockOcrRequest` 의 라우터에 `POST /visits/{id}/guide/generate` 가 없었고,
 * 못 알아본 경로는 마지막 줄에서 `resolve(job)` 으로 흘러갔다 — 가짜 판독
 * 작업 객체다. 화면은 그걸 성공으로 읽는다. 그래서 이 PR 이 공들인
 * `409 GUIDE_ALREADY_EXISTS` · `403` · `404` 갈래를 `?mock=1` 로는 한 번도
 * 확인할 수 없었다.
 *
 * 조용한 성공이 제일 나쁘다. 화면을 목업으로 본 사람은 「다 된다」고 믿는다.
 *
 * 여기 값은 전부 합성이다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

const VISIT = 8801;

function box(search) {
  return load("api", "ocr-api", search ? { search: search } : {});
}

test("처음 누르면 만들어진다", async () => {
  const api = box();

  const made = await api.ocrApi.generateGuide(VISIT);

  assert.equal(made.visit_id, VISIT, "만든 안내문이 그 진료 것이어야 한다");
  assert.equal(made.status, "DRAFT", "서버 계약대로 초안으로 선다");
});

test("또 누르면 409 다 — 두 번째가 조용히 또 성공하지 않는다", async () => {
  const api = box();
  await api.ocrApi.generateGuide(VISIT);

  await assert.rejects(
    () => api.ocrApi.generateGuide(VISIT),
    (error) => error.code === "GUIDE_ALREADY_EXISTS" && error.status === 409,
    "두 번째 호출은 409 GUIDE_ALREADY_EXISTS 여야 한다",
  );
});

test("다른 진료는 막히지 않는다 — 409 가 진료마다 따로 선다", async () => {
  const api = box();
  await api.ocrApi.generateGuide(VISIT);

  const other = await api.ocrApi.generateGuide(VISIT + 1);

  assert.equal(other.visit_id, VISIT + 1, "다른 진료는 처음이므로 만들어져야 한다");
});

test("권한이 없으면 403 FORBIDDEN", async () => {
  const api = box("?mock=1&case=forbidden");

  await assert.rejects(
    () => api.ocrApi.generateGuide(VISIT),
    (error) => error.code === "FORBIDDEN" && error.status === 403,
  );
});

test("진료가 없으면 404 VISIT_NOT_FOUND", async () => {
  const api = box("?mock=1&case=novisit");

  await assert.rejects(
    () => api.ocrApi.generateGuide(VISIT),
    (error) => error.code === "VISIT_NOT_FOUND" && error.status === 404,
  );
});

test("이미 있는 진료로 열면 처음부터 409 — 새로고침 뒤 다시 누른 모양", async () => {
  const api = box("?mock=1&case=guide-exists");

  await assert.rejects(
    () => api.ocrApi.generateGuide(VISIT),
    (error) => error.code === "GUIDE_ALREADY_EXISTS",
  );
});

test("만든 안내문에 지어낸 진료 문장이 없다", async () => {
  const api = box();

  const made = await api.ocrApi.generateGuide(VISIT);

  assert.deepEqual(made.sections, [], "목업이 의학 문장을 지어 넣으면 안 된다");
});

test("**목업이 모르는 경로는 조용히 성공하지 않는다** — 이 결함의 뿌리", async () => {
  const api = box();

  await assert.rejects(
    () => api.ocrRequest("/visits/8801/guide/approve", { method: "POST" }),
    (error) => error.code === "MOCK_ROUTE_MISSING" && error.status === 501,
    "목업에 없는 경로가 가짜 성공으로 돌아오면, 화면을 목업으로 본 사람은 다 된다고 믿는다",
  );
});

test("아는 경로는 그대로 답한다 — 위 검사가 전부를 막아 버리지 않았는가", async () => {
  const api = box();

  const job = await api.ocrApi.jobForVisit(8801);

  assert.ok(job && job.ocr_job_id, `판독 작업 조회가 살아 있어야 한다 — ${JSON.stringify(job)}`);
});
