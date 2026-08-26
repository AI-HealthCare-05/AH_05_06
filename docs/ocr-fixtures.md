# 판독(OCR) 샘플과 기대값 — KEY-68

> 실제 OCR 어댑터(KEY-56)와 E2E(KEY-69)가 **같은 샘플·같은 기대값**을 쓰게 하는 규격이다.
> 업로드 차단 테스트가 쓰는 매직바이트 더미와는 다른 물건이다 — 아래 「둘을 헷갈리지 않는다」 참고.

---

## 1. 저장소에 두는 것과 두지 않는 것

| | |
|---|---|
| **둔다** | 기대값 `docs/data/ocr-fixtures/*.toml` · 생성기 `scripts/make_ocr_fixture.py` |
| **안 둔다** | 만들어진 그림(SVG·PNG·PDF)과 기대값 JSON |

KEY-68 범위 밖 첫 줄이 「합성 이미지의 Git 저장소 커밋」이다. 그래서 **만드는 법만 두고
만든 것은 안 둔다.** 부를 때마다 같은 값에서 같은 것이 나오므로 보관할 이유가 없다.

기본 출력 자리는 `build/ocr-fixtures/` 이고, `.gitignore` 3행의 `build/` 가 이미 막는다.
규칙을 새로 더하지 않았다 — 같은 것을 두 곳에 적을 이유가 없다. 막고 있다는 것은
`app/tests/ocr/test_key68_fixture_spec.py` 의
`test_the_default_output_place_is_ignored_by_git` 이 `git check-ignore` 로 **직접 물어서** 확인하고,
`test_the_generator_runs_and_writes_nothing_into_the_repo` 가 저장소를 **세어서** 확인한다.

## 2. 값은 어디서 오는가

```
docs/data/synthetic-patients.csv        환자·처방 값        ← 정본
docs/data/ocr-fixtures/*.toml           ICD 코드 · 표의 어느 칸    ← EMR 에만 있는 것
docs/decisions/KEY-163-ocr-real-contract.md   필수·권장 분류
```

기대값 TOML 은 **값을 적지 않는다.** `csv_column = "처방일수"` 처럼 **열 이름을 가리킨다.**
`docs/synthetic-data-spec.md` 1절이 「한 곳에서만 고친다 — 정본은 `docs/data/` 아래 CSV
둘뿐」이라고 못 박았기 때문이다. 값을 TOML 에 박으면 기준이 두 곳이 된다.

## 3. 파일명·버전 규칙

```
{시나리오ID}.{문서유형소문자}.{버전}

  기대값   docs/data/ocr-fixtures/SYN-EMS-01.emr.v1.toml
  산출물   SYN-EMS-01.emr.v1.svg
           SYN-EMS-01.emr.v1.expected.json
```

- **시나리오 ID** 는 `docs/synthetic-data-spec.md` 2절의 것을 그대로 쓴다. 새로 짓지 않는다.
- **문서 유형** 은 `OcrDocumentType` 값의 소문자다 — `emr` · `prescription` · `lab_result`.
  코드에 없는 유형은 파일명으로도 쓰지 않는다.
- **버전** 은 `v1` 부터 정수로 올린다. **기대값이 바뀌면 올린다.** 그림만 예뻐지는 것은
  버전이 아니다. KEY-56·KEY-69 가 버전으로 고정해 부르므로, 같은 버전은 늘 같은 기대값이어야 한다.

## 4. 만드는 법

```bash
uv run python scripts/make_ocr_fixture.py
```

`build/ocr-fixtures/` 에 SVG 한 장과 기대값 JSON 한 장이 나온다. 다른 자리에 내려면 `--out`.

SVG 로 내는 이유는 둘이다 — 글자가 그대로 남아 **사람이 열어 확인할 수 있고**, 저장소가
이미 가진 것 말고 아무 의존성도 안 늘린다(Pillow 는 `torchvision` 경유라 `app`·`dev` 에 없다).

판독기에 넣을 래스터·PDF 가 필요하면 각자 환경에서 바꾼다. 변환기를 저장소 의존성으로
넣지 않는다.

```bash
# macOS
qlmanage -t -s 1600 -o . build/ocr-fixtures/SYN-EMS-01.emr.v1.svg
# rsvg 가 있으면
rsvg-convert -w 1600 build/ocr-fixtures/SYN-EMS-01.emr.v1.svg -o emr.png
```

> **글꼴 주의** — SVG 의 한글은 **바꾸는 쪽 환경의 글꼴**로 그려진다. 같은 SVG 라도 글꼴이
> 다르면 픽셀이 달라지고 **판독 결과도 달라진다.** 손으로 바꾸지 말고 아래 4-1 을 쓴다.

## 4-1. 시연용 고정 이미지 — 누가 돌려도 같은 바이트 (KEY-190)

```bash
./scripts/render_ocr_fixture.sh            # 기본 build/ocr-fixtures
```

그리는 환경을 컨테이너에 가둔다. 이 셋이 고정하는 것이 전부다.

```text
알파인          alpine:3.20
              sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc
래스터          rsvg-convert 2.58.5-r0
글꼴            font-noto-cjk 0_git20220127-r1   (SVG 의 애플 글꼴은 컨테이너에 없어
                                                 스택이 여기로 떨어진다)
해상도          150 dpi · 원본 900×520 → 1875×1083
```

### 지금 값

| 항목 | sha256 |
|---|---|
| `SYN-EMS-01.emr.v1.png` | `29458d8bf82cd901d1f5abacbd1d435530cf4d9bc0eae2aa3caf0e3893bcc983` |
| `SYN-EMS-01.emr.v1.svg` | `cbd590f056384c830927453796d57d55a9710f25a08c89155d0102c61c681ae0` |
| `docs/data/synthetic-patients.csv` | `88143d5a32440a25ec8f9b7e571f9acd6c6f13ab78cfee5f1936ad3a42fdb43c` |

`develop` `136f5ec` 기준. **셋을 함께 적는 이유가 있다** — 이미지 해시만 두면
값이 달라졌을 때 「렌더가 흔들린 것」인지 「정본 CSV 가 바뀐 것」인지 모른다.
CSV 해시가 다르면 뒤쪽이다.

### PDF 는 해시를 고정하지 않는다

`rsvg-convert -f pdf` 도 되지만 **매번 다른 바이트가 나온다.** 압축된 객체
스트림 안에 만든 시각이 들어가서다 — 두 번 돌려 71283 / 71284 바이트로 갈렸고
70701 번째 바이트부터 달랐다.

그래서 **못 박는 것은 PNG 하나다.** PDF 가 필요하면 같은 스크립트가 함께 내지만
해시로 같은 것임을 주장하지 않는다.

### KEY-69 가 쓰는 법

E2E 는 이 스크립트를 먼저 부르고 `build/ocr-fixtures/SYN-EMS-01.emr.v1.png` 를
업로드한다. 기대값은 옆의 `SYN-EMS-01.emr.v1.expected.json` 이다 — 같은 실행에서
같이 나오므로 둘이 어긋날 일이 없다.

## 5. 외부 보관 — **MinIO** (KEY-191)

KEY-163 §8 이 「합성 EMR 이미지 보관 위치 — 미확인」으로 열어 두었던 자리다.
저장소에 바이너리를 안 두기로 했는데(KEY-68 범위 밖 첫 줄) 그러면 팀이 **같은
바이트**를 나눠 가질 자리가 없었다.

`docker-compose.yml` 의 `minio` 서비스다. **S3 호환이라서 골랐다** — Sprint 6 에
AWS 로 가면 엔드포인트만 바꾼다.

| 항목 | 값 |
|---|---|
| 보관 위치 | 팀 서버 MinIO · 버킷 `ocr-fixtures` |
| 경로 규칙 | `emr/v{N}/SYN-EMS-01.emr.v{N}.png` — 3절의 `vN` 을 그대로 쓴다 |
| 접근 권한 | 팀 6인. 버킷 정책 `private`, 익명 접근 **403** |
| 버전 | **덮어쓰지 않는다.** `v2` 가 생기면 `emr/v2/` 로 올린다 |
| 폐기 | 프로젝트 종료 시 버킷째 삭제. 실제 환자 자료가 섞였다는 의심이 들면 **즉시** 삭제하고 다시 만든다 |

### 데이터 내구성 — **여기 있는 것은 잃어도 된다**

`MINIO_VOLUMES` 가 `/data` 한 경로라 **EC:0(Erasure Coding 없음)** 으로 돈다.
MinIO 자체는 드라이브 손실을 복구하지 않는다. 이름 붙은 볼륨은 컨테이너
재시작을 견딜 뿐, 호스트가 죽거나 볼륨을 실수로 지우면 같이 사라진다
(한금준 님 `#149` 검토).

**그래도 되는 자리다.** 여기 두는 것은 `scripts/render_ocr_fixture.sh` 로
언제든 같은 바이트로 다시 만들 수 있다 (§4-1). 잃으면 다시 굽는다.

**잃으면 안 되는 것이 생기면 이 구성으로는 안 된다** — S3 나 다중 노드로
옮겨야 한다. 그때는 KEY-191 범위 밖이니 별도로 정한다.

### 자격증명

`MINIO_ROOT_USER` · `MINIO_ROOT_PASSWORD` 를 `.env` 에 넣는다. 이름은
`envs/example.*.env` 에 있고 **값은 저장소 어디에도 없다.** 팀에는 저장소가
아닌 경로로 나눈다.

### 운영에서는 포트를 밖으로 안 연다

`infra/docker/docker-compose.prod.yml` 은 9000·9001 을 **`127.0.0.1` 에만**
묶는다. 보안 그룹이 한 번 잘못 열려도 공개 인터넷에서는 안 닿는다.

```bash
ssh -N -L 9000:127.0.0.1:9000 -L 9001:127.0.0.1:9001 ubuntu@<서버>
# 그 다음 http://127.0.0.1:9001 로 콘솔에 붙는다
```

「팀 6인만」이 **자격증명 하나에만 걸려 있지 않게** 하는 것이 요점이다.
버킷 정책 `private` 과 익명 GET 403 은 두 번째 문이다.

### 정책은 손이 아니라 스크립트가 닫는다

`scripts/minio_init.sh` 가 버킷을 만들 때마다 `mc anonymous set none` 을 다시
건다. MinIO 기본값이 private 이지만 **기대지 않는다** — 버킷이 다른 서버에서
다시 만들어지거나 누가 `download` 로 한 번 열면, 문서에 적힌 「403 이더라」는
아무것도 못 막는다 (이희진 님 `#149` ④). 실제로 열어 놓고 다시 돌려 보니
`download` → `private` 로 돌아왔다.

### 올리고 되받는 법

```bash
# 1) KEY-190 렌더로 만든다 (§4-1 — 누가 돌려도 같은 바이트)
./scripts/render_ocr_fixture.sh

# 2) 버킷을 준비한다. **익명 접근을 매번 다시 닫는다** — 멱등이라 몇 번 돌려도 된다.
#    MC_HOST_… 에 자격증명을 담는다 — 명령줄에 쓰면 `ps` 에 남는다.
export MC_HOST_team="http://<사용자>:<비밀번호>@<서버>:9000"
./scripts/minio_init.sh team

# 3) 올린다
mc cp build/ocr-fixtures/SYN-EMS-01.emr.v1.png \
      team/ocr-fixtures/emr/v1/SYN-EMS-01.emr.v1.png

# 4) 받은 것이 같은 바이트인지 본다
mc cp team/ocr-fixtures/emr/v1/SYN-EMS-01.emr.v1.png ./받은것.png
shasum -a 256 ./받은것.png     # §4-1 의 해시와 같아야 한다
```

### 실행 기록 — 2026-08-26

인수조건이 「업로드→조회 1회 실행 기록」이라 실제로 돌렸다. 자격증명은
**합성**이고 로컬 컨테이너다.

```text
기동          2초 만에 health 응답
업로드        emr/v1/SYN-EMS-01.emr.v1.png   32.32 KiB
되받은 바이트  29458d8bf82cd901d1f5abacbd1d435530cf4d9bc0eae2aa3caf0e3893bcc983
              → §4-1 의 해시와 같다

익명 GET(객체)     HTTP 403  AccessDenied
익명 GET(버킷 목록) HTTP 403
익명 GET(루트)     HTTP 403
자격증명 있음       조회됨      ← 양성 대조. 없으면 「403」이 무의미하다
틀린 비밀번호       서명 불일치
```

**PDF 는 안 올린다.** 만들 때마다 바이트가 달라(압축 스트림에 시각이 들어간다)
「같은 것」을 주장할 수 없다 — §4-1 이 그렇게 정했다. 필요하면 PNG 에서 각자
만든다.

## 6. 실제 환자정보 미포함 — 검수 기록

| 검수 | 방법 | 결과 |
|---|---|---|
| 신원 값이 합성 CSV 에서만 오는가 | `test_the_patient_comes_only_from_the_synthetic_csv` | 통과 |
| 값을 코드·TOML 에 지어 넣지 않았는가 | TOML 은 열 이름만 가리킨다 (2절) | 통과 |
| 산출물이 저장소에 남는가 | `test_the_generator_runs_and_writes_nothing_into_the_repo` | 안 남음 |
| 실제 병원 화면을 캡처했는가 | 안 했다. 렌더러는 KEY-163 §2 의 표 구조만 그린다 | 해당 없음 |

`SYN-EMS-01` 은 `docs/synthetic-data-spec.md` 가 「기준 케이스」로 지정한 합성 행이다.
전화번호는 그림에 넣지 않는다 — 판독에 필요 없고, 합성 번호라도 실제 가입자와 겹칠 수 있다
(같은 문서 1절).

## 7. KEY-56 · KEY-69 가 가져다 쓰는 법

```python
# 1) 만든다
#    uv run python scripts/make_ocr_fixture.py --out <원하는 자리>
# 2) 기대값을 읽는다
expected = json.loads(Path("build/ocr-fixtures/SYN-EMS-01.emr.v1.expected.json").read_text("utf-8"))
# 3) 판독 결과와 맞댄다
for name in expected["success_requires"]:
    assert ocr_fields[name] == expected["fields"][name]["value"]
```

`success_requires` 가 KEY-163 §4 의 성공 판정 기준이다. 이 셋 중 하나라도 비면 fallback 이다.

## 8. 둘을 헷갈리지 않는다

| | 무엇을 재는가 | 어디 |
|---|---|---|
| 매직바이트 더미 | 형식·용량·경로 조작 **차단** | `app/tests/document_apis/test_document_upload_api.py` |
| 이 문서의 샘플 | 판독 **인식 품질**과 fallback | `docs/data/ocr-fixtures/` |

앞엣것은 이 일감에서 **건드리지 않는다.** KEY-68 인수조건 마지막 줄이 「기존 업로드 형식·용량·
경로 조작 차단 테스트는 변경하거나 약화하지 않음」이다.

## 9. 아직 안 만든 것

| 무엇 | 왜 |
|---|---|
| 처방전 · 검사결과지 | KEY-163 §1 이 「이번은 EMR 1종으로 범위를 한정하는 결정」이라고 적었다 |
| 약봉투 | `OcrDocumentType` 에 값이 없다 (`EMR` · `PRESCRIPTION` · `LAB_RESULT` 뿐) — 올릴 자리가 없다 |
| 저신뢰 · 누락 · 복수 후보 · 환자 불일치 | v1 정상 기준선을 비틀어 만든다. 확정 뒤 v2 로 |
| 실제 병원 EMR 레이아웃 재현 | KEY-163 §8 「대상 병원 EMR 시스템 이름·버전 — 미기입」 |

넷 다 8/28 멘토링 확정 뒤에 이어서 한다.
