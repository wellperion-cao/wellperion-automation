_assets/logo — 웰페리온 공식 로고 자산 단일 SSOT

이 폴더는 가이드허브 및 모든 하위 페이지(공지 서식·홍보물 등)에서 공통으로 참조하는 공식 로고 자산을 보관합니다.
새 페이지를 만들 때 base64 인라인 금지. 항상 이 폴더의 PNG 파일을 상대경로로 참조하세요.

1. 자산 목록
   - wellperion_wordmark.png       : WELLPERION 가로 wordmark (베이지 톤, 어두운 배경용) — 푸터·헤더 기본
   - wellperion_wordmark_white.png : WELLPERION 가로 wordmark (흰색, 어두운 배경 강조용)
   - wellperion_wordmark_black.png : WELLPERION 가로 wordmark (검정, 밝은 배경용)
   - w_mark.png                    : W 한 글자 (정사각형, 워터마크·아이콘용)

2. 출처
   - wellperion_wordmark.png       ← 2. 브랜드_공식문서/로고(최종)/로고3.PNG
   - wellperion_wordmark_white.png ← 2. 브랜드_공식문서/로고(최종)/로고1.PNG
   - wellperion_wordmark_black.png ← 2. 브랜드_공식문서/로고(최종)/로고.PNG
   - w_mark.png                    ← wellperion_brand_identity(최종시안).pdf 페이지 2 LOGO·VERTICAL 시안 PNG화

3. 페이지에서 사용하는 법 (예시)
   - 가이드허브 (현재 폴더 기준)
     <img src="_assets/logo/wellperion_wordmark.png" alt="WELLPERION">
   - 1단계 하위 (예: cmo/)
     <img src="../_assets/logo/wellperion_wordmark.png" alt="WELLPERION">
   - 2단계 하위 (예: coo/notice/)
     <img src="../../_assets/logo/wellperion_wordmark.png" alt="WELLPERION">

4. 인쇄·새 윈도우(window.open)에서 상대경로 사용하는 법
   새 윈도우는 about:blank 기준이므로 상대경로가 깨집니다.
   인쇄용 HTML <head>에 다음 한 줄을 넣으면 부모 페이지 기준으로 상대경로가 해석됩니다.

   <base href="현재 페이지의 디렉토리 URL">

   JS 예시:
     var baseUrl = window.location.href.replace(/[^/]*$/, '');
     html += '<base href="' + baseUrl + '">';

5. 로고 교체 시
   - 이 폴더의 PNG 파일만 교체하면 모든 페이지에 자동 반영됩니다.
   - 파일명·위치 변경 금지.

6. 자산 공식 SSOT
   - 색상·로고·서브브랜드 정의: 1. AI학습자료_아카이브/06_공지_안내/wellperion_brand_identity(최종시안).pdf
   - 변경은 위 PDF 갱신 후 이 폴더 PNG 함께 교체.
