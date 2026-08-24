/* 🚨 응급 문장을 다섯째 갈래로 뗀 것 — KEY-161.
 *
 * 잠금은 **섹션 단위**다(`SectionResponse.locked: bool`). 그래서 응급 문장을
 * 지키려고 `caution` 을 통째로 잠그면, 원장님이 환자에 맞춰 고쳐야 할 일반
 * 주의 문구까지 함께 잠긴다. 와이어프레임 D1-2 의 규칙은 「🚨 응급 문장만
 * 수정 불가」다.
 *
 * 여기 값은 전부 합성이다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const VISIT = 8801;
const DOCTOR_JS = path.join(__dirname, "..", "js", "doctor.js");

function box() {
  return load("api", "doctor-api");
}

test("목업이 다섯 갈래를 서버와 같은 차례로 준다", async () => {
  const guide = await box().doctorApi.guide(VISIT);

  /* 차례까지 계약이다. 서버는 `guide_section_id` 순서로 실어 주고, 그 순서가
     곧 환자 화면의 차례(P2·P3·P4)다. 응급 문장은 주의 문구 **바로 뒤**다. */
  /* `Array.from` 으로 옮겨 담는다. `browser-shim` 은 `vm` 안에서 화면 코드를
     돌리므로 거기서 만든 배열은 프로토타입이 달라 `deepStrictEqual` 이
     내용과 무관하게 실패한다. */
  assert.deepStrictEqual(Array.from(guide.sections, (s) => s.key), [
    "medication",
    "caution",
    "emergency",
    "life",
    "messages",
  ]);
});

test("일반 주의 문구는 잠기지 않는다 — KEY-161 이 풀려던 자리다", async () => {
  const guide = await box().doctorApi.guide(VISIT);
  const caution = guide.sections.find((s) => s.key === "caution");

  assert.strictEqual(caution.locked, false);
  assert.ok(caution.body.trim(), "일반 주의 문구가 비어 있다 — 쪼개면서 잃었다");
});

test("응급 문장은 잠긴다", async () => {
  const guide = await box().doctorApi.guide(VISIT);
  const emergency = guide.sections.find((s) => s.key === "emergency");

  assert.ok(emergency, "응급 갈래가 없다");
  assert.strictEqual(emergency.locked, true);
  assert.ok(emergency.body.trim(), "응급 문장이 비어 있다");
});

test("응급 문장 수정은 409 SECTION_LOCKED 다", async () => {
  const api = box();
  await assert.rejects(
    () => api.doctorApi.editSection(VISIT, "emergency", { body: "사람이 고쳐 본다" }),
    (error) => error.code === "SECTION_LOCKED" && error.status === 409,
    "응급 문장 수정이 통과했다",
  );
});

test("일반 주의 문구 수정은 그대로 된다 — 잠금이 옆칸으로 번지지 않았다", async () => {
  const api = box();
  const updated = await api.doctorApi.editSection(VISIT, "caution", { body: "환자분께 맞춰 고친 문구" });

  assert.strictEqual(updated.key, "caution");
  assert.strictEqual(updated.body, "환자분께 맞춰 고친 문구");
  assert.strictEqual(updated.locked, false);
});

/* ── 화면 — 원문으로 본다 ────────────────────────────────────────────────
 *
 * `doctor.js` 는 IIFE 라 검사기가 불러 실행할 수 없다(그 구조 변경이 KEY-158
 * 이다). 그래서 **원문에서 규칙이 살아 있는지**를 본다 — 한금준 님이 `#94`
 * 에서 `select_for_update()` 를 원문으로 확인한 것과 같은 방식이다.
 *
 * 잡으려는 회귀는 하나다: 누가 `TUCKED_UNDER` 를 지우면 **다섯째 탭이 생기고**,
 * 원장님이 그 탭을 안 열고 승인할 수 있게 된다.
 */
test("화면이 응급 문장에 탭을 만들지 않는다", () => {
  const source = fs.readFileSync(DOCTOR_JS, "utf8");

  assert.match(source, /TUCKED_UNDER\s*=\s*\{\s*emergency:\s*"caution"/, "탭에서 빼는 규칙이 없다");
  assert.match(source, /function tabSections\(\)/, "탭 목록을 거르는 자리가 없다");
  assert.doesNotMatch(
    source,
    /var tabs = guide\.sections\s*\n?\s*\.map\(/,
    "탭을 거르지 않고 섹션 전부로 만들고 있다 — 🚨 탭이 생긴다",
  );
});

test("원문 검사가 실제로 doctor.js 를 읽었다", () => {
  /* 경로가 틀리면 위 검사가 빈 문자열을 보고 조용히 통과한다. */
  const source = fs.readFileSync(DOCTOR_JS, "utf8");
  assert.ok(source.length > 5000, `doctor.js 를 못 읽었다: ${source.length} 자`);
  assert.match(source, /SECTION_LABEL/, "읽은 것이 doctor.js 가 아니다");
});
