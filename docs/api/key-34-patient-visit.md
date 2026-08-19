# KEY-34 환자·진료 API 구현 기록

## 구현 범위

- `POST/GET /api/v1/patients`
- `GET/PATCH /api/v1/patients/{patient_id}`
- `POST/GET /api/v1/patients/{patient_id}/visits`
- `GET/PATCH /api/v1/visits/{visit_id}`
- 병원 범위 조회, `staff`·`doctor` 역할 검사, 중복·404·403 오류 계약
- 서명된 cursor pagination과 `Asia/Seoul` 현지 날짜 기준 중복 진료 검사

요청 본문의 `hospital_id`, `patient_id`, `visit_id`는 허용하지 않습니다. 병원 범위는
인증된 직원 컨텍스트에서만 가져오며 타 병원 리소스는 존재 여부를 숨기기 위해
`404`로 응답합니다. 테스트 데이터는 `SYN-` 식별자의 합성값만 사용합니다.

## 현재 통합 경계

현재 `User` 모델에는 확정된 `staff.hospital_id`와 `roles`가 아직 병합되지 않았습니다.
따라서 API 의존성은 해당 속성이 없는 로그인 주체를 허용하지 않고 `403`으로
차단합니다. KEY-73의 Staff·Hospital 관계가 병합되면 같은 의존성이 인증 컨텍스트의
값을 사용하며, 클라이언트가 병원 값을 지정하는 우회 경로는 생기지 않습니다.

Department·Staff 기준 테이블도 아직 없으므로 `doctor_id` 또는 `department_id`가
포함된 진료 생성·수정은 `INVALID_DEPARTMENT`로 안전하게 실패합니다. 두 값을 검증 없이
저장하지 않으며, KEY-73 병합 뒤 같은 병원의 활성 진료과와 의사 소속 검증을 연결해야
합니다. 환자·진료 기본 흐름은 담당의 미지정 상태로 통합 테스트합니다.

환자번호 제한 정정은 `admin`과 임상 역할을 함께 가진 사용자, 진료가 없는 환자,
필수 정정 사유 조건까지 검사합니다. 감사 이벤트 테이블이 병합되기 전에는 실제 운영
활성화 대상에서 제외하며, 이벤트 기록 연결은 감사로그 담당 일감의 선행 조건입니다.
