const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const root = path.join(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");
const box = () => load("api", "session", "patient-guide-cards", "guide-view");
const sections = [{ key: "medication", body: "승인된 복약 문구" }];
const preview = {
  visit: "2026.09.15", clinic: "합성 예시의원",
  stat: { drugName: "합성약", drugSub: "1일 1회", prescribed: 28, dayOn: 7, remaining: 21, pct: 25, out: "ⓘ 10월 6일경 약이 소진돼요", why: "승인된 복약 문구" },
};

test("현황의 클래스와 문구는 실제 환자 renderStatus에 존재한다", () => {
  const { patientStatusHtml } = box();
  const source = read("patient_wireframe/js/guide.js");
  const statusSource = source.slice(source.indexOf("function renderStatus("), source.indexOf("function renderGuide("));
  const html = patientStatusHtml(preview, sections[0].body);
  for (const cls of new Set([...html.matchAll(/class="([^"]+)"/g)].flatMap((m) => m[1].split(" ")))) {
    assert.ok(statusSource.includes(cls) || cls === "btn", `환자 현황에 없는 클래스: ${cls}`);
  }
  for (const text of ["복약 진행률", "% 복용했어요", "재진 예약을 잡거나 병원에 문의해 주세요.", "복약지도 보기"]) {
    assert.ok(statusSource.includes(text));
    assert.ok(html.includes(text));
  }
  assert.match(html, /2026.09.15 처방 · 합성 예시의원/);
  assert.match(html, /28일분 · 7일째 · 21일 남음/);
  assert.match(html, /aria-valuenow="25"/);
  assert.match(html, /style="width:25%"/);
  assert.equal(html.split("승인된 복약 문구").length - 1, 1, "약 카드와 핑크 카드에 중복하지 않는다");
});

test("null 현황/0일/시작일 미확정의 빈 상태도 환자와 같다", () => {
  const { patientStatusHtml } = box();
  const source = read("patient_wireframe/js/guide.js");
  const cases = [
    [null, "", "표시할 승인 복약 안내가 아직 없어요."],
    [{ stat: { prescribed: 0, pct: null } }, "", "처방 일수가 없어 복약 기간을 표시하지 않아요."],
    [{ stat: { prescribed: 28, pct: null } }, "", "복약 시작일이 없어 진행률과 남은 일수를 표시하지 않아요."],
  ];
  for (const [data, medication, message] of cases) {
    const html = patientStatusHtml(data, medication);
    assert.ok(source.includes(message));
    assert.ok(html.includes(message));
    assert.doesNotMatch(html, /role="progressbar"/);
  }
  const fallback = patientStatusHtml({ stat: null }, "승인 문구");
  assert.match(fallback, /복약 현황/);
  assert.match(fallback, /승인 문구/);
});

test("0%와 100%도 그대로 표시하고, 텍스트/스타일 삽입을 차단한다", () => {
  const { patientStatusHtml } = box();
  for (const pct of [0, 100]) assert.ok(patientStatusHtml({ stat: { pct } }, "").includes(`aria-valuenow="${pct}"`));
  const html = patientStatusHtml({ clinic: '<img src=x onerror="alert(1)">', stat: { drugName: "<script>", pct: '1\" onmouseover=\"alert(1)' } }, "");
  assert.doesNotMatch(html, /<img|<script|role="progressbar"/);
  assert.match(html, /&lt;img/);
});

test("4개 탭은 현황부터 배치하되 기존 복약지도 선택과 안전한 iframe을 유지한다", () => {
  const { patientGuidePreviewHtml, patientTabBarHtml, guidePreviewHtml } = box();
  const tabs = patientTabBarHtml("medication");
  assert.deepEqual([...tabs.matchAll(/data-preview-tab="([^"]+)"/g)].map((m) => m[1]), ["status", "medication", "caution", "life"]);
  assert.equal((tabs.match(/aria-selected="true"/g) || []).length, 1);
  assert.match(tabs, /aria-selected="true" data-preview-tab="medication"/);
  assert.doesNotMatch(tabs, /disabled/);
  const html = patientGuidePreviewHtml(sections, "status", "", preview);
  assert.match(html, /sandbox="allow-same-origin"/);
  assert.doesNotMatch(html, /allow-scripts|<script|#t=/);
  assert.equal(guidePreviewHtml(sections, "status", "", preview), html, "guide-view도 공용 렌더러를 쓴다");
});

test("관리/현황 모달은 같은 공용 렌더러와 하단 닫기 하나만 쓴다", () => {
  const manage = read("js/manage.js");
  const visit = read("js/visit-guide.js");
  for (const source of [manage, visit]) {
    const start = source.indexOf('<div class="modal__top"><h2 class="modal__title" id="modal-title">안내문 미리보기');
    assert.ok(start >= 0);
    const end = source.indexOf("</div>'", source.indexOf('class="modal__acts"', start)) + 7;
    const modal = source.slice(start, end);
    assert.equal((modal.match(/data-close/g) || []).length, 1);
    assert.match(modal, /patientGuidePreviewHtml/);
    assert.match(modal, /modal__acts.*button-ghost.*data-close>닫기/);
    assert.ok(modal.indexOf("patientGuidePreviewHtml") < modal.indexOf("data-close"));
  }
  assert.match(visit, /event.key === "Escape"/);
  assert.match(visit, /previewReturnFocus\.focus\(\)/);
  assert.match(read("js/patient-guide-cards.js"), /new KeyboardEvent\("keydown", \{ key: "Escape", bubbles: true \}\)/);
});
