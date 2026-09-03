# 프런트를 **이미지에 굽는다** — KEY-189.
#
# 로컬은 `./frontend` 를 바인드 마운트해서 서빙하지만, 운영에는 그 볼륨이 없어
# `/` 가 404 였다. 셋 중(이미지에 굽기 · 볼륨 마운트 · 별도 호스팅) ①로 정한
# 이유는 **이미지 태그로 어떤 프런트를 띄웠는지 고정**되기 때문이다 — QA 가
# 「그때 그 화면」을 다시 띄울 수 있어야 한다 (한금준 님 결정).
#
# 프런트는 빌드 단계가 없다. npm 도 번들러도 없는 평범한 ES5 파일이라
# `frontend/` 를 그대로 굽는다.
FROM nginx:latest

# 컨텍스트는 저장소 루트다 (`docker build … .`) — 다른 이미지들과 같다.
#
# **`frontend/` 를 통째로 굽지 않는다.** 예전 판은 그랬는데, 그러면
# `frontend/tests/` 19 개가 같이 실려서 `https://<운영도메인>/tests/contract.test.js`
# 로 열렸다 — 계약 가정과 목 데이터가 밖에서 읽힌다 (이희진 님 `#145` ①).
#
# `.dockerignore` 로 빼는 길도 있었지만 **실패하는 방향이 반대다.** 거기서
# 빠뜨리면 조용히 나가고(유출), 여기서 빠뜨리면 404 로 눈에 보인다. 유출이
# 걸린 자리라 닫히는 쪽으로 실패해야 한다.
#
# 글롭이라 화면·스타일·스크립트를 새로 더해도 손댈 것이 없다. 대신
# `frontend/` 밑에 **새 폴더**를 만들면 여기 한 줄이 필요하다.
COPY frontend/*.html /vol/web/frontend/
COPY frontend/css/   /vol/web/frontend/css/
COPY frontend/js/    /vol/web/frontend/js/
COPY frontend/patient_wireframe/ /vol/web/frontend/patient_wireframe/

# 설정은 굽지 않는다. `deployment.sh` 가 http/https 중 고른 것을 올려 주고,
# certbot 이 갱신하면서 바꾸기도 한다 — 이미지에 넣으면 그때마다 다시 구워야
# 한다.
