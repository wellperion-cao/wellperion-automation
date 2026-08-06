# scripts/naver_talktalk_custommenu.py
# 네이버 톡톡 파트너센터 채팅방 커스텀메뉴 반자동 관리
#
# 배경: 파트너센터 커스텀메뉴·자동응대 설정용 공식 API 없음 → 브라우저 자동화 유일.
#       비가역·회원대면 화면이므로 저장 직전 사람이 확인(갈래 C). 신뢰 10회 후 무인 전환 가능.
#       저장이 막히는 정확한 원인 아직 미검증 — 이 스크립트가 1회차 실측 담당.
#
# 전제: pip install playwright && playwright install chromium
#       profiles/naver-blog_state.json 존재(setup 모드로 생성, 또는 블로그 자동화 기존 파일)
#
# 모드:
#   inspect  : 현재 메뉴 목록 + 스크린샷. 변경 없음. 기본.
#   fix-typo : 멤버쉽→멤버십 오타 수정 드라이런(변경 없음, 계획만 출력+TG).
#              --go 붙이면 실제 수정·저장 시도·3단 캡처·TG 보고.
#   setup    : GM 수동 로그인 → storage_state 저장 (최초 1회).
#
# 실행 예:
#   python scripts\naver_talktalk_custommenu.py --mode inspect
#   python scripts\naver_talktalk_custommenu.py --mode fix-typo
#   python scripts\naver_talktalk_custommenu.py --mode fix-typo --go
#   python scripts\naver_talktalk_custommenu.py --mode setup

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
STORAGE_STATE = ROOT / "profiles" / "naver-blog_state.json"
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"
CUSTOMMENU_URL = "https://partner.talk.naver.com/web/accounts/102187005/custommenu"
LOGIN_SIGNALS = ("nid.naver.com/nidlogin", "nid.naver.com/login", "nidlogin.login")

# 오타 수정 대상
TYPO_OLD = "웰페리온 멤버쉽 회원권 문의"
TYPO_NEW = "웰페리온 멤버십 회원권 문의"


# -----------------------------------------------------------------
# 환경변수 로더 (telegram_bot/.env SSOT)
# -----------------------------------------------------------------
def _env(key: str) -> str:
    val = os.environ.get(key, "")
    if val:
        return val
    env_file = ROOT / "telegram_bot" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
REPORT_CHAT_ID = _env("OWNER_ID") or "8254867551"  # GM 업무보고방


# -----------------------------------------------------------------
# 텔레그램 발신 (토큰 stdout 미노출)
# -----------------------------------------------------------------
def _tg_send(text: str, *, photo_path: Path | None = None) -> bool:
    try:
        import requests
        headers = {}
        if photo_path and photo_path.exists():
            caption = text[:1024]
            with open(photo_path, "rb") as f:
                r = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    data={"chat_id": REPORT_CHAT_ID, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": f},
                    timeout=15,
                )
        else:
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": REPORT_CHAT_ID, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=10,
            )
        return r.status_code == 200
    except Exception as e:
        print(f"[WARN] TG 발신 실패: {e}")
        return False


def tg(text: str, photo: Path | None = None) -> None:
    if not BOT_TOKEN:
        print(f"[WARN] BOT_TOKEN 없음 — TG 생략: {text[:60]}")
        return
    ok = _tg_send(text, photo_path=photo)
    print(f"[TG] {'✓' if ok else '✗'} {text[:60]}")


# -----------------------------------------------------------------
# 스크린샷 저장 경로
# -----------------------------------------------------------------
def shot_path(label: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return EVIDENCE_DIR / f"talktalk_custommenu_{label}_{ts}.png"


# -----------------------------------------------------------------
# iframe 전환 헬퍼 — 마지막 프레임(실측: SPA 내비=메인, 내용=마지막 iframe)
# -----------------------------------------------------------------
def get_content_frame(page):
    frames = page.frames
    if len(frames) < 2:
        return page.main_frame
    return frames[-1]


# -----------------------------------------------------------------
# 메뉴 목록 읽기
# -----------------------------------------------------------------
def read_menus(frame) -> list[str]:
    """버튼 텍스트로 메뉴 이름 목록 반환(순서 유지)."""
    try:
        # 메뉴 버튼: 탭/사이드바 내 클릭 가능한 항목 — 선택자 실측 필요
        # 웰리 실측 메모: 그 이름의 button 클릭으로 메뉴 선택 가능
        btns = frame.locator("button").all()
        names = []
        for b in btns:
            txt = b.inner_text().strip()
            if txt and "웰페리온" in txt:
                names.append(txt)
        return names
    except Exception as e:
        print(f"[WARN] 메뉴 읽기 실패: {e}")
        return []


# -----------------------------------------------------------------
# inspect 모드 — 현재 상태 스크린샷 + TG 보고
# -----------------------------------------------------------------
def run_inspect(page) -> int:
    print("[INFO] inspect: 커스텀메뉴 현재 상태 확인")
    page.goto(CUSTOMMENU_URL, wait_until="networkidle", timeout=30_000)

    if any(sig in page.url for sig in LOGIN_SIGNALS):
        print("[ERROR] 로그인 필요 — storage_state 만료. --mode setup 으로 재인증 후 재시도")
        return 1

    page.wait_for_timeout(2000)  # SPA 렌더 대기
    frame = get_content_frame(page)

    # 전체 페이지 스크린샷
    p_full = shot_path("inspect_full")
    page.screenshot(path=str(p_full), full_page=True)
    print(f"[INFO] 스크린샷: {p_full}")

    # iframe 스크린샷
    p_frame = shot_path("inspect_frame")
    try:
        frame.locator("body").screenshot(path=str(p_frame))
    except Exception:
        p_frame = p_full  # iframe body 접근 불가 시 전체 폴백

    menus = read_menus(frame)
    menu_txt = "\n".join(f"  {i+1}. {m}" for i, m in enumerate(menus)) if menus else "  (읽기 실패 — DOM 구조 확인 필요)"

    report = (
        f"🔍 <b>[시토] 톡톡 커스텀메뉴 현황</b>\n"
        f"URL: {CUSTOMMENU_URL}\n\n"
        f"<b>현재 메뉴({len(menus)}개):</b>\n{menu_txt}\n\n"
        f"오타 감지: {'✅ 있음(멤버쉽)' if TYPO_OLD in menus else '없음(이미 수정됐거나 읽기 실패)'}"
    )
    print(report)
    tg(report, photo=p_frame)
    return 0


# -----------------------------------------------------------------
# fix-typo 모드
# -----------------------------------------------------------------
def run_fix_typo(page, *, go: bool) -> int:
    if not go:
        plan = (
            f"[DRY-RUN] fix-typo 계획:\n"
            f"  변경: '{TYPO_OLD}'\n"
            f"    → '{TYPO_NEW}'\n\n"
            f"실제 수행하려면:\n"
            f"  python scripts\\naver_talktalk_custommenu.py --mode fix-typo --go\n\n"
            f"저장 성공 조건은 아직 미검증(막힌 지점). --go 실행 시 저장 시도+3단 캡처+TG 보고."
        )
        print(plan)
        tg(f"📋 <b>[시토] 톡톡 오타 수정 계획</b>\n{plan}")
        return 0

    # ── 실제 수행 ──
    print("[INFO] fix-typo --go: 라이브 시도 시작")
    page.goto(CUSTOMMENU_URL, wait_until="networkidle", timeout=30_000)

    if any(sig in page.url for sig in LOGIN_SIGNALS):
        print("[ERROR] 로그인 필요 — storage_state 만료. --mode setup 실행 후 재시도")
        tg("❌ [시토] 톡톡 오타수정 실패: storage_state 만료 — setup 필요")
        return 1

    page.wait_for_timeout(2000)
    frame = get_content_frame(page)

    # STEP 1: 현재 상태 캡처
    p_before = shot_path("fix_1_before")
    page.screenshot(path=str(p_before), full_page=True)
    print(f"[STEP1] before 스크린샷: {p_before}")
    tg(f"📸 <b>[시토] 오타수정 STEP1: 수정 전</b>\n메뉴: {TYPO_OLD}", photo=p_before)

    # STEP 2: 오타 메뉴 버튼 클릭
    try:
        btn = frame.get_by_role("button", name=TYPO_OLD)
        btn.wait_for(timeout=5_000)
        btn.click()
        page.wait_for_timeout(1000)
        print(f"[STEP2] '{TYPO_OLD}' 버튼 클릭 완료")
    except Exception as e:
        print(f"[WARN] 메뉴 버튼 클릭 실패: {e}")
        # fallback: 텍스트 매칭
        try:
            frame.locator(f"button:has-text('{TYPO_OLD}')").first.click()
            page.wait_for_timeout(1000)
            print("[STEP2] fallback 텍스트 매칭 클릭 완료")
        except Exception as e2:
            print(f"[ERROR] 메뉴 버튼 찾기 실패: {e2}")
            tg(f"❌ [시토] 오타수정 STEP2 실패: 메뉴 버튼 없음\n{e2}")
            return 1

    # STEP 3: 메뉴명 입력칸 찾아 수정
    try:
        # 실측: input[placeholder*='메뉴명']
        inp = frame.locator("input[placeholder*='메뉴명']").first
        inp.wait_for(timeout=5_000)
        current_val = inp.input_value()
        print(f"[STEP3] 현재 입력값: '{current_val}'")

        if current_val != TYPO_OLD:
            print(f"[WARN] 예상 오타값과 불일치: '{current_val}' ≠ '{TYPO_OLD}'")
            # 계속 진행(다른 메뉴가 선택됐을 수 있음)

        inp.triple_click()
        inp.type(TYPO_NEW, delay=50)
        page.wait_for_timeout(500)
        new_val = inp.input_value()
        print(f"[STEP3] 입력 후 값: '{new_val}'")
    except Exception as e:
        print(f"[ERROR] 메뉴명 입력칸 조작 실패: {e}")
        tg(f"❌ [시토] 오타수정 STEP3 실패: 입력칸 조작 불가\n{e}")
        return 1

    # STEP 4: 저장 전 스크린샷 (GM 확인용)
    p_preflight = shot_path("fix_2_preflight")
    page.screenshot(path=str(p_preflight), full_page=True)
    print(f"[STEP4] 저장 직전 스크린샷: {p_preflight}")
    tg(
        f"📸 <b>[시토] 오타수정 STEP2: 저장 직전 — GM 확인</b>\n"
        f"입력값: '{new_val}'\n"
        f"저장 시도 중...",
        photo=p_preflight,
    )

    # STEP 5: 저장 버튼 탐색 + 클릭 (성공 조건 미검증 지점)
    save_result = "미시도"
    save_error = ""
    try:
        # 예상 후보들 (실측 필요)
        SAVE_SELECTORS = [
            "button:has-text('입력 내용 저장')",
            "button:has-text('저장')",
            "[data-action='save']",
            "button[type='submit']",
        ]
        save_btn = None
        for sel in SAVE_SELECTORS:
            try:
                loc = frame.locator(sel).first
                loc.wait_for(timeout=2_000)
                save_btn = loc
                print(f"[STEP5] 저장 버튼 발견: {sel}")
                break
            except Exception:
                continue

        if save_btn is None:
            save_result = "버튼 없음"
            print("[WARN] 저장 버튼 셀렉터 미매칭 — 현재 DOM 상태 확인 필요")
        else:
            save_btn.click()
            page.wait_for_timeout(2000)
            save_result = "클릭 완료"
            print("[STEP5] 저장 버튼 클릭 완료 — 반영 확인 대기")
    except Exception as e:
        save_result = "오류"
        save_error = str(e)
        print(f"[WARN] 저장 시도 중 예외: {e}")

    # STEP 6: 저장 후 스크린샷
    p_after = shot_path("fix_3_after_save")
    page.screenshot(path=str(p_after), full_page=True)
    print(f"[STEP6] 저장 후 스크린샷: {p_after}")

    # STEP 7: 페이지 새로고침 후 반영 확인
    page.reload(wait_until="networkidle", timeout=20_000)
    page.wait_for_timeout(2000)
    frame2 = get_content_frame(page)
    menus_after = read_menus(frame2)
    p_verify = shot_path("fix_4_verify")
    page.screenshot(path=str(p_verify), full_page=True)
    persisted = TYPO_NEW in menus_after
    still_typo = TYPO_OLD in menus_after

    summary = (
        f"📋 <b>[시토] 오타수정 결과 요약</b>\n\n"
        f"저장 버튼: {save_result}{' — ' + save_error if save_error else ''}\n"
        f"새로고침 후:\n"
        f"  {TYPO_NEW}: {'✅ 반영됨' if persisted else '❌ 미반영'}\n"
        f"  {TYPO_OLD}: {'⚠️ 아직 있음(오타 유지)' if still_typo else '✅ 없음'}\n\n"
        f"메뉴 전체({len(menus_after)}개):\n" +
        "\n".join(f"  · {m}" for m in menus_after) +
        f"\n\n증거:\n  before: {p_before.name}\n  preflight: {p_preflight.name}\n"
        f"  after: {p_after.name}\n  verify: {p_verify.name}"
    )
    print(summary)
    tg(summary, photo=p_verify)

    # 저장 미검증 원인 진단 힌트 출력
    if not persisted:
        print("[DIAG] 저장 미반영 가능 원인:")
        print("  1) 메시지 내용(빈 내용)이 필수 조건일 수 있음 — '메시지 내용 편집' 먼저 해야 할 수도")
        print("  2) 확인 모달이 한 번 더 있을 수 있음 — 저장 후 DOM 확인 필요")
        print("  3) '저장' 버튼이 아니라 다른 확정 버튼이 있을 수 있음")
        print("  → poc-evidence/ 스크린샷 확인 후 셀렉터 재조정 필요")

    return 0 if (persisted or save_result == "클릭 완료") else 1


# -----------------------------------------------------------------
# setup 모드 — GM 수동 로그인 → storage_state 저장
# -----------------------------------------------------------------
def run_setup(playwright) -> int:
    print("[INFO] setup: 브라우저 열림 — 네이버 로그인 후 Enter 누르세요")
    browser = playwright.chromium.launch(headless=False)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto("https://nid.naver.com/nidlogin.login")
    input("로그인 완료 후 Enter ▶ ")
    STORAGE_STATE.parent.mkdir(parents=True, exist_ok=True)
    ctx.storage_state(path=str(STORAGE_STATE))
    browser.close()
    print(f"[INFO] storage_state 저장: {STORAGE_STATE}")
    return 0


# -----------------------------------------------------------------
# 공통 브라우저 세팅
# -----------------------------------------------------------------
def make_page(playwright, *, headless: bool):
    if not STORAGE_STATE.exists():
        print(f"[ERROR] storage_state 없음: {STORAGE_STATE}")
        print("       먼저 python scripts\\naver_talktalk_custommenu.py --mode setup 실행")
        sys.exit(1)
    browser = playwright.chromium.launch(headless=headless)
    ctx = browser.new_context(storage_state=str(STORAGE_STATE))
    page = ctx.new_page()
    return browser, page


# -----------------------------------------------------------------
# CLI
# -----------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="네이버 톡톡 파트너센터 커스텀메뉴 반자동 관리")
    ap.add_argument("--mode", choices=["inspect", "fix-typo", "setup"], default="inspect")
    ap.add_argument("--go", action="store_true", help="fix-typo 실제 실행(없으면 드라이런)")
    ap.add_argument("--headless", action="store_true", default=False, help="헤드리스 모드(기본: 창 표시)")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        if args.mode == "setup":
            return run_setup(pw)

        browser, page = make_page(pw, headless=args.headless)
        try:
            if args.mode == "inspect":
                rc = run_inspect(page)
            else:  # fix-typo
                rc = run_fix_typo(page, go=args.go)
        finally:
            if args.go or args.mode == "inspect":
                browser.close()
            else:
                browser.close()

    return rc


if __name__ == "__main__":
    sys.exit(main())
