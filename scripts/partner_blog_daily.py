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

흐름: 주제 = 오늘 인스타 런(status/partner_instagram/{client}.json · 06:30 먼저 게시 · 캡션·사진 3장이 씨앗 · GM 2026-09-18)
→ 인스타가 없는 날은 topic_bank(상태 파일로 중복 방지) → run_claude 로 본문(인사~마지막 TIP)만 생성
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


RULES_PATH = ROOT / "ssot" / "blog_exposure_rules.json"
_RULES: dict = {}


def rules() -> dict:
    """공통 노출·가독성 규칙 한 파일(파트너 무관) — blog_style.seo.ref 가 가리킨다. 값을 style 에 베끼지 않는다."""
    if not _RULES:
        _RULES.update(json.loads(RULES_PATH.read_text(encoding="utf-8")))
    return _RULES


def _pick_axis(style: dict, axis: dict | None, state: dict | None) -> dict:
    """axis 는 보통 랜덤(jo·dc). philosophy.cycle=true(ax) 면 발행 회차로 axes 를 순서대로 돈다(GM 09-16 「3축 순환」)."""
    if axis is not None:
        return axis
    axes = style["philosophy"]["axes"]
    if style["philosophy"].get("cycle") and state is not None:
        return axes[len(state.get("runs", [])) % len(axes)]
    return random.choice(axes)


def format_block(style: dict) -> str:
    """① 공통 층 — ssot/blog_exposure_rules.json 을 문장으로 편다(파트너 이름 없음)."""
    r = rules()
    ex, rd, mk = r["exposure"], r["readability"], style["markers"]
    emojis = mk.get("section_emoji") or []
    head = f"「{mk['section_prefix']}」 하나" if mk.get("section_prefix") else "이모지(" + ", ".join(emojis) + ") 하나"
    lines = [
        f"# 형식 — 공통 노출·가독성 규칙(ssot/blog_exposure_rules.json v{r['version'].split()[0]}) · 이것부터 지킨다",
        f"- 흐름 = {' → '.join(rd['flow'])} · 소제목은 {rd['subheads_min']}~{rd['subheads_max']}개, 소제목 줄은 {head} + 제목 낱말 몇 개로만(소제목 줄에 문장을 쓰지 않는다)",
        f"- 한 문단은 {rd['paragraph_max_lines']}줄({rd['paragraph_max_chars']}자) 안 · 문단과 문단 사이에 빈 줄 하나(모바일에서 읽힌다)",
        f"- 목록이 필요하면 「{rd['list_marker']}」 로 시작하는 줄 {rd['list_lines_min']}~{rd['list_lines_max']}개",
        f"- 굵게(**) 는 문단당 1개 이하 · 이모지는 {'소제목 줄에만' if emojis else '쓰지 않는다'}",
        f"- 첫 문단 안에 제목의 핵심 낱말을 자연스럽게 1회 · 같은 낱말을 반복하지 않는다(한 낱말 밀도 {ex['keyword_max_ratio']:.0%} 상한 · 키워드 나열 금지)",
        f"- 직접 경험·구체 장면·순서를 담는다(정보 나열이 아니라 겪은 것처럼) · 제목과 다른 이야기로 새지 않는다",
        f"- 본문 {max(ex['min_len'], style.get('min_len', 0) - 400)}자 이상 · 링크·주소·전화·해시태그·시설 정보·푸터는 쓰지 않는다(코드가 맨 아래 붙인다)",
        f"- 마지막 덩어리 = 「{mk.get('tip_header', '오늘의 TIP')}」 + 오늘 바로 할 수 있는 한 문장",
    ]
    if mk.get("divider"):
        lines.append(f"- 소제목 줄 앞에 구분선 \"{mk['divider']}\" 한 줄")
    return "\n".join(lines)


def voice_block(topic: str, style: dict, axis: dict) -> str:
    """② 파트너 층 — 그 파트너 브랜드가이드(blog_style.voice·philosophy·hard_rules·facility_facts). 빈 값은 「미수령」."""
    v, ph = style.get("voice") or {}, style["philosophy"]
    j = lambda x: json.dumps(x, ensure_ascii=False)  # noqa: E731
    return "\n".join([
        f"# 목소리 — 이 파트너만의 브랜드가이드({v.get('_source') or 'blog_style.json'})",
        f"- 이름: 본문에서는 {' · '.join(style['naming']['in_text'])} 로만 부른다",
        f"- 한 줄: {ph.get('one_line', '미수령')}",
        f"- 어투: {v.get('tone', '미수령')}",
        f"- 누구에게: {v.get('audience', '미수령')}",
        f"- 쓰는 말: {v.get('use_words', '미수령')} · 안 쓰는 말: {v.get('avoid_words', '미수령')} · 금지: {j(ph.get('forbidden', []))}",
        f"- 오늘 철학 축(본론 한 덩어리에 자연스럽게 · 설교 금지): {axis['name']} — {axis['body']} · 쓰는 법: {j(ph.get('how_to_write', ''))}",
        f"- 절대 규칙: {j(style['hard_rules'])}",
        f"- 참고 사실(이 값만 쓴다): {j(style['facility_facts'])}",
        f"- 마무리 행동 하나(재촉 없이): {v.get('cta', '미수령')}",
    ])


def build_prompt(topic: str, style: dict, axis: dict | None = None, state: dict | None = None) -> str:
    """프롬프트 = 출력 형태 경고 + ①형식(공통 규칙) + ②목소리(파트너) + 오늘 주제(GM 2026-09-18 두 층 구조).
    옛 prompt_template(2026-09-10~17 · blog_style.json)은 안 쓴다 — 자가점검이 testdata/gocheok_prompt_expected.txt 와 대조한다."""
    axis = _pick_axis(style, axis, state)
    return "\n\n".join([
        "손님이 읽는 네이버 블로그 글 본문만 쓴다. 업무 보고가 아니다 — 표(|---|)·체크리스트 보고·작업 요약·「위 본문 그대로 쓰시면 됩니다」 같은 말을 쓰지 마라. "
        "다른 말 없이 본문만 출력해라(설명·머리말·제목 줄 금지).",
        format_block(style),
        voice_block(topic, style, axis),
        f"# 오늘 주제\n{topic}",
    ])


def make_title(topic: str, tmax: int) -> str:
    """제목은 주제 그대로, {tmax}자를 넘으면 「 — 」 앞 토막(8자 이상)으로, 그것도 안 되면 마지막 띄어쓰기에서 자른다."""
    if len(topic) <= tmax:
        return topic
    head = re.split(r"\s+[—–-]\s+|:\s+", topic, maxsplit=1)[0].strip()
    if 8 <= len(head) <= tmax:
        return head
    cut = topic[:tmax]
    return (cut[: cut.rfind(" ")] if " " in cut[8:] else cut).strip()


def default_tags(style: dict) -> list[str]:
    """모델이 못 고른 날의 태그 — 필수 1 + 창고 앞에서 tags_max-1 개."""
    seo, t = rules()["exposure"], style["tags"]
    pool = [x for x in (t.get("pool") or t.get("core_25") or []) if x != style["required_tag"]]   # ax 는 아직 core_25
    return [style["required_tag"]] + pool[: seo["tags_max"] - 1]


def check_tags(tags: list[str], style: dict) -> list[str]:
    """태그 5~8 · 필수 태그 포함 · 창고(tags.pool) 밖 금지(GM 2026-09-18 · 규칙 파일 sources 태그 줄)."""
    seo = rules()["exposure"]
    errs = []
    if not (seo["tags_min"] <= len(tags) <= seo["tags_max"]):
        errs.append(f"태그 {len(tags)}개 — {seo['tags_min']}~{seo['tags_max']}개여야 한다")
    if style["required_tag"] not in tags:
        errs.append(f"필수 태그 {style['required_tag']} 없음")
    out = [x for x in tags if x not in set(style["tags"]["pool"]) | {style["required_tag"]}]
    if out:
        errs.append("창고 밖 태그: " + ", ".join(out))
    if len(set(tags)) != len(tags):
        errs.append("태그 중복")
    return errs


def pick_tags(topic: str, llm_body: str, style: dict) -> list[str]:
    """글마다 창고(tags.pool)에서 주제에 맞는 태그를 모델이 고른다 — 검사 통과 못 하면 default_tags."""
    from model_router import run_claude  # noqa: PLC0415
    seo, pool, must = rules()["exposure"], style["tags"]["pool"], style["required_tag"]
    prompt = (f"아래 네이버 블로그 글에 붙일 태그를 창고에서만 골라라. 필수 태그 {must} 를 맨 앞에 두고, 글 내용과 직접 맞는 것만 "
              f"총 {seo['tags_min']}~{seo['tags_max']}개. 결과는 태그를 공백으로 이은 한 줄만(설명 없이).\n\n"
              f"창고: {' '.join(pool)}\n\n제목: {topic}\n\n본문:\n{llm_body[:1500]}")
    out, _ = run_claude(prompt, label=f"partner-blog-tags-{style['tenant']}", cwd=tempfile.gettempdir())
    tags = [x for x in re.findall(r"#[^\s#]+", out or "")]
    tags = list(dict.fromkeys([must] + [x for x in tags if x != must]))[: seo["tags_max"]]
    if check_tags(tags, style):
        print(f"[tags] 모델 선택 불통과({check_tags(tags, style)}) → 기본 태그")
        return default_tags(style)
    return tags


def build_footer_and_tags(style: dict, tags: list[str] | None = None) -> str:
    fc = style["footer_canon"]
    divider = style["markers"]["divider"]
    lines = [fc["name"], fc["address"], fc["parking"], fc["hours"], fc["phone"], fc["closing"]]
    if fc.get("counsel"):   # 상담 페이지 한 줄(GM 2026-09-17 「상담봇 활성화」) — 값이 있는 파트너만
        lines.append(fc["counsel"])
    footer = "\n".join(lines)
    return f"\n\n{divider}\n\n{footer}\n\n{' '.join(tags or default_tags(style))}\n"


def assemble_body(llm_body: str, style: dict, tags: list[str] | None = None) -> str:
    return llm_body.strip() + build_footer_and_tags(style, tags)


def fix_prompt(errs: list[str], llm_body: str, style: dict) -> str:
    """검사에 걸린 본문을 한 번 고쳐 쓰게 하는 프롬프트 — 형식 규칙을 같이 줘야 고치면서 다른 규칙을 깨지 않는다.
    「미만」(짧음) 지적이면 문단을 더해 늘리고, 그 밖엔 길이를 지킨다."""
    length = "지적된 길이만큼 문단을 더해 늘려라(각 문단은 형식 규칙 안에서)" if any("미만" in e for e in errs) else "길이는 그대로"
    return ("아래 네이버 블로그 본문을 지적 사항만 고쳐 다시 써라. 다른 문장·구성은 그대로 · " + length + " · 본문만 출력.\n\n"
            "지적: " + " · ".join(errs) + "\n\n" + format_block(style) + "\n\n" + llm_body)


def seo_checks(body: str, style: dict, title: str = "", images: int | None = None) -> list[str]:
    """네이버 노출 + 가독성 규칙(ssot/blog_exposure_rules.json · style.seo.ref) — 본문(푸터·태그 줄 뺀 것)에 건다."""
    if not style.get("seo"):
        return []
    r = rules()
    seo, rd, fc, mk = r["exposure"], r["readability"], style["footer_canon"], style["markers"]
    errs = []
    core = body
    for v in list(fc.values()) + [" ".join(style["tags"].get("pool") or [])]:
        if isinstance(v, str) and v:
            core = core.replace(v, " ")
    core = re.sub(r"#[^\s#]+", " ", core)
    if title:
        if len(title) > seo["title_max"]:
            errs.append(f"제목 {len(title)}자 — {seo['title_max']}자 안")
        words = [w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", title) if w not in ("하는", "하지", "해야", "것과", "가장", "먼저")]
        if words and not any(w in core[: seo["lead_chars"]] for w in words):
            errs.append(f"제목 핵심 낱말이 첫 {seo['lead_chars']}자에 없음(제목≠내용)")
    # 소제목 = 줄 머리가 section_prefix 또는 section_emoji 인 줄(TIP 머리는 빼고 센다 · 본문 안 이모지는 안 센다)
    tip = mk.get("tip_header") or "\x00"
    lines = [ln.strip() for ln in core.splitlines()]
    is_head = lambda ln: bool(ln) and tip not in ln and (  # noqa: E731
        ln.startswith(mk["section_prefix"]) if mk.get("section_prefix") else any(ln.startswith(e) for e in mk.get("section_emoji", [])))
    heads = sum(1 for ln in lines if is_head(ln))
    if not (rd["subheads_min"] <= heads <= rd["subheads_max"]):
        errs.append(f"소제목 {heads}개 — {rd['subheads_min']}~{rd['subheads_max']}개")
    # 가독성 — 문단 = 빈 줄로 나뉜 덩어리 · 소제목·목록·구분선 줄은 문단 길이에서 뺀다
    paras = [p for p in re.split(r"\n\s*\n", core.strip()) if p.strip()]
    if len(paras) < rd["subheads_min"] + 2:
        errs.append(f"문단 사이 빈 줄 없음(덩어리 {len(paras)}개)")
    long_paras = 0
    for p in paras:
        body_lines = [ln for ln in p.splitlines() if ln.strip() and not is_head(ln.strip())
                      and not ln.strip().startswith(rd["list_marker"]) and ln.strip() != (mk.get("divider") or "\x00")]
        text = "".join(body_lines)
        if len(text) > rd["paragraph_max_chars"] or len(body_lines) > rd["paragraph_max_lines"]:
            long_paras += 1
        if p.count("**") // 2 > rd["bold_per_paragraph_max"]:
            errs.append("굵게 강조가 한 문단에 2개 이상")
    if long_paras:
        errs.append(f"긴 문단 {long_paras}개 — 한 문단 {rd['paragraph_max_lines']}줄({rd['paragraph_max_chars']}자) 안")
    run = 0
    for ln in lines + [""]:
        if ln.startswith(rd["list_marker"]):
            run += 1
        elif run:
            if not (rd["list_lines_min"] <= run <= rd["list_lines_max"]):
                errs.append(f"목록 {run}줄 — 「{rd['list_marker']}」 {rd['list_lines_min']}~{rd['list_lines_max']}줄")
            run = 0
    toks = re.findall(r"[가-힣]{2,}", core)
    if len(toks) >= 100:
        top = max(set(toks), key=toks.count)
        ratio = toks.count(top) / len(toks)
        if ratio > seo["keyword_max_ratio"]:
            errs.append(f"낱말 「{top}」 밀도 {ratio:.1%} — {seo['keyword_max_ratio']:.0%} 상한(키워드 반복)")
    links = len(re.findall(r"https?://", core))
    if links > seo["links_max"]:
        errs.append(f"본문 링크 {links}개 — 상담 페이지 외 링크 금지({seo['links_max']}개)")
    if images is not None and images < seo["images_min"]:
        errs.append(f"사진 {images}장 — {seo['images_min']}장 이상")
    return errs


# ── 검사 (보내기 전 코드로 막는다) ──────────────────────────────────
def run_checks(body: str, style: dict, title: str = "", images: int | None = None) -> list[str]:
    errs: list[str] = seo_checks(body, style, title, images)
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


def run_upload(title: str, body: str, style: dict, mode: str,
               images: tuple[Path, str] | None = None, tags: list[str] | None = None) -> tuple[int, str]:
    """images = (폴더, 글롭) 를 주면 그 사진(오늘 인스타 3장)을, 없으면 style.photo_dir 를 붙인다. tags 는 발행 패널 태그(5~8)."""
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
        if mode == "publish":
            argv.append("--i-am-sure")                 # 업로더의 실발행 가드 — 이 스크립트가 곧 GM go(2026-09-18 지시)
            env["TELEGRAM_BOT_TOKEN"] = ""             # 업로더 자체 텔레그램 보고는 끈다(알림은 이 스크립트 notify 한 곳)
        photo_dir = style.get("photo_dir")
        if images:
            argv += ["--image-dir", str(images[0]), "--image-glob", images[1]]
        elif photo_dir:
            # --blog-id 는 넘기지 않는다 — 업로더가 로그인 세션(WP_TENANT)에서
            # 실제 블로그 아이디를 자동 확인한다(_resolve_blog_id). 화면 프로필 표시명은
            # 실제 blogId 슬러그가 아니어서 고정 지정하면 "유효하지 않은 요청" 에러로
            # draft가 막힌다(2026-09-10 실측, 고척골프).
            argv += ["--image-dir", str(ROOT / photo_dir), "--image-glob", "*.jpg"]
        argv += ["--tags", *(tags or default_tags(style))]
        ret = subprocess.run(argv, cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (ret.stdout or "") + (ret.stderr or "")
        return ret.returncode, out[-4000:]
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def ig_seed(client: str, path: Path | None = None) -> dict | None:
    """오늘 인스타 런(status/partner_instagram/{client}.json · 06:30 partner_instagram_daily) — 주제·캡션·사진 3장.

    GM 2026-09-18: 인스타를 먼저 올리고 그 내용으로 블로그를 만든다(주제 원천 = 인스타). 인스타가 안 나온 날은
    None → 종전대로 블로그 자체 주제(topic_bank). 게시 여부는 보지 않는다 — 임시안만 있어도 같은 주제로 간다(다캠 세션 없는 날).
    """
    p = path or (ROOT / "status" / "partner_instagram" / f"{client}.json")
    try:
        runs = json.loads(p.read_text(encoding="utf-8")).get("runs", [])
    except Exception:                            # noqa: BLE001
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    r = next((r for r in reversed(runs)
              if str(r.get("at", "")).startswith(today) and r.get("topic") and r.get("caption") and r.get("folder")), None)
    return r if r and (Path(r["folder"]) / "output").exists() else None


def seed_block(seed: dict) -> str:
    """프롬프트 정본(prompt_template)은 그대로 두고 뒤에 씨앗 한 절만 붙인다 — 구조를 재조립하지 않는다.
    캡션 끝의 상담 주소 줄은 씨앗에서 뺀다 — 2026-09-18 실측: 「옮기지 말라」고 써도 모델이 본문에 베껴 넣어
    banned_ours(wellperion) 검사에 걸렸다. 푸터 정본 줄은 코드가 따로 붙인다."""
    body = "\n".join(ln for ln in seed["caption"].splitlines() if "erp.wellperion.com" not in ln).strip()
    return ("\n\n★오늘 인스타그램에 먼저 올린 같은 주제의 캡션(이 글의 씨앗 — 흐름과 핵심 문장은 이어받되 "
            "문장을 그대로 복사하지 않고 블로그 길이로 풀어 쓴다 · 주소·링크는 쓰지 않는다):\n" + body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, choices=sorted(CLIENT_DIRS),
                     help="jo=고척골프 조재오 지점장님 · dc=다이어트캠프 이승기대표님 · ax=AX 랩스 「피트니스 AX」")
    ap.add_argument("--dry-run", action="store_true", help="본문만 만들고 브라우저를 열지 않는다")
    ap.add_argument("--self-test", action="store_true", help="검사 함수 자가점검")
    ap.add_argument("--force", action="store_true", help="오늘 성공 기록이 있어도 한 번 더(사람이 실측할 때만)")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        print("partner_blog_daily 자가점검 통과")
        return 0

    style = load_style(args.client)
    fail_name = style["fail_notify_name"]
    # 시험 실행(--dry-run)이 GM 방에 실패 알림을 보내고 상태 파일에 fail 을 남기면 안 된다(2026-09-18 실측 — 시험 한 번에 GM DM 1통).
    # 함수 안에서 이름을 덮으므로 main 의 모든 호출이 이 판을 쓴다 — 첫 사용보다 앞에 둔다.
    notify = globals()["notify"] if not args.dry_run else (lambda m: print(f"[dry-run] 알림 생략: {m[:80]}"))  # noqa: E731
    _record_run = globals()["_record_run"] if not args.dry_run else (lambda *a, **k: None)                    # noqa: E731
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

    if datetime.now().weekday() >= 5:
        log(style, "주말 정지(토·일 · GM 2026-09-18 평일만 발행) — 생성·발행 없음")
        return 0
    state = load_state(style)
    if _already_ok_today(state) and not args.dry_run and not args.force:   # dry-run 은 생성·검사만 시험하는 길이라 당일 성공 여부와 무관(2026-09-17 감사)
        log(style, "오늘 이미 임시저장 성공 — 건너뜀")
        return 0
    seed = ig_seed(args.client)
    topic = seed["topic"] if seed else pick_topic(style, state)
    if topic is None:
        msg = f"{fail_name} 블로그 — topic_bank {len(style['topic_bank'])}개 전부 사용함. 주제 추가 필요."
        log(style, msg)
        notify(msg)
        return 0
    log(style, f"주제 원천 = {'오늘 인스타 ' + Path(seed['folder']).name if seed else '블로그 자체(topic_bank)'} · 「{topic}」")

    from model_router import run_claude
    prompt = build_prompt(topic, style, state=state) + (seed_block(seed) if seed else "")
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

    images = (Path(seed["folder"]) / "output", "ig_*.jpg") if seed else None   # 인스타에 올린 사진 3장 그대로
    n_images = len(list(images[0].glob(images[1]))) if images else None
    tags = pick_tags(topic, llm_body, style)
    body = assemble_body(llm_body, style, tags)
    title = make_title(topic, rules()["exposure"]["title_max"]) if style.get("seo") else topic
    errs = run_checks(body, style, title=title, images=n_images)
    if errs and not any("금액" in e or "혼입" in e for e in errs):
        # 노출 규칙만 걸린 것은 한 번 고쳐 쓴다(seo._doc) — 금액·낱말 혼입은 규칙 위반이라 고쳐 쓰지 않는다
        fixed, _ = run_claude(fix_prompt(errs, llm_body, style), label=f"partner-blog-daily-{args.client}-fix", cwd=tempfile.gettempdir())
        if fixed and len(fixed.strip()) > len(llm_body) * 0.7:
            body2 = assemble_body(fixed, style, tags)
            errs2 = run_checks(body2, style, title=title, images=n_images)
            log(style, f"노출 규칙 고쳐 쓰기 1회 — 전 {len(errs)}건 → 후 {len(errs2)}건")
            if not errs2:
                llm_body, body, errs = fixed, body2, errs2
    if errs:
        reason = "; ".join(errs)
        fail_path = ROOT / "status" / "drafts" / (f"{fail_name}블로그_불통과_%s.md" % datetime.now().strftime("%Y%m%d_%H%M%S"))
        try:
            if args.dry_run:
                raise OSError("dry-run 은 파일을 남기지 않는다")
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

    if args.dry_run:
        print(f"[dry-run] 제목 「{title}」 · 태그 {tags}")
        rc, out = run_upload(title, body, style, mode="dryrun", images=images, tags=tags)
        log(style, f"[dry-run] rc={rc}\n{out}")
        print(f"[dry-run] 본문 {len(body)}자 · 검사 통과 · 업로더 dryrun rc={rc}")
        return 0 if rc == 0 else 1

    tenant = style["tenant"]
    # 직접 발행(GM 2026-09-18 「파트너가 누르지 않는다」) — 발행이 안 되면 임시저장으로 남기고 로그(글은 버리지 않는다)
    rc, out = run_upload(title, body, style, mode="publish", images=images, tags=tags)
    relogin_tag: str | None = None
    if rc != 0 and ("로그인이 풀렸다" in out or "로그인된 블로그가 웰페리온" in out):
        relogin_tag = _try_relogin(style, tenant)
        if relogin_tag == "auto-ok":
            rc, out = run_upload(title, body, style, mode="publish", images=images, tags=tags)
    url = _post_url(out) if rc == 0 else ""
    kind = "발행"
    if rc != 0 or not url:
        log(style, f"발행 실패(rc={rc} · url={'있음' if url else '없음'}) → 임시저장으로 남긴다")
        rc, out = run_upload(title, body, style, mode="draft", images=images, tags=tags)
        kind, url = "임시저장(발행 실패)", ""

    if rc == 0:
        msg = f"{fail_name} 블로그 {kind} 성공 — 「{topic}」 {len(body)}자 (모델 {used_model}){' ' + url if url else ''}"
        log(style, msg + "\n" + out)
        notify(msg)
        state.setdefault("used_topics", []).append(topic)
        _record_run(style, state, topic, "ok", "" if url else "발행 실패 → 임시저장", len(body), used_model, relogin_tag,
                    seed=bool(seed), url=url)
        save_state(style, state)
        archive_body(args.client, title, body, tags, url, kind)
        # 파트너 방 아침 안내는 안 보낸다 — 그 시각에 대신 나가는 것은 없다(GM 2026-09-18 「오전 통은 다 삭제」 · 저녁 통이 한 번에 정리)
        log(style, "아침 안내 skip(GM 2026-09-18)")
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


def archive_body(client: str, title: str, body: str, tags: list[str], url: str, kind: str) -> Path | None:
    """발행·임시저장한 본문을 파트너 폴더에 남긴다 — 05_콘텐츠_초안/blog/YYMMDD_<제목>.md(주말 평가·GM 열람용 · 종전엔 temp 로 사라졌다)."""
    safe = re.sub(r"[\\/:*?\"<>|\s]+", "_", title)[:40]
    p = CLIENT_DIRS[client] / "05_콘텐츠_초안" / "blog" / f"{datetime.now().strftime('%y%m%d')}_{safe}.md"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {title}\n\n- {kind} · {datetime.now().strftime('%Y-%m-%d %H:%M')}\n- url: {url or '(임시저장)'}\n- tags: {' '.join(tags)}\n\n---\n\n{body}\n",
                     encoding="utf-8")
        return p
    except OSError as exc:
        print(f"[WARN] 본문 보관 실패(무시): {exc}")
        return None


def _post_url(out: str) -> str:
    """업로더가 찍는 「post_url: https://blog.naver.com/…」 한 줄 — 회수불가면 빈 값.
    발행 직후 주소(PostView.naver?blogId=…&logNo=…&isAfterWrite=…)는 짧은 정식 주소 blog.naver.com/{blogId}/{logNo} 로 바꾼다."""
    m = re.search(r"^post_url:\s*(https?://\S+)", out, re.M)
    if not m:
        return ""
    url = m.group(1)
    b, n = re.search(r"[?&]blogId=([A-Za-z0-9_-]+)", url), re.search(r"[?&]logNo=(\d+)", url)
    return f"https://blog.naver.com/{b.group(1)}/{n.group(1)}" if b and n else url


def _fail_streak(state: dict) -> int:
    """지금까지 몇 번을 내리 실패했나. 기록을 뒤에서부터 센다."""
    n = 0
    for r in reversed(state.get("runs", [])):
        if r.get("result") != "fail":
            break
        n += 1
    return n


def _record_run(style: dict, state: dict, topic: str, result: str, reason: str, chars: int,
                 model: str | None, relogin: str | None = None, seed: bool = False, url: str = "") -> None:
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
    if seed:
        rec["seed"] = "instagram"           # 인스타 → 블로그 순서가 실제로 돌았다는 표식
    if url:
        rec["url"] = url                    # 발행 글 주소(저녁 통·주말 되짚기가 읽는다)
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
        # 표본 본문 = 같은 낱말이 없는 글(밀도 검사) + 소제목 2개 + 문단 사이 빈 줄 + ▪ 목록 3줄 + 굵게 1개 + TIP 머리 — 옛 검사·공통 노출·가독성 검사를 한 벌로 통과해야 한다
        mk = style["markers"]
        head = (mk.get("section_prefix") or (mk.get("section_emoji") or ["■"])[0]) + " 소제목"
        uniq = [chr(0xAC00 + i * 7) + chr(0xAC00 + i * 11 + 3) + "다" for i in range(900)]        # 같은 낱말이 없는 본문(밀도 검사용)
        para = lambda k: " ".join(uniq[k * 30:(k + 1) * 30])                                     # noqa: E731 — 한 문단 ≈ 120자
        good_seo = "\n\n".join(["연습장 장면 하나를 떠올립니다. " + para(0), para(1), head, para(2), para(3),
                                "▪ " + uniq[200] + "\n▪ " + uniq[201] + "\n▪ " + uniq[202], head, para(4), "**" + uniq[300] + "** " + para(5),
                                para(6), para(7), para(8), para(9), para(10), para(11), para(12), para(13), para(15), para(16), para(17),
                                (mk.get("tip_header") or "오늘의 TIP") + " " + para(14)])
        good = good_seo + good_footer_tags
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

        # ── 공통 노출·가독성 규칙(ssot/blog_exposure_rules.json) — 통과 본문 1개 → 통과 · 위반 본문 → 항목별 불통과 ──
        if style.get("seo"):
            dt = default_tags(style)
            assert check_tags(dt, style) == [] and style["required_tag"] == dt[0] and 5 <= len(dt) <= 8, (client, dt)
            assert any("개여야" in e for e in check_tags(dt[:3], style)), client
            assert any("창고 밖" in e for e in check_tags(dt[:-1] + ["#없는태그"], style)), client
            assert any("필수 태그" in e for e in check_tags(dt[1:] + ["#골프"], style)), client
            good_seo = good_seo + build_footer_and_tags(style, dt)
            ok_errs = seo_checks(good_seo, style, title="연습장 장면 하나", images=3)
            assert ok_errs == [], (client, ok_errs)
            assert any("제목" in e and "자 안" in e for e in seo_checks(good_seo, style, title="가" * 31)), client
            assert any("제목≠내용" in e for e in seo_checks(good_seo, style, title="전혀다른낱말")), client
            assert any("소제목" in e for e in seo_checks(good_seo.replace(head, "소제목아님", 1), style)), client + " 소제목 1개"
            assert any("소제목" in e for e in seo_checks(good_seo.replace(para(6), head + "\n\n" + head + "\n\n" + head), style)), client + " 소제목 5개"
            assert any("긴 문단" in e for e in seo_checks(good_seo.replace(para(7), " ".join(uniq[400:480])), style)), client
            assert any("빈 줄" in e for e in seo_checks(good_seo.replace("\n\n", "\n"), style)), client
            assert any("목록" in e for e in seo_checks(good_seo.replace("▪ " + uniq[202], ""), style)), client + " 목록 2줄"
            assert any("굵게" in e for e in seo_checks(good_seo.replace("**" + uniq[300] + "**", "**a** **b**"), style)), client
            assert any("밀도" in e for e in seo_checks(good_seo + "\n\n" + " 반복낱말" * 60, style)), client
            assert any("링크" in e for e in seo_checks(good_seo + "\n\nhttps://a.b/ https://c.d/", style)), client
            assert any("사진" in e for e in seo_checks(good_seo, style, images=1)) and seo_checks(good_seo, style, images=None) == [], client
            assert make_title("GDR 숫자 읽는 법 — 볼 스피드와 발사각이 말해 주는 것", 30) == "GDR 숫자 읽는 법"
            assert len(make_title("가" * 20 + " " + "나" * 20, 30)) <= 30 and make_title("짧은 제목", 30) == "짧은 제목"
            assert "# 형식" in build_prompt("주제", style, axis=style["philosophy"]["axes"][0]) and "# 목소리" in build_prompt("주제", style, axis=style["philosophy"]["axes"][0])
            assert "늘려라" in fix_prompt(["본문 900자 — 2000자 미만"], "x", style) and "# 형식" in fix_prompt(["긴 문단 1개"], "x", style) and "그대로" in fix_prompt(["긴 문단 1개"], "x", style)

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

    # ── 인스타 씨앗: 오늘 런(주제·캡션·폴더 output/)만 · 어제 것·캡션 없는 것은 None ──
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        (Path(td) / "output").mkdir()
        p = Path(td) / "ig.json"
        now = datetime.now().strftime("%Y-%m-%dT06:30:00")
        p.write_text(json.dumps({"runs": [{"at": now, "topic": "주제A", "caption": "첫 문장.\n\nerp.wellperion.com/x/counsel/ 에서 24시간 상담", "folder": td}]}), encoding="utf-8")
        s = ig_seed("jo", p)
        assert s and s["topic"] == "주제A" and "첫 문장." in seed_block(s), s
        assert "24시간 상담" not in seed_block(s) and "wellperion" not in seed_block(s), "상담 주소 줄이 씨앗에 남음"
        p.write_text(json.dumps({"runs": [{"at": now.replace("2026", "2025"), "topic": "주제A", "caption": "x", "folder": td}]}), encoding="utf-8")
        assert ig_seed("jo", p) is None, "어제 인스타를 오늘 씨앗으로 삼음"
        p.write_text(json.dumps({"runs": [{"at": now, "topic": "주제A", "folder": td}]}), encoding="utf-8")
        assert ig_seed("jo", p) is None, "캡션 없는 런을 씨앗으로 삼음"
    assert ig_seed("jo", Path("없는/파일.json")) is None
    assert _post_url("[INFO] 발행 완료\npost_url: https://blog.naver.com/abc/223\n") == "https://blog.naver.com/abc/223"
    assert _post_url("post_url: https://blog.naver.com/PostView.naver?blogId=spogym21qa&Redirect=View&logNo=224415780789&isAfterWrite=true") \
        == "https://blog.naver.com/spogym21qa/224415780789"
    assert _post_url("post_url: (회수불가)") == ""

    # ── 비밀 파일 파서: 공백·CRLF 허용, 키 없으면 None ──
    assert _secret_from_response(200, {"ok": True, "id": "abc", "pw": "Xample1234!"}) == {"NAVER_ID": "abc", "NAVER_PW": "Xample1234!"}
    assert _secret_from_response(200, {"ok": True, "id": " abc ", "pw": " x "}) == {"NAVER_ID": "abc", "NAVER_PW": "x"}
    assert _secret_from_response(200, {"ok": True, "id": "abc"}) is None, "비밀번호 없는데 통과함"
    assert _secret_from_response(404, {"ok": False}) is None and _secret_from_response(200, None) is None


if __name__ == "__main__":
    sys.exit(main())
