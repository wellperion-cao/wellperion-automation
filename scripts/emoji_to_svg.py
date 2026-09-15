"""이모지 아이콘 → 선 아이콘(inline SVG) 치환기 — 화면 UI/UX 표준 ⑥ 「이모지 아이콘 0」용.

왜 있나: 디자인 규칙집(UI/UX Pro Max) 「no-emoji-icons — SVG 아이콘을 쓴다」. 이모지는 기기마다 다르게 그려지고
글자 크기·색을 화면이 다스릴 수 없다. 2026-09-15 전수 실측에서 화면 82장에 이모지 아이콘이 있었다.

하는 일: HTML 의 글(태그 밖 텍스트)에 있는 이모지를 같은 뜻의 선 아이콘(24×24 · currentColor · 1em)으로 바꾼다.
  · <script>·<style>·주석·태그 속성(title="…") 안은 건드리지 않는다 — 코드·툴팁 글자는 그대로.
  · 뜻이 색인 것(🔴🟢🟡⚫⚪)은 같은 색의 점으로.
  · 표에 없는 이모지는 그대로 두고 --report 로 알려 준다(모르는 것을 지우지 않는다).
  · 항해 세계관 아이콘(🌟🌊🧭🚢⚓🏁⛵⛴️🛳️)도 표에 있다 — 쓸지 말지는 GM 이 A/B 로 정한다(2026-09-15).

쓰는 법:
  C:/Python314/python.exe scripts/emoji_to_svg.py "<html>" [--out 사본경로] [--report]
  --out 이 없으면 제자리에 쓴다. 파이썬에서: from emoji_to_svg import convert
"""
import io
import re
import sys

# 이름: (path d, fill색 또는 None) — stroke 는 currentColor · 채운 점만 fill
ICONS = {
    "⚠": ("M12 3 2 20h20L12 3z M12 9v5 M12 17h.01", None),
    "🚨": ("M12 3 2 20h20L12 3z M12 9v5 M12 17h.01", None),
    "🔴": ("", "#B91C1C"), "🟢": ("", "#0A6E66"), "🟡": ("", "#B45309"), "⚫": ("", "#0F172A"), "⚪": ("", "#94A3B8"),
    "📊": ("M4 20V10 M10 20V4 M16 20v-7 M22 20H2", None),
    "📘": ("M2 4h7a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H2z M22 4h-7a3 3 0 0 0-3 3v13a2 2 0 0 1 2-2h8z", None),
    "📖": ("M2 4h7a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H2z M22 4h-7a3 3 0 0 0-3 3v13a2 2 0 0 1 2-2h8z", None),
    "📚": ("M4 4h4v16H4z M10 4h4v16h-4z M16 6l4-1 3 15-4 1z", None),
    "⚙": ("M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M12 2v3 M12 19v3 M2 12h3 M19 12h3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M4.9 19.1 7 17 M17 7l2.1-2.1", None),
    "🔧": ("M14 6a4 4 0 0 0 5 5l-9 9-3-3 9-9z M4 20l3-3", None),
    "🤖": ("M5 8h14v10H5z M9 12h.01 M15 12h.01 M12 3v5 M9 18v3 M15 18v3", None),
    "📋": ("M9 4h6v3H9z M6 6h2v14h8V6h2 M9 12h6 M9 16h6", None),
    "📄": ("M6 3h9l4 4v14H6z M15 3v4h4 M9 12h6 M9 16h6", None),
    "📝": ("M4 20h4l10-10-4-4L4 16z M13 7l4 4", None),
    "✍": ("M4 20h4l10-10-4-4L4 16z M13 7l4 4", None),
    "🌟": ("M12 3l2.7 5.6 6.2.9-4.5 4.3 1.1 6.2L12 17l-5.5 3 1.1-6.2L3 9.5l6.2-.9z", None),
    "🎯": ("M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0 M12 12m-5 0a5 5 0 1 0 10 0a5 5 0 1 0-10 0 M12 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0-2 0", None),
    "🌊": ("M2 12c2-2 4-2 6 0s4 2 6 0 4-2 6 0 M2 18c2-2 4-2 6 0s4 2 6 0 4-2 6 0", None),
    "🧭": ("M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0 M16 8l-3 7-5 1 3-7z", None),
    "🚢": ("M3 17l2-6h14l2 6 M6 11V7h12v4 M10 7V4h4v3 M2 20c2 1 4 1 6 0s4-1 6 0 4 1 6 0", None),
    "⛴": ("M3 17l2-6h14l2 6 M6 11V7h12v4 M10 7V4h4v3 M2 20c2 1 4 1 6 0s4-1 6 0 4 1 6 0", None),
    "🛳": ("M3 17l2-6h14l2 6 M6 11V7h12v4 M10 7V4h4v3 M2 20c2 1 4 1 6 0s4-1 6 0 4 1 6 0", None),
    "⛵": ("M12 3v15 M12 3l7 10H12 M5 13h7 M3 19c3 1 6 1 9 0s6-1 9 0", None),
    "⚓": ("M12 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4z M12 7v14 M5 13a7 7 0 0 0 14 0 M3 13h4 M17 13h4", None),
    "🏁": ("M5 3v18 M5 4h12l-2 4 2 4H5", None),
    "🖨": ("M6 9V3h12v6 M6 18H3v-7h18v7h-3 M6 15h12v6H6z", None),
    "🔗": ("M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1", None),
    "📨": ("M3 6h18v12H3z M3 7l9 6 9-6", None),
    "✉": ("M3 6h18v12H3z M3 7l9 6 9-6", None),
    "🖥": ("M3 4h18v12H3z M8 20h8 M12 16v4", None),
    "🧑": ("M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M4 21a8 8 0 0 1 16 0", None),
    "👤": ("M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M4 21a8 8 0 0 1 16 0", None),
    "👥": ("M9 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M2 21a7 7 0 0 1 14 0 M16 4a4 4 0 0 1 0 8 M22 21a7 7 0 0 0-5-6.7", None),
    "💼": ("M3 8h18v12H3z M8 8V5h8v3 M3 13h18", None),
    "🧯": ("M9 6h6v15H9z M12 6V3 M12 3h4 M9 10h6", None),
    "🚑": ("M3 8h13l5 4v6H3z M8 10v4 M6 12h4 M7 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M17 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4z", None),
    "📅": ("M4 5h16v15H4z M4 10h16 M8 3v4 M16 3v4", None),
    "🗓": ("M4 5h16v15H4z M4 10h16 M8 3v4 M16 3v4", None),
    "✅": ("M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0 M8 12l3 3 5-6", None),
    "⚖": ("M12 3v18 M6 21h12 M3 8h18 M6 8l-3 6h6z M18 8l-3 6h6z", None),
    "💗": ("M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z", None),
    "🩺": ("M6 3v6a6 6 0 0 0 12 0V3 M12 15v3a3 3 0 0 0 6 0v-3 M18 12a2 2 0 1 0 0 4 2 2 0 0 0 0-4z", None),
    "🏢": ("M4 21V4h10v17 M14 9h6v12 M8 8h2 M8 12h2 M8 16h2 M17 13h.01 M17 17h.01", None),
    "💰": ("M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0 M12 7v10 M9.5 9.5h4a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3h4", None),
    "📌": ("M12 17v5 M8 3h8l-1 6 3 3H6l3-3z", None),
    "🔍": ("M10 10m-6 0a6 6 0 1 0 12 0a6 6 0 1 0-12 0 M15 15l6 6", None),
    "📤": ("M4 17v3h16v-3 M12 15V4 M8 8l4-4 4 4", None),
    "⏱": ("M12 13m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0 M12 9v4l3 2 M9 2h6", None),
    "💡": ("M9 18h6 M10 21h4 M12 3a6 6 0 0 0-4 10.5c.6.6 1 1.4 1 2.5h6c0-1.1.4-1.9 1-2.5A6 6 0 0 0 12 3z", None),
    "👉": ("M5 12h12 M13 6l6 6-6 6", None),
    "🔔": ("M6 16V11a6 6 0 0 1 12 0v5l2 2H4z M10 21h4", None),
    "📎": ("M20 11l-8 8a5 5 0 0 1-7-7l9-9a3 3 0 0 1 4 4l-9 9a1 1 0 0 1-1.5-1.5L15 7", None),
    "🏠": ("M3 11l9-8 9 8 M5 10v10h5v-6h4v6h5V10", None),
    "🔒": ("M6 11h12v10H6z M8 11V7a4 4 0 0 1 8 0v4", None),
    "🔥": ("M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-6 1-9z", None),
    "☀": ("M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M4.9 19.1 7 17 M17 7l2.1-2.1", None),
    "🧹": ("M14 3l7 7-6 6-7-7z M8 9l-5 5 4 4 5-5", None),
    "📈": ("M3 17l6-6 4 4 8-8 M15 7h6v6", None),
    "📉": ("M3 7l6 6 4-4 8 8 M15 17h6v-6", None),
    "🗂": ("M3 6h6l2 2h10v12H3z", None),
    "📂": ("M3 6h6l2 2h10v12H3z", None),
    "📁": ("M3 6h6l2 2h10v12H3z", None),
    "🗑": ("M4 7h16 M9 7V4h6v3 M6 7l1 14h10l1-14", None),
    "✏": ("M4 20h4l10-10-4-4L4 16z M13 7l4 4", None),
    "🗣": ("M4 6h12v9H9l-4 3v-3H4z M19 8a4 4 0 0 1 0 6", None),
    "💬": ("M4 4h16v12h-9l-5 4v-4H4z", None),
    "📞": ("M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z", None),
    "📱": ("M7 3h10v18H7z M11 18h2", None),
    "🎥": ("M3 7a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7zm13 3 5-3v10l-5-3", None),
    "📷": ("M4 8h4l2-3h4l2 3h4v11H4z M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z", None),
    "🏋": ("M3 10v4 M21 10v4 M6 8v8 M18 8v8 M6 12h12", None),
}

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]\uFE0F?")
_SKIP = re.compile(r"(<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->|<[^>]*>)", re.S | re.I)


def svg(key: str) -> str:
    d, fill = ICONS[key]
    if fill:
        return (f'<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
                f'<circle cx="12" cy="12" r="6" fill="{fill}"/></svg>')
    return (f'<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
            f'<path d="{d}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def convert(html: str):
    """(치환된 html, 치환 수, 표에 없는 이모지 집합)"""
    unknown, n = set(), 0
    parts = _SKIP.split(html)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:            # 태그·스크립트·스타일·주석 — 그대로
            out.append(p); continue
        def rep(m):
            nonlocal n
            key = m.group(0).replace("\uFE0F", "")
            if key in ICONS:
                n += 1; return svg(key)
            unknown.add(key); return m.group(0)
        out.append(_EMOJI.sub(rep, p))
    s = "".join(out)
    if n and ".ico{" not in s and "class=\"ico\"" in s:
        css = "<style>.ico{display:inline-block;width:1em;height:1em;vertical-align:-.15em}</style>"
        s = s.replace("</head>", css + "</head>", 1) if "</head>" in s else css + s
    return s, n, unknown


def main(argv):
    if not argv:
        print(__doc__); return 2
    src = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else src
    raw = io.open(src, encoding="utf-8", newline="").read()
    s, n, unknown = convert(raw)
    io.open(out, "w", encoding="utf-8", newline="").write(s)
    print(f"치환 {n} · 표에 없음 {len(unknown)}" + (" " + " ".join(sorted(unknown)) if unknown and "--report" in argv else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
