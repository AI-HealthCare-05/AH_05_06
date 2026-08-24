/* 의사 승인 화면이 **서버가 실제로 주는 모양**을 그대로 받는가 — KEY-160.
 *
 * `#48`(KEY-86) 화면은 `sections[].label/blocks` 를 기대하며 만들어졌는데,
 * `#50`(KEY-111) 이 확정한 서버 응답은 `{key, body, edited, locked, warn}`
 * 평문이다. `#76` 에서 화면을 그 모양에 맞췄고, 이 검사는 **그 정합이 다시
 * 어긋나지 않게** 붙잡는다.
 *
 * 아래 fixture 는 `app/dtos/guides.py` 의 `GuideResponse` · `SectionResponse`
 * 를 그대로 옮긴 것이다. 값은 전부 합성이다 — 실제 환자정보·전화번호가 아니다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

/** 서버 `GuideResponse` 를 그대로 옮긴 응답. */
const REAL_RESPONSE = {
  visit_id: 8801,
  patient: {
    name: "박수빈",
    birth_date: "1992-09-18",
    age: 33,
    gender: "FEMALE",
    hospital_patient_no: "09871",
  },
  summary: "자궁내막증 · 비잔 계속",
  status: "APPROVAL_PENDING",
  version: 3,
  sections: [
    { key: "medication", body: "하루 한 알, 같은 시간에 드세요.", edited: false, locked: false, warn: null },
    { key: "caution", body: "출혈이 계속되면 알려 주세요.", edited: true, locked: true, warn: "AMH 값이 없습니다" },
    { key: "life", body: "수면 시간을 기록해 보세요.", edited: false, locked: false, warn: null },
    { key: "messages", body: "일주일 뒤 확인이 예약됩니다.", edited: false, locked: false, warn: null },
  ],
  approved_at: null,
  scheduled_at: "2026-08-21T18:00:00+09:00",
  returned_reason: null,
};

test("서버 응답에 화면이 기대하던 옛 칸이 하나도 없다", () => {
  const gone = ["label", "blocks", "editable", "to", "send_at"];
  const text = JSON.stringify(REAL_RESPONSE);
  gone.forEach((key) => {
    assert.ok(!text.includes(`"${key}"`), `서버가 안 주는 칸을 fixture 가 들고 있다: ${key}`);
  });
});

test("섹션은 다섯 칸뿐이다 — 화면이 그 밖의 것을 기대하면 안 된다", () => {
  REAL_RESPONSE.sections.forEach((s) => {
    assert.deepStrictEqual(
      Object.keys(s).sort(),
      ["body", "edited", "key", "locked", "warn"],
      `SectionResponse 모양이 다르다: ${s.key}`
    );
  });
});

test("섹션 수정 경로가 서버 계약과 같다 — /guide/sections/{key}", async () => {
  const api = load("api", "doctor-api");
  const calls = [];
  const origin = api.mockDoctorRequest;
  api.mockDoctorRequest = function (path, options) {
    calls.push({ path, method: (options || {}).method });
    return origin.apply(this, arguments);
  };

  await api.doctorApi.editSection(8801, "life", { body: "고친 문장" });

  assert.strictEqual(calls.length, 1);
  assert.match(calls[0].path, /\/visits\/8801\/guide\/sections\/life$/, `경로가 계약과 다르다: ${calls[0].path}`);
  assert.strictEqual(calls[0].method, "PATCH");
});

test("승인 응답은 scheduled_at 을 쓴다 — send_at 이 아니다", async () => {
  const api = load("api", "doctor-api");
  const result = await api.doctorApi.approve(8801);
  assert.ok("scheduled_at" in result, "승인 응답에 scheduled_at 이 없다");
  assert.ok(!("send_at" in result), "승인 응답이 옛 이름 send_at 을 쓴다");
});

test("목업 안내문이 서버와 같은 다섯 칸을 준다", async () => {
  const api = load("api", "doctor-api");
  const guide = await api.doctorApi.guide(8801);

  assert.ok("patient" in guide, "목업에 patient 가 없다 — 화면 머리가 빈다");
  assert.ok("scheduled_at" in guide);
  guide.sections.forEach((s) => {
    assert.deepStrictEqual(
      Object.keys(s).sort(),
      ["body", "edited", "key", "locked", "warn"],
      `목업 섹션이 서버와 다르다: ${s.key}`
    );
  });
});

test("목업이 없는 문자 발송을 약속하지 않는다", async () => {
  const api = load("api", "doctor-api");
  const guide = await api.doctorApi.guide(8801);
  const messages = guide.sections.find((s) => s.key === "messages");
  assert.ok(messages, "문자 설정 섹션이 없다");
  assert.ok(
    !/자동 발송됩니다/.test(messages.body),
    "보내는 것이 아직 없는데 「자동 발송됩니다」라고 말한다"
  );
});
