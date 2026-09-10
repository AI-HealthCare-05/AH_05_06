/* 화면 목록표 — 와이어프레임 2.3.1 의 64프레임.
   docs/wireframes/*.html 의 data-screen-label 에서 뽑았다.

     level   지금 수준    1 완전 구현 · 2 일부 동작 · 3 화면 없음/잠김
     target  이번 주 목표
     url     1·2단계일 때 실제 화면 주소
     blocker 무엇이 막고 있나 (B1~B8 은 구조 분석 보고서의 차단 항목 번호)
     role    3단계일 때 이 화면이 할 일

   **level 은 지금 실제 상태다. 목표를 여기 적지 않는다.**
   3단계 화면에는 동작하지 않는 버튼을 두지 않고 데이터도 읽지 않는다. */
var FRAMES = [
  {"id": "L-1", "area": "medic", "name": "로그인 (기본)", "level": 1, "target": 1, "url": "/login.html"},
  {"id": "L-2", "area": "medic", "name": "로그인 오류", "level": 1, "target": 1, "url": "/login.html"},
  {"id": "L-3", "area": "medic", "name": "첫 로그인 — 비밀번호 바꾸기", "level": 1, "target": 1, "url": "/password.html"},
  {"id": "S1-1", "area": "medic", "name": "할 일 없음 · 환자 0명", "level": 1, "target": 1, "url": "/patients.html"},
  {"id": "S1-2", "area": "medic", "name": "환자 등록 — 찾아서 고른다", "level": 1, "target": 1, "url": "/patients.html"},
  {"id": "S1-3", "area": "medic", "name": "환자 등록 — 없으면 새로 만든다", "level": 1, "target": 1, "url": "/patients.html"},
  {"id": "S1-4", "area": "medic", "name": "환자 카드 · 기본정보", "level": 2, "target": 2, "url": "/patients.html", "blocker": "발송 이력 · 지난 안내문 열기 없음"},
  {"id": "S1-5", "area": "medic", "name": "진료기록 업로드", "level": 1, "target": 1, "url": "/ocr-review.html"},
  {"id": "S1-6", "area": "medic", "name": "판독 확인 — 상태 ① 모두 읽힘", "level": 2, "target": 2, "url": "/ocr-review.html", "blocker": "확인 항목이 처방별로 안 갈린다 — 무엇을 여쭐지 정하는 자리(D2-3)가 없어 지금은 다섯을 다 여쭙는다"},
  {"id": "S1-7", "area": "medic", "name": "판독 확인 — 상태 ② 못 읽은 항목이 있을 때", "level": 2, "target": 2, "url": "/ocr-review.html", "blocker": "「이번 미시행」이 서버에 안 담긴다(S1-9 와 같은 자리) — 못 읽은 줄의 「직접 입력」은 이제 실제로 저장된다"},
  {"id": "S1-8", "area": "medic", "name": "판독 확인 — 상태 ③ 같은 항목이 두 곳에 있을 때", "level": 2, "target": 2, "url": "/ocr-review.html", "blocker": "후보 테이블을 채우는 코드가 없어 항상 빈 목록"},
  {"id": "S1-9", "area": "medic", "name": "판독 확인 — 상태 ④ 이번에 검사를 안 했을 때 가장 흔하다", "level": 2, "target": 2, "url": "/ocr-review.html", "blocker": "「이번 미시행」 버튼은 이제 그려지는데 눌러도 안 담긴다 — UpdateOcrFieldRequest(StrictModel)에 field_status 칸이 없어 PATCH 가 422 로 떨어진다"},
  {"id": "S1-10", "area": "medic", "name": "안내문 생성 실패", "level": 3, "target": 3, "blocker": "화면 없음. 목록에 실패 상태도 안 뜸", "role": "안내문 생성이 실패했을 때 다시 만들거나 약을 골라 기본 안내문을 만든다"},
  {"id": "S1-11", "area": "medic", "name": "스탭 확인 — 복약지도", "level": 2, "target": 1, "url": "/patients.html", "blocker": "탭은 열려 있고 보기·고치기·의사에게 넘기기가 다 된다. 다만 본문이 평문 한 덩이다 — 「오늘 진료 요약」·「나의 목표」(시작·지금·목표) 절이 없고 약별 「왜 드시나요」·「먹는 방법」이 구조로 안 나뉜다 (`_medication_body`). 같은 본문을 환자 쪽에서 보는 P2-1 도 같은 이유로 2 다"},
  {"id": "S1-12", "area": "medic", "name": "스탭 확인 — 주의사항", "level": 2, "target": 1, "url": "/patients.html", "blocker": "탭은 열려 있고 보기·고치기·넘기기가 다 된다. 다만 주의 문구가 평문 한 덩이라 원문의 항목 구조(증상별 묶음)가 없다 — 🚨 응급만 따로 잠긴 절로 선다"},
  {"id": "S1-13", "area": "medic", "name": "스탭 확인 — 생활지도", "level": 2, "target": 1, "url": "/patients.html", "blocker": "탭은 열려 있고 보기·고치기·넘기기가 다 된다. 다만 생활지도가 단락 하나다 — 원문의 네 축(수면·뼈건강·운동·통증)·「이번 4주 챌린지」·「왜 이 세 가지인가요」 구조가 없고, D2 챌린지 목록 설정도 화면에 없다. 구조화 소스가 없어 서버가 지어내지 않는다(`patient_links.py`)"},
  {"id": "S1-14", "area": "medic", "name": "문자 설정 — 확인 · 재진", "level": 2, "target": 2, "url": "/patients.html", "blocker": "재진 안내 발송 자리가 없다 · 소진 예정일을 화면이 못 받아 「처방일수를 확인하면 셈합니다」로 뜬다 · 의원 템플릿(D2-5) 없음"},
  {"id": "D1-1", "area": "medic", "name": "확인 대기 + 안내문 — 미리보기 하나 · 고치기 하나", "level": 1, "target": 1, "url": "/doctor.html"},
  {"id": "D1-2", "area": "medic", "name": "주의사항 보기", "level": 1, "target": 1, "url": "/doctor.html"},
  {"id": "D1-3", "area": "medic", "name": "생활지도 보기", "level": 1, "target": 1, "url": "/doctor.html"},
  {"id": "D1-4", "area": "medic", "name": "문자 설정 — 나갈 문자 확인", "level": 2, "target": 2, "url": "/patients.html", "blocker": "소진 임박 예정일이 안 뜬다(처방일수가 안 와 「처방일수를 확인하면 셈합니다」) · 재진 안내 「지금 발송」·「템플릿으로 저장」 없음 · /doctor.html 의 같은 탭은 껍데기다 — guideSmsPlan 이 없어 환자값·저장 없이 「이 환자만 적용」이 눌리기만 한다"},
  {"id": "D1-5", "area": "medic", "name": "승인 확인 모달", "level": 1, "target": 1, "url": "/doctor.html"},
  {"id": "D1-6", "area": "medic", "name": "현황", "level": 2, "target": 2, "url": "/patients.html", "blocker": "하단 [링크 무효화]·[재발송] 없음 · 「안 나간 문자 전부 보기 ↗」(S2-3) 링크 없음 · 발송 줄에 열람 진도(「발송 완료 · 19:14 열람 · 5장 중 2장」)가 안 붙는다"},
  {"id": "D1-7", "area": "medic", "name": "현황 · 못 보냈을 때 + 🔔 알림 패널", "level": 3, "target": 3, "blocker": "🔔 알림 패널 없음(모든 화면에서 aria-disabled) · ⚠ 실패 줄이 안 펼쳐진다 — 실패 사유·번호 수정·[수정 후 재발송]·[링크 무효화]가 없다. 발송기 자체는 붙었다(KEY-249)", "role": "발송 실패를 확인하고 다시 보낸다"},
  {"id": "S2-1", "area": "medic", "name": "환자 관리 — 이탈을 잡는 자리", "level": 2, "target": 2, "url": "/manage.html", "blocker": "재진 안내 발송 없음 · 3회 연속 미열람은 아직 못 뜬다 — 발송기는 붙었지만(KEY-249) {링크}를 못 채워 SENT 줄이 안 쌓인다"},
  {"id": "S2-2", "area": "medic", "name": "환자 이력 모달", "level": 2, "target": 2, "url": "/manage.html", "blocker": "「자세히 보기」(A1-7) 없음"},
  {"id": "S2-3", "area": "medic", "name": "발송 예정", "level": 2, "target": 2, "url": "/manage.html", "blocker": "즉시 발송 · 문자 충전 없음 — 시각 변경(KEY-257)과 발송기(KEY-249)는 붙었다. 다만 발송기가 {링크}·{예약링크}를 못 채워 그 변수가 든 문구는 발송 직전 FAILED 로 끝난다"},
  {"id": "S2-4", "area": "medic", "name": "발송 이력", "level": 2, "target": 2, "url": "/manage.html", "blocker": "재승인(다시 보내기) 없음 — 발송기는 붙었다(KEY-249). 다만 {링크}를 못 채워 실제 SENT 줄은 아직 안 쌓인다"},
  {"id": "D2-1", "area": "medic", "name": "안내문 — 처방 한 장", "level": 2, "target": 2, "url": "/settings.html", "blocker": "고칠 문구가 약 단위가 아니라 처방 세트 단위다 — DoctorGuideCopy 가 (세트, 갈래)로 잡혀 약마다 다른 문구를 못 준다"},
  {"id": "D2-2", "area": "medic", "name": "안내문 고치기 — 원본 ↔ 원장님 문구", "level": 2, "target": 2, "url": "/settings.html", "blocker": "고친 글이 안내문에서 어떻게 보이는지 이 화면에서 못 본다 (KEY-258 · #252 리뷰 중). 안내문 생성이 고친 문구를 읽는 것은 KEY-243 이 붙였다"},
  {"id": "D2-3", "area": "medic", "name": "처방", "level": 2, "target": 1, "url": "/settings.html", "blocker": "안내문 미리보기는 D2-1·D2-2 몫이라 아직 없다"},
  {"id": "D2-4", "area": "medic", "name": "검사 기준선", "level": 2, "target": 2, "url": "/settings.html", "blocker": "의원 「판독 키워드」를 판독이 쓰기 시작했다(KEY-245) — 다만 기준선 이름이 내장 정규식에 걸리는 항목만 등록돼(build_lab_keywords) 정규식이 모르는 이름은 그대로 안 잡힌다"},
  {"id": "D2-5", "area": "medic", "name": "문자 문구", "level": 2, "target": 2, "url": "/settings.html", "blocker": "{링크}·{예약링크}를 채우는 자리가 없다 — 발송기는 여기서 정한 문구로 보내지만(KEY-249) 그 변수가 남으면 발송 직전 FAILED 로 끝난다. {예약링크}는 의원 정보(A1-4)도 있어야 채워진다"},
  {"id": "P1-1", "area": "patient", "name": "링크로 들어옴 — 인증번호 보내기", "level": 3, "target": 1, "blocker": "B3 실제 OTP 발송기가 없다(고정 OTP 좁은문이 닫히면 `UnavailableOtpDelivery` 503) · **그리고 토큰이 화면에 안 들어간다** — 여는 쪽은 모두 `#t=` 로 주는데(`doctor.js`·`checkin.js`) `otp.html` 은 비목업에서 `?token=` 만 읽어, 실서버에서 「본인 확인 열기」를 누르면 「일시적인 오류가 생겼어요」로 떨어진다", "role": "환자가 안내문 링크로 들어와 인증번호를 받는다"},
  {"id": "P1-2", "area": "patient", "name": "인증번호 입력", "level": 2, "target": 2, "url": "/checkin.html", "blocker": "B3 인증번호를 못 받는다 — OTP 발송이 UnavailableOtpDelivery 라 실제 문자로는 안 나가고, 고정 OTP 좁은문이 열렸을 때만 들어간다. 문자 발송기(KEY-249)는 OTP 쪽에 안 붙었다"},
  {"id": "P1-3", "area": "patient", "name": "폴백 (링크 만료 · 폐기)", "level": 3, "target": 3, "blocker": "생년월일·전화번호 재확인 폼이 없다 · 「새 링크 요청하기」가 **거짓 성공**이다 — `patient_links` 가 새 토큰을 만들어 해시만 쓰고 원문을 아무 데도 안 넘겨(발송 호출 없음) 환자는 새 링크를 못 받는데 화면은 202 를 받는다 · 하루 3회 제한 없음", "role": "만료·폐기된 링크에서 본인 확인 후 다시 받는다"},
  {"id": "P1-4", "area": "patient", "name": "5회 초과 차단", "level": 2, "target": 2, "url": "/checkin.html", "blocker": "병원 문의 연결 없음"},
  {"id": "P2-1", "area": "patient", "name": "복약지도 자궁내막증", "level": 2, "target": 1, "url": "/guide.html", "blocker": "실서버로는 단순 텍스트. 구조화 화면은 목업 전용"},
  {"id": "P3-1", "area": "patient", "name": "주의사항 자궁내막증 (비잔)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "같음. 문의하기는 준비 안내만"},
  {"id": "P4-1", "area": "patient", "name": "생활관리 (자궁내막증 세트)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "같음"},
  {"id": "P5-1", "area": "patient", "name": "복약 현황 (자궁내막증 · 비잔 1개)", "level": 2, "target": 2, "url": "/guide.html", "blocker": "예약하기·문의하기 버튼 없음 — 의원 예약 URL 설정도 연락처 종점도 없다(KEY-236) · 진행률(N일째 · 남은 일수 · %)은 판독 확정본이 있어야 나온다 · 오류 신고는 목업 전용(P9)"},
  {"id": "P6-1", "area": "patient", "name": "챗봇 (의료진 문의 유형)", "level": 2, "target": 2, "url": "/guide.html", "blocker": "문의하기 연결 없음 — 병원 연락처 종점이 계약에 없어 그 버튼은 잠가 두었다 (KEY-236). 도움됨·안 됨은 실제로 저장된다"},
  {"id": "P2-2", "area": "patient", "name": "복약지도 다낭성난소증후군 (야즈)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "실서버로는 단순 텍스트. 구조화 화면은 목업 전용"},
  {"id": "P3-2", "area": "patient", "name": "주의사항 다낭성난소증후군 (야즈)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "같음. 문의하기는 준비 안내만"},
  {"id": "P4-2", "area": "patient", "name": "생활관리 (다낭성난소증후군 세트)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "같음"},
  {"id": "P5-2", "area": "patient", "name": "복약 현황 (다낭성난소증후군 · 야즈)", "level": 2, "target": 2, "url": "/guide.html", "blocker": "예약하기·문의하기 버튼 없음(KEY-236) · 진행률은 판독 확정본이 있어야 나온다 · 여러 약 중 「먼저 떨어져요」 표시가 없다 — 서버가 약 하나만 골라 내려준다 · 오류 신고는 목업 전용(P9)"},
  {"id": "P6-2", "area": "patient", "name": "챗봇 (긴급 안내 유형)", "level": 2, "target": 2, "url": "/guide.html", "blocker": "같음"},
  {"id": "P1-5", "area": "patient", "name": "확인 문자로 들어옴 (회차 표시)", "level": 3, "target": 3, "blocker": "인증 시작 화면(otp.html)은 생겼지만 회차 상자·부제를 안 그린다 — /patient-auth/context 응답에 회차 값이 없다. 확인 문자로 이 화면에 들어오는 링크를 만드는 코드도 없다(B4)", "role": "확인 문자로 들어와 회차를 보고 인증한다"},
  {"id": "P7-1", "area": "patient", "name": "확인 + 기록 (기본)", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 이 화면으로 가는 링크를 만드는 코드가 없음"},
  {"id": "P7-2", "area": "patient", "name": "「먹고 있는데 불편해요」 펼침", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 · 응급 블록은 목업 전용"},
  {"id": "P7-3", "area": "patient", "name": "「가끔 놓쳐요」 펼침", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4"},
  {"id": "P7-4", "area": "patient", "name": "「불편해서 중단」 펼침", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 · 문의하기 준비 안내만"},
  {"id": "P7-5", "area": "patient", "name": "「좋아져서 중단」 펼침", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 · 문의하기 준비 안내만"},
  {"id": "P7-6", "area": "patient", "name": "저장 완료", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 · 완료 화면 네 칸이 서버 DTO 에서 항상 비어 있음"},
  {"id": "P8-1", "area": "patient", "name": "PDF 저장 · 범위 선택", "level": 3, "target": 3, "blocker": "PDF 생성 기능 없음", "role": "저장할 안내문 범위를 고른다"},
  {"id": "P8-2", "area": "patient", "name": "미리보기 · 저장", "level": 3, "target": 3, "blocker": "PDF 렌더링 · 내려받기 없음", "role": "PDF 를 미리 보고 저장한다"},
  {"id": "P9", "area": "patient", "name": "피드백 · 오류 신고", "level": 3, "target": 3, "blocker": "신고 화면이 목업에만 있다 — 저장은 POST /patient-feedback 으로 실제로 되고 관리 화면도 있는데, 실서버 안내문에는 신고 버튼이 안 그려진다", "role": "안내문의 잘못된 내용을 신고한다"},
  {"id": "A1-1", "area": "admin", "name": "직원", "level": 2, "target": 2, "url": "/admin.html", "blocker": "검색 칸이 없다 — 목록은 GET /admin/staffs 로 실제로 뜬다(KEY-321)", "role": "직원 목록을 보고 검색한다"},
  {"id": "A1-2", "area": "admin", "name": "직원 추가", "level": 1, "target": 1, "url": "/admin.html", "role": "직원을 등록한다 — 초기 비밀번호는 관리자가 정해 주고 첫 로그인에서 본인이 바꾼다"},
  {"id": "A1-3", "area": "admin", "name": "직원 수정", "level": 3, "target": 3, "blocker": "직원 수정 · 비밀번호 재설정 API 없음", "role": "역할·재직 상태를 바꾸고 비밀번호를 재설정한다"},
  {"id": "A1-4", "area": "admin", "name": "의원 정보", "level": 3, "target": 2, "blocker": "Hospital 모델은 있음. GET /hospital 조회 API 없음", "role": "의원 정보를 수정한다"},
  {"id": "A1-5", "area": "admin", "name": "문자 이 프로그램이 멈추는 유일한 자리", "level": 3, "target": 3, "blocker": "SMS 잔량 조회 · 충전 API 없음", "role": "문자 잔량을 확인하고 충전한다"},
  {"id": "A1-6", "area": "admin", "name": "전체 로그", "level": 3, "target": 3, "blocker": "감사 로그 모델 · 조회 API 없음", "role": "시스템 감사 로그를 조회한다"},
  {"id": "A1-7", "area": "admin", "name": "한 건 시간 흐름", "level": 3, "target": 3, "blocker": "감사 로그 모델 · 조회 API 없음", "role": "진료 한 건의 처리 흐름을 시간순으로 본다"}
];

var FRAME_AREAS  = { medic: "의료진", patient: "환자", admin: "어드민" };
var FRAME_LEVELS = { 1: "완전 구현", 2: "일부 동작", 3: "화면 없음" };

/* **안내 화면을 씌울 대상** — KEY-234 인수조건 ④ 「핵심 데모 화면에는 적용하지 않는다」.

   지금 화면이 없어도(level 3) 곧 올라갈 프레임(target < 3)은 제외한다 —
   P1-1(링크 진입 인증)·A1-1(직원)·A1-4(의원 정보) 셋이다. 씌우면 같은 주에
   두 번 만들게 되고, 시연 대본이 안내 화면을 지난다.

   여기 S1-11~13(스탭 확인)이 예시로 적혀 있었는데 **지금은 아니다.** KEY-235
   로 다시 재면서 그 셋은 level 2 가 되어 `level === 3` 에 애초에 안 걸린다
   (이희진 님 `#254`). 예시가 표와 갈리면 다음 사람이 표 대신 이 글을 믿는다 —
   그래서 아래 검사가 이 세 번호를 표에 대고 잰다. */
function needsGuideScreen(frame) {
  return frame.level === 3 && frame.target === 3;
}

function frameById(id) {
  for (var i = 0; i < FRAMES.length; i++) if (FRAMES[i].id === id) return FRAMES[i];
  return null;
}
