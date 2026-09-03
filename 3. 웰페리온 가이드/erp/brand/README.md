# ERP 브랜드 자산 v1 (배932)

- 출처: `1. AI자료_아카이브/08_로고&워터마크/_assets/logo/웰페리온 로고(가로).ai` (PDF 호환 벡터, 텍스트 아웃라인 완료).
- 방법: PyMuPDF(`page.get_svg_image()`)로 원본 벡터 패스를 그대로 SVG 추출 → 워드마크는 W+WELLPERION 11개 패스 전체를 콘텐츠 bbox로 크롭, W 심볼은 W 패스 1개만 32×32 정사각 viewBox에 센터링. 픽셀 트레이싱 아님 — 원본 벡터 그대로라 한계 없음(계단 현상 없음).
- fill은 전부 `currentColor`로 교체(원본 베이지 하드코딩 값 폐기) — 색은 tokens.css로 제어.
- 한계: `wellperion-wordmark.svg`는 라이트닝(가로형) 락업만 있음, 세로형·SPA&FITNESS 태그라인은 원본 자체에서 제외(금지어). 로고 형태가 바뀌면(리브랜딩) 이 두 SVG를 원본부터 재추출해야 함 — 근사치 보정 아님.
