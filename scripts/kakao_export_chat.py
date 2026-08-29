#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★운영부 카톡 대화 무인 내보내기 — kakao_export_chat.py (2026-07-14 CTO, 배906 B)

아침 다이제스트(ops_daily_digest.py)의 앞단계. 지정 카톡 방의 대화를 카카오톡 PC
'대화 내보내기'(단축키 Ctrl+S)로 .txt 저장한다. GM 데스크톱처럼 창이 많이 겹친
환경에서도 실패하지 않도록, kakao_report_sender의 검증된 pywinauto 포커스로 방 창을
확실히 앞으로 가져온 뒤 Ctrl+S를 '창에 직접' 꽂고(전역 hotkey는 위에 덮인 창에 먹힘),
'다른 이름으로 저장' 대화상자(#32770)에 목표 전체경로를 넣어 저장한다.

성공 레시피(2026-07-14 실측): ①KakaoTalk.exe 재실행(트레이→메인창 전면) ②방 검색 자동열기
③focus_window(포커스) ④room.type_keys('^s') ⑤저장 대화상자에 경로 set_edit_text+저장.

★개인정보: 산출물(대화 원문)은 gitignore된 "1. AI자료_아카이브/11_카카오톡/{폴더}/{YYYY-MM}/"
에만. 이 스크립트·산출물은 커밋하지 않는다. 발송·요약은 범위 밖(ops_daily_digest.py).

사용법:
  python scripts/kakao_export_chat.py                    # '★운영부' → 오늘자 auto export
  python scripts/kakao_export_chat.py --room "★운영부"  # 방 지정
"""
from __future__ import annotations

import argparse
import json
import io
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

KAKAO_EXE = os.environ.get(
    "KAKAOTALK_EXE", r"C:\Program Files (x86)\Kakao\KakaoTalk\KakaoTalk.exe"
)
ARCHIVE_BASE = ROOT / "1. AI자료_아카이브" / "11_카카오톡"
# 카톡 방 제목 → 파일시스템 폴더명(★·공백 등 정규화, 기존 관례 유지)
# 배536(2026-08-11 GM→시토) — ★중간관리자도 ★운영부와 동일 배선(매핑 없어도 아래 fallback
# room_name.replace(" ", "")로 이미 "★중간관리자"가 나오지만, 관례대로 명시해 둔다.
ROOM_DIR_NAME = {"★ 운영부": "★운영부", "★ 중간관리자": "★중간관리자"}


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def ensure_kakao_foreground(wait: float = 5.0) -> None:
    """카톡 메인창 전면화 — 트레이로 내려가 창을 못 찾는 실패 방지. 단일 인스턴스라
    exe 재실행 시 기존 인스턴스 메인창이 앞으로 나온다. 실패해도 계속(비치명)."""
    try:
        if not os.path.exists(KAKAO_EXE):
            log(f"[kakao] 실행파일 없음({KAKAO_EXE}) — 자동 띄우기 생략")
            return
        subprocess.Popen([KAKAO_EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"[kakao] 메인창 자동 띄우기 — {wait:.0f}s 대기")
        time.sleep(wait)
    except Exception as e:
        log(f"[kakao] 자동 띄우기 실패(무시): {type(e).__name__}: {e}")


def _find_dialog(keyword: str, timeout: float, exclude: int | None = None) -> int | None:
    """제목에 keyword를 포함한 보이는 #32770 대화상자 hwnd를 timeout 내 폴링해 반환."""
    import win32gui

    end = time.time() + timeout
    while time.time() < end:
        found: list[int] = []

        def cb(h, _):
            if (
                win32gui.IsWindowVisible(h)
                and win32gui.GetClassName(h) == "#32770"
                and keyword in win32gui.GetWindowText(h)
                and h != exclude
            ):
                found.append(h)
            return True

        win32gui.EnumWindows(cb, None)
        if found:
            return found[0]
        time.sleep(0.4)
    return None


def _resolve_out_path(room_name: str, out: str | None, date: str | None) -> Path:
    if out:
        return Path(out)
    folder = ROOM_DIR_NAME.get(room_name, room_name.replace(" ", ""))
    day = date or datetime.now().strftime("%Y%m%d")
    month = f"{day[:4]}-{day[4:6]}"
    return ARCHIVE_BASE / folder / month / f"{folder}_auto_{day}.txt"


def export_room_chat(room_name: str, out_path: Path) -> bool:
    """방 대화를 out_path로 무인 내보내기. 성공=파일 생성·비어있지 않음."""
    import warnings

    warnings.filterwarnings("ignore")
    import kakao_report_sender as s
    from pywinauto import Application

    ensure_kakao_foreground()

    # 방 열기 + 포커스(창 겹침 극복 핵심)
    try:
        main = s.find_kakao_main_window()
        room = s.open_room_via_search(main, room_name)
        time.sleep(1.0)
        s.focus_window(room, room_name)
        time.sleep(0.5)
    except Exception as e:
        log(f"[export] 방 열기/포커스 실패({room_name}): {type(e).__name__}: {e}")
        return False

    # Ctrl+S → '다른 이름으로 저장' 대화상자
    # 방 창이 아직 활성화되기 전(ElementNotEnabled)에 단축키를 보내면 예외로 스크립트가 통째로 죽는다.
    # 최근 20일 중 5일이 이 지점에서 실패했고(08-17·21·22·24·29), 그날 아침 다이제스트는 옛 내보내기로
    # 만들어졌다. 다시 포커스를 잡고 최대 3회 기다렸다 보낸다. 3회 모두 실패하면 예외 대신 False.
    for attempt in range(3):
        try:
            room.type_keys("^s")
            break
        except Exception as e:
            log(f"[export] Ctrl+S 미수신({attempt + 1}/3): {type(e).__name__}")
            if attempt == 2:
                log(f"[export] 방 창이 끝내 활성화되지 않음({room_name}) — 내보내기 건너뜀")
                return False
            try:
                s.focus_window(room, room_name)
            except Exception:
                pass
            time.sleep(1.5)

    dlg_h = _find_dialog("저장", timeout=8.0)
    if not dlg_h:
        log("[export] 저장 대화상자가 안 뜸(Ctrl+S 미반응) — 방 포커스 확인 필요")
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        app = Application(backend="win32").connect(handle=dlg_h)
        dlg = app.window(handle=dlg_h)
        dlg.child_window(class_name="Edit", found_index=0).set_edit_text(str(out_path))
        time.sleep(0.4)
        dlg.child_window(title_re="저장.*", class_name="Button").click_input()
    except Exception as e:
        log(f"[export] 저장 대화상자 조작 실패: {type(e).__name__}: {e}")
        return False

    # 같은 이름 존재 시 '덮어쓰기 확인' 팝업 → 예(&Y)
    confirm = _find_dialog("저장 확인", timeout=2.0, exclude=dlg_h) or _find_dialog(
        "확인", timeout=1.0, exclude=dlg_h
    )
    if confirm:
        try:
            capp = Application(backend="win32").connect(handle=confirm)
            capp.window(handle=confirm).child_window(
                title_re="예.*", class_name="Button"
            ).click_input()
            log("[export] 덮어쓰기 확인(예)")
        except Exception:
            try:
                import pyautogui

                pyautogui.press("enter")
            except Exception:
                pass

    time.sleep(1.5)
    ok = out_path.exists() and out_path.stat().st_size > 0
    size = out_path.stat().st_size if out_path.exists() else 0
    log(f"[export] {'성공' if ok else '실패'} — {out_path} ({size:,} bytes)")
    return ok


def main() -> int:
    if sys.platform != "win32":
        print("FAILED: Windows 전용")
        return 1
    ap = argparse.ArgumentParser(description="★운영부 카톡 대화 무인 내보내기")
    ap.add_argument("--room", default="★운영부", help="카톡 방 제목(기본 '★운영부')")
    ap.add_argument("--out", default=None, help="저장 전체경로 직접 지정(미지정 시 아카이브 오늘자)")
    ap.add_argument("--date", default=None, help="파일명 날짜 YYYYMMDD(기본 오늘)")
    # 방 이름 별칭 정본 = scripts/kakao_rooms.json 의 room_aliases (여기서 복제하지 않는다).
    # .bat 은 CP949 로 읽혀 한글 인자가 깨지므로 예약 실행은 이 별칭으로 부른다(2026-08-12 수리).
    ROOM_KEYS = json.loads((Path(__file__).resolve().parent / "kakao_rooms.json")
                           .read_text(encoding="utf-8")).get("room_aliases") or {}
    ap.add_argument("--room-key", dest="room_key", choices=sorted(ROOM_KEYS),
                    help="방 이름 ASCII 별칭(ops·mgr) — .bat 에서 부를 때 쓴다")
    args = ap.parse_args()
    room = ROOM_KEYS[args.room_key] if args.room_key else args.room

    out_path = _resolve_out_path(room, args.out, args.date)
    log(f"내보내기 시작 — 방='{room}' → {out_path}")

    # ★한 번 실패했다고 하루를 버리지 않는다 (2026-08-14 시토 · 배613 계열).
    #   실측 2026-08-14 07:30 — 두 방 모두 "카톡 검색창 활성화 실패(돋보기 클릭 후에도 Edit 못 찾음)"로
    #   한 번에 끝났다. 그 결과 아침 정리가 **하루 지난 8/12 내용으로 나갔고**(오늘 것을 못 읽었으니
    #   최근 완결일로 내려앉는다), 웰리가 08:05 에 손으로 다시 보내야 했다.
    #   원인은 화면 상태에 따라 갈리는 UI 조작이라 대개 잠깐 뒤엔 된다 — 그래서 세 번까지 다시 해 본다.
    #   ▸잠금 화면이면 세 번 다 실패한다(윈도우가 막는다). 그건 여기서 풀 수 없고, 그 사실이
    #     항로 회신칸에 "확인 못 함"으로 뜬다(hangro_board · 배613).
    #   ▸새 스크립트·새 감시기 0 — 이미 모든 호출이 지나가는 이 자리에만 넣는다(약속 L21).
    attempts = 3
    for i in range(1, attempts + 1):
        ok = export_room_chat(room, out_path)
        if ok:
            if i > 1:
                log(f"[export] {i}번째 시도에서 성공")
            print(f"DONE: 내보내기 완료 — {out_path}")
            return 0
        if i < attempts:
            wait = 5 * i
            log(f"[export] {i}/{attempts} 실패 — {wait}초 뒤 다시 시도")
            time.sleep(wait)
    print(f"FAILED: 내보내기 실패({attempts}회 전부) — 화면이 잠겨 있으면 여기서는 못 푼다. 로그 확인")
    return 1


if __name__ == "__main__":
    sys.exit(main())
