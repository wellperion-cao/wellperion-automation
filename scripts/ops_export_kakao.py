#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/ops_export_kakao.py — ★운영부 카톡 대화 무인 내보내기 (검증된 로직 승격)

원본: 스크래치패드 export_robust.py (2026-07-13 GM PC 라이브 성공 검증 — 어수선한 창 정리
→ 방 포커스 → ≡메뉴 동적 rect 탐색 → 대화 내용 hover → 대화 내보내기 → 저장창 Enter(기본값)
→ 생성 파일 탐색 → 아카이브 이동). 핵심 클릭 시퀀스·동적 rect·팝업 정리·Enter 저장·파일 이동
로직을 그대로 보존한다(대화창 타이핑 없음 — 포커스/금지문자 이슈 회피). 이 승격에서 추가한
것은 아래 4가지뿐:
  ① 방 창이 안 열려 있으면 억지로 진행하지 않고 실패 반환
  ② 생성된 txt 파일을 못 찾으면 실패 반환
  ③ 실패 시 텔레그램 OWNER 경보(scripts/generate_sales_report_image.py의 send_owner_alert 패턴 재사용)
  ④ stdout 계약: 성공 "EXPORT_OK: <경로>" / 실패 "EXPORT_FAIL: <이유>"

사용:
    C:\\Python314\\python.exe -u scripts\\ops_export_kakao.py

주의: 라이브 카카오톡 PC 앱 UI 조작(클릭·키 입력)이다 — 실행 시 실제 창을 건드린다.
      ★운영부 방이 닫혀 있으면 카톡 검색으로 직접 연다(kakao_report_sender.open_or_find_room 재사용, GM 2026-07-13).
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949) 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
MONTH_DIR = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★운영부" / datetime.now().strftime("%Y-%m")
HOME = Path.home()
SEARCH_DIRS = [
    ROOT / "1. AI자료_아카이브" / "11_카카오톡",
    HOME / "Documents",
    HOME / "Downloads",
    HOME / "Desktop",
]
ROOM_NAME_CONTAINS = "운영부"  # 방 창 제목에 포함되어야 하는 문자열(★ 운영부)
ENV_PATH = ROOT / "telegram_bot" / ".env"


def log(*a) -> None:
    print(" ".join(str(x) for x in a), flush=True)


def _load_env(path: Path) -> dict:
    """key=value .env 파싱(주석·빈줄 무시) — generate_sales_report_image.py와 동일 방식(직독)."""
    env: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except Exception as exc:
        log(f"[경고] .env 읽기 실패: {exc}")
    return env


def send_owner_alert(message: str) -> None:
    """OWNER 텔레그램 DM으로 실패 경보(best-effort — 경보 발송 자체 실패는 무시하고 계속 진행).
    scripts/generate_sales_report_image.py의 send_owner_alert와 동일 패턴."""
    try:
        import requests
        env = _load_env(ENV_PATH)
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        owner_id = env.get("OWNER_ID") or env.get("TELEGRAM_CHAT_ID", "")
        if not token or not owner_id:
            log("[경고] TELEGRAM_BOT_TOKEN/OWNER_ID(.env) 없음 — 경보 발송 생략")
            return
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(owner_id), "text": message},
            timeout=15,
        )
        if resp.status_code != 200 or not resp.json().get("ok", False):
            log(f"[경고] 경보 발송 실패: status={resp.status_code} body={resp.text[:200]}")
        else:
            log("OWNER 텔레그램 경보 발송 완료")
    except Exception as exc:
        log(f"[경고] 경보 발송 예외(무시): {exc}")


def close_dialogs(win32gui, win32con, pyautogui) -> None:
    # 열린 #32770(저장/에러) Esc/닫기
    for _ in range(4):
        dlgs = []

        def e(h, _):
            if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "#32770":
                dlgs.append(h)

        win32gui.EnumWindows(e, None)
        if not dlgs:
            break
        for h in dlgs:
            try:
                win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        time.sleep(0.6)
    pyautogui.press("esc")
    time.sleep(0.3)


def eva(win32gui):
    acc = []

    def e(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "EVA_Window_Dblclk":
            acc.append((h, win32gui.GetWindowText(h), win32gui.GetWindowRect(h)))

    win32gui.EnumWindows(e, None)
    return acc


def eva_menus(win32gui):
    acc = []

    def e(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "EVA_Menu":
            acc.append((h, win32gui.GetWindowRect(h)))

    win32gui.EnumWindows(e, None)
    return acc


def run_export() -> "tuple[bool, str]":
    """라이브 카톡 PC 앱 조작으로 ★운영부 대화 내보내기 실행. 반환: (성공여부, 성공시 저장경로/실패시 사유)."""
    import win32con
    import win32gui
    import pyautogui
    from pywinauto import Desktop

    MONTH_DIR.mkdir(parents=True, exist_ok=True)

    log("[0] 어수선한 저장/에러창 정리")
    close_dialogs(win32gui, win32con, pyautogui)

    # 방 찾기 + 잡팝업 닫기
    room = None
    for h, t, r in eva(win32gui):
        if ROOM_NAME_CONTAINS in t:
            room = h
        elif t.strip() == "" and (r[2] - r[0]) < 700:
            try:
                win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
    if not room:
        # 방이 닫혀 있으면 시토가 카톡 검색으로 직접 연다 (GM 2026-07-13) — kakao_report_sender 검증 로직 재사용
        log("[방] 창 없음 → 카톡 검색으로 자동 열기 시도")
        try:
            import kakao_report_sender as _krs
            _krs.open_or_find_room("★ 운영부")
            time.sleep(1.0)
            for h, t, r in eva(win32gui):
                if ROOM_NAME_CONTAINS in t:
                    room = h
                    break
        except Exception as e:
            log(f"[방] 자동 열기 실패: {e}")
    if not room:
        return False, f"'{ROOM_NAME_CONTAINS}' 방 창을 열지 못함(검색 자동열기도 실패 — 카톡 메인창 확인)"
    time.sleep(0.5)
    try:
        Desktop(backend="win32").window(handle=room).set_focus()
    except Exception as e:
        log("focus warn", e)
    L, T, R, B = win32gui.GetWindowRect(room)
    pyautogui.click((L + R) // 2, (T + B) // 2)
    time.sleep(0.5)  # 방 포커스

    # 기준시각(이후 생성 파일 탐색용)
    t0 = time.time()

    log("[1] ≡ → 대화 내용 → 대화 내보내기")
    pyautogui.click(R - 25, T + 57)
    time.sleep(1.2)
    menus = eva_menus(win32gui)
    if not menus:
        return False, "≡ 메뉴가 뜨지 않음"
    mh, (mL, mT, mR, mB) = menus[0]
    pyautogui.moveTo(mL + 50, mB - 78)
    time.sleep(1.5)
    subs = [m for m in eva_menus(win32gui) if m[0] != mh]
    if not subs:
        pyautogui.moveTo(mL + 50, mB - 78)
        time.sleep(1.5)
        subs = [m for m in eva_menus(win32gui) if m[0] != mh]
    if not subs:
        return False, "서브메뉴(대화 내용)가 뜨지 않음"
    sh, (sL, sT, sR, sB) = subs[0]
    pyautogui.click(sL + 45, sT + 22)
    time.sleep(2.0)

    # 저장창 뜨면 Enter(기본 이름·폴더)
    save = None

    def find_save(h, _):
        nonlocal save
        if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "#32770" and "저장" in win32gui.GetWindowText(h):
            save = h

    win32gui.EnumWindows(find_save, None)
    if not save:
        return False, "저장창이 뜨지 않음"
    log(f"[2] 저장창 hwnd={save} → Enter(기본값 저장)")
    try:
        win32gui.SetForegroundWindow(save)
    except Exception:
        pass
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(2.5)

    # 덮어쓰기/에러창 있으면 Enter 한번 더(예/확인)
    def foreground_others(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "#32770" and h != save:
            try:
                win32gui.SetForegroundWindow(h)
            except Exception:
                pass

    win32gui.EnumWindows(foreground_others, None)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.5)

    # 생성 파일 탐색(t0 이후 mtime, *.txt)
    log("[3] 생성 파일 탐색")
    cand = []
    for d in SEARCH_DIRS:
        for p in glob.glob(str(d / "*.txt")):
            try:
                if os.path.getmtime(p) >= t0 - 2:
                    cand.append(p)
            except Exception:
                pass
    cand.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    log(f"  후보 {len(cand)}개: {[os.path.basename(c) for c in cand[:5]]}")
    if not cand:
        return False, "저장 직후 생성된 txt 파일을 찾지 못함(저장 안 됐거나 다른 폴더에 저장됨)"

    src = cand[0]
    dst = MONTH_DIR / f"운영부_autoexport_{datetime.now().strftime('%Y%m%d')}.txt"
    shutil.move(src, str(dst))
    sz = dst.stat().st_size
    log(f"[성공] {os.path.basename(src)} → {dst} ({round(sz / 1024, 1)} KB)")
    return True, str(dst)


def main() -> int:
    if sys.platform != "win32":
        print("EXPORT_FAIL: Windows(카카오톡 PC 앱) 전용 스크립트입니다.")
        return 1

    try:
        ok, detail = run_export()
    except Exception as exc:
        ok, detail = False, f"예외 발생: {exc}"

    if ok:
        print(f"EXPORT_OK: {detail}")
        return 0

    msg = f"⚠️ ★운영부 카톡 대화 내보내기 실패 — {detail}"
    log(msg)
    send_owner_alert(msg)
    print(f"EXPORT_FAIL: {detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
