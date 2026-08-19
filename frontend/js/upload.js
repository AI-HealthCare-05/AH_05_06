/* S1-5 진료기록 업로드 — KEY-53
 *
 * 한 버튼으로 여러 장을 받고, 무엇이 찍혔는지는 프로그램이 가려낸다.
 * 종류별로 나눠 올리게 하면 스탭이 매번 어느 칸인지 고민한다.
 *
 * 서버에 업로드 API 가 아직 없다(KEY-39). 계약이 정해지면 uploadOne 만 갈아 끼운다.
 */

(function () {
  var drop = document.getElementById("drop");
  var input = document.getElementById("file");
  var list = document.getElementById("files");
  var next = document.getElementById("next");
  var later = document.getElementById("later");

  /* 명세에 제약이 없어 여기서 정한다 — PR 에 적어 서버와 맞춘다.
     화면 검증은 편의일 뿐이고 최종 판정은 서버가 한다(KEY-9 와 같은 원칙). */
  var MAX_BYTES = 20 * 1024 * 1024;
  var MAX_FILES = 10;
  var ACCEPT = /^(image\/|application\/pdf$)/;

  /* 자동 분류 결과. 프로그램이 틀릴 수 있으므로 사람이 고칠 수 있어야 한다. */
  var KINDS = [
    { key: "emr", label: "과거기록" },
    { key: "note", label: "소견" },
    { key: "lab", label: "검사지" },
  ];

  var files = [];
  var seq = 0;

  function human(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  function reject(file) {
    if (!ACCEPT.test(file.type)) return "이미지나 PDF만 올릴 수 있어요";
    if (file.size > MAX_BYTES) return "파일이 너무 커요 (" + human(MAX_BYTES) + " 까지)";
    return null;
  }

  function render() {
    var done = files.filter(function (f) {
      return f.state === "done";
    });
    /* 실패와 거부를 가른다.
       실패 — 올리다 끊긴 것. 다시 시도하면 될 수 있다.
       거부 — 형식이나 크기가 안 맞는 것. 다시 시도해도 똑같이 안 된다.
       둘을 같게 다루면 눌러도 아무 일이 안 일어나는 버튼을 계속 누르게 된다. */
    var stuck = files.filter(function (f) {
      return f.state === "failed" || f.state === "rejected";
    });

    var head = "";
    if (files.length) {
      head = '<div class="files__count">' + done.length + "장 업로드됨";
      if (stuck.length) head += " · <span style='color:var(--danger)'>" + stuck.length + "장 안 올라감</span>";
      head += "</div>";
    }

    list.innerHTML =
      head +
      files
        .map(function (f) {
          var meta;
          if (f.state === "uploading") {
            meta =
              '<div class="file__meta">올리는 중 ' +
              f.progress +
              '%</div><div class="bar"><div class="bar__fill" style="width:' +
              f.progress +
              '%"></div></div>';
          } else if (f.state === "failed" || f.state === "rejected") {
            meta = '<div class="file__meta file__meta--failed">' + f.error + "</div>";
          } else {
            meta = '<div class="file__meta">' + human(f.size) + "</div>";
          }

          var right = "";
          if (f.state === "done") {
            right =
              '<select class="file__kind" data-kind="' +
              f.id +
              '" aria-label="' +
              f.name +
              ' 종류">' +
              KINDS.map(function (k) {
                return '<option value="' + k.key + '"' + (k.key === f.kind ? " selected" : "") + ">" + k.label + "</option>";
              }).join("") +
              "</select>";
          } else if (f.state === "failed") {
            right = '<button class="file__act" type="button" data-retry="' + f.id + '">다시 시도</button>';
          }
          /* rejected 에는 다시 시도를 붙이지 않는다 — 지우고 다른 파일을 올려야 한다 */

          return (
            '<div class="file' +
            (f.state === "failed" || f.state === "rejected" ? " file--failed" : "") +
            '">' +
            '<div class="file__thumb">' +
            (f.thumb ? '<img src="' + f.thumb + '" alt="">' : f.type === "application/pdf" ? "📄" : "🖼") +
            "</div>" +
            '<div class="file__body"><div class="file__name">' +
            f.name +
            "</div>" +
            meta +
            "</div>" +
            right +
            '<button class="file__act file__act--danger" type="button" data-remove="' +
            f.id +
            '" aria-label="' +
            f.name +
            ' 지우기">지우기</button>' +
            "</div>"
          );
        })
        .join("");

    /* EMR 과거기록이 「안내문 생성 필수」다. 한 장도 없으면 다음으로 못 간다 —
       화면에 필수라고 적어 놓고 통과시키면 다음 단계에서 막힌다. */
    var hasEmr = done.some(function (f) {
      return f.kind === "emr";
    });
    next.disabled = !hasEmr;
    next.title = hasEmr ? "" : "EMR 과거기록을 한 장 이상 올려 주세요";
  }

  /* 임시 업로드. 서버 계약이 정해지면 여기만 갈아 끼운다.
     이름에 "fail" 이 들어가면 실패시킨다 — 재시도 UI 를 눈으로 보려는 것이다. */
  function uploadOne(item) {
    item.state = "uploading";
    item.progress = 0;
    render();

    var timer = setInterval(function () {
      item.progress += 20;
      if (item.progress < 100) return render();
      clearInterval(timer);
      if (/fail/i.test(item.name)) {
        item.state = "failed";
        item.error = "업로드하지 못했어요. 다시 시도해 주세요";
      } else {
        item.state = "done";
        item.kind = guessKind(item.name);
      }
      render();
    }, 120);
  }

  /* 서버가 판독으로 가려내기 전, 화면에서 미리 어림잡는다.
     맞히려는 것이 아니라 고르는 수고를 줄이려는 것이다 — 사람이 고칠 수 있다. */
  function guessKind(name) {
    if (/lab|검사|결과지|result/i.test(name)) return "lab";
    if (/note|소견|메모|초음파/i.test(name)) return "note";
    return "emr";
  }

  function add(fileList) {
    var incoming = Array.prototype.slice.call(fileList);
    var room = MAX_FILES - files.length;
    if (incoming.length > room) {
      incoming = incoming.slice(0, Math.max(0, room));
      alert("한 번에 " + MAX_FILES + "장까지 올릴 수 있어요");
    }

    incoming.forEach(function (file) {
      var item = {
        id: "f" + ++seq,
        name: file.name,
        size: file.size,
        type: file.type,
        state: "uploading",
        progress: 0,
        thumb: null,
        kind: "emr",
      };
      var bad = reject(file);
      files.push(item);

      if (bad) {
        item.state = "rejected";
        item.error = bad;
        return render();
      }
      if (/^image\//.test(file.type)) item.thumb = URL.createObjectURL(file);
      uploadOne(item);
    });
    render();
  }

  document.getElementById("pick").addEventListener("click", function () {
    input.click();
  });

  input.addEventListener("change", function () {
    add(this.files);
    this.value = ""; // 같은 파일을 다시 골라도 change 가 나게 한다
  });

  /* 끌어다 놓기 — 창 전체에서 기본 동작(파일 열기)을 막지 않으면
     빗나가게 놓았을 때 브라우저가 그 파일로 화면을 덮어 버린다. */
  ["dragenter", "dragover", "dragleave", "drop"].forEach(function (name) {
    window.addEventListener(name, function (event) {
      event.preventDefault();
    });
  });

  drop.addEventListener("dragenter", function () {
    drop.classList.add("is-over");
  });
  drop.addEventListener("dragover", function () {
    drop.classList.add("is-over");
  });
  drop.addEventListener("dragleave", function (event) {
    if (!drop.contains(event.relatedTarget)) drop.classList.remove("is-over");
  });
  drop.addEventListener("drop", function (event) {
    drop.classList.remove("is-over");
    if (event.dataTransfer && event.dataTransfer.files.length) add(event.dataTransfer.files);
  });

  list.addEventListener("click", function (event) {
    var retry = event.target.closest("[data-retry]");
    var remove = event.target.closest("[data-remove]");
    if (retry) {
      var again = files.find(function (f) {
        return f.id === retry.dataset.retry;
      });
      if (again) uploadOne(again);
      return;
    }
    if (remove) {
      files = files.filter(function (f) {
        if (f.id !== remove.dataset.remove) return true;
        if (f.thumb) URL.revokeObjectURL(f.thumb); // 미리보기를 놓아준다
        return false;
      });
      render();
    }
  });

  list.addEventListener("change", function (event) {
    var picker = event.target.closest("[data-kind]");
    if (!picker) return;
    var item = files.find(function (f) {
      return f.id === picker.dataset.kind;
    });
    if (item) item.kind = picker.value;
    render();
  });

  /* 여기서 그만둬도 환자는 남는다. 「작성 중 · 진료기록 없음」으로 목록에 있다. */
  later.addEventListener("click", function () {
    location.href = "/patients.html";
  });

  next.addEventListener("click", function () {
    location.href = "/guide.html"; // S1-6 판독 결과 — 아직 없다
  });

  /* 환자 머리 — 지금은 목록의 첫 행을 따른다. KEY-35 가 실제 선택과 잇는다. */
  document.addEventListener("session:ready", function () {
    var row = document.querySelector(".row[aria-current='true']");
    if (!row) return;
    var name = row.querySelector(".row__name").textContent;
    document.getElementById("p-name").textContent = name;
    document.getElementById("p-id").textContent = "차트 " + row.dataset.chart;
    document.getElementById("p-visit").textContent =
      row.querySelector(".row__meta").textContent.split(" · ").pop() + " · 오늘 진료";
  });

  render();
})();
