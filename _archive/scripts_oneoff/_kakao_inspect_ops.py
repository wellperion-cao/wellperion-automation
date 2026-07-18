# -*- coding: utf-8 -*-
"""카카오톡 '운영부' 방 창 컨트롤 구조 진단 (일회성·읽기전용).
- 열려있는 모든 카톡 방 창(EVA_Window_Dblclk)을 먼저 나열
- 제목에 '운영부'가 들어간 창을 찾아 컨트롤 트리를 덤프 → 말풍선(대화)이 읽히는지 판정
- 아무것도 보내지 않음. 창의 글자만 들여다봄.
결과는 tmp/kakao_inspect_ops.txt 에 저장.
"""
import sys, io, os, traceback
import win32gui

os.makedirs("tmp", exist_ok=True)
buf = io.StringIO()
def out(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    buf.write(line + "\n")

# 1) 열린 모든 카톡 방 창 나열
out("=== 열린 카카오톡 방 창(EVA_Window_Dblclk) 목록 ===")
found = []
try:
    def enum(hwnd, acc):
        if win32gui.IsWindowVisible(hwnd):
            c = win32gui.GetClassName(hwnd)
            if c == "EVA_Window_Dblclk":
                acc.append((hwnd, win32gui.GetWindowText(hwnd)))
    win32gui.EnumWindows(enum, found)
    for hwnd, t in found:
        out(f"  hwnd={hwnd} title='{t}'")
except Exception as e:
    out("EnumWindows 실패:", e); out(traceback.format_exc())

# 2) 제목에 '운영부' 포함 창 선택 (없으면 안내)
target = None
for hwnd, t in found:
    if "운영부" in t:
        target = (hwnd, t); break
out(f"\n선택된 운영부 방 = {target}")

if target is None:
    out("  (운영부 방이 안 열려 있음 — 카톡에서 ★운영부 방을 '별도 창'으로 열어두고(더블클릭) 재실행)")
else:
    hwnd, title = target
    for backend in ("win32", "uia"):
        out(f"\n=== backend={backend}: '{title}' 컨트롤 트리 (말풍선 텍스트 노출 여부 판정) ===")
        try:
            from pywinauto import Desktop
            win_spec = Desktop(backend=backend).window(handle=hwnd)
            tmp = io.StringIO()
            old = sys.stdout; sys.stdout = tmp
            try:
                win_spec.print_control_identifiers(depth=8)
            finally:
                sys.stdout = old
            txt = tmp.getvalue()
            out(txt[:12000])
            if len(txt) > 12000:
                out(f"  ...(트리 {len(txt)}자 중 앞 12000자만 · 전체는 파일 참조)")
        except Exception as e:
            out(f"  backend={backend} 실패:", e); out(traceback.format_exc())

with open("tmp/kakao_inspect_ops.txt", "w", encoding="utf-8") as f:
    f.write(buf.getvalue())
out("\n[저장] tmp/kakao_inspect_ops.txt")
