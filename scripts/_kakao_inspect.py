# -*- coding: utf-8 -*-
"""카카오톡 '웰페리온 운영부' 방 창 컨트롤 구조 진단 (일회성).
핵심: Desktop().windows()가 반환하는 Wrapper 객체엔 print_control_identifiers가 없음
(WindowSpecification 전용 메서드). 반드시 app.window(handle=hwnd) 스펙으로 접근할 것.
결과는 tmp/kakao_inspect.txt 에도 저장.
"""
import sys, io, os, traceback
import win32gui

os.makedirs("tmp", exist_ok=True)
buf = io.StringIO()
def out(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    buf.write(line + "\n")

ROOM_TITLE = "웰페리온 운영부"

# 1) win32gui EnumWindows로 방 창 hwnd 직접 확보 (클래스=EVA_Window_Dblclk, 제목=방 이름)
out(f"=== win32gui EnumWindows: '{ROOM_TITLE}' 창 탐색 ===")
target_hwnd = None
main_hwnd = None
try:
    def enum(hwnd, acc):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            c = win32gui.GetClassName(hwnd)
            if c == "EVA_Window_Dblclk":
                acc.append((hwnd, t, c))
    found = []
    win32gui.EnumWindows(enum, found)
    for hwnd, t, c in found:
        out(f"  hwnd={hwnd} [{c}] title='{t}'")
        if t.strip() == ROOM_TITLE:
            target_hwnd = hwnd
        elif t.strip() == "카카오톡":
            main_hwnd = hwnd
except Exception as e:
    out("EnumWindows 실패:", e); out(traceback.format_exc())

out(f"\n target_hwnd({ROOM_TITLE})={target_hwnd}, main_hwnd(카카오톡)={main_hwnd}")

# 2) app.window(handle=hwnd) 스펙으로 컨트롤 트리 출력 (Wrapper 아닌 WindowSpecification)
for backend in ("win32", "uia"):
    out(f"\n=== pywinauto backend={backend}: '{ROOM_TITLE}' 방 창 컨트롤 트리 (window spec) ===")
    if target_hwnd is None:
        out("  (target_hwnd 없음 — 방이 안 열려 있는 듯. 카톡에서 그 방을 열어두고 재실행)")
        continue
    try:
        from pywinauto import Desktop
        win_spec = Desktop(backend=backend).window(handle=target_hwnd)
        tmp = io.StringIO()
        old = sys.stdout; sys.stdout = tmp
        try:
            win_spec.print_control_identifiers(depth=6)
        finally:
            sys.stdout = old
        txt = tmp.getvalue()
        out(txt[:8000])
        if len(txt) > 8000:
            out(f"  ...(트리 {len(txt)}자 중 앞 8000자만)")
    except Exception as e:
        out(f"  backend={backend} 실패:", e); out(traceback.format_exc())

with open("tmp/kakao_inspect.txt", "w", encoding="utf-8") as f:
    f.write(buf.getvalue())
out("\n[저장] tmp/kakao_inspect.txt")
