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

> **글꼴 주의** — SVG 의 한글은 **바꾸는 쪽 환경의 글꼴**로 그려진다. 판독 결과를 비교할
> 때는 어느 글꼴로 래스터했는지 함께 적는다. 같은 SVG 라도 글꼴이 다르면 인식률이 달라진다.

## 5. 외부 보관 — **아직 정해지지 않았다**

`docs/decisions/KEY-163-ocr-real-contract.md` §8 이 「합성 EMR 이미지 보관 위치 — 미확인 —
(확정 후 기입)」으로 두고 있다. 8/28 멘토링 확정 항목이다.

**그때까지는 보관하지 않는다.** 지금 판은 값에서 결정적으로 나오므로 보관할 것이 없다.
확정된 뒤 실제 병원 EMR 레이아웃을 재현한 판이 생기면 그것만 외부에 둔다.

확정되면 이 절에 아래를 채운다.

| 항목 | 채울 것 |
|---|---|
| 보관 위치 | (확정 후 기입) |
| 접근 권한 | 팀 6인. 외부 공유 금지 |
| 버전 | 파일명 규칙 3절과 같은 `vN`. 덮어쓰지 않고 올린다 |
| 폐기 | 프로젝트 종료 시 삭제. 실제 환자 자료가 섞였다는 의심이 들면 **즉시** 삭제하고 다시 만든다 |

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
