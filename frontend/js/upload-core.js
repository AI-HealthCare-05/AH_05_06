/* **진료기록 올리기 — 알맹이.**
 *
 * 올리는 자리가 둘이다. 진료기록 탭(S1-5)과 판독 확인 화면(S1-6) 왼쪽 판.
 * 판독을 보다가 「사진이 흐려서 못 읽었구나」를 알게 되는데, 그때 다시 올리러
 * 다른 화면으로 갔다가 돌아오면 보던 값을 잃는다. 그 자리에서 올려야 한다.
 *
 * 두 화면이 각자 올리는 코드를 가지면 크기 제한이나 보내는 주소가 갈라진다 —
 * 한쪽만 고쳐지고, 어느 쪽에서 올렸느냐에 따라 되고 안 되고가 달라진다.
 * 판독 항목 이름표를 한 곳에 모은 것과 같은 이유다 (WP-S③ 공용 모듈).
 *
 * **여기 있는 것은 규칙과 보내는 일뿐이다.** 그리는 것은 화면마다 다르다 —
 * 진료기록 탭은 큰 판에 목록까지 세우고, 판독 화면은 접었다 펴는 작은 판이다.
 */

/* 명세에 제약이 없어 여기서 정한다 — PR 에 적어 서버와 맞춘다.
   화면 검증은 편의일 뿐이고 최종 판정은 서버가 한다 (KEY-9 와 같은 원칙). */
var UPLOAD_MAX_BYTES = 20 * 1024 * 1024;
var UPLOAD_MAX_FILES = 10;
var UPLOAD_ACCEPT = /^(image\/|application\/pdf$)/;

/** 이 파일을 받을 수 있나. 받을 수 없으면 **왜** 안 되는지 사람 말로. */
function rejectFile(file, human) {
  if (!file) return "파일이 없습니다.";
  if (!UPLOAD_ACCEPT.test(file.type || "")) return "이미지나 PDF만 올릴 수 있습니다.";
  if (file.size > UPLOAD_MAX_BYTES) {
    return "파일이 너무 큽니다 (" + (human ? human(UPLOAD_MAX_BYTES) : "20MB") + " 까지).";
  }
  return null;
}

/** 몇 장을 더 받을 수 있나. 넘치면 **자르되 말해 준다** — 조용히 버리지 않는다. */
function roomFor(have) {
  return Math.max(0, UPLOAD_MAX_FILES - (have || 0));
}

/* 서버로 보낸다.
 *
 * `document_type` 을 **안 보낸다.** 서버가 EMR 로 두고 판독이 가려낸다 —
 * 스탭이 매번 어느 칸인지 고민하게 만들지 않는다 (와이어프레임 S1-3).
 * 화면이 문서를 종류가 아니라 「이미지1 · 이미지2」로 부르는 것과 같은 판단이다.
 *
 * **붙이는 자리는 `visit_id` 다.** 화면에 보이는 것은 차트번호이고 둘은 다르다.
 * 차트번호로 걸면 같은 환자의 지난 진료에 이번 기록이 붙는다.
 */
function postDocument(visitId, file) {
  var form = new FormData();
  form.append("files", file);

  var headers = { Accept: "application/json" };
  var token = session.token();
  if (token) headers["Authorization"] = "Bearer " + token;

  return fetch(API_BASE + "/front-desk/visits/" + visitId + "/documents", {
    method: "POST",
    headers: headers,
    credentials: "include",
    body: form,
  }).then(function (res) {
    return res.json().then(function (data) {
      if (!res.ok) throw new Error(data.message || "업로드 실패");
      return data;
    });
  });
}

/* 끌어다 놓기를 붙인다.
 *
 * 창 전체에서 기본 동작(파일 열기)을 막지 않으면, 빗나가게 놓았을 때 브라우저가
 * 그 파일로 화면을 덮어 버린다 — 올리던 것이 통째로 날아간다. */
var dropGuardOn = false;

function guardWindowDrop() {
  if (dropGuardOn) return;
  dropGuardOn = true;
  ["dragenter", "dragover", "dragleave", "drop"].forEach(function (name) {
    window.addEventListener(name, function (event) {
      event.preventDefault();
    });
  });
}

function wireDrop(dropEl, onFiles) {
  if (!dropEl) return;
  guardWindowDrop();

  dropEl.addEventListener("dragenter", function () {
    dropEl.classList.add("is-over");
  });
  dropEl.addEventListener("dragover", function () {
    dropEl.classList.add("is-over");
  });
  dropEl.addEventListener("dragleave", function (event) {
    /* 안쪽 요소를 지날 때도 dragleave 가 난다 — 그때 지우면 깜빡인다 */
    if (!dropEl.contains(event.relatedTarget)) dropEl.classList.remove("is-over");
  });
  dropEl.addEventListener("drop", function (event) {
    dropEl.classList.remove("is-over");
    if (event.dataTransfer && event.dataTransfer.files.length) onFiles(event.dataTransfer.files);
  });
}
