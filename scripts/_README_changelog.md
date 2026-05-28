가이드허브 홈 최신 카드 자동 동기화

파일: scripts/update_guide_hub_changelog.py
워크플로: .github/workflows/changelog.yml


동작 원리

master 브랜치에 push가 발생하면 GitHub Actions가 이 스크립트를 자동 실행합니다.
스크립트는 git log에서 최근 1주일 이내 커밋(최대 15건)을 읽어,
가이드허브 홈 페이지(3. 웰페리온 가이드/wellperion_guide(main).html)의
두 영역을 자동 갱신합니다.

갱신 영역 1: 최신 카드
마커: <!-- AUTO:LATEST-START --> ~ <!-- AUTO:LATEST-END -->
내용: 최근 5건 커밋의 날짜와 제목을 card grow 블록으로 표시

갱신 영역 2: 업데이트 기록 표
마커: <!-- AUTO:TABLE-START --> ~ <!-- AUTO:TABLE-END -->
내용: 최근 커밋을 날짜별로 그룹화해 표 행(tr)으로 맨 위에 자동 추가

무한 루프 방지
changelog.yml의 paths-ignore 설정으로
가이드허브 파일 자체 변경은 워크플로를 재트리거하지 않습니다.
또한 "auto(changelog):" 로 시작하는 자동 커밋은 커밋 목록에서 제외됩니다.

마커 자동 삽입
HTML에 마커가 없으면 최초 1회 자동으로 삽입합니다.
이후 실행부터는 마커 사이 내용만 교체합니다.


로컬 사용 방법

변경 미리보기 (파일 수정 없음):
    python scripts/update_guide_hub_changelog.py --dry-run

실제 반영:
    python scripts/update_guide_hub_changelog.py

필요 환경: Python 3.11 이상, git 명령어 PATH에 등록
외부 패키지 의존성 없음 (표준 라이브러리만 사용)


파일 구성

scripts/update_guide_hub_changelog.py   핵심 스크립트
.github/workflows/changelog.yml         GitHub Actions 워크플로
scripts/_README_changelog.md            이 문서
