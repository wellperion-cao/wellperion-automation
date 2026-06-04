# -*- coding: utf-8 -*-
"""웰리(AI CEO) 캐릭터 시안 샘플 생성 — 무료 Pollinations.ai (키 불필요).
프롬프트 3종을 URL 인코딩해 GET → instagram/Image/welly_concept/시안N.jpg 저장.
실패 시 추정 금지: 시안별 성공/실패를 콘솔에 명시."""
import os, sys, time, urllib.parse, urllib.request

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "instagram", "Image", "welly_concept")
OUT_DIR = os.path.abspath(OUT_DIR)
os.makedirs(OUT_DIR, exist_ok=True)

# 브랜드 색: 베이지 #B79F8A, 블랙 #221F20, 하이라이트 #ED5B3F
PROMPTS = {
    "시안1_친근마스코트": (
        "Cute friendly mascot character of an AI butler concierge named Welly, "
        "wearing a small elegant golden crown, warm rounded body, big kind eyes, gentle confident smile, "
        "soft beige (#B79F8A) and deep charcoal black (#221F20) color palette with a subtle warm orange (#ED5B3F) accent, "
        "premium high-end private sports club brand mascot, clean vector illustration, "
        "front facing friendly pose with one hand gently raised in greeting, "
        "minimal flat design, solid soft beige background, centered, no text, high quality"
    ),
    "시안2_미니멀프리미엄심볼": (
        "Minimal premium luxury emblem of an AI orchestrator named Welly, "
        "abstract refined crown symbol fused with a calm geometric face silhouette, "
        "single elegant line-art style, thin even strokes, beige (#B79F8A) lines on deep black (#221F20) background, "
        "tiny warm orange (#ED5B3F) accent dot, high-end private sports club luxury magazine aesthetic, "
        "sophisticated restrained icon, perfectly centered, lots of negative space, no text, ultra clean"
    ),
    "시안3_세련된캐릭터": (
        "Sophisticated elegant character of a warm yet systematic AI chief executive named Welly, "
        "slender modern stylized figure wearing a sleek minimal golden crown, "
        "calm reassuring expression, premium tailored silhouette, "
        "luxury beige (#B79F8A) and charcoal black (#221F20) palette with subtle warm orange (#ED5B3F) highlight, "
        "refined editorial illustration, high-end private sports club brand character, "
        "three-quarter confident standing pose, clean solid neutral background, centered, no text, magazine quality"
    ),
}

def gen(name, prompt):
    enc = urllib.parse.quote(prompt, safe="")
    url = f"https://image.pollinations.ai/prompt/{enc}?width=1024&height=1024&nologo=true&seed=42"
    out = os.path.join(OUT_DIR, f"{name}.jpg")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 welperion-welly-concept"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
        if not data or len(data) < 3000:
            print(f"FAIL\t{name}\t응답 너무 작음({len(data)}B) — 차단 의심")
            return False
        with open(out, "wb") as f:
            f.write(data)
        print(f"OK\t{name}\t{len(data)}B\t{out}")
        return True
    except Exception as e:
        print(f"FAIL\t{name}\t{type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    results = {}
    for n, p in PROMPTS.items():
        results[n] = gen(n, p)
        time.sleep(2)
    print("---SUMMARY---")
    for n, ok in results.items():
        print(f"{'OK ' if ok else 'FAIL'}\t{n}")
