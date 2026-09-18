/* KEY-353 — 상단에는 의사라고 나오는데 승인·문자 수정은 잠기는 회귀.
 *
 * 원인은 두 가지였다. `shell.js` 보다 늦게 실린 `doctor.js` 가 일회성
 * `session:ready` 이벤트를 놓칠 수 있었고, 비활성 사유를 전부 권한 문제로
 * 표시했다. 서버 RBAC는 이미 의사의 수정·승인을 허용하므로 프런트 계약만 잰다. */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

test("확인한 세션은 늦게 로드된 화면도 다시 읽을 수 있다", async () => {
  const box = load("api", "session");
  const login = await box.api.login("doctor01", "valid-password");
  box.session.save(login.access_token);

  const who = await box.requireSession();

  assert.deepEqual(Array.from(who.roles), ["doctor"]);
  assert.strictEqual(box.session.current, who, "일회성 이벤트 밖에는 현재 사용자가 남지 않는다");

  box.session.clear();
  assert.equal(box.session.current, null, "로그아웃 뒤 이전 역할이 남는다");
});

test("의사는 승인 대기 안내문을 승인·반려할 수 있다", () => {
  const { doctorApprovalState } = load("api", "session", "doctor");

  assert.deepEqual(
    JSON.parse(JSON.stringify(doctorApprovalState({ roles: ["doctor"] }, { status: "APPROVAL_PENDING" }))),
    { canAct: true, why: "" },
  );
});

test("권한 없음과 아직 없음·이미 승인을 서로 다른 이유로 말한다", () => {
  const { doctorApprovalState } = load("api", "session", "doctor");

  assert.match(doctorApprovalState({ roles: ["staff"] }, { status: "APPROVAL_PENDING" }).why, /의사 권한/);
  assert.doesNotMatch(doctorApprovalState({ roles: ["doctor"] }, null).why, /권한/);
  assert.match(doctorApprovalState({ roles: ["doctor"] }, { status: "SCHEDULED_TO_SEND" }).why, /이미 승인/);
});

test("의사 단독 계정과 의사를 포함한 복수 역할 계정이 같게 판정된다 — 어드민을 더 얹었다고 막히지 않는다", () => {
  const { doctorApprovalState } = load("api", "session", "doctor");
  const pending = { status: "APPROVAL_PENDING" };

  assert.equal(doctorApprovalState({ roles: ["doctor"] }, pending).canAct, true);
  assert.equal(doctorApprovalState({ roles: ["doctor", "admin"] }, pending).canAct, true);
  assert.equal(doctorApprovalState({ roles: ["admin"] }, pending).canAct, false);
});

test("의사 화면은 늦게 등록돼도 저장된 세션을 복구하고 문자 저장 권한을 명시한다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(code, /if \(session\.current\) acceptSession\(session\.current\)/);
  assert.match(code, /canSave:\s*lock\.canSave/);
  assert.match(code, /APPROVAL_PENDING/);
});

/* 리뷰(유가은 님, c1781ae 기준)에서 잡힌 두 가지 — `canSave` 만 켜고 실제
 * 저장 배선이 빠진 것과, 반려 뒤에도 승인·반려 버튼이 풀린 채로 남는 것.
 * `browser-shim` 은 그리는 코드를 못 돌리므로(`innerHTML` 이 터진다) 여기서는
 * 원문 패턴으로 다시 풀리지 않게 고정한다. */
test("이 환자만 적용은 실제로 saveMessagePlan 을 부르고 서버 응답을 다시 반영한다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /save:\s*function\s*\(plan\)[\s\S]*?doctorApi\s*\n?\s*\.saveMessagePlan\(/,
    "wireSmsSettings 에 save 콜백이 있어야 「이 환자만 적용」이 저장 요청을 보낸다",
  );
  assert.match(code, /doctorApi\s*\n?\s*\.messagePlan\(/, "문자 설정을 불러오는 자리가 있어야 한다");
  assert.match(code, /smsAdopt\(data\)/, "서버가 돌려준 값을 화면 상태로 다시 삼아야 한다");
});

test("반려가 성공하면 전역 안내문 상태도 같이 바뀌어 승인·반려 버튼이 다시 잠긴다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /returnToStaff\(returningId, text\)\s*\.then\(function \(result\) \{[\s\S]{0,600}?guide = result/,
    "return-go 성공 콜백이 guide 를 서버 응답으로 갱신해야 renderRole() 이 최신 상태를 본다",
  );
});

/* 자체 재검토 — 승인·반려 성공 콜백의 `guide = result` 가 진료 번호만 보고
 * 있었다. `save()` 가 3차 리뷰에서 받은 것과 같은 경합이다: A 에서 승인·반려
 * 요청 → 같은 A 를 다시 열면(`load()` 가 `loadSeq` 를 올린다) `visit.visit_id`
 * 는 그대로라, 뒤집혀 온 응답이 방금 새로 불러온 `guide` 를 예전 값으로
 * 덮을 수 있었다. */
test("승인·반려 응답도 같은 환자를 다시 열면 지금 화면을 건드리지 못한다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /var approvingId = visit\.visit_id;[\s\S]{0,400}?var approvingSeq = loadSeq;/,
    "approve() 가 승인 시점의 loadSeq 를 잡아 둬야 그 사이 같은 환자를 다시 열었는지 가릴 수 있다",
  );
  assert.match(
    code,
    /var returningId = visit\.visit_id;[\s\S]{0,400}?var returningSeq = loadSeq;/,
    "return-go 가 반려 시점의 loadSeq 를 잡아 둬야 그 사이 같은 환자를 다시 열었는지 가릴 수 있다",
  );
});

/* 유가은 님 4차 리뷰(fe4cdd2c 기준) — 위 `loadSeq` 검사를 `guide = result`
 * 대입에만 걸어 두면, 응답이 뒤집혀 온 사이 같은 환자를 다시 열었을 때
 * `markDone`(목록 patch)·`openModal`(완료 모달)·실패 모달·`renderRole()` 은
 * 그대로 실행됐다. `approvedModal` 은 **지금 화면의** `visit.name` 을 읽으므로,
 * 다른 환자로 넘어간 사이 오래된 승인 모달이 뜨면 엉뚱한 환자 이름으로
 * 뜬다. 상태 대입과 같은 손잡이로 모든 부수효과를 이르게 `return` 해 끊는다. */
test("승인·반려 응답이 오래됐으면 목록 갱신·모달·오류 안내까지 전부 건너뛴다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /\.approve\(approvingId\)\s*\.then\(function \(result\) \{[\s\S]{0,600}?if \(!visit \|\| visit\.visit_id !== approvingId \|\| loadSeq !== approvingSeq\) return;[\s\S]{0,300}?guide = result;[\s\S]{0,150}?markDone\(approvingId,[\s\S]{0,200}?openModal\(approvedModal\(result\)\)/,
    "approve() 성공 콜백이 이르게 return 한 뒤에만 guide 대입·markDone·openModal 을 실행해야 한다",
  );
  assert.match(
    code,
    /\.approve\(approvingId\)[\s\S]{0,1000}?\.catch\(function \(error\) \{[\s\S]{0,300}?if \(!visit \|\| visit\.visit_id !== approvingId \|\| loadSeq !== approvingSeq\) return;[\s\S]{0,150}?renderRole\(\);[\s\S]{0,80}?openModal\(failedModal/,
    "approve() 실패 콜백도 오래된 응답이면 renderRole·실패 모달을 실행하지 않아야 한다",
  );
  assert.match(
    code,
    /\.returnToStaff\(returningId, text\)\s*\.then\(function \(result\) \{[\s\S]{0,600}?if \(!visit \|\| visit\.visit_id !== returningId \|\| loadSeq !== returningSeq\) return;[\s\S]{0,400}?guide = result;[\s\S]{0,150}?markDone\(returningId,/,
    "return-go 성공 콜백이 이르게 return 한 뒤에만 guide 대입·markDone 을 실행해야 한다",
  );
  assert.match(
    code,
    /\.returnToStaff\(returningId, text\)[\s\S]{0,1300}?\.catch\(function \(\) \{[\s\S]{0,500}?if \(!visit \|\| visit\.visit_id !== returningId \|\| loadSeq !== returningSeq\) return;[\s\S]{0,150}?target\.disabled = false;/,
    "return-go 실패 콜백도 오래된 응답이면 버튼 재활성화·오류 안내를 실행하지 않아야 한다",
  );
});

/* 2차 리뷰(유가은 님, 51fe39f 기준)에서 잡힌 세 가지 — 문자 설정을 실제로
 * 받기 전에도 저장이 열려 있던 것, 저장이 도는 중에도 재렌더링으로 버튼이
 * 다시 눌리던 것, 환자를 바꿔도 앞 환자의 저장 안내가 남던 것.
 *
 * 「smsPlanState·smsSaving → canSave」 판정 자체는 `guide-view.js` 의
 * `smsSaveLock` 으로 뺐다(iljun-sys 님 리뷰) — 그 함수의 동작은
 * `sms-plan-saved.test.js` 가 실제로 불러서 잰다. 여기서는 doctor.js 가 그
 * 함수에 **무엇을 넘기는지**만 원문으로 고정한다. */
test("문자 설정을 실제로 받아 오기 전(로딩·실패)에는 저장을 잠근다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(code, /var smsPlanState = "loading"/, "환자마다 불러오기 상태를 loading 으로 시작해야 한다");
  assert.match(
    code,
    /var lock = smsSaveLock\(\s*roleEditable,\s*smsPlanState,\s*smsSaving,/,
    "guideSmsPlan 이 smsSaveLock 에 roleEditable·smsPlanState·smsSaving 을 그대로 넘겨야 한다",
  );
  const messagePlanBlock = code.slice(code.indexOf(".messagePlan("));
  assert.match(
    messagePlanBlock,
    /\.messagePlan\([\s\S]{0,20}\)\s*\.then\(function \(data\) \{[\s\S]{0,80}?smsPlanState = "ready"/,
    "messagePlan 응답이 와야 ready 로 열린다",
  );
  assert.match(
    messagePlanBlock,
    /\.catch\(function \(\) \{[\s\S]{0,600}?smsPlanState = "failed"/,
    "messagePlan 이 실패하면 failed 로 남아 저장이 잠긴 채여야 한다",
  );
});

test("저장이 도는 동안에는 재렌더링돼도 버튼이 다시 활성화되지 않는다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /save:\s*function\s*\(plan\)\s*\{[\s\S]{0,1200}?smsSaving = true;[\s\S]{0,120}?renderPanel\(\);/,
    "save 콜백이 smsSaving 을 켠 뒤에 renderPanel() 을 불러야 새로 그려진 버튼도 잠긴다",
  );
  assert.match(code, /smsSaving = false;[\s\S]{0,300}?smsAdopt\(data\)/, "성공하면 smsSaving 을 풀어야 다음 저장이 된다");
  assert.match(code, /smsSaving = false;[\s\S]{0,300}?저장하지 못했습니다/, "실패해도 smsSaving 을 풀어야 다시 시도할 수 있다");
});

/* 3차 리뷰(유가은 님, 34c2b683 기준)에서 잡힌 것 — 같은 환자를 다시 열어도
 * `wantedId` 는 똑같아서, A 저장 → B 로 이동 → A 로 복귀 → 재저장 순서에서
 * 응답이 뒤집히면 오래된 응답이 새 값을 덮을 수 있었다. */
test("환자를 다시 열면 그 전 저장 요청의 응답은 지금 화면을 건드리지 못한다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /save:\s*function\s*\(plan\)[\s\S]{0,40}?var wantedId[\s\S]{0,600}?var wantedSeq = loadSeq;/,
    "save 가 저장 시점의 loadSeq 를 잡아 둬야 그 사이 같은 환자를 다시 열었는지 가릴 수 있다",
  );
  assert.match(
    code,
    /\.then\(function \(data\) \{\s*if \(!visit \|\| visit\.visit_id !== wantedId \|\| loadSeq !== wantedSeq\) return;/,
    "성공 콜백이 loadSeq 도 같이 봐야 오래된 응답이 smsAdopt 로 최신 값을 덮지 않는다",
  );
  assert.match(
    code,
    /\.catch\(function \(err\) \{\s*if \(!visit \|\| visit\.visit_id !== wantedId \|\| loadSeq !== wantedSeq\) return;/,
    "실패 콜백도 loadSeq 를 봐야 오래된 실패가 새 저장의 smsSaving 을 잘못 풀지 않는다",
  );
});

test("환자를 바꾸면 저장 안내·불러오기 상태를 새로 잰다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /smsForget\(\);[\s\S]{0,300}?smsSaying = "";[\s\S]{0,60}?smsPlanState = "loading";[\s\S]{0,60}?smsSaving = false;/,
    "load() 가 smsForget 뒤에 smsSaying·smsPlanState·smsSaving 을 모두 초기화해야 앞 환자의 안내가 안 남는다",
  );
});

/* 자체 재검토 — `#say` 는 `wireGuideEditing`(고치기)·`wireSmsSettings`(문자
 * 설정) 가 함께 쓰는 결과 알림 줄이다. 위 시험이 잡는 `smsSaying` 과 같은
 * 이유로, 환자 전환 시 이것도 비워야 한다. */
test("환자를 바꾸면 고치기·문자 설정의 결과 알림 줄도 비운다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /smsForget\(\);[\s\S]{0,600}?el\("say"\)\)\s*el\("say"\)\.textContent = "";/,
    'load() 가 smsForget·smsSaying 등을 초기화한 뒤 "#say" 도 비워야 앞 환자의 "고쳤습니다"가 안 남는다',
  );
});

/* 4차 점검(2heej 님 요청, 원 리뷰어 부재 시 자체 재검토) — 저장이
 * `GUIDE_NOT_PENDING`(다른 곳에서 이미 승인·반려됨)으로 막혀도 `guide` 를
 * 갱신하지 않아, `roleEditable` 이 옛 상태를 본 채 계속 열려 있었다. 승인·
 * 반려 콜백이 `guide = result` 로 하는 것과 같은 것을 저장 실패에도 해야
 * 원장님이 같은 충돌에 몇 번이고 다시 걸리지 않는다. */
test("저장이 GUIDE_NOT_PENDING 으로 막히면 안내문을 다시 읽어 실제 상태로 되돌린다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /var isConflict = err && err\.code === "GUIDE_NOT_PENDING";[\s\S]{0,1000}?doctorApi\s*\n?\s*\.guide\(wantedId\)\s*\.then\(function \(fresh\) \{[\s\S]{0,200}?guide = fresh;/,
    "GUIDE_NOT_PENDING 실패 뒤에 doctorApi.guide 를 다시 불러 전역 guide 를 서버 응답으로 갱신해야 한다",
  );
});

/* 자체 재검토 — 위 재조회가 끝나기 전에 `smsSaving` 을 풀면, 화면은 옛
 * `guide.status` 를 그대로 보고 있어 「승인된 뒤에는 고칠 수 없습니다」 문구
 * 옆에서 저장 버튼이 다시 눌리는 채로 선다. 재조회가 끝난 뒤(성공·실패 모두)
 * 에만 풀어야 한다. 목록 줄도 다른 곳에서 이미 승인·반려됐다는 뜻이니
 * `visit:changed` 로 다시 물어야 한다(승인·반려 성공과 같은 이유). */
test("GUIDE_NOT_PENDING 재조회가 끝나기 전에는 저장 잠금을 풀지 않고, 끝나면 목록도 다시 묻는다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /if \(!isConflict\) smsSaving = false;/,
    "충돌이 아닌 일반 실패만 즉시 smsSaving 을 풀어야 한다",
  );
  assert.match(
    code,
    /\.guide\(wantedId\)\s*\.then\(function \(fresh\) \{[\s\S]{0,300}?guide = fresh;[\s\S]{0,120}?smsSaving = false;[\s\S]{0,500}?visit:changed/,
    "재조회 성공 뒤에 smsSaving 을 풀고 목록에도 visit:changed 로 다시 물어야 한다",
  );
  assert.match(
    code,
    /\.guide\(wantedId\)[\s\S]{0,800}?\.catch\(function \(\) \{[\s\S]{0,400}?smsSaving = false;/,
    "재조회 자체가 실패해도 smsSaving 을 풀어야 다음 시도가 막히지 않는다",
  );
});
