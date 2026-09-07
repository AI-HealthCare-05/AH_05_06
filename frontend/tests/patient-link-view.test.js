/* 환자 링크 블록의 규칙 — KEY-275.
 *
 * 두 화면(안내문 문자 설정 · 현황)이 같은 답을 봐야 한다. 규칙이 두 벌이 되면
 * 한쪽만 고쳐지고, 같은 링크가 화면마다 다르게 보인다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { codeOnly } = require("./source.js");

function rules() {
  return load("api", "patient-link-view");
}

const AT = (s) => new Date(s);

test("승인 전에는 링크가 없다 — 스탭이 만들 수 있는 것이 아니다", () => {
  const { patientLinkState, LINK_STATE } = rules();
  assert.equal(patientLinkState(null, "STAFF_REVIEW", AT("2026-09-05T10:00:00+09:00")), LINK_STATE.NOT_YET);
  assert.equal(
    patientLinkState({ expiresAt: "2026-09-12T18:00:00+09:00" }, "APPROVAL_PENDING", AT("2026-09-05T10:00:00+09:00")),
    LINK_STATE.NOT_YET,
    "승인 대기인데 링크가 산 것처럼 보였다",
  );
});

test("기한이 지나면 살아 있는 것으로 안 보인다", () => {
  const { patientLinkState, LINK_STATE } = rules();
  const link = { expiresAt: "2026-09-04T18:00:00+09:00" };
  assert.equal(patientLinkState(link, "SCHEDULED_TO_SEND", AT("2026-09-05T10:00:00+09:00")), LINK_STATE.EXPIRED);
});

test("**딱 만료 시각이면 지난 것이다** — 경계에서 살아 있다고 하면 환자가 빈 화면을 본다", () => {
  const { patientLinkExpired } = rules();
  const at = "2026-09-12T18:00:00+09:00";
  assert.equal(patientLinkExpired({ expiresAt: at }, AT(at)), true);
  assert.equal(patientLinkExpired({ expiresAt: at }, AT("2026-09-12T17:59:59+09:00")), false);
});

test("**못 읽는 값은 지난 것으로 보지 않는다** — 멀쩡한 링크를 죽이면 환자가 쥔 것이 끊긴다", () => {
  const { patientLinkExpired, patientLinkState, LINK_STATE } = rules();
  const broken = { expiresAt: "어제쯤" };
  assert.equal(patientLinkExpired(broken, AT("2026-09-05T10:00:00+09:00")), false);
  assert.equal(patientLinkState(broken, "SCHEDULED_TO_SEND", AT("2026-09-05T10:00:00+09:00")), LINK_STATE.LIVE);
});

test("방금 만든 것만 주소를 쥔다 — 새로고침하면 되찾을 길이 없다", () => {
  const { patientLinkState, LINK_STATE } = rules();
  const now = AT("2026-09-05T10:00:00+09:00");
  const at = { expiresAt: "2026-09-12T18:00:00+09:00" };
  assert.equal(patientLinkState({ ...at, fresh: true }, "SCHEDULED_TO_SEND", now), LINK_STATE.FRESH);
  assert.equal(patientLinkState(at, "SCHEDULED_TO_SEND", now), LINK_STATE.LIVE);
});

test("남은 날은 내림이다 — 6일 하고 반나절은 6일이다", () => {
  const { patientLinkDaysLeft } = rules();
  const link = { expiresAt: "2026-09-12T18:00:00+09:00" };
  assert.equal(patientLinkDaysLeft(link, AT("2026-09-06T06:00:00+09:00")), 6);
  assert.equal(patientLinkDaysLeft(link, AT("2026-09-12T06:00:00+09:00")), 0);
});

test("**상태마다 다음에 할 일을 말한다** — 「링크 없음」만 있으면 제 잘못인 줄 안다", () => {
  const { patientLinkStateNote, LINK_STATE } = rules();
  const now = AT("2026-09-05T10:00:00+09:00");
  assert.match(patientLinkStateNote(LINK_STATE.NOT_YET, null, now), /의사가 승인하면/);
  assert.match(patientLinkStateNote(LINK_STATE.EXPIRED, null, now), /안내문이 안 보입니다/);
  assert.match(
    patientLinkStateNote(LINK_STATE.LIVE, { expiresAt: "2026-09-12T18:00:00+09:00" }, now),
    /7일 남음/,
  );
  assert.match(
    patientLinkStateNote(LINK_STATE.LIVE, { expiresAt: "2026-09-05T18:00:00+09:00" }, now),
    /오늘 안에/,
    "마지막 날에 「0일 남음」이라 하면 남은 줄 안다",
  );
});

test("**주소가 없으면 복사·열기를 내주지 않는다** — 눌러도 아무 일 없는 단추가 가장 나쁘다", () => {
  const { patientLinkActions, LINK_STATE } = rules();
  assert.deepEqual(patientLinkActions(LINK_STATE.NOT_YET), []);
  assert.deepEqual(patientLinkActions(LINK_STATE.FRESH), ["copy", "open", "new"]);
  assert.deepEqual(patientLinkActions(LINK_STATE.LIVE), ["new"], "주소를 안 쥐고 복사를 내줬다");
  assert.deepEqual(patientLinkActions(LINK_STATE.EXPIRED), ["new"]);
});

test("주소가 저장소·로그로 안 샌다 — 이 창의 기억으로만 산다", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const src = codeOnly(fs.readFileSync(path.join(__dirname, "..", "js", "patient-link-view.js"), "utf8"));

  /* **앞서는 `document.` 까지 통째로 막았다.** 그때는 이 파일이 순수 규칙뿐이라
     그래도 됐는데, 배선(`wirePatientLink`)이 들어오면서 `addEventListener` 가
     걸렸다. 금지 목록을 넓히는 대신 **막으려던 것을 그대로** 적는다 — 주소가
     이 창 밖으로 나가는 길은 저장소·로그·DOM 셋이다. */
  assert.doesNotMatch(src, /localStorage|sessionStorage/, "주소를 저장소에 남기면 새로고침 뒤에도 남는다");
  assert.doesNotMatch(src, /console\./, "로그에 남기면 개발자도구를 여는 누구나 본다");
});

test("주소를 DOM 에 꽂는 길이 이 파일에 없다", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const src = codeOnly(fs.readFileSync(path.join(__dirname, "..", "js", "patient-link-view.js"), "utf8"));

  /* 블록 HTML 은 **돌려주기만** 한다 — 꽂는 것은 화면 몫이다. 이 파일이 직접
     꽂기 시작하면 주소를 실어 꽂는 한 줄이 언제든 끼어들 수 있다. */
  for (const sink of ["innerHTML", "setAttribute", "textContent", "outerHTML"]) {
    assert.ok(!src.includes(sink), `규칙 파일이 ${sink} 로 화면을 직접 만졌다`);
  }
});

test("쥔 주소는 그 진료의 것일 때만 나온다 — 환자를 옮기면 없는 것이다", () => {
  const { patientLinkKeep, patientLinkOf, patientLinkForget } = rules();

  patientLinkKeep(11, { expiresAt: "2026-09-14T18:00:00+09:00", fresh: true, url: "/x#t=aaa" });
  assert.equal(patientLinkOf(11).url, "/x#t=aaa");

  /* **다음 사람 화면에서 앞 사람 주소를 복사하는 구멍.** 번호가 다르면
     없는 것으로 답한다 — 지우는 것을 잊어도 새지 않게. */
  assert.equal(patientLinkOf(12), null, "남의 진료에 앞 사람 링크가 따라갔다");
  assert.equal(patientLinkOf(undefined), null);

  patientLinkForget();
  assert.equal(patientLinkOf(11), null);
});

test("다시 읽어도 방금 만든 주소는 안 버린다 — 만료만 서버 것으로", () => {
  const { patientLinkKeep, patientLinkAdopt, patientLinkOf, patientLinkForget } = rules();
  patientLinkForget();

  patientLinkKeep(7, { expiresAt: "2026-09-10T18:00:00+09:00", fresh: true, url: "/x#t=bbb" });
  patientLinkAdopt(7, { issued: true, expires_at: "2026-09-14T18:00:00+09:00" });

  const held = patientLinkOf(7);
  assert.equal(held.url, "/x#t=bbb", "다시 읽었다고 주소를 버리면 [복사] 가 사라진다");
  assert.equal(held.fresh, true);
  assert.equal(held.expiresAt, "2026-09-14T18:00:00+09:00", "만료는 서버가 정본이다");
});

test("서버가 「없다」고 하면 쥔 것도 놓는다", () => {
  const { patientLinkKeep, patientLinkAdopt, patientLinkOf, patientLinkForget } = rules();
  patientLinkForget();

  patientLinkKeep(7, { expiresAt: "2026-09-10T18:00:00+09:00", fresh: true, url: "/x#t=ccc" });
  patientLinkAdopt(7, { issued: false, expires_at: null });

  assert.equal(patientLinkOf(7), null, "서버에 없는 링크의 주소를 화면이 계속 쥐고 있다");
});

/* ── 두 화면이 같은 것을 그리는가 ─────────────────────────────────────── */

test("**두 화면이 같은 블록을 그린다** — 규칙도 모양도 한 벌이어야 한다", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const read = (f) => fs.readFileSync(path.join(__dirname, "..", "js", f), "utf8");

  ["guide-view.js", "status-view.js"].forEach((f) => {
    assert.match(
      read(f),
      /patientLinkBlockHtml\(/,
      `${f} 가 블록을 제 손으로 그린다 — 두 벌이 되면 같은 링크가 화면마다 달라진다`,
    );
  });
});

test("**두 화면이 그 파일을 싣는다** — 안 실으면 그 화면에서만 죽는다", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  ["patients.html", "doctor.html"].forEach((f) => {
    const html = fs.readFileSync(path.join(__dirname, "..", f), "utf8");
    assert.match(html, /js\/patient-link-view\.js/, `${f} 가 규칙 파일을 안 싣는다`);
  });
});

test("**모양이 두 화면 다 닿는 CSS 에 있다** — doctor.css 에 두면 스탭 화면만 안 먹는다", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const css = fs.readFileSync(path.join(__dirname, "..", "css", "blocks.css"), "utf8");
  assert.match(css, /\.pl__acts\s*\{/, "블록 모양이 blocks.css 에 없다");

  /* `.grow` 가 딱 그렇게 갈려 있다 — doctor.css 에만 있어 스탭 화면에서 안 민다. */
  const doctorCss = fs.readFileSync(path.join(__dirname, "..", "css", "doctor.css"), "utf8");
  assert.doesNotMatch(doctorCss, /\.pl__/, "블록 모양이 의사 화면 전용 CSS 에 있다");
});

test("**주소를 DOM 에 안 싣는다** — data-* 에도 안 담는다", () => {
  const { patientLinkBlockHtml, LINK_STATE } = rules();
  const now = AT("2026-09-05T10:00:00+09:00");
  const html = patientLinkBlockHtml(
    { expiresAt: "2026-09-12T18:00:00+09:00", fresh: true, url: "https://care-on.kr/g/SECRET" },
    "SCHEDULED_TO_SEND",
    now,
  );
  assert.doesNotMatch(html, /SECRET/, "링크 원문이 HTML 에 실렸다");
  assert.doesNotMatch(html, /https?:\/\//, "주소가 HTML 에 실렸다");
  assert.match(html, /data-patient-link="copy"/, "복사 단추가 없다");
});

test("아직 없을 때는 단추를 안 낸다 — 눌러도 안 되는 단추가 가장 나쁘다", () => {
  const { patientLinkBlockHtml } = rules();
  const html = patientLinkBlockHtml(null, "STAFF_REVIEW", AT("2026-09-05T10:00:00+09:00"));
  assert.doesNotMatch(html, /data-patient-link=/);
  assert.match(html, /의사가 승인하면/);
});

test("기한이 지나면 그렇게 말하고 새로 만들 길만 준다", () => {
  const { patientLinkBlockHtml } = rules();
  const html = patientLinkBlockHtml(
    { expiresAt: "2026-09-04T18:00:00+09:00" },
    "SCHEDULED_TO_SEND",
    AT("2026-09-05T10:00:00+09:00"),
  );
  assert.match(html, /닫혔습니다/);
  assert.match(html, /data-patient-link="new"/);
  assert.doesNotMatch(html, /data-patient-link="copy"/, "주소도 없는데 복사를 내줬다");
});

/* ── 승인은 됐는데 아직 안 만든 상태 ─────────────────────────────────────
 *
 * **브라우저에서 잡았다.** 목업 단계에서는 승인 전과 한 덩어리(`NOT_YET`)였다.
 * 서버의 `approve()` 가 링크를 자동으로 만들어 준다면 그래도 됐는데,
 * `app/services/guides.py` 에 그런 코드가 없다 — 승인된 채 링크가 없는 상태는
 * 실제로 지나가는 자리다.
 *
 * 그 자리에서 블록은 **이미 승인된 건에 대고** 「의사가 승인하면 자동으로
 * 발급됩니다」라고 말했고, 단추도 안 냈다. 스탭이 첫 링크를 만들 길이 화면에서
 * 사라져 있었다 — 인수조건 「스탭 계정으로 「새 링크」가 된다」가 못 서는 자리다.
 */

test("승인됐는데 아직 안 만든 것은 **승인 전과 다른 상태**다", () => {
  const { patientLinkState, LINK_STATE } = rules();
  const now = AT("2026-09-07T10:00:00+09:00");

  assert.equal(patientLinkState(null, "APPROVAL_PENDING", now), LINK_STATE.NOT_YET);
  assert.equal(patientLinkState(null, "SCHEDULED_TO_SEND", now), LINK_STATE.NOT_ISSUED, "승인 전과 같은 상태로 뭉갰다");
});

test("승인 뒤에는 만들 단추가 있다 — 없으면 스탭이 첫 링크를 못 만든다", () => {
  const { patientLinkActions, LINK_STATE } = rules();

  assert.deepEqual(patientLinkActions(LINK_STATE.NOT_YET), [], "승인 전에 만들 단추를 내면 눌러도 409 다");
  assert.deepEqual(patientLinkActions(LINK_STATE.NOT_ISSUED), ["new"]);
});

test("두 상태가 서로 다른 말을 한다 — 승인된 건에 「승인하면」이라고 하지 않는다", () => {
  const { patientLinkStateNote, LINK_STATE } = rules();
  const now = AT("2026-09-07T10:00:00+09:00");

  const before = patientLinkStateNote(LINK_STATE.NOT_YET, null, now);
  const after = patientLinkStateNote(LINK_STATE.NOT_ISSUED, null, now);

  assert.notEqual(before, after, "승인 전과 승인 뒤가 같은 말을 한다");
  assert.ok(!/승인하면/.test(after), `이미 승인된 건에 「승인하면」이라고 말한다 — ${after}`);
  assert.ok(/새 링크/.test(after), "무엇을 눌러야 하는지 안 알려 준다");
});

test("첫 발급은 issue, 교체는 re-issue — 없는 링크에 교체를 부르면 404 다", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const src = codeOnly(fs.readFileSync(path.join(__dirname, "..", "js", "patient-link-view.js"), "utf8"));

  /* 서버가 `_lock_link` 로 막는다 — 스탭에게는 「새 링크가 안 만들어진다」로
     보인다. 쥔 것이 있느냐로 종점을 가른다. */
  assert.ok(src.includes("doctorApi.issuePatientLink"), "첫 발급 종점을 안 쓴다");
  assert.ok(src.includes("doctorApi.reIssuePatientLink"), "교체 종점을 안 쓴다");
  assert.match(src, /patientLinkOf\(visitId\)\s*\?\s*doctorApi\.reIssuePatientLink\s*:\s*doctorApi\.issuePatientLink/);
});
