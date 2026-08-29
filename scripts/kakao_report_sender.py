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
#
# 2026-07-21 트레이 최소화 하드닝(INC — 09:30 3방 전량 BLOCKED, 배9423):
#   원인: 카톡 메인창이 트레이 최소화(IsWindowVisible=0) 상태였고
#   find_kakao_main_window()가 '보이는 창'만 열거해 통째로 놓침 → 3방 전량 BLOCKED.
#   수리: find_kakao_main_window()에 폴백 경로 추가 — 전체 창 열거(_enum_all_top_level_windows)
#   로 숨은 메인창 hwnd 탐지 → ShowWindow(SW_SHOW+SW_RESTORE)로 자가복원.
#   focus_window()에 SetForegroundWindow 선행 추가, open_room_via_search()에서
#   검색 Edit 조작 직전 포그라운드 재확인 추가.
#   ★정직 한계(2026-07-21 기준 미검증 영역): 트레이 복원 직후 '백그라운드' 상태인
#   창에서 돋보기 클릭 → Edit 활성화 → 검색어 입력 순서가 포그라운드 잠금(Windows
#   보안 정책)으로 여전히 실패할 수 있다. 이 경로는 라이브 무인 환경에서 완전히
#   검증되지 않았다(실방 조작 위험 회피로 의도적 미검증).
#   ✅ 권장 주경로(가장 안정적): **3방 채팅창을 카톡에서 미리 열어두면**
#   find_room_window()가 창-제목 직접탐지로 즉시 성공하며 검색 플로우 전체를 우회한다.
#   09:30 무인 발송 전날 밤(또는 PC 부팅 직후) GM이 3방을 더블클릭해 열어두는 것이
#   가장 신뢰할 수 있는 운영 지침이다. 트레이 자가복원은 창이 닫힌 경우의 보조 경로.

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
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
DEFAULT_ARCHIVE_DIR = ROOT / "1. AI자료_아카이브" / "10_매출보고"
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


def _title_key(s: str) -> str:
    """방 이름 대조용 정규화 — 공백만 지운다.

    ★왜(2026-08-04 시토 · 배314·202). 방 찾기가 창 제목 완전일치였다. 그래서 카톡에서
    방 이름을 바꾸거나 별표 뒤 공백 한 칸이 다르면 **매출보고가 그 방을 못 찾고 조용히
    실패**한다 — 2026-08-01 「★ 운영부」가 정확히 그 사고였고, 그때는 목록 쪽에
    '공백 한 칸 있음' 주석을 다는 것으로 넘겼다(방마다 주석 = 다음 방에서 또 터진다).
    공백만 지우고 대조하면 「★관리부」·「★ 관리부」가 같은 방으로 잡혀 이 부류가 끝난다.
    ▸공백만 지운다(글자·기호는 그대로) — 현재 방 4개는 공백을 지워도 서로 안 겹친다.
    """
    return "".join(str(s or "").split())


# ★이름표만 바뀐 같은 방을 같은 방으로 본다 (2026-08-13 시토 · 배314).
#   배314 의 남은 일 = GM 이 카톡에서 「웰페리온 관리부」를 「★관리부」로 바꾸는 것. 그런데 지금
#   구조에서는 **이름을 바꾸는 순간과 목록을 고치는 순간이 같아야** 한다(안 맞으면 그 방 발송이
#   조용히 실패). 그 동시성 요구 때문에 이 배가 10일 멈춰 있었다.
#   그래서 대조를 한 단 더 둔다: 정확일치(공백 무시)로 못 찾으면, **꾸밈만 떼고** 다시 본다.
#   꾸밈 = 앞뒤 별표류와 회사 이름 접두사. 「웰페리온 관리부」·「★관리부」·「★ 관리부」가
#   모두 '관리부'로 모인다 → GM 이 언제 바꾸셔도 발송이 끊기지 않는다.
#   ▸안전장치: 느슨한 대조로 후보가 **2개 이상이면 고르지 않는다**(엉뚱한 방에 매출이 나가는
#     것이 발송 실패보다 나쁘다). 현재 4방은 꾸밈을 떼도 서로 겹치지 않는다 —
#     차의주회장님 · 관리부 · 운영부 · 부서장.
_ROOM_DECOR = ("★", "☆", "*", "웰페리온")


def _room_core_key(s: str) -> str:
    core = _title_key(s)
    for token in _ROOM_DECOR:
        core = core.replace(token, "")
    return core


KAKAO_MAIN_WINDOW_TITLE = "카카오톡"


class RoomNotOpenError(RuntimeError):
    """대상 방의 채팅창이 카톡에서 열려 있지 않을 때(창-제목 탐색 실패)."""


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── 실무진 못 읽는 내부 용어 경고 (GM 지적 2026-08-13) ──────────────────────
# notify_gm_progress.count_jargon(오늘 아침 추가)과 같은 패턴 — 채널만 카톡으로.
# 오늘 실제로 나간 두 통(임정은M·이정헌 소장님 앞)에서 뽑은 용어 + GM 이 예시로 든 것들.
# 막지 않는다 — 발신은 그대로, log() 로 경고만 남긴다(오탐 많으면 아무도 안 봄 → 목록은 좁게).
_STAFF_JARGON = {
    "staff_message": "실무진 전달문", "SSOT": "정본 자료", "dedup": "중복 방지",
    "릴레이": "전달", "등록분류": "회원 등록 종류", "재등록분류": "재등록 종류",
    "LOSS사유": "해지·이탈 사유", "원장불일치": "기록 불일치", "데이터 빈틈": "빠진 정보",
}
_SHIP_NO_RE = re.compile(r"배\d{2,5}")  # "배581" 류 배 번호 — 받는 사람은 무슨 뜻인지 모른다


def warn_jargon(text: str) -> list[str]:
    """경고만(차단 안 함). 반환 = 발견된 용어 목록(→바꿔 쓸 말 포함), 없으면 []."""
    hits = [f"{term}(→{sug})" for term, sug in _STAFF_JARGON.items() if term in text]
    if _SHIP_NO_RE.search(text):
        hits.append("배N(→무슨 작업인지 말로 풀어쓰기)")
    return hits


# ── 임정은M 건은 이경연 실장을 통해서만 (GM 지시 2026-08-16 · 약속 L24 실행판) ──────
# GM 원문: "임정은m건은 이경연실장 통해서만".
# 왜 코드로 박나: 같은 규칙이 약속 L24 에 글로만 있었고, 그 사이에도 임정은M 앞 요청이
#   그분이 계신 ★운영부 방으로 바로 나갈 뻔했다(2026-08-16 배413). 문서는 기계를 못 막는다(L02).
# 무엇을 막나: **요청·확인을 담은 글**이 임정은M 을 지목한 채, 그분이 멤버로 있는 방으로
#   나가는 것. 실장을 건너뛰게 되기 때문이다. 이름만 스쳐 지나가는 현황 공유(아침 다이제스트
#   등)는 막지 않는다 — 그건 답을 요구하지 않아 실장을 건너뛰는 일이 아니다.
# 어디로 보내야 하나: ★중간관리자 방(이경연 실장이 계시고 임정은M 은 안 계신다 —
#   kakao_rooms.json members 실측). 그 방에서 실장이 나눠 주신다.
# 방 멤버 명단은 kakao_rooms.json 이 정본이라 여기 베끼지 않는다(약속 L01).
_VIA_MANAGER_STAFF = "임정은"
_VIA_MANAGER_ROOM = "★중간관리자"
_VIA_MANAGER_ASK = ("부탁", "알려주", "주세요", "주시면", "확인해", "회신")
_VIA_MANAGER_SKIP_ENV = "WP_ALLOW_DIRECT_TO_STAFF"


def _room_members(room_name: str) -> str:
    """그 방의 멤버 문자열(kakao_rooms.json 정본). 못 찾으면 빈 문자열."""
    try:
        cfg = load_rooms_config()
    except Exception:
        return ""
    for r in cfg.get("all_rooms", []) or []:
        if _room_core_key(str(r.get("name") or "")) == _room_core_key(room_name):
            return str(r.get("members") or "")
    return ""


# 매일 정해진 시각에 나가는 현황 공유는 '지시'가 아니다 — 실장 경유 가드 대상이 아니다.
#   ▸왜 필요한가(2026-08-20 실측): 아침 「🌅 어제 운영부 정리」가 임정은M 이름과 함께
#     "…부탁", "주시면" 같은 낱말을 담자 가드가 통째로 막았다. 그 결과 ★운영부 방에
#     8/19·8/20 이틀 연속 아침 정리가 안 나갔고, 발신 로그엔 '전량 스킵'으로만 남아
#     아무도 몰랐다. GM 이 직접 "운영부방은 안되어있네?" 라고 물어서야 드러났다.
#   ▸가드의 목적은 **지시가 실장을 건너뛰지 않게** 하는 것이다. 정해진 시각의 현황 공유는
#     지시가 아니라 공유라 이 규칙의 대상이 아니다(약속 L24 — ★운영부 = 공유 전용).
#   ▸판정은 좁게 둔다: 아침 정리 머리글로 시작할 때만 면제한다. 사람이 손으로 쓰는 전달문은
#     이 머리글을 쓰지 않으므로 그대로 막힌다.
_ROUTINE_DIGEST_HEADS = ("🌅 어제 ", "📊 [하루 일과 정리]", "[오늘 하루 정리]")


def _is_routine_digest(text: str) -> bool:
    head = str(text or "").lstrip()
    return any(head.startswith(h) for h in _ROUTINE_DIGEST_HEADS)


def via_manager_violation(room_name: str, text: str) -> str | None:
    """실장을 건너뛰는 발신이면 차단 문구를 만든다(아니면 None)."""
    if _VIA_MANAGER_STAFF not in text:
        return None
    if _is_routine_digest(text):
        return None                      # 매일 나가는 현황 공유 — 지시가 아니다(아래 함수 주석 참조)
    if not any(k in text for k in _VIA_MANAGER_ASK):
        return None                      # 요청이 아닌 단순 언급 — 막지 않는다
    if _VIA_MANAGER_STAFF not in _room_members(room_name):
        return None                      # 그분이 없는 방 = 실장을 건너뛰지 않는다
    if os.environ.get(_VIA_MANAGER_SKIP_ENV) == "1":
        log(f"[{room_name}] {_VIA_MANAGER_SKIP_ENV}=1 — 실장 경유 가드 강행 통과")
        return None
    return (f"임정은M 건은 이경연 실장을 통해서만 나갑니다(GM 지시 2026-08-16). "
            f"'{room_name}' 방에는 임정은M 이 계셔서 실장을 건너뜁니다 — "
            f"'{_VIA_MANAGER_ROOM}' 방으로 보내고 첫 줄을 '이경연 실장님, …' 으로 쓰세요. "
            f"정말 이 방으로 보내야 하면 env {_VIA_MANAGER_SKIP_ENV}=1 로 다시 실행하세요.")


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
        rooms = [(h, t) for h, t, c in _enum_visible_top_level_windows()
                 if c == KAKAO_ROOM_WINDOW_CLASS]
        for hwnd, title in rooms:
            if _title_key(title) == _title_key(room_name):
                return Desktop(backend="uia").window(handle=hwnd)
        # 정확일치 실패 — 꾸밈만 뗀 이름으로 다시 본다(배314). 후보가 딱 하나일 때만 쓴다.
        want = _room_core_key(room_name)
        loose = [(h, t) for h, t in rooms if want and _room_core_key(t) == want]
        if len(loose) == 1:
            hwnd, title = loose[0]
            log(f"[{room_name}] 이름표가 달라 느슨한 대조로 찾음 → 실제 방 제목 '{title}' "
                f"(목록의 이름을 이 제목으로 고쳐두면 이 줄이 사라진다)")
            return Desktop(backend="uia").window(handle=hwnd)
        if len(loose) > 1:
            log(f"[{room_name}] 느슨한 대조 후보 {len(loose)}개 — 엉뚱한 방 발송을 막기 위해 "
                f"고르지 않는다: {[t for _h, t in loose]}")
        if time.time() >= deadline:
            raise RoomNotOpenError(
                f"[{room_name}] 방 창이 안 열려 있음 — 카카오톡에서 그 방을 먼저 열어두세요"
                f"(채팅목록에서 더블클릭해 대화창을 띄운 상태여야 전송 가능합니다)."
            )
        time.sleep(0.5)


def focus_window(win, room_name: str) -> None:
    """포그라운드 전환. win32gui.SetForegroundWindow는 Windows 포그라운드 잠금으로
    막힐 수 있어(오류 183) pywinauto set_focus()(내부 AttachThreadInput 등 우회)를 쓴다.

    2026-07-21 하드닝(INC — 트레이 최소화 메인창 09:30 3방 전량 BLOCKED): 트레이에서
    막 복원된 창처럼 포커스가 불안정한 상황에 대비해 SetForegroundWindow를 먼저
    best-effort로 시도(실패해도 무시)한 뒤 기존 set_focus() 경로를 그대로 쓴다.
    카톡이 이미 포그라운드에 떠 있는 기존 정상 경로는 사실상 no-op이라 영향 없음."""
    try:
        win32gui.SetForegroundWindow(win.handle)
    except Exception:
        pass  # 포그라운드 잠금 등으로 실패해도 무시 — set_focus()가 주 경로
    try:
        win.set_focus()
    except Exception as exc:
        log(f"[{room_name}] set_focus 실패(계속 진행): {exc}")
    time.sleep(0.3)


# ── 자동 방 열기(2026-07-06 추가, GM PC 라이브 실측 검증 완료) — 방 창을 못 찾았을 때
#    카톡 메인창 검색으로 자동으로 방을 연다. §0-4/§0-5 실측 함정 참조.
def _enum_all_top_level_windows() -> list[tuple[int, str, str]]:
    """(hwnd, title, class_name) 목록 — 가시성 무관 전체 최상위 창(트레이 최소화 포함).

    2026-07-21 하드닝(INC 실측): 카톡 메인창이 트레이로 최소화(IsWindowVisible=0)돼
    있으면 _enum_visible_top_level_windows()로는 찾지 못해 09:30 무인 3방 발송이
    전량 BLOCKED됐다(로그인 자체는 정상 — 그 hwnd는 존재). find_kakao_main_window()의
    폴백 전용(주 경로인 방-창 탐색·주 경로인 보이는 메인창 탐색은 그대로 둔다)."""
    result: list[tuple[int, str, str]] = []

    def _cb(hwnd, acc):
        acc.append((hwnd, win32gui.GetWindowText(hwnd), win32gui.GetClassName(hwnd)))

    win32gui.EnumWindows(_cb, result)
    return result


def find_kakao_main_window() -> int:
    """카카오톡 메인창(친구/채팅 목록) hwnd 탐색. 실행 안 돼 있으면 예외.

    창-제목 탐색과 동일한 방식(_enum_visible_top_level_windows)으로 클래스=
    EVA_Window_Dblclk·제목="카카오톡" 완전일치를 찾는다. hwnd(int)를 반환하는 이유:
    검색 Edit 활성화 여부 판정에 win32 EnumChildWindows가 필요해 uia
    WindowSpecification보다 hwnd가 다루기 쉽다(open_room_via_search 참조).

    2026-07-21 하드닝(INC — 09:30 3방 전량 BLOCKED, 실측 재현): 보이는 창에서 못
    찾으면 가시성 무관 전체 열거(_enum_all_top_level_windows)로 폴백해 같은 클래스·
    제목의 창을 찾는다. 트레이 최소화 상태였다면 ShowWindow(SW_SHOW)→
    ShowWindow(SW_RESTORE)로 자가복원한다(실측 확인: 이 두 호출로 IsWindowVisible이
    다시 1이 됨). 그래도 없으면 기존과 동일하게 RuntimeError로 명확히 실패한다."""
    for hwnd, title, cls in _enum_visible_top_level_windows():
        if cls == KAKAO_ROOM_WINDOW_CLASS and title.strip() == KAKAO_MAIN_WINDOW_TITLE:
            return hwnd

    for hwnd, title, cls in _enum_all_top_level_windows():
        if cls == KAKAO_ROOM_WINDOW_CLASS and title.strip() == KAKAO_MAIN_WINDOW_TITLE:
            log(f"[카카오톡(메인창)] 트레이 최소화 메인창 자가복원 시도(hwnd={hwnd})")
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            except Exception as exc:
                log(f"[카카오톡(메인창)] 자가복원 ShowWindow 실패(계속 진행): {exc}")
            time.sleep(0.8)
            log(f"[카카오톡(메인창)] 트레이 최소화 메인창 자가복원 완료(hwnd={hwnd})")
            return hwnd

    raise RuntimeError("카카오톡 메인창을 찾지 못함 — 앱이 실행 중인지 확인 필요")


def _dismiss_kakao_dialog() -> str | None:
    """카톡이 띄운 알림 다이얼로그(#32770)를 닫는다. 닫은 문구를 돌려준다(없으면 None).

    2026-08-15 실사고: "업데이트에 문제가 발생했습니다." 팝업이 떠 있어 메인창 조작이
    전부 막혔고, 아침 요약이 ★운영부·★중간관리자 두 방 모두 안 나갔다. 겉으로는
    "검색창 활성화 실패"로만 보여 진짜 원인을 찾는 데 시간이 걸렸다 — 이 함수가
    그 문구를 로그에 남긴다.
    ▸카톡 자기 다이얼로그만 닫는다(제목에 '카카오' 포함). 다른 앱 창은 건드리지 않는다.
    """
    closed = None
    targets: list[int] = []

    def _top(h, _):
        if win32gui.GetClassName(h) == "#32770" and win32gui.IsWindowVisible(h) \
                and "카카오" in win32gui.GetWindowText(h):
            targets.append(h)
        return True

    try:
        win32gui.EnumWindows(_top, None)
    except Exception:
        return None

    for h in targets:
        texts: list[str] = []

        def _child(c, _):
            if win32gui.GetClassName(c) == "Static":
                t = win32gui.GetWindowText(c).strip()
                if t:
                    texts.append(t)
            return True

        try:
            win32gui.EnumChildWindows(h, _child, None)
            win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
            time.sleep(1.0)
            closed = " / ".join(texts) or "(문구 없음)"
            log(f"[카톡] 알림 팝업을 닫고 진행합니다 — {closed}")
        except Exception as e:  # noqa: BLE001
            log(f"[카톡] 알림 팝업 닫기 실패: {e}")
    return closed


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


def _current_main_tab(main_hwnd: int) -> str:
    """메인창이 지금 어느 탭('친구'/'채팅'/'더보기')인지 UIA로 판별(픽셀·문구 의존 없음).

    실측(2026-07-10): 이 앱 헤더 텍스트는 UIA Text 컨트롤로 노출되지 않지만(검색 아이콘과
    동일한 커스텀 렌더링 문제), 탭별로 내부 뷰 컨트롤 이름(window_text)이 명확히 갈린다 —
    채팅탭="ChatRoomListView_*"·친구탭="ContactListView_*"·더보기탭="MoreView_*" 접두사로
    항상 등장(라이브 3탭 순환 실측 확인). 반환: "chat"/"friends"/"more"/"unknown"."""
    try:
        win = Desktop(backend="uia").window(handle=main_hwnd)
        names = [d.window_text() for d in win.descendants() if d.window_text()]
    except Exception:
        return "unknown"
    if any(n.startswith("ChatRoomListView") for n in names):
        return "chat"
    if any(n.startswith("ContactListView") for n in names):
        return "friends"
    if any(n.startswith("MoreView") for n in names):
        return "more"
    return "unknown"


def _ensure_chat_tab(main_hwnd: int, max_presses: int = 3) -> bool:
    """메인창을 '채팅' 탭으로 강제 전환(GM PC가 부팅 후 '친구' 탭으로 뜨는 문제 대응 — INC 진단).

    실측(2026-07-10): '친구' 탭 상태에서 방을 검색하면 채팅방이 아닌 사람(친구)을 찾아
    방을 못 여는 사례가 확인돼, 검색 전에 반드시 '채팅' 탭인지 확인 후 강제 전환한다.
    Ctrl+Tab = 탭 간 순환 이동(친구→채팅→더보기→친구, 3탭 순환 — 라이브 실측 확인.
    "채팅으로 바로 가기"가 아니라 "다음 탭"이라 이미 채팅탭이면 누르면 안 됨). 그래서 매번
    현재 탭을 먼저 확인(_current_main_tab)하고 채팅이 아닐 때만 1탭씩 순환시키며, 최대
    max_presses(=탭 개수)까지만 시도해 무한루프를 막는다. 메인창엔 Escape를 보내지 않는다
    (실측: 메인창에서 Escape는 트레이로 숨어버림 — 별도 확인된 함정)."""
    for _ in range(max_presses):
        if _current_main_tab(main_hwnd) == "chat":
            return True
        pyautogui.hotkey("ctrl", "tab")
        time.sleep(0.5)
    return _current_main_tab(main_hwnd) == "chat"


def open_room_via_search(main_hwnd: int, room_name: str, timeout: float = 10.0):
    """카톡 메인창 검색으로 room_name을 찾아 자동으로 열고 그 채팅방 창을 반환한다.

    (2026-07-06 GM PC 라이브 실측 검증 완료 — "김남욱" 방을 의도적으로 닫은 뒤
    이 경로로 자동 재오픈 성공 확인.) 절차:
      0) '채팅' 탭이 아니면 강제 전환(_ensure_chat_tab, 2026-07-10 추가 — '친구' 탭에서
         검색하면 방을 못 찾던 문제 대응).
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
    # 카톡 알림 팝업이 떠 있으면 메인창 조작이 전부 막힌다 — 방 열기 전에 한 번 걷어낸다
    # (2026-08-15 실사고: 업데이트 오류 팝업 하나로 아침 요약 2방이 통째로 안 나갔다).
    _dismiss_kakao_dialog()

    main_win = Desktop(backend="win32").window(handle=main_hwnd)
    focus_window(main_win, "카카오톡(메인창)")

    if not _ensure_chat_tab(main_hwnd):
        log(f"[{room_name}] '채팅' 탭 전환 실패(순환 3회 시도) — 검색 계속 시도(폴백)")

    edit_hwnd = _find_visible_search_edit(main_hwnd)
    if edit_hwnd is None:
        _click_search_icon(main_hwnd)
        time.sleep(0.6)
        edit_hwnd = _find_visible_search_edit(main_hwnd)
    if edit_hwnd is None:
        raise RuntimeError(f"[{room_name}] 카톡 검색창 활성화 실패(돋보기 아이콘 클릭 후에도 Edit 못 찾음)")

    # 2026-07-21 하드닝: 실제 조작(검색 Edit 클릭) 직전에 메인창 포그라운드를 한 번 더
    # 확인한다 — 트레이 복원 직후·탭 순환 이후 포커스가 흔들릴 수 있음(이미 포그라운드인
    # 기존 정상 경로에는 영향 없는 재확인일 뿐).
    focus_window(main_win, "카카오톡(메인창)")
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
            if cls == KAKAO_ROOM_WINDOW_CLASS and _title_key(title) == _title_key(room_name):
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


CHAIRMAN_ROOM_NAME = "차의주 회장님"

# 회장님 방 본문 정제(2026-08-01 GM 지시) — northstar_reach.build_northstar_block()이
# 진척 10% 이하 항목을 자동으로 골라 낮은 순 2건("📉"줄)+"그 외 손 안 댄 것 N건"을
# 붙이는데, 무엇이 뽑힐지 사람이 안 보고 그대로 회장님 방에 나갔다(오늘 목욕탕 허가건이
# 뽑혀 GM 지적). 관리부·운영부 등 내부 방에서는 그대로 유용해 그쪽은 건드리지 않는다 —
# 회장님 방으로 나가는 본문에서만 뺀다.
_CLEVEL_NICKNAME_TO_TITLE = {
    "웰리": "AI CEO", "시우": "AI COO", "시토": "AI CTO",
    "시모": "AI CMO", "시포": "AI CPO", "시뽀": "AI CFO", "시로": "AI CHRO",
}


def _sanitize_for_chairman(text: str) -> str:
    """회장님 방 전용 정제. ① '📉' 줄·'그 외 손 안 댄 것' 줄 제거 ② 남는 본문에 내부
    AI 닉네임이 있으면 직함으로 치환(회장님 화면에 닉네임 노출 금지, 방어적 안전망 —
    현재는 ①에서 같이 빠지지만 이 필터가 앞으로 다른 줄에도 자동 적용된다)."""
    lines = [ln for ln in text.splitlines()
             if not ln.strip().startswith("📉") and "손 안 댄 것" not in ln]
    out = "\n".join(lines)
    for nick, title in _CLEVEL_NICKNAME_TO_TITLE.items():
        out = out.replace(nick, title)
    return out


# 회장님 방 평균% 정확성(2026-08-01 GM 정정) — 📋 운영계획 줄의 "평균 NN%"는 진척을
# 못 잰 항목(honesty.level=manual/observed/기타 — "정직하게 0%로 표기"일 뿐 실제로
# 안 했다는 뜻이 아님, status/monthly_ops_plan.json 실측 확인)까지 포함해 계산된
# 값이라 회장님께 그대로 내보내면 부정확하다. 신뢰 가능한 등급(measured=실측·
# basis=근거계산)만으로 다시 계산해 대체한다. 모르는 등급이 나와도 안전측(=제외)으로
# 떨어진다(allowlist 방식). 내부 방은 원본 그대로 둔다(_sanitize_for_chairman과
# 마찬가지로 회장님 방에서만 적용).
MONTHLY_PLAN_PATH = ROOT / "status" / "monthly_ops_plan.json"
_TRUSTED_HONESTY_LEVELS = {"measured", "basis"}
_AVG_LINE_RE = re.compile(r" · 평균 \d+%")


def _trusted_month_avg(mkey: str) -> "tuple[int, int, int] | None":
    """(신뢰평균%, 신뢰건수, 전체건수). 계획을 못 읽거나 신뢰 가능한 값이 하나도
    없으면 None(지어내지 않는다)."""
    try:
        plan = json.loads(MONTHLY_PLAN_PATH.read_text(encoding="utf-8"))
        objs = [o for o in (plan.get("months", {}).get(mkey, {}).get("objectives") or []) if isinstance(o, dict)]
        all_n = sum(1 for o in objs if isinstance(o.get("progress"), (int, float)))
        trusted = [o["progress"] for o in objs
                   if isinstance(o.get("progress"), (int, float))
                   and (o.get("honesty") or {}).get("level") in _TRUSTED_HONESTY_LEVELS]
        if not trusted:
            return None
        return round(sum(trusted) / len(trusted)), len(trusted), all_n
    except Exception:
        return None


def _fix_avg_for_chairman(text: str) -> str:
    """" · 평균 NN%" 조각을 신뢰 등급만의 평균으로 교체(제외된 건이 있으면 "(M건 기준)"
    표기). 신뢰 가능한 값이 없으면 조각째 뺀다. 본문 안 " · 평균 NN%" 등장 순서 =
    이번 달 블록 → 다음 달 블록(build_northstar_block 호출 순서와 동일)."""
    now = datetime.now()
    mkeys = iter([now.strftime("%Y-%m"), (now.replace(day=1) + timedelta(days=32)).strftime("%Y-%m")])

    def _sub(_m: "re.Match") -> str:
        stat = _trusted_month_avg(next(mkeys, ""))
        if not stat:
            return ""
        avg, trusted_n, all_n = stat
        suffix = f"({trusted_n}건 기준)" if trusted_n < all_n else ""
        return f" · 평균 {avg}%{suffix}"

    return _AVG_LINE_RE.sub(_sub, text)


# ── 존칭 보정(GM 지시 2026-08-26 — "카카오톡은 다 뒤에 님자를 붙여줬으면 좋겠어") ──
# 사람에게 나가는 글에서 직함 뒤 '님'이 빠지는 자리는 한 곳이 아니다(배 전달문·기한초과
# 알림·요약 카드가 각자 문장을 만든다). 문장을 만드는 자리마다 챙기면 새 발신 경로가
# 생길 때 또 빠진다 — 모든 카톡 발신이 지나가는 이 관문 하나에만 둔다(약속 L21).
# ▸이미 '님'이 붙은 것은 건드리지 않는다. '프로'는 프로그램·프로젝트에 걸리지 않게
#   뒤에 글자가 없을 때만 본다. 'M'·'AM'은 한글 이름 뒤에 붙은 것만 본다(임정은M님).
_HONORIFIC_RES = [
    re.compile(r"(?<=[가-힣])\s?(실장|소장|팀장|반장|원장|프로|부장|과장|주임|사원|대리|점장)(?![가-힣님])"),
    re.compile(r"(?<=[가-힣])(AM|GM|M)(?![A-Za-z가-힣님])"),
]


def add_honorifics(text: str) -> str:
    """이름·직함 뒤에 '님'이 빠졌으면 붙인다. 이미 붙어 있으면 그대로 둔다."""
    out = str(text or "")
    for rx in _HONORIFIC_RES:
        out = rx.sub(lambda m: m.group(0) + "님", out)
    return out


# ── 사람 방 발신 주체 가드(배 11070 ⑤ · 약속 L24 "사람 방 발신은 웰리 한 사람") ──
# ★중간관리자·★운영부는 사람이 읽는 방이다. GM 원문(2026-08-28 웰리 판정): "정기 자동
# 발신이 웰리를 안 거친다 — 틀(제목·블록·상한)이 확정된 것만 자동으로 두고 문구가
# 바뀌면 웰리 승인 뒤 나가게 가드를 건다." 여태 문서로만 있던 규칙을 모든 카톡 발신이
# 지나는 이 관문 하나에 넣는다(약속 L21 — 새 관문 안 만든다).
# ▸이미 틀이 확정된 정기 자동 발송(호출부가 --sender 로 자기 이름을 밝힌 것)은 그대로
#   통과한다 — 그때그때 사람이 즉흥으로 쓰는 글이 아니라 정해진 시각·형식의 현황 발신이다.
# ▸--sender 를 안 넘기면(기본값 "") 사람 방에서 막힌다 — 새 호출부가 생겨도 기본은 안전측.
HUMAN_APPROVAL_ROOMS = {"★중간관리자", "★운영부", "★부서장", "★운영+시설+지원+주차"}   # 약속 L24 — 사람 방 4곳 전부 웰리 경유(2026-08-29 확대)
AUTO_PIPELINE_SENDERS = {
    "아침정리다이제스트",   # send_ops_digest.py — 아침 정리 다이제스트(★운영부·★중간관리자)
    "매출보고",            # report_stream_3_mgmt.py·kakao_auto_daily_report.py·bot.py 카톡버튼
                          # — 09:30 매출·운영+인사 현황(예약·GM 수동버튼 두 갈래 모두 같은 보고)
    "중간관리자알림합본",   # daily_scheduler.run_mgmt_notice_digest — 17:00 알림성 합본
    "주간보고초안",        # daily_scheduler — 운영부 주간 보고 초안
    "아침요약카드",        # kakao_summary_card_auto.py — 07:30 경보·4지표 요약 카드(현재 킬스위치 OFF)
    "다이어트캠프정기발신", # daily_scheduler.run_diet_camp_morning — 07:00 「다이어트캠프 이승기
                          # 대표님」 방(배 11022 · GM 승인 2026-08-29). 대외 방이라 HUMAN_APPROVAL_ROOMS
                          # 밖이지만 정기 자동 발송은 전부 --sender 로 밝히는 관례를 그대로 따른다.
    # "업무판채움보드" 제거(GM 지시 2026-08-29 폐기) — ops_fill_board 전체 폐기.
    # ── 아래 4개(2026-08-29 · ★부서장·★운영+시설+지원+주차를 HUMAN_APPROVAL_ROOMS 에
    #    추가하며 신규) — status/kakao_auto_send_inventory.json 전수 등록부 대조로 이 두
    #    방에 실제로 자동 발신하는 호출부를 찾아 배선했다(회귀 위험 전수 폐쇄, eae230dc6 와
    #    같은 방식). ─────────────────────────────────────────────────────────
    "문의정리",            # report_stream_1_inquiry.py·daily_scheduler.py — 22:30/20:00
                          # 문의+컨택&등록 현황(★부서장) + 멤버십 몫(★운영부)
    "점검접수정리",         # report_stream_2_check.py·daily_scheduler.py — 22:30/20:00
                          # 시설·지원·주차 점검현황+종합접수현황 합본(★운영+시설+지원+주차)
    "강습업장접수",         # report_stream_2b_reception.py build_lesson_digest — 22:30/20:00
                          # 강습·업장 접수 기한초과분(★부서장)
    "접수전달",            # report_stream_2b_reception.py run_intake_relay — 신규 접수 부서별
                          # 실시간 전달(대상 방이 매번 달라 항상 이 이름으로 통과)
}
SENDER_WELLY = "웰리"

# 테스트 꼬리표 — 사람 방 절대 금지(2026-08-29 실사고 후속: 10:42 ★운영부에 테스트 발신
# + 10:43 정정문 두 통이 실무진에게 나갔다). 테스트는 업무보고방(--test 재경로)으로만 —
# GM 확정 규칙. 화이트리스트·웰리 표기와 무관하게 이 꼬리표가 붙으면 사람 방은 막는다.
_TEST_SENDER_RE = re.compile(r"테스트|test|tmp|샘플|smoke", re.IGNORECASE)


def _sender_gate_ok(room_name: str, sender: str) -> bool:
    """사람 방(HUMAN_APPROVAL_ROOMS)이 아니면 발신 주체와 무관하게 항상 통과.
    사람 방이면 웰리 본인이거나 이미 화이트리스트에 오른 자동 발송일 때만 통과.
    테스트 꼬리표(_TEST_SENDER_RE)는 어떤 경우에도 사람 방 불가."""
    if room_name not in HUMAN_APPROVAL_ROOMS:
        return True
    if _TEST_SENDER_RE.search(sender or ""):
        return False
    return sender == SENDER_WELLY or sender in AUTO_PIPELINE_SENDERS


def _selfcheck_sender_gate() -> None:
    assert _sender_gate_ok("★관리부", "") is True, "사람 방이 아니면 발신 주체 무관 통과"
    # 사람 방 4곳(약속 L24) 전부 — 주체 미상(빈 문자열)은 막히고, 웰리 본인은 항상 통과.
    for room in ("★중간관리자", "★운영부", "★부서장", "★운영+시설+지원+주차"):
        assert room in HUMAN_APPROVAL_ROOMS, f"{room} 이 사람 방 가드에서 빠졌다"
        assert _sender_gate_ok(room, "") is False, f"{room} — 주체 미상은 사람 방에서 막혀야 한다"
        assert _sender_gate_ok(room, "웰리") is True, f"{room} — 웰리는 항상 통과해야 한다"
    assert _sender_gate_ok("★운영부", "아침정리다이제스트") is True
    assert _sender_gate_ok("★운영부", "아무개") is False, "화이트리스트 밖 주체는 막혀야 한다"
    assert _sender_gate_ok("★부서장", "문의정리") is True
    assert _sender_gate_ok("★부서장", "강습업장접수") is True
    assert _sender_gate_ok("★운영+시설+지원+주차", "점검접수정리") is True
    assert _sender_gate_ok("★운영+시설+지원+주차", "접수전달") is True
    assert _sender_gate_ok("★부서장", "아무개") is False, "화이트리스트 밖 주체는 막혀야 한다"
    # 테스트 태그는 사람 방으로 못 간다(2026-08-29 실사고 후속) — 웰리 표기가 섞여도 금지.
    for room in ("★중간관리자", "★운영부", "★부서장", "★운영+시설+지원+주차"):
        for tag in ("테스트", "웰리테스트", "smoke-test", "tmp발신", "샘플카드"):
            assert _sender_gate_ok(room, tag) is False, f"{room} — 테스트 태그({tag})는 사람 방 금지"
    print("[selfcheck] _sender_gate_ok OK — 사람 방 4곳 + 테스트 태그 금지까지 확인")


# ── 명단 마스킹(GM 확정 2026-08-28 — "김남* 이렇게 하는건 어때? 연락처는 010-****-1531") ──
# 회원 명단(이름·연락처)이 카톡 방에 그대로 남으면 안 된다 — 전체 정보는 실무진이 현황
# 화면에 들어가 본다. 모든 카톡 발신이 지나가는 이 관문 하나에만 마스킹을 박는다(약속 L21).
# ▸전화번호는 형식(대시 유무) 상관없이 앞3자리·뒤4자리만 남기고 가운데를 ****로 가린다.
# ▸이름은 전화번호 바로 앞(명단 줄)에 붙은 것만 마지막 한 글자를 *로 가린다 — 자유 문장
#   속 사람 이름(보고서 본문 등)은 손대지 않는다.
# ▸이미 가려진 값(010-****-1531, 김남*)은 다시 건드리지 않는다: 전화 정규식은 가운데가
#   숫자일 때만 잡고, 이름 정규식은 뒤에 *가 이미 있으면 그 자리에서 멈춘다.
_PHONE_RE = re.compile(r"(?<!\d)(01[0-9])-?(\d{3,4})-?(\d{4})(?!\d)")
_NAME_BEFORE_PHONE_RE = re.compile(
    r"(?<![가-힣])([가-힣]{2,4})(?!\*)(?=\s*[:\-()]?\s*01[0-9]-\*{4}-\d{4})"
)
# 전화번호 앞에 오지만 이름이 아닌 낱말(2026-08-29 실측 오탐 — 「연락처 010-…」이 「연락*」로
# 망가짐). 뒤가 전화·번호·연락처로 끝나는 합성어(대표전화·전화번호·휴대전화 등)는 꼬리로 잡고,
# 나머지는 낱말 그대로 막는다. 이름 판정을 더 똑똑하게 만들지 않는다 — 명단 줄에서 실제로
# 전화 앞에 서는 비이름 낱말은 이 부류뿐이다(발신 로그 실측).
_NOT_A_NAME = {"연락처", "전화", "휴대폰", "핸드폰", "번호", "대표", "문의", "담당", "연락", "접수", "예약"}
_NOT_A_NAME_TAILS = ("전화", "번호", "연락처")


def _mask_name(m: "re.Match") -> str:
    word = m.group(1)
    if word in _NOT_A_NAME or word.endswith(_NOT_A_NAME_TAILS):
        return word
    return word[:-1] + "*"


# ── 회원 실명(전화 없는 명단 줄) 마스킹 (GM 승인 2026-08-29) ─────────────────────
# 실무진 이름 정본 = ssot/kpi.json (약속 L01 — 코드에 이름을 복제하지 않는다).
# ①「이름+직함」·「이름+M/AM」 짝 전수 스캔 ②팀리더·부서반장 표의 값이 이름뿐인 경우(편한별).
# 못 읽으면 빈 집합 = 그날은 실무진 이름도 가려질 수 있으나 회원 노출보다 낫다(안전측).
_STAFF_TITLE_RE = re.compile(
    r"(?<![가-힣])([가-힣]{2,4})(?=\s*(?:팀장|실장|소장|반장|과장|차장|원장|사원|주임|프로|매니저)"
    r"|(?:AM|M)(?![A-Za-z가-힣]))")
_STAFF_CACHE: "set[str] | None" = None


def _staff_names() -> "set[str]":
    global _STAFF_CACHE
    if _STAFF_CACHE is not None:
        return _STAFF_CACHE
    names: set[str] = set()
    try:
        d = json.loads((ROOT / "ssot" / "kpi.json").read_text(encoding="utf-8"))
        # 전수 스캔은 3자 이상만 — 2자 매칭은 산문 부스러기(경연·정은·여자 등)라 회원 이름과
        # 충돌해 마스킹 구멍이 된다. 실무진 정식 이름은 전원 3자다(2자 실무진이 생기면 dict 경로에 얹기).
        names.update(n for n in _STAFF_TITLE_RE.findall(json.dumps(d, ensure_ascii=False))
                     if len(n) >= 3)
        for sec, key in (("_팀리더_2026_08_25", "teams"), ("_부서반장_2026_08_26", "depts")):
            for v in ((d.get(sec) or {}).get(key) or {}).values():
                w = str(v).split()[0] if str(v).split() else ""
                if re.fullmatch(r"[가-힣]{2,4}", w):
                    names.add(w)
    except Exception:
        pass
    _STAFF_CACHE = names
    return names


_PURE_NAME_RE = re.compile(r"^[가-힣]{2,4}$")


def _mask_roster_names(text: str) -> str:
    """전화 없는 명단 줄의 회원 실명을 가린다(이경언→이경*).

    명단 줄 판정 기준: 「·」(U+00B7)로 구분된 불릿 줄에서 **첫 번째 순수 한글 2~4자 구획**만
    회원 이름으로 본다 — 문의정리 통의 두 명단 형태가 전부 이 꼴이다:
      ①「· 이름 · 종목(…) · 담당강사 [상태]」  ②「· [강습] 일시 · 이름 · 종목 · N일째 · …」
    뒤에 오는 순수 한글 구획(종목명 「바레」·담당 강사명)은 첫-구획 규칙으로 자연히 보호되고,
    첫 구획이라도 실무진 정본(_staff_names)에 있으면 통과시킨다. 자유 문장·「•」 불릿 줄은
    「·」 구분이 없어 애초에 안 걸린다."""
    staff = _staff_names()
    out_lines = []
    for line in text.split("\n"):
        if line.lstrip().startswith("·") and "·" in line.lstrip()[1:]:
            segs = line.split("·")
            for i, seg in enumerate(segs):
                w = seg.strip()
                if _PURE_NAME_RE.fullmatch(w):
                    if w not in staff:
                        segs[i] = seg.replace(w, w[:-1] + "*")
                    break   # 첫 순수 한글 구획까지만 본다 — 이름 자리는 하나뿐
            line = "·".join(segs)
        out_lines.append(line)
    return "\n".join(out_lines)


def mask_pii(text: str) -> str:
    """카톡 발신 명단 줄의 이름·연락처를 가린다. 이름=마지막 한 글자만 *,
    연락처=앞3자리·뒤4자리만 남기고 가운데 ****. 「연락처」·「전화」 같은
    비이름 낱말은 건드리지 않는다(_NOT_A_NAME). 전화 없는 「·」 명단 줄의
    회원 실명도 가린다(_mask_roster_names · 실무진 이름은 kpi.json 정본으로 통과)."""
    out = _PHONE_RE.sub(lambda m: f"{m.group(1)}-****-{m.group(3)}", str(text or ""))
    out = _NAME_BEFORE_PHONE_RE.sub(_mask_name, out)
    out = _mask_roster_names(out)
    return out


def _selfcheck_mask_pii() -> None:
    cases = [
        ("김남욱 010-1234-1531", "김남* 010-****-1531"),          # 3자 이름
        ("박민 010-2222-3333", "박* 010-****-3333"),               # 2자 이름
        ("남궁도경 010-4444-5555", "남궁도* 010-****-5555"),       # 4자 이름
        ("김남* 010-****-1531", "김남* 010-****-1531"),            # 이미 가려진 값(재적용 무변화)
        ("황보준 01012341531", "황보* 010-****-1531"),             # 대시 없는 형식
        ("이경연 실장님께 여쭙고 있습니다", "이경연 실장님께 여쭙고 있습니다"),  # 전화 없으면 이름 무영향
        # 비이름 낱말 오탐 금지(2026-08-29 실측 — 「연락처」가 「연락*」로 망가지던 것)
        ("연락처 010-1234-1531 입니다", "연락처 010-****-1531 입니다"),
        ("전화 010-1234-1531", "전화 010-****-1531"),
        ("대표 010-1234-1531", "대표 010-****-1531"),
        ("문의 010-1234-1531", "문의 010-****-1531"),
        ("대표전화 010-1234-1531", "대표전화 010-****-1531"),      # 합성어(꼬리 매칭)
        ("전화번호 010-1234-1531", "전화번호 010-****-1531"),
        # 비이름 낱말을 막아도 진짜 명단은 그대로 가려진다(회귀 0)
        ("담당 김남욱 010-1234-1531", "담당 김남* 010-****-1531"),
        # 전화 없는 명단 줄 — 회원 실명은 가리고(첫 순수 한글 구획), 실무진·종목명은 그대로(GM 승인 2026-08-29)
        ("· 이경언 · 성인강습(스쿼시)      · 이상훈  [컨택중]",
         "· 이경* · 성인강습(스쿼시)      · 이상훈  [컨택중]"),
        ("· [성인강습] 2026-08-01 10:14 · 이지수 · 바레 · 28일째 · 담당있음·컨택없음",
         "· [성인강습] 2026-08-01 10:14 · 이지* · 바레 · 28일째 · 담당있음·컨택없음"),
        ("· 이상훈 · 스쿼시 레인 안내", "· 이상훈 · 스쿼시 레인 안내"),          # 실무진(팀리더)은 통과
        ("· 이경* · 성인강습(스쿼시)", "· 이경* · 성인강습(스쿼시)"),           # 이미 가려진 값 무변화
        ("이경언 회원님이 문의 주셨습니다", "이경언 회원님이 문의 주셨습니다"),  # 자유 문장 무영향
        (" • 이경연 실장님 — 확인 부탁", " • 이경연 실장님 — 확인 부탁"),       # 「•」 불릿(아침 통) 무영향
    ]
    for src, want in cases:
        got = mask_pii(src)
        assert got == want, f"{src!r} → {got!r} (기대 {want!r})"
    print("[selfcheck] mask_pii OK — 비이름 낱말 오탐 금지 포함")


def _selfcheck_honorifics() -> None:
    cases = [
        ("이경연 실장 — 확인 부탁드립니다", "이경연 실장님 — 확인 부탁드립니다"),
        ("이경연 실장님께 여쭙고 있습니다", "이경연 실장님께 여쭙고 있습니다"),   # 중복 금지
        ("이연희 반장, 박남일 반장", "이연희 반장님, 박남일 반장님"),
        ("임정은M 확인", "임정은M님 확인"),
        ("윤병현AM 전달", "윤병현AM님 전달"),
        ("김태엽 프로 담당", "김태엽 프로님 담당"),
        ("프로그램 점검·프로젝트 일정", "프로그램 점검·프로젝트 일정"),          # 오탐 금지
        ("실장님 자리", "실장님 자리"),
    ]
    for src, want in cases:
        got = add_honorifics(src)
        assert got == want, f"{src!r} → {got!r} (기대 {want!r})"
    print("[selfcheck] add_honorifics OK")


def build_caption(room: dict, base_caption: str) -> str:
    """방별 prefix + 원본 캡션(그대로, 날짜 재계산 없음) 조합. 회장님 방은 발신 전
    _sanitize_for_chairman()·_fix_avg_for_chairman()을 거친다(다른 방은 무영향).
    마지막으로 모든 방 공통 명단 마스킹(mask_pii) + 존칭 보정(add_honorifics) +
    링크 공백 인코딩을 거친다."""
    from tg_outbound_log import encode_url_spaces
    text = base_caption
    if room.get("name") == CHAIRMAN_ROOM_NAME:
        text = _sanitize_for_chairman(text)
        text = _fix_avg_for_chairman(text)
    return encode_url_spaces(add_honorifics(mask_pii(f"{room.get('prefix', '')}{text}")))


# ══════════════════════════════════════════════════════════════════════════
# 발신 전 링크 검수(2026-08-27 GM 지시) — "실무진 카톡방은 검수 한 번 하고 보낸다".
# 2026-08-26 시포 발신에서 링크 두 개를 한 줄에 이어 붙여 첫 주소가 깨졌고(404),
# 실무진이 화면에 못 들어갔다. 사람이 매번 눈으로 보는 대신 관문에서 재고 보낸다.
# 여기 한 곳에만 둔다(약속 L21) — 발신하는 모든 경로가 이 함수를 지난다.
_LINK_RE = re.compile(r'https?://[^\s<>"\')]+')
_LINK_TIMEOUT = 6.0
_SKIP_LINK_CHECK_ENV = "WP_SKIP_LINK_CHECK"   # 급할 때 우회(값 1)
_LINK_CACHE: dict[str, int | None] = {}


def _link_status(url: str) -> int | None:
    """URL 응답 코드. 네트워크 오류·타임아웃은 None(판정 불가)."""
    if url in _LINK_CACHE:
        return _LINK_CACHE[url]
    import urllib.error
    import urllib.parse
    import urllib.request
    code: int | None = None
    try:
        # 우리 주소에는 한글 경로가 흔하다(.../지원부%20체계.html) — 그대로 요청하면
        # urllib 이 터져 '못 쟀음'으로 빠지고 죽은 링크가 그냥 통과한다. 먼저 인코딩한다.
        safe = urllib.parse.quote(url, safe="%/:=&?~#+!$,;'@()*[]")
        req = urllib.request.Request(safe, method="GET", headers={"User-Agent": "wellperion-linkcheck"})
        with urllib.request.urlopen(req, timeout=_LINK_TIMEOUT) as resp:
            code = int(resp.status)
    except urllib.error.HTTPError as e:
        code = int(e.code)
    except Exception:
        code = None      # 못 쟀으면 막지 않는다 — 발신을 멈추는 쪽이 더 손해다
    _LINK_CACHE[url] = code
    return code


def broken_links(text: str) -> list[str]:
    """발신 전 검수 — 못 여는 링크만 돌려준다(빈 목록 = 통과).

    ①한 줄에 링크가 둘이면 카톡이 첫 주소 뒤까지 먹어 깨진다 → 형식 위반으로 잡는다.
    ②나머지는 실제로 열어 본다. 4xx·5xx 면 깨진 것, 못 쟀으면(None) 통과시킨다.
    """
    if os.environ.get(_SKIP_LINK_CHECK_ENV) == "1":
        return []
    bad: list[str] = []
    for line in str(text or "").splitlines():
        urls = _LINK_RE.findall(line)
        if len(urls) > 1:
            bad.append(f"{urls[0]} (한 줄에 링크 {len(urls)}개 — 줄을 나눠 주세요)")
            continue
        for u in urls:
            code = _link_status(u)
            if code is not None and code >= 400:
                bad.append(f"{u} ({code})")
    return bad


def _selfcheck_broken_links() -> None:
    base = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/"
    two = f"강습: {base}lesson.html · 멤버십: {base}membership.html"
    assert broken_links(two), "한 줄에 링크 둘 — 잡아야 한다"
    assert not broken_links(f"👉 강습: {base}lesson.html"), "정상 링크는 통과해야 한다"
    assert broken_links(base + "없는페이지.html"), "404 는 잡아야 한다"
    print("[selfcheck] broken_links OK")


# ══════════════════════════════════════════════════════════════════════════
# 중복 발신 가드(2026-07-24, 배10008) — 같은 방 + 같은 내용의 발신이 짧은 시간 안에
# 두 번 들어오면 두 번째부터 차단한다.
#
# 배경: daily_scheduler.py(22:30/20:00, KAKAO_GO_STREAM2)와 kakao_daily_check_share.py
#   (23:00, 배10008로 삭제)가 서로 완전히 다른 코드 경로에서 같은 렌더 함수
#   (support_check_summary.build_summary_lines)의 결과를 같은 카톡방(★운영+시설+
#   지원+주차)에 각자 발송해 하루 두 번 중복 배달됐다. 뿌리는 "새 발신 경로를 켤 때
#   기존 경로가 있는지 확인하는 지점이 없음"(약속 L01) — 문서 경고(report_stream_2_
#   check.py docstring)만으로는 실제 사고를 못 막았다.
#
# 이 스크립트(kakao_report_sender.py)는 저장소의 모든 카톡 발신이 통과하는 **단일
# 관문**이라(daily_scheduler·kakao_daily_check_share·kakao_summary_card_auto 등 전부
# subprocess로 이 파일을 호출), 여기서 (방, 내용) 서명 기반 원장 검사를 하면 앞으로
# 어떤 새 발신 경로가 추가되더라도 자동으로 같이 방어된다(개별 스크립트마다 매번
# 새로 챙길 필요 없음 — 근본 위치에 1회 박음).
# ══════════════════════════════════════════════════════════════════════════
# ── 발신 계측(배99, 2026-07-25) — 카톡도 하루 단위로 셀 수 있게, 텔레그램과 같은
# 관문 로거(tg_outbound_log.log_outbound)를 channel='kakao'로 재사용해
# logs/kakao_sent-YYYY-MM-DD.log 에 실발송 1건=1줄 남긴다(L21 — 새 로거 신설 없음).
# 이 스크립트는 저장소의 모든 카톡 발신이 통과하는 단일 관문이라 여기 1곳이면 전량 계측된다.
# best-effort: 계측 실패가 실제 발신을 절대 막지 않는다.
try:
    from tg_outbound_log import log_outbound as _log_outbound
except Exception:
    def _log_outbound(*a, **k):
        pass

DEDUP_LEDGER_PATH = ROOT / "status" / "kakao_dedup_ledger.json"
DEDUP_WINDOW_SEC = float(os.environ.get("KAKAO_DEDUP_WINDOW_SEC", 7200))  # 2시간(22:30↔23:00류 30분 간격을 넉넉히 덮음)
SKIP_DEDUP_ENV = "SKIP_KAKAO_DEDUP_GUARD"


def _dedup_signature(room_name: str, text: str = "", image_path: Path | None = None) -> str:
    """(방, 본문[, 이미지 내용]) 조합의 서명. 이미지가 있으면 파일 내용까지 해시에 포함해
    "같은 이미지를 다른 파일명으로 두 번 보내는" 케이스도 같은 서명으로 잡는다."""
    h = hashlib.sha256()
    # 방 이름은 _room_core_key 로 정규화한다(2026-08-17 시토). 방 찾기는 이미 공백·별표·
    # 회사이름을 무시해 「★ 운영부」와 「★운영부」를 같은 방으로 보내는데, 중복 가드만
    # 원문을 키로 써서 두 방으로 봤다 — 표기가 다른 호출부가 하나라도 남아 있으면 같은
    # 내용이 같은 방에 두 번 나간다(실측 2026-08-15 ★운영부 두 표기 동시 사용).
    h.update(_room_core_key(room_name).encode("utf-8"))
    h.update(b"\x00")
    h.update((text or "").strip().encode("utf-8"))
    if image_path is not None:
        h.update(b"\x00")
        try:
            h.update(image_path.read_bytes())
        except Exception:
            h.update(str(image_path).encode("utf-8"))
    return h.hexdigest()[:24]


def _load_dedup_ledger() -> list[dict]:
    try:
        if DEDUP_LEDGER_PATH.exists():
            return json.loads(DEDUP_LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"[dedup] 원장 읽기 실패(무시, 빈 원장으로 계속): {exc}")
    return []


def _save_dedup_ledger(entries: list[dict]) -> None:
    try:
        DEDUP_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEDUP_LEDGER_PATH.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        log(f"[dedup] 원장 저장 실패(무시 — 가드는 best-effort, 발신 자체는 계속): {exc}")


def check_dedup(room_name: str, text: str = "", image_path: Path | None = None) -> bool:
    """True 반환 = 중복(발신 차단해야 함). False = 신규(정상 진행).

    판정만 한다 — 기록은 하지 않는다(배348: 실제 발송 전에 원장을 적으면 발송이 실패해도
    "보냄"으로 남아 재시도를 막는다). 성공 확정 후에는 record_dedup_sent()가 기록한다.
    우회: env SKIP_KAKAO_DEDUP_GUARD=1."""
    if os.environ.get(SKIP_DEDUP_ENV) == "1":
        return False
    sig = _dedup_signature(room_name, text, image_path)
    now = time.time()
    entries = [e for e in _load_dedup_ledger() if now - e.get("ts", 0) < DEDUP_WINDOW_SEC]

    hit = next((e for e in entries if e.get("sig") == sig), None)
    if hit:
        age_min = (now - hit["ts"]) / 60
        log(f"[dedup] 차단 — [{room_name}] 동일 내용이 {age_min:.0f}분 전에 이미 발신됨"
            f"(중복 발신 가드, 배10008). 의도된 재발송이면 env {SKIP_DEDUP_ENV}=1 로 우회.")
        _save_dedup_ledger(entries)  # 창 밖 항목 정리만 반영
        return True

    _save_dedup_ledger(entries)  # 창 밖 항목 정리만 반영(신규 기록은 없음)
    return False


def record_dedup_sent(room_name: str, text: str = "", image_path: Path | None = None) -> None:
    """실제 발송 성공이 확정된 뒤에만 호출 — 원장에 "보냄"을 기록한다(배348).
    dry-run 은 호출부에서 애초에 부르지 않는다. 우회 시(env)에는 기록도 생략.
    text 필드도 같이 남긴다 — check_near_dup(아래)의 유사도 판정용(2026-08-15 GM 지시)."""
    if os.environ.get(SKIP_DEDUP_ENV) == "1":
        return
    sig = _dedup_signature(room_name, text, image_path)
    now = time.time()
    entries = [e for e in _load_dedup_ledger() if now - e.get("ts", 0) < DEDUP_WINDOW_SEC]
    entries.append({
        "room": room_name, "sig": sig, "ts": now,
        "at_kst": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "text": (text or "").strip()[:2000],
    })
    _save_dedup_ledger(entries)


# ── 근접 중복(형식만 고친 재발송) 가드 (2026-08-15 GM 지시 · 중복 알림 정리) ──────────
# 실측 8/13 ★중간관리자 12분 사이 4통 — 본문에 스스로 "방금 보낸 것과 내용 같습니다.
# 줄 간격만…"이라고 적혀 있었다. 위 check_dedup(정확 일치, 2시간)은 한 글자만 달라도
# 못 잡는다 — 형식만 고쳐 다시 보내면 해시가 통째로 바뀌기 때문이다. 새 판정 로직을
# 만들지 않고 kungjjak_board.find_repeats 와 같은 낱말겹침 기준(_norm)을 재사용하고,
# 저장소도 새로 안 만들고 위 kakao_dedup_ledger.json 의 text 필드를 그대로 읽는다(약속 L21).
NEAR_DUP_WINDOW_SEC = float(os.environ.get("KAKAO_NEAR_DUP_WINDOW_SEC", 1800))  # 30분
NEAR_DUP_OVERLAP_RATIO = 0.7  # 짧은 쪽 낱말의 70% 이상 겹치면 "내용 같음"으로 본다


def _word_set(t: str) -> set:
    from kungjjak_board import _norm  # noqa: PLC0415  (낱말겹침 판정 재사용 — 새로 안 만듦)
    return _norm(t)


_NUM_TOKENS_RE = re.compile(r'\d{2,}')


def _num_tokens(t: str) -> frozenset:
    """2자리 이상 숫자 토큰 집합 — 접수ID·건수 같은 고유 식별자 추출용.
    ponytail: 단순 정규식. 복합 ID(RECEPTION-131) 도 분리 후 131만 잡혀 충분."""
    return frozenset(_NUM_TOKENS_RE.findall(str(t or '')))


def check_near_dup(room_name: str, text: str) -> tuple[bool, float]:
    """True = 30분 안에 같은 방으로 낱말이 크게 겹치는 내용을 이미 보냈다(형식만 고친
    재발송 의심). (판정, 겹침비율) 반환 — 판정만 하고 기록은 하지 않는다(기록은
    record_dedup_sent 가 이미 text 필드까지 같이 남긴다). 우회: env SKIP_KAKAO_DEDUP_GUARD=1."""
    if os.environ.get(SKIP_DEDUP_ENV) == "1":
        return False, 0.0
    wt = _word_set(text)
    if len(wt) < 3:  # 너무 짧은 메시지는 겹침 판정 자체가 불안정 — 스킵(오탐 방지)
        return False, 0.0
    nt = _num_tokens(text)
    now = time.time()
    for e in _load_dedup_ledger():
        if (_room_core_key(e.get("room")) != _room_core_key(room_name)
                or now - e.get("ts", 0) >= NEAR_DUP_WINDOW_SEC):
            continue
        ep = str(e.get("text") or "")
        # 숫자 토큰(접수번호·건수 등)이 서로 다르면 내용이 다른 메시지 — 형식만 고친 재발송이 아니다
        if nt and _num_tokens(ep) and nt != _num_tokens(ep):
            continue
        wp = _word_set(ep)
        if len(wp) < 3:
            continue
        overlap = len(wt & wp) / min(len(wt), len(wp))
        if overlap >= NEAR_DUP_OVERLAP_RATIO:
            return True, overlap
    return False, 0.0


# ══════════════════════════════════════════════════════════════════════════
# 회장님 방 "새 내용" 게이트(2026-08-01 GM 정정판) — ①안(매 회 GM 승인)은 폐기.
# GM: "매출보고는 계속 해야지" — 매일 발신은 평소대로 나간다. 막는 건 직전 발신에
# 없던 **새 종류의 줄(구성)**이 이번에 생겼을 때뿐이다("오늘은 새로운 내용이니까
# 미리 알려줬으면 좋았던거지"). 숫자·날짜·요일은 매일 바뀌는 게 당연하므로 그것만
# 다르면 그냥 나간다.
#
# 판정: 줄마다 숫자·요일·진행바를 지운 "줄 종류"의 집합을 만들어(_content_signature)
# 직전 발신 기준선(status/kakao_chairman_content_baseline.json, 새 파일 1개)과 비교.
# 새 종류가 있으면 이번 회차만 보류하고 GM 업무보고방(8254867551)에 미리보기+무엇이
# 새로운지 알린 뒤, **기준선을 즉시 이번 내용으로 갱신**한다 — 그래서 다음 회차는
# 자동으로 다시 정상 발신된다(사람이 매번 풀어줄 필요 없음). 새 폴러·새 프로세스 없음
# — 이 발신 관문 안에서 매 실행마다 1회 비교할 뿐이다.
# ══════════════════════════════════════════════════════════════════════════
CHAIRMAN_BASELINE_PATH = ROOT / "status" / "kakao_chairman_content_baseline.json"
_NUM_RE = re.compile(r"[0-9][0-9,.]*")
_BAR_RE = re.compile(r"[▓░]+")
_WEEKDAY_RE = re.compile(r"\([월화수목금토일]\)")


def _line_kind(line: str) -> str:
    """줄에서 매일 바뀌는 숫자·요일·진행바를 지우고 '구성'만 남긴다."""
    k = _WEEKDAY_RE.sub("(요일)", line.strip())
    k = _BAR_RE.sub("#bar#", k)
    return _NUM_RE.sub("#", k)


def _content_signature(text: str) -> list[str]:
    """줄 종류의 정렬된 목록 — 새 종류의 줄(섹션)이 생기면 이 목록이 바뀐다."""
    return sorted({_line_kind(ln) for ln in text.splitlines() if ln.strip()})


def _load_chairman_baseline() -> list[str]:
    try:
        if CHAIRMAN_BASELINE_PATH.exists():
            return json.loads(CHAIRMAN_BASELINE_PATH.read_text(encoding="utf-8")).get("kinds", [])
    except Exception as exc:
        log(f"[chairman-content] 기준선 읽기 실패(신규로 취급): {exc}")
    return []


def _save_chairman_baseline(kinds: list[str]) -> None:
    try:
        CHAIRMAN_BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHAIRMAN_BASELINE_PATH.write_text(
            json.dumps({"kinds": kinds, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        log(f"[chairman-content] 기준선 저장 실패(무시): {exc}")


# ══════════════════════════════════════════════════════════════════════════
# 실패를 조용히 넘기지 않는다 (배669 · 웰리 전달 2026-08-18 · GM 손 쓰게 만든 날 2026-08-19)
#   카톡 발신은 PC 앱 UI 자동화라 **화면이 잠겨 있거나 다른 창이 포그라운드를 쥐고 있으면**
#   통째로 실패한다. 실측 2건: 08-17 저녁 수집(ElementNotEnabled) · 08-19 09:32 매출보고
#   4방 전부(set_focus 거부 → 검색창 못 찾음). 그날 GM 이 4방을 손으로 보내셨다.
#   ▸웰리가 바란 것은 자동 잠금해제 같은 새 장치가 아니라 **'잠김이라 못 했다'가 눈에 띄게
#     남는 것**이다(약속 L21). 그래서 새 감시기를 만들지 않고 **이 관문의 실패 출구 한 곳**에만
#     붙인다 — 이 파일을 지나지 않는 카톡 발신은 없다.
#   ▸본문을 함께 실어 보낸다. 그래야 GM 이 그 자리에서 복사해 손으로 보낼 수 있다(폴백).
_FAIL_ALERT_BODY_CAP = 900


def _failure_reason(failures: list) -> str:
    """실패 메시지에서 사람이 읽는 사유 한 줄. 못 가르면 '원인 불명'이라 적는다(지어내지 않음)."""
    blob = " ".join(str(x) for pair in failures for x in pair).lower()
    if "no active desktop" in blob or "fail-safe" in blob or "failsafe" in blob:
        return "PC 화면이 잠겨 있어 카톡 창을 조작하지 못했습니다(세션 잠금·화면보호기)"
    if "elementnotenabled" in blob:
        return "카톡 창이 입력을 받지 않는 상태였습니다(다른 창·대화상자에 가림)"
    if "setforegroundwindow" in blob or "set_focus" in blob or "검색창" in blob or "찾지" in blob:
        return "카톡 창을 앞으로 띄우지 못했습니다(다른 창이 화면을 쥐고 있음)"
    return "원인 불명 — 아래 오류 원문을 봐 주세요"


def _notify_send_failure(failures: list, kind: str, body: str) -> None:
    """실패했을 때 GM 업무보고방으로 한 통. best-effort — 여기서 또 실패해도 발신 결과는 안 바꾼다."""
    try:
        agents_dir = str(ROOT / "wellperion-agents")
        if agents_dir not in sys.path:
            sys.path.insert(0, agents_dir)
        from telegram_notifier import TelegramNotifier
        rooms = " · ".join(str(name) for name, _err in failures)
        errs = "\n".join(f"  · {name}: {str(err)[:120]}" for name, err in failures)
        preview = (body or "").strip()[:_FAIL_ALERT_BODY_CAP]
        msg = (f"🔴 카톡 발신 실패 {len(failures)}개 방 ({kind})\n"
               f"{_failure_reason(failures)}\n"
               f"못 간 방: {rooms}\n{errs}\n\n"
               f"— 아래 본문을 그대로 복사해 보내실 수 있습니다 —\n{preview}")
        TelegramNotifier().send(msg)
        log(f"[fail-alert] 업무보고방 통보 완료 — {len(failures)}개 방")
    except Exception as exc:
        log(f"[fail-alert] 통보 실패(무시): {exc}")


def _send_chairman_preview(text: str, new_kinds: list[str]) -> None:
    """GM 업무보고방으로 '새 구성이 생겨 이번 회차를 보류했다'는 미리보기를 보낸다
    (best-effort — 실패해도 회장님 방 발신은 어차피 보류 상태이므로 안전)."""
    try:
        agents_dir = str(ROOT / "wellperion-agents")
        if agents_dir not in sys.path:
            sys.path.insert(0, agents_dir)
        from telegram_notifier import TelegramNotifier
        new_lines = "\n".join(f"  + {k}" for k in new_kinds)
        preview = (
            "⚠️ 새 내용이 포함돼 회장님 발신을 한 회 보류했습니다 — 확인해 주세요\n"
            f"새로 생긴 줄:\n{new_lines}\n\n{text}"
        )
        TelegramNotifier().send(preview)
    except Exception as exc:
        log(f"[chairman-content] 미리보기 발송 실패(무시): {exc}")


def chairman_content_allows(text: str) -> bool:
    """True=평소대로 발신 진행. False=새 구성 발견 — 이번 회차만 보류(미리보기 발송 +
    기준선 갱신, 다음 회차부터 자동 재개)."""
    kinds = _content_signature(text)
    baseline = _load_chairman_baseline()
    if not baseline:
        # 기준선이 아예 없으면(최초 실행) 비교 대상이 없다 — 매번 "전부 새 것"으로
        # 오판해 평소 발신까지 막는 것을 피하기 위해 기준선만 세우고 통과시킨다.
        _save_chairman_baseline(kinds)
        return True
    new_kinds = [k for k in kinds if k not in baseline]
    if new_kinds:
        _send_chairman_preview(text, new_kinds)
        # 합집합으로 누적한다(덮어쓰기 금지). 덮어쓰면 미리 승인해 둔 다른 문구
        # (밀린 회차 인사말·휴관일 안내문 등)가 평소 발송 한 번에 지워지고, 정작
        # 그 문구가 나가야 하는 날 다시 보류된다 — 2026-08-19 승인분 2종이 08-22
        # 정상 발송으로 지워진 것이 실제 사례다.
        _save_chairman_baseline(sorted(set(baseline) | set(kinds)))
        log(f"[chairman-content] 새 구성 {len(new_kinds)}건 발견 — 이번 회차 보류, 미리보기 발송, 기준선 갱신")
        return False
    return True


def open_or_find_room(room_name: str):
    """방 창-제목 탐색(주 경로) → 실패 시 카톡 메인창 검색으로 자동 열기(폴백).
    send_to_room·send_message_to_room 공용 — 방 열기 로직 중복 방지.

    ★자동 열기는 3번까지 다시 해 본다(2026-08-15 · 실사고). 07:36 아침 요약이
    "검색창 활성화 실패" 한 번으로 rc=1 로 끝났는데, 08:49 손 재실행은 한 번에 됐다 —
    화면 상태에 따라 갈리는 UI 조작이라 대개 잠깐 뒤엔 된다(kakao_export_chat.py 의
    3회 재시도와 같은 근거·같은 간격). 모든 방 발신이 이 함수를 지나므로 여기 한 곳에만
    넣는다(약속 L21). 잠금 화면이면 3번 다 실패한다 — 그건 여기서 못 푼다.
    되돌리기 = 아래 for 루프를 지우고 본문을 1회 시도로 되돌린다(git revert 가능)."""
    try:
        room_win = find_room_window(room_name)
        log(f"[{room_name}] 방 창 발견(창-제목 탐색 성공, 이미 열려 있었음)")
        return room_win
    except RoomNotOpenError:
        log(f"[{room_name}] 방 창이 안 열려 있음 — 카톡 메인창 검색으로 자동 열기 시도")
    attempts = 3
    for i in range(1, attempts + 1):
        try:
            main_hwnd = find_kakao_main_window()
            room_win = open_room_via_search(main_hwnd, room_name)
            log(f"[{room_name}] 자동 열기 성공(검색{f' · {i}번째 시도' if i > 1 else ''})")
            return room_win
        except Exception as open_exc:
            if i < attempts:
                wait = 5 * i
                log(f"[{room_name}] 자동 열기 실패 {i}/{attempts}({open_exc}) — {wait}초 뒤 다시 시도")
                time.sleep(wait)
            else:
                raise RoomNotOpenError(
                    f"방 '{room_name}'을 자동으로 열지 못함({open_exc} · {attempts}회 전부). "
                    "카톡에서 직접 열어두세요."
                ) from open_exc


def send_message_to_room(room: dict, base_message: str, dry_run: bool) -> tuple[bool, str]:
    """이미지 없이 텍스트만 전송(휴관일 안내문 등). 이미지 팝업 경로를 전혀 타지 않고
    채팅 입력창에 바로 paste_text → send_enter 한다.

    반환: (발송여부, 보류사유). 발송여부 True=실제 발송(또는 dry-run 진행), False=미발신.
    보류사유는 미발신일 때만 채워짐 — "chairman_gate"(회장님 방 새 내용 게이트) 또는
    "dedup"(중복 발신 가드). 둘을 한 문구로 뭉뚱그리면 호출측이 원인을 잘못 기록한다
    (2026-08-10: 새내용게이트 보류를 "중복 발신 가드" 로 잘못 적은 사고)."""
    room_name = room["name"]
    # 링크에 낀 공백을 %20 으로 — 카톡은 공백에서 링크를 끊어 앞부분만 눌리고 404 가 난다.
    # 정본 = tg_outbound_log.encode_url_spaces (텔레그램·카톡 두 관문이 같은 함수를 쓴다).
    from tg_outbound_log import encode_url_spaces
    text = encode_url_spaces(build_caption(room, base_message))
    log(f"── {room_name} 텍스트 전용 처리 시작 (dry_run={dry_run}, text={text!r}) ──")
    _jargon = warn_jargon(text)
    if _jargon:
        log(f"[{room_name}] ⚠ 실무진이 못 읽을 수 있는 말: {', '.join(_jargon)}")

    _via = via_manager_violation(room_name, text)
    if _via:
        log(f"[{room_name}] ⛔ {_via}")
        return False, "via_manager"

    _bad = broken_links(text)
    if _bad:
        log(f"[{room_name}] ⛔ 못 여는 링크 — 발신 보류: {' / '.join(_bad)}")
        return False, "broken_link"

    if room_name == CHAIRMAN_ROOM_NAME and not dry_run and not chairman_content_allows(text):
        return False, "chairman_gate"

    if check_dedup(room_name, text=text):
        log(f"[{room_name}] 중복 발신 가드로 스킵(전송 안 함)")
        return False, "dedup"

    _near, _ratio = check_near_dup(room_name, text)
    if _near:
        log(f"[{room_name}] 근접 중복 가드로 스킵(전송 안 함) — 30분 안 유사도 {_ratio:.0%} "
            f"내용 이미 발신됨(형식만 고친 재발송 의심). 의도된 재발송이면 env {SKIP_DEDUP_ENV}=1 로 우회.")
        return False, "near_dup"

    room_win = open_or_find_room(room_name)
    focus_window(room_win, room_name)
    input_box = get_input_box(room_win, room_name)
    input_box.click_input()
    time.sleep(0.2)
    paste_text(input_box, text)

    if dry_run:
        screenshot(room_win, room_name, "dryrun_message_preview")
        clear_input(input_box)  # 실제 전송 안 하고 미리보기 텍스트만 지워 잔여물 방지
        log(f"[{room_name}] DRY-RUN: 텍스트 미리보기까지 확인, 전송 생략(안전) — {text!r}")
        return True, ""

    send_enter(input_box)
    time.sleep(0.5)
    screenshot(room_win, room_name, "message_sent")
    log(f"[{room_name}] 텍스트 전송 완료")
    record_dedup_sent(room_name, text=text)
    _log_outbound(text, chat_id=room_name, source="kakao_report_sender.message",
                  ok=True, kind="message", channel="kakao")
    return True, ""


def send_to_room(room: dict, image_path: Path, base_caption: str, dry_run: bool) -> tuple[bool, str]:
    """반환: (발송여부, 보류사유) — send_message_to_room과 동일 계약."""
    room_name = room["name"]
    caption = build_caption(room, base_caption)
    log(f"── {room_name} 처리 시작 (dry_run={dry_run}, caption={caption!r}) ──")
    _jargon = warn_jargon(caption)
    if _jargon:
        log(f"[{room_name}] ⚠ 실무진이 못 읽을 수 있는 말: {', '.join(_jargon)}")

    _bad = broken_links(caption)
    if _bad:
        log(f"[{room_name}] ⛔ 못 여는 링크 — 발신 보류: {' / '.join(_bad)}")
        return False, "broken_link"

    if room_name == CHAIRMAN_ROOM_NAME and not dry_run and not chairman_content_allows(caption):
        return False, "chairman_gate"

    if check_dedup(room_name, text=caption, image_path=image_path):
        log(f"[{room_name}] 중복 발신 가드로 스킵(전송 안 함)")
        return False, "dedup"

    if caption:
        _near, _ratio = check_near_dup(room_name, caption)
        if _near:
            log(f"[{room_name}] 근접 중복 가드로 스킵(전송 안 함) — 30분 안 유사도 {_ratio:.0%} "
                f"캡션 이미 발신됨(형식만 고친 재발송 의심). 의도된 재발송이면 env {SKIP_DEDUP_ENV}=1 로 우회.")
            return False, "near_dup"

    room_win = open_or_find_room(room_name)
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
        return True, ""

    if popup is not None:
        confirm_clipboard_popup(popup, room_name)  # 이미지 전송(팝업 캡션칸 Enter)
    else:
        send_enter(input_box)  # 팝업 없는 구버전 카톡 폴백 — 입력창에서 바로 전송
    time.sleep(1.0)
    # ── 캡션은 사진 다음의 '별도 메시지' 다. 붙여넣기가 먹었는지 눈으로 확인하고 보낸다.
    #   2026-08-12 실사고: 사진은 갔는데 캡션이 안 갔고, 로그에는 image+caption 성공으로
    #   찍혔다. GM 이 방을 보고서야 알았다("내용을 사진에 넣지말고 따로 남겨줘"). 원인은
    #   이미지 전송 팝업이 닫힌 직후 포커스가 방 입력창에 없어 붙여넣기가 허공에 떨어진 것.
    #   그래서 ①방 창을 다시 앞으로 ②붙인 뒤 입력창에 글이 실제로 들어갔는지 확인
    #   ③비어 있으면 한 번 더 ④그래도 비면 성공이라고 적지 않는다.
    caption_sent = False
    if caption:
        for attempt in range(2):
            focus_window(room_win, room_name)
            time.sleep(0.3)
            input_box = get_input_box(room_win, room_name)
            input_box.click_input()
            time.sleep(0.2)
            paste_text(input_box, caption)
            time.sleep(0.3)
            try:
                typed = (input_box.window_text() or "").strip()
            except Exception:
                typed = ""
            if not typed:
                log(f"[{room_name}] 캡션 붙여넣기가 안 먹었다 — 재시도 {attempt + 1}/2")
                continue
            send_enter(input_box)
            time.sleep(0.5)
            caption_sent = True
            break
        if not caption_sent:
            log(f"[{room_name}] ⚠️ 사진은 갔으나 설명 글을 못 보냈다 — 사람이 직접 보내야 한다")

    screenshot(room_win, room_name, "sent")
    log(f"[{room_name}] 전송 완료" + ("" if caption_sent or not caption else " (설명 글 누락)"))
    record_dedup_sent(room_name, text=caption, image_path=image_path)
    # 로그는 실제로 나간 것만 적는다 — 캡션이 못 갔는데 image+caption 으로 적으면
    # 어떤 감시기도 그 누락을 못 잡는다(오늘 사고의 실제 원인).
    _log_outbound(caption if caption_sent else "", chat_id=room_name,
                  source="kakao_report_sender.image", ok=True,
                  kind="image+caption" if caption_sent else "image", channel="kakao")
    return True, ""


# ══════════════════════════════════════════════════════════════════════════
# 상태 기록 단일 관문(2026-08-04 CTO) — status/kakao_last_send.json 등 "발신 결과"
# 파일은 이 스크립트(모든 카톡 발신이 통과하는 관문)에서만 쓴다. 이전엔 호출측
# (kakao_auto_daily_report.py·telegram_bot/bot.py 버튼)이 각자 따로 같은 파일에 썼는데,
# 사람이 이 스크립트를 직접 불러 재발송하면(09:34 3방 재발송 사고, 2026-08-04) 그 결과가
# 어느 쪽에도 안 남았다 — 발신은 성공했는데 화면엔 그 이전 실패가 그대로 남는 사고.
# --status-file 을 지정한 호출만 기록한다(기본 None=기록 안 함) — 이 스크립트는 매출보고
# 외에도 하루 수십 번(아침 다이제스트 등) 다른 목적으로 불려 나가므로, 지정 없는 호출까지
# 전부 기록하면 무관한 발신이 이 파일을 밟는다.
# rooms는 기존 파일의 값과 병합한다(덮어쓰지 않음) — "3방 중 재발송으로 성공한 2방만"처럼
# 여러 번 나눠 부른 호출도 정직하게 누적되게 한다(부분 성공을 뭉개지 않는다).
# ══════════════════════════════════════════════════════════════════════════
def write_status(status_file: str, detail: str, kind: str, room_results: dict) -> None:
    """room_results: {방이름: {"ok": bool, "detail": str}} — 이번 호출이 실제 처리한 방만."""
    path = Path(status_file)
    try:
        prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        prev = {}
    rooms = prev.get("rooms") if isinstance(prev.get("rooms"), dict) else {}
    now_s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for name, r in room_results.items():
        rooms[name] = {"ok": bool(r.get("ok")), "detail": str(r.get("detail", ""))[:200], "at": now_s}
    overall_ok = all(r.get("ok") for r in rooms.values()) if rooms else False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"ok": overall_ok, "detail": detail[:300], "kind": kind, "at": now_s, "rooms": rooms},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        log(f"[경고] {status_file} 기록 실패(무시): {exc}")


# 보류 사유 코드 → 사람이 읽는 문구(2026-08-10) — send_message_to_room/send_to_room이
# "chairman_gate"(회장님 방 새 내용 게이트)와 "dedup"(중복 발신 가드)을 구분해 반환하므로
# 여기서도 갈라 적는다. 이전엔 둘 다 "중복 발신 가드로 스킵" 한 문구로 뭉뚱그려, 08-10
# 09:30 회장님 방이 새내용게이트로 보류됐는데도 기록엔 "중복 발신 가드"로 남는 오류가 있었다.
_HOLD_REASON_LABEL = {
    "chairman_gate": "새 내용 게이트로 이번 회차 보류 — GM 텔레그램 미리보기 발송됨",
    "dedup": "중복 발신 가드로 스킵(최근 동일 발신 있음)",
}
# 요약 한 줄에 넣을 짧은 표기. 긴 라벨을 글자수로 자르면 "새 내용 게" 처럼 말이 끊긴다
# (2026-08-10 실제로 그렇게 남았다) — 자르지 말고 처음부터 짧은 말을 따로 둔다.
_HOLD_REASON_SHORT = {
    "chairman_gate": "새 문구 확인 대기",
    "dedup": "중복 방지",
}


def _status_summary(rooms: list[dict], failures: list, dedup_skipped: dict, suffix: str = "") -> str:
    """write_status용 요약 문구. 실제로 발송된 방 수만 '발송'으로 센다 — 보류(dedup_skipped)를
    성공에 섞지 않는다(2026-08-10: "4/4개 방 성공"이라 적혔지만 실제론 회장님 방 1개 보류였던 사고)."""
    sent = len(rooms) - len(failures) - len(dedup_skipped)
    text = f"{sent}/{len(rooms)}개 방 발송" + (f"({suffix})" if suffix else "")
    if dedup_skipped:
        names = ", ".join(f"{name}({_HOLD_REASON_SHORT.get(reason, reason)})"
                           for name, reason in dedup_skipped.items())
        text += f" · {len(dedup_skipped)}개 보류: {names}"
    return text


def _room_results(rooms: list[dict], failures: list, dedup_skipped: dict) -> dict:
    """이번 호출이 처리한 각 방의 결과를 write_status용 dict로 정리.
    dedup_skipped: {방이름: 보류사유코드} — ok는 기존 소비자 호환을 위해 True로 유지하고,
    보류 여부는 별도 held 필드로 추가한다(ok 의미를 바꾸지 않음)."""
    fail_map = dict(failures)
    results = {}
    for room in rooms:
        name = room["name"]
        if name in fail_map:
            results[name] = {"ok": False, "detail": fail_map[name]}
        elif name in dedup_skipped:
            reason = dedup_skipped[name]
            results[name] = {"ok": True, "held": True,
                              "detail": _HOLD_REASON_LABEL.get(reason, f"보류({reason})")}
        else:
            results[name] = {"ok": True, "detail": ""}
    return results


def resolve_image_path(cfg: dict, args) -> Path:
    """--image 직접지정 우선, 없고 --from-folder면 archive_dir/YYYY-MM/에서 오늘자 파일 자동선택."""
    if args.image:
        return Path(args.image)
    archive_dir = get_archive_dir(cfg)
    today = datetime.now()
    candidate = archive_dir / today.strftime("%Y-%m") / today.strftime(ARCHIVE_FILENAME_FMT)
    return candidate


def _selftest() -> None:
    """회장님 정제·평균 정확성·새내용 게이트 자가검사(assert 기반, 실제 발신 0건).
    텔레그램 전송·기준선 파일·계획 파일을 전부 가짜/임시로 바꿔치기해 부작용 0."""
    import tempfile
    global CHAIRMAN_BASELINE_PATH, MONTHLY_PLAN_PATH, _send_chairman_preview
    orig_baseline_path = CHAIRMAN_BASELINE_PATH
    orig_plan_path = MONTHLY_PLAN_PATH
    orig_preview_fn = _send_chairman_preview
    calls = []
    _send_chairman_preview = lambda text, new_kinds: calls.append((text, new_kinds))  # noqa: E731
    tmp_dir = Path(tempfile.mkdtemp(prefix="kakao_chairman_selftest_"))
    CHAIRMAN_BASELINE_PATH = tmp_dir / "baseline.json"
    MONTHLY_PLAN_PATH = tmp_dir / "plan.json"
    try:
        mkey = datetime.now().strftime("%Y-%m")
        MONTHLY_PLAN_PATH.write_text(json.dumps({"months": {mkey: {"objectives": [
            {"progress": 80, "honesty": {"level": "measured"}},
            {"progress": 0, "honesty": {"level": "manual"}},
        ]}}}, ensure_ascii=False), encoding="utf-8")

        raw = ("🌟 북극성 대비 — 8/1(토)\n"
               "매출 연72억   ▓▓▓▓▓░░░░  56% 40.5억 / 72억\n"
               "\n"
               "📋 8월 운영계획 — 목표 21개 · 평균 40%\n"
               "   📉 0% 목욕탕 허가건 진행 (7월 이월) — 시토\n"
               "   그 외 손 안 댄 것 3건\n")

        # ① 정제 — 회장님 방은 📉·손 안 댄 것·닉네임·None/null류 제거, 내부 방은 그대로
        chairman_text = build_caption({"name": CHAIRMAN_ROOM_NAME, "prefix": "회장님, "}, raw)
        assert "📉" not in chairman_text and "손 안 댄 것" not in chairman_text and "시토" not in chairman_text
        for bad in ("None", "null", "NaN", "undefined"):
            assert bad not in chairman_text, f"회장님 본문에 '{bad}'가 남음(정확성 위반)"
        internal_text = build_caption({"name": "웰페리온 관리부", "prefix": ""}, raw)
        assert "📉" in internal_text and "시토" in internal_text, "내부 방 본문에서 원래 있던 줄이 회귀로 사라짐"

        # ② 평균 정확성 — 신뢰불가(manual) 항목이 섞인 원래 평균(40%) 대신 신뢰 등급만의
        # 평균(80%, 1건 기준)으로 바뀌었는지
        assert "평균 40%" not in chairman_text, "신뢰 불가 항목이 섞인 원래 평균이 그대로 나감"
        assert "평균 80%(1건 기준)" in chairman_text, f"신뢰 평균 재계산 결과가 다름: {chairman_text!r}"

        # 신뢰 가능한 값이 하나도 없으면 평균 조각 자체를 뺀다(지어내지 않는다)
        MONTHLY_PLAN_PATH.write_text(json.dumps({"months": {mkey: {"objectives": [
            {"progress": 40, "honesty": {"level": "manual"}},
            {"progress": 20, "honesty": {"level": "observed"}},
        ]}}}, ensure_ascii=False), encoding="utf-8")
        no_trust_text = build_caption({"name": CHAIRMAN_ROOM_NAME, "prefix": ""}, raw)
        assert "평균" not in no_trust_text, f"신뢰 가능한 값이 없는데 평균이 남음: {no_trust_text!r}"

        # ③ 새 내용 게이트 — 평소(숫자만 다름)엔 정상 발신, 새 구성이 생겼을 때만 1회
        # 보류 후 기준선을 갱신해 다음 회차부터 자동 재개
        assert chairman_content_allows(chairman_text) is True, "최초 실행인데 보류됨(평소 발신을 막으면 안 됨)"
        assert len(calls) == 0, "최초 실행인데 미리보기가 나감(불필요)"
        print("  [기준선 없음(파일 삭제 상태 시뮬레이션)] 첫 실행: 통과(발신)")
        assert chairman_content_allows(chairman_text) is True, "동일 구성 재실행인데 보류됨"

        # 연속 3일 시뮬레이션 — 날짜·매출 숫자만 바뀌는 realistic 시나리오, 3번 다 통과해야 함
        day_variants = [
            chairman_text,
            chairman_text.replace("56%", "61%").replace("40.5억", "41.2억"),
            chairman_text.replace("56%", "48%").replace("40.5억", "35.9억").replace("8/1(토)", "8/3(월)"),
        ]
        for i, day_text in enumerate(day_variants, 1):
            ok = chairman_content_allows(day_text)
            print(f"  [3일 시뮬레이션] {i}일차: {'통과(발신)' if ok else '보류'}")
            assert ok is True, f"{i}일차(숫자만 다름)인데 보류됨(매일 발신이 멈추면 실패)"

        new_section = chairman_text + "\n🆕 신규 섹션 테스트\n"
        held = chairman_content_allows(new_section)
        print(f"  [구성 변경(신규 섹션 추가)] 그 회차: {'통과(발신)' if held else '보류'} (보류 기대)")
        assert held is False, "새 구성이 생겼는데 통과됨"
        assert len(calls) == 1, "새 구성 발견 시 미리보기가 안 감"
        resumed = chairman_content_allows(new_section)
        print(f"  [구성 변경 다음 회차(동일 신규 섹션)] {'통과(발신·자동재개)' if resumed else '보류'} (통과 기대)")
        assert resumed is True, "미리보기 이후 기준선이 안 바뀌어 다음 회차도 계속 보류됨"
        assert len(calls) == 1, "이미 기준선에 반영된 구성인데 미리보기가 또 감"

        print("SELFTEST OK: 회장님 새내용게이트/정제/평균정확성 정상(발신 0건)")

        # ④ 상태 기록 관문(write_status) — 전량 성공/부분 실패/전량 실패 3가지 + 병합(부분
        # 재발송 누적) 자가검사. 실제 status 파일은 안 건드리고 tmp_dir 안 임시 파일로만 검증.
        status_path = tmp_dir / "kakao_last_send_test.json"
        rooms4 = [{"name": n, "prefix": ""} for n in ["★운영부", "차의주 회장님", "★관리부", "★부서장"]]

        # 전량 성공
        write_status(str(status_path), "4/4개 방 성공", "IMAGE_REPORT",
                     _room_results(rooms4, [], {}))
        s1 = json.loads(status_path.read_text(encoding="utf-8"))
        assert s1["ok"] is True and len(s1["rooms"]) == 4, f"전량성공인데 ok=False거나 방 수 틀림: {s1}"
        print("  [전량 성공] ok=True, 4개 방 기록 — 통과")

        # 부분 실패(2방 실패) — 같은 파일에 다시 기록
        write_status(str(status_path), "2/4개 방 성공", "IMAGE_REPORT",
                     _room_results(rooms4, [("차의주 회장님", "err1"), ("★관리부", "err2")], {}))
        s2 = json.loads(status_path.read_text(encoding="utf-8"))
        assert s2["ok"] is False, f"2방 실패인데 ok=True: {s2}"
        assert s2["rooms"]["차의주 회장님"]["ok"] is False and s2["rooms"]["★관리부"]["ok"] is False
        assert s2["rooms"]["★운영부"]["ok"] is True and s2["rooms"]["★부서장"]["ok"] is True
        print("  [부분 실패 2/4] ok=False, 실패 2방만 False — 통과")

        # 병합 검증 — 실패했던 2방만 재발송 성공(나머지 2방은 이번 호출에 안 나옴).
        # 이전에 기록된 나머지 2방 값이 지워지지 않고 그대로 남아야 정직한 병합이다.
        write_status(str(status_path), "2/2개 방 성공(재발송)", "IMAGE_REPORT",
                     _room_results([{"name": "차의주 회장님", "prefix": ""}, {"name": "★관리부", "prefix": ""}], [], {}))
        s3 = json.loads(status_path.read_text(encoding="utf-8"))
        assert s3["ok"] is True, f"재발송으로 4방 다 성공했는데 ok=False: {s3}"
        assert len(s3["rooms"]) == 4, f"병합 후 방 수가 4가 아님(이전 기록 유실): {s3['rooms'].keys()}"
        print("  [재발송 병합] 실패 2방만 재기록해도 이전 성공 2방 값 보존 + 전체 ok=True — 통과")

        # 전량 실패
        write_status(str(status_path), "0/4개 방 성공", "IMAGE_REPORT",
                     _room_results(rooms4, [(r["name"], "err") for r in rooms4], {}))
        s4 = json.loads(status_path.read_text(encoding="utf-8"))
        assert s4["ok"] is False and all(not r["ok"] for r in s4["rooms"].values())
        print("  [전량 실패] ok=False, 4개 방 전부 False — 통과")

        print("SELFTEST OK: write_status 전량성공/부분실패/재발송병합/전량실패 정상")

        # ⑤ 보류 사유 분리 + 요약문구 정확성(2026-08-10 사고 재발 방지) — 회장님 방이
        # 새내용게이트로 보류됐는데 "중복 발신 가드로 스킵"·"4/4개 방 성공"으로 잘못
        # 기록된 사고. 새내용게이트/중복가드 사유가 각각 다르게 남는지, 보류가 발송
        # 수에서 빠지는지 검증.
        held = {"차의주 회장님": "chairman_gate"}
        summary = _status_summary(rooms4, [], held, "텍스트")
        assert "3/4" in summary, f"보류 1건인데 발송 수가 3/4이 아님: {summary!r}"
        assert "성공" not in summary, f"보류가 성공으로 표기됨(원인은닉 재발): {summary!r}"
        assert "보류" in summary, f"보류 사실이 요약에 안 드러남: {summary!r}"
        print(f"  [요약문구] {summary!r} — 성공 아닌 보류로 정확히 표기 — 통과")

        held_results = _room_results(rooms4, [], held)
        chairman_r = held_results["차의주 회장님"]
        assert chairman_r["ok"] is True, "보류도 ok=True 유지(기존 소비자 호환 — S2 결정)"
        assert chairman_r.get("held") is True, "보류 방에 held=True 표시 안 됨"
        assert "중복" not in chairman_r["detail"], \
            f"새내용게이트 보류인데 중복가드 문구가 남음(08-10 원인오기 재발): {chairman_r['detail']!r}"
        assert chairman_r["detail"] == "새 내용 게이트로 이번 회차 보류 — GM 텔레그램 미리보기 발송됨"

        dedup_results = _room_results(rooms4, [], {"★관리부": "dedup"})
        assert dedup_results["★관리부"]["detail"] == "중복 발신 가드로 스킵(최근 동일 발신 있음)"
        print("  [보류 사유] chairman_gate≠dedup, 문구·held 필드 정확 — 통과")

        print("SELFTEST OK: 보류(성공 아님) 표기 정확성 + 사유 분리 정상")

        # ⑥ 실패 사유 분류(배669) — 잠김·포커스거부·불명이 서로 안 섞이는지. 발신 0건.
        assert "잠겨" in _failure_reason([("★운영부", "There is no active desktop required...")])
        assert "입력을 받지" in _failure_reason([("★부서장", "ElementNotEnabled: ...")])
        assert "앞으로 띄우지" in _failure_reason([("차의주 회장님", "카톡 검색창 활성화 실패")])
        assert "원인 불명" in _failure_reason([("★관리부", "ZeroDivisionError")])
        print("SELFTEST OK: 발신 실패 사유 분류 정상")

        # ⑦ 명단 마스킹 + 존칭 보정 + 발신 전 링크 검수(2026-08-27). 링크 검수는 실제로
        #    주소를 열어 보므로 망이 끊긴 곳에서는 건너뛴다 — 검사 자체가 발신을 막는
        #    사고가 나면 안 된다.
        _selfcheck_mask_pii()
        _selfcheck_honorifics()
        _selfcheck_sender_gate()
        try:
            _selfcheck_broken_links()
        except AssertionError:
            raise
        except Exception as exc:
            print(f"  [링크 검수] 망 문제로 건너뜀 — {exc}")
    finally:
        CHAIRMAN_BASELINE_PATH = orig_baseline_path
        MONTHLY_PLAN_PATH = orig_plan_path
        _send_chairman_preview = orig_preview_fn
        try:
            for f in tmp_dir.glob("*"):
                f.unlink()
            tmp_dir.rmdir()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="텔레그램 매출보고 이미지를 카톡 방(들)에 전송(카카오톡 PC 앱 UI 자동화)")
    ap.add_argument("--selftest", action="store_true",
                     help="회장님 게이트·정제 로직 자가검사만 실행(실제 발신 없음)")
    ap.add_argument("--image", default=None, help="전송할 이미지 파일 경로(미지정 시 --from-folder 필요)")
    ap.add_argument("--from-folder", action="store_true",
                     help="--image 미지정 시 kakao_rooms.json의 archive_dir/YYYY-MM/에서 오늘 날짜 파일 자동 선택")
    ap.add_argument("--caption", default="", help="함께 보낼 원본 캡션 텍스트(방별 prefix는 자동 조합)")
    ap.add_argument("--message", default=None,
                     help="이미지 없이 텍스트만 전송(휴관일 안내문 등). 지정 시 --image/--from-folder 무시")
    ap.add_argument("--dry-run", action="store_true",
                     help="방 열기+클립보드+미리보기까지만, 실제 전송(Enter) 안 함")
    ap.add_argument("--only-room", default=None, help="지정한 방 1개만 처리(검증용)")
    ap.add_argument("--test", action="store_true",
                    help="테스트 발신 — 카톡에 일절 손대지 않고 본문을 텔레그램 업무보고방"
                         "(8254867551)으로만 보낸다(GM 확정: 테스트는 항상 그 방).")
    ap.add_argument("--sender", default="",
                     help="이 발신을 실제로 작성한 주체 — 사람 방(★중간관리자·★운영부) 발신 가드용. "
                          "'웰리' 또는 정기 자동 발송 이름(AUTO_PIPELINE_SENDERS). 미지정 시 사람 방은 막힌다.")
    ap.add_argument("--status-file", default=None,
                     help="발신 결과를 이 경로(JSON)에 기록(상태 기록 단일 관문). 미지정 시 기록 안 함 — "
                          "매출보고 등 상태 추적이 필요한 호출만 지정할 것")
    ap.add_argument("--status-kind", default="IMAGE_REPORT",
                     help="--status-file 기록 시 kind 필드(기본 IMAGE_REPORT, 예: HOLIDAY_NOTICE)")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return 0

    if sys.platform != "win32":
        print("BLOCKED: 이 스크립트는 Windows(카카오톡 PC 앱) 전용입니다.")
        return 1

    if not args.image and not args.from_folder and not args.message:
        print("BLOCKED: --image, --from-folder, --message 중 하나는 필수입니다.")
        return 1

    # ── 테스트 재경로 (2026-08-29 실사고 후속) — 테스트는 업무보고방으로만(GM 확정) ──
    #   10:42 ★운영부에 테스트 발신 + 10:43 정정문 두 통이 실무진에게 나간 사고의 근본 봉쇄.
    #   --test 면 카톡 창·방 목록에 아예 접근하지 않고 텔레그램 업무보고방으로만 보낸다.
    if args.test:
        try:
            agents_dir = str(ROOT / "wellperion-agents")
            if agents_dir not in sys.path:
                sys.path.insert(0, agents_dir)
            from telegram_notifier import TelegramNotifier
            body = (args.message or args.caption or "").strip()
            img_line = f"\n(이미지 파일: {args.image})" if args.image else ""
            msg = (f"🧪 [테스트 발신] 원래 대상 방 = {args.only_room or '(전체)'} — 카톡 미접촉\n\n"
                   f"{body}{img_line}")
            TelegramNotifier().send(msg)
            print("DONE: 테스트 발신 — 텔레그램 업무보고방으로만 전송(카톡·실무진 방 미접촉)")
            return 0
        except Exception as exc:
            print(f"BLOCKED: 테스트 발신 실패({exc}) — 카톡으로 폴백하지 않는다")
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

    # ── 폐기된 알림 차단 (GM 지시 2026-08-08 "이거 보내지마") ──
    #   60일 무응답 경보를 daily_scheduler 에서 지웠지만, 그 스케줄러는 상주 프로세스라
    #   오늘 밤(22:30) 까지는 옛 코드를 들고 있다. 발송은 이 파일을 **매번 새로 실행**하므로
    #   여기서 막으면 오늘 밤부터 즉시 안 나간다.
    #   ▸스케줄러가 재기동되면(오늘 밤 PC 종료 → 내일 로그온) 이 가드는 할 일이 없어진다.
    #     그때 지워도 되지만, 남아 있어도 폐기된 알림 하나를 막는 6줄이라 해가 없다.
    _msg0 = str(getattr(args, "message", "") or "")
    if "무응답" in _msg0 and ("60일" in _msg0 or "2개월" in _msg0):
        print("BLOCKED: 60일 무응답 경보는 2026-08-08 GM 지시로 폐기됨 (발송하지 않음)")
        return 0

    rooms = load_rooms(cfg, args.only_room)
    if not rooms:
        print("BLOCKED: 전송 대상 방이 없음 (kakao_rooms.json 확인)")
        return 1
    room_names = [r["name"] for r in rooms]

    def _log_room_members(target_rooms):
        """보내기 직전, 그 방을 **누가 읽는지** 로그에 남긴다(발송은 막지 않는다).

        왜: 2026-08-06 GM 지시 "항상 조직에 혼란없게 카카오톡 전달해줘". 같은 날
        ★중간관리자 방 구성원을 저장소의 낡은 목록(6명·매니저 포함)으로 잘못 알고
        "매니저에게 가면 안 되는 내용"의 판단을 틀리게 했다(실제 4명·매니저 없음).
        보내는 사람이 수신자를 눈으로 보게 하는 것이 가장 싼 예방이다.
        명단 정본은 scripts/kakao_rooms.json — 여기서 새로 정의하지 않는다(약속 L01).
        """
        try:
            # 방 목록은 T2 웹(GAS)이 편집 SSOT라 members 칸이 없다 — 명단은 로컬
            # kakao_rooms.json(폴백 캐시)에만 적혀 있으므로 이름으로 찾아 붙인다.
            by_name = {}
            try:
                cfg = json.loads(ROOMS_CONFIG.read_text(encoding="utf-8"))
                for key in ("rooms", "all_rooms"):
                    for r in cfg.get(key, []):
                        m = str((r or {}).get("members") or "").strip()
                        if m:
                            by_name.setdefault(str(r.get("name") or "").strip(), m)
            except Exception:
                pass
            for r in target_rooms:
                name = str(r.get("name") or "").strip()
                members = str(r.get("members") or "").strip() or by_name.get(name, "")
                log(f"  읽는 사람 [{name}] — {members or '명단 미기록(kakao_rooms.json 에 채워 주세요)'}")
        except Exception:
            pass  # 안내용이라 실패해도 발송을 막지 않는다

    failures = []
    dedup_skipped: dict[str, str] = {}  # 발신 안 함(실패 아님) — {방이름: "chairman_gate"|"dedup"}

    if args.message:
        log(f"대상 방 {len(rooms)}개: {room_names} / message={args.message!r} / dry_run={args.dry_run}")
        _log_room_members(rooms)
        for idx, room in enumerate(rooms):
            room_name = room["name"]
            if not _sender_gate_ok(room_name, args.sender):
                log(f"[gate] {room_name} — 사람 방은 웰리만 보낸다(--sender {args.sender!r} 거부)")
                dedup_skipped[room_name] = "웰리_승인_필요"
                if idx < len(rooms) - 1:
                    time.sleep(2.0)
                continue
            try:
                sent, hold_reason = send_message_to_room(room, args.message, args.dry_run)
                if not sent:
                    dedup_skipped[room_name] = hold_reason
            except Exception as exc:
                log(f"실패 [{room_name}]: {exc}")
                failures.append((room_name, str(exc)))
            if idx < len(rooms) - 1:
                time.sleep(2.0)  # 방 사이 지연
        if args.status_file and not args.dry_run:
            write_status(args.status_file, _status_summary(rooms, failures, dedup_skipped, "텍스트"),
                         args.status_kind, _room_results(rooms, failures, dedup_skipped))
        if failures:
            if not args.dry_run:
                _notify_send_failure(failures, "텍스트", args.message)
            print(f"BLOCKED: {len(failures)}개 방 실패 — {_failure_reason(failures)} — {failures}")
            return 1
        if dedup_skipped and len(dedup_skipped) == len(rooms):
            # 전량 보류도 조용히 넘기지 않는다 — 중복은 정상이지만 '가드에 막힘'은 사고다.
            # 2026-08-20: 아침 정리가 실장 경유 가드에 이틀 걸려 있었는데 로그에만 남아
            # 아무도 몰랐다(GM 이 물어서 드러남). 중복(dedup) 외 사유는 알린다.
            if not args.dry_run and any(r != "dedup" for r in dedup_skipped.values()):
                _notify_send_failure([(k, f"보류: {v}") for k, v in dedup_skipped.items()],
                                     "텍스트(보류)", args.message)
            print(f"BLOCKED: 전량 중복/보류 스킵(실발신 0건) — {dedup_skipped}")
            return 1
        # ★일부만 보류돼도 조용히 넘어가지 않는다(전량 보류는 위에서 이미 알린다) — 특히
        # 웰리 승인 가드에 걸린 방은 일반 dedup과 성격이 다르다(=배선 누락 사고). 다른 방이
        # 정상 발신되면 exit 0 인 채 이 방만 묻혀 아무도 모르는 사고를 막는다(GM 지적).
        gate_held = [k for k, v in dedup_skipped.items() if v == "웰리_승인_필요"]
        if gate_held and not args.dry_run:
            _notify_send_failure([(k, "웰리_승인_필요(--sender 누락/미승인 — 다른 방은 정상 발신)")
                                  for k in gate_held], "텍스트(부분 보류)", args.message)
        note = f" (미발신 {len(dedup_skipped)}개: {list(dedup_skipped)})" if dedup_skipped else ""
        print(f"DONE: {'DRY-RUN 검증' if args.dry_run else '전송'} 완료(텍스트) — {len(rooms)}개 방{note}")
        return 0

    image_path = resolve_image_path(cfg, args)
    if not image_path.exists():
        print(f"BLOCKED: 이미지 파일을 찾을 수 없음: {image_path}")
        return 1

    log(f"대상 방 {len(rooms)}개: {room_names} / image={image_path} / dry_run={args.dry_run}")

    for idx, room in enumerate(rooms):
        room_name = room["name"]
        if not _sender_gate_ok(room_name, args.sender):
            log(f"[gate] {room_name} — 사람 방은 웰리만 보낸다(--sender {args.sender!r} 거부)")
            dedup_skipped[room_name] = "웰리_승인_필요"
            if idx < len(rooms) - 1:
                time.sleep(2.0)
            continue
        try:
            sent, hold_reason = send_to_room(room, image_path, args.caption, args.dry_run)
            if not sent:
                dedup_skipped[room_name] = hold_reason
        except Exception as exc:
            log(f"실패 [{room_name}]: {exc}")
            failures.append((room_name, str(exc)))
        if idx < len(rooms) - 1:
            time.sleep(2.0)  # 방 사이 지연

    if args.status_file and not args.dry_run:
        write_status(args.status_file, _status_summary(rooms, failures, dedup_skipped),
                     args.status_kind, _room_results(rooms, failures, dedup_skipped))

    if failures:
        if not args.dry_run:
            # 이미지 발신은 본문 대신 캡션을 싣는다(사진은 텔레그램으로 옮겨 붙일 수 없다 —
            # GM 이 어느 방에 무엇이 못 갔는지 알고 손으로 보내실 수 있으면 충분하다).
            _notify_send_failure(failures, "이미지", f"[사진 {image_path.name}]\n{args.caption or ''}")
        print(f"BLOCKED: {len(failures)}개 방 실패 — {_failure_reason(failures)} — {failures}")
        return 1
    if dedup_skipped and len(dedup_skipped) == len(rooms):
        if not args.dry_run and any(r != "dedup" for r in dedup_skipped.values()):
            _notify_send_failure([(k, f"보류: {v}") for k, v in dedup_skipped.items()],
                                 "이미지(보류)", f"[사진 {image_path.name}]\n{args.caption or ''}")
        print(f"BLOCKED: 전량 중복/보류 스킵(실발신 0건) — {list(dedup_skipped)}")
        return 1
    # ★일부만 보류돼도 조용히 넘어가지 않는다 — 특히 웰리 승인 가드에 걸린 방은 일반
    # dedup과 성격이 다르다(=배선 누락 사고). 다른 방이 정상 발신되면 exit 0 인 채 이
    # 방만 묻혀 아무도 모르는 사고를 막는다(GM 지적 — 09:30 매출보고 4방처럼 여러 방을
    # 한 번에 도는 호출이 여기 해당한다).
    gate_held = [k for k, v in dedup_skipped.items() if v == "웰리_승인_필요"]
    if gate_held and not args.dry_run:
        _notify_send_failure([(k, "웰리_승인_필요(--sender 누락/미승인 — 다른 방은 정상 발신)")
                              for k in gate_held], "이미지(부분 보류)",
                             f"[사진 {image_path.name}]\n{args.caption or ''}")

    note = f" (보류 {len(dedup_skipped)}개: {list(dedup_skipped)})" if dedup_skipped else ""
    print(f"DONE: {'DRY-RUN 검증' if args.dry_run else '전송'} 완료 — {len(rooms)}개 방{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
