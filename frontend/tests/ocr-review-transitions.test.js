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

/* ── 판독이 실패해도 화면을 덮지 않는다 ─────────────────────────────── */

const { codeOnly: strip2, read: read2 } = require("./source.js");

test("**실패는 위에 붙고, 나머지는 덮는다**", () => {
  const { stateRules } = load("api", "session", "patients-api", "shell", "ocr-api", "ocr-review");
  const rules = stateRules();

  /* 판독이 실패해도 값은 사람이 눈으로 읽어 넣을 수 있어야 한다.
     덮어 버리면 그 길이 막힌다 — 사진은 멀쩡한데 표 한 칸을 못 읽어서
     화면이 통째로 막히던 것이 1차 시연이 멈춘 방식이다. */
  assert.equal(rules.job_failed.keepsWork, true, "판독 실패가 화면을 덮는다 — 직접 적을 길이 막힌다");

  /* 아래에 보여 줄 것이 아직 없는 상태는 덮어야 한다. 반쯤 그린 값을
     보여 주면 그것을 판독 결과로 읽는다. */
  for (const kind of ["loading", "processing", "not_ready", "poll_failed", "result_failed"]) {
    assert.equal(rules[kind].keepsWork, false, `${kind} 이 반쯤 그린 화면을 보여 준다`);
  }

  /* **아직 아무것도 안 올린 것은 다르다.** 방금 등록한 환자가 처음 만나는
     화면이고 여기서 할 수 있는 일이 올리는 것뿐이라, 통째로 덮으면 「없다」는
     말만 남고 다음 걸음이 사라진다. 왼쪽(올리는 자리)만 남긴다 — 오른쪽
     판독 값은 읽은 것이 없어 빈 칸만 늘어선다. */
  assert.equal(rules.no_job.keepsWork, "left", "올릴 자리까지 덮는다 — 다음 걸음이 사라진다");

  /* **화면이 그 규칙을 실제로 본다.** 규칙만 있고 `hidden = true` 를 그대로
     두면 검사가 안 문다 — 돌연변이를 넣어 보고 알았다. 그리는 것은 shim
     아래서 안 돌기 때문에 원문으로 잰다. */
  const code = strip2(read2("js/ocr-review.js"));
  const at = code.indexOf('getElementById("work").hidden');
  assert.notEqual(at, -1, "작업 칸을 감추는 자리가 없다 — 검사가 헛돈다");

  const line = code.slice(at, code.indexOf(";", at));
  assert.match(line, /rule\.keepsWork/, `규칙을 안 보고 늘 덮는다: 「${line.trim()}」`);
});

test("**실패해도 빈 프레임을 세운다** — 결과가 없어도 적을 자리는 있어야 한다", () => {
  const code = strip2(read2("js/ocr-review.js"));
  const at = code.indexOf('showState(\n        "job_failed"');
  assert.notEqual(at, -1, "실패를 그리는 자리가 없다 — 검사가 헛돈다");

  const around = code.slice(Math.max(0, at - 400), at + 500);
  assert.match(around, /if \(!result\) result = \{/, "결과가 없을 때 빈 것을 안 세운다");
  assert.match(around, /documents: \[\], fields: \[\]/, "빈 것의 모양이 다르다");
  assert.ok(around.includes("redraw()"), "빈 프레임을 안 그린다");
  assert.match(around, /직접 적거나/, "직접 적을 수 있다는 것을 안 알린다");
});

test("**값이 하나도 없으면 안내문 만들기를 미리 잠근다** — 눌러도 422 로 떨어진다", () => {
  const { noFieldsSaying } = load("ocr-groups");

  assert.equal(noFieldsSaying([{ field_type: "DIAGNOSIS" }]), "", "값이 있는데 잠갔다");
  assert.match(noFieldsSaying([]), /만들 수 없습니다/, "왜 안 되는지 안 말한다");
  assert.match(noFieldsSaying([]), /다시 올리|자리가 붙으면/, "무엇을 하면 되는지 안 말한다");

  const code = strip2(read2("js/ocr-review.js"));
  assert.ok(code.includes("noFieldsSaying(result.fields)"), "화면이 그 규칙을 안 쓴다");
});

test("**읽은 것이 없으면 왼쪽만 남는다** — 빈 값 칸은 고장으로 읽힌다", () => {
  const code = strip2(read2("js/ocr-review.js"));
  const at = code.indexOf('getElementById("work").hidden');
  assert.notEqual(at, -1, "작업 칸을 감추는 자리가 없다 — 검사가 헛돈다");

  const around = code.slice(at, at + 400);
  assert.match(around, /review--left/, "왼쪽만 남기는 자리가 없다");
  assert.match(around, /keepsWork === "left"/, "규칙을 안 읽고 스스로 정한다");

  /* 감추는 규칙이 CSS 에도 있어야 한다 — 클래스만 붙이고 규칙이 없으면 그대로 뜬다 */
  const css = read2("css/ocr-review.css");
  assert.match(css, /\.review--left \.main-col \{[^}]*display:\s*none/, "값 칸이 안 감춰진다");
});

test("올릴 자리가 저절로 펴진다 — 접힌 채면 올릴 데를 못 찾는다", () => {
  const code = strip2(read2("js/ocr-review.js"));
  const at = code.indexOf('"no_job"');
  assert.notEqual(at, -1, "판독 없음 갈래가 없다");

  const around = code.slice(Math.max(0, at - 300), at + 200);
  assert.match(around, /ocrOpenAddPanel/, "올리는 판을 안 편다");

  /* 펴는 자리가 실제로 있어야 한다 */
  assert.match(code, /window\.ocrOpenAddPanel\s*=/, "펴는 함수가 없다");
});
