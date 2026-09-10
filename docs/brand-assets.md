# 브랜드 자산 — 케어온 마크

KEY-316 에서 병원 웹(로그인 + 상단바 여섯 화면)에 마크를 붙이며 정리한 것이다.
**지금 쓰는 자산이 무엇이고, 왜 그렇게 쓰는지**를 여기 적어 둔다.

## 지금 쓰는 것

| | |
|---|---|
| 파일 | `frontend/assets/careon-mark.svg` |
| 크기 | `viewBox="0 0 100 100"` — 어느 크기로도 선명하다 |
| 색 | `#1E2A44` 하나. 그라디언트 없음 |
| 배경 | **없다.** 투명이라 어디에 얹어도 네모가 안 생긴다 |
| 출처 | 이희진 님이 KEY-316 티켓에 첨부(`careon-concept-e-mono.svg`) |

**병원용은 모노톤이다.** 환자 화면(`guide.html`)이 쓰는
`patient_wireframe/assets/logo.png` 는 보라 그라디언트이고 배경까지 박혀 있다 —
그것을 병원 화면에 그대로 쓰면 `tokens.css` 머리말의 「보라 계열을 안 쓴다」와
부딪힌다.

## 어떻게 쓰는가

`frontend/css/style.css` 의 `.brandmark` 한 곳이다.

```
상단바   24px   .topbar__brand .brandmark   (shell.css)
로그인   36px   .card__title .brandmark     (auth.css)
```

`background-size: contain` 이라 **상자 크기만 바꾸면 따라온다.** 크기별 계산식이
없다.

### 처음에는 PNG 를 잘라 썼다 — 없어진 것들

SVG 가 오기 전에는 환자용 PNG 를 CSS 로 잘라 쓰고 있었다. 그 자산이 168×123 에
배경(`#f9effc`)이 박혀 있고 마크도 가운데가 아니라, 타일을 깔고 좌표를 계산해
잘라 냈다. **이희진 님이 모노톤 SVG 를 주시면서 그 전부가 없어졌다** — 아래는
이제 저장소에 없다.

- `tokens.css` 의 `--brand-tile` 토큰
- `.brandmark` 의 타일 배경과 `background-size`·`background-position` 계산식
- 「보라 계열을 안 쓴다」에 대한 예외 설명

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
`prefers-color-scheme` 블록이 없다). 생기면 그때 함께 정한다 — 배경이 없는
SVG 라 네모가 뜨지는 않지만, `#1E2A44` 는 어두운 바탕에서 안 읽힌다. 그때는
아래 「색을 바꾸려면」이 답이다.

**축소** — 마크는 `flex: none` 이라 좁아져도 안 줄어든다. 768px 아래에서
`.topbar__brand` 가 말줄임(`overflow: hidden`)으로 바뀌는데, 마크가 광학
중심에 맞추느라 1.75px 올라가 있어 **윗동이 0.75px 잘렸다.** 자르는 상자만
위로 2px 넓히고 같은 값의 음수 여백으로 배치를 제자리에 두어 막았다
(`shell.css` 의 `@media (max-width: 768px)`).

## 색을 바꾸려면

지금은 자산이 든 `#1E2A44` 를 그대로 쓴다. `--ink`(#1c1f23) 곁의 값이라 흰
상단바에서 글자와 같은 무게로 읽힌다.

화면마다 색을 달리해야 하는 날이 오면 `background-image` 대신 `mask-image` 와
`background-color: currentColor` 로 바꾼다 — 그러면 색이 CSS 에서 온다. 지금
그렇게 하지 않는 것은 **바꿀 일이 없어서**이고, 마스크는 브라우저 지원을 한 겹
더 따져야 한다.
