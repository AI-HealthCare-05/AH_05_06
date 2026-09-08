/* KEY-260 — 세션이 끝나 OTP 로 돌려보낼 때 **돌아올 길을 잃지 않는다.**
 *
 * 환자 링크 토큰은 access log 에 안 남기려고 주소에서 즉시 지운다(KEY-205).
 * 그런데 OTP 화면 주소를 만드는 `otpEntryUrl()` 이 **주소를 다시 읽고** 있어서,
 * 지운 뒤에 부르면 빈 손으로 돌아왔다.
 *
 * 그런 자리가 실제로 있다 — 링크는 살아 있는데 세션만 끝난 401 에서 OTP 로
 * 돌려보내는 갈래(KEY-178). 거기서 토큰을 잃으면 환자는 **어느 안내로 돌아가야
 * 하는지 모르는** OTP 화면에 떨어지고, 받았던 문자를 다시 찾아야 한다.
 *
 * ── 왜 원문 대조로는 못 잡았나 ──────────────────────────────────
 * 이 흐름을 지키던 검사 둘이 소스에 `otpEntryUrl` 이 있는지만 봤다. 함수는 늘
 * 있었고 부르는 자리도 맞았다 — 틀린 것은 **부르는 시각**이다. 그래서 여기서는
 * 순서를 실제로 재현한다: 토큰이 주소에 있는 상태와, 지워진 뒤의 상태.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const GUIDE_JS = path.join(__dirname, "..", "patient_wireframe", "js", "guide.js");
const TOKEN = "synthetic-link-token";

/** `otpEntryUrl` 만 떼어 내, 토큰을 담기 전과 후를 각각 돌려 본다. */
function otpEntryUrlWith(captured, search, hash) {
  const source = fs.readFileSync(GUIDE_JS, "utf8");
  const at = source.indexOf("function otpEntryUrl()");
  assert.notEqual(at, -1, "otpEntryUrl 이 사라졌다");
  const body = source.slice(at, source.indexOf("\n  }", at) + 4);

  /* 토큰을 읽는 규칙은 `js/link-token.js` 것이다 — `guide.html` 이 `guide.js`
     보다 먼저 싣는다(KEY-292). 여기서도 같은 차례로 태운다. */
  const rule = fs.readFileSync(path.join(__dirname, "..", "js", "link-token.js"), "utf8");

  /* `TOKEN` 은 같은 IIFE 의 `var` 라 끌어올려진다 — 담기기 전에는 `undefined`. */
  const make = new Function(
    "URLSearchParams",
    "window",
    "TOKEN",
    rule + "\n" + body + "\nreturn otpEntryUrl();",
  );
  return make(URLSearchParams, { location: { search, hash } }, captured);
}

test("① 주소에서 토큰을 지운 뒤에도 돌아갈 곳을 안다", () => {
  /* 401 갈래가 부르는 시각이다 — `takeGuideToken()` 이 이미 주소를 비웠다. */
  const url = otpEntryUrlWith(TOKEN, "", "");

  assert.match(url, /^\/patient_wireframe\/html\/otp\.html/, "OTP 화면이 아니다");
  assert.ok(url.includes(`#t=${TOKEN}`), `돌아갈 토큰을 잃었다 — ${url}`);
});

test("② 토큰을 담기 전에는 주소에서 읽는다 — 목업 갈래가 그 시각이다", () => {
  /* `otpEntryUrl()` 은 `TOKEN` 이 담기기 **전에** 한 번 불린다(목업에서 OTP 미인증).
     그때 `TOKEN` 은 `undefined` 이므로 주소 읽기가 살아 있어야 한다. */
  const url = otpEntryUrlWith(undefined, "?mock=1", `#t=${TOKEN}`);

  assert.ok(url.includes(`#t=${TOKEN}`), `주소에 있는 토큰도 못 읽는다 — ${url}`);
  assert.ok(url.includes("mock=1"), "목업 갈래를 잃었다");
});

test("③ 토큰은 질의가 아니라 조각으로 싣는다 — access log 에 안 남는다", () => {
  const url = otpEntryUrlWith(TOKEN, "?mock=1", "");
  const [beforeHash] = url.split("#");

  assert.ok(!beforeHash.includes(TOKEN), `토큰이 질의 문자열에 실렸다 — ${url}`);
  assert.match(url, /#t=/, "조각으로 안 싣는다");
});

test("④ 401 갈래가 그 주소로 돌려보낸다", () => {
  /* 함수가 옳아도 부르는 자리가 없으면 소용없다. */
  const source = fs.readFileSync(GUIDE_JS, "utf8");
  const at = source.indexOf("GUIDE_ERROR.SESSION_EXPIRED");
  assert.notEqual(at, -1, "세션 만료 갈래가 사라졌다");

  assert.match(
    source.slice(at, at + 200),
    /location\.replace\(otpEntryUrl\(\)\)/,
    "세션이 끝났는데 OTP 로 안 보낸다",
  );
});
