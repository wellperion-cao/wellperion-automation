# scripts/kakao_report_sender.py
# 카톡 매출보고 원클릭 3방 전송기 (2026-07-06 CTO, 배488 / 확장: 창-제목 기반 재설계)
#
# 배경: 카톡 그룹방은 공식 API 불가 → 카카오톡 PC 앱 UI 자동화(pywinauto+pywin32)로
#       텔레그램 9시 매출보고 이미지+캡션을 카톡 방(들)에 그대로 전달한다.
#       이미지 재생성 없음(텔레그램 사진 원본 그대로) · 시트 접근 불필요.
#
# ══════════════════════════════════════════════════════════════════════════
# 방 찾기 방식 재설계(2026-07-06, 실측 기반) — 검색창 방식 폐기, 창-제목 방식 채택:
#   실측(win32gui.EnumWindows)으로 확인: **열려 있는 카톡 채팅방은 각각 독립된
#   최상위 창으로 존재**하며, 창 클래스=`EVA_Window_Dblclk`·창 제목=방 이름 그대로다.
#   (메인창도 클래스는 같으나 제목이 "카카오톡"이라 이름 불일치로 자연 제외됨.)
#   → 방을 "검색해서 여는" 대신 "이미 열려 있는 방 창을 제목으로 찾는" 방식이
#     훨씬 안정적이다(카톡 메인창 검색창 UIA 트리는 버전에 취약·find 실패 잦음).
#   **전제조건: 전송 대상 3방을 카톡에서 미리 열어(대화창을 띄워)둬야 한다.**
#   방이 안 열려 있으면 명확한 에러로 실패한다(자동으로 검색해 열려는 폴백은
#   최후수단으로만 시도 — 주 경로 아님, 실패해도 정상).
# ══════════════════════════════════════════════════════════════════════════
#
# 방별 캡션: kakao_rooms.json의 rooms[].prefix + --caption(원본 그대로) 조합.
#   예) 차의주 회장님: "회장님, 7.5(일) 매출 및 운영사항 보고드립니다."
#       웰페리온 관리부/운영부: "7.5(일) 매출 및 운영사항 보고드립니다." (prefix 없음)
#
# 이미지 소스 2가지 지원(택1):
#   --image PATH      : 이미지 경로 직접 지정(봇 콜백은 통상 이 방식 — 이미 archive 저장한 파일 재사용).
#   --from-folder      : 미지정 시 kakao_rooms.json의 archive_dir/YYYY-MM/ 에서
#                         오늘 날짜 파일(웰페리온_일일보고_YYYYMMDD.png)을 자동 선택.
#
# 필수 사전 설치(1회, GM PC — 없으면 아래 _check_and_import_deps()가 자동 설치 시도):
#   pip install pywinauto pyautogui pyperclip pywin32 Pillow
#
# ══════════════════════════════════════════════════════════════════════════
# 안전장치(절대 준수 — 회장님방 등 오발송 금지):
#   --dry-run   : 방 창 탐색+포커스+클립보드 세팅+이미지 붙여넣기(팝업 뜨는 것까지)만
#                 수행. 전송 트리거(팝업 캡션칸 Enter)는 어떤 경우에도 호출하지 않고,
#                 팝업은 Escape로 직접 닫아 방에 잔여물을 남기지 않는다.
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
#   4) 이미지 직접 지정 없이 오늘자 archive 파일 자동 사용:
#      python scripts\kakao_report_sender.py --from-folder --caption "..." --dry-run --only-room "웰페리온 운영부"
#
# 한계(정직히 기록): 창-제목 방식이라도 카카오톡 PC 앱 UI(창 클래스·팝업 구조)는
#   버전 업데이트로 바뀔 수 있어 취약하다(2026-07-06 실측 기준). GM PC 켜짐·카톡
#   로그인·화면잠금해제·**전송 대상 3방이 미리 열려 있어야 함**이 전제.
#   검색 폴백(open_room_via_search)은 최후수단이며 그 자체도 취약함(당초 실패 원인과 동일).
#   2026-07-06 GM PC 라이브 검증: "웰페리온 운영부" 방 dry-run+실전송 둘 다 성공
#   확인(scripts/poc-evidence/ 스크린샷 증빙). 나머지 2방(회장님·관리부)은 오발송
#   방지를 위해 이번 세션에서 열지 않아 미검증 — GM이 3방을 열어둔 뒤 재확인 필요.

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
DEFAULT_ARCHIVE_DIR = ROOT / "1. AI학습자료_아카이브" / "10_매출보고"
ARCHIVE_FILENAME_FMT = "웰페리온_일일보고_%Y%m%d.png"


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
                import win32gui as _wg
                mods["win32clipboard"] = _wc
                mods["win32con"] = _wcon
                mods["win32gui"] = _wg
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
win32gui = _DEPS["win32gui"]
pyperclip = _DEPS["pyperclip"]
pyautogui = _DEPS["pyautogui"]

from pywinauto import Desktop  # noqa: E402

KAKAO_ROOM_WINDOW_CLASS = "EVA_Window_Dblclk"  # 메인창·채팅방 창 공통 클래스(제목으로 구분)
KAKAO_MAIN_WINDOW_TITLE = "카카오톡"


class RoomNotOpenError(RuntimeError):
    """대상 방의 채팅창이 카톡에서 열려 있지 않을 때(창-제목 탐색 실패)."""


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_rooms_config() -> dict:
    return json.loads(ROOMS_CONFIG.read_text(encoding="utf-8"))


def _normalize_room(entry) -> dict:
    """rooms[] 항목을 {"name":..., "prefix":...} 로 정규화(구 형식=순수 문자열도 허용)."""
    if isinstance(entry, str):
        return {"name": entry, "prefix": ""}
    return {"name": entry.get("name", ""), "prefix": entry.get("prefix", "")}


def get_archive_dir(cfg: dict) -> Path:
    raw = cfg.get("archive_dir")
    return Path(raw).expanduser() if raw else DEFAULT_ARCHIVE_DIR


def load_rooms(cfg: dict, only_room: str | None) -> list[dict]:
    """전송 대상 방 목록 반환(각 항목: {"name", "prefix"}).

    --only-room 지정 시 kakao_rooms.json에서 이름이 일치하는 항목의 prefix를 그대로 쓰고,
    설정에 없는 이름이면 prefix="" 로 폴백(검증용 임시 방 이름 등)."""
    rooms = [_normalize_room(r) for r in cfg.get("rooms", [])]
    if only_room:
        for r in rooms:
            if r["name"] == only_room:
                return [r]
        return [{"name": only_room, "prefix": ""}]
    return rooms


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


def _enum_visible_top_level_windows() -> list[tuple[int, str, str]]:
    """(hwnd, title, class_name) 목록 — 보이는 최상위 창만."""
    result: list[tuple[int, str, str]] = []

    def _cb(hwnd, acc):
        if win32gui.IsWindowVisible(hwnd):
            acc.append((hwnd, win32gui.GetWindowText(hwnd), win32gui.GetClassName(hwnd)))

    win32gui.EnumWindows(_cb, result)
    return result


def find_room_window(room_name: str, timeout: float = 3.0):
    """열려 있는 카톡 채팅방 창을 제목 완전일치로 탐색(주 경로 — 실측 기반).

    실측(win32gui.EnumWindows): 카톡 채팅방은 각각 독립 최상위 창으로 존재하며
    클래스=EVA_Window_Dblclk·제목=방 이름 그대로. 메인창도 같은 클래스이나
    제목이 "카카오톡"이라 자연 제외된다. 못 찾으면 RoomNotOpenError
    (그 방이 카톡에서 열려 있지 않다는 뜻 — GM이 먼저 방을 열어둬야 함)."""
    deadline = time.time() + timeout
    while True:
        for hwnd, title, cls in _enum_visible_top_level_windows():
            if cls == KAKAO_ROOM_WINDOW_CLASS and title.strip() == room_name:
                return Desktop(backend="uia").window(handle=hwnd)
        if time.time() >= deadline:
            raise RoomNotOpenError(
                f"[{room_name}] 방 창이 안 열려 있음 — 카카오톡에서 그 방을 먼저 열어두세요"
                f"(채팅목록에서 더블클릭해 대화창을 띄운 상태여야 전송 가능합니다)."
            )
        time.sleep(0.5)


def focus_window(win, room_name: str) -> None:
    """포그라운드 전환. win32gui.SetForegroundWindow는 Windows 포그라운드 잠금으로
    막힐 수 있어(오류 183) pywinauto set_focus()(내부 AttachThreadInput 등 우회)를 쓴다."""
    try:
        win.set_focus()
    except Exception as exc:
        log(f"[{room_name}] set_focus 실패(계속 진행): {exc}")
    time.sleep(0.3)


# ── 폴백(최후수단) — 방 창이 안 열려 있을 때만 시도. 카톡 메인창 검색은
#    UIA 트리가 버전에 취약해 실패가 잦다(당초 실패 원인). 주 경로는 항상
#    find_room_window(이미 열린 방 창 제목 탐색)이며, 이 폴백은 보너스일 뿐이다.
def find_kakao_main_window():
    """카카오톡 메인창(친구/채팅 목록) 탐색. 실행 안 돼 있으면 예외."""
    candidates = Desktop(backend="uia").windows(title_re=".*카카오톡.*", top_level_only=True)
    for w in candidates:
        if w.window_text().strip() == "카카오톡":
            return w
    if candidates:
        return candidates[0]
    raise RuntimeError("카카오톡 메인창을 찾지 못함 — 앱이 실행 중인지 확인 필요")


def open_room_via_search(main_win, room_name: str, timeout: float = 15.0):
    """메인창 상단 검색으로 room_name 검색 → 첫 결과 열기 → 해당 채팅방 창 반환.
    (폴백 전용 — 취약함을 알고 최후수단으로만 사용)"""
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

    # 새 채팅방 창이 뜰 때까지 폴링(주 경로와 동일하게 창-제목 완전일치로 확인)
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd, title, cls in _enum_visible_top_level_windows():
            if cls == KAKAO_ROOM_WINDOW_CLASS and title.strip() == room_name:
                room_win = Desktop(backend="uia").window(handle=hwnd)
                focus_window(room_win, room_name)
                return room_win
        time.sleep(0.5)

    raise RuntimeError(f"[{room_name}] 채팅방 창을 열지 못함(검색 폴백도 실패, {timeout}초 대기)")


def get_input_box(room_win, room_name: str):
    edits = room_win.descendants(control_type="Edit")
    if not edits:
        edits = room_win.descendants(control_type="Document")  # 일부 버전은 입력창=Document
    if not edits:
        raise RuntimeError(f"[{room_name}] 채팅 입력창을 찾지 못함")
    return edits[-1]  # 통상 하단 입력창이 마지막 요소


def paste_image_preview(room_win, room_name: str):
    """채팅 입력창 포커스 → Ctrl+V로 클립보드 이미지 붙여넣기.

    실측(2026-07-06 라이브 확인): Ctrl+V는 메인 입력창에 인라인 미리보기를 넣는 게
    아니라 **별도 모달 "클립보드 이미지 전송" 팝업**(클래스=EVA_Window_Dblclk·제목 없음·
    캡션칸 Edit 자식 1개 보유, "전송" 버튼은 UIA 미노출 커스텀 컨트롤)을 띄운다.
    전송·취소는 이 팝업을 대상으로 해야 한다(원래 입력창 참조로 Enter를 보내면
    팝업이 아닌 엉뚱한 곳에 꽂혀 무반응이거나 포커스를 뺏을 수 있음 — 실측으로 확인)."""
    input_box = get_input_box(room_win, room_name)
    input_box.click_input()
    time.sleep(0.2)
    input_box.type_keys("^v", pause=0.1)
    time.sleep(1.2)  # 미리보기/팝업 렌더 대기
    return input_box


def find_clipboard_popup(timeout: float = 2.0):
    """Ctrl+V 후 뜨는 '클립보드 이미지 전송' 팝업 탐색(제목 없는 EVA_Window_Dblclk +
    캡션칸 Edit 자식으로 식별). 구버전 카톡이 팝업 없이 인라인 미리보기만 쓰는 경우엔
    None(호출측이 기존 입력창 경로로 폴백)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd, title, cls in _enum_visible_top_level_windows():
            if cls == KAKAO_ROOM_WINDOW_CLASS and title.strip() == "":
                try:
                    spec = Desktop(backend="uia").window(handle=hwnd)
                    if spec.descendants(control_type="Edit"):
                        return spec
                except Exception:
                    continue
        time.sleep(0.2)
    return None


def confirm_clipboard_popup(popup, room_name: str) -> None:
    """팝업 캡션칸에서 Enter로 전송 확정(실측 확인: "전송" 버튼은 UIA로 못 찾아
    캡션칸 Enter가 유일하게 접근 가능한 트리거)."""
    edits = popup.descendants(control_type="Edit")
    target = edits[0] if edits else popup
    target.click_input()
    time.sleep(0.1)
    target.type_keys("{ENTER}", pause=0.1)
    log(f"[{room_name}] 클립보드 팝업 전송 확정(Enter)")


def cancel_clipboard_popup(popup, room_name: str) -> None:
    """dry-run 종료 시 팝업을 실제 전송 없이 닫는다(Escape). 메인 입력창과는
    별개 창이라 clear_input만으론 안 닫힘 — 반드시 팝업 자체를 대상으로 처리."""
    try:
        win32gui.PostMessage(popup.handle, win32con.WM_KEYDOWN, win32con.VK_ESCAPE, 0)
    except Exception as exc:
        log(f"[{room_name}] 클립보드 팝업 취소(Escape) 실패(무시): {exc}")


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


def build_caption(room: dict, base_caption: str) -> str:
    """방별 prefix + 원본 캡션(그대로, 날짜 재계산 없음) 조합."""
    return f"{room.get('prefix', '')}{base_caption}"


def send_to_room(room: dict, image_path: Path, base_caption: str, dry_run: bool) -> None:
    room_name = room["name"]
    caption = build_caption(room, base_caption)
    log(f"── {room_name} 처리 시작 (dry_run={dry_run}, caption={caption!r}) ──")

    try:
        room_win = find_room_window(room_name)
        log(f"[{room_name}] 방 창 발견(창-제목 탐색 성공)")
    except RoomNotOpenError as exc:
        log(f"[{room_name}] 방 창 탐색 실패 — 검색 폴백 시도(최후수단): {exc}")
        try:
            main_win = find_kakao_main_window()
            room_win = open_room_via_search(main_win, room_name)
            log(f"[{room_name}] 검색 폴백으로 방 창 확보")
        except Exception:
            raise exc  # 원인은 "방이 안 열려 있음" — 폴백 실패는 부가정보일 뿐

    focus_window(room_win, room_name)
    image_to_clipboard(image_path)
    input_box = paste_image_preview(room_win, room_name)
    popup = find_clipboard_popup()  # 실측: Ctrl+V는 보통 별도 "클립보드 이미지 전송" 팝업을 띄움

    if dry_run:
        screenshot(room_win, room_name, "dryrun_preview")
        if popup is not None:
            cancel_clipboard_popup(popup, room_name)  # 팝업은 별도 창 — Escape로 직접 닫아야 함
        else:
            clear_input(input_box)  # 팝업 없이 인라인 미리보기였던 구버전 카톡용 폴백
        log(f"[{room_name}] DRY-RUN: 미리보기까지 확인, 전송 생략(안전) — 캡션 미리보기: {caption!r}")
        return

    if popup is not None:
        confirm_clipboard_popup(popup, room_name)  # 이미지 전송(팝업 캡션칸 Enter)
    else:
        send_enter(input_box)  # 팝업 없는 구버전 카톡 폴백 — 입력창에서 바로 전송
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


def resolve_image_path(cfg: dict, args) -> Path:
    """--image 직접지정 우선, 없고 --from-folder면 archive_dir/YYYY-MM/에서 오늘자 파일 자동선택."""
    if args.image:
        return Path(args.image)
    archive_dir = get_archive_dir(cfg)
    today = datetime.now()
    candidate = archive_dir / today.strftime("%Y-%m") / today.strftime(ARCHIVE_FILENAME_FMT)
    return candidate


def main() -> int:
    ap = argparse.ArgumentParser(
        description="텔레그램 매출보고 이미지를 카톡 방(들)에 전송(카톡 PC 앱 UI 자동화)")
    ap.add_argument("--image", default=None, help="전송할 이미지 파일 경로(미지정 시 --from-folder 필요)")
    ap.add_argument("--from-folder", action="store_true",
                     help="--image 미지정 시 kakao_rooms.json의 archive_dir/YYYY-MM/에서 오늘 날짜 파일 자동 선택")
    ap.add_argument("--caption", default="", help="함께 보낼 원본 캡션 텍스트(방별 prefix는 자동 조합)")
    ap.add_argument("--dry-run", action="store_true",
                     help="방 열기+클립보드+미리보기까지만, 실제 전송(Enter) 안 함")
    ap.add_argument("--only-room", default=None, help="지정한 방 1개만 처리(검증용)")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("BLOCKED: 이 스크립트는 Windows(카카오톡 PC 앱) 전용입니다.")
        return 1

    if not args.image and not args.from_folder:
        print("BLOCKED: --image 또는 --from-folder 중 하나는 필수입니다.")
        return 1

    cfg = load_rooms_config()
    image_path = resolve_image_path(cfg, args)
    if not image_path.exists():
        print(f"BLOCKED: 이미지 파일을 찾을 수 없음: {image_path}")
        return 1

    rooms = load_rooms(cfg, args.only_room)
    if not rooms:
        print("BLOCKED: 전송 대상 방이 없음 (kakao_rooms.json 확인)")
        return 1

    room_names = [r["name"] for r in rooms]
    log(f"대상 방 {len(rooms)}개: {room_names} / image={image_path} / dry_run={args.dry_run}")

    failures = []
    for idx, room in enumerate(rooms):
        room_name = room["name"]
        try:
            send_to_room(room, image_path, args.caption, args.dry_run)
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
