/* 판독 리뷰 화면의 **전환 규칙** — KEY-158 (KEY-62 / PR `#40` 의 수동 확인 이관).
 *
 * `#40` 리뷰에서 셋을 눈으로만 확인하고 넘겼다. 화면 파일이 IIFE 라 검사기가
 * 부를 수 없었기 때문이다. 이제 규칙이 IIFE 밖에 있어 부를 수 있다.
 *
 *   ① 환자를 바꾸면 앞 환자 상태가 하나도 남지 않는다
 *   ② 판독 실패는 화면을 막지 않는다 — 재업로드로 되돌아갈 수 있다
 *   ③ 판독 완료면 결과 화면으로 넘어간다
 *
 * 그리는 것은 여기서 재지 않는다. 껍데기로 흉내내면 「검사에서는 되는데
 * 브라우저에서는 안 되는」 거리가 벌어진다 — 화면은 눈으로 본다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

function box() {
  return load("api", "session", "patients-api", "shell", "ocr-api", "ocr-review");
}

/* ── ① 환자 전환 ─────────────────────────────────────────────────────── */

test("환자를 바꾸면 앞 환자의 편집·충돌·저장 표시가 하나도 안 남는다", () => {
  const { blankReviewState } = box();
  const fresh = blankReviewState();

  /* 앞 환자를 보던 상태를 흉내낸다 — 값이 남는 칸을 전부 채운다. */
  fresh.result = { fields: [{ id: 1 }] };
  fresh.activeDoc = 7;
  fresh.openCandidates[11] = true;
  fresh.editing[11] = "치던 값";
  fresh.saving[11] = true;
  fresh.saved[12] = true;
  fresh.failed[13] = { code: "CONFLICT" };
  fresh.conflict[13] = { mine: "내 값", theirs: "옆자리 값" };
  fresh.focusOn = 11;

  const next = blankReviewState();

  assert.strictEqual(next.result, null);
  assert.strictEqual(next.activeDoc, null);
  assert.strictEqual(next.focusOn, null);
  for (const key of ["openCandidates", "editing", "saving", "saved", "failed", "conflict"]) {
    assert.deepStrictEqual(Object.keys(next[key]), [], `${key} 에 앞 환자 것이 남았다`);
  }
});

test("버릴 칸 목록이 화면이 실제로 쓰는 칸과 같다", () => {
  /* 상태 칸이 늘었는데 초기화를 잊는 것이 이 화면에서 제일 흔한 사고다.
     `resetState()` 가 손으로 나열하지 않고 이 표를 그대로 쓰는지 원문으로
     확인한다 — 나열로 돌아가면 하나를 빠뜨릴 수 있다. */
  const fs = require("node:fs");
  const path = require("node:path");
  const source = fs.readFileSync(path.join(__dirname, "..", "js", "ocr-review.js"), "utf8");

  assert.match(source, /var blank = blankReviewState\(\);/, "resetState 가 표를 안 쓴다");
  assert.match(source, /var view = blankReviewState\(\);/, "처음 값도 표에서 받아야 한다");

  const { blankReviewState } = box();
  for (const key of Object.keys(blankReviewState())) {
    assert.match(source, new RegExp(`${key} = blank\\.${key};`), `resetState 가 ${key} 를 안 되돌린다`);
  }
});

/* ── ② 판독 실패 ─────────────────────────────────────────────────────── */

test("판독 실패는 화면을 막지 않는다 — 재업로드로 되돌아갈 수 있다", () => {
  const { jobPhase } = box();
  const failed = jobPhase({ status: "FAILED", failure_code: "UNREADABLE" });

  assert.strictEqual(failed.phase, "failed");
  assert.strictEqual(failed.retryByReupload, true, "되돌아갈 길이 없으면 스탭이 멈춘다");
  assert.strictEqual(failed.showsWork, false);
});

/* ── ③ 판독 완료 ─────────────────────────────────────────────────────── */

test("판독 완료면 결과 화면으로 넘어간다", () => {
  const { jobPhase } = box();
  const done = jobPhase({ status: "COMPLETED" });

  assert.strictEqual(done.phase, "ready");
  assert.strictEqual(done.showsWork, true);
});

test("판독 중이면 기다리는 화면에 머문다", () => {
  const { jobPhase } = box();
  const running = jobPhase({ status: "PROCESSING", progress: 40 });

  assert.strictEqual(running.phase, "processing");
  assert.strictEqual(running.showsWork, false, "결과 화면으로 넘어가면 빈 표가 뜬다");
});

test("모르는 상태는 막지 않는다 — 결과 화면으로 보낸다", () => {
  /* 서버가 새 상태를 주기 시작해도 스탭이 갇히지 않아야 한다.
     기다리는 화면에 세우면 영영 안 바뀐다. */
  const { jobPhase } = box();
  assert.strictEqual(jobPhase({ status: "SOMETHING_NEW" }).phase, "ready");
  assert.strictEqual(jobPhase(null).phase, "ready");
});
