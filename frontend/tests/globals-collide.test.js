/* **한 화면이 싣는 파일들이 같은 이름을 두 번 얹지 않는다.**
 *
 * 이 저장소의 화면 코드는 모듈이 아니다 — `<script src>` 로 그냥 실려서 전역에
 * 얹힌다. 그래서 **이름이 곧 자리**이고, 두 파일이 같은 이름을 선언하면 나중에
 * 실린 쪽이 앞의 것을 통째로 덮는다.
 *
 * 실제로 그랬다. `patients-api.js` 의 `MOCK_PATIENTS`(배열)를 `doctor-api.js`
 * 의 `MOCK_PATIENTS`(객체)가 덮어서, 목록 목업이 `.find is not a function` 으로
 * 죽었다. 화면은 「환자가 없습니다」만 띄웠고, 오류는 콘솔에만 있었다.
 *
 * 덮어쓰기는 **조용하다.** 어느 검사도 안 걸리고, 두 파일을 따로 읽으면 둘 다
 * 멀쩡하다. 같이 실었을 때만 드러난다 — 그래서 화면 단위로 잰다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { codeOnly, markupOnly } = require("./source.js");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");

/** 그 화면이 싣는 스크립트를 실리는 차례대로. */
function scriptsOf(page) {
  const html = markupOnly(fs.readFileSync(path.join(ROOT, page), "utf8"));
  return [...html.matchAll(/<script\s+src="\/js\/([\w-]+\.js)"/g)].map((m) => m[1]);
}

/** 그 파일이 전역에 얹는 이름들 — 맨 왼쪽에서 시작하는 선언만 본다.
    함수 안의 `var` 는 들여쓰기가 있어 걸리지 않는다. */
function globalsOf(file) {
  const code = codeOnly(fs.readFileSync(path.join(ROOT, "js", file), "utf8"));
  const names = new Set();
  for (const m of code.matchAll(/^(?:var|let|const|function)\s+([A-Za-z_$][\w$]*)/gm)) {
    names.add(m[1]);
  }
  return names;
}

test("**한 화면 안에서 전역 이름이 겹치지 않는다**", () => {
  const pages = fs.readdirSync(ROOT).filter((n) => n.endsWith(".html"));
  assert.ok(pages.length >= 5, `화면 파일을 못 읽었다: ${pages.length}개`);

  const clashes = [];
  let checked = 0;

  for (const page of pages) {
    const scripts = scriptsOf(page).filter((f) => fs.existsSync(path.join(ROOT, "js", f)));
    if (scripts.length < 2) continue;
    checked += 1;

    const owner = new Map();
    for (const file of scripts) {
      for (const name of globalsOf(file)) {
        if (owner.has(name) && owner.get(name) !== file) {
          clashes.push(`${page}: ${name} — ${owner.get(name)} 을 ${file} 이 덮는다`);
        } else {
          owner.set(name, file);
        }
      }
    }
  }

  assert.ok(checked >= 3, `여러 파일을 싣는 화면을 못 찾았다: ${checked}개 — 검사가 헛돈다`);
  assert.deepEqual(
    [...new Set(clashes)],
    [],
    "전역 이름이 덮인다 — 나중에 실린 쪽이 이깁니다:\n  " + [...new Set(clashes)].join("\n  "),
  );
});

test("검사가 실제로 이름을 읽는다 — 못 읽으면 늘 초록이다", () => {
  /* 정규식이 어긋나 이름을 하나도 못 읽으면 위 검사가 조용히 통과한다.
     아는 이름 몇 개가 실제로 걸리는지 본다. */
  assert.ok(globalsOf("patients-api.js").has("MOCK_PATIENTS"), "목록 목업을 못 읽었다");
  assert.ok(globalsOf("doctor-api.js").has("MOCK_GUIDE_PATIENTS"), "의사 목업을 못 읽었다");
  assert.ok(globalsOf("shell.js").has("selectedVisit"), "함수 선언을 못 읽었다");

  /* 함수 **안**의 것은 안 읽어야 한다 — 전역이 아니다 */
  assert.ok(!globalsOf("shell.js").has("mine"), "함수 안의 이름까지 전역으로 센다");
});

/* ── 목업이 오늘도 쓸모 있는가 ───────────────────────────────────────── */

test("**목업 고정 데이터가 오늘 날짜로 선다** — 달력이 지나면 조용히 쓸모없어진다", () => {
  /* 고정 값은 「2026-08-20 이 오늘」이라 치고 적혔다. 밀어 주지 않으면 하루가
     지날 때마다 목록이 「오늘 등록된 환자가 없습니다」만 띄운다. */
  const { MOCK_TODAY } = load("api", "session", "patients-api");
  assert.ok(Array.isArray(MOCK_TODAY) && MOCK_TODAY.length >= 3, "목업 목록을 못 읽었다");

  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

  const onToday = MOCK_TODAY.filter((v) => String(v.visited_at).slice(0, 10) === today);
  assert.ok(onToday.length >= 2, `오늘 진료가 ${onToday.length}건이다 — 목록이 비어 보인다`);

  /* **사이 간격은 남는다.** 박수빈의 보완은 「며칠 전에 걸린 채로 남은 것」이라,
     오늘로 당겨 버리면 오늘 것과 구분이 안 된다. */
  const older = MOCK_TODAY.filter((v) => String(v.visited_at).slice(0, 10) < today);
  assert.ok(older.length >= 1, "지난 날짜 진료가 하나도 없다 — 간격이 뭉갰다");
});

test("**진료기록을 안 올린 진료에는 판독이 없다**", async () => {
  /* 어느 진료를 물어도 작업 번호를 내주면, 목록이 「진료기록 없음」이라 적은
     환자를 눌러도 판독 결과가 뜬다 — 방금 등록한 환자가 처음 만나는 화면을
     `?mock=1` 로는 한 번도 못 본다. */
  const box = load("api", "session", "patients-api", "ocr-api");
  const { MOCK_TODAY, mockJobForVisit } = box;

  const blank = MOCK_TODAY.filter((v) => v.detail_status === "NO_DOCUMENT")[0];
  assert.ok(blank, "목업에 진료기록 없는 진료가 없다 — 검사가 헛돈다");

  await assert.rejects(
    () => mockJobForVisit(blank.visit_id),
    (err) => err && err.code === "NOT_FOUND",
    "진료기록이 없는데 판독을 내준다",
  );

  const done = MOCK_TODAY.filter((v) => v.detail_status !== "NO_DOCUMENT")[0];
  assert.ok(done, "목업에 판독이 있는 진료가 없다");
  const job = await mockJobForVisit(done.visit_id);
  assert.ok(job && job.ocr_job_id, "판독이 있는 진료에까지 안 내준다");
});
