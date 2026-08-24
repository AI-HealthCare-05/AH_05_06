/* 안내문 조회 한 겹 — KEY-93
 *
 *   GET /api/v1/guides/{token}   승인 완료된 안내문만 내려온다
 *
 * 실제 경로는 KEY-90 개발용 링크 토큰을 사용한다. 아래 목업은 화면 정본을
 * 서버 없이 확인할 때만 사용한다.
 * 주소에 ?mock=1 을 붙이면 켜지고 한 번 켜면 그 탭에서 유지된다 — js/api.js 와 같은 방식이다.
 *
 * 환자는 원문 의료문서를 볼 수 없다. 이 응답에는 승인된 안내 문구와
 * 처방·검사 값만 담기고 업로드 원본이나 OCR 원문은 담기지 않는다(KEY-94 가 검사한다).
 */

var GUIDE_API_BASE = "/api/v1";

var GUIDE_ERROR = {
  NOT_APPROVED: "GUIDE_NOT_APPROVED",
  NOT_FOUND: "LINK_NOT_FOUND",
  LINK_EXPIRED: "LINK_EXPIRED",
};

var GUIDE_MOCK = (function () {
  try {
    var q = new URLSearchParams(window.location.search);
    if (q.has("mock")) {
      sessionStorage.setItem("guide_mock", q.get("mock") === "0" ? "0" : "1");
    }
    return sessionStorage.getItem("guide_mock") === "1";
  } catch (e) {
    return false;
  }
})();

/* 목업 두 벌 — 와이어프레임 P2~P4 의 두 질환 묶음을 그대로 옮겼다.
   ?case=pcos 로 두 번째를 본다. 이름·날짜는 전부 지어낸 것이다. */
var MOCK_GUIDES = {
  endo: {
    visit_date: "2026.08.13",
    clinic_name: "〇〇여성의원",
    generated_at: "2026.08.13 10:44",
    disease_label: "자궁내막증 · 비잔정 복용 중",
    summary: "자궁내막증으로 진료받으셨고, 통증 관리를 위한 약을 처방받으셨어요.",
    goals: [
      { name: "빈혈 Hb", start: "10.2", now: "10.4", target: "12" },
      { name: "자궁내막종", start: "2.8", now: "2.4", target: "─" },
      { name: "AMH", start: "곧 나와요", now: "─", target: "─" },
    ],
    goal_note: "빈혈은 목표까지 다 왔어요.\n자궁내막종은 더 커지지 않게 · AMH는 결과가 나오면 채워드릴게요",
    drugs: [{ name: "비잔정 2mg", ingredient: "성분 · 디에노게스트", dosage: "1일 1회 · 84일분" }],
    why: [
      "지난번 8점이던 생리통이 오늘 4점까지 내려왔어요. 약이 잘 듣고 있다는 뜻이에요.",
      "다만 통증이 줄었다고 병변까지 없어진 것은 아니에요. 남아 있으면 계속 염증을 일으켜 유착과 폐경 후 만성 골반통의 원인이 됩니다.",
      "끊을 시기는 진료 때 함께 정해요.",
    ],
    how: ["매일 같은 시간에 드세요.", "휴약기 없이 계속 복용합니다."],
    next_visit: "3개월 뒤 재진 예정이에요. 아팠던 날이나 불편했던 점을 기억해 두셨다가 이야기해 주세요.",
    caution: {
      title: "비잔정 2mg 드시는 동안",
      lead: "미리 알아두시면 걱정을 덜 수 있어요",
      groups: [
        {
          title: "흔하고 괜찮은 반응",
          strong: true,
          items: [
            "피가 조금씩 비치는 것이 가장 흔해요. 특히 처음 3개월에 그래요. 팬티라이너에 묻을 정도로 나왔다 안 나왔다 합니다.",
            "가슴이 단단해지는 느낌, 몸이 붓는 느낌도 시간이 지나면 좋아집니다.",
            "생리가 없어지는 것은 폐경이 아니에요. 약을 끊으면 다시 돌아옵니다.",
            "임의로 중단하지 마세요.",
          ],
        },
        {
          title: "이런 건 알려주세요",
          items: [
            "드물게 기분이 가라앉는 분들이 있어요. 평소와 다르게 느껴지면 참지 마시고 알려주세요. 약을 조절하거나 바꿀 수 있어요.",
          ],
        },
        {
          title: "함께 드시면 안 되는 것",
          items: [
            "세인트존스워트(성요한풀)가 든 건강기능식품이나 허브차는 약효를 떨어뜨릴 수 있어요. 드시고 계시다면 알려주세요.",
            "드시는 영양제나 한약이 있으면 진료 때 말씀해 주세요.",
          ],
        },
        {
          title: "이 약은 피임약이 아니에요",
          items: ["피임이 필요하시면 별도의 방법을 함께 사용하세요."],
        },
      ],
      emergency: [
        "기분이 심하게 가라앉아 일상생활이 어려울 때",
        "스스로를 해치고 싶은 생각이 들 때",
        "생리가 아닌데 출혈이 많아 어지럽거나 힘이 빠질 때",
      ],
      ask: "출혈이 2주 이상 계속되거나 심한 복통이 있으면 연락 주세요.",
    },
    challenge: [
      { text: "밤 11시 전에 잠들기", freq: "주 5일" },
      { text: "칼슘 음식 챙겨 먹기", freq: "주 5일" },
      { text: "주 3회 30분 걷기", freq: "주 3회" },
    ],
    axes: [
      {
        name: "수면",
        challenge: true,
        item: { text: "밤 11시 전에 잠들기", freq: "주 5일" },
        body: [
          "지금은 새벽 1시쯤 주무신다고 하셨죠. 밤 10시~새벽 2시 사이에 잠들어 있는 것이 좋아요. 좋은 호르몬이 이 시간에 가장 많이 나옵니다.",
          "자기 전 2시간은 휴대폰을 보지 않으시면 더 좋아요.",
        ],
      },
      {
        name: "뼈 건강",
        challenge: true,
        item: { text: "칼슘 음식 챙겨 먹기", freq: "주 5일" },
        body: [
          "우유 · 요거트 · 치즈 · 두부 · 녹색 잎채소를 매일 챙겨 드세요. 햇빛을 짧게라도 매일 쬐어 주세요.",
          "약을 오래 드시는 동안 뼈를 함께 챙기면 좋습니다.",
        ],
      },
      {
        name: "운동",
        challenge: true,
        item: { text: "주 3회 30분 걷기", freq: "주 3회" },
        body: [
          "걷기 · 계단 오르기처럼 뼈에 체중이 실리는 운동이 특히 좋아요. 생리통이 심한 날은 쉬어가셔도 돼요.",
        ],
      },
      {
        name: "통증 관리",
        body: [
          "달력이나 메모에 생리통 점수를 0점(안 아픔)~10점(아주 아픔)으로 적어두세요. 다음 진료 때 가장 도움이 되는 기록이에요.",
        ],
      },
    ],
  },
};

/* 다낭성 묶음은 자궁내막증과 구조가 같고 문구만 다르다.
   화면이 질환을 몰라도 그려지는지 확인하려고 최소한만 채운다. */
MOCK_GUIDES.pcos = {
  visit_date: "2026.08.13",
  clinic_name: "〇〇여성의원",
  generated_at: "2026.08.13 10:44",
  disease_label: "다낭성난소증후군 · 야즈정 복용 중",
  summary: "다낭성난소증후군으로 진료받으셨고, 주기를 고르게 하는 약을 처방받으셨어요.",
  goals: [
    { name: "LH / FSH 비율", start: "3.2", now: "2.4", target: "2.0" },
    { name: "DHEA-S", start: "260", now: "210", target: "200" },
    { name: "생리 주기", start: "안 옴", now: "38일", target: "35일" },
  ],
  goal_note: "주기가 돌아오고 있어요.",
  drugs: [{ name: "야즈정", ingredient: "성분 · 드로스피레논 · 에티닐에스트라디올", dosage: "1일 1회 · 84일분" }],
  why: [
    "주기가 규칙적이 된 것은 약이 잘 듣고 있다는 뜻이에요. 다 나은 것이 아니라서 끊으면 다시 돌아옵니다.",
    "끊을 시기는 진료 때 함께 정해요.",
  ],
  how: ["분홍색 알약을 먼저 다 드시고, 이어서 흰색 알약을 드세요.", "매일 같은 시간에 드세요."],
  next_visit: "3개월 뒤 재진 예정이에요.",
  caution: {
    title: "야즈정 드시는 동안",
    lead: "미리 알아두시면 걱정을 덜 수 있어요",
    groups: [
      {
        title: "흔하고 괜찮은 반응",
        strong: true,
        items: ["처음 몇 달은 부정출혈이 있을 수 있어요. 대개 시간이 지나면 줄어듭니다."],
      },
      { title: "담배는 끊어 주세요", items: ["흡연은 혈전 위험을 크게 높입니다."] },
    ],
    emergency: ["갑자기 숨이 차거나 가슴이 아플 때", "한쪽 종아리가 붓고 아플 때", "심한 두통이나 시야 이상이 있을 때"],
    ask: "부정출혈이 3개월 이상 계속되면 연락 주세요.",
  },
  challenge: [
    { text: "밤 11시 전에 잠들기", freq: "주 5일" },
    { text: "배달음식 줄이기", freq: "주 5일" },
    { text: "주 3회 30분 걷기", freq: "주 3회" },
  ],
  axes: [
    { name: "수면", challenge: true, item: { text: "밤 11시 전에 잠들기", freq: "주 5일" }, body: ["규칙적인 수면이 호르몬 주기를 돕습니다."] },
    { name: "식이", challenge: true, item: { text: "배달음식 줄이기", freq: "주 5일" }, body: ["정제 탄수화물을 줄이면 인슐린 저항성 개선에 도움이 됩니다."] },
    { name: "운동", challenge: true, item: { text: "주 3회 30분 걷기", freq: "주 3회" }, body: ["가벼운 유산소로 시작해 꾸준히 이어가는 것이 중요합니다."] },
    { name: "월경주기", body: ["생리 시작일을 달력에 적어두세요. 다음 진료 때 가장 도움이 되는 기록이에요."] },
  ],
};

function GuideError(code) {
  this.name = "GuideError";
  this.code = code;
}
GuideError.prototype = Object.create(Error.prototype);

/* 승인 완료된 안내문 하나를 가져온다.
   목업에서는 ?case=pcos 로 두 번째 묶음, ?case=none 으로 예외(미승인)를 본다. */
function fetchGuide(token) {
  if (GUIDE_MOCK) {
    var q = new URLSearchParams(window.location.search);
    var key = q.get("case") || "endo";
    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        if (key === "none") {
          reject(new GuideError(GUIDE_ERROR.NOT_APPROVED));
          return;
        }
        var guide = MOCK_GUIDES[key];
        if (!guide) {
          reject(new GuideError(GUIDE_ERROR.NOT_FOUND));
          return;
        }
        resolve(guide);
      }, 150);
    });
  }

  return fetch(GUIDE_API_BASE + "/guides/" + encodeURIComponent(token), {
    credentials: "include",
    headers: { Accept: "application/json" },
  }).then(function (res) {
    if (res.ok) return res.json();
    return res
      .json()
      .catch(function () {
        return {};
      })
      .then(function (data) {
        throw new GuideError(data.code || GUIDE_ERROR.NOT_FOUND);
      });
  });
}
