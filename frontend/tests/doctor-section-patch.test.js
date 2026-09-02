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

test("없는 섹션은 404 SECTION_NOT_FOUND 다 — 잠금 판정이 그 앞을 가리지 않는다", async () => {
  const api = box();
  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, "그런키없음", { body: "x" }),
    /* 계약(`docs/api/hospital.md` §918)이 정한 이름이다. 상태만 재면 목업이
       뭉뚱그린 `NOT_FOUND` 를 줘도 통과한다. */
    (error) => error.code === "SECTION_NOT_FOUND" && error.status === 404,
  );
});

/* 이희진 님 `#76` 리뷰 — `SECTION_LOCKED` 와 같은 기준.
 *
 * 서버는 스탭 확인·승인 요청·반려 상태에서만 섹션 수정을 허용하고, 이미 승인해
 * 발송을 기다리는 글은 `GUIDE_NOT_PENDING` 409 로 막는다. 승인 뒤에 조용히
 * 바꾸면 **환자가 받는 것과 의사가 승인한 것이 달라진다.**
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

test("반려 뒤에는 섹션을 고칠 수 있다 — 보완 후 재제출할 수 있어야 한다", async () => {
  const api = box();
  const before = await api.doctorApi.guide(VISIT);
  const open = before.sections.find((s) => !s.locked);

  await api.doctorApi.returnToStaff(VISIT, "검사 결과지를 다시 올려 주세요");

  const updated = await api.doctorApi.editSection(VISIT, open.key, { body: "반려 뒤에 고친다" });
  assert.strictEqual(updated.body, "반려 뒤에 고친다");
  assert.strictEqual(updated.edited, true);
});

/* ── 두 번 승인 — `ALREADY_APPROVED` (이희진 님 `#76` 리뷰) ───────────────
 *
 * 「이 PR 의 주제가 승인 경합인데, 정작 이중 승인을 목업으로 검증할 방법이
 * 없으면 이 PR 이 고치려는 것 자체를 못 재는 셈입니다.」
 *
 * 서버 `_require_pending()` 은 상태를 **두 갈래**로 센다. 뭉뚱그리면 두 번
 * 승인이 조용히 통과하고 **발송 예정 시각이 뒤로 밀린다.**
 */

test("두 번 승인은 409 ALREADY_APPROVED 다 — 발송 시각이 밀리지 않는다", async () => {
  const api = box();
  const first = await api.doctorApi.approve(VISIT, {});
  assert.strictEqual(first.status, "SCHEDULED_TO_SEND");

  await assert.rejects(
    () => api.doctorApi.approve(VISIT, {}),
    (error) => error.code === "ALREADY_APPROVED" && error.status === 409,
    "두 번째 승인이 통과했다",
  );

  /* 막혔으니 **예약 시각도 그대로**여야 한다. 코드만 맞고 상태가 덮여
     쓰이면 승인 경합을 막은 것이 아니다. */
  const again = await api.doctorApi.guide(VISIT);
  assert.strictEqual(again.scheduled_at, first.scheduled_at);
});

test("첫 승인은 막히지 않는다 — 가드가 길을 막지 않는다", async () => {
  const api = box();
  const guide = await api.doctorApi.guide(VISIT);
  assert.strictEqual(guide.status, "APPROVAL_PENDING");

  const approved = await api.doctorApi.approve(VISIT, {});
  assert.strictEqual(approved.status, "SCHEDULED_TO_SEND");
  assert.ok(approved.scheduled_at, "예약 시각이 실려야 한다");
});

test("승인된 글은 반려도 못 한다 — 서버와 같은 문을 지난다", async () => {
  const api = box();
  await api.doctorApi.approve(VISIT, {});

  await assert.rejects(
    () => api.doctorApi.returnToStaff(VISIT, "역시 다시 보겠습니다"),
    (error) => error.code === "ALREADY_APPROVED" && error.status === 409,
    "승인된 글의 반려가 통과했다",
  );
});

test("반려된 글의 재승인은 GUIDE_NOT_PENDING 이다 — ALREADY_APPROVED 가 아니다", async () => {
  const api = box();
  await api.doctorApi.returnToStaff(VISIT, "검사지를 다시 올려 주세요");

  await assert.rejects(
    () => api.doctorApi.approve(VISIT, {}),
    (error) => error.code === "GUIDE_NOT_PENDING" && error.status === 409,
    "반려 상태의 승인이 통과했거나 코드가 뒤바뀌었다",
  );
});

test("승인된 글의 잠긴 섹션은 SECTION_LOCKED 다 — 서버와 검사 순서가 같다", async () => {
  const api = box();
  const guide = await api.doctorApi.guide(VISIT);
  const locked = guide.sections.find((s) => s.locked);
  assert.ok(locked, "잠긴 섹션이 하나는 있어야 이 검사가 성립한다");
  await api.doctorApi.approve(VISIT, {});

  /* 서버 `edit_section()` 은 잠금을 먼저 본다. 목업이 상태를 먼저 보면
     같은 요청에 `GUIDE_NOT_PENDING` 이 나와 서버와 갈린다. */
  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, locked.key, { body: "사람이 고쳐 본다" }),
    (error) => error.code === "SECTION_LOCKED" && error.status === 409,
    "승인 뒤 잠긴 섹션의 오류 코드가 서버와 다르다",
  );
});

/* ── 빈 본문 — `EMPTY_BODY` 422 (이희진 님 `#76` 리뷰) ────────────────────
 *
 * 「여기서 마저 함께 막아주시면 좋겠습니다.」
 *
 * 서버 `edit_section()` 은 받은 값을 `strip()` 한 뒤 비어 있으면 422 로 막는다.
 * 목업은 빈 문자열을 그대로 저장했다 — 승인된 안내문의 한 갈래가 빈 채로
 * 환자에게 갈 수 있는데, 화면 회귀를 목업으로는 못 잡았다.
 */

test("빈 본문은 422 EMPTY_BODY 다 — 문장이 통째로 비지 않는다", async () => {
  const api = box();
  const guide = await api.doctorApi.guide(VISIT);
  const open = guide.sections.find((s) => !s.locked);

  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, open.key, { body: "" }),
    (error) => error.code === "EMPTY_BODY" && error.status === 422,
    "빈 본문 저장이 통과했다",
  );
});

test("공백만 있는 본문도 빈 것이다 — 서버가 다듬은 뒤 판정한다", async () => {
  const api = box();
  const guide = await api.doctorApi.guide(VISIT);
  const open = guide.sections.find((s) => !s.locked);

  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, open.key, { body: "   \n\t  " }),
    (error) => error.code === "EMPTY_BODY" && error.status === 422,
    "공백만 있는 본문이 통과했다 — 다듬지 않고 판정한 것이다",
  );
});

test("없는 섹션에 빈 본문이면 SECTION_NOT_FOUND 다 — 서버와 검사 순서가 같다", async () => {
  const api = box();

  /* 서버 `edit_section()` 은 `GuideSectionKey(key)` 파싱을 doctor 권한 검사
     바로 다음, `strip()` 검사보다 앞에서 한다. 키가 유효하지 않으면 본문을
     보기도 전에 `SECTION_NOT_FOUND` 다 — 목업이 순서를 바꾸면 같은 요청에
     `EMPTY_BODY` 가 나와 서버와 갈린다. */
  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, "그런키없음", { body: "" }),
    (error) => error.code === "SECTION_NOT_FOUND" && error.status === 404,
    "섹션 조회보다 빈 본문 검사가 앞서 있다",
  );
});

test("저장되는 본문은 앞뒤 공백이 잘린다 — 서버가 다듬은 값을 넣는다", async () => {
  const api = box();
  const guide = await api.doctorApi.guide(VISIT);
  const open = guide.sections.find((s) => !s.locked);

  const updated = await api.doctorApi.editSection(VISIT, open.key, { body: "  고친 문장  " });
  assert.strictEqual(updated.body, "고친 문장");
});

/* ── 수정이 남는가 — `mockGuideState()` 부분 갱신 ─────────────────────────
 *
 * 예전에는 PATCH 가 고친 본문을 응답에만 실어 보내고 저장하지 않았다.
 * `mockGuide()` 가 매번 `mockGuideBase()` 로 새로 만들어서, 고치고 다시
 * 조회하면 고치기 전 문장이 다시 나왔다 — 편집 UI 가 붙는 날 「저장했는데
 * 새로고침하면 원래대로 돌아온다」가 재현될 자리였다.
 */

test("섹션을 고치고 다시 조회해도 고친 본문이 남는다", async () => {
  const api = box();
  const guide = await api.doctorApi.guide(VISIT);
  const open = guide.sections.find((s) => !s.locked);

  await api.doctorApi.editSection(VISIT, open.key, { body: "다시 조회해도 남아야 한다" });

  const again = await api.doctorApi.guide(VISIT);
  const target = again.sections.find((s) => s.key === open.key);
  assert.strictEqual(target.body, "다시 조회해도 남아야 한다");
  assert.strictEqual(target.edited, true);
});

test("섹션 수정 뒤 승인해도 그 수정은 지워지지 않는다 — 부분 갱신이다", async () => {
  const api = box();
  const guide = await api.doctorApi.guide(VISIT);
  const open = guide.sections.find((s) => !s.locked);

  await api.doctorApi.editSection(VISIT, open.key, { body: "승인 전에 고친 문장" });
  await api.doctorApi.approve(VISIT, {});

  const after = await api.doctorApi.guide(VISIT);
  const target = after.sections.find((s) => s.key === open.key);
  assert.strictEqual(after.status, "SCHEDULED_TO_SEND");
  assert.strictEqual(target.body, "승인 전에 고친 문장", "승인이 이전 수정을 통째로 덮어썼다");
});

/* ── `/guide/sections/{key}` 에 잘못된 메서드 ──────────────────────────
 *
 * `sec` 정규식이 이 경로를 「안다」고만 표시하고, PATCH 가 아닌 메서드는
 * 따로 막지 않았다. 그래서 GET 같은, 서버에는 없는 라우트가 조용히 200 과
 * 전체 guide 를 돌려주고 있었다 — 실제로는 404/405 여야 한다.
 */

test("섹션 경로에 GET 을 보내면 404 다 — 그런 라우트는 서버에 없다", async () => {
  const api = box();
  await assert.rejects(
    () => api.mockDoctorRequest("/visits/" + VISIT + "/guide/sections/medication", {}),
    (error) => error.status === 404,
    "섹션 경로에 대한 GET 이 통과했다",
  );
});
