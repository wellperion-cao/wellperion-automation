# -*- coding: utf-8 -*-
"""meeting_transcribe.py — 회의 녹음(m4a 등) → 글 → AI 요약 A4, 비용 0(GM PC 로컬 Whisper).

회장님 말씀 2026-09-16 「회의 녹음 → AI 요약」 · 웰리 요청 · 시토.

왜 로컬인가
  서버(2vCPU·1GB)는 Whisper를 못 돌리고, 외부 음성→글 서비스는 돈이 들어 GM 결재가 필요하다.
  GM PC 에서 faster-whisper(CPU·small·한국어)로 돌리면 비용 0.

입력 폴더
  GM 구글드라이브 데스크톱 동기 폴더를 먼저 찾아봤다 — 이 PC엔 없다(2026-09-16 실측:
  `Get-ChildItem $env:USERPROFILE -Directory`에 Google/Drive/내 드라이브 이름 폴더가 0건,
  `%LOCALAPPDATA%\\Google`은 있지만 동기 폴더가 아니라 Chrome 류 캐시다).
  그래서 기본 입력 폴더 = status/meeting_recordings/(로컬·gitignore) · --dir 로 바꾼다.

원문·요약
  원문(.txt, 개인정보는 kakao_room_listen.mask_secrets 로 가림) = status/meeting_recordings/transcripts/
  요약 4절(결정·지시·숫자·다음 걸음) = model_router.run_claude, 지어내지 않기(불명은 「미확인」)
  A4 한 장 = coo/chairman/회의요약_A3.html 의 :root 색 토큰·폰트를 그대로 재사용(새 렌더러 안 만든다),
  png 캡처는 meeting_brief_a3.measure()를 그대로 부른다(같은 헤드리스 캡처 재사용).

사용
  python scripts/meeting_transcribe.py                # 새 녹음 찾아 전부 처리(기본 dry-run 알림)
  python scripts/meeting_transcribe.py --send          # 텔레그램 실발신
  python scripts/meeting_transcribe.py --file X.m4a    # 한 파일만
  python scripts/meeting_transcribe.py --selfcheck      # 모델 없이 마스킹·상태파일·요약파싱 점검
  python scripts/meeting_transcribe.py --dry-run        # 무음 시험 음성으로 끝까지(요약은 --no-llm)

# ponytail: faster-whisper 모델은 함수 안에서 매회 새로 올린다(여러 파일 처리 시 재사용 안 함) —
#   느리면 process() 밖으로 모델 로드를 빼 재사용하게 고친다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from kakao_room_listen import mask_secrets  # noqa: E402
from model_router import run_claude  # noqa: E402
from notify.telegram_send import send as tg_send  # noqa: E402
from cpo_report import GM_CHAT_ID  # noqa: E402
import meeting_brief_a3 as _a3  # noqa: E402 — esc()·measure()(png 캡처) 재사용

DEFAULT_DIR = os.path.join(ROOT, "status", "meeting_recordings")
TRANSCRIPT_DIR = os.path.join(DEFAULT_DIR, "transcripts")
STATE = os.path.join(ROOT, "status", "meeting_transcribe_state.json")
OUT_DIR = os.path.join(ROOT, "3. 웰페리온 가이드", "coo", "chairman")
EXTS = (".m4a", ".mp3", ".wav", ".mp4")
MODEL_SIZE = "small"
SECTIONS = ["참석·일시", "결정", "지시", "숫자", "다음 걸음"]

TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>회의 녹음 요약 — {title}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Noto+Serif+KR:wght@600;800&display=swap" rel="stylesheet">
<style>
:root{{--ink:#1a1815;--sub:#5f5a54;--line:#d9d3cc;--navy:#1f2f4a;--gold:#b58a3a;--bg:#faf8f5;--red:#a33a2a;--ok:#2f6f4e}}
@page{{size:A4;margin:0}}
*{{box-sizing:border-box}}
body{{margin:0;background:#8A9099;font-family:'Noto Sans KR',sans-serif;color:var(--ink)}}
@media print{{body{{background:#fff}}.page{{margin:0!important;box-shadow:none!important}}}}
.page{{width:794px;min-height:1123px;background:#fff;margin:30px auto;padding:34px 40px;box-shadow:0 4px 20px rgba(0,0,0,.35)}}
.hd{{border-bottom:3px solid var(--navy);padding-bottom:10px;margin-bottom:14px}}
.brand{{font:700 12px/1 'Noto Serif KR',serif;letter-spacing:.32em;color:var(--gold)}}
h1{{font:800 22px/1.3 'Noto Serif KR',serif;margin:6px 0 4px;color:var(--navy)}}
.meta{{font-size:12px;color:var(--sub)}}
.box{{border:1px solid var(--line);border-radius:6px;padding:12px 14px;margin-bottom:14px}}
.box h2{{margin:0 0 6px;font-size:14px;font-weight:900;color:var(--navy);border-left:4px solid var(--gold);padding-left:8px}}
ul{{margin:0;padding-left:18px}}
li{{font-size:13px;line-height:1.7;margin:2px 0}}
.empty{{color:var(--sub);font-size:12.5px}}
.ft{{border-top:1px solid var(--line);margin-top:6px;padding-top:8px;font-size:11px;color:var(--sub);display:flex;justify-content:space-between}}
</style></head><body>
<div class="page">
  <div class="hd">
    <div class="brand">WELLPERION</div>
    <h1>회의 녹음 요약 — {title}</h1>
    <div class="meta">{meta}</div>
  </div>
  {boxes}
  <div class="ft"><span>원문 텍스트는 status/meeting_recordings/transcripts/ · 생성 scripts/meeting_transcribe.py</span><span>AI 웰리</span></div>
</div>
</body></html>
"""


def load_state() -> dict:
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(s: dict) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def find_new_files(folder: str, state: dict) -> list[str]:
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(EXTS):
            continue
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        if state.get(name, {}).get("hash") == file_hash(path):
            continue  # 이미 처리한 파일(해시 동일) — 중복 차단
        out.append(path)
    return out


def transcribe(path: str) -> str:
    from faster_whisper import WhisperModel  # 무거운 import — 필요할 때만

    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(path, language="ko")
    lines = []
    for seg in segments:
        ts = f"[{int(seg.start) // 60:02d}:{int(seg.start) % 60:02d}]"
        lines.append(f"{ts} {seg.text.strip()}")
    return mask_secrets("\n".join(lines))


SUMMARY_PROMPT = """다음은 회의 녹음을 글로 옮긴 원문이다. 아래 형식으로만 요약하라.
규칙: 원문에 없는 숫자·사실을 지어내지 않는다 — 그 절에 원문 근거가 없으면 정확히 "미확인"이라고만 쓴다.

## 참석·일시
## 결정
## 지시
## 숫자
## 다음 걸음

원문:
{text}
"""


def summarize(text: str) -> str:
    out, _used = run_claude(SUMMARY_PROMPT.format(text=text[:12000]), label="meeting-transcribe")
    return out or ""


def parse_summary(md_text: str) -> dict:
    sections = {k: "" for k in SECTIONS}
    cur = None
    for line in (md_text or "").splitlines():
        m = re.match(r"##\s*(.+)", line.strip())
        if m:
            cur = m.group(1).strip()
            continue
        if cur in sections and line.strip():
            sections[cur] += line.strip() + "\n"
    return sections


def render_a4(title: str, sections: dict, meta: str, out_path: str) -> None:
    boxes = []
    for name in SECTIONS:
        body = sections.get(name, "").strip()
        if body:
            items = "".join(f"<li>{_a3.esc(li)}</li>" for li in body.splitlines() if li.strip())
            inner = f"<ul>{items}</ul>"
        else:
            inner = '<div class="empty">미확인</div>'
        boxes.append(f'<div class="box"><h2>{_a3.esc(name)}</h2>{inner}</div>')
    html = TEMPLATE.format(title=_a3.esc(title), meta=_a3.esc(meta), boxes="\n  ".join(boxes))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def notify(title: str, out_path: str, send: bool) -> None:
    text = f"\U0001f399 회의 요약 준비 — {title} · {out_path}"
    if send:
        ok = tg_send(GM_CHAT_ID, text)
        print("[텔레그램]", "발송" if ok else "실패", text)
    else:
        print("[dry-run 텔레그램]", text)


def gen_silent_wav(path: str, seconds: float = 2.0) -> None:
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


def process(path: str, no_llm: bool) -> str:
    name = os.path.basename(path)
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    text = transcribe(path)
    txt_path = os.path.join(TRANSCRIPT_DIR, os.path.splitext(name)[0] + ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    title = os.path.splitext(name)[0]
    sections = {k: "" for k in SECTIONS} if no_llm else parse_summary(summarize(text))

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out_html = os.path.join(OUT_DIR, f"회의녹음요약_{dt.date.today():%y%m%d}.html")
    render_a4(title, sections, stamp, out_html)
    png = os.path.splitext(out_html)[0] + ".png"
    _a3.measure(out_html, png)
    return out_html


def selfcheck() -> int:
    ok = True

    # mask_secrets 는 키워드(비밀번호·계정·아이디 등) 뒤 값과 영문+숫자+특수문자 8자+ 토큰만 가린다
    # (kakao_room_listen.py 원설계 — 09-15 카톡 계정 유출 사고 대응). 전화·주민번호 모양은 이 함수의
    # 범위 밖이다 — ponytail: 여기서 새 정규식을 얹지 않는다, 필요해지면 mask_secrets 자체를 고친다.
    masked = mask_secrets("비밀번호 abcd1234!")
    if "abcd1234" in masked:
        print("[FAIL] mask_secrets 가 값을 못 가림:", masked)
        ok = False
    else:
        print("[OK] mask_secrets")

    s = load_state()
    s["_selfcheck"] = {"hash": "x", "at": "test"}
    save_state(s)
    if load_state().get("_selfcheck", {}).get("hash") != "x":
        print("[FAIL] 상태 파일 읽기/쓰기")
        ok = False
    else:
        print("[OK] 상태 파일 읽기/쓰기")
    s.pop("_selfcheck", None)
    save_state(s)

    demo_md = "## 참석·일시\n2026-09-16 오전 10시\n## 결정\n- A 결정\n## 지시\n- B 지시\n## 숫자\n- 300만원\n## 다음 걸음\n- 다음주 재논의\n"
    sec = parse_summary(demo_md)
    if "A 결정" not in sec["결정"] or "300만원" not in sec["숫자"]:
        print("[FAIL] 요약 파싱:", sec)
        ok = False
    else:
        print("[OK] 요약 파싱")

    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEFAULT_DIR, help="녹음 폴더(기본 status/meeting_recordings/)")
    ap.add_argument("--file", help="이 파일 하나만 처리(폴더 스캔 생략)")
    ap.add_argument("--send", action="store_true", help="텔레그램 실발신(기본 dry-run)")
    ap.add_argument("--no-llm", action="store_true", help="요약 호출 생략(연결 시험용)")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="무음 시험 음성으로 끝까지(요약은 --no-llm)")
    a = ap.parse_args()

    if a.selfcheck:
        return selfcheck()

    if a.dry_run:
        os.makedirs(a.dir, exist_ok=True)
        test_path = os.path.join(a.dir, "_selfcheck_silence.wav")
        gen_silent_wav(test_path)
        try:
            out = process(test_path, no_llm=True)
        finally:
            os.remove(test_path)
        print("dry-run 완료 →", out)
        return 0

    state = load_state()
    targets = [a.file] if a.file else find_new_files(a.dir, state)
    if not targets:
        print("새 녹음 없음:", a.dir)
        return 0

    for path in targets:
        name = os.path.basename(path)
        print("처리:", name)
        out = process(path, no_llm=a.no_llm)
        state[name] = {"hash": file_hash(path), "at": dt.datetime.now().isoformat(timespec="seconds")}
        save_state(state)
        notify(os.path.splitext(name)[0], out, a.send)
        print("완료 →", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
