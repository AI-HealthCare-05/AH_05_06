/* 화면이 계약을 지키는가 — KEY-117
 *
 * 픽셀이 아니라 **말로 적힌 규칙**을 잰다. 여기 있는 것은 전부
 * `docs/contracts/patient-visit-api-v1.md` 나 와이어프레임이 이미 정해 둔 것이고,
 * 지금까지는 사람이 브라우저를 열어야만 확인되던 것들이다.
 *
 * 이번 스프린트에 프런트에서 나온 결함이 다섯인데 전부 사람이 눌러서 찾았다.
 * 그중 「오늘 목록이 없는 엔드포인트를 부른다」와 「목록·상세 모델이 샌다」는
 * 여기서 잡힌다.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const { load } = require("./browser-shim");

/* `vm` 안에서 만든 배열·객체는 **realm 이 달라** `deepEqual` 이 구조가 같아도
   실패한다("same structure but are not reference-equal"). 값만 보고 싶으므로
   내 realm 으로 한 번 옮긴다.

   JSON 왕복이 아니라 `structuredClone` 을 쓴다. JSON 은 **`undefined` 인 칸을
   통째로 지우고** `Date` 를 문자열로 바꾼다 — 아래 「칸이 안 샌다」 검사들이
   새어 나온 칸의 값이 `undefined` 이면 그 키가 사라져 **조용히 통과**한다.
   이희진 님이 `#64` 리뷰에서 짚어 주신 자리다. */
const plain = (v) => structuredClone(v);

/* 실리는 순서가 브라우저의 <script> 순서와 같다 — shell.js 가 session·patients-api 를 쓴다. */
const api = load("api", "session", "patients-api", "shell");

/* ── 오늘 목록 (계약 §6 S1-1) ───────────────────────────── */

test("보완은 날짜를 무시한다 — 해결될 때까지 딸려 온다", async () => {
  // 박수빈은 08-11 건인데 NEEDS_ATTENTION 이라 오늘 목록에 선다.
  const today = await api.patientsApi.onDay("2026-08-20", []);
  const names = today.items.map((v) => v.name);
  assert.ok(names.includes("박수빈"), `오늘 목록에 보완 건이 없다: ${names}`);

  // 아무도 진료하지 않은 날에도 남아야 한다. 이 줄이 규칙의 증거다.
  const empty = await api.patientsApi.onDay("2026-03-01", []);
  assert.deepEqual(plain(empty.items.map((v) => v.name)), ["박수빈"], "아무도 진료 안 한 날인데 보완 건이 사라졌다");
});

test("오늘 목록 응답이 계약의 봉투를 갖춘다", async () => {
  const page = await api.patientsApi.onDay("2026-08-20", []);
  assert.deepEqual(plain(Object.keys(page).sort()), [
    "counts",
    "date",
    "items",
    "page",
    "selected_categories",
    "timezone",
  ]);
  assert.equal(page.timezone, "Asia/Seoul", "날짜 규칙의 기준은 병원 표시 시간대다");
  assert.deepEqual(plain(Object.keys(page.page).sort()), ["has_next", "next_cursor"]);
});

test("탭을 고르면 그 카테고리만 남고 counts 는 그대로다", async () => {
  const all = await api.patientsApi.onDay("2026-08-20", []);
  const one = await api.patientsApi.onDay("2026-08-20", ["NEEDS_ATTENTION"]);

  assert.ok(one.items.every((v) => v.work_category === "NEEDS_ATTENTION"));
  // counts 는 「지금 보이는 것」이 아니라 「그 날 전체」다 — 탭 배지가 걸러도 안 줄어야 한다.
  assert.deepEqual(plain(one.counts), plain(all.counts), "탭을 걸렀다고 배지 숫자가 줄면 안 된다");
});

/* ── 목록과 상세는 다른 계약이다 ───────────────────────── */

test("오늘 목록에 진료 상세 칸이 새지 않는다", async () => {
  const page = await api.patientsApi.onDay("2026-08-20", []);
  const detailOnly = ["department", "status", "planned_stop", "visit_summary", "doctor_note"];
  for (const row of page.items) {
    const leaked = detailOnly.filter((k) => k in row);
    assert.deepEqual(plain(leaked), [], `목록 줄에 상세 칸이 있다: ${leaked}`);
  }
});

test("진료 상세에 목록 칸이 새지 않는다", async () => {
  const page = await api.patientsApi.onDay("2026-08-20", []);
  const visit = await api.patientsApi.getVisit(page.items[0].visit_id);

  assert.deepEqual(
    plain(Object.keys(visit).sort()),
    [
      "department",
      "doctor_id",
      "doctor_note",
      "patient_id",
      "planned_stop",
      "status",
      "visit_id",
      "visit_summary",
      "visited_at",
    ].sort(),
  );

  const listOnly = ["name", "work_category", "detail_status", "diagnosis_name", "age"];
  const leaked = listOnly.filter((k) => k in visit);
  assert.deepEqual(plain(leaked), [], `상세에 목록 칸이 있다: ${leaked}`);
});

/* ── 상태 두 층 (계약 §6) ───────────────────────────────── */

test("화면은 상태를 파생하지 않고 한국어로 옮기기만 한다", () => {
  assert.equal(api.statusLabel("NO_DOCUMENT"), "진료기록 없음");
  assert.equal(api.statusLabel("INVALID_PHONE"), "번호 오류");
  assert.equal(api.statusLabel("SCHEDULED_TO_SEND"), "발송 예정");

  // 모르는 값은 지어내지 않고 받은 그대로 보인다 — 서버가 값을 늘려도 화면이 안 죽는다.
  assert.equal(api.statusLabel("SOMETHING_NEW"), "SOMETHING_NEW");
  assert.equal(api.statusLabel(null), "");
});

test("배지 색은 한글 문구가 아니라 업무 카테고리로 정한다", () => {
  // 문구가 바뀔 때마다 색이 조용히 빠지던 자리다.
  assert.match(api.stateClass("NEEDS_ATTENTION"), /--warn/);
  assert.match(api.stateClass("COMPLETED"), /--done/);
  assert.doesNotMatch(api.stateClass("IN_PROGRESS"), /--warn|--done/);
});

test("계약이 정한 카테고리 다섯이 전부 있다", () => {
  assert.deepEqual(plain(api.WORK_CATEGORIES.map((c) => c.key)), [
    "IN_PROGRESS",
    "NEEDS_ATTENTION",
    "APPROVAL_REQUESTED",
    "SEND_PENDING",
    "COMPLETED",
  ]);
});

/* ── 검색 (계약 §4·§6) ──────────────────────────────────── */

test("이름 검색은 앞부분 일치다 — 서버가 name__startswith 로 돈다", async () => {
  const hit = await api.patientsApi.search("김");
  assert.ok(hit.items.length > 0, "한 글자로도 찾혀야 한다");
  assert.ok(hit.items.every((p) => p.name.startsWith("김")));

  // 「포함」으로 흉내내면 목업에서는 찾히고 실서버에서 0건이 된다.
  // 그 차이는 서버가 붙는 날에야 드러난다.
  const middle = await api.patientsApi.search("서연");
  assert.equal(middle.items.length, 0, "가운데 글자로 찾히면 실서버와 어긋난다");
});

test("차트번호로도 찾힌다", async () => {
  const hit = await api.patientsApi.search("12345");
  assert.deepEqual(plain(hit.items.map((p) => p.hospital_patient_no)), ["12345"]);
});

/* ── 값 다루기 ──────────────────────────────────────────── */

test("나이는 저장하지 않고 생년월일에서 계산한다", () => {
  // `toISOString()`은 UTC 날짜라 KST 자정~08:59엔 현지 날짜보다 하루 전을
  // 돌려준다. 로컬 getter로 만드는 `api.toIsoDate()`를 써서 이 문제를 피한다.
  const born = new Date();
  born.setFullYear(born.getFullYear() - 30);
  const iso = api.toIsoDate(born);
  assert.equal(api.ageOf(iso), 30);

  // 생일이 아직 안 지났으면 한 살 적다
  const soon = new Date();
  soon.setFullYear(soon.getFullYear() - 30);
  soon.setDate(soon.getDate() + 1);
  assert.equal(api.ageOf(api.toIsoDate(soon)), 29);
});

test("휴대폰은 뒤 네 자리만 남긴다", () => {
  assert.equal(api.maskPhone("01044524085"), "010-****-4085");
});

test("오늘 날짜는 현지 기준이다 — UTC 로 재면 자정 근처에서 날이 갈린다", () => {
  /* **이 검사는 두 조건이 맞아야 뜻이 있다.**

     ① 현지 시간대가 UTC 와 달라야 한다. 같으면 현지 getter 와 UTC getter 가
        같은 값을 내서 **무엇으로 고쳐도 통과한다.**
     ② 고른 시각이 실제로 날을 가르는 구간이어야 한다. 앞서 쓰던 「현지 23:30」
        은 KST 로도 UTC 로도 같은 날이라 `TZ=Asia/Seoul` 에서조차 안 잡혔다.
        KST(+9)에서 날이 갈리는 것은 **00:00~08:59** 다.

     ①은 검사가 스스로 확인한다. 아니면 여기서 죽는다 — 조용히 무력해지느니
     시끄럽게 죽는 편이 낫다. CI 는 `checks.yml` 에서 `TZ` 를 고정한다. */
  const local = new Date(2026, 7, 21, 0, 30); // 현지 8월 21일 새벽 0시 반
  assert.notEqual(
    local.getTimezoneOffset(),
    0,
    "TZ 가 UTC 라 이 검사는 아무것도 확인하지 못한다 — TZ=Asia/Seoul 로 돌려라",
  );

  /* 현지로 재면 21일, UTC 로 재면 20일이다. 둘이 같게 나오면 UTC 로 재고 있다. */
  assert.notEqual(
    api.toIsoDate(local),
    local.toISOString().slice(0, 10),
    "현지 날짜와 UTC 날짜가 갈리는 시각인데 같게 나왔다 — UTC 로 재고 있다",
  );
  assert.equal(api.toIsoDate(local), "2026-08-21");
});

/* ── 진료과·담당의는 id 로 보낸다 (계약 §4) ─────────────── */

test("진료과 이름은 서버가 붙인다 — 화면은 id 만 보낸다", () => {
  assert.equal(api.departmentOf(7), "산부인과");
  assert.equal(api.departmentOf(999), null, "없는 진료과면 이름을 지어내지 않는다");
});

test("수정 가능 필드가 계약 §6 그대로다", () => {
  assert.deepEqual(plain(api.PATIENT_EDITABLE), ["name", "birth_date", "gender", "phone", "sms_consent"]);
  assert.deepEqual(plain(api.VISIT_EDITABLE), [
    "doctor_id",
    "department_id",
    "visited_at",
    "visit_summary",
    "doctor_note",
    "status",
    "planned_stop",
  ]);
});

test("계약 밖 필드를 보내면 서버처럼 목업도 거부한다", async () => {
  const page = await api.patientsApi.onDay("2026-08-20", []);
  const id = page.items[0].visit_id;

  await assert.rejects(
    () => api.patientsApi.updateVisit(id, { doctor_name: "박연 원장" }),
    (err) => err.code === "INVALID_REQUEST",
    "옛 필드 이름이 통과하면 서버가 붙는 날 처음 안다",
  );
  await assert.rejects(
    () => api.patientsApi.updateVisit(id, {}),
    (err) => err.code === "EMPTY_UPDATE_FIELDS",
  );
});

test("진료 생성 목업도 존재하지 않는 담당의를 거부한다", async () => {
  await assert.rejects(
    () =>
      api.patientsApi.createVisit(1001, {
        doctor_id: 999999,
        visited_at: "2026-08-27T10:30:00+09:00",
      }),
    (err) => err.code === "INVALID_REQUEST" && err.status === 400,
    "PATCH와 달리 POST 목업만 잘못된 담당의를 조용히 null로 저장하면 안 된다",
  );
});

test("오류 코드는 대문자다 (계약 §7)", async () => {
  await assert.rejects(
    () => api.patientsApi.getVisit(999999),
    (err) => err.code === "VISIT_NOT_FOUND" && err.status === 404,
  );
  await assert.rejects(
    () => api.patientsApi.get(999999),
    (err) => err.code === "PATIENT_NOT_FOUND" && err.status === 404,
  );
});
