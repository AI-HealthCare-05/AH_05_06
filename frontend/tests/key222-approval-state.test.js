/* KEY-222 — 스탭 확인 → 의사 승인 → 반려·재제출 상태전이.
 *
 * 실서버 경로는 KEY-234에서 이미 검증한다. 이 파일은 같은 화면이 쓰는 `?mock=1`
 * 경로가 서버보다 뒤처져 데모에서만 404/403이 나는 회귀를 막는다. 테스트 데이터는
 * `doctor-api.js`의 합성 fixture만 사용한다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

const VISIT = 8801;

function staffBox() {
  return load("api", "doctor-api", { search: "?mock=1&case=staff" });
}

test("스탭 확인 상태에서 수정하고 의사 승인 요청으로 넘긴다", async () => {
  const api = staffBox();
  const guide = await api.doctorApi.guide(VISIT);
  const open = guide.sections.find((section) => !section.locked);

  assert.strictEqual(guide.status, "STAFF_REVIEW");

  const edited = await api.doctorApi.editSection(VISIT, open.key, {
    body: "  스탭이 확인한 합성 문장  ",
  });
  assert.strictEqual(edited.body, "스탭이 확인한 합성 문장");

  const submitted = await api.doctorApi.submit(VISIT);
  assert.strictEqual(submitted.status, "APPROVAL_PENDING");
  assert.strictEqual(submitted.returned_reason, null);

  const persisted = await api.doctorApi.guide(VISIT);
  assert.strictEqual(persisted.status, "APPROVAL_PENDING");
  assert.strictEqual(persisted.sections.find((section) => section.key === open.key).body, edited.body);
});

test("의사에게 넘긴 뒤에는 스탭이 내용을 바꿀 수 없다", async () => {
  const api = staffBox();
  const guide = await api.doctorApi.guide(VISIT);
  const open = guide.sections.find((section) => !section.locked);
  await api.doctorApi.submit(VISIT);

  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, open.key, { body: "승인 대기 중 변경" }),
    (error) => error.code === "FORBIDDEN" && error.status === 403,
  );
});

test("반려 사유를 보고 수정한 뒤 재제출하면 현재 사유만 지워진다", async () => {
  const api = staffBox();
  const guide = await api.doctorApi.guide(VISIT);
  const open = guide.sections.find((section) => !section.locked);

  api.MOCK_GUIDE_STATE[VISIT] = {
    status: "APPROVAL_RETURNED",
    approved_at: null,
    scheduled_at: null,
    returned_reason: "복약 시점을 보완해 주세요",
    patient_link_issued: false,
    sections: {},
  };

  const returned = await api.doctorApi.guide(VISIT);
  assert.strictEqual(returned.returned_reason, "복약 시점을 보완해 주세요");

  await api.doctorApi.editSection(VISIT, open.key, { body: "아침 식후 30분에 복용" });
  const resubmitted = await api.doctorApi.submit(VISIT);
  assert.strictEqual(resubmitted.status, "APPROVAL_PENDING");
  assert.strictEqual(resubmitted.returned_reason, null);

  await assert.rejects(
    () => api.doctorApi.submit(VISIT),
    (error) => error.code === "GUIDE_NOT_IN_REVIEW" && error.status === 409,
    "재제출을 두 번 허용했다",
  );
});
