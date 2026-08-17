"""PC 잠금 여부 감지"""
import ctypes
import sys

# OpenInputDesktop: 잠금화면이면 NULL 반환
DESKTOP_SWITCHDESKTOP = 0x0100
hwnd = ctypes.windll.user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
if hwnd:
    ctypes.windll.user32.CloseDesktop(hwnd)
    print("UNLOCKED")
    sys.exit(0)
else:
    print("LOCKED")
    sys.exit(1)
