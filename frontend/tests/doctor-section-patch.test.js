/* 잠긴 섹션을 목업도 막는가 — KEY-86 / `#76` 리뷰(이희진).
 *
 * 🚨 응급 문장은 식약처 정보를 근거로 미리 써 둔 것이라 사람이 고칠 자리가
 * 아니다. 서버는 `SECTION_LOCKED` 409 로 막는데(`app/services/guides.py`),
 * 목업은 통과시켰다. **목업이 서버보다 헐거우면 화면 버그를 목업으로 못 잡는다** —
 * 잠긴 섹션에 [수정]이 열리는 회귀가 나도 목업에서는 저장까지 성공한다.
 *
 * 여기 값은 전부 합성이다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

const VISIT = 8801;

function box() {
  return load("api", "doctor-api");
}

test("잠긴 섹션은 목업도 409 SECTION_LOCKED 로 막는다", async () => {
  const api = box();
  const guide = await api.doctorApi.guide(VISIT);
  const locked = guide.sections.find((s) => s.locked);
  assert.ok(locked, "잠긴 섹션이 하나는 있어야 이 검사가 성립한다");

  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, locked.key, { body: "사람이 고쳐 본다" }),
    (error) => error.code === "SECTION_LOCKED" && error.status === 409,
    "잠긴 섹션 수정이 통과했다",
  );
});

test("안 잠긴 섹션은 그대로 고쳐진다 — 가드가 길을 막지 않는다", async () => {
  const api = box();
  const guide = await api.doctorApi.guide(VISIT);
  const open = guide.sections.find((s) => !s.locked);
  assert.ok(open, "고칠 수 있는 섹션이 하나는 있어야 한다");

  const updated = await api.doctorApi.editSection(VISIT, open.key, { body: "고친 문장" });
  assert.strictEqual(updated.key, open.key);
  assert.strictEqual(updated.body, "고친 문장");
  assert.strictEqual(updated.edited, true);
});

test("없는 섹션은 404 다 — 잠금 판정이 그 앞을 가리지 않는다", async () => {
  const api = box();
  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, "그런키없음", { body: "x" }),
    (error) => error.status === 404,
  );
});

/* 이희진 님 `#76` 리뷰 — `SECTION_LOCKED` 와 같은 기준.
 *
 * 서버는 `APPROVAL_PENDING` 이 아닌 안내문의 섹션 수정을 `GUIDE_NOT_PENDING`
 * 409 로 막는다. 이미 승인해 발송을 기다리는 글을 조용히 바꾸면 **환자가 받는
 * 것과 의사가 승인한 것이 달라진다.**
 *
 * 목업에는 그 검사가 없었고, 더 근본적으로 **안내문 상태를 저장하지 않았다** —
 * 승인해도 다음 조회는 다시 「승인 요청」이라 상태에 걸리는 규칙을 잴 수조차
 * 없었다.
 */
test("승인 뒤에는 섹션을 못 고친다 — 409 GUIDE_NOT_PENDING", async () => {
  const api = box();
  const before = await api.doctorApi.guide(VISIT);
  const open = before.sections.find((s) => !s.locked);
  assert.strictEqual(before.status, "APPROVAL_PENDING", "시작 상태가 승인 요청이 아니다");

  await api.doctorApi.approve(VISIT);

  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, open.key, { body: "승인 뒤에 몰래 고친다" }),
    (error) => error.code === "GUIDE_NOT_PENDING" && error.status === 409,
    "승인된 안내문의 섹션 수정이 통과했다",
  );
});

test("승인이 상태를 남긴다 — 다시 조회해도 발송 대기다", async () => {
  const api = box();
  await api.doctorApi.approve(VISIT);

  const after = await api.doctorApi.guide(VISIT);
  assert.strictEqual(after.status, "SCHEDULED_TO_SEND", "승인이 다음 조회에 안 남았다");
  assert.ok(after.scheduled_at, "발송 예정 시각이 비어 있다");
});

test("반려 뒤에도 섹션을 못 고친다 — 스탭 손에 있는 글이다", async () => {
  const api = box();
  const before = await api.doctorApi.guide(VISIT);
  const open = before.sections.find((s) => !s.locked);

  await api.doctorApi.returnToStaff(VISIT, "검사 결과지를 다시 올려 주세요");

  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, open.key, { body: "반려 뒤에 고친다" }),
    (error) => error.code === "GUIDE_NOT_PENDING" && error.status === 409,
    "반려된 안내문의 섹션 수정이 통과했다",
  );
});
