# 발레 IG 슬라이드 — 시모→웰리 인계 브리프 (2026-06-05)

GM 지시로 시모(CMO)에서 웰리(CEO)로 인계. GM이 반복 미세수정에 지쳐 직접 맡김.

## 목표
발레 런칭 IG 슬라이드(`instagram/260520_발레_런칭/output(인스타그램)/ig_01~07.jpg`)를 **바레 슬라이드와 시각적으로 동일하게** 만들기. 사진·텍스트만 발레, 디자인은 바레와 1:1.

## 근본 이슈 (가장 중요)
- **바레 정본은 캔바(Canva) 제작본**이다 (`compose_barre.py` 헤더 "Canva 완성본 픽셀 실측 기반", 커밋 7e1883f "이미지 교체").
- 코드(`compose_ballet.py`)는 캔바를 **눈대중/픽셀측정으로 모방** → 칩·선·글자가 픽셀 단위로 완벽히는 안 맞음. GM이 매번 미세차이를 지적한 근본 원인.
- **M5(cmo-publish)엔 디자인 표준이 없음** (검수·업로드 단계일 뿐). 디자인 SSOT가 어디에도 없던 게 구조적 문제.
- 캔바 MCP 검색('바레/발레/wellperion') = 빈 결과 (현 연결계정에 원본 없음).

## 현재 엔진 (단일화 완료)
- `scripts/compose_ballet.py` = `scripts/compose_barre.py`의 스타일 함수(draw_chip·paste_logo·gradient·to_duotone 등) **직접 import**. 발레 고유는 사진경로·텍스트·top_crop_fill(표지 인물보정)·full_dark만.
- 소스: `output(인스타그램)/_src_gm/ig_01~06` (GM이 직접 고른 새 사진 6장, 백업 보존).

## GM 지시로 측정·반영 완료분
- 카운트 제거 / CTA 1줄 "문의 wellperion.com/ko/inquiry"
- 표지: 영문(BALLET) 베이지·큰·위 + 한글(발레) 흰색·작은·아래 (바레 배치로 정정)
- BALLET bold88→58 (바레 BARRE 글자높이41 기준), 중심 y786
- 칩 240×52→180×48, 우측끝 x1030·y60 (표지+본문)
- 날짜색 GRAY→(166,151,139), 본문 메타 위 연한 분리선(y772)

## 남은 차이 후보 (GM이 추가로 볼 수 있는 것)
- 발레 표지 사진이 밝은 흰배경이라 듀오톤 후 로고·칩이 바레(어두운 배경)보다 흐릿
- 칩 글자 세로/가로 미세 정렬, 본문 헤드라인·메타 색/크기 미세차
- 캔바 원본과의 잔여 픽셀차(코드 모방의 구조적 한계)

## 웰리 판단 필요 (방향 결정)
1. **캔바 원본 확보** → 복제해 사진·글자만 교체 (픽셀 100%, 진짜 복사). GM께 바레 캔바 링크 요청.
2. **코드 단일엔진을 표준으로 수용** → 미세차이 감수, 바레도 코드본으로 정렬해 완전 통일.
3. **사람 디자이너 외주** → 브랜드 핵심 비주얼은 AI 영역 아님([[project_cmo_designer_and_image_originals]]).

## 파일·참조
- 슬라이드: `output(인스타그램)/ig_01~07.jpg` / 비교: `_cover_compare.jpg`·`_body_compare.jpg`
- 채널 후속: 승인 시 블로그·카페 등 임시저장 (`scripts/publish_4channel_dispatcher.py`)
- 메모리: `project_slide_engine_canva_independence`, `project_4channel_dispatcher`
