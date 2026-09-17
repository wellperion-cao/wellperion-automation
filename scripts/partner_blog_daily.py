# -*- coding: utf-8 -*-
"""
partner_blog_daily.py — 파트너 블로그 매일 임시저장 자동화 (테넌트 공용).
GM 지시 2026-09-10(고척골프) · 2026-09-15(다이어트캠프 합류): 「데이터값들 정확하면
블로그 내용 학습해서 그 방식대로 블로그 매일 작업해서 임시저장해놔줘」

정본(이 파일이 지어내지 않고 그대로 읽는 곳) — 업체마다 하나:
  --client jo (고척골프) = "2. 브랜드_자료/11_고척골프_조재오부장님/blog_style.json"
  --client dc (다이어트캠프) = "2. 브랜드_자료/10_다이어트캠프_브랜드가이드/blog_style.json"
  --client ax (AX 랩스 「피트니스 AX」) = "2. 브랜드_자료/12_AX랩스/blog_style.json"
    (배 2694 ② · 계정 없음 — 편집 라인·발행기 준비까지만. 사람용 정리본 =
     status/briefs/CMO-피트니스AX-편집라인-20260916.md, 코드는 blog_style.json 만 읽는다)
프롬프트도 blog_style.json 의 prompt_template 키가 정본이다 — 이 코드는 값만 끼운다
(2026-09-10~11 네 번 실패 끝에 겨우 도는 프롬프트라 구조에서 재조립하지 않는다).

흐름: 주제 선택(상태 파일로 중복 방지) → run_claude 로 본문(인사~마지막 TIP)만 생성
→ 푸터·해시태그는 footer_canon·tags.core_25 그대로 코드로 붙임(정확성 보장) →
검사 통과해야 → naver_blog_upload_playwright.py --mode draft (WP_TENANT={client}) 로 임시저장.

상태 = style["state_file"] (쓴 주제 · 실행 기록). 로그 = style["log_file"].
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIRS = {
    "jo": ROOT / "2. 브랜드_자료" / "11_고척골프_조재오부장님",
    "dc": ROOT / "2. 브랜드_자료" / "10_다이어트캠프_브랜드가이드",
    "ax": ROOT / "2. 브랜드_자료" / "12_AX랩스",
}
UPLOADER = ROOT / "scripts" / "naver_blog_upload_playwright.py"

sys.path.insert(0, str(ROOT / "scripts"))


def style_file(client: str) -> Path:
    return CLIENT_DIRS[client] / "blog_style.json"


def load_style(client: str) -> dict:
    return json.loads(style_file(client).read_text(encoding="utf-8"))


def log_file(style: dict) -> Path:
    return ROOT / style["log_file"]


def log(style: dict, msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    # 2026-09-11: 로그 파일이 다른 프로세스에 잡혀 PermissionError 가 나 스크립트가 통째로
    # 죽었다 — 그 바람에 실패 기록조차 상태 파일에 남지 않았다. 로그는 부수적이다.
    lf = log_file(style)
    try:
        lf.parent.mkdir(parents=True, exist_ok=True)
        with lf.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as exc:
        print(f"[WARN] 로그 기록 실패(무시): {exc}")


def notify(msg: str) -> None:
    """GM 업무보고방 1줄 — alert_router 단일 관문(약속 L01) + notify.telegram_send 재사용."""
    try:
        import alert_router
        from notify.telegram_send import send as tg_send
        chat_id = alert_router.route(alert_router.GM_ACTION)
        tg_send(chat_id, msg)
    except Exception as e:
        print(f"[WARN] 텔레그램 알림 실패(무시): {e}")


def state_file(style: dict) -> Path:
    return ROOT / style["state_file"]


def load_state(style: dict) -> dict:
    sf = state_file(style)
    if sf.exists():
        try:
            return json.loads(sf.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"used_topics": [], "runs": []}


def save_state(style: dict, state: dict) -> None:
    sf = state_file(style)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _already_ok_today(state: dict) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    return any(r.get("result") == "ok" and r.get("date", "").startswith(today)
               for r in state.get("runs", []))


SECRET_FETCH_URL = "https://erp.wellperion.com/api/partner-secrets/fetch"
PUSH_KEY_FILE = Path.home() / ".claude" / "token_push.key"


def _push_key() -> str:
    """발행 PC 열쇠 — token_usage_push 와 같은 파일(없으면 환경변수 ERP_TOKEN_PUSH_KEY)."""
    try:
        v = PUSH_KEY_FILE.read_text(encoding="utf-8").strip()
        if v:
            return v
    except OSError:
        pass
    return (os.environ.get("ERP_TOKEN_PUSH_KEY") or "").strip()


def _secret_from_response(status: int, body: dict | None) -> dict[str, str] | None:
    """서버 응답 → {NAVER_ID, NAVER_PW} 또는 None. 값은 어디에도 찍지 않는다."""
    if status != 200 or not body or not body.get("ok"):
        return None
    nid, npw = str(body.get("id") or "").strip(), str(body.get("pw") or "").strip()
    if not nid or not npw:
        return None
    return {"NAVER_ID": nid, "NAVER_PW": npw}


def _read_login_secret(tenant: str, channel: str = "naver-blog") -> dict[str, str] | None:
    """파트너 계정은 서버 플랫폼관리 한 곳(GM 확정 2026-09-15 · 보기는 코드 1531)에서만 가져온다.
    실행 때 GET 으로 받아 환경변수로만 쓰고 디스크에 남기지 않는다. PC 파일 폴백은 없다."""
    import json as _json
    import urllib.error
    import urllib.parse
    import urllib.request
    key = _push_key()
    if not key:
        return None
    url = SECRET_FETCH_URL + "?" + urllib.parse.urlencode({"tenant": tenant, "channel": channel})
    req = urllib.request.Request(url, headers={"X-Token-Push-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return _secret_from_response(r.status, _json.load(r))
    except urllib.error.HTTPError as e:
        # 404 = 아직 안 넣음 · 401 = 열쇠 불일치. 값이 아니라 상태만 로그에 남긴다.
        print(f"[INFO] 서버 계정 조회 {tenant}/{channel}: HTTP {e.code}")
        return None
    except Exception as e:                      # noqa: BLE001
        print(f"[WARN] 서버 계정 조회 실패({type(e).__name__})")
        return None


def _try_relogin(style: dict, tenant: str) -> str:
    """세션이 풀린 것으로 판단됐을 때 비밀 파일로 자동 재로그인 시도.

    반환값: "no-secret"(비밀 파일 없음) · "auto-ok"(로그인 성공, 내일까지 버팀) ·
    "auto-fail"(로그인 시도했지만 실패 또는 확인 절차에 막힘).
    """
    secret = _read_login_secret(tenant)
    if secret is None:
        return "no-secret"
    env = dict(os.environ)
    env["WP_TENANT"] = tenant
    env.update(secret)
    log(style, "자동 재로그인 시도 — naver_blog_upload_playwright.py --mode setup")
    try:
        r = subprocess.run(
            [sys.executable, str(UPLOADER), "--mode", "setup"],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=17 * 60,
        )
        setup_out = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        log(style, "자동 재로그인 실패 — setup 시간초과(17분)")
        return "auto-fail"
    tagged = [ln for ln in setup_out.splitlines() if ln.startswith(("[INFO]", "[WARN]", "[ERROR]"))]
    log(style, "setup 결과:\n" + "\n".join(tagged))
    check = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_blog_session.py"), "--tenant", tenant],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return "auto-ok" if check.returncode == 0 else "auto-fail"


def pick_topic(style: dict, state: dict) -> str | None:
    used = set(state.get("used_topics", []))
    for t in style["topic_bank"]:
        if t not in used:
            return t
    return None


def build_prompt(topic: str, style: dict, axis: dict | None = None, state: dict | None = None) -> str:
    """style["prompt_template"] 에 값만 끼운다 — 프롬프트 문자열 자체는 blog_style.json 이 정본.

    axis 는 보통 랜덤이다(jo·dc). philosophy.cycle=true(ax) 면 state 의 발행 회차(runs 길이)로
    axes 를 순서대로 돈다 — GM 09-16 「3축 순환」. 자가점검에서만 axis 를 직접 넘겨 결과를 고정한다.
    """
    if axis is None:
        axes = style["philosophy"]["axes"]
        if style["philosophy"].get("cycle") and state is not None:
            axis = axes[len(state.get("runs", [])) % len(axes)]
        else:
            axis = random.choice(axes)
    markers = style["markers"]
    return style["prompt_template"].format(
        topic=topic,
        hard_rules_json=json.dumps(style["hard_rules"], ensure_ascii=False, indent=2),
        divider=markers.get("divider", ""),
        section_emoji_joined=", ".join(markers.get("section_emoji", [])),
        section_prefix=markers.get("section_prefix", ""),
        checklist=markers.get("checklist"),
        axis_name=axis["name"],
        axis_body=axis["body"],
        how_to_write_json=json.dumps(style["philosophy"]["how_to_write"], ensure_ascii=False),
        forbidden_json=json.dumps(style["philosophy"]["forbidden"], ensure_ascii=False),
        tip_header=markers.get("tip_header", ""),
        facility_facts_json=json.dumps(style["facility_facts"], ensure_ascii=False, indent=2),
    )


def build_footer_and_tags(style: dict) -> str:
    fc = style["footer_canon"]
    divider = style["markers"]["divider"]
    lines = [fc["name"], fc["address"], fc["parking"], fc["hours"], fc["phone"], fc["closing"]]
    if fc.get("counsel"):   # 상담 페이지 한 줄(GM 2026-09-17 「상담봇 활성화」) — 값이 있는 파트너만
        lines.append(fc["counsel"])
    footer = "\n".join(lines)
    tags = " ".join(style["tags"]["core_25"])
    return f"\n\n{divider}\n\n{footer}\n\n{tags}\n"


def assemble_body(llm_body: str, style: dict) -> str:
    return llm_body.strip() + build_footer_and_tags(style)


# ── 검사 (보내기 전 코드로 막는다) ──────────────────────────────────
def run_checks(body: str, style: dict) -> list[str]:
    errs: list[str] = []
    fc = style["footer_canon"]
    for key in ("name", "address", "parking", "hours", "phone", "closing", "counsel"):
        if fc.get(key) and fc[key] not in body:
            errs.append(f"푸터가 정본과 다름({key})")
    allowed_amounts = set(style["allowed_amounts"])
    amounts = re.findall(r"[0-9][0-9,]*\s*원", body)
    for a in amounts:
        num = int(re.sub(r"[^0-9]", "", a))
        if num not in allowed_amounts:
            errs.append(f"허용 안 된 금액 발견: {a.strip()}")
    required_tag = style["required_tag"]
    if required_tag not in body:
        errs.append(f"{required_tag} 태그 없음")
    if "|---|" in body.replace(" ", "") or "GM요청" in body or "더나았을방법" in body:
        errs.append("블로그 글이 아니라 업무 보고 표가 왔다")
    low = body.replace(fc.get("counsel") or "<none>", "").lower()   # 상담 페이지 주소(erp.wellperion.com)는 정본 줄이라 혼입 검사에서 뺀다
    hit = [w for w in style["banned_ours"] if w.lower() in low]
    if hit:
        errs.append("우리 쪽 낱말 혼입: " + ", ".join(hit))
    # ax 전용: 웰페리온·파트너는 본문 사례로는 허용하되 제목·첫머리(앞 200자)에 앞세우면 막는다.
    # 이 키가 없는 client(jo·dc)는 그대로 통과 — 영향 0.
    lead_brands = style.get("case_brands_not_in_lead")
    if lead_brands:
        lead_hit = [b for b in lead_brands if b in body[:200]]
        if lead_hit:
            errs.append("제목·첫 200자에 사례 브랜드 등장: " + ", ".join(lead_hit))
    min_len = style["min_len"]
    if len(body) < min_len:
        errs.append(f"본문 {len(body)}자 — {min_len}자 미만")
    return errs


def run_upload(title: str, body: str, style: dict, mode: str) -> tuple[int, str]:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False)
    try:
        tmp.write(body)
        tmp.close()
        env = dict(os.environ)
        env["WP_TENANT"] = style["tenant"]
        argv = [
            sys.executable, str(UPLOADER),
            "--mode", mode,
            "--title", title,
            "--body-file", tmp.name,
        ]
        photo_dir = style.get("photo_dir")
        if photo_dir:
            # --blog-id 는 넘기지 않는다 — 업로더가 로그인 세션(WP_TENANT)에서
            # 실제 블로그 아이디를 자동 확인한다(_resolve_blog_id). 화면 프로필 표시명은
            # 실제 blogId 슬러그가 아니어서 고정 지정하면 "유효하지 않은 요청" 에러로
            # draft가 막힌다(2026-09-10 실측, 고척골프).
            argv += ["--image-dir", str(ROOT / photo_dir), "--image-glob", "*.jpg"]
        argv += ["--tags", *style["tags"]["core_25"]]
        ret = subprocess.run(argv, cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (ret.stdout or "") + (ret.stderr or "")
        return ret.returncode, out[-4000:]
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def tell_owner(style: dict, topic: str) -> None:
    """글이 올라가면 그 자리에서 담당자 방에 한 줄 알린다(GM 지시 2026-09-11 「부장님 방에도 항상 보내줘」).

    아침 통이 대신 알리게 두지 않는다 — 글은 올라간 그때 바로 아시는 편이 낫다.
    발신 관문은 종전대로 kakao_report_sender 하나다(새 발신기 만들지 않는다).
    """
    owner = style["owner"]
    text = owner["message"].format(topic=topic)
    if owner.get("telegram"):
        # 카톡 방이 없는 client(ax) — GM 텔레그램(업무보고방)으로만 알린다. 새 발신기 안 만든다.
        notify(text)
        log(style, "GM 텔레그램 알림 보냄(owner.telegram)")
        return
    try:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "kakao_report_sender.py"),
                            "--message", text, "--only-room", owner["room"], "--sender", "웰리"],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900)
        ok = r.returncode == 0 and "DONE" in (r.stdout or "")
        log(style, "%s 방 알림 %s" % (owner["room"], "보냄" if ok else "실패 — " + (r.stdout or r.stderr or "")[-200:]))
    except Exception as exc:                    # noqa: BLE001
        log(style, "%s 방 알림 실패(무시): %s" % (owner["room"], exc))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, choices=sorted(CLIENT_DIRS),
                     help="jo=고척골프 조재오 지점장님 · dc=다이어트캠프 이승기대표님 · ax=AX 랩스 「피트니스 AX」")
    ap.add_argument("--dry-run", action="store_true", help="본문만 만들고 브라우저를 열지 않는다")
    ap.add_argument("--self-test", action="store_true", help="검사 함수 자가점검")
    ap.add_argument("--no-owner-notice", action="store_true",
                    help="임시저장은 하되 업체 방 카톡 알림은 보내지 않는다(첫 가동 확인용)")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        print("partner_blog_daily 자가점검 통과")
        return 0

    style = load_style(args.client)
    fail_name = style["fail_notify_name"]
    # 같은 업체 실행이 겹치면 글이 두 번 올라간다 — 2026-09-15 14:49·14:50 다캠 「무릎…」 2건(두 프로세스가
    # 동시에 돌아 둘 다 「오늘 성공 없음」으로 보고 각자 올렸다). 잠금 파일 하나로 한 번에 하나만 돈다.
    lock = ROOT / "status" / f".{args.client}_blog_daily.lock"
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = datetime.now().timestamp() - lock.stat().st_mtime
        if age < 40 * 60:
            print(f"[INFO] 이미 도는 중({int(age)}초 전 시작) — 건너뜀 · 잠금 {lock.name}")
            return 0
        lock.unlink(missing_ok=True)   # 40분 넘은 잠금은 죽은 프로세스가 남긴 것
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode()); os.close(fd)
    import atexit
    atexit.register(lambda: lock.unlink(missing_ok=True))

    state = load_state(style)
    if _already_ok_today(state):
        log(style, "오늘 이미 임시저장 성공 — 건너뜀")
        return 0
    topic = pick_topic(style, state)
    if topic is None:
        msg = f"{fail_name} 블로그 — topic_bank {len(style['topic_bank'])}개 전부 사용함. 주제 추가 필요."
        log(style, msg)
        notify(msg)
        return 0

    from model_router import run_claude
    prompt = build_prompt(topic, style, state=state)
    # 저장소 밖에서 부른다 — 이 프로젝트의 CLAUDE.md·훅(「[형식 고정] 8요소 표」)이 붙으면
    # 블로그 본문 자리에 업무 보고 표가 나온다(2026-09-11 실측, 4회 연속). 프롬프트로는 못 이긴다.
    llm_body, used_model = run_claude(prompt, label=f"partner-blog-daily-{args.client}",
                                      cwd=tempfile.gettempdir())
    if not llm_body:
        msg = f"{fail_name} 블로그 실패 — 모델 호출 실패(주제: {topic})"
        log(style, msg)
        notify(msg)
        _record_run(style, state, topic, "fail", "모델 호출 실패", 0, None)
        return 1

    body = assemble_body(llm_body, style)
    errs = run_checks(body, style)
    if errs:
        reason = "; ".join(errs)
        fail_path = ROOT / "status" / "drafts" / (f"{fail_name}블로그_불통과_%s.md" % datetime.now().strftime("%Y%m%d_%H%M%S"))
        try:
            fail_path.parent.mkdir(parents=True, exist_ok=True)
            fail_path.write_text("# %s\n\n<!-- 불통과 사유: %s -->\n\n%s" % (topic, reason, body), encoding="utf-8")
        except OSError:
            fail_path = None
        msg = (f"{fail_name} 블로그 실패 — 검사 불통과(%s) 주제: %s" % (reason, topic)
               + (" · 본문 %s" % fail_path.name if fail_path else ""))
        log(style, msg)
        notify(msg)
        _record_run(style, state, topic, "fail", reason, len(body), used_model)
        return 1

    title = topic
    if args.dry_run:
        rc, out = run_upload(title, body, style, mode="dryrun")
        log(style, f"[dry-run] rc={rc}\n{out}")
        print(f"[dry-run] 본문 {len(body)}자 · 검사 통과 · 업로더 dryrun rc={rc}")
        return 0 if rc == 0 else 1

    tenant = style["tenant"]
    rc, out = run_upload(title, body, style, mode="draft")
    relogin_tag: str | None = None
    if rc != 0 and ("로그인이 풀렸다" in out or "로그인된 블로그가 웰페리온" in out):
        relogin_tag = _try_relogin(style, tenant)
        if relogin_tag == "auto-ok":
            rc, out = run_upload(title, body, style, mode="draft")

    if rc == 0:
        msg = f"{fail_name} 블로그 임시저장 성공 — 「{topic}」 {len(body)}자 (모델 {used_model})"
        log(style, msg + "\n" + out)
        notify(msg)
        state.setdefault("used_topics", []).append(topic)
        _record_run(style, state, topic, "ok", "", len(body), used_model, relogin_tag)
        save_state(style, state)
        if args.no_owner_notice:
            log(style, "업체 방 알림 생략(--no-owner-notice)")
        else:
            tell_owner(style, topic)
        return 0

    # 실패 사유는 지어내지 않는다 — 업로더가 찍은 [ERROR] 줄을 그대로 실어 보낸다.
    # 2026-09-10: 「임시저장 큐 누적 여부 확인 필요」라고 미리 적어 두었더니 실제 원인(파트너 계정 자리에
    # 웰페리온 세션이 들어 있던 것)과 다른 곳을 가리켰다.
    err = next((ln.strip() for ln in reversed(out.splitlines()) if "[ERROR]" in ln), "")
    reason = f"업로더 rc={rc}" + (f" · {err[:160]}" if err else "")
    _record_run(style, state, topic, "fail", reason, len(body), used_model, relogin_tag)
    # 연속 회차를 앞에 붙인다 — 2026-09-12~14 사흘 연속 실패가 매일 같은 문구로 나가는 바람에
    # 새 소식인지 어제 것인지 구별되지 않아 아무도 움직이지 않았다.
    연속 = _fail_streak(state)
    if relogin_tag == "auto-fail":
        꼬리 = (f" · 자동 재로그인이 네이버 확인 절차(로봇 확인·기기 인증)에 막혔다"
                f"\nPC 앞에서 ops\\relogin_blog.bat {tenant} 을 눌러 달라")
    elif relogin_tag == "no-secret" and 연속 >= 1:
        꼬리 = (f" · 네이버 재로그인이 필요하다(사람 손)\n👉 재로그인: ops\\relogin_blog.bat {tenant}"
                f"\n★로그인 창에서 「로그인 상태 유지」를 켜야 내일도 돕니다"
                f"\n(서버에 이 계정이 아직 없다 · 플랫폼관리 > 파트너사 > 「계정 넣기」에 {tenant}/naver-blog 을 코드로 넣어 두면 다음부턴 스스로 로그인한다)")
    elif 연속 >= 1:
        # 로그인이 풀리는 진짜 원인은 「로그인 상태 유지」를 안 켜고 로그인한 것이다(2026-09-15 실측 —
        # 세 계정 모두 NID_AUT·NID_SES 가 세션 쿠키였다). 재로그인 안내는 1회 실패부터 낸다.
        꼬리 = (f" · 네이버 재로그인이 필요하다(사람 손)\n👉 재로그인: ops\\relogin_blog.bat {tenant}"
                f"\n★로그인 창에서 「로그인 상태 유지」를 켜야 내일도 돕니다")
    else:
        꼬리 = ""
    msg = f"{fail_name} 블로그 임시저장 실패({연속}회 연속) — 「{topic}」 {reason}{꼬리}"
    log(style, msg + "\n" + out)
    notify(msg)
    save_state(style, state)
    return 1


def _fail_streak(state: dict) -> int:
    """지금까지 몇 번을 내리 실패했나. 기록을 뒤에서부터 센다."""
    n = 0
    for r in reversed(state.get("runs", [])):
        if r.get("result") != "fail":
            break
        n += 1
    return n


def _record_run(style: dict, state: dict, topic: str, result: str, reason: str, chars: int,
                 model: str | None, relogin: str | None = None) -> None:
    rec = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "topic": topic,
        "result": result,
        "reason": reason,
        "chars": chars,
        "model": model,
    }
    if relogin is not None:
        rec["relogin"] = relogin
    state.setdefault("runs", []).append(rec)
    save_state(style, state)


def _self_test() -> None:
    # ── 프롬프트 동일성: 테넌트화 전 build_prompt 가 만들던 고척 프롬프트와 글자 단위로 같아야 한다.
    # philosophy.axes 는 random 이라 axes[0] 으로 고정해서 비교한다.
    jo_style = load_style("jo")
    expected = (ROOT / "scripts" / "testdata" / "gocheok_prompt_expected.txt").read_text(encoding="utf-8")
    fixed_axis = jo_style["philosophy"]["axes"][0]
    fixed_topic = jo_style["topic_bank"][0]
    got = build_prompt(fixed_topic, jo_style, axis=fixed_axis)
    assert got == expected, "고척 프롬프트가 테넌트화 전과 달라졌다"

    for client in sorted(CLIENT_DIRS):
        style = load_style(client)
        fc = style["footer_canon"]
        good_footer_tags = build_footer_and_tags(style)
        filler = ("연습장에서 흔히 보는 장면을 오늘도 하나 떠올려 봅니다. " * 80)
        good = filler + good_footer_tags
        assert len(good) >= style["min_len"], f"[{client}] 자가점검 표본이 최소길이보다 짧음"
        assert run_checks(good, style) == [], (client, run_checks(good, style))

        bad_footer = good.replace(fc["phone"], "010-0000-0000")
        assert any("푸터" in e for e in run_checks(bad_footer, style)), client

        bad_amount = good + " 체험비는 150,000원 입니다."
        assert any("금액" in e for e in run_checks(bad_amount, style)), client

        bad_tag = good.replace(style["required_tag"], "")
        assert any("태그" in e for e in run_checks(bad_tag, style)), client

        # 우리 쪽 낱말 혼입 — client 마다 banned_ours 목록이 다르므로 첫 낱말을 뽑아 일반화한다
        # (jo·dc = 파트너 블로그에 웰페리온을 못 쓰게 · ax = 본명·영업문구·클리셰를 못 쓰게).
        banned_word = style["banned_ours"][0]
        bad_brand = good + f" {banned_word} 이야기입니다."
        assert any(banned_word in e for e in run_checks(bad_brand, style)), client

        # ax 전용: 사례 브랜드(웰페리온 등)가 제목·첫머리엔 안 되고 본문 사례로는 되는지.
        lead_brands = style.get("case_brands_not_in_lead")
        if lead_brands:
            lead_brand = lead_brands[0]
            bad_lead = f"{lead_brand} 이야기로 시작합니다. " + good
            assert any("사례 브랜드" in e for e in run_checks(bad_lead, style)), client
            ok_case = good + f" {lead_brand} 에서 실제로 그렇게 됐습니다."
            assert run_checks(ok_case, style) == [], (client, run_checks(ok_case, style))

        bad_len = "짧은 글"
        assert any("미만" in e for e in run_checks(bad_len, style)), client

    # dc(다이어트캠프): 금액은 허용값이 없으므로 99,000원 하나만 있어도 불통과여야 한다.
    dc_style = load_style("dc")
    dc_good = ("연습장에서 흔히 보는 장면을 오늘도 하나 떠올려 봅니다. " * 80) + build_footer_and_tags(dc_style)
    dc_amount = dc_good + " 체험비는 99,000원 입니다."
    assert any("금액" in e for e in run_checks(dc_amount, dc_style)), "다캠은 어떤 금액도 통과하면 안 된다"
    dc_no_tag = dc_good.replace("#다이어트캠프", "")
    assert any("태그" in e for e in run_checks(dc_no_tag, dc_style))

    f = lambda *rs: _fail_streak({"runs": [{"result": r} for r in rs]})
    assert f() == 0 and f("ok") == 0, "실패가 없는데 연속 실패로 센다"
    assert f("fail", "ok", "fail", "fail") == 2, "중간에 성공한 것을 넘어 센다"
    assert f("fail", "fail", "fail") == 3

    # ── 오늘 이미 성공했으면 건너뛴다 ──
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert _already_ok_today({"runs": [{"date": f"{today} 09:00:00", "result": "ok"}]})
    assert not _already_ok_today({"runs": [{"date": f"{yesterday} 09:00:00", "result": "ok"}]}), "어제 ok 를 오늘로 침"
    assert not _already_ok_today({"runs": [{"date": f"{today} 09:00:00", "result": "fail"}]}), "fail 인데 skip 함"
    assert not _already_ok_today({"runs": []})

    # ── 비밀 파일 파서: 공백·CRLF 허용, 키 없으면 None ──
    assert _secret_from_response(200, {"ok": True, "id": "abc", "pw": "Xample1234!"}) == {"NAVER_ID": "abc", "NAVER_PW": "Xample1234!"}
    assert _secret_from_response(200, {"ok": True, "id": " abc ", "pw": " x "}) == {"NAVER_ID": "abc", "NAVER_PW": "x"}
    assert _secret_from_response(200, {"ok": True, "id": "abc"}) is None, "비밀번호 없는데 통과함"
    assert _secret_from_response(404, {"ok": False}) is None and _secret_from_response(200, None) is None


if __name__ == "__main__":
    sys.exit(main())
