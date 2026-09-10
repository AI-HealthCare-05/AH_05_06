const { test } = require("node:test");
const assert = require("node:assert/strict");
const { load } = require("./browser-shim.js");

test("KEY-277 근거 표시와 외부 문자열 escaping", () => {
  const box = load("api", "guide-view");
  const html = box.guideSourcesHtml([{
    generation_mode: "rag", source_org: "<script>bad</script>",
    document_id: "synthetic", version: "v1", verified_at: "2026-09-10",
    source_url: "https://example.invalid",
  }]);
  assert.ok(html.includes("RAG"));
  assert.ok(html.includes("2026-09-10"));
  assert.ok(!html.includes("<script>"));
  assert.equal(box.guideSourcesHtml([]), "");
});

test("KEY-277 검색 장애 fallback 표시", () => {
  const box = load("api", "guide-view");
  const html = box.guideSourcesHtml([{
    generation_mode: "template", template_id: "synthetic-template", version: "v2",
    fallback_reason: "search_infrastructure_exhausted",
  }]);
  assert.ok(html.includes("검색 장애 → 템플릿"));
  assert.ok(html.includes("synthetic-template"));
  assert.ok(html.includes("v2"));
});

test("KEY-277 생성 접수 후 같은 작업만 폴링하고 저장 결과 반환", async () => {
  const box = load("api", "ocr-api");
  const calls = [];
  const ready = { visit_id: 7, sections: [] };
  box.ocrRequest = async (path, options) => {
    calls.push({ path, options });
    return calls.length < 3 ? { job_id: "synthetic-job", state: "queued" } : ready;
  };
  assert.equal(await box.ocrApi.generateGuide(7), ready);
  assert.equal(calls.length, 3);
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[1].path, "/visits/7/guide/generation/synthetic-job");
  assert.equal(calls[2].path, calls[1].path);
});

test("KEY-277 실패는 성공처럼 반환하지 않고 재접수도 하지 않음", async () => {
  const box = load("api", "ocr-api");
  let calls = 0;
  box.ocrRequest = async () => {
    calls++;
    return { job_id: "synthetic-job", state: "failed", failure_reason: "source_conflict" };
  };
  await assert.rejects(box.ocrApi.generateGuide(7), { code: "source_conflict" });
  assert.equal(calls, 1);
});
