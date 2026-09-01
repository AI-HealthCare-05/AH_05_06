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
  {"id": "S1-5", "area": "medic", "name": "진료기록 업로드", "level": 1, "target": 1, "url": "/patients.html"},
  {"id": "S1-6", "area": "medic", "name": "판독 확인 — 상태 ① 모두 읽힘", "level": 2, "target": 1, "url": "/ocr-review.html", "blocker": "③이전 값 유지 · ④확인 항목은 서버에 자리가 없다"},
  {"id": "S1-7", "area": "medic", "name": "판독 확인 — 상태 ② 못 읽은 항목이 있을 때", "level": 2, "target": 1, "url": "/ocr-review.html", "blocker": "B2 못 읽은 항목이 레코드로 안 남아 「직접 입력」이 안 뜬다"},
  {"id": "S1-8", "area": "medic", "name": "판독 확인 — 상태 ③ 같은 항목이 두 곳에 있을 때", "level": 2, "target": 2, "url": "/ocr-review.html", "blocker": "후보 테이블을 채우는 코드가 없어 항상 빈 목록"},
  {"id": "S1-9", "area": "medic", "name": "판독 확인 — 상태 ④ 이번에 검사를 안 했을 때 가장 흔하다", "level": 2, "target": 1, "url": "/ocr-review.html", "blocker": "field_status 미지원으로 「이번 미시행」 버튼이 안 뜸"},
  {"id": "S1-10", "area": "medic", "name": "안내문 생성 실패", "level": 3, "target": 3, "blocker": "화면 없음. 목록에 실패 상태도 안 뜸", "role": "안내문 생성이 실패했을 때 다시 만들거나 약을 골라 기본 안내문을 만든다"},
  {"id": "S1-11", "area": "medic", "name": "스탭 확인 — 복약지도", "level": 3, "target": 1, "blocker": "안내문 탭이 tab--later 로 잠김", "role": "스탭이 복약지도를 확인하고 고쳐 의사에게 넘긴다"},
  {"id": "S1-12", "area": "medic", "name": "스탭 확인 — 주의사항", "level": 3, "target": 1, "blocker": "주의사항 탭이 잠김", "role": "스탭이 주의사항을 확인하고 고쳐 의사에게 넘긴다"},
  {"id": "S1-13", "area": "medic", "name": "스탭 확인 — 생활지도", "level": 3, "target": 1, "blocker": "생활지도 탭이 잠김", "role": "스탭이 생활지도를 확인하고 고쳐 의사에게 넘긴다"},
  {"id": "S1-14", "area": "medic", "name": "문자 설정 — 확인 · 재진", "level": 3, "target": 3, "blocker": "화면 · API · 발송 이력 테이블 모두 없음", "role": "회차별 발송 시각과 문구를 설정한다"},
  {"id": "D1-1", "area": "medic", "name": "확인 대기 + 안내문 — 미리보기 하나 · 고치기 하나", "level": 1, "target": 1, "url": "/doctor.html"},
  {"id": "D1-2", "area": "medic", "name": "주의사항 보기", "level": 1, "target": 1, "url": "/doctor.html"},
  {"id": "D1-3", "area": "medic", "name": "생활지도 보기", "level": 1, "target": 1, "url": "/doctor.html"},
  {"id": "D1-4", "area": "medic", "name": "문자 설정 — 나갈 문자 확인", "level": 3, "target": 3, "blocker": "문자 설정 API 없음", "role": "승인 전에 환자에게 나갈 문자를 확인한다"},
  {"id": "D1-5", "area": "medic", "name": "승인 확인 모달", "level": 1, "target": 1, "url": "/doctor.html"},
  {"id": "D1-6", "area": "medic", "name": "현황", "level": 3, "target": 3, "blocker": "발송·열람·응답 타임라인 본문 없음", "role": "승인 뒤 발송·열람·응답을 시간순으로 본다"},
  {"id": "D1-7", "area": "medic", "name": "현황 · 못 보냈을 때 + 🔔 알림 패널", "level": 3, "target": 3, "blocker": "발송 실패 상세 · 재시도 · 알림 패널 없음", "role": "발송 실패를 확인하고 다시 보낸다"},
  {"id": "S2-1", "area": "medic", "name": "환자 관리 — 이탈을 잡는 자리", "level": 2, "target": 1, "url": "/manage.html", "blocker": "전체 이력 보기(S2-2) · 재진 안내 발송 없음 · 3회 연속 미열람은 발송기가 있어야 뜬다"},
  {"id": "S2-2", "area": "medic", "name": "환자 이력 모달", "level": 2, "target": 1, "url": "/manage.html", "blocker": "「5장 중 3장」 열람 진도 없음 — 열람 이벤트에 어느 장인지가 안 남는다 · 「자세히 보기」(A1-7) 없음"},
  {"id": "S2-3", "area": "medic", "name": "발송 예정", "level": 2, "target": 1, "url": "/manage.html", "blocker": "시각 변경 · 즉시 발송 · 문자 충전 없음 — 문자를 보내는 발송기 자체가 없다"},
  {"id": "S2-4", "area": "medic", "name": "발송 이력", "level": 2, "target": 1, "url": "/manage.html", "blocker": "재승인(다시 보내기) 없음 — 문자를 보내는 발송기 자체가 없다"},
  {"id": "D2-1", "area": "medic", "name": "안내문 — 약 하나에 한 장", "level": 3, "target": 3, "blocker": "병원별 안내문 설정 모델 · API 없음", "role": "약마다 기본 안내문을 관리한다"},
  {"id": "D2-2", "area": "medic", "name": "안내문 고치기 — 원본 ↔ 원장님 문구", "level": 3, "target": 3, "blocker": "안내문 설정 모델 · API 없음", "role": "원본과 원장님 문구를 비교해 고친다"},
  {"id": "D2-3", "area": "medic", "name": "처방", "level": 2, "target": 1, "url": "/settings.html", "blocker": "안내문 미리보기는 D2-1·D2-2 몫이라 아직 없다"},
  {"id": "D2-4", "area": "medic", "name": "검사 기준선", "level": 2, "target": 1, "url": "/settings.html", "blocker": "D1 「나의 목표」가 이 값을 아직 안 읽는다 · 판독이 「판독 키워드」로 항목을 찾지 않는다"},
  {"id": "D2-5", "area": "medic", "name": "문자 문구", "level": 2, "target": 1, "url": "/settings.html", "blocker": "정한 문구로 실제 발송하는 발송기가 없다 · {예약링크}는 의원 정보(A1-4)가 있어야 채워진다"},
  {"id": "P1-1", "area": "patient", "name": "링크로 들어옴 — 인증번호 보내기", "level": 3, "target": 1, "blocker": "B3 OTP 발송 구현체가 없어 항상 503. 진입 화면도 없음", "role": "안내문 링크로 들어와 인증번호를 받는다"},
  {"id": "P1-2", "area": "patient", "name": "인증번호 입력", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B3 인증번호를 받을 수 없음"},
  {"id": "P1-3", "area": "patient", "name": "폴백 (링크 만료 · 폐기)", "level": 3, "target": 3, "blocker": "생년월일 재확인 · 링크 재발송 폼 없음", "role": "만료·폐기된 링크에서 본인 확인 후 다시 받는다"},
  {"id": "P1-4", "area": "patient", "name": "5회 초과 차단", "level": 2, "target": 2, "url": "/checkin.html", "blocker": "병원 문의 연결 없음"},
  {"id": "P2-1", "area": "patient", "name": "복약지도 자궁내막증", "level": 2, "target": 1, "url": "/guide.html", "blocker": "실서버로는 단순 텍스트. 구조화 화면은 목업 전용"},
  {"id": "P3-1", "area": "patient", "name": "주의사항 자궁내막증 (비잔)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "같음. 문의하기는 준비 안내만"},
  {"id": "P4-1", "area": "patient", "name": "생활관리 (자궁내막증 세트)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "같음"},
  {"id": "P5-1", "area": "patient", "name": "복약 현황 (자궁내막증 · 비잔 1개)", "level": 3, "target": 3, "blocker": "복약 이행 기록 모델 · 집계 API 없음", "role": "복약 이행률과 챌린지 달성을 본다"},
  {"id": "P6-1", "area": "patient", "name": "챗봇 (의료진 문의 유형)", "level": 2, "target": 2, "url": "/guide.html", "blocker": "문의하기 연결 없음. 피드백은 정적 텍스트"},
  {"id": "P2-2", "area": "patient", "name": "복약지도 다낭성난소증후군 (야즈)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "실서버로는 단순 텍스트. 구조화 화면은 목업 전용"},
  {"id": "P3-2", "area": "patient", "name": "주의사항 다낭성난소증후군 (야즈)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "같음. 문의하기는 준비 안내만"},
  {"id": "P4-2", "area": "patient", "name": "생활관리 (다낭성난소증후군 세트)", "level": 2, "target": 1, "url": "/guide.html", "blocker": "같음"},
  {"id": "P5-2", "area": "patient", "name": "복약 현황 (다낭성난소증후군 · 야즈)", "level": 3, "target": 3, "blocker": "복약 이행 기록 모델 · 집계 API 없음", "role": "복약 이행률과 챌린지 달성을 본다"},
  {"id": "P6-2", "area": "patient", "name": "챗봇 (긴급 안내 유형)", "level": 2, "target": 2, "url": "/guide.html", "blocker": "같음"},
  {"id": "P1-5", "area": "patient", "name": "확인 문자로 들어옴 (회차 표시)", "level": 3, "target": 3, "blocker": "회차 표시 인증 시작 화면 없음", "role": "확인 문자로 들어와 회차를 보고 인증한다"},
  {"id": "P7-1", "area": "patient", "name": "확인 + 기록 (기본)", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 이 화면으로 가는 링크를 만드는 코드가 없음"},
  {"id": "P7-2", "area": "patient", "name": "「먹고 있는데 불편해요」 펼침", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 · 응급 블록은 목업 전용"},
  {"id": "P7-3", "area": "patient", "name": "「가끔 놓쳐요」 펼침", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4"},
  {"id": "P7-4", "area": "patient", "name": "「불편해서 중단」 펼침", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 · 문의하기 준비 안내만"},
  {"id": "P7-5", "area": "patient", "name": "「좋아져서 중단」 펼침", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 · 문의하기 준비 안내만"},
  {"id": "P7-6", "area": "patient", "name": "저장 완료", "level": 2, "target": 1, "url": "/checkin.html", "blocker": "B4 · 완료 화면 네 칸이 서버 DTO 에서 항상 비어 있음"},
  {"id": "P8-1", "area": "patient", "name": "PDF 저장 · 범위 선택", "level": 3, "target": 3, "blocker": "PDF 생성 기능 없음", "role": "저장할 안내문 범위를 고른다"},
  {"id": "P8-2", "area": "patient", "name": "미리보기 · 저장", "level": 3, "target": 3, "blocker": "PDF 렌더링 · 내려받기 없음", "role": "PDF 를 미리 보고 저장한다"},
  {"id": "P9", "area": "patient", "name": "피드백 · 오류 신고", "level": 3, "target": 3, "blocker": "피드백 저장 API 없음", "role": "안내문의 잘못된 내용을 신고한다"},
  {"id": "A1-1", "area": "admin", "name": "직원", "level": 3, "target": 2, "blocker": "Staff 모델은 있음. GET /staffs 조회 API 없음", "role": "직원 목록을 보고 검색한다"},
  {"id": "A1-2", "area": "admin", "name": "직원 추가", "level": 3, "target": 3, "blocker": "직원 생성 API 없음", "role": "직원을 등록하고 초기 비밀번호를 발급한다"},
  {"id": "A1-3", "area": "admin", "name": "직원 수정", "level": 3, "target": 3, "blocker": "직원 수정 · 비밀번호 재설정 API 없음", "role": "역할·재직 상태를 바꾸고 비밀번호를 재설정한다"},
  {"id": "A1-4", "area": "admin", "name": "의원 정보", "level": 3, "target": 2, "blocker": "Hospital 모델은 있음. GET /hospital 조회 API 없음", "role": "의원 정보를 수정한다"},
  {"id": "A1-5", "area": "admin", "name": "문자 이 프로그램이 멈추는 유일한 자리", "level": 3, "target": 3, "blocker": "SMS 잔량 조회 · 충전 API 없음", "role": "문자 잔량을 확인하고 충전한다"},
  {"id": "A1-6", "area": "admin", "name": "전체 로그", "level": 3, "target": 3, "blocker": "감사 로그 모델 · 조회 API 없음", "role": "시스템 감사 로그를 조회한다"},
  {"id": "A1-7", "area": "admin", "name": "한 건 시간 흐름", "level": 3, "target": 3, "blocker": "감사 로그 모델 · 조회 API 없음", "role": "진료 한 건의 처리 흐름을 시간순으로 본다"}
];

var FRAME_AREAS  = { medic: "의료진", patient: "환자", admin: "어드민" };
var FRAME_LEVELS = { 1: "완전 구현", 2: "일부 동작", 3: "화면 없음" };

/* **안내 화면을 씌울 대상** — KEY-234 인수조건 ④ 「핵심 데모 화면에는 적용하지 않는다」.

   지금 화면이 없어도(level 3) 이번 주에 올라갈 프레임(target < 3)은 제외한다.
   S1-11~13(스탭 확인)·P1-1(링크 진입 인증)이 여기 걸린다 — 시연 경로라
   안내 화면을 씌우면 그 주에 두 번 만들게 되고, 시연 대본이 안내 화면을 지난다. */
function needsGuideScreen(frame) {
  return frame.level === 3 && frame.target === 3;
}

function frameById(id) {
  for (var i = 0; i < FRAMES.length; i++) if (FRAMES[i].id === id) return FRAMES[i];
  return null;
}
