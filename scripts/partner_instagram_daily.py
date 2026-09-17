#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""partner_instagram_daily.py — 파트너 인스타 임시안 하루 한 장 (시보 · 배 12718 · GM 지시 2026-09-17 「마케팅 자동화 활성화」).

무엇을 하나(1단계 = 임시안 · 2단계 = 게시):
  ① 오늘 블로그 임시저장 글의 주제(status/{client}_blog_daily.json 마지막 ok 런)를 받아
  ② 캡션 300자 안(담담 · 금액 0 · 금지어 0) + 인스타 해시태그 15개를 만들고
  ③ 파트너 화면 사진(erp/admin/{tenant}/img · 로고 제외)에서 3장을 돌려 뽑아 1080×1080 으로 잘라
  ④ instagram_upload_playwright.py 가 읽는 폴더 규격(output/ig_NN.jpg + 큐레이션_추천.md)으로 저장하고
  ⑤ 파트너 카톡 방에 사진 1장 + 캡션을 보내 「올려요」 한 마디를 받는다(게시는 그 뒤 --publish · 계정 세션은 profiles/instagram/{account}).

정본 = 파트너 blog_style.json(말투·금지어·태그) · client.json(사실). 계정 값은 어디에도 두지 않는다(서버 1531 규칙 · 세션 프로필만).
상태 = status/partner_instagram/{client}.json (마지막 날짜 · 폴더 · 사진 회전 index · 확인 대기).

  C:/Python314/python.exe scripts/partner_instagram_daily.py jo            # 임시안 만들고 카톡으로 보냄
  C:/Python314/python.exe scripts/partner_instagram_daily.py jo --no-send  # 폴더만 만든다
  C:/Python314/python.exe scripts/partner_instagram_daily.py jo --publish  # 파트너 「올려요」 뒤 — 오늘 폴더를 그 계정으로 게시
  C:/Python314/python.exe scripts/partner_instagram_daily.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
PY = sys.executable

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


def room_name(c: dict) -> str:
    names: list[str] = []

    def walk(x):  # 파일 모양(중첩 dict·list)에 기대지 않고 name 값만 모은다
        if isinstance(x, dict):
            if isinstance(x.get("name"), str):
                names.append(x["name"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(json.loads((ROOT / "scripts" / "kakao_rooms.json").read_text(encoding="utf-8")))
    for n in names:
        if c["room_key"] in n:
            return n
    raise SystemExit(f"카톡 방 이름을 못 찾음 — kakao_rooms.json 에 「{c['room_key']}」 없음")


def today_topic(style: dict) -> str | None:
    """오늘(또는 마지막) 블로그 임시저장 성공 런의 주제 — 글과 같은 주제로 인스타를 만든다."""
    p = ROOT / style["state_file"]
    if not p.exists():
        return None
    runs = [r for r in json.loads(p.read_text(encoding="utf-8")).get("runs", []) if r.get("result") == "ok"]
    return runs[-1].get("topic") if runs else None


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
        f"길이 {CAPTION_MAX}자 안 · 첫 줄은 손님 마음에 걸리는 한 문장 · 마지막 줄은 「프로필 링크에서 24시간 상담」 한 줄 · 차분히 설명하는 말투 · 존댓말\n"
    )


def fallback_caption(topic: str, c: dict) -> str:
    return f"{topic}\n\n오늘 블로그에 정리해 두었습니다. {c['name']}에서 편하게 물어보셔도 됩니다.\n프로필 링크에서 24시간 상담"


def run_checks(caption: str, style: dict) -> list[str]:
    errs = []
    for w in forbidden_words(style):
        if w and w.lower() in caption.lower():
            errs.append(f"금지어 「{w}」")
    if re.search(r"[0-9][0-9,]*\s*원", caption):
        errs.append("금액 숫자")
    if len(caption) > CAPTION_MAX:
        errs.append(f"캡션 {len(caption)}자 — {CAPTION_MAX}자 초과")
    if "|---|" in caption or "GM요청" in caption:
        errs.append("보고 표 혼입")
    return errs


TAIL = "프로필 링크에서 24시간 상담"


def trim_to_sentence(caption: str, limit: int) -> str:
    """문장 경계에서 잘라 limit 안으로 — 마지막 줄(상담 안내)은 남긴다."""
    body = caption.replace(TAIL, "").strip()
    out = ""
    for sent in re.split(r"(?<=[.!?다요])\s+", body):
        if len(out) + len(sent) + len(TAIL) + 2 > limit:
            break
        out = (out + " " + sent).strip()
    return (out or body[: limit - len(TAIL) - 2]).strip() + "\n\n" + TAIL


def pick_photos(c: dict, st: dict, n: int = 3) -> list[Path]:
    imgs = sorted(p for p in (ADMIN / c["tenant"] / "img").glob("*.jpg") if not SKIP_IMG.search(p.name))
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


def send_kakao(c: dict, folder: Path, caption: str, tags: list[str]) -> int:
    body = (f"{c['owner']}, 웰페리온 AI입니다.\n"
            f"오늘 블로그 글로 인스타그램 게시물 초안을 만들었습니다(사진 3장 중 1장 첨부).\n"
            f"▪ 캡션\n{caption.strip()}\n"
            f"▪ 해시태그 {len(tags)}개는 캡션 아래에 붙습니다\n"
            f"👉 「올려요」 한 마디면 그 계정으로 올리고, 고칠 문장은 그 줄만 주시면 바꾸겠습니다.")
    p = subprocess.run([PY, str(ROOT / "scripts" / "kakao_report_sender.py"), "--image", str(folder / "output" / "ig_01.jpg"),
                        "--caption", body, "--only-room", room_name(c), "--sender", "웰리"],
                       cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (p.stdout or "").strip().splitlines()[-1:] or [""]
    print("[kakao]", p.returncode, tail[0][:120])
    return p.returncode


def publish(c: dict, folder: Path) -> int:
    cmd = [PY, str(ROOT / "scripts" / "instagram_upload_playwright.py"), "--mode", "publish",
           "--account", c["account"], "--content-folder", str(folder), "--tenant", "wellperion"]
    print("[publish]", " ".join(cmd[2:]))
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("client", nargs="?", choices=sorted(CLIENTS))
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--publish", action="store_true", help="파트너 「올려요」 뒤 — 오늘 폴더를 게시")
    ap.add_argument("--topic", default="", help="주제를 직접 줄 때(기본 = 오늘 블로그 주제)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.client:
        ap.error("client")
    c = CLIENTS[a.client]
    style, cj, st = style_of(c), client_json(c), load_state(a.client)
    day = datetime.now().strftime("%y%m%d")
    folder = c["dir"] / "05_콘텐츠_초안" / "instagram" / day
    if a.publish:
        if not (folder / "큐레이션_추천.md").exists():
            raise SystemExit(f"오늘 임시안 폴더 없음 — {folder}")
        rc = publish(c, folder)
        st["runs"].append({"at": datetime.now().isoformat(timespec="seconds"), "folder": str(folder), "publish_rc": rc})
        save_state(a.client, st)
        return rc
    topic = a.topic or today_topic(style)
    if not topic:
        raise SystemExit("오늘 블로그 주제가 없다 — partner_blog_daily 가 먼저 돌아야 한다(--topic 으로 직접 줄 수 있음)")
    from model_router import run_claude  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    caption, used = run_claude(build_prompt(topic, style, cj, c), label=f"partner-ig-{a.client}", cwd=tempfile.gettempdir())
    caption = (caption or "").strip() or fallback_caption(topic, c)
    errs = run_checks(caption, style)
    if errs and all(e.startswith("캡션 ") for e in errs):   # 길이만 넘친 것은 한 번 줄여 본다(규칙 캡션은 마지막 수단)
        shorter, _ = run_claude(f"아래 인스타 캡션을 {CAPTION_MAX - 20}자 안으로 줄여라. 말투·문장 순서·마지막 줄은 그대로, 결과는 캡션만.\n\n{caption}",
                                label=f"partner-ig-{a.client}-short", cwd=tempfile.gettempdir())
        if shorter and not run_checks(shorter.strip(), style):
            caption, errs = shorter.strip(), []
        else:                                                  # 모델이 길이를 안 지키면 문장 경계에서 자른다(내용은 앞부분 그대로)
            cut = trim_to_sentence(caption, CAPTION_MAX - 30)
            if not run_checks(cut, style):
                caption, errs = cut, []
    if errs:
        print("[check] 캡션 탈락 —", " · ".join(errs), "→ 규칙 캡션으로 대체")
        caption = fallback_caption(topic, c)
    tags = hashtags(style)
    photos = pick_photos(c, st)
    write_folder(folder, caption, tags, photos, c)
    print(f"[ok] {folder} · 사진 {[p.name for p in photos]} · 캡션 {len(caption)}자 · 모델 {used or '규칙'}")
    rc = 0 if a.no_send else send_kakao(c, folder, caption, tags)
    st["runs"].append({"at": datetime.now().isoformat(timespec="seconds"), "topic": topic, "folder": str(folder),
                       "photos": [p.name for p in photos], "sent": (rc == 0 and not a.no_send), "await_ok": not a.no_send})
    st["last_folder"] = str(folder)
    save_state(a.client, st)
    return rc


def self_test() -> int:
    c = CLIENTS["jo"]
    style = style_of(c)
    assert len(hashtags(style)) == 15 and hashtags(style)[0] == "#고척골프"
    assert run_checks("체험권 99,000원", style) and run_checks("웰페리온이 만든", style)
    assert not run_checks("차분히 연습하는 저녁", style)
    st = {"photo_idx": 0}
    p1 = pick_photos(c, st); p2 = pick_photos(c, st)
    assert len(p1) == 3 and p1 != p2 and not any(SKIP_IMG.search(p.name) for p in p1)
    assert room_name(c) == "★조재오 지점장님"
    long = ("첫 문장입니다. " * 30) + TAIL
    cut = trim_to_sentence(long, CAPTION_MAX - 30)
    assert len(cut) <= CAPTION_MAX - 30 and cut.endswith(TAIL) and cut.startswith("첫 문장입니다.")
    print("partner_instagram_daily 자가점검 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
