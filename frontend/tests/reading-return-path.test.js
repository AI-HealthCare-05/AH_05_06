/* **판독으로 돌아가는 길** — 와이어프레임에 없는 추가.
 *
 * 판독 확인 도중에 「기본정보」를 눌러 돌아오면 판독 화면으로 갈 길이 없었다.
 * 단계 줄의 「진료기록」은 업로드 칸으로 오고 판독 확인은 그 다음 화면이라
 * 단계 줄에 자리가 없다 — 막다른 곳이다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");

function box() {
  return load("api", "session", "patients-api", "shell", "ocr-api", "upload");
}

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

test("**판독 작업이 없으면 길을 내지 않는다** — 눌러도 아무 일 없는 버튼이 된다", () => {
  const { readingLink } = box();

  assert.equal(readingLink(null).show, false, "작업이 없는데 버튼이 뜬다");
  assert.equal(readingLink({}).show, false, "빈 응답에도 버튼이 뜬다");
  assert.equal(readingLink({ status: "PROCESSING" }).show, false, "작업 번호가 없는데 버튼이 뜬다");
});

test("판독이 도는 중에도 길을 낸다 — 기다리는 화면이 판독 화면에 있다", () => {
  const { readingLink } = box();

  const link = readingLink({ ocr_job_id: "j1", status: "PROCESSING", progress: 40 });
  assert.equal(link.show, true);
  assert.match(link.say, /판독 중/);
  assert.match(link.say, /40/, "얼마나 됐는지 안 알려 준다");
});

test("**실패해도 막지 않는다** — 여기서 막으면 실패 사유를 볼 데가 없다", () => {
  const { readingLink } = box();

  const link = readingLink({ ocr_job_id: "j1", status: "FAILED" });
  assert.equal(link.show, true, "실패하면 판독 화면으로 갈 길이 사라진다");
  assert.match(link.say, /실패/);
});

test("끝났으면 끝났다고 말한다", () => {
  const { readingLink } = box();

  const link = readingLink({ ocr_job_id: "j1", status: "SUCCEEDED" });
  assert.equal(link.show, true);
  assert.match(link.say, /끝났/);
  assert.equal(link.label, "판독 결과 확인");
});

test("**화면에 그 자리가 있다** — 규칙만 있고 자리가 없으면 소용없다", () => {
  const page = read("patients.html");

  const at = page.indexOf('id="reading"');
  assert.ok(at !== -1, "진료기록 탭에 판독 블록이 없다");

  /* 업로드 칸 **위**에 있어야 한다. 아래에 두면 파일 목록과 안내문이 길어서
     스크롤해야 보이고, 그러면 없는 것과 같다. */
  const record = page.indexOf('id="panel-record"');
  const drop = page.indexOf('id="drop"');
  assert.ok(record < at && at < drop, "판독 블록이 업로드 칸 아래에 있다 — 스크롤해야 보인다");

  assert.ok(page.includes('id="reading-go"'), "누를 것이 없다");
  assert.ok(page.includes('id="reading-say"'), "지금 어느 상태인지 말할 자리가 없다");
});

test("**처음엔 숨어 있다** — 물어보기 전에 뜨면 판독이 있는 것처럼 보인다", () => {
  const page = read("patients.html");
  const tag = page.slice(page.indexOf('id="reading"') - 200, page.indexOf('id="reading"') + 40);
  assert.match(tag, /hidden/, "물어보기 전부터 떠 있다");
});

test("**다른 환자를 고르면 앞 사람의 길이 안 남는다**", () => {
  /* 답이 오는 사이 다른 환자를 고르면, 늦게 온 답이 새 환자 화면에 붙는다 —
     남의 판독으로 가는 버튼이 된다. `doctor.js` 가 승인에서 같은 이유로
     `approvingId` 를 따로 잡는다. */
  const source = read("js/upload.js");
  const code = source
    .split("\n")
    .filter((line) => !line.trim().startsWith("/*") && !line.trim().startsWith("*"))
    .join("\n");

  const at = code.indexOf("function askReading");
  const body = code.slice(at, code.indexOf("function drawReading"));

  assert.ok(body.includes("var asked"), "어느 진료를 물었는지 안 붙잡는다");

  /* **두 갈래를 다 센다.** 성공 쪽 방어만 빼도 실패 쪽이 남아 통과했다 —
     한 번만 보면 검사가 안 문다(돌연변이가 살아남았다). 답은 성공으로도
     실패로도 오고, 어느 쪽이든 늦게 오면 남의 화면에 붙는다. */
  const guards = body.match(/visit\.visit_id !== asked/g) || [];
  assert.equal(
    guards.length,
    2,
    `답이 온 뒤 아직 그 환자인지 보는 자리가 ${guards.length}곳이다 — 성공·실패 두 갈래 모두 봐야 한다`,
  );
});
