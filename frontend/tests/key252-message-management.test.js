const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

test("발송 예정 미리보기와 발송 이력 재발송 경로가 연결된다", () => {
  const api = codeOnly(read("js/messages-api.js"));
  const screen = codeOnly(read("js/manage.js"));

  assert.match(api, /\/visits\/.*\/guide/);
  assert.match(api, /\/messages\/history\/.*\/resend/);
  assert.match(screen, /data-preview-visit/);
  assert.match(screen, /data-resend-message/);
  assert.match(screen, /patientGuidePreviewHtml/);
  assert.match(screen, /messageResendResultHtml\(body\)/);
});

test("관리 화면은 공용 환자 카드 렌더러만 불러온다", () => {
  const html = markupOnly(read("manage.html"));

  assert.match(html, /\/js\/patient-guide-cards\.js/);
  assert.doesNotMatch(html, /patient_wireframe\/js\/guide\.js/);
});

test("목업에서도 미리보기와 재발송이 실제 계약 모양으로 끝난다", async () => {
  const box = load(
    "api",
    "clinic-clock",
    "message-words",
    "schedule-rules",
    "history-rules",
    "messages-api",
  );
  box.MOCK = true;

  const preview = await box.messagesApi.preview(8803);
  const resent = await box.messagesApi.resend(7001);

  assert.strictEqual(preview.status, "SCHEDULED_TO_SEND");
  assert.ok(preview.approved_at);
  assert.strictEqual(resent.guide_message_id, 9901);
  assert.strictEqual(resent.status, "SCHEDULED");
  assert.strictEqual(JSON.stringify(resent).includes("token"), false);
});

test("링크 상태는 두 배지와 세 종료 사유로만 표시한다", () => {
  const screen = codeOnly(read("js/manage.js"));

  for (const word of ["사용 중", "사용 불가", "기간 만료", "새 링크로 교체", "직접 폐기"]) {
    assert.ok(screen.includes(word), `${word} 표시가 없다`);
  }
});

test("미리보기의 늦은 응답과 모달 기본 접근성을 지킨다", () => {
  const screen = codeOnly(read("js/manage.js"));

  assert.match(screen, /requestVersion !== previewVersion/);
  assert.match(screen, /event\.key === "Escape"/);
  assert.match(screen, /document\.querySelector\(modalReturnSelector\)/);
  assert.match(screen, /returnFocus\.focus\(\)/);
});

test("닫히거나 다른 용도로 바뀐 모달은 늦은 재발송 응답이 덮어쓰지 않는다", () => {
  const screen = codeOnly(read("js/manage.js"));

  assert.match(screen, /var resendVersion = 0/);
  assert.ok((screen.match(/requestVersion !== resendVersion/g) || []).length >= 3);
  assert.match(screen, /if \(!el\("modal"\)\.hidden\) closeHistory\(\)/);
  assert.match(screen, /if \(!saveButton \|\| !errorBox\) return/);
});

test("공용 환자 미리보기는 주의 아래 접힌 응급 문구도 찾는다", () => {
  const cards = codeOnly(read("js/patient-guide-cards.js"));

  assert.match(cards, /var tuckedUnder = \{ emergency: "caution" \}/);
  assert.match(cards, /tuckedUnder\[section\.key\] === key/);
  assert.doesNotMatch(cards, /GUIDE_TUCKED_UNDER/);
});

test("D1-6은 공용 안내문 미리보기를 열고 링크 상태만 읽기 전용으로 보여 준다", () => {
  const status = codeOnly(read("js/status-view.js"));
  const visit = codeOnly(read("js/visit-guide.js"));
  const links = codeOnly(read("js/patient-link-view.js"));

  assert.match(status, /data-status-preview/);
  assert.match(visit, /patientGuidePreviewHtml/);
  assert.match(visit, /data-status-preview/);
  assert.doesNotMatch(visit, /wirePatientLink/);
  assert.match(links, /사용 중/);
  assert.match(links, /사용 불가/);

  const box = load("api", "clinic-clock", "patient-link-view");
  const html = box.patientLinkBlockHtml(
    { expiresAt: "2026-09-20T18:00:00+09:00" },
    "SCHEDULED_TO_SEND",
    new Date("2026-09-14T10:00:00+09:00"),
  );
  assert.doesNotMatch(html, /data-patient-link|새 링크 만들기|>복사<|>열기<|링크 폐기/);

  const statusBox = load("api", "clinic-clock", "message-words", "patient-link-view", "status-view");
  const statusHtml = statusBox.statusScreenHtml({
    canPreview: true,
    entries: [],
    messages: [],
  });
  assert.match(statusHtml, /data-status-preview/);
});

test("D1-6 미리보기는 승인 완료된 안내문만 연다", () => {
  const visit = codeOnly(read("js/visit-guide.js"));
  const statusBox = load("api", "clinic-clock", "message-words", "patient-link-view", "status-view");

  assert.match(visit, /function canPreviewApprovedGuide/);
  assert.match(visit, /currentGuide\.status === "SCHEDULED_TO_SEND"/);
  assert.match(visit, /!!currentGuide\.approved_at/);
  assert.match(visit, /canPreview: canPreviewApprovedGuide\(guide\)/);
  assert.match(visit, /if \(!canPreviewApprovedGuide\(guide\)\)/);
  assert.match(visit, /미리볼 수 없는 안내문입니다/);
  assert.match(visit, /승인 완료된 안내문만 미리볼 수 있습니다/);

  const blockedHtml = statusBox.statusScreenHtml({
    canPreview: false,
    entries: [],
    messages: [],
  });
  assert.doesNotMatch(blockedHtml, /data-status-preview/);
});
