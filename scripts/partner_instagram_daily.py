#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""partner_instagram_daily.py — 파트너 인스타 하루 한 편 자동 게시 (시보 · 배 12718 · GM 2026-09-18 「인스타그램 발행 가능 · 그 내용으로 블로그 등 자동화」).

무엇을 하나(매일 06:30 · 파트너 승낙 없이 바로 게시):
  ① 주제 하나를 고른다(blog_style.json topic_bank 에서 블로그·인스타가 아직 안 쓴 것 — 인스타가 그날 주제의 원천이다)
  ② 캡션 300자 안(담담 · 금액 0 · 금지어 0) + 해시태그 15개 · 마지막 줄은 상담 페이지 주소를 코드가 붙인다
  ③ 파트너 화면 사진(erp/admin/{tenant}/img · 로고 제외)에서 3장을 돌려 뽑아 1080×1080 으로 잘라
  ④ instagram_upload_playwright.py 폴더 규격(output/ig_NN.jpg + 큐레이션_추천.md)으로 저장하고
  ⑤ 세션(profiles/instagram/{account})이 있으면 그 자리에서 게시 → 게시물 페이지를 다시 열어 캡션이 붙었는지 실측한다.
     세션이 없으면 임시안만 두고 로그 한 줄(다캠 = gm_asks #56). 실패는 재시도 없이 로그 + 자동화현황방 한 줄.
  블로그(partner_blog_daily)가 이 상태 파일의 오늘 주제·캡션·사진 3장을 씨앗으로 본문을 만든다(인스타 → 블로그 순).

정본 = 파트너 blog_style.json(말투·금지어·태그·상담 주소) · client.json(사실). 계정 값은 어디에도 두지 않는다(서버 1531 규칙 · 세션 프로필만).
상태 = status/partner_instagram/{client}.json (runs: 날짜·주제·캡션·사진·게시 URL·실측 · photo_idx).
가드 = 실행 잠금(status/.{client}_instagram_daily.lock) + 같은 날 게시가 있으면 skip.

  C:/Python314/python.exe scripts/partner_instagram_daily.py jo              # 오늘 임시안 → 게시 → 실측
  C:/Python314/python.exe scripts/partner_instagram_daily.py jo --no-publish # 임시안만 만든다
  C:/Python314/python.exe scripts/partner_instagram_daily.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
PY = sys.executable
PROFILES = ROOT / "profiles" / "instagram"

CLIENTS = {
    "jo": {"dir": ROOT / "2. 브랜드_자료" / "11_고척골프_조재오부장님", "tenant": "gocheokgolf", "account": "jo",
           "room_key": "조재오", "owner": "조재오 지점장님", "name": "고척GDR QA 골프존"},
    "dc": {"dir": ROOT / "2. 브랜드_자료" / "10_다이어트캠프_브랜드가이드", "tenant": "dietcamp", "account": "dc",
           "room_key": "이승기", "owner": "이승기 대표님", "name": "다이어트캠프"},
}
ADMIN = ROOT / "3. 웰페리온 가이드" / "erp" / "admin"
STATE_DIR = ROOT / "status" / "partner_instagram"
CAPTION_MAX = 300
IG_SIZE = 1080
SKIP_IMG = re.compile(r"logo|cover", re.I)


def style_of(c: dict) -> dict:
    return json.loads((c["dir"] / "blog_style.json").read_text(encoding="utf-8"))


def client_json(c: dict) -> dict:
    p = c["dir"] / "client.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_state(key: str) -> dict:
    p = STATE_DIR / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"photo_idx": 0, "runs": []}


def save_state(key: str, st: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"{key}.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_topic(style: dict, st: dict) -> str | None:
    """topic_bank 에서 블로그(used_topics)도 인스타(runs)도 아직 안 쓴 첫 주제 — 인스타가 그날 주제를 정하고 블로그가 따른다."""
    p = ROOT / style["state_file"]
    used = set(json.loads(p.read_text(encoding="utf-8")).get("used_topics", [])) if p.exists() else set()
    used |= {r.get("topic") for r in st.get("runs", [])}
    return next((t for t in style["topic_bank"] if t not in used), None)


def today_run(st: dict, today: str) -> dict | None:
    """오늘 만든 런(있으면) — 블로그 씨앗·하루 한 번 가드가 같이 본다."""
    return next((r for r in reversed(st.get("runs", [])) if str(r.get("at", "")).startswith(today)), None)


def hashtags(style: dict) -> list[str]:
    t = style.get("tags") or {}
    tags = t.get("instagram_15") or (t.get("core_25") or [])[:15]
    must = style.get("required_tag")
    if must and must not in tags:
        tags = [must] + tags
    return tags[:15]


def forbidden_words(style: dict) -> list[str]:
    return list(style.get("banned_ours") or []) + list((style.get("philosophy") or {}).get("forbidden") or [])


def build_prompt(topic: str, style: dict, cj: dict, c: dict) -> str:
    ph = style.get("philosophy") or {}
    fc = (cj.get("facts_confirmed") or {})
    return (
        f"아래 조건으로 {c['name']} 인스타그램 캡션 한 편만 써라. 결과는 캡션 본문만(제목·해시태그·따옴표·설명 없이).\n"
        f"주제: {topic}\n"
        f"한 줄(브랜드): {ph.get('one_line', '')}\n"
        f"쓰는 법: {json.dumps(ph.get('how_to_write', ''), ensure_ascii=False)}\n"
        f"금지: {json.dumps(forbidden_words(style), ensure_ascii=False)} · 금액·가격 숫자 · 마감·임박 재촉 · 링크 · 이모지 3개 넘게\n"
        f"확인된 사실만: {json.dumps({k: fc.get(k) for k in ('hours', 'parking', 'scale', 'address') if fc.get(k)}, ensure_ascii=False)}\n"
        f"길이 {CAPTION_MAX - len(tail_of(style)) - 2}자 안 · 첫 줄은 손님 마음에 걸리는 한 문장 · 상담 안내 줄은 쓰지 않는다(코드가 붙인다) · 차분히 설명하는 말투 · 존댓말\n"
    )


def tail_of(style: dict) -> str:
    """캡션 마지막 줄 — 인스타 프로필 링크는 파트너가 안 걸어 둔 계정이 있어 「프로필 링크에서」라 쓰면 거짓이 된다.
    블로그 푸터 정본(footer_canon.counsel)의 상담 주소를 그대로 적는다."""
    m = re.search(r"https?://\S+", (style.get("footer_canon") or {}).get("counsel") or "")
    if not m:
        raise SystemExit("blog_style.json footer_canon.counsel 에 상담 주소가 없다 — 캡션 마지막 줄을 못 만든다")
    return m.group(0).replace("https://", "") + " 에서 24시간 상담"


def with_tail(body: str, tail: str) -> str:
    return body.strip() + "\n\n" + tail


def fallback_caption(topic: str, c: dict, tail: str) -> str:
    return with_tail(f"{topic}\n\n{c['name']}에서 편하게 물어보셔도 됩니다.", tail)


def run_checks(caption: str, style: dict) -> list[str]:
    errs = []
    low = caption.replace(tail_of(style), "").lower()   # 상담 주소(erp.wellperion.com)는 정본 줄이라 혼입 검사에서 뺀다(블로그와 같은 규칙)
    for w in forbidden_words(style):
        if w and w.lower() in low:
            errs.append(f"금지어 「{w}」")
    if re.search(r"[0-9][0-9,]*\s*원", caption):
        errs.append("금액 숫자")
    if len(caption) > CAPTION_MAX:
        errs.append(f"캡션 {len(caption)}자 — {CAPTION_MAX}자 초과")
    if "|---|" in caption or "GM요청" in caption:
        errs.append("보고 표 혼입")
    return errs


def trim_to_sentence(caption: str, limit: int, tail: str) -> str:
    """문장 경계에서 잘라 limit 안으로 — 마지막 줄(상담 안내)은 남긴다."""
    body = caption.replace(tail, "").strip()
    out = ""
    for sent in re.split(r"(?<=[.!?다요])\s+", body):
        if len(out) + len(sent) + len(tail) + 2 > limit:
            break
        out = (out + " " + sent).strip()
    return with_tail(out or body[: limit - len(tail) - 2], tail)


def gen_prompt(c: dict, topic: str) -> str:
    """힉스필드 보충 컷 문장 — 시설 실사가 아니라 TIP·개념 장면만(사람 얼굴·글자·간판 없음 · 다큐 톤)."""
    return (f"{c['name']} 인스타그램 개념 컷 — 주제 「{topic}」 를 설명하는 장면 하나. 실사 다큐 사진 톤, 자연광, "
            f"사람 얼굴·글자·로고·간판 없음, 정사각 구도, 과장된 색 없음")


def gen_photo(ref: Path | None, prompt: str, dst: Path, max_credits: float = 2) -> Path | None:
    """파트너 사진이 3장에 못 미칠 때만 — 힉스필드 nano_banana(1:1 · 실측 1크레딧) 한 장(GM 2026-09-18 「힉스필드도 붙여놔서」).
    비용을 먼저 재고 상한을 넘으면 만들지 않는다 · 실패는 재시도 없이 None(호출부가 부족한 채로 멈춘다)."""
    import shutil  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    exe = shutil.which("higgsfield")
    if not exe:
        print("[gen] higgsfield CLI 없음 — 보충 컷 생략"); return None
    spec = ["nano_banana", "--prompt", prompt, "--aspect_ratio", "1:1"] + (["--image-references", str(ref)] if ref else [])

    def cli(args: list[str]):
        p = subprocess.run([exe, *args, "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=400)
        try:
            return json.loads(p.stdout) if p.returncode == 0 else None
        except json.JSONDecodeError:
            return None
    cost = cli(["generate", "cost", *spec])
    credits = float((cost or {}).get("credits", 99))
    if credits > max_credits:
        print(f"[gen] 비용 {credits}크레딧 > 상한 {max_credits} — 만들지 않음"); return None
    resp = cli(["generate", "create", *spec, "--wait", "--wait-timeout", "5m", "--wait-interval", "5s"])
    job = (resp[0] if isinstance(resp, list) else resp) or {}
    url = job.get("result_url") if job.get("status") == "completed" else None
    if not url:
        print(f"[gen] 생성 실패 — status={job.get('status')}"); return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dst)
    print(f"[gen] 보충 컷 {dst.name} · {credits}크레딧")
    return dst


def pick_photos(c: dict, st: dict, n: int = 3, topic: str = "", folder: Path | None = None) -> list[Path]:
    """파트너 시설 사진 우선(돌려 뽑기) · 모자라는 장수만 힉스필드 개념 컷으로 보충(topic·folder 를 준 실행에서만)."""
    imgs = sorted(p for p in (ADMIN / c["tenant"] / "img").glob("*.jpg") if not SKIP_IMG.search(p.name))
    if len(imgs) < n and folder is not None:
        for k in range(n - len(imgs)):
            g = gen_photo(imgs[0] if imgs else None, gen_prompt(c, topic), folder / f"gen_{k + 1}.jpg")
            if g:
                imgs.append(g)
    if len(imgs) < n:
        raise SystemExit(f"사진 부족 — {len(imgs)}장(3장 필요) · {ADMIN / c['tenant'] / 'img'}")
    i = int(st.get("photo_idx") or 0) % len(imgs)
    chosen = [imgs[(i + k) % len(imgs)] for k in range(n)]
    st["photo_idx"] = (i + n) % len(imgs)
    return chosen


def square(src: Path, dst: Path) -> None:
    from PIL import Image  # noqa: PLC0415
    im = Image.open(src).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((IG_SIZE, IG_SIZE), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=90)


def write_folder(folder: Path, caption: str, tags: list[str], photos: list[Path], c: dict) -> None:
    for k, p in enumerate(photos, 1):
        square(p, folder / "output" / f"ig_{k:02d}.jpg")
    md = ("## post A\n\n### 캡션\n" + caption.strip() + "\n\n### 해시태그\n" + " ".join(tags) +
          "\n\n### Collaborator\n(없음)\n\n### 종목\n" + c["name"] + "\n")
    (folder / "큐레이션_추천.md").write_text(md, encoding="utf-8")


def make_caption(topic: str, style: dict, cj: dict, c: dict, key: str) -> tuple[str, str]:
    """모델 캡션(검사 통과) 또는 규칙 캡션 — (캡션, 모델 이름)."""
    from model_router import run_claude  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    tail = tail_of(style)
    body, used = run_claude(build_prompt(topic, style, cj, c), label=f"partner-ig-{key}", cwd=tempfile.gettempdir())
    caption = with_tail(body, tail) if (body or "").strip() else fallback_caption(topic, c, tail)
    errs = run_checks(caption, style)
    if errs and all(e.startswith("캡션 ") for e in errs):   # 길이만 넘친 것은 한 번 줄여 본다(규칙 캡션은 마지막 수단)
        shorter, _ = run_claude(f"아래 인스타 캡션을 {CAPTION_MAX - len(tail) - 20}자 안으로 줄여라. 말투·문장 순서는 그대로, 결과는 캡션만.\n\n{body}",
                                label=f"partner-ig-{key}-short", cwd=tempfile.gettempdir())
        if shorter and not run_checks(with_tail(shorter, tail), style):
            caption, errs = with_tail(shorter, tail), []
        else:                                                  # 모델이 길이를 안 지키면 문장 경계에서 자른다(내용은 앞부분 그대로)
            cut = trim_to_sentence(caption, CAPTION_MAX - 30, tail)
            if not run_checks(cut, style):
                caption, errs = cut, []
    if errs:
        print("[check] 캡션 탈락 —", " · ".join(errs), "→ 규칙 캡션으로 대체")
        caption, used = fallback_caption(topic, c, tail), None
    return caption, used or "규칙"


POST_URL_RE = re.compile(r"https?://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?")


def publish(c: dict, folder: Path) -> tuple[int, str | None]:
    """업로더로 게시 — (rc, 게시 URL). 업로더의 자체 텔레그램 보고는 끈다(GM 봇방에 안 보낸다 · 실패 알림은 여기서 자동화현황방으로)."""
    cmd = [PY, str(ROOT / "scripts" / "instagram_upload_playwright.py"), "--mode", "publish",
           "--account", c["account"], "--content-folder", str(folder), "--tenant", "wellperion"]
    print("[publish]", " ".join(cmd[2:]))
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, IG_SUPPRESS_TELEGRAM="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
    out = (p.stdout or "") + (p.stderr or "")
    for line in out.splitlines():
        if line.startswith(("[INFO] post", "[ERROR]", "[WARN]")):
            print("  ", line[:200])
    m = POST_URL_RE.search(next((ln for ln in out.splitlines() if ln.strip().startswith("post A:")), ""))
    return p.returncode, (m.group(0) if m else None)


def verify(c: dict, url: str, caption: str) -> bool:
    """게시물 페이지를 그 계정 세션으로 다시 열어 캡션 첫 문장이 실제로 붙었는지 본다(읽기만 · ig_publish_verify 헬퍼 재사용)."""
    import asyncio  # noqa: PLC0415
    import ig_publish_verify as v  # noqa: PLC0415

    async def _go() -> bool:
        p, ctx = await v._launch(c["account"])
        try:
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2500)
            live, _ = await v._read_post(page)
            return v._squash(caption.splitlines()[0])[:20] in v._squash(live)
        finally:
            await ctx.close()
            await p.stop()
    try:
        return asyncio.run(_go())
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] 실측 실패(게시는 됐을 수 있음): {type(exc).__name__}: {exc}")
        return False


LOGIN_URL = "https://www.instagram.com/accounts/login/"


def try_login(c: dict, key: str, st: dict) -> bool:
    """세션이 없거나 풀렸을 때 1회 — 서버 계정 자리(플랫폼관리 코드 1531 · 실행 때 GET → 메모리만 · 디스크 금지)로 로그인.
    2단계 인증·확인 문턱이면 그 자리에서 멈추고 state login_needed 에 남긴다(파트너 방에 직접 묻지 않는다 · 문안은 시보가 GM 승인 뒤)."""
    import asyncio  # noqa: PLC0415
    from partner_blog_daily import _read_login_secret  # noqa: PLC0415
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sec = _read_login_secret(c["tenant"], "instagram")
    if not sec:
        st["login_needed"] = f"{now} 서버 계정 자리 없음({c['tenant']}/instagram) — 플랫폼관리 코드 1531 에 넣으면 다음 실행에 스스로 로그인"
        print("[login]", st["login_needed"]); save_state(key, st)
        return False

    async def _go() -> tuple[bool, str]:
        from playwright.async_api import async_playwright  # noqa: PLC0415
        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(str(PROFILES / c["account"]), headless=True,
                                                             args=["--disable-blink-features=AutomationControlled"])
            try:
                page = await ctx.new_page()
                await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(2500)
                if await page.locator('input[name="password"]').count() == 0:
                    return True, page.url                       # 이미 로그인돼 있다
                await page.fill('input[name="username"]', sec["NAVER_ID"])
                await page.fill('input[name="password"]', sec["NAVER_PW"])
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(7000)
                url = page.url
                blocked = any(s in url for s in ("/challenge/", "two_factor", "/accounts/login")) or \
                    await page.locator('input[name="verificationCode"]').count() > 0
                if not blocked:
                    for txt in ("정보 저장", "Save info"):          # 세션 쿠키를 영속으로
                        btn = page.locator(f'button:has-text("{txt}")')
                        if await btn.count():
                            await btn.first.click(); await page.wait_for_timeout(2000); break
                return (not blocked), url
            finally:
                await ctx.close()
    try:
        ok, url = asyncio.run(_go())
    except Exception as exc:  # noqa: BLE001
        ok, url = False, f"{type(exc).__name__}: {exc}"[:120]
    st["login_needed"] = "" if ok else f"{now} 인증번호 필요(2단계 인증·확인 문턱) — {url}"
    print("[login]", "성공(세션 저장)" if ok else st["login_needed"]); save_state(key, st)
    return ok


def alert(msg: str) -> None:
    """AI 살림 경보 = 자동화현황방 한 줄(GM 봇방·파트너 방 아님)."""
    try:
        import alert_router  # noqa: PLC0415
        from notify.telegram_send import send  # noqa: PLC0415
        send(alert_router.route(alert_router.TECH_CHECK), msg)
    except Exception as exc:  # noqa: BLE001
        print(f"[alert] 자동화현황방 알림 실패(무시): {exc}")


def acquire_lock(key: str) -> bool:
    """같은 업체 실행이 겹치면 두 번 올라간다(2026-09-15 다캠 블로그 임시저장 2건) — 잠금 파일 하나로 한 번에 하나만."""
    lock = ROOT / "status" / f".{key}_instagram_daily.lock"
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if datetime.now().timestamp() - lock.stat().st_mtime < 40 * 60:
            return False
        lock.unlink(missing_ok=True)   # 40분 넘은 잠금은 죽은 프로세스가 남긴 것
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode()); os.close(fd)
    import atexit  # noqa: PLC0415
    atexit.register(lambda: lock.unlink(missing_ok=True))
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("client", nargs="?", choices=sorted(CLIENTS))
    ap.add_argument("--no-publish", action="store_true", help="임시안만 만든다(게시 안 함)")
    ap.add_argument("--topic", default="", help="주제를 직접 줄 때(기본 = topic_bank 에서 안 쓴 첫 주제)")
    ap.add_argument("--retry", action="store_true", help="오늘 실패 기록이 있어도 다시 게시(세션 재로그인 뒤 사람이 부를 때만)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.client:
        ap.error("client")
    c = CLIENTS[a.client]
    if datetime.now().weekday() >= 5:
        print("[skip] 주말 정지(토·일 · GM 2026-09-18 평일만 게시) — 생성·게시 없음")
        return 0
    if not acquire_lock(a.client):
        print(f"[skip] 이미 도는 중 — 잠금 status/.{a.client}_instagram_daily.lock")
        return 0
    style, cj, st = style_of(c), client_json(c), load_state(a.client)
    today = datetime.now().strftime("%Y-%m-%d")
    run = today_run(st, today)
    if run and run.get("published_at"):
        print(f"[skip] 오늘({today}) 이미 게시 — {run.get('post_url') or run['published_at']}")
        return 0
    if run and run.get("publish_rc") is not None and not a.retry:
        print(f"[skip] 오늘({today}) 게시 실패 기록 있음(rc={run['publish_rc']}) — 재시도하지 않는다(로그·자동화현황방에 이미 남김 · 사람이 --retry)")
        return 0
    if run and run.get("caption"):                      # 오늘 임시안은 있고 게시만 안 된 날(세션 없음 등) — 다시 만들지 않는다
        folder, caption = Path(run["folder"]), run["caption"]
        print(f"[reuse] 오늘 임시안 그대로 — {folder.name} · 캡션 {len(caption)}자")
    else:
        topic = a.topic or pick_topic(style, st)
        if not topic:
            alert(f"⚠️ {c['name']} 인스타 — topic_bank 를 다 썼다(주제 추가 필요)")
            return 1
        caption, used = make_caption(topic, style, cj, c, a.client)
        folder = c["dir"] / "05_콘텐츠_초안" / "instagram" / datetime.now().strftime("%y%m%d")
        tags, photos = hashtags(style), pick_photos(c, st, topic=topic, folder=folder)
        write_folder(folder, caption, tags, photos, c)
        print(f"[ok] {folder} · 사진 {[p.name for p in photos]} · 캡션 {len(caption)}자 · 모델 {used}")
        run = {"at": datetime.now().isoformat(timespec="seconds"), "topic": topic, "folder": str(folder),
               "photos": [p.name for p in photos], "caption": caption, "model": used}
        st["runs"].append(run); st["last_folder"] = str(folder)
        save_state(a.client, st)
    if a.no_publish:
        return 0
    if not (PROFILES / c["account"]).exists() and not try_login(c, a.client, st):
        print(f"[skip] {c['name']} 인스타 세션 없음 · 로그인 대기 — 임시안만 두고 게시 안 함")
        return 0
    rc, url = publish(c, folder)
    if rc == 2 and try_login(c, a.client, st):       # 세션이 풀린 것 — 서버 계정 자리로 1회 재로그인 뒤 다시(게시 재시도가 아니다)
        rc, url = publish(c, folder)
    run["publish_rc"] = rc
    if rc == 0 and url:
        run["published_at"] = datetime.now().isoformat(timespec="seconds")
        run["post_url"] = url
        run["verified"] = verify(c, url, caption)
        print(f"[published] {url} · 실측 {'일치' if run['verified'] else '미확인'}")
    elif rc == 2:
        print(f"[wait] {c['name']} 인스타 로그인 대기 — {st.get('login_needed')}")   # 사람 손 대기는 경보가 아니다(state login_needed 한 칸)
    else:
        # rc 9 = 성공 토스트는 떴는데 URL 미확정(업로더 규칙: 재시도 금지 · 중복 게시 방지) — 실패와 같이 사람 확인으로 넘긴다
        print(f"[fail] {c['name']} 인스타 게시 실패 rc={rc} — 재시도하지 않는다")
        alert(f"⚠️ {c['name']} 인스타 자동 게시 실패 rc={rc} · {folder.name} · 재시도 없음(logs/partner_instagram_daily.log)")
    save_state(a.client, st)
    return 0 if run.get("published_at") else 1


def self_test() -> int:
    c = CLIENTS["jo"]
    style = style_of(c)
    assert len(hashtags(style)) == 15 and hashtags(style)[0] == "#고척골프"
    assert run_checks("체험권 99,000원", style) and run_checks("웰페리온이 만든", style)
    assert not run_checks("차분히 연습하는 저녁", style)
    st = {"photo_idx": 0}
    p1 = pick_photos(c, st); p2 = pick_photos(c, st)
    assert len(p1) == 3 and p1 != p2 and not any(SKIP_IMG.search(p.name) for p in p1)
    tail = tail_of(style)
    assert tail == "erp.wellperion.com/gocheokgolf/counsel/ 에서 24시간 상담", tail
    assert tail_of(style_of(CLIENTS["dc"])).startswith("erp.wellperion.com/dietcamp/counsel/")
    long = with_tail("첫 문장입니다. " * 30, tail)
    cut = trim_to_sentence(long, CAPTION_MAX - 30, tail)
    assert len(cut) <= CAPTION_MAX - 30 and cut.endswith(tail) and cut.startswith("첫 문장입니다.")
    assert fallback_caption("주제", c, tail).endswith(tail)
    # 주제 = 블로그가 쓴 것도 인스타가 쓴 것도 뺀 첫 주제
    bank = style["topic_bank"]
    assert pick_topic(style, {"runs": [{"topic": t} for t in bank]}) is None
    assert pick_topic(style, {"runs": []}) not in json.loads((ROOT / style["state_file"]).read_text(encoding="utf-8")).get("used_topics", [])
    # 오늘 런·가드
    assert today_run({"runs": [{"at": "2026-09-18T06:30:00"}]}, "2026-09-18")["at"].startswith("2026-09-18")
    assert today_run({"runs": [{"at": "2026-09-17T06:30:00"}]}, "2026-09-18") is None
    assert POST_URL_RE.search("  post A: https://www.instagram.com/p/AbC_12-x/").group(0) == "https://www.instagram.com/p/AbC_12-x/"
    gp = gen_prompt(c, "주제")
    assert "주제" in gp and "얼굴" in gp and "글자" in gp
    assert gen_photo(None, gp, Path("x.jpg"), max_credits=0) is None, "상한 0 인데 만들었다"   # 비용 조회만(크레딧 0)
    print("partner_instagram_daily 자가점검 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
