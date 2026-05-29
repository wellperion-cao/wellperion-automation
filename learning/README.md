AI 학습 자료 자동 수집 인프라

이 폴더는 웰페리온이 Anthropic·Claude 최신 정보를 주기적으로 자동 수집하기 위한
소스 설정(SSOT)을 담는다. 실제 수집·요약·발송 로직은 scripts 폴더의 기존
ai_education_auto_learner.py 가 수행하고, 이 폴더의 sources.json 만 읽어간다.


1. 이 인프라가 하는 일

   웹에 흩어진 Anthropic·Claude 공식 정보를 한 곳에서 자동으로 긁어와
   핵심 제목을 요약하고 텔레그램으로 보고한다. 사람이 매번 여러 사이트를
   돌아다닐 필요 없이 새 소식·릴리스·문서 변경을 한 번에 받아본다.
   자기학습 4단계(수집 → 요약 → 제안 → 승인) 중 "수집" 단계에 해당한다.


2. 수집 소스 7개 (sources.json)

   기존 3개
   2-1. Anthropic 공식 뉴스        https://www.anthropic.com/news
   2-2. Anthropic 리서치          https://www.anthropic.com/research
   2-3. Claude 문서 변경사항       https://docs.anthropic.com/en/docs/about-claude/models

   신규 4개 (2026-05-29 확장)
   2-4. Claude Code 문서          https://docs.anthropic.com/en/docs/claude-code/overview
   2-5. Anthropic 엔지니어링 블로그  https://www.anthropic.com/engineering
   2-6. API 릴리스 노트           https://docs.anthropic.com/en/release-notes/api
   2-7. Claude 앱 릴리스 노트      https://docs.anthropic.com/en/release-notes/claude-apps


3. 실행법

   3-1. 전체 (수집 → 요약 → 발송)
        python scripts/ai_education_auto_learner.py
   3-2. 수집만
        python scripts/ai_education_auto_learner.py --collect
   3-3. 요약만 (직전 수집 결과 사용)
        python scripts/ai_education_auto_learner.py --summary
   3-4. 마지막 요약 텔레그램 발송
        python scripts/ai_education_auto_learner.py --send
   3-5. 현황 조회 (소스 목록·마지막 수집/요약 시각)
        python scripts/ai_education_auto_learner.py --status


4. 기존 learner 와의 관계

   4-1. ai_education_auto_learner.py 가 본 폴더의 sources.json 을 읽어 소스 목록을 정한다.
   4-2. sources.json 이 없거나 형식이 깨지면 스크립트 내장 기본 3개로 자동 폴백한다.
        (즉 이 파일이 사라져도 기존 동작은 깨지지 않는다.)
   4-3. 소스를 늘리거나 줄일 때는 코드를 고치지 말고 sources.json 만 편집한다.
   4-4. 각 소스 항목 필수 키: id · label · url · parser.
        parser 는 현재 html_title_extract 단일 (페이지 제목·헤딩 추출 방식).
   4-5. 수집 결과 데이터는 scripts/_education_data/ 에 저장된다.


5. 자동 실행

   매주 월요일 윈도우 작업 스케줄러가 위 전체 파이프라인을 1회 자동 실행한다.
   (작업명 Wellperion-AI-Education-Weekly). 따라서 평소에는 손댈 것이 없고,
   소스를 바꾸고 싶을 때만 sources.json 을 편집하면 다음 실행부터 반영된다.
