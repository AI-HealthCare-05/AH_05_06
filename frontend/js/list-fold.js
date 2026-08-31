/* ── 좌측 목록 접기 (320 ↔ 48) ──────────────────────────────────────────
 *
 * 와이어프레임의 모든 의료진·어드민 프레임에 좌측 머리의 `◀` 접기 단추가 있다.
 * 접힌 모습은 `S1-7` 이 그려 두었다 — 「좌측 48px 접힌 레일」.
 *
 * **직접 접은 것만 기억한다.** 화면이 접으라고 할 수도 있는데(`screenWants`),
 * 그것까지 기억하면 다음에 환자 목록을 열었을 때 까닭 없이 접혀 있다 —
 * 사람은 자기가 접은 기억이 없으니 고장으로 읽는다.
 *
 * 판독 화면은 지금 저절로 접지 않는다. 와이어프레임 `S1-7` 이 「좌측 48px 접힌
 * 레일」을 그려 두었지만, 실제로 써 보니 화면을 옮길 때마다 목록이 사라져
 * 다음 환자로 가는 길을 잃었다. 접고 싶으면 `◀` 로 접는다.
 *
 * `sessionStorage` 를 쓴다. 탭을 닫으면 잊는 편이 낫다 — 다른 자리에서 일하다
 * 돌아왔을 때 접힘이 남아 있으면 그것도 까닭 없는 상태다.
 */
var FOLD_KEY = "listFolded";

/* 접혀야 하는가 — 사람이 접었거나, 화면이 접으라고 했거나. */
function listShouldFold(remembered, screenWants) {
  return remembered === true || screenWants === true;
}

function foldMemory() {
  try {
    return sessionStorage.getItem(FOLD_KEY) === "1";
  } catch (denied) {
    /* 사생활 보호 창에서는 저장소가 던진다. 기억을 못 할 뿐 화면은 돌아야 한다. */
    return false;
  }
}

function rememberFold(folded) {
  try {
    if (folded) sessionStorage.setItem(FOLD_KEY, "1");
    else sessionStorage.removeItem(FOLD_KEY);
  } catch (denied) {
    /* 못 적어도 그만이다 */
  }
}

/* 화면에 반영한다. `byHand` 가 참일 때만 기억한다. */
function applyFold(folded, byHand) {
  var list = document.querySelector(".list");
  var button = document.querySelector(".list__fold");
  if (!list) return;

  list.classList.toggle("list--folded", folded);
  if (button) {
    button.textContent = folded ? "▶" : "◀";
    button.setAttribute("aria-expanded", folded ? "false" : "true");
    button.setAttribute("title", folded ? "목록 펴기" : "목록 접기");
  }
  if (byHand) rememberFold(folded);
}

function wireFold(screenWants) {
  var button = document.querySelector(".list__fold");
  applyFold(listShouldFold(foldMemory(), screenWants), false);
  if (!button) return;

  button.addEventListener("click", function () {
    var list = document.querySelector(".list");
    applyFold(!(list && list.classList.contains("list--folded")), true);
  });
}
