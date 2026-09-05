/* 환자 링크 블록의 규칙 — KEY-275.
 *
 * 두 화면(안내문 문자 설정 · 현황)이 같은 답을 봐야 한다. 규칙이 두 벌이 되면
 * 한쪽만 고쳐지고, 같은 링크가 화면마다 다르게 보인다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

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

test("규칙에 주소가 안 담긴다 — 토큰이 이 파일을 지나가지 않는다", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const src = fs.readFileSync(path.join(__dirname, "..", "js", "patient-link-view.js"), "utf8");
  assert.doesNotMatch(src, /localStorage|sessionStorage|console\.|document\./, "규칙이 화면·저장소를 만졌다");
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
