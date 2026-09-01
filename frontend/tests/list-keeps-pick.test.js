/* **오른쪽 환자는 누른 것만 바꾼다.**
 *
 * 목록의 상태 탭(작성 중 · 보완 · 승인 요청 · 발송 대기 · 완료)을 누르거나
 * 날짜를 옮기면 오른쪽 상세가 통째로 리셋됐다. 두 가지가 겹쳐 있었다.
 *
 *   ① 고른 사실이 줄의 `aria-current` **한 곳에만** 있었다. 탭을 끄면 그 줄이
 *      목록에서 빠지면서 고른 사실까지 사라졌고, 탭을 다시 켜도 안 돌아왔다.
 *   ② 탭을 누를 때마다 **같은 환자에게도** `visit:selected` 를 다시 쐈다.
 *      그 신호는 상세를 처음부터 그리게 한다 — 열어 둔 칸이 기본정보로
 *      되감기고, 치던 문자 문구가 날아가고, 열어 둔 창이 닫힌다.
 *
 * 목록에 **안 보이는 것**과 **안 고른 것**은 다르다. 상태 탭도 날짜도 목록의
 * 보기일 뿐, 무엇을 열어 뒀는지가 아니다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function box() {
  return load("api", "session", "patients-api", "shell");
}

const SHOWN = [{ visit_id: 11 }, { visit_id: 12 }, { visit_id: 13 }];

/* ── ① 고른 것을 놓지 않는다 ────────────────────────────────────────── */

test("**필터가 가려도, 날짜를 옮겨도 고른 것을 놓지 않는다**", () => {
  const { nextPicked } = box();
  const mine = { visit_id: 12 };

  /* 12번을 골라 뒀는데 상태 탭을 꺼서 목록에서 빠졌다 */
  assert.equal(nextPicked(mine, [{ visit_id: 11 }]), mine, "가려졌다고 고른 것을 버렸다");

  /* 어제로 옮겨서 그 날 목록에 아예 없다 */
  assert.equal(nextPicked(mine, []), mine, "날짜를 옮겼다고 고른 것을 버렸다");

  /* 다른 날의 줄들이 보여도 맨 위로 갈아타지 않는다 — 자동 선택이 오른쪽을
     누르지도 않은 환자로 바꾸던 자리다 */
  assert.equal(nextPicked(mine, SHOWN), mine, "다른 날 맨 위 사람으로 갈아탔다");
});

test("아직 아무도 안 골랐을 때만 맨 위를 고른다", () => {
  const { nextPicked } = box();

  assert.equal(nextPicked(null, SHOWN), SHOWN[0], "처음 들어왔는데 아무것도 안 골랐다");
  assert.equal(nextPicked(null, []), null, "고를 줄이 없는데 무언가를 골랐다");
});

/* ── ② 같은 사람에게 두 번 알리지 않는다 ───────────────────────────── */

test("**같은 사람이면 상세를 다시 그리지 않는다**", () => {
  const { paneMove } = box();

  /* 12번을 열어 둔 채 상태 탭을 눌렀다 — 고른 것도 알린 것도 12번 그대로다 */
  assert.deepEqual(paneMove(12, 12), { view: "view-card", tell: "refresh" });
});

test("사람이 바뀌면 상세를 처음부터 그린다", () => {
  const { paneMove } = box();
  assert.deepEqual(paneMove(13, 12), { view: "view-card", tell: "select" });
  assert.deepEqual(paneMove(12, null), { view: "view-card", tell: "select" });
});

test("**아무도 안 골랐을 때만 판을 비운다**", () => {
  const { paneMove } = box();

  assert.deepEqual(paneMove(null, null), { view: "view-none", tell: null });

  /* 목록이 다 가려졌든 빈 날짜로 옮겼든, 고른 환자는 그대로 열려 있어야 한다.
     예전에는 「보이는 줄이 없다」는 이유로 오른쪽을 「할 일 없음」으로 밀어
     보던 환자를 빼앗았다. */
  assert.deepEqual(paneMove(12, 12), { view: "view-card", tell: "refresh" });
});

/* ── 붙어 있는가 ────────────────────────────────────────────────────── */

test("규칙이 실제로 쓰인다 — 만들어만 두면 화면은 옛길로 간다", () => {
  const code = codeOnly(read("js/shell.js"));

  const rows = code.indexOf("function renderRows");
  assert.ok(code.slice(rows, rows + 900).includes("nextPicked("), "renderRows 가 안 쓴다");

  const sync = code.indexOf("function syncPane");
  assert.ok(code.slice(sync, sync + 900).includes("paneMove("), "syncPane 이 안 쓴다");

  /* 고른 것을 DOM 에서 되읽으면 ①이 그대로 돌아온다 */
  const pick = code.indexOf("function selectedVisit");
  assert.ok(
    !code.slice(pick, pick + 400).includes("aria-current"),
    "고른 것을 다시 DOM 에서 읽는다 — 필터가 가리면 또 사라진다",
  );
});

test("**날짜를 옮겨도 고른 것을 놓지 않는다**", () => {
  const code = codeOnly(read("js/shell.js"));
  const at = code.indexOf("function loadDay");
  const around = code.slice(at, at + 900);
  assert.ok(
    !/picked\s*=\s*null/.test(around),
    "날짜를 옮기면서 고른 것을 버린다 — 돌아왔을 때 다시 찾아 눌러야 한다",
  );
});

test("다른 날을 보는 중에도 고른 환자를 들고 있는다", () => {
  const code = codeOnly(read("js/shell.js"));
  const at = code.indexOf("function selectedVisit");
  const around = code.slice(at, at + 500);

  /* 아이디만 들고 오늘 목록에서 되찾으면, 어제로 옮기는 순간 못 찾아 오른쪽이
     빈다. 줄 자체를 들고 있다가 목록에 있을 때만 새 값으로 갈아 준다. */
  assert.match(around, /rowByVisit\(rows, picked\.visit_id\)\s*\|\|\s*picked/, "줄을 안 들고 있는다");
});

/* ── 받는 쪽 ────────────────────────────────────────────────────────── */

test("상세와 의사 화면이 「줄 값만 새로 왔다」를 받는다", () => {
  ["js/detail.js", "js/doctor.js"].forEach((file) => {
    const code = codeOnly(read(file));
    const at = code.indexOf('"visit:refreshed"');
    assert.ok(at !== -1, `${file} 이 안 받는다 — 승인 뒤 상태 배지가 옛것으로 남는다`);

    const around = code.slice(at, at + 400);
    assert.match(around, /renderHead\(\)/, `${file} 이 머리를 안 고친다`);
    assert.ok(
      !/\bload\(/.test(around),
      `${file} 이 다시 통째로 불러온다 — 되감기를 막으려던 것이 그대로 돌아온다`,
    );
  });
});

test("**줄을 누르면 그것이 전역의 고른 진료가 된다**", () => {
  const code = codeOnly(read("js/shell.js"));
  const at = code.indexOf('getElementById("rows").addEventListener');
  assert.ok(at !== -1, "줄 누름을 받는 자리가 없다");

  const handler = code.slice(at, at + 1400);

  /* 누른 것을 전역에 안 담으면 오른쪽이 앞사람에 머문다 */
  assert.match(handler, /(^|[^.\w])picked\s*=\s*\w/m, "누른 것을 담아 두지 않는다");

  /* 손잡이 안에서 `picked` 를 다시 선언하면 **전역을 가린다** — 여기서 정한
     것이 밖으로 안 나가, 목록만 바뀌고 오른쪽은 그대로다. 한 번 겪은 함정이다. */
  assert.ok(
    !/\b(var|let|const)\s+picked\b/.test(handler),
    "손잡이가 `picked` 를 다시 선언한다 — 전역을 가려서 고른 것이 밖으로 안 나간다",
  );
});

test("**상태 탭은 처음에 하나도 안 켜진다** — 그 날 전부가 보인다", () => {
  /* 켜 둔 채 시작하면 목록에 없는 환자가 **숨겨진 것인지 없는 것인지** 구분이
     안 된다. 방금 등록한 사람이 안 보여 「등록이 안 됐나」가 되던 자리다. */
  const code = codeOnly(read("js/shell.js"));
  const at = code.indexOf("function renderChips");
  assert.notEqual(at, -1, "칩을 그리는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n}", at));
  assert.match(body, /aria-pressed="false"/, "칩이 켜진 채 시작한다");
  assert.ok(!body.includes("DEFAULT_TABS"), "역할별 기본 선택이 남아 있다");
  assert.ok(!code.includes("var DEFAULT_TABS"), "안 쓰는 기본 선택표가 남아 있다");

  /* 하나도 안 켜면 전부 보여야 한다 — 아무것도 안 보이면 그게 더 나쁘다 */
  const { visibleRows } = load("api", "session", "patients-api", "shell");
  assert.equal(typeof visibleRows, "function", "거르는 자리를 못 읽었다");
  const filter = codeOnly(read("js/shell.js"));
  assert.match(filter, /if \(on\.length &&/, "안 켰을 때도 걸러 낸다 — 목록이 통째로 빈다");
});
