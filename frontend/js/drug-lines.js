/* **처방약 내역** — 판독 화면(S1-6) 맨 위 「진단 · 처방」 줄 아래.
 *
 * 2heej 님 `#176` 리뷰: 「그 아래 처방약 내역이 목록으로 추가되면 좋겠습니다.
 * 아래와 같은 식으로 복용법도 함께 보이면 좋을 것 같습니다.
 *
 *     처방약1  28일  일 1회 같은시간
 *     처방약2  28일  아침 식후
 *     처방약3  10일  필요 시 복용」
 *
 * **한 줄이 두 곳에서 온다.**
 *
 *   약 이름 · 용법 · 복용법  ← 고른 **약속처방**(설정 D2-3 의 「처방 약」)
 *   일수                    ← 이 진료의 **판독값**(「총투」)을 세트 규칙으로 환산
 *
 * 세트는 「이 처방은 통으로 센다 · 한 통은 28일」까지만 알고, 몇 통인지는 그날
 * 판독이 안다. 그래서 어느 한쪽만으로는 이 줄을 못 만든다.
 *
 * 여기 있는 것은 **순수 함수**다 — 화면 요소를 찾지 않으므로 검사가 부를 수
 * 있다. 날짜를 세는 규칙은 눈으로 확인하기 어렵다.
 */

/** 처방일수를 실제 일수로 — **소진 예정일이 이 셈으로 정해진다.**
 *
 * EMR 「총투」 칸의 「3」이 3통일 수도 3일일 수도 있어서 의원마다 다르다.
 * 통으로 세는데 한 통이 며칠인지 모르면 **셈하지 않는다**(`null`) — 지어낸
 * 날짜로 예약하면 엉뚱한 날 문자가 간다.
 */
function courseDaysOf(setting, written) {
  var n = parseInt(String(written), 10);
  if (isNaN(n) || n <= 0) return null;

  var mode = setting && setting.days_mode;
  if (mode !== "PACK") return n;

  var per = parseInt(String(setting && setting.days_per_pack), 10);
  if (isNaN(per) || per <= 0) return null;
  return n * per;
}

/* 기간이 붙지 않는 용법. 서버의 `app/models/prescriptions.py:AS_NEEDED` 와
   같은 낱말이다 — 「필요할 때만」 먹는 약에는 정해진 복용 기간이 없다. */
var AS_NEEDED = "필요시";

/** 이 용법이 **기간을 갖는가.**
 *
 * 「필요시」·「필요 시」·「필요시 복용」이 다 같은 뜻인데 EMR 마다 띄어쓰기가
 * 다르다. 공백을 지우고 본다 — 띄어쓰기 하나로 「진통제를 84일간 드세요」가
 * 되는 것을 막는 자리다.
 */
function hasCourse(frequency) {
  var text = String(frequency == null ? "" : frequency).replace(/\s/g, "");
  return text.indexOf(AS_NEEDED) === -1;
}

/** 한 줄의 오른쪽에 붙는 말 — 「일 1회 · 같은 시간」.
 *
 * **빈 것은 자리를 차지하지 않는다.** 용법만 있고 복용법이 없는 약이 흔한데,
 * 가운뎃점만 남으면 무언가 빠진 것처럼 보인다.
 */
function drugSaying(drug) {
  var parts = [];
  if (drug && drug.frequency) parts.push(String(drug.frequency));
  if (drug && drug.note) parts.push(String(drug.note));
  return parts.join(" · ");
}

/** 며칠치인가. **모르면 `null` 이고, 그건 화면이 비워 둔다.**
 *
 * 「필요시」면 애초에 기간이 없다. 총투를 못 읽었거나 통으로 세는데 한 통이
 * 며칠인지 안 정해 두었으면 셈할 수 없다 — 지어내지 않는다.
 */
function drugDays(drug, set, written) {
  if (!hasCourse(drug && drug.frequency)) return null;
  return courseDaysOf(set, written);
}

/** 고른 처방의 약을 화면 줄로 — 차례는 설정이 정한 그대로다.
 *
 * **고른 것이 없으면 빈 목록이다**(`null` 이 아니다). 「아직 안 골랐다」와
 * 「골랐는데 약이 없다」는 화면이 다르게 말해야 하고, 그 판단은 부르는 쪽이
 * `set` 이 있는지로 한다.
 */
function drugLines(set, written) {
  var drugs = (set && set.drugs) || [];
  return drugs.map(function (drug) {
    return {
      name: String(drug.name == null ? "" : drug.name),
      days: drugDays(drug, set, written),
      saying: drugSaying(drug),
    };
  });
}
