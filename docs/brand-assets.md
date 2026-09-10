# 브랜드 자산 — 케어온 마크

KEY-316 에서 병원 웹(로그인 + 상단바 여섯 화면)에 마크를 붙이며 정리한 것이다.
**지금 쓰는 자산이 무엇이고, 왜 그렇게 쓰는지**를 여기 적어 둔다.

## 지금 있는 것

| | |
|---|---|
| 파일 | `frontend/patient_wireframe/assets/logo.png` |
| 크기 | 168 × 123 · 8bit RGBA |
| 투명 | **없다.** 모서리까지 `#f9effc` 로 채워진 그림이다 |
| 실제 마크 | `x 37~123 · y 23~108` (87 × 86) |
| 박힌 여백 | 좌 37 · 우 44 · 상 23 · 하 14 — **가운데가 아니다** |
| SVG 원본 | **없다.** 저장소·디자인 폴더 어디에도 없다 |

## 그래서 어떻게 쓰는가

**자산은 안 건드리고 CSS 로 잘라 쓴다** — `frontend/css/style.css` 의 `.brandmark`.

상자에 `--brand-tile`(= 자산에 박힌 `#f9effc`)을 깔고 `background-size` ·
`background-position` 으로 마크만 가운데 세운다. 타일 색이 자산의 박힌 색과
같아서 이음매가 안 보인다. 셈이 어떻게 나왔는지는 그 규칙의 주석에 있다.

```
상단바   24px   .topbar__brand .brandmark   (shell.css)
로그인   36px   .card__title .brandmark     (auth.css)
```

**왜 잘라 쓰는가.** 흰 상단바에 원본을 그대로 얹으면 연보라 네모가 뜬다. 환자
화면(`guide.html`)은 24 × 24 타일에 `object-fit: cover` 로 우겨넣고 있는데,
그러면 마크 오른쪽 끝이 잘리는 자리까지 간다. 같은 잘못을 병원 웹에 옮기지
않는다.

## 정해 둔 것

**대체 텍스트 — 없다.** 마크는 늘 「케어온」 글자 바로 옆에 선다. 글자가 이미
이름을 말하므로 마크까지 읽으면 낭독기에서 「케어온 케어온」이 된다. 빈
`<span>` 에 `aria-hidden="true"` 로 둔다 (WCAG 1.1.1 장식 이미지).

**누르는 곳이 아니다.** 상단바 마크에 링크를 걸지 않는다. 세 가지 까닭이다.

1. 갈 곳이 이미 상단바에 있다 — 현황 · 관리 · 설정
2. 「기본 진입 화면」이 역할마다 다르다(의사·스탭은 `/patients.html`,
   어드민은 `/admin.html` — `js/session.js` 의 `landingFor`). 로고가 사람마다
   다른 곳으로 가면 그것은 길잡이가 아니다
3. 안내문을 고치는 중에 눌리면 **쓰던 것이 날아간다.** 그 자리를 막는 문이
   이미 있는데(`doctor.js` 의 `canDiscardPatientLink`), 로고에 또 하나를
   달 값이 없다

**다크 대응 — 안 한다.** 지금 이 저장소에 다크 테마가 없다(`tokens.css` 에
`prefers-color-scheme` 블록이 없다). 생기면 그때 함께 정한다 — 지금 자산은
밝은 배경이 박혀 있어 어두운 상단바에서는 연보라 네모가 된다.

**축소** — 마크는 `flex: none` 이라 좁아져도 안 줄어든다. 768px 아래에서
`.topbar__brand` 가 말줄임(`overflow: hidden`)으로 바뀌는데, 마크가 광학
중심에 맞추느라 1.75px 올라가 있어 **윗동이 0.75px 잘렸다.** 자르는 상자만
위로 2px 넓히고 같은 값의 음수 여백으로 배치를 제자리에 두어 막았다
(`shell.css` 의 `@media (max-width: 768px)`).

## SVG 가 들어오면

한 자리만 고치면 된다 — `style.css` 의 `.brandmark`. 함께 없어지는 것들:

- `tokens.css` 의 `--brand-tile`
- `.brandmark` 의 잘라 쓰는 셈(`background-size` · `background-position`)
- 이 문서의 「지금 있는 것」 · 「그래서 어떻게 쓰는가」 두 절

`aria-hidden` · 링크 없음 · 다크 대응 여부는 자산이 바뀌어도 그대로다.
