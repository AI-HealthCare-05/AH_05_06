/* 환자 링크 블록의 규칙 — KEY-275.
 *
 * 두 화면(안내문 문자 설정 · 현황)이 같은 답을 봐야 한다. 규칙이 두 벌이 되면
 * 한쪽만 고쳐지고, 같은 링크가 화면마다 다르게 보인다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");
const { codeOnly } = require("./source.js");

function rules() {
  /* `clinic-clock` 을 함께 싣는다 — 만료 시각을 의원 시계로 읽는다(KEY-275).
     화면 둘(`doctor.html`·`patients.html`)도 이 차례로 싣는다. */
  return load("api", "clinic-clock", "patient-link-view");
}

const AT = (s) => new Date(s);

test("승인 전이고 링크도 없으면 만들 것이 없다", () => {
  const { patientLinkState, LINK_STATE } = rules();
  assert.equal(patientLinkState(null, "STAFF_REVIEW", AT("2026-09-05T10:00:00+09:00")), LINK_STATE.NOT_YET);
  assert.equal(patientLinkState(null, "APPROVAL_PENDING", AT("2026-09-05T10:00:00+09:00")), LINK_STATE.NOT_YET);
});

test("**승인이 철회돼도 살아 있는 링크는 감추지 않는다** — 이희진 님 `#250` 리뷰 ②", () => {
  /* 여기 있던 단언이 정반대였다 — 「승인 대기인데 링크가 산 것처럼 보였다」를
     실패로 적어 두어서, **감추는 것**이 계약이 돼 있었다. 그런데 서버의
     `unapprove()` 는 상태만 되돌리고 `PatientGuideLink` 를 안 건드린다.
     그래서 그 링크는 여전히 열리는데 화면에서만 사라졌다 — 스탭이 그것을
     폐기할 길도 함께 사라졌고, 나중에 재승인되면 회전된 적 없는 옛 토큰이
     아무 신호 없이 다시 산다. */
  const { patientLinkState, patientLinkActions, patientLinkTag, LINK_STATE } = rules();
  const alive = { expiresAt: "2026-09-12T18:00:00+09:00" };
  const now = AT("2026-09-05T10:00:00+09:00");

  assert.equal(patientLinkState(alive, "APPROVAL_PENDING", now), LINK_STATE.ORPHAN);
  assert.equal(patientLinkState(alive, "STAFF_REVIEW", now), LINK_STATE.ORPHAN);

  /* 기한이 지난 것까지 되살리지는 않는다 — 그건 이미 아무도 못 연다. */
  const dead = { expiresAt: "2026-09-01T18:00:00+09:00" };
  assert.equal(patientLinkState(dead, "APPROVAL_PENDING", now), LINK_STATE.NOT_YET);

  /* **보이기만 하면 소용이 없다 — 끊을 길이 함께 있어야 한다.** */
  /* `join` 으로 견준다 — 상자 안에서 만든 배열이라 프로토타입이 달라
     `deepStrictEqual` 이 값이 같아도 걸린다. */
  assert.equal(patientLinkActions(LINK_STATE.ORPHAN).join(","), "revoke", "폐기할 단추가 없다");
  assert.equal(patientLinkTag(LINK_STATE.ORPHAN), "승인 철회됨");
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

test("같은 링크를 다시 읽으면 방금 만든 주소는 안 버린다", () => {
  const { patientLinkKeep, patientLinkAdopt, patientLinkOf, patientLinkForget } = rules();
  patientLinkForget();

  /* 같은 링크의 **단순 재조회**다 — 만료 시각이 그대로다. */
  patientLinkKeep(7, { expiresAt: "2026-09-10T18:00:00+09:00", fresh: true, url: "/x#t=bbb" });
  patientLinkAdopt(7, { issued: true, expires_at: "2026-09-10T18:00:00+09:00" });

  const held = patientLinkOf(7);
  assert.equal(held.url, "/x#t=bbb", "다시 읽었다고 주소를 버리면 [복사] 가 사라진다");
  assert.equal(held.fresh, true);
  assert.equal(held.expiresAt, "2026-09-10T18:00:00+09:00", "만료는 서버가 정본이다");
});

/* ── 다른 창·다른 직원이 링크를 돌렸을 때 — 유가은 님 `#250` ────────────────
 *
 * 여기 있던 단언이 **버그를 계약으로 적어 두고 있었다**: 만료 시각이 달라졌는데도
 * 옛 주소를 지키는 것을 「통과」로 셌다. 그래서 다음 흐름이 검사에 안 걸렸다.
 *
 *   ① 화면 A 가 링크를 발급해 원문 주소를 쥔다
 *   ② 화면 B(또는 다른 직원)가 같은 진료의 링크를 다시 발급한다
 *   ③ 화면 A 가 상태를 다시 읽는다
 *   ④ 화면 A 에는 **새 링크의 만료일**이 뜨는데 [복사]·[열기] 에는
 *      **폐기된 옛 주소**가 남는다 — 환자는 안 열리는 링크를 받는다
 */

test("**다른 곳에서 링크가 돌면 옛 주소를 놓는다** — 세대가 다르다", () => {
  const { patientLinkKeep, patientLinkAdopt, patientLinkOf, patientLinkForget } = rules();
  patientLinkForget();

  patientLinkKeep(7, { expiresAt: "2026-09-10T18:00:00+09:00", fresh: true, url: "/otp.html#t=old" });
  /* 다른 창이 재발급했다 — 새 토큰과 함께 만료 시각도 새로 잡힌다. */
  const next = patientLinkAdopt(7, { issued: true, expires_at: "2026-09-15T10:00:00+09:00" });

  assert.equal(next.url, "", "폐기된 주소를 계속 쥐고 있다 — 스탭이 복사하면 환자가 못 연다");
  assert.equal(next.fresh, false, "남의 세대 링크를 「방금 만든 것」으로 보였다");
  assert.equal(next.expiresAt, "2026-09-15T10:00:00+09:00", "만료는 서버가 정본이다");
  assert.equal(patientLinkOf(7).url, "", "쥔 자리에도 옛 주소가 남았다");
});

test("만료 시각은 **글자가 아니라 시각**으로 견준다", () => {
  const { patientLinkSameGeneration } = rules();

  /* 같은 순간을 다른 모양으로 적어 보내도 같은 세대다 — 여기서 갈라 버리면
     서버가 표기만 바꿔도 [복사] 가 사라진다. */
  assert.equal(patientLinkSameGeneration("2026-09-10T18:00:00+09:00", "2026-09-10T09:00:00Z"), true);
  assert.equal(patientLinkSameGeneration("2026-09-10T18:00:00+09:00", "2026-09-10T18:00:00+09:00"), true);

  assert.equal(patientLinkSameGeneration("2026-09-10T18:00:00+09:00", "2026-09-15T10:00:00+09:00"), false);

  /* **못 읽는 값은 다른 세대로 친다.** 「모르겠으니 쥔 것을 쓰자」로 기울면
     폐기된 주소가 살아남고, 그 값이 환자에게 그대로 간다. */
  assert.equal(patientLinkSameGeneration(null, "2026-09-10T18:00:00+09:00"), false);
  assert.equal(patientLinkSameGeneration("2026-09-10T18:00:00+09:00", null), false);
  assert.equal(patientLinkSameGeneration("어제", "2026-09-10T18:00:00+09:00"), false);
  assert.equal(patientLinkSameGeneration(null, null), false);
});

test("**옛 링크를 복사·열기 할 수 없다** — 세대가 돈 뒤의 화면", () => {
  const { patientLinkKeep, patientLinkAdopt, patientLinkForget, patientLinkState, patientLinkActions, LINK_STATE } =
    rules();
  patientLinkForget();

  patientLinkKeep(7, { expiresAt: "2026-09-10T18:00:00+09:00", fresh: true, url: "/otp.html#t=old" });
  const next = patientLinkAdopt(7, { issued: true, expires_at: "2026-09-15T10:00:00+09:00" });

  const state = patientLinkState(next, "APPROVED", AT("2026-09-11T10:00:00+09:00"));
  assert.notEqual(state, LINK_STATE.FRESH, "돌아간 링크를 「방금 만든 것」으로 그린다");

  const acts = patientLinkActions(state);
  assert.ok(!acts.includes("copy"), `폐기된 주소에 [복사] 가 남았다 — ${acts.join(",")}`);
  assert.ok(!acts.includes("open"), `폐기된 주소에 [열기] 가 남았다 — ${acts.join(",")}`);
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

test("링크 관리 화면이 공용 규칙 파일을 싣는다", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  ["patients.html"].forEach((f) => {
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

/* ── 이희진 님 `#250` 리뷰 반영을 잰다 ────────────────────────────────── */

test("**만료 시각을 보는 사람의 시계로 읽지 않는다** — 리뷰 ①", () => {
  /* `new Date(...).getHours()` 는 **브라우저 시간대**로 답한다. 이 저장소가
     `clinic-clock.js` 에서 한 번 밟고 고친 자리인데(「KST 아닌 자리에서 열면
     18시가 09시로 뜬다」) 이 파일이 제 손으로 `Date` 를 만들며 되돌려 넣었다.

     **검사를 돌리는 시계와 무관하게** 재려면 글자에 박힌 옵셋을 그대로 읽는지
     보면 된다 — `+00:00` 짜리를 주고 그 자리의 숫자가 그대로 나오는지 본다.
     로컬 시계로 옮기는 코드라면 KST 러너에서 다음 날 03:00 이 된다. */
  const { patientLinkWhen, LINK_STATE } = rules();

  assert.equal(patientLinkWhen({ expiresAt: "2026-09-10T18:00:00+09:00" }, LINK_STATE.LIVE), "9월 10일 18:00 까지");
  assert.equal(
    patientLinkWhen({ expiresAt: "2026-09-10T18:00:00+00:00" }, LINK_STATE.LIVE),
    "9월 10일 18:00 까지",
    "글자에 박힌 시각이 아니라 보는 사람의 시계로 옮겼다",
  );
  assert.equal(patientLinkWhen({ expiresAt: "2026-09-01T09:05:00+09:00" }, LINK_STATE.EXPIRED), "9월 1일 09:05 에 닫혔습니다");
  assert.equal(patientLinkWhen({ expiresAt: "쓰레기" }, LINK_STATE.LIVE), "", "못 읽는 값을 그대로 뱉었다");
});

test("**늦게 온 답은 지금 화면의 것만 그린다** — 리뷰 ③", () => {
  /* 쥔 자리가 지도가 아니라 칸 하나라, 진료 A 의 늦은 답이 B 가 방금 만든
     링크를 통째로 밀어낸다. 그 판정을 이름 있는 함수로 두어 여기서 잰다. */
  const { patientLinkStillCurrent } = rules();
  const on = (id) => ({ visitId: () => id });

  assert.equal(patientLinkStillCurrent(on(7), 7), true);
  assert.equal(patientLinkStillCurrent(on(9), 7), false, "다른 진료로 넘어갔는데 제 것이라고 한다");
  assert.equal(patientLinkStillCurrent(on("7"), 7), true, "글자와 숫자를 다르게 본다");
  assert.equal(patientLinkStillCurrent(on(null), 7), false, "고른 진료가 없는데 그린다");
  assert.equal(patientLinkStillCurrent({}, 7), false, "물을 곳이 없으면 그리지 않는다");
});

test("상태 주석이 실제 상태를 다 적는다 — 리뷰 ⑧ 이 다시 안 나게", () => {
  /* 「상태 넷」이라 적어 둔 것이 `NOT_ISSUED` 를 더할 때 안 따라 고쳐졌다.
     숫자만 고치면 다음에 또 뒤쳐진다 — **이름을 다 적었는지**를 잰다. */
  const { LINK_STATE } = rules();
  /* **주석을 재는 검사라 `codeOnly` 를 안 쓴다** — 그 함수가 걷어내는 것이
     바로 여기서 봐야 할 글이다. */
  const src = fs.readFileSync(path.join(__dirname, "..", "js", "patient-link-view.js"), "utf8");
  const head = src.slice(0, src.indexOf("var LINK_STATE"));

  for (const name of Object.keys(LINK_STATE)) {
    assert.ok(head.includes(name), `상태 주석에 ${name} 이 빠졌다`);
  }
});

test("서버를 부르고 돌아오는 자리마다 그 관문이 있다 — 리뷰 ③", () => {
  /* 위 검사는 판정 **함수**를 잰다. 그 함수를 안 부르면 못 잡는다 —
     실제로 빠져 있던 것이 「함수가 틀렸다」가 아니라 「자리에 없다」였다.

     이벤트를 흘려 재는 것이 낫지만 `browser-shim` 은 일부러 안 흘린다
     (「그리는 것은 브라우저가 할 일」). 그래서 저장소가 같은 걱정에 쓰는 방식을
     따른다 — `key205-patient-link-launch.test.js` 가 `isCurrentPatientLinkRequest`
     를 이렇게 잰다. **이음매를 세어** 하나도 빠지지 않게 한다. */
  const src = codeOnly(fs.readFileSync(path.join(__dirname, "..", "js", "patient-link-view.js"), "utf8"));

  const joints = [...src.matchAll(/\.(then|catch)\(function \([^)]*\) \{/g)];
  assert.ok(joints.length >= 5, `이음매를 못 찾았다 — ${joints.length}개`);

  for (const joint of joints) {
    /* 주석을 걷어낸 자리가 공백으로 남아 창을 밀어낸다 — 접고 나서 본다. */
    const after = src.slice(joint.index, joint.index + 900).replace(/\s+/g, " ");
    /* 관문은 둘 중 하나다 — 진료 번호로 견주거나(`patientLinkStillCurrent`),
       화면이 준 세대 번호로 견주거나(`stale()`). 뒤쪽이 더 강하다: 같은 진료를
       두 번 부른 경우까지 가른다. */
    assert.match(
      after,
      /patientLinkStillCurrent\(opts, visitId\)|if \(stale\(\)\) return;/,
      `서버에서 돌아오는 자리에 관문이 없다 — 「${joint[0]}」 뒤`,
    );
  }
});
