# -*- coding: utf-8 -*-
"""GAS 버전 위생 정리 — 전용 프로필 브라우저 UI 일괄삭제 (비가역·최고신중).

배경:
    Google Apps Script 편집기 UI가 버전 삭제를 지원한다(2024~).
      · Project History → "Bulk delete versions" (활성 배포에 물린 버전은 목록서 자동 제외)
      · 개별: ⋮ More actions → "Delete this version"
    REST API에는 versions.delete 가 없어(회수 불가) UI 만이 유일 경로.

전용 프로필:
    GM 메인 크롬과 별개 user-data-dir. 기존 danggn/naver 프로필은 Kakao/Naver 인증뿐
    (script.google.com=cao 구글세션 없음) → 신규 전용 프로필 + GM 수동 로그인.
    구글은 자동화 브라우저 로그인을 'this browser may not be secure'로 차단할 수 있음 →
    감지 즉시 status.blocked 기록.

모드:
    probe  : 브라우저 기동 → 편집기 이동 → 인증 게이트(최대 10분 GM 수동 로그인 폴링)
             → 인증되면 Project History 열어 스크린샷 + Bulk delete 버튼 존재/영향 버전 파악.
             삭제는 절대 하지 않음. 세션은 프로필에 저장됨(delete 모드가 재사용).
    delete : 프로필의 기존 세션 재사용(로그인 불요) → Bulk delete versions 실행.
             ★ 반드시 --i-am-sure + 대상 프로젝트 지정. 활성배포 물린 버전은 UI가 자동 제외.

실행:
    C:/Python314/python.exe scripts/gas_version_cleanup.py --mode probe --project funnel
    C:/Python314/python.exe scripts/gas_version_cleanup.py --mode delete --project funnel --i-am-sure
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
PROFILE_DIR = ROOT / "profiles" / "gas-cleanup"
SCRATCH = Path(r"C:\Users\jjky0\AppData\Local\Temp\claude\C--Users-jjky0-welperion-automation\ca5d031a-83b7-43bd-bfba-3fb30c49b86a\scratchpad")
STATUS_PATH = SCRATCH / "gas_cleanup_status.json"
SHOT_DIR = SCRATCH / "gas_cleanup_shots"

PROJECTS = {
    "funnel": "1A77oDRaa21K25c3-M1AgewNfUzfW-zamfRhYWjlYUrvIdPCYazs8KQru",
    "check": "1FLQAzjq6IME2A41QZlfZZSzzAeaFFDAr58M6T-JzDtzzbC4gEKuQFNp6",
}

# 구글 보안 차단 텍스트 시그널
BLOCK_SIGNALS = (
    "browser or app may not be secure",
    "this browser may not be secure",
    "브라우저 또는 앱이 보안에 취약",
    "couldn't sign you in",
    "로그인할 수 없",
)

_status = {}


def write_status(**kw):
    _status.update(kw)
    _status["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(_status, ensure_ascii=False, indent=2), encoding="utf-8")


async def _shot(page, name):
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = SHOT_DIR / f"{name}.png"
    try:
        await page.screenshot(path=str(p), full_page=False)
        return str(p)
    except Exception as e:
        return f"(shot fail: {e})"


async def _launch(p):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",                 # 실제 Chrome (구글이 Chromium보다 관대)
        headless=False,
        no_viewport=True,
        ignore_default_args=["--enable-automation"],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    )
    # navigator.webdriver 제거 (자동화 탐지 완화)
    await ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    )
    return ctx


def _auth_state(url: str, body_text: str) -> str:
    u = (url or "").lower()
    bt = (body_text or "").lower()
    for s in BLOCK_SIGNALS:
        if s in bt:
            return "blocked"
    if "accounts.google.com" in u or "servicelogin" in u or "signin" in u:
        return "awaiting_login"
    if "script.google.com" in u and ("/projects/" in u or "/edit" in u or "/d/" in u):
        return "authed"
    return "loading"


async def _dump_nav(page):
    """좌측 레일 + 상단 클릭요소 aria-label 덤프(한글 UI 라벨 파악용)."""
    labels = []
    try:
        labels = await page.eval_on_selector_all(
            "[aria-label]",
            "els => els.slice(0,120).map(e => (e.getAttribute('aria-label')||'').trim()).filter(Boolean)",
        )
    except Exception as e:
        labels = [f"(dump fail: {e})"]
    # 중복 제거, 짧은 것 위주
    seen, out = set(), []
    for l in labels:
        if l and l not in seen and len(l) < 40:
            seen.add(l); out.append(l)
    return out


async def _open_history(page):
    """Project History 패널 열기. 한글/영문 라벨 + 좌측 레일 아이콘. best-effort."""
    candidates = [
        "[aria-label*='프로젝트 기록']",
        "[aria-label*='기록']",
        "[aria-label*='Project history' i]",
        "[aria-label*='history' i]",
        "[data-tooltip*='기록']",
        "[data-tooltip*='Project history' i]",
    ]
    for sel in candidates:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=4000)
                await page.wait_for_timeout(2500)
                return sel
        except Exception:
            continue
    return None


async def run_probe(project: str):
    script_id = PROJECTS[project]
    edit_url = f"https://script.google.com/home/projects/{script_id}/edit"
    # 미인증 시 편집기 URL은 developers.google.com docs로 튕김 → 로그인 페이지로 직행 후 성공시 편집기 continue.
    login_url = ("https://accounts.google.com/ServiceLogin?continue=" +
                 f"https%3A%2F%2Fscript.google.com%2Fhome%2Fprojects%2F{script_id}%2Fedit")
    write_status(mode="probe", project=project, script_id=script_id, phase="launching",
                 blocked=False, authed=False, shots=[])
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    ctx = await _launch(p)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    try:
        await page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        write_status(phase="goto_error", note=f"goto 실패: {e}")
    write_status(phase="waiting_auth",
                 note="브라우저 창이 열렸습니다. GM님이 그 창에서 cao@wellperion.com 으로 로그인해 주세요. 로그인 성공 시 자동으로 funnel 편집기로 이동합니다.")

    deadline = time.time() + 600  # 10분
    state = "loading"
    shots = []
    renav = 0
    while time.time() < deadline:
        try:
            url = page.url
            body = ""
            try:
                body = await page.inner_text("body", timeout=3000)
            except Exception:
                body = ""
            state = _auth_state(url, body)
            # docs 랜딩으로 튕겼는데(=미인증 바운스) 로그인 흔적 없으면 로그인 URL 재요청(throttle).
            if "developers.google.com" in url.lower():
                renav += 1
                if renav % 3 == 1:
                    try:
                        await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                    await asyncio.sleep(3)
                    continue
            if state == "blocked":
                s = await _shot(page, "blocked")
                shots.append(s)
                write_status(phase="blocked", blocked=True, authed=False, cur_url=url,
                             shots=shots,
                             note="구글이 자동화 브라우저 로그인을 차단('browser may not be secure'). 전용 프로필 자동로그인 불가.")
                break
            if state == "authed":
                write_status(phase="authed", authed=True, cur_url=url,
                             note="인증 확인됨. Project History 여는 중.")
                await page.wait_for_timeout(3000)
                s0 = await _shot(page, "editor_authed")
                shots.append(s0)
                sel = await _open_history(page)
                await page.wait_for_timeout(1500)
                s1 = await _shot(page, "project_history")
                shots.append(s1)
                # Bulk delete 버튼 탐지
                bulk = 0
                try:
                    bulk = await page.locator("text=/Bulk delete versions/i").count()
                except Exception:
                    bulk = -1
                write_status(phase="history_open", authed=True, history_selector=sel,
                             bulk_delete_button=bulk, shots=shots,
                             note=("Project History 열림. Bulk delete 버튼 %s. 스크린샷 확인 후 delete 모드로 진행 가능." %
                                   ("발견" if bulk and bulk > 0 else "미발견(개별삭제 폴백 필요)")))
                break
            else:
                write_status(phase="waiting_auth", cur_url=url, auth_state=state)
        except Exception as e:
            write_status(phase="poll_error", note=f"폴링 예외: {e}")
        await asyncio.sleep(8)
    else:
        write_status(phase="timeout", note="10분 내 인증 안 됨(GM 로그인 대기). 창은 닫습니다.")

    # probe는 세션 저장 위해 잠시 대기 후 종료(프로필 저장). blocked/authed/timeout 모두 종료.
    await page.wait_for_timeout(1500)
    try:
        await ctx.close()
    except Exception:
        pass
    write_status(phase="probe_done_state_" + state)


async def _open_row_menu(page):
    """버전 행을 hover → 나타나는 ⋮('추가 작업') 클릭 → 메뉴 오픈. 열린 메뉴 item 텍스트 반환."""
    # 버전 200 행(현재 아님) 우선, 없으면 아무 listitem.
    row = None
    try:
        cand = page.get_by_text("버전 200", exact=False).first
        if await cand.count() > 0:
            row = cand.locator("xpath=ancestor-or-self::*[@role='listitem'][1]")
            if await row.count() == 0:
                row = cand
    except Exception:
        row = None
    if row is None or await row.count() == 0:
        row = page.locator("[role='listitem']").nth(1)
    try:
        await row.hover(timeout=4000)
        await page.wait_for_timeout(600)
    except Exception:
        pass
    # 행 내부 ⋮
    clicked = False
    for msel in ["[aria-label='추가 작업']", "button[aria-label*='작업']", "[aria-haspopup='true']"]:
        try:
            m = row.locator(msel).first
            if await m.count() > 0:
                await m.click(timeout=3000)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        # 행 스코프 실패 시 전역 첫 visible ⋮
        gl = page.locator("[aria-label='추가 작업']")
        for i in range(min(await gl.count(), 6)):
            try:
                b = gl.nth(i)
                if await b.is_visible():
                    await b.click(timeout=2500)
                    clicked = True
                    break
            except Exception:
                continue
    await page.wait_for_timeout(900)
    items = []
    try:
        items = await page.eval_on_selector_all(
            "[role='menuitem'], [role='menu'] *[aria-label], .goog-menuitem",
            "els => els.map(e => (e.textContent||e.getAttribute('aria-label')||'').trim()).filter(Boolean).slice(0,40)",
        )
    except Exception:
        items = []
    return clicked, items


async def _open_bulk_dialog(page):
    """프로젝트 기록 열린 상태에서 '버전 일괄 삭제' 다이얼로그 오픈. (성공, 진단) 반환."""
    diag = {}
    # 1) 지속 요소 '버전 일괄 삭제'(패널 헤더 버튼, hover 전 숨김일 수 있음) 직접 클릭.
    bulk = page.locator("[aria-label='버전 일괄 삭제']").first
    try:
        diag["bulk_count"] = await bulk.count()
        if diag["bulk_count"] > 0:
            try:
                await bulk.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            # 헤더 영역 hover로 아이콘 노출 유도
            try:
                await bulk.hover(timeout=2500)
                await page.wait_for_timeout(400)
            except Exception:
                pass
            await bulk.click(timeout=4000, force=True)
            await page.wait_for_timeout(1800)
            await _shot(page, "delete_afterbulkclick")
            # 일괄삭제 모드 진입 판정: 체크박스 출현 or role=dialog.
            cb = await page.locator("input[type=checkbox]").count()
            dlg = page.locator("[role='dialog']").first
            dlg_vis = (await dlg.count() > 0) and (await dlg.is_visible())
            diag["checkbox_count"] = cb
            diag["dialog_visible"] = dlg_vis
            if cb > 0 or dlg_vis:
                return True, diag
    except Exception as e:
        diag["direct_err"] = str(e)
    # 2) 폴백: 행 ⋮ 메뉴(진단용) — 여기엔 '이 버전 삭제'만 있을 가능성 큼.
    clicked, items = await _open_row_menu(page)
    diag["row_menu_items"] = items
    await _shot(page, "delete_rowmenu")
    try:
        item = page.get_by_text("버전 일괄 삭제", exact=False).first
        if await item.count() > 0 and await item.is_visible():
            await item.click(timeout=4000)
            await page.wait_for_timeout(1500)
            return True, diag
    except Exception:
        pass
    return False, diag


async def run_delete(project: str, sure: bool):
    script_id = PROJECTS[project]
    edit_url = f"https://script.google.com/home/projects/{script_id}/edit"
    write_status(mode="delete", project=project, script_id=script_id, phase="launching",
                 sure=sure, blocked=False, authed=False, shots=[])
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    ctx = await _launch(p)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    try:
        await page.goto(edit_url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        write_status(phase="goto_error", note=f"goto 실패: {e}")
    # 인증 재확인(세션 재사용). 최대 90초.
    deadline = time.time() + 90
    state = "loading"
    while time.time() < deadline:
        url = page.url
        try:
            body = await page.inner_text("body", timeout=3000)
        except Exception:
            body = ""
        state = _auth_state(url, body)
        if state in ("authed", "blocked"):
            break
        await asyncio.sleep(5)
    if state != "authed":
        s = await _shot(page, "delete_no_auth")
        write_status(phase="delete_no_auth", authed=False, note=f"삭제 모드 인증 실패(state={state}).", shots=[s])
        await ctx.close(); return
    shots = []
    await page.wait_for_timeout(3000)
    rounds = []
    try:
        for rnd in range(1, 2):  # 한 호출당 1라운드(상태 이월 방지). 반복은 외부에서 count 검증하며 구동.
            # 매 라운드: history 재확인 + bulk 다이얼로그 오픈
            await _open_history(page)
            await page.wait_for_timeout(1200)
            opened, diag = await _open_bulk_dialog(page)
            if not opened:
                # 더 열 다이얼로그 없음 = 삭제 가능 버전 소진(또는 UI 변화)
                rounds.append({"round": rnd, "result": "no_dialog", "diag": diag})
                shots.append(await _shot(page, f"delete_r{rnd}_nodialog"))
                break
            # 남은 삭제가능 수 파악: "N 중 1-25"
            remaining = None
            try:
                dtxt = await page.locator("[role='dialog']").first.inner_text(timeout=3000)
                import re as _re
                m = _re.search(r"(\d+)\s*중", dtxt)
                if m:
                    remaining = int(m.group(1))
            except Exception:
                pass
            if rnd == 1:
                shots.append(await _shot(page, "delete_dialog"))
            # 헤더 전체선택
            for sel_all in ["[aria-label*='모두 선택']", "[aria-label*='전체 선택']",
                            "[aria-label*='Select all' i]", "th input[type=checkbox]",
                            "[role='dialog'] input[type=checkbox]"]:
                try:
                    c = page.locator(sel_all).first
                    if await c.count() > 0:
                        await c.check(timeout=3000)
                        break
                except Exception:
                    continue
            await page.wait_for_timeout(700)
            checked_n = -1
            try:
                checked_n = await page.locator("input[type=checkbox]:checked").count()
            except Exception:
                pass
            if not sure:
                shots.append(await _shot(page, "delete_selected"))
                try:
                    cancel = page.get_by_text("취소", exact=False).first
                    if await cancel.count() > 0:
                        await cancel.click(timeout=3000)
                except Exception:
                    pass
                write_status(phase="dry_preview_done", remaining_deletable=remaining,
                             checked_count=checked_n, shots=shots,
                             note=f"DRY: 삭제가능 {remaining}, 이번 페이지 선택 {checked_n-1 if checked_n>0 else checked_n}. 확정 안 함.")
                await page.wait_for_timeout(800)
                await ctx.close(); return
            # 확정 삭제(1차)
            confirmed = False
            try:
                b = page.get_by_role("button", name="삭제").last
                if await b.count() > 0 and await b.is_enabled():
                    await b.click(timeout=5000)
                    confirmed = True
            except Exception:
                pass
            await page.wait_for_timeout(1500)
            if rnd == 1:
                shots.append(await _shot(page, "r1_afterclick"))
            # 2차 확인 다이얼로그 처리(경고 후 재확인 '삭제')
            conf2_txt = ""
            try:
                dlgs = page.locator("[role='dialog'], [role='alertdialog']")
                nd = await dlgs.count()
                if nd > 0:
                    d2 = dlgs.last
                    if await d2.is_visible():
                        conf2_txt = (await d2.inner_text(timeout=2000))[:200]
                        b2 = d2.get_by_role("button", name="삭제").last
                        if await b2.count() > 0 and await b2.is_enabled():
                            await b2.click(timeout=4000)
                            if rnd == 1:
                                shots.append(await _shot(page, "r1_after2ndconfirm"))
            except Exception as _e:
                conf2_txt = f"(2nd err: {_e})"
            if rnd == 1:
                write_status(phase="round1_diag", conf2_txt=conf2_txt, shots=shots)
            await page.wait_for_timeout(5000)
            rounds.append({"round": rnd, "remaining_before": remaining,
                           "selected": (checked_n - 1) if checked_n and checked_n > 0 else checked_n,
                           "confirmed": confirmed})
            write_status(phase=f"round_{rnd}_done", rounds=rounds, shots=shots,
                         note=f"라운드 {rnd}: 삭제전 남은 {remaining}, 선택 {checked_n-1 if checked_n>0 else checked_n}, 확정={confirmed}")
            if not confirmed:
                shots.append(await _shot(page, f"delete_r{rnd}_notconfirmed"))
                break
            await page.wait_for_timeout(1500)
        shots.append(await _shot(page, "delete_final"))
        write_status(phase="delete_loop_done", rounds=rounds, shots=shots,
                     note=f"삭제 루프 종료. {len([r for r in rounds if r.get('confirmed')])}개 라운드 확정.")
    except Exception as e:
        shots.append(await _shot(page, "delete_error"))
        write_status(phase="delete_error", note=f"삭제 흐름 예외: {e}", rounds=rounds, shots=shots)
    await page.wait_for_timeout(1500)
    await ctx.close()


async def run_inspect(project: str):
    """세션 재사용(로그인 불요) → 편집기 → nav 라벨 덤프 + Project History 열어 스크린샷. 삭제 안 함."""
    script_id = PROJECTS[project]
    edit_url = f"https://script.google.com/home/projects/{script_id}/edit"
    write_status(mode="inspect", project=project, script_id=script_id, phase="launching", shots=[])
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    ctx = await _launch(p)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    try:
        await page.goto(edit_url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        write_status(phase="goto_error", note=f"goto 실패: {e}")
    # 인증 대기(세션 재사용) 최대 60초
    deadline = time.time() + 60
    state = "loading"
    while time.time() < deadline:
        url = page.url
        try:
            body = await page.inner_text("body", timeout=3000)
        except Exception:
            body = ""
        state = _auth_state(url, body)
        if state in ("authed", "blocked"):
            break
        await asyncio.sleep(4)
    if state != "authed":
        s = await _shot(page, "inspect_no_auth")
        write_status(phase="inspect_no_auth", authed=False, note=f"세션 재사용 인증 실패(state={state}).", shots=[s])
        await ctx.close(); return
    await page.wait_for_timeout(4000)
    shots = [await _shot(page, "inspect_editor")]
    sel = await _open_history(page)
    await page.wait_for_timeout(2500)
    shots.append(await _shot(page, "inspect_history"))
    # history 패널 OPEN 상태에서 aria-label 재덤프(패널 컨트롤 포착)
    nav_after = await _dump_nav(page)
    # 버전 행 hover → 행별 ⋮ 액션 메뉴 노출 시도. 여러 행 후보 셀렉터.
    row_dump = {}
    hover_shot = "(none)"
    for rsel in ["[role='listitem']", "[role='row']", "li", "[data-version]", "[jsname]"]:
        try:
            loc = page.locator(rsel)
            cnt = await loc.count()
            row_dump[rsel] = cnt
        except Exception as e:
            row_dump[rsel] = f"err:{e}"
    # '버전 200' 텍스트 요소 근처 hover
    try:
        v = page.get_by_text("버전 200", exact=False).first
        if await v.count() > 0:
            await v.hover(timeout=4000)
            await page.wait_for_timeout(1200)
            hover_shot = await _shot(page, "inspect_row_hover")
            shots.append(hover_shot)
    except Exception as e:
        hover_shot = f"(hover fail: {e})"
    # 삭제 관련 라벨/텍스트 재탐지
    bulk_hits = {}
    for t in ["일괄 삭제", "일괄삭제", "Bulk delete", "이 버전 삭제", "버전 삭제", "삭제", "추가 작업", "더보기", "옵션"]:
        try:
            bulk_hits[t] = await page.get_by_text(t, exact=False).count()
        except Exception:
            bulk_hits[t] = -1
    write_status(phase="inspect_done", authed=True, history_selector=sel,
                 nav_labels_after_history=nav_after, row_counts=row_dump,
                 bulk_text_hits=bulk_hits, hover_shot=hover_shot, shots=shots,
                 note="history OPEN 상태 재덤프+행 hover 스샷. 삭제 어포던스 확인용.")
    await page.wait_for_timeout(1500)
    await ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["probe", "inspect", "delete"], required=True)
    ap.add_argument("--project", choices=list(PROJECTS.keys()), required=True)
    ap.add_argument("--i-am-sure", action="store_true")
    a = ap.parse_args()
    if a.mode == "probe":
        asyncio.run(run_probe(a.project))
    elif a.mode == "inspect":
        asyncio.run(run_inspect(a.project))
    else:
        asyncio.run(run_delete(a.project, a.i_am_sure))


if __name__ == "__main__":
    main()
