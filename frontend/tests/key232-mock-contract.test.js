/* KEY-232: 핵심 mock 응답은 서버 OpenAPI(Pydantic DTO)보다 관대할 수 없다. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { load } = require("./browser-shim");

const ROOT = path.join(__dirname, "..", "..");
const OPENAPI = JSON.parse(fs.readFileSync(path.join(ROOT, "docs/api/openapi.json"), "utf8"));
const plain = (value) => structuredClone(value);

function dereference(schema) {
  if (!schema || !schema.$ref) return schema;
  return schema.$ref.split("/").slice(1).reduce((value, key) => value[key], OPENAPI);
}

function validate(value, rawSchema, at = "response") {
  const schema = dereference(rawSchema);
  if (schema.anyOf) {
    const failures = [];
    for (const candidate of schema.anyOf) {
      try {
        validate(value, candidate, at);
        return;
      } catch (error) {
        failures.push(error.message);
      }
    }
    assert.fail(`${at}: anyOf 불일치 (${failures.join(" | ")})`);
  }
  if (Object.hasOwn(schema, "const")) assert.deepEqual(value, schema.const, `${at}: const 불일치`);
  if (schema.enum) assert.ok(schema.enum.includes(value), `${at}: enum 밖의 값 ${value}`);

  if (schema.type === "null") return assert.equal(value, null, `${at}: null이어야 함`);
  if (schema.type === "string") return assert.equal(typeof value, "string", `${at}: string이어야 함`);
  if (schema.type === "boolean") return assert.equal(typeof value, "boolean", `${at}: boolean이어야 함`);
  if (schema.type === "number") return assert.equal(typeof value, "number", `${at}: number이어야 함`);
  if (schema.type === "integer") return assert.ok(Number.isInteger(value), `${at}: integer이어야 함`);
  if (schema.type === "array") {
    assert.ok(Array.isArray(value), `${at}: array여야 함`);
    value.forEach((item, index) => validate(item, schema.items, `${at}[${index}]`));
    return;
  }
  if (schema.type === "object" || schema.properties) {
    assert.ok(value && typeof value === "object" && !Array.isArray(value), `${at}: object여야 함`);
    for (const key of schema.required || []) assert.ok(Object.hasOwn(value, key), `${at}.${key}: 필수 필드 누락`);
    if (schema.additionalProperties === false) {
      const extras = Object.keys(value).filter((key) => !Object.hasOwn(schema.properties || {}, key));
      assert.deepEqual(extras, [], `${at}: 서버 DTO에 없는 필드 ${extras.join(", ")}`);
    }
    for (const [key, item] of Object.entries(value)) {
      if (schema.properties && schema.properties[key]) validate(item, schema.properties[key], `${at}.${key}`);
    }
  }
}

function schema(name) {
  const found = OPENAPI.components.schemas[name];
  assert.ok(found, `OpenAPI schema 없음: ${name}`);
  return found;
}

function validateExactProperties(value, rawSchema, at) {
  const expected = Object.keys(dereference(rawSchema).properties || {}).sort();
  assert.deepEqual(Object.keys(value).sort(), expected, `${at}: 서버 응답 필드 목록과 정확히 일치해야 함`);
}

test("배포/Pilot 주소에서는 ?mock=1을 무시하고 로컬에서만 고정 배너를 사용한다", () => {
  const local = load("api", { search: "?mock=1", hostname: "localhost" });
  const deployed = load("api", { search: "?mock=1", hostname: "pilot.example.com" });
  assert.equal(local.MOCK, true);
  assert.equal(deployed.MOCK, false);
  assert.equal(local.localMockRequested({ search: "", hostname: "localhost", protocol: "http:" }), true);
  assert.equal(local.localMockRequested({ search: "?mock=1", hostname: "pilot.example.com", protocol: "https:" }), false);

  let inserted = null;
  const mockState = new Map();
  const source = fs.readFileSync(path.join(ROOT, "frontend/js/api.js"), "utf8");
  const context = vm.createContext({
    URLSearchParams,
    location: { search: "?mock=1", hostname: "localhost", protocol: "http:" },
    sessionStorage: {
      getItem(key) { return mockState.has(key) ? mockState.get(key) : null; },
      setItem(key, value) { mockState.set(key, String(value)); },
      removeItem(key) { mockState.delete(key); },
    },
    document: {
      getElementById() { return null; },
      createElement() { return { style: {}, setAttribute(name, value) { this[name] = value; } }; },
      body: { dataset: {}, style: {}, prepend(node) { inserted = node; } },
    },
  });
  vm.runInContext(source, context);
  assert.equal(inserted.id, "mock-mode-banner");
  assert.equal(inserted.role, "status");
  assert.match(inserted.textContent, /실제 서버 데이터가 아닙니다/);

  const guideSource = fs.readFileSync(path.join(ROOT, "frontend/patient_wireframe/js/guide.js"), "utf8");
  const guideCss = fs.readFileSync(path.join(ROOT, "frontend/patient_wireframe/css/guide.css"), "utf8");
  assert.match(guideSource, /document\.body\.style\.paddingTop\s*=/);
  assert.match(guideSource, /getBoundingClientRect\(\)\.height/);
  assert.match(guideSource, /--guide-mock-offset/);
  assert.match(guideCss, /top:\s*var\(--guide-mock-offset,\s*0px\)/);
  assert.match(guideCss, /\.guide-mock-badge\s*\{[\s\S]*pointer-events:\s*none/);
});

/* 「사용하지 않는 구 안내 API」 검사는 그 파일과 함께 없앴다 — 아무 화면도
   안 싣던 `js/guide-api.js` 다 (KEY-281 이 남긴 처분). 실리는 쪽
   (`patient_wireframe/js/guide-api.js`)의 같은 계약은 아래 검사가 잰다. */


test("로그인 mock 응답은 StaffLoginResponse·StaffMeResponse와 일치한다", async () => {
  const box = load("api");
  const login = plain(await box.api.login("staff01", "local-only-password"));
  const me = plain(await box.api.me(login.access_token));
  validate(login, schema("StaffLoginResponse"), "login");
  validate(me, schema("StaffMeResponse"), "me");
  /* 두 DTO는 현재 OpenAPI에 additionalProperties:false가 없어 공통 validator만으로는
     초과 필드를 잡지 못한다. mock은 실제 응답 필드 목록과 정확히 맞춘다. */
  validateExactProperties(login, schema("StaffLoginResponse"), "login");
  validateExactProperties(me, schema("StaffMeResponse"), "me");
});

test("OCR 확정 mock 응답은 OcrFieldResponse와 일치한다", async () => {
  const box = load("api", "ocr-api");
  const before = plain(await box.ocrApi.result("mock-8801"));
  before.fields.forEach((field, index) => validate(field, schema("OcrFieldResponse"), `ocr-result.fields[${index}]`));
  const result = plain(await box.ocrApi.updateField(9106, { value: "2.4", base_version: 1, confirm: true }));
  validate(result, schema("OcrFieldResponse"), "ocr-confirm");
});

test("안내 제출·승인·링크 발급 mock 응답은 서버 DTO와 일치한다", async () => {
  const submitBox = load("api", "doctor-api", { search: "?mock=1&case=staff" });
  validate(plain(await submitBox.doctorApi.submit(8801)), schema("GuideResponse"), "guide-submit");

  const approveBox = load("api", "doctor-api");
  validate(plain(await approveBox.doctorApi.approve(8801)), schema("GuideResponse"), "guide-approve");

  const linkBox = load("api", "doctor-api", { search: "?mock=1&case=approved" });
  validate(plain(await linkBox.doctorApi.issuePatientLink(8801)), schema("PatientLinkIssueResponse"), "guide-link");
});

test("OTP 발급·검증 mock 응답은 서버 DTO와 일치한다", async () => {
  const box = load("api", "checkin-api");
  validate(plain(await box.checkinApi.issueOtp("synthetic-link")), schema("PatientOtpIssueResponse"), "otp-issue");
  validate(plain(await box.checkinApi.verifyOtp("synthetic-link", "123456")), schema("PatientOtpVerifyResponse"), "otp-verify");
});

test("환자 가이드 mock fixture는 PatientGuideResponse와 일치하고 비밀값 키를 갖지 않는다", () => {
  const source = fs.readFileSync(path.join(ROOT, "frontend/patient_wireframe/js/guide-api.js"), "utf8");
  const context = vm.createContext({
    URLSearchParams,
    Promise,
    setTimeout: (fn) => setTimeout(fn, 0),
    window: { location: { search: "?mock=1", hostname: "localhost", protocol: "http:" } },
  });
  vm.runInContext(source, context);
  for (const [name, guide] of Object.entries(context.MOCK_GUIDES)) {
    const response = plain(guide);
    validate(response, schema("PatientGuideResponse"), `patient-guide.${name}`);
    assert.doesNotMatch(JSON.stringify(Object.keys(response)), /otp|token|raw_link/i);
  }
});

test("mock 오류 상태는 실제 서버 분기와 같은 HTTP status를 보존한다", async () => {
  const login = load("api");
  await assert.rejects(login.api.login("missing", "wrong-password"), (error) => error.status === 401);

  const guide = load("api", "doctor-api", { search: "?mock=1&case=returned" });
  await assert.rejects(guide.doctorApi.approve(8801), (error) => error.status === 409 && error.code === "GUIDE_NOT_PENDING");
  await assert.rejects(guide.doctorApi.issuePatientLink(8801), (error) => error.status === 409);

  const otp = load("api", "checkin-api", { search: "?mock=1&case=locked" });
  await assert.rejects(otp.checkinApi.issueOtp("synthetic-link"), (error) => error.status === 429);
});

test("finalize mock 은 서버와 같은 것만 막는다 — 값이 있는데 안 본 것", async () => {
  /* **관대해도 엄해도 거짓말이다** — KEY-271.
   *
   * 서버 `finalize_ocr` 는 「값이 있는데 미확정」 하나만 막는다
   * (`app/ocr/service.py`). 못 읽어 빈 칸은 화면이 확정하지 않으므로
   * (`fieldsToConfirm`) 그것까지 막으면 S1-7 진료는 안내문을 영영 못 만든다.
   *
   * 목업이 서버보다 **엄하면** 실서버에서 되는 일을 `?mock=1` 로 못 해 보고,
   * **느슨하면** 여기서 되는 일이 실서버에서 막힌다. 이 검사는 그 둘을 다 잰다. */
  const blocked = load("api", "ocr-api");
  await assert.rejects(
    blocked.ocrApi.finalizeOcr(8801),
    (error) => error.status === 422 && error.code === "OCR_NOT_CONFIRMED",
    "아무것도 확정 안 한 판독을 그냥 통과시켰다 — 확정의 뜻이 없어진다",
  );

  const box = load("api", "ocr-api");
  const before = await box.ocrApi.result("mock-8801");
  const unread = before.fields.filter((field) => field.value === null || field.value === "");
  assert.ok(unread.length > 0, "목업에 못 읽은 칸이 없다 — 이 검사가 헛돈다");

  for (const field of before.fields) {
    if (field.value === null || field.value === "") continue;
    await box.ocrApi.updateField(field.ocr_field_id, { base_version: field.version, confirm: true });
  }

  /* 못 읽은 칸은 여전히 미확정으로 남아 있다. 그래도 통과해야 한다. */
  const made = await box.ocrApi.finalizeOcr(8801);
  assert.equal(made.visit_id, 8801, "못 읽은 칸 하나가 처방을 통째로 막았다 — S1-7 이 죽는다");
});
