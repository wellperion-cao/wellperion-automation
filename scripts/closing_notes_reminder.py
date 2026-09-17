# -*- coding: utf-8 -*-
"""월말 결산 리더 입력칸 리마인드 — 회의 전날 아침 한 통씩(실장·소장 = ★중간관리자 카톡 · 나우열M = AtoA).

나우열M 요청 2026-09-17 21:18 「9월 30일에 다시 리마인드 줘 수정할 내용 수정하게」. 첫 회 = 예약작업
Wellperion-Closing-Reminder-0930(2026-09-30 08:30 · 1회). 다음 달부터는 시토 결산 리마인드 파이프에 합친다.
화면 = coo/report/매출회원현황보고.html 「📑 N월 결산 & N+1월 계획」 단추 → 본인 면 오른쪽 입력칸.
"""
from __future__ import annotations

import datetime
import subprocess
import sys

PY = sys.executable
URL = "https://erp.wellperion.com/coo/report/매출회원현황보고.html"


def main() -> int:
    today = datetime.date.today()
    nxt = (today.replace(day=28) + datetime.timedelta(days=4)).month
    where = f"{URL} → 「📑 {today.month}월 결산 & {nxt}월 계획」 단추 → 본인 면 오른쪽 「특이사항 · 이달 계획」 칸"
    kakao = ("[웰페리온 AI] 이경연 실장님, 이정헌 소장님 — 내일 월말 결산 회의 자료 리마인드입니다.\n"
             f"▪ 어디서 — {where}\n"
             "▪ 오늘까지 — 특이사항·이번 달 계획을 적거나, 이미 적으셨으면 고칠 내용만 손보시면 됩니다\n"
             "👉 화면이 번거로우시면 이 방에 글로 주셔도 됩니다 — 대신 옮겨 적겠습니다")
    tg = ("▪ 내일 월말 결산 회의 자료 리마인드 — 파트너팀 면 수정하실 내용 있으면 오늘 손봐 주세요.\n"
          f"   어디서: {where}")
    r1 = subprocess.run([PY, "scripts/kakao_report_sender.py", "--only-room", "★중간관리자", "--sender", "웰리", "--message", kakao]).returncode
    r2 = subprocess.run([PY, "scripts/notify/telegram_user_send.py", "--send", "--chat", "AtoA", "--text", tg]).returncode
    return 0 if (r1 == 0 and r2 == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
