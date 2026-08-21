/* 값 없는 수정 요청이 필드 값을 오염시키지 않는가 — KEY-109 / `#81` 리뷰(이희진).
 *
 * 「이번 미시행」이 충돌하면 「내 값으로 덮기」가 보낼 값이 없는 채로 재전송했다.
 * 목업은 그걸 `String(undefined)` 로 삼켜 **문자열 `"undefined"` 를 검사값으로
 * 저장**했고, `mockFieldById()` 가 저장소 원본 참조를 주므로 재조회해도 남았다.
 *
 * 진짜 서버는 `require_one_value_source`(`app/ocr/schemas.py`)로 거절한다.
 * **목업만 조용히 삼키면 목업으로는 이 결함을 못 잡는다** — 그래서 맞춘다.
 *
 * 여기 값은 전부 합성이다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

function box() {
  return load("api", "ocr-api");
}

/** 고칠 수 있는 필드 하나와 그 상자를 준다. */
async function anEditableField() {
  const api = box();
  const job = await api.ocrApi.jobForVisit(8801);
  const fields = await api.ocrApi.fields(job.ocr_job_id);
  const field = fields.find((f) => !f.is_confirmed);
  assert.ok(field, "고칠 수 있는 필드가 하나는 있어야 한다");
  return { api, field };
}

test("값도 후보도 확정도 없는 수정은 거절한다 — 서버와 같게", async () => {
  const { api, field } = await anEditableField();
  await assert.rejects(
    () => api.ocrApi.updateField(field.ocr_field_id, { base_version: field.version }),
    (error) => error.code === "INVALID_REQUEST",
    "값이 없는 요청은 400 이어야 한다",
  );
});

test('거절된 요청이 필드 값을 "undefined" 로 만들지 않는다', async () => {
  const { api, field } = await anEditableField();
  const before = field.value;
  await api.ocrApi
    .updateField(field.ocr_field_id, { corrected_value: undefined, base_version: field.version })
    .catch(() => {});

  /* 재조회한다 — 저장소가 실제로 오염됐는지는 다시 읽어야 드러난다. */
  const job = await api.ocrApi.jobForVisit(8801);
  const again = (await api.ocrApi.fields(job.ocr_job_id)).find(
    (f) => f.ocr_field_id === field.ocr_field_id,
  );
  assert.notStrictEqual(again.value, "undefined", '값이 문자열 "undefined" 가 됐다');
  assert.strictEqual(again.value, before, "거절된 요청이 값을 바꿨다");
  assert.strictEqual(again.version, field.version, "거절된 요청이 버전을 올렸다");
});

test("확정만 하는 요청은 값을 건드리지 않는다", async () => {
  const { api, field } = await anEditableField();
  const before = field.value;
  const updated = await api.ocrApi.updateField(field.ocr_field_id, {
    confirm: true,
    base_version: field.version,
  });
  assert.strictEqual(updated.value, before, "확정이 값을 바꿨다");
  assert.strictEqual(updated.is_confirmed, true);
  assert.ok(updated.confirmed_at, "확정 시각이 비어 있다");
});

test("정상 수정은 그대로 저장된다 — 가드가 길을 막지 않는다", async () => {
  const { api, field } = await anEditableField();
  const updated = await api.ocrApi.updateField(field.ocr_field_id, {
    corrected_value: "10.4",
    base_version: field.version,
  });
  assert.strictEqual(updated.value, "10.4");
  assert.strictEqual(updated.version, field.version + 1);
});
