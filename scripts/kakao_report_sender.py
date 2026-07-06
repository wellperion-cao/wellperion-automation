# scripts/kakao_report_sender.py
# 카톡 매출보고 원클릭 3방 전송기 (2026-07-06 CTO, 배488)
#
# 배경: 카톡 그룹방은 공식 API 불가 → 카카오톡 PC 앱 UI 자동화(pywinauto+pywin32)로
#       텔레그램 9시 매출보고 이미지+캡션을 카톡 방(들)에 그대로 전달한다.
#       이미지 재생성 없음(텔레그램 사진 원본 그대로) · 시트 접근 불필요.
#
# 필수 사전 설치(1회, GM PC — 없으면 아래 _check_and_import_deps()가 자동 설치 시도):
#   pip install pywinauto pyautogui pyperclip pywin32 Pillow
#
# ══════════════════════════════════════════════════════════════════════════
# 안전장치(절대 준수 — 회장님방 등 오발송 금지):
#   --dry-run   : 방 열기 + 클립보드 세팅 + 입력창 미리보기(Ctrl+V)까지만 수행.
#                 Enter(실제 전송)는 어떤 경우에도 호출하지 않는다.
#   --only-room : 지정한 방 1개만 처리(전 방 순회 안 함) — 안전 검증 단계에서 사용.
#   기본 실행(옵션 없음)은 3방 실발송이므로, 첫 배포 검증 전엔 절대 임의 실행 금지.
# ══════════════════════════════════════════════════════════════════════════
#
# 실행 예:
#   1) 방 열기·미리보기만(전송 안 함):
#      python scripts\kakao_report_sender.py --image "C:\...\report.png" ^
#          --caption "7.6(월) 매출 및 운영사항 보고드립니다." --dry-run --only-room "웰페리온 운영부"
#   2) 안전한 방 1개 실발송 검증:
#      python scripts\kakao_report_sender.py --image "C:\...\report.png" ^
#          --caption "..." --only-room "웰페리온 운영부"
#   3) 3방 전체 실발송(검증 완료 후에만):
#      python scripts\kakao_report_sender.py --image "C:\...\report.png" --caption "..."
#
# 한계(정직히 기록): 카카오톡 PC 앱 UI(창 제목·검색창 UIA 트리)는 버전 업데이트로
#   바뀔 수 있어 취약하다. GM PC 켜짐·카톡 로그인·화면잠금해제가 전제.
#   방 검색은 이름 기반(좌표 하드코딩 최소화)이나, 카톡 버전에 따라 검색→열기
#   키 입력 시퀀스가 달라질 수 있음 — 최초 1회는 반드시 GM이 dry-run으로 확인.

from __future__ import annotations

import argparse
import io
import json
import subprocess
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
ROOMS_CONFIG = Path(__file__).resolve().parent / "kakao_rooms.json"
EVIDENCE_DIR = Path(__file__).resolve().parent / "poc-evidence"


# ══════════════════════════════════════════════════════════════════════════
# 의존 라이브러리 체크 — 없으면 pip install 1회 자동 시도, 실패 시 BLOCKED로 중단
# ══════════════════════════════════════════════════════════════════════════
_REQUIRED = ["pywinauto", "pyautogui", "pyperclip", "win32clipboard", "PIL"]


def _check_and_import_deps(_retried: bool = False) -> dict:
    missing = []
    mods: dict = {}
    for name in _REQUIRED:
        try:
            if name == "win32clipboard":
                import win32clipboard as _wc
                import win32con as _wcon
                mods["win32clipboard"] = _wc
                mods["win32con"] = _wcon
            elif name == "PIL":
                from PIL import Image as _im
                mods["Image"] = _im
            else:
                mods[name] = __import__(name)
        except ImportError:
            missing.append(name)

    if missing:
        if _retried:
            print(f"BLOCKED: 자동 설치 후에도 임포트 실패 — 수동 확인 필요: {missing}")
            sys.exit(1)
        pip_pkgs = {
            "pywinauto": "pywinauto",
            "pyautogui": "pyautogui",
            "pyperclip": "pyperclip",
            "win32clipboard": "pywin32",
            "PIL": "Pillow",
        }
        pkgs = sorted({pip_pkgs[m] for m in missing})
        print(f"[kakao_report_sender] 누락된 라이브러리: {missing}")
        print(f"[kakao_report_sender] 설치 시도: pip install {' '.join(pkgs)}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", *pkgs],
                check=True, timeout=180,
            )
        except Exception as exc:
            print(f"BLOCKED: 자동 설치 실패 — 수동 설치 필요: pip install {' '.join(pkgs)} ({exc})")
            sys.exit(1)
        return _check_and_import_deps(_retried=True)

    return mods


_DEPS = _check_and_import_deps()
Image = _DEPS["Image"]
win32clipboard = _DEPS["win32clipboard"]
win32con = _DEPS["win32con"]
pyperclip = _DEPS["pyperclip"]
pyautogui = _DEPS["pyautogui"]

from pywinauto import Desktop  # noqa: E402


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_rooms(only_room: str | None) -> list[str]:
    if only_room:
        return [only_room]
    cfg = json.loads(ROOMS_CONFIG.read_text(encoding="utf-8"))
    return cfg.get("rooms", [])


def image_to_clipboard(image_path: Path) -> None:
    """PNG/JPG 등을 Windows 클립보드에 CF_DIB 비트맵으로 로드 (카톡 Ctrl+V 붙여넣기용)."""
    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "BMP")
    dib = buf.getvalue()[14:]  # BMP 파일헤더(14byte) 제거 → DIB만 클립보드에 남김
    buf.close()

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
    finally:
        win32clipboard.CloseClipboard()


def find_kakao_main_window():
    """카카오톡 메인창(친구/채팅 목록) 탐색. 실행 안 돼 있으면 예외."""
    candidates = Desktop(backend="uia").windows(title_re=".*카카오톡.*", top_level_only=True)
    for w in candidates:
        if w.window_text().strip() == "카카오톡":
            return w
    if candidates:
        return candidates[0]
    raise RuntimeError("카카오톡 메인창을 찾지 못함 — 앱이 실행 중인지 확인 필요")


def open_room(main_win, room_name: str, timeout: float = 15.0):
    """메인창 상단 검색으로 room_name 검색 → 첫 결과 열기 → 해당 채팅방 창 반환."""
    main_win.set_focus()
    time.sleep(0.3)

    edits = main_win.descendants(control_type="Edit")
    if not edits:
        raise RuntimeError(f"[{room_name}] 카카오톡 검색창(Edit)을 찾지 못함")
    search_box = edits[0]
    search_box.click_input()
    time.sleep(0.2)
    search_box.type_keys("^a", pause=0.05)  # 기존 검색어 있으면 전체선택
    search_box.type_keys(room_name, with_spaces=True, pause=0.03)
    time.sleep(0.8)  # 검색 결과 렌더 대기
    search_box.type_keys("{DOWN}", pause=0.1)  # 첫 결과 하이라이트
    time.sleep(0.2)
    search_box.type_keys("{ENTER}", pause=0.1)  # 채팅방 열기

    # 새 채팅방 창이 뜰 때까지 폴링 (제목에 room_name 포함하는 최상위 창, 메인창 제외)
    deadline = time.time() + timeout
    room_win = None
    while time.time() < deadline:
        found = Desktop(backend="uia").windows(title_re=f".*{room_name}.*", top_level_only=True)
        for w in found:
            if w.window_text().strip() != "카카오톡":
                room_win = w
                break
        if room_win:
            break
        time.sleep(0.5)

    if room_win is None:
        raise RuntimeError(f"[{room_name}] 채팅방 창을 열지 못함(제목 매칭 실패, {timeout}초 대기)")

    room_win.set_focus()
    time.sleep(0.3)
    return room_win


def get_input_box(room_win, room_name: str):
    edits = room_win.descendants(control_type="Edit")
    if not edits:
        edits = room_win.descendants(control_type="Document")  # 일부 버전은 입력창=Document
    if not edits:
        raise RuntimeError(f"[{room_name}] 채팅 입력창을 찾지 못함")
    return edits[-1]  # 통상 하단 입력창이 마지막 요소


def paste_image_preview(room_win, room_name: str):
    """채팅 입력창 포커스 → Ctrl+V로 클립보드 이미지 붙여넣기(미리보기 표시). 전송(Enter)은 별도 호출 필요."""
    input_box = get_input_box(room_win, room_name)
    input_box.click_input()
    time.sleep(0.2)
    input_box.type_keys("^v", pause=0.1)
    time.sleep(1.2)  # 미리보기 렌더 대기
    return input_box


def send_enter(input_box) -> None:
    input_box.type_keys("{ENTER}", pause=0.1)


def clear_input(input_box) -> None:
    """dry-run 종료 시 미리보기/텍스트 잔여물 정리(방에 미전송 잔여물 방치 금지)."""
    try:
        input_box.type_keys("^a{DELETE}", pause=0.1)
    except Exception:
        pass


def paste_text(input_box, text: str) -> None:
    """캡션은 한글 포함 → type_keys 대신 클립보드 경유 붙여넣기(IME 조합 문제 회피)."""
    prev = None
    try:
        prev = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(text)
    time.sleep(0.1)
    input_box.type_keys("^v", pause=0.1)
    time.sleep(0.3)
    if prev is not None:
        try:
            pyperclip.copy(prev)
        except Exception:
            pass


def screenshot(room_win, room_name: str, tag: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in room_name if c not in '\\/:*?"<>|')
    path = EVIDENCE_DIR / f"kakao_send_{safe_name}_{tag}_{ts}.png"
    try:
        img = room_win.capture_as_image()
        img.save(str(path))
    except Exception as exc:
        log(f"[{room_name}] 창 캡처 실패({exc}) — 전체화면 캡처로 폴백")
        try:
            pyautogui.screenshot(str(path))
        except Exception as exc2:
            log(f"[{room_name}] 스크린샷 저장 실패(무시): {exc2}")
    return path


def send_to_room(room_name: str, image_path: Path, caption: str, dry_run: bool) -> None:
    log(f"── {room_name} 처리 시작 (dry_run={dry_run}) ──")
    main_win = find_kakao_main_window()
    room_win = open_room(main_win, room_name)
    image_to_clipboard(image_path)
    input_box = paste_image_preview(room_win, room_name)

    if dry_run:
        screenshot(room_win, room_name, "dryrun_preview")
        clear_input(input_box)
        log(f"[{room_name}] DRY-RUN: 미리보기까지 확인, Enter 전송 생략(안전)")
        return

    send_enter(input_box)  # 이미지 전송
    time.sleep(1.0)
    if caption:
        input_box = get_input_box(room_win, room_name)
        input_box.click_input()
        time.sleep(0.2)
        paste_text(input_box, caption)
        send_enter(input_box)  # 캡션 전송(이미지 다음 별도 메시지)
        time.sleep(0.5)

    screenshot(room_win, room_name, "sent")
    log(f"[{room_name}] 전송 완료")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="텔레그램 매출보고 이미지를 카톡 방(들)에 전송(카톡 PC 앱 UI 자동화)")
    ap.add_argument("--image", required=True, help="전송할 이미지 파일 경로")
    ap.add_argument("--caption", default="", help="함께 보낼 캡션 텍스트")
    ap.add_argument("--dry-run", action="store_true",
                     help="방 열기+클립보드+미리보기까지만, 실제 전송(Enter) 안 함")
    ap.add_argument("--only-room", default=None, help="지정한 방 1개만 처리(검증용)")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("BLOCKED: 이 스크립트는 Windows(카카오톡 PC 앱) 전용입니다.")
        return 1

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"BLOCKED: 이미지 파일을 찾을 수 없음: {image_path}")
        return 1

    rooms = load_rooms(args.only_room)
    if not rooms:
        print("BLOCKED: 전송 대상 방이 없음 (kakao_rooms.json 확인)")
        return 1

    log(f"대상 방 {len(rooms)}개: {rooms} / dry_run={args.dry_run}")

    failures = []
    for idx, room_name in enumerate(rooms):
        try:
            send_to_room(room_name, image_path, args.caption, args.dry_run)
        except Exception as exc:
            log(f"실패 [{room_name}]: {exc}")
            failures.append((room_name, str(exc)))
        if idx < len(rooms) - 1:
            time.sleep(2.0)  # 방 사이 지연

    if failures:
        print(f"BLOCKED: {len(failures)}개 방 실패 — {failures}")
        return 1

    print(f"DONE: {'DRY-RUN 검증' if args.dry_run else '전송'} 완료 — {len(rooms)}개 방")
    return 0


if __name__ == "__main__":
    sys.exit(main())
