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
