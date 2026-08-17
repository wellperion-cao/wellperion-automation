"""임정은M 회신 — 2026-08-18 ★운영부 방 텍스트 발송 wrapper
배 ID: CEO-2026-08-15-임정은M-회신-발송-신규문의-6명-연락이력-원래-없
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 시포 배576 원문 (3문단, 링크 쿼리 없음)
MESSAGE = (
    "신규 문의 여섯 분(육세라·정새벽·최정호·이도경·익명여/신동아·맹기훈)의 연락 기록이 없어졌다고 하신 건, "
    "저희가 지난 기록을 처음부터 다시 훑어봤습니다. 기록이 있다가 지워진 것이 아니라 처음부터 비어 있던 것이 맞았습니다. "
    "지워진 것이 없으니 되살릴 것도 없고, 여섯 분만 직접 채워 주시면 됩니다.\n"
    "멤버십 회원관리 https://wellperion-cao.github.io/wellperion-automation/cpo/member/membership.html "
    "화면 맨 위 [신규 문의] 카드를 누르면 나오는 목록에서 그 여섯 분을 찾으시면 됩니다.\n"
    "각 줄의 연락 기록 칸에 통화하신 내용을 적어 주세요. "
    "혹시 통화한 적이 없는 분이면 그대로 두셔도 됩니다."
)

TARGET_ROOM = "★운영부"
DRY_RUN = "--dry-run" in sys.argv

argv_orig = sys.argv[:]
sys.argv = [
    "kakao_report_sender.py",
    "--message", MESSAGE,
    "--only-room", TARGET_ROOM,
]
if DRY_RUN:
    sys.argv.append("--dry-run")

import kakao_report_sender
result = kakao_report_sender.main()
sys.argv = argv_orig
sys.exit(result)
