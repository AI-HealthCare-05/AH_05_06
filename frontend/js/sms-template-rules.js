/* 문자 문구 — 와이어프레임 D2-5 의 규칙들. KEY-234.
 *
 * 원문 부제: 「문자 본문 템플릿 — 안내문(링크 콘텐츠)과 층이 다르다」.
 * 환자 카드의 안내문 탭은 링크로 **열리는** 글을 다루고, 이 화면은 그 링크를
 * **실어 나르는** 문자 본문을 다룬다.
 *
 * `sms-plan.js`(S1-14 문자 설정)와도 다르다. 저쪽은 「이 환자에게 어느 회차를
 * 보낼까」이고 이쪽은 「그 회차의 글이 무엇인가」다.
 */

/* 90바이트를 넘으면 장문(LMS)이 되어 문자 단가가 달라진다(어드민 A1-5).
   서버도 같은 수를 갖는다 — 화면이 「단문」이라 했는데 서버가 막으면 안 된다. */
var SMS_LIMIT = 90;

/* **EUC-KR 기준으로 센다** — 문자 단가를 정하는 것이 그 셈이다.
 *
 * UTF-8 로 세면 한글이 3바이트라 90바이트 제한이 실제보다 훨씬 빨리 걸려,
 * 보낼 수 있는 문구를 못 보낸다고 말하게 된다.
 *
 * 브라우저에 EUC-KR 인코더가 없어 코드포인트로 가른다: 아스키 한 자 1바이트,
 * 그 밖은 2바이트. 한글·한자·전각 기호가 EUC-KR 에서 2바이트라 맞아떨어진다.
 * 서버(`app/services/message_templates.py`)와 같은 수가 나와야 하고, 검사가
 * 같은 글로 양쪽을 잰다.
 */
function smsBytes(body) {
  var text = body == null ? "" : String(body);
  var total = 0;
  for (var i = 0; i < text.length; i++) {
    total += text.charCodeAt(i) < 128 ? 1 : 2;
  }
  return total;
}

/** 단문인가 장문인가. 원문 「단문 · 84바이트」·「⚠ 장문(LMS) · 96바이트」. */
function smsLength(body) {
  var bytes = smsBytes(body);
  return {
    bytes: bytes,
    long: bytes > SMS_LIMIT,
    say: (bytes > SMS_LIMIT ? "⚠ 장문(LMS) · " : "단문 · ") + bytes + "바이트",
  };
}

/** 문구에 든 변수 이름들. */
function templateVariables(body) {
  var found = [];
  var re = /\{([^{}]*)\}/g;
  var hit;
  while ((hit = re.exec(String(body == null ? "" : body)))) found.push(hit[1]);
  return found;
}

/* 저장하기 전에 화면이 먼저 재는 것. **서버가 판정하지만** 눌러 보고서야
   아는 것보다 치는 동안 아는 편이 낫다. 서버와 같은 이유로 막는다.

   돌려주는 것은 **막는 까닭 한 줄**이다. 없으면 저장할 수 있다. */
function templateProblem(item, body, known) {
  var text = String(body == null ? "" : body).trim();
  if (!text) return "문구를 비워 둘 수 없습니다";

  var found = templateVariables(text);
  var required = (item && item.required_variables) || [];
  for (var i = 0; i < required.length; i++) {
    if (found.indexOf(required[i]) === -1) {
      return (
        "{" +
        required[i] +
        "} 는 지울 수 없습니다 — 환자가 안내를 열 곳이 없어집니다"
      );
    }
  }
  for (var j = 0; j < found.length; j++) {
    if ((known || []).indexOf(found[j]) === -1) {
      return "{" + found[j] + "} 는 발송 시 채울 수 없는 변수입니다";
    }
  }
  return "";
}

/* 회차 이름. **문자 어휘를 다시 적지 않는다** — `message-words.js` 것을 쓰고,
   거기 없는 둘만 여기서 채운다. 재진 안내는 회차가 아니라(승인이 세우지
   않는다) 그 표에 없고, 인증번호는 고칠 수 없어 그 표에 없다. */
var EXTRA_TEMPLATE_SAYING = { REVISIT: "재진 안내", OTP: "인증번호" };

function templateSaying(kind) {
  return EXTRA_TEMPLATE_SAYING[kind] || MESSAGE_SAYING[kind] || kind || "";
}

/* 원문이 문구마다 붙여 둔 한 줄. 기능에 매인 것만 적는다 — 「이 변수는 이런
   뜻이다」를 다 적으면 화면이 설명서가 된다. */
var TEMPLATE_NOTE = {
  GUIDE: "{링크}는 지울 수 없습니다 · 만료는 발송 후 3일",
  CHECK_D7: "{링크}는 지울 수 없습니다 · 해제할 수 없는 회차입니다",
  RUN_OUT: "{D}는 처방 설정의 「소진 N일 전」 값입니다",
  REVISIT: "{의원명} · {예약링크}는 어드민에서 정합니다",
};
