/* KEY-154: 실제 비동기 로더를 실행한다. DOM 렌더링은 브라우저에서 별도 검증한다. */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { load } = require("./browser-shim.js");
const source = fs.readFileSync(path.join(__dirname, "../js/ocr-review.js"), "utf8");
const flush = () => new Promise(setImmediate);
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function harness() {
  const requests = [], timers = [];
  const box = {
    loadSeq: 0, jobIds: [], jobId: null, result: null, visit: null,
    activeDoc: null, threshold: 0.8, pollTimer: null, POLL_MS: 1900,
    setTimeout: (fn) => { timers.push(fn); return timers.length; },
    resetState: () => { box.result = null; },
    showState: (state) => { box.state = state; },
    showWork: () => { box.state = "work"; },
    renderMultiJobProgress: () => { box.state = "processing"; },
    renderJobState: () => { box.state = "failed"; },
  };
  for (const name of ["renderDocTabs", "renderDocView", "renderRaw", "applyPrescriptionSetSuggestion",
    "redraw", "renderPatientHead", "renderSteps", "loadCheckItems", "loadPreviousFields"])
    box[name] = () => {};
  box.ocrApi = {};
  for (const method of ["jobsForVisit", "job", "result"])
    box.ocrApi[method] = (id) => {
      const pending = deferred(); requests.push({ method, id, ...pending }); return pending.promise;
    };
  vm.createContext(box);
  const mergeStart = source.indexOf("  function mergeResults(");
  const mergeEnd = source.indexOf("  function renderMultiJobProgress(", mergeStart);
  const start = source.indexOf("  function pollAllJobs(");
  const end = source.indexOf("  /* ── 시작", start);
  assert.ok(mergeStart >= 0 && mergeEnd > mergeStart && start >= 0 && end > start);
  vm.runInContext(source.slice(mergeStart, mergeEnd) + source.slice(start, end), box);
  async function answer(method, id, payload) {
    const request = requests.find((r) => r.method === method && r.id === id && !r.done);
    assert.ok(request, `${method} ${id} request missing`);
    request.done = true; request.resolve(payload); await flush(); return request;
  }
  async function complete(id) {
    await answer("jobsForVisit", id, [{ ocr_job_id: id }]);
    await answer("job", id, { ocr_job_id: id, status: "COMPLETED" });
    await answer("result", id, { ocr_result_id: id, documents: [], fields: [] });
  }
  return { box, requests, timers, answer, complete };
}
for (const stage of ["jobsForVisit", "job", "result", "poll"]) {
  for (const rejected of [false, true]) {
    test(`빠른 환자 전환: 이전 ${stage} ${rejected ? "오류" : "응답"}가 새 화면을 덮지 않는다`, async () => {
      const h = harness();
      h.box.loadVisit({ visit_id: "old" });
      if (stage !== "jobsForVisit") await h.answer("jobsForVisit", "old", [{ ocr_job_id: "old" }]);
      if (stage === "result") await h.answer("job", "old", { status: "COMPLETED" });
      if (stage === "poll") {
        await h.answer("job", "old", { status: "PROCESSING", ocr_job_id: "old" });
        h.timers.shift()();
      }
      const pending = h.requests.find((r) => !r.done);
      h.box.loadVisit({ visit_id: "new" });
      await h.complete("new");
      const snapshot = h.box.result;
      if (rejected) pending.reject({ code: "OCR_RESULT_NOT_READY" });
      else pending.resolve(stage === "jobsForVisit" ? [{ ocr_job_id: "old" }] :
        stage === "result" ? { documents: [], fields: [], ocr_result_id: "old" } : { status: "FAILED" });
      await flush();
      assert.equal(h.box.result, snapshot);
      assert.equal(h.box.result.ocr_result_id, "new");
      assert.equal(h.box.state, "work");
    });
  }
}
test("같은 환자로 돌아와도 첫 요청은 무효다 (A → B → A)", async () => {
  const h = harness();
  h.box.loadVisit({ visit_id: "A" });
  const stale = h.requests[0]; stale.done = true;
  h.box.loadVisit({ visit_id: "B" });
  h.box.loadVisit({ visit_id: "A" });
  await h.complete("A");
  const snapshot = h.box.result;
  stale.reject({ code: "NOT_FOUND" }); await flush();
  assert.equal(h.box.result, snapshot); assert.equal(h.box.state, "work");
});
test("시간 초과는 기존 FAILED 재업로드 경로와 한국어 문구를 사용한다", () => {
  const box = load("api", "session", "patients-api", "shell", "ocr-api", "ocr-review");
  assert.equal(box.jobPhase({ status: "FAILED", failure_code: "PROCESSING_TIMEOUT" }).retryByReupload, true);
  assert.match(box.failureSaying("PROCESSING_TIMEOUT").why, /파일을 다시 올려/);
});
