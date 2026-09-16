/* 절의 **차례** — KEY-317, 그리고 그 단추를 걷어낸 자리.
 *
 * 차례를 바꾸는 단추([◀][▶])는 탭 줄 오른쪽에 있었다. 그 자리에 그 모양이면
 * **「이전·다음 탭」으로 읽힌다** — 넘기려고 눌렀는데 복약지도가 주의사항을
 * 뛰어넘어 생활지도 자리로 갔다. 안전 절(주의사항)에서는 단추가 통째로 사라져
 * 줄 폭까지 흔들렸다. 그래서 **누르는 자리를 화면에서 뺐다.**
 *
 * 저장하는 자리(`PUT /guide/sections/order`)는 서버 계약이라 그대로 둔다.
 * 여기서 재는 것은 두 가지다 — ① 탭 줄에 옮기는 단추가 다시 안 선다
 * ② 목업이 서버와 같은 코드로 차례를 검증한다(계약이 살아 있다).
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { load } = require("./browser-shim");
const { read, bareCode } = require("./source");

/** 계약 차례 그대로의 다섯 절. 안전 둘은 `movable: false` 다. */
function sections() {
  return [
    { key: "medication", movable: true },
    { key: "caution", movable: false },
    { key: "emergency", movable: false },
    { key: "life", movable: true },
    { key: "messages", movable: true },
  ];
}

function box() {
  /* 화면이 싣는 차례 그대로 함께 싣는다 — `esc` 는 `api.js`, 미리보기 칸은
     `patient-guide-cards.js` 에 있다. */
  return load("api", "session", "patient-guide-cards", "guide-view");
}

test("탭 줄에 차례를 옮기는 단추가 서지 않는다", () => {
  /* 탭 옆의 [◀][▶] 는 「이전·다음 탭」으로 읽혀 안 된다. 다시 달 일이 생기면
     탭 줄이 아닌 다른 자리여야 한다. */
  const view = box();

  const html = view.guideScreenHtml(sections(), "medication", "guide", true, null, "", null);
  /* 탭 줄만 떼어 본다 — `guideSegmentsHtml` 이 탭 줄을 그리는 그 함수라,
     전체 화면 문자열에서 자리를 잘라 내는 것보다 무엇을 재는지가 분명하고,
     탭이 아닌 다른 자리(가령 문자 설정 미리보기)의 글자에 흔들리지 않는다. */
  const tabRow = view.guideSegmentsHtml(sections(), "medication");

  assert.ok(!html.includes("data-move"), "옮기는 단추가 다시 섰다");
  assert.ok(!html.includes("gs__move"), "옮기는 단추 자리가 다시 섰다");
  assert.ok(!/[◀▶]/.test(tabRow), "탭 줄에 화살표가 섰다");
});

test("옮기는 단추를 그리던 코드가 통째로 없다", () => {
  /* 안 불리는 채 남아 있으면 다음 사람이 「왜 안 뜨지」로 되살린다. */
  const code = bareCode(read("js/guide-view.js"));

  for (const name of ["guideMoveHtml", "guideOrderMoved", "guideMovableKeys", "guideMoveSection"]) {
    assert.ok(!code.includes(name), `죽은 코드가 남았다: ${name}`);
  }
  const css = bareCode(read("css/blocks.css"));
  assert.ok(!css.includes("gs__movebtn"), "죽은 CSS(단추)가 남았다");
  /* `gs__move` 는 `gs__movebtn` 의 앞 글자라, 뒤엣것만 재면 감싸개
     `.gs__move` 홀로 되살아나도 못 잡는다 — 뒤에 `btn` 이 안 붙는 자리를 따로 잰다. */
  assert.ok(!/\.gs__move(?!btn)/.test(css), "죽은 CSS(감싸개)가 남았다");
});

test("목업도 차례를 저장하고 다시 준다", async () => {
  /* 목업이 이 자리를 모르면 `?mock=1` 로 화면을 검수할 수 없다 — 눌러도
     「불러오지 못했습니다」만 나온다. */
  const api = load("api", "doctor-api");
  const wanted = ["life", "caution", "emergency", "medication", "messages"];

  const saved = await api.doctorApi.reorderSections(8801, { order: wanted });
  const again = await api.doctorApi.guide(8801);

  /* 글자로 견준다 — 목업은 제 realm 의 `Array` 를 돌려줘서 `deepEqual` 이
     「모양은 같은데 같은 것이 아니다」로 떨어진다. */
  assert.equal(saved.sections.map((s) => s.key).join(","), wanted.join(","));
  assert.equal(
    again.sections.map((s) => s.key).join(","),
    wanted.join(","),
    "다시 불러오니 차례가 돌아갔다"
  );
});

test("목업도 안전 절을 옮기는 요청을 서버와 같은 코드로 막는다", async () => {
  /* 목업이 헐거우면 `?mock=1` 에서는 되는데 실서버에서만 422 가 난다. */
  const api = load("api", "doctor-api");

  await assert.rejects(
    api.doctorApi.reorderSections(8801, {
      order: ["medication", "life", "caution", "emergency", "messages"],
    }),
    (error) => error.status === 422 && error.code === "SECTION_ORDER_INVALID"
  );
});

test("목업도 빠뜨린 절을 막는다", async () => {
  const api = load("api", "doctor-api");

  await assert.rejects(
    api.doctorApi.reorderSections(8801, { order: ["medication", "caution", "emergency", "life"] }),
    (error) => error.status === 422
  );
});
