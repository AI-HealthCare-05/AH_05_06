/* **「확인 완료」가 서버에 확정을 보내는가** — B1.
 *
 * 와이어프레임 `S1-6` 의 버튼은 「확인 완료 · 안내문 생성」 하나다. 확정과
 * 생성이 한 동작이다. 그런데 화면은 생성만 불렀다 — `frontend/js/` 어디에서도
 * `confirm` 을 서버로 보내지 않았다.
 *
 * 서버는 이렇게 막는다 (`app/services/guides.py`).
 *
 *     confirmed = await OcrField.filter(..., is_confirmed=True).first()
 *     if confirmed is None:
 *         raise ApiError("OCR_NOT_CONFIRMED", 422, ...)
 *
 * 그리고 `is_confirmed` 를 세우는 자리는 `app/ocr/service.py` 의
 * `if request.confirm:` 한 곳뿐이다. **그래서 실서버에서는 안내문이 한 번도
 * 만들어지지 않았다.** 목업은 확정을 흉내 내므로 `?mock=1` 로는 잘 돌았다 —
 * 1차 시연에서 이 차이를 못 봤다.
 *
 * 그리는 코드는 shim 아래서 안 돌기 때문에, 배선은 원문으로 잰다.
 * 그 대신 **글자가 아니라 코드 줄**을 보고, 자리가 없으면 검사가 헛도는 것을
 * 알 수 있게 가드를 둔다 (이 폴더의 관례).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");

function box() {
  return load("api", "session", "patients-api", "shell", "ocr-api", "ocr-review");
}

function source() {
  return fs.readFileSync(path.join(ROOT, "js", "ocr-review.js"), "utf8");
}

/* ── 무엇을 확정할 것인가 (순수 규칙) ──────────────────────────────────── */

test("이미 확정된 항목은 다시 보내지 않는다 — 409 가 난다", () => {
  const { fieldsToConfirm } = box();

  const picked = fieldsToConfirm([
    { ocr_field_id: 1, value: "비잔정", is_confirmed: true },
    { ocr_field_id: 2, value: "84", is_confirmed: false },
  ]);

  assert.deepEqual(
    picked.map((f) => f.ocr_field_id),
    [2],
    "확정된 것을 또 보내면 서버가 409 OCR_FIELD_CONFIRMED 로 막는다",
  );
});

test("값이 없는 항목은 확정하지 않는다 — 빈칸이 안내문에 그대로 나간다", () => {
  const { fieldsToConfirm } = box();

  const picked = fieldsToConfirm([
    { ocr_field_id: 1, value: null, is_confirmed: false },
    { ocr_field_id: 2, value: "", is_confirmed: false },
    { ocr_field_id: 3, value: "자궁내막증", is_confirmed: false },
  ]);

  assert.deepEqual(
    picked.map((f) => f.ocr_field_id),
    [3],
    "못 읽은 칸을 확정하면 빈 값이 환자 안내문에 실린다",
  );
});

test("빈 목록·없는 값에도 죽지 않는다", () => {
  const { fieldsToConfirm } = box();

  assert.deepEqual(fieldsToConfirm([]), []);
  assert.deepEqual(fieldsToConfirm(null), []);
  assert.deepEqual(fieldsToConfirm(undefined), []);
});

/* ── 배선 ──────────────────────────────────────────────────────────────── */

test("**생성보다 확정이 먼저다** — 순서가 뒤집히면 첫 요청이 늘 422 다", () => {
  const text = source();

  /* 파일 전체가 아니라 **버튼 핸들러 안**만 본다. `confirmShownFields` 는
     정의부가 호출부보다 앞에 있어서, 파일 전체로 재면 정의를 호출로 착각한다. */
  const handlerAt = text.indexOf('target.id === "submit"');
  assert.notEqual(handlerAt, -1, "생성 버튼 핸들러가 없다 — 검사가 헛돈다");

  const handler = text.slice(handlerAt, handlerAt + 1600);

  const confirmAt = handler.indexOf("confirmShownFields()");
  const generateAt = handler.indexOf(".generateGuide(");

  assert.notEqual(confirmAt, -1, "핸들러가 확정을 안 부른다 — 실서버에서 늘 422 다");
  assert.notEqual(generateAt, -1, "핸들러가 생성을 안 부른다 — 검사가 헛돈다");
  assert.ok(
    confirmAt < generateAt,
    "생성을 먼저 부른다 — 확정된 항목이 없어 서버가 422 OCR_NOT_CONFIRMED 로 막는다",
  );

  /* 둘이 같은 사슬에 있어야 한다. 사이에 다른 갈래가 끼면 확정을 건너뛰고
     생성으로 가는 길이 생긴다. */
  const between = handler.slice(confirmAt, generateAt);
  assert.ok(
    !between.includes("if ("),
    `확정과 생성 사이에 갈래가 있다 — 확정을 건너뛰는 길이 남는다: 「${between.trim()}」`,
  );
});

test("**처방을 못 세워도 안내문은 만든다** — 다리가 막는 쪽이 되면 안 된다", () => {
  /* `ocr-finalize` 는 생성보다 조건이 둘 더 많다 — `PRESCRIPTION_SET` 과
     `FREQUENCY`. 그 둘이 없는 진료도 **여태 안내문은 만들어졌다**(세트를 못
     찾아 기본 문구로 나갔을 뿐이다).

     그 둘을 사슬에서 죽게 두면 이 다리가 **없던 것보다 나빠진다** — 처방 행을
     세우려다 안내문 자체를 못 만들게 된다. */
  const { finalizeMayPass } = box();

  assert.equal(finalizeMayPass({ code: "MISSING_PRESCRIPTION_SET" }), null);
  assert.equal(finalizeMayPass({ code: "MISSING_FREQUENCY" }), null);
});

test("**진짜 막아야 하는 것은 그대로 던진다** — 미확정을 넘기면 확정의 뜻이 없다", () => {
  const { finalizeMayPass } = box();

  [{ code: "OCR_NOT_CONFIRMED" }, { code: "FORBIDDEN" }, { code: "VISIT_NOT_FOUND" }, {}].forEach((e) => {
    assert.throws(
      () => finalizeMayPass(e),
      `${e.code || "코드 없음"} 을 삼켰다 — 사슬이 조용히 이어진다`,
    );
  });
});

test("사슬이 확정 → 처방 → 생성 차례다 — 처방이 확정보다 먼저면 늘 422 다", () => {
  const text = source();
  const at = text.indexOf('target.id === "submit"');
  assert.notEqual(at, -1, "생성 버튼 핸들러가 없다 — 검사가 헛돈다");
  const handler = text.slice(at, at + 1600);

  const confirmAt = handler.indexOf("confirmShownFields()");
  const finalizeAt = handler.indexOf(".finalizeOcr(");
  const generateAt = handler.indexOf(".generateGuide(");

  assert.notEqual(finalizeAt, -1, "핸들러가 처방을 안 세운다 — KEY-271 다리가 없다");
  assert.ok(confirmAt < finalizeAt, "처방이 확정보다 먼저다 — finalize 가 늘 422 다");
  assert.ok(finalizeAt < generateAt, "안내문을 먼저 만든다 — 처방 행이 없는 채로 나간다");
});

test("확정 요청이 `confirm` 을 싣는다 — 이게 없으면 서버가 아무것도 안 굳힌다", () => {
  const text = source();

  const start = text.indexOf("function confirmShownFields");
  assert.notEqual(start, -1, "confirmShownFields 가 없다 — 검사가 헛돈다");

  const body = text.slice(start, start + 900);
  assert.ok(body.includes("confirm: true"), "확정 요청에 confirm 이 없다");
  assert.ok(body.includes("base_version"), "base_version 없이 보내면 서버가 거절한다");
  assert.ok(
    body.includes("fieldsToConfirm("),
    "무엇을 확정할지 규칙을 안 쓴다 — 확정된 것을 또 보내거나 빈칸을 굳힌다",
  );
});

/* ── 확정이 실패했을 때 ────────────────────────────────────────────────── */

test("확정 쪽 오류도 사람 말로 나온다 — 서버 문구는 흘리지 않는다", () => {
  const { generateFailureSaying } = box();

  const conflict = generateFailureSaying({
    code: "VERSION_CONFLICT",
    status: 409,
    message: "환자 윤지아 · 비잔정 2mg",
  });

  assert.match(conflict, /값이 바뀌었/, "무엇을 해야 하는지 말해 주지 않는다");
  assert.ok(!conflict.includes("윤지아"), `서버 문구가 새어 나왔다: ${conflict}`);
  assert.ok(!conflict.includes("비잔정"), `서버 문구가 새어 나왔다: ${conflict}`);
});
