# -*- coding: utf-8 -*-
"""실무진 안내 카드(HTML→PNG) — 위생·감염 예방 선제조치 편.

2026-08-26 ★운영+시설+지원+주차 방 발송분. 렌더러와 CSS 는 kakao_summary_card 를
그대로 재사용한다(새 렌더 엔진 없음). 다음 안내를 만들 때는 build() 안의 item()
목록만 갈아 끼우면 된다.

한글은 word-break:keep-all 이 없으면 단어 중간에서 잘린다("체크해 주/세요").
EXTRA_CSS 첫 줄이 그 방어다 — 지우지 말 것.
발송은 이 파일이 하지 않는다. scripts/kakao_report_sender.py --image <png>
--caption <본문> --only-room <방 이름> 으로 따로 보낸다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kakao_summary_card as ksc  # STYLE_CSS · PAGE_TEMPLATE · render_card_png 재사용

EXTRA_CSS = """
body{word-break:keep-all; overflow-wrap:break-word}
.card{max-width:500px}
.hd{padding:20px 22px 16px; background:linear-gradient(135deg,#2C4E74,#1A2230); color:#fff}
.hd .k{font-size:11px; letter-spacing:.12em; font-weight:800; opacity:.72}
.hd .t{font-size:21px; font-weight:800; letter-spacing:-.02em; margin-top:6px}
.hd .s{font-size:12.5px; opacity:.78; margin-top:6px; line-height:1.5}
.body{padding:18px 22px 6px}
.item{display:flex; gap:12px; padding:14px 0; border-top:1px solid var(--line)}
.item:first-child{border-top:0; padding-top:2px}
.no{flex:0 0 auto; width:25px; height:25px; border-radius:8px; background:var(--blue); color:#fff;
    display:grid; place-items:center; font-size:12.5px; font-weight:800; margin-top:1px}
.no.gold{background:var(--gold)}
.it .h{font-size:14.5px; font-weight:800; letter-spacing:-.01em}
.it .d{font-size:12.8px; color:var(--dim); margin-top:4px; line-height:1.62}
.it .d b{color:var(--ink); font-weight:700}
.it .who{display:inline-block; font-size:10.5px; font-weight:800; padding:2px 8px;
    border-radius:999px; margin-top:7px; color:var(--good); background:var(--goodbg)}
.it .who.warn{color:var(--warn); background:var(--warnbg)}
.ask{margin:4px 22px 0; padding:13px 15px; border-radius:13px;
     background:var(--warnbg); border:1px solid color-mix(in srgb,var(--warn) 32%,transparent)}
.ask .a1{font-size:12.5px; font-weight:800; color:var(--warn)}
.ask .a2{font-size:12.3px; color:var(--ink); margin-top:3px; line-height:1.6}
footer.foot{margin-top:16px}
"""


def item(no, title, desc, who=None, who_cls="", gold=False):
    w = f'<div class="who {who_cls}">{who}</div>' if who else ""
    return (f'<div class="item"><div class="no{" gold" if gold else ""}">{no}</div>'
            f'<div class="it"><div class="h">{title}</div>'
            f'<div class="d">{desc}</div>{w}</div></div>')


def build() -> str:
    items = "".join([
        item(1, "접점 알콜소독",
             "손잡이 · 락커 · 키오스크 · 무인발권기 · 주차 정산기<br>"
             "<b>오픈 전 · 마감 후 하루 2회</b> 직접 소독하신 뒤 일일점검에 체크해 주세요.<br>"
             "점검은 보는 칸이 아니라 <b>하신 것을 남기는 칸</b>입니다.",
             "실무진 직접 실행"),
        item(2, "손소독제 3곳 비치",
             "리셉션 · 사우나 · 주차<br>"
             "<b>회원님들 쓰시는 용</b>입니다. 직원 소독은 위 접점 알콜소독으로 따로 갑니다.<br>"
             "<b>9/1(월) 시행</b> · 8/31까지 배치 완료",
             "운영부 · 배치", gold=True),
        item(3, "벌레 — 방역 + 벌레트랩",
             "집중 3곳 : 여자 키즈락커 · 여자사우나 · 수영장 주변<br>"
             "7~8월 벌레 접수 <b>7건</b>이 이 3곳에 몰렸습니다.<br>"
             "방역에 <b>벌레트랩</b>을 더하는 방향이며, <b>세스코 협의가 필요한 단계</b>입니다.",
             "세스코 협의 필요", who_cls="warn"),
        item(4, "일일점검 나머지 3가지",
             "환기 · 공용 비품(매트리스 · 의자 · 소파) · 직원 건강<br>"
             "기존 점검 동선 안에서 그대로 확인해 주시면 됩니다.",
             "실무진 직접 실행"),
        item(5, "9/30 두 숫자 확인",
             "손소독제 한 달 사용량 · 9월 벌레 접수 건수<br>"
             "7월 5건 → 8월 2건. 9월 숫자로 효과를 봅니다."),
    ])
    card = (
        '<div class="card" id="card">'
        '<div class="hd">'
        '<div class="k">WELLPERION</div>'
        '<div class="t">위생 · 감염 예방 선제 조치</div>'
        '<div class="s">별도 공지 없이, 현장 관리를 꾸준히 강화하는 방향으로 갑니다.<br>'
        '9월부터 아래대로 진행합니다.</div>'
        '</div>'
        f'<div class="body">{items}</div>'
        '<div class="ask"><div class="a1">시설부 확인 부탁드립니다</div>'
        '<div class="a2">세스코 계약에 <b>해충 방제</b>와 <b>벌레트랩</b>이 들어 있는지 확인 부탁드립니다. '
        '소독만 있고 방제가 빠져 있으면 벌레가 계속 나오는 원인일 수 있습니다.</div></div>'
        '<footer class="foot"><div class="frow"><span class="tag">웰페리온</span>'
        '<b>★운영 + 시설 + 지원 + 주차</b> · 2026-08-26</div>'
        '<div class="frow">AI 웰리 드림</div></footer>'
        '</div>'
    )
    return ksc.PAGE_TEMPLATE.format(style=ksc.STYLE_CSS + EXTRA_CSS, card=card)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("위생감염예방_선제조치_20260826.png")
    ksc.render_card_png(build(), out)
    print("PNG:", out, out.stat().st_size, "bytes")
