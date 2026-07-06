# scripts/kakao_report_sender.py
# 카톡 매출보고 원클릭 3방 전송기 (2026-07-06 CTO, 배488 / 확장: 창-제목 기반 재설계
#                                    + 자동 방 열기 추가, 실측 기반)
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
#   이 창-제목 탐색이 **1차 경로**(이미 열려 있으면 즉시 성공, 가장 빠르고 안정적)다.
#
# 자동 방 열기 추가(2026-07-06, GM PC 라이브 실측 검증 완료) — PC 재부팅 시 방이
#   자동으로 안 열려 있는 문제 해결:
#   방 창을 못 찾으면(RoomNotOpenError) **카톡 메인창 검색으로 자동으로 방을 연 뒤**
#   전송을 진행한다(`open_room_via_search`). 실측으로 확인한 핵심 함정 2가지:
#     ①검색 Edit 컨트롤은 win32 클래스="Edit"로 실존하지만 비활성 시 rect가 0폭으로
#       붕괴돼 있어(GetWindowRect 폭=0) UIA descendants(control_type="Edit")로는 전혀
#       안 잡힌다(당초 실패 원인) → 메인창 우상단 돋보기 아이콘을 먼저 클릭해 검색을
#       활성화해야 Edit가 실제 폭을 가지고 나타난다(고정 픽셀 오프셋 클릭, §0-4 참조).
#     ②검색 Edit에 **Ctrl+A(전체선택)를 보내면 안 됨** — 실측 확인: 이 앱은 Ctrl+A를
#       편집칸 단위가 아닌 **전역 단축키("친구 추가" 다이얼로그 오픈)**로 가로챈다.
#       기존 텍스트 제거는 End→Shift+Home→Delete로만 한다(§0-5 참조).
#   방이 정말 안 열려 있으면(자동 열기까지 실패) 명확한 에러로 실패한다(RoomNotOpenError).
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
#   로그인·화면잠금해제가 전제. **방이 미리 열려 있지 않아도 자동으로 열도록
#   2026-07-06 확장**(open_room_via_search, GM PC 라이브 실측 검증 완료 — "김남욱"
#   방을 의도적으로 닫은 뒤 검색으로 자동 재오픈 성공 확인). 자동 열기도 카톡 PC 앱
#   UI(검색 아이콘 고정 픽셀 오프셋)에 의존해 버전 변경에 취약할 수 있음 — 실패 시
#   RoomNotOpenError로 명확히 실패하며 GM 수동 열기로 폴백.
#   2026-07-06 GM PC 라이브 검증: "웰페리온 운영부" 방 dry-run+실전송 둘 다 성공
#   확인(scripts/poc-evidence/ 스크린샷 증빙). 나머지 2방(회장님·관리부)은 오발송
#   방지를 위해 이번 세션에서 열지 않아 미검증 — GM이 3방을 열어둔 뒤 재확인 필요.
#   (자동 방 열기 자체는 "김남욱" 방으로 안전 검증 완료.)

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
import urllib.request
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

# 방 목록 편집 SSOT = T2 "카톡전송관리" 웹(GAS 시트). 로컬 kakao_rooms.json은 폴백 캐시.
# GAS scriptId=1VUMgK-vJvxCUO_mjQPpTFLjtv3NWWt8ESkCHH-l3QyCYrpBw2RXsYFFg(업무&결재 현황 GAS,
# 다른 여러 스크립트가 이미 공유하는 동일 exec URL — 신규 배포 아님). action=kakao_rooms_get.
KAKAO_ROOMS_GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)


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


def fetch_rooms_from_gas(timeout: float = 6.0) -> list[dict] | None:
    """T2 "카톡전송관리" 웹에서 GM이 편집한 방 목록을 GAS(kakao_rooms_get)로 조회.

    실패(네트워크 오류·GAS 다운·빈 목록 등) 시 None을 반환 — 호출측이 로컬
    kakao_rooms.json으로 안전하게 폴백한다(웹=편집 SSOT, 로컬=폴백 캐시)."""
    try:
        req = urllib.request.Request(KAKAO_ROOMS_GAS_URL + "?action=kakao_rooms_get")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if not payload.get("ok"):
            return None
        rooms = [_normalize_room(r) for r in (payload.get("rooms") or []) if r.get("name")]
        return rooms or None
    except Exception as exc:
        log(f"[kakao_rooms] GAS 방 목록 조회 실패(로컬 kakao_rooms.json으로 폴백): {exc}")
        return None


def _update_local_rooms_cache(rooms: list[dict]) -> None:
    """GAS 조회 성공 시 로컬 kakao_rooms.json의 rooms[]만 갱신(archive_dir 등 나머지 칸은 보존).
    GAS 장애 시에도 최근에 성공했던 목록으로 폴백할 수 있도록 캐시를 최신 상태로 유지한다."""
    try:
        cfg = load_rooms_config()
        cfg["rooms"] = rooms
        ROOMS_CONFIG.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        log(f"[kakao_rooms] 로컬 캐시 갱신 실패(무시, 전송은 계속 진행): {exc}")


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


# ── 자동 방 열기(2026-07-06 추가, GM PC 라이브 실측 검증 완료) — 방 창을 못 찾았을 때
#    카톡 메인창 검색으로 자동으로 방을 연다. §0-4/§0-5 실측 함정 참조.
def find_kakao_main_window() -> int:
    """카카오톡 메인창(친구/채팅 목록) hwnd 탐색. 실행 안 돼 있으면 예외.

    창-제목 탐색과 동일한 방식(_enum_visible_top_level_windows)으로 클래스=
    EVA_Window_Dblclk·제목="카카오톡" 완전일치를 찾는다. hwnd(int)를 반환하는 이유:
    검색 Edit 활성화 여부 판정에 win32 EnumChildWindows가 필요해 uia
    WindowSpecification보다 hwnd가 다루기 쉽다(open_room_via_search 참조)."""
    for hwnd, title, cls in _enum_visible_top_level_windows():
        if cls == KAKAO_ROOM_WINDOW_CLASS and title.strip() == KAKAO_MAIN_WINDOW_TITLE:
            return hwnd
    raise RuntimeError("카카오톡 메인창을 찾지 못함 — 앱이 실행 중인지 확인 필요")


def _find_visible_search_edit(main_hwnd: int):
    """메인창 자식 중 '검색이 활성화된' Edit 컨트롤(hwnd)을 찾는다.

    실측(2026-07-06): 카톡 검색 Edit는 평소(비활성) rect가 폭 0으로 붕괴돼 있어
    (GetWindowRect 좌우폭=0) UIA descendants(control_type="Edit")로는 아예 안 잡힌다
    (당초 "검색창 Edit 못 찾음" 실패 원인). win32 EnumChildWindows로 class_name="Edit"
    이면서 visible=True + 폭/높이 > 0인 것만 골라내면 활성화된 실제 검색창을 정확히
    특정할 수 있다(우상단 돋보기 아이콘 클릭 직후에만 폭>0으로 나타남)."""
    found = []

    def _cb(hwnd, _acc):
        try:
            if win32gui.GetClassName(hwnd) == "Edit" and win32gui.IsWindowVisible(hwnd):
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                if right > left and bottom > top:
                    found.append(hwnd)
        except Exception:
            pass
        return True

    win32gui.EnumChildWindows(main_hwnd, _cb, None)
    return found[0] if found else None


def _click_search_icon(main_hwnd: int) -> None:
    """메인창 우상단 돋보기(검색) 아이콘 클릭 — 검색 Edit 활성화 트리거.

    실측(2026-07-06): 이 아이콘은 UIA/win32 컨트롤 트리에 별도 버튼으로 노출되지
    않는 커스텀 그림 아이콘이라, 창 우상단 기준 고정 픽셀 오프셋으로 클릭한다
    (창 우측 끝에서 좌로 112px, 상단에서 아래로 57px 지점 — 라이브 실측·검증됨).
    창 크기가 달라져도 이 아이콘 행은 고정 높이 툴바라 오프셋이 유지될 것으로 본다."""
    left, top, right, _bottom = win32gui.GetWindowRect(main_hwnd)
    pyautogui.click(right - 112, top + 57)


def open_room_via_search(main_hwnd: int, room_name: str, timeout: float = 10.0):
    """카톡 메인창 검색으로 room_name을 찾아 자동으로 열고 그 채팅방 창을 반환한다.

    (2026-07-06 GM PC 라이브 실측 검증 완료 — "김남욱" 방을 의도적으로 닫은 뒤
    이 경로로 자동 재오픈 성공 확인.) 절차:
      1) 검색 Edit이 이미 활성 상태가 아니면 우상단 돋보기 아이콘 클릭으로 활성화
         (_click_search_icon) → _find_visible_search_edit로 재탐색.
      2) Edit 클릭해 포커스 확보 → 기존 텍스트는 End/Shift+Home/Delete로만 제거
         (★Ctrl+A 절대 금지 — 실측 확인: 이 앱은 Ctrl+A를 편집칸 전체선택이 아닌
         **전역 단축키("친구 추가" 다이얼로그 오픈)**로 가로챈다. 라이브에서 실제로
         이 다이얼로그가 뜬 것을 확인하고 Escape로 안전하게 닫아 회피했다).
      3) 클립보드 경유 Ctrl+V로 room_name 붙여넣기(paste_text와 동일 원칙 — 한글은
         type_keys로 직접 타이핑 시 IME 조합이 안 돼 깨진다).
      4) Enter로 최상단 검색결과 열기(라이브 실측: 정확히 일치하는 방 이름이면
         Enter 한 번으로 그 방이 곧바로 열림 — Down 키 불필요).
      5) 새 방 창(EVA_Window_Dblclk·제목=room_name **완전일치**)이 뜰 때까지 폴링.
         제목이 정확히 일치하는 창만 성공으로 인정한다 — 오발송 방지: 확인 안 된
         창에는 절대 진행하지 않는다(엉뚱한 방이 열려도 타임아웃으로 안전 실패)."""
    main_win = Desktop(backend="win32").window(handle=main_hwnd)
    focus_window(main_win, "카카오톡(메인창)")

    edit_hwnd = _find_visible_search_edit(main_hwnd)
    if edit_hwnd is None:
        _click_search_icon(main_hwnd)
        time.sleep(0.6)
        edit_hwnd = _find_visible_search_edit(main_hwnd)
    if edit_hwnd is None:
        raise RuntimeError(f"[{room_name}] 카톡 검색창 활성화 실패(돋보기 아이콘 클릭 후에도 Edit 못 찾음)")

    edit = Desktop(backend="win32").window(handle=edit_hwnd)
    edit.click_input()
    time.sleep(0.15)
    # 기존 검색어 제거(Ctrl+A 금지 — 위 함정 참조) — End→Shift+Home→Delete만 사용
    edit.type_keys("{END}", pause=0.05)
    edit.type_keys("+{HOME}", pause=0.05)
    edit.type_keys("{DELETE}", pause=0.05)
    time.sleep(0.15)

    prev_clip = None
    try:
        prev_clip = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(room_name)
    time.sleep(0.1)
    edit.type_keys("^v", pause=0.1)
    time.sleep(0.8)  # 검색 결과 렌더 대기
    if prev_clip is not None:
        try:
            pyperclip.copy(prev_clip)
        except Exception:
            pass

    edit.type_keys("{ENTER}", pause=0.1)  # 최상단 검색결과 열기

    # 새 채팅방 창이 뜰 때까지 폴링(주 경로와 동일하게 창-제목 완전일치로 확인)
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd, title, cls in _enum_visible_top_level_windows():
            if cls == KAKAO_ROOM_WINDOW_CLASS and title.strip() == room_name:
                room_win = Desktop(backend="uia").window(handle=hwnd)
                focus_window(room_win, room_name)
                return room_win
        time.sleep(0.4)

    raise RuntimeError(f"[{room_name}] 검색으로 열었으나 방 창을 확인 못함({timeout}초 대기)")


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
        log(f"[{room_name}] 방 창 발견(창-제목 탐색 성공, 이미 열려 있었음)")
    except RoomNotOpenError:
        log(f"[{room_name}] 방 창이 안 열려 있음 — 카톡 메인창 검색으로 자동 열기 시도")
        try:
            main_hwnd = find_kakao_main_window()
            room_win = open_room_via_search(main_hwnd, room_name)
            log(f"[{room_name}] 자동 열기 성공(검색)")
        except Exception as open_exc:
            raise RoomNotOpenError(
                f"방 '{room_name}'을 자동으로 열지 못함({open_exc}). 카톡에서 직접 열어두세요."
            ) from open_exc

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
    gas_rooms = fetch_rooms_from_gas()
    if gas_rooms:
        cfg["rooms"] = gas_rooms
        log(f"[kakao_rooms] T2 카톡전송관리(GAS) 방 목록 사용 — {len(gas_rooms)}개")
        _update_local_rooms_cache(gas_rooms)
    else:
        log(f"[kakao_rooms] GAS 미가용 — 로컬 kakao_rooms.json 방 목록으로 폴백 "
            f"({len(cfg.get('rooms', []))}개)")

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
