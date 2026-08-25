/* 의사 화면 목업이 **고른 진료의 사람**을 돌려주는가 — KEY-126.
 *
 * 목록에서 박수빈(`8798`)을 눌렀는데 오른쪽에 김서연이 떴다. 원인은
 * `mockGuideBase()` 의 폴백이었다.
 *
 *     var who = MOCK_PATIENTS[visitId] || MOCK_PATIENTS[8801];
 *
 * `8798` 이 표에 없어서 조용히 김서연으로 바뀌었다. 화면 코드는 맞았다 —
 * `doctor.js` 는 고른 진료를 그대로 넘긴다(`load(event.detail)`).
 *
 * **의무기록 화면이 다른 사람을 보여 주는 것**이라 「고르기가 고장난 것처럼
 * 보인다」보다 나쁘다. 고장은 눈에 띄지만 이건 멀쩡해 보인다.
 *
 * 그래서 두 가지를 못 박는다.
 *   ① 목록에서 의사 화면에 닿을 수 있는 진료는 **자기 사람**을 돌려준다
 *   ② 모르는 진료는 **없다고 답한다** — 서버와 같은 `404 GUIDE_NOT_FOUND`
 *
 * 값은 전부 합성이다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const PATIENTS_API = path.join(__dirname, "..", "js", "patients-api.js");

function box() {
  return load("api", "doctor-api");
}

/** 목록이 의사 화면에 올릴 수 있는 줄 — `patients-api.js` 의 목업에서 뽑는다. */
const DOCTOR_VISIBLE = [
  { visit_id: 8798, name: "박수빈", chart: "09871" }, // NEEDS_ATTENTION — 보완 탭
  { visit_id: 8801, name: "김서연", chart: "12345" }, // APPROVAL_REQUESTED
  { visit_id: 8802, name: "최다인", chart: "10982" }, // APPROVAL_REQUESTED
];

for (const row of DOCTOR_VISIBLE) {
  test(`진료 ${row.visit_id} 를 고르면 ${row.name} 의 안내문이 온다`, async () => {
    const guide = await box().doctorApi.guide(row.visit_id);

    assert.equal(guide.visit_id, row.visit_id);
    assert.equal(guide.patient.name, row.name, "고른 진료와 다른 사람이 왔다");
    assert.equal(guide.patient.hospital_patient_no, row.chart);
  });
}

test("모르는 진료는 없다고 답한다 — 남의 것으로 바꿔치지 않는다", async () => {
  await assert.rejects(
    () => box().doctorApi.guide(99999),
    (err) => {
      assert.equal(err.status, 404, `404 여야 한다 — 받은 것 ${err.status}`);
      assert.equal(err.code, "GUIDE_NOT_FOUND");
      return true;
    },
  );
});

test("승인·반려·섹션 수정도 모르는 진료에는 같은 404 를 준다", async () => {
  const api = box().doctorApi;
  for (const [label, call] of [
    ["승인", () => api.approve(99999)],
    ["반려", () => api.returnToStaff(99999, "사유")],
    ["섹션 수정", () => api.editSection(99999, "caution", { body: "본문" })],
  ]) {
    await assert.rejects(call, (err) => {
      assert.equal(err.status, 404, `${label} 이 404 가 아니다 — ${err.status}`);
      return true;
    });
  }
});

test("목록 목업과 이름·차트가 어긋나면 죽는다", () => {
  /* 두 파일이 같은 사람을 다르게 적으면 화면에서 또 어긋난다. 여기서
     `patients-api.js` 를 읽어 대조한다 — 한쪽만 고치고 넘어가는 것을 막는다. */
  const listSource = fs.readFileSync(PATIENTS_API, "utf8");

  for (const row of DOCTOR_VISIBLE) {
    /* `indexOf` 가 못 찾으면 `-1` 이고, `slice(-1)` 은 빈 문자열이 아니라
       **파일의 마지막 한 글자**다. 1 글자는 늘 truthy 라 `assert.ok(block)`
       가드는 **절대 걸리지 않았다** — 진료가 목록에서 빠져도 조용히 지나가고,
       뒤이은 이름 대조가 「이름이 다르다」로 엉뚱하게 죽는다
       (이희진 님 `#106` 리뷰). 찾았는지를 **자리로** 확인한다. */
    const at = listSource.indexOf(`visit_id: ${row.visit_id},`);
    assert.notEqual(at, -1, `목록에 진료 ${row.visit_id} 가 없다`);
    const chunk = listSource.slice(at, at + 500);
    assert.match(chunk, new RegExp(`name: "${row.name}"`), `목록의 ${row.visit_id} 이름이 다르다`);
    assert.match(
      chunk,
      new RegExp(`hospital_patient_no: "${row.chart}"`),
      `목록의 ${row.visit_id} 차트번호가 다르다`,
    );
  }
});
