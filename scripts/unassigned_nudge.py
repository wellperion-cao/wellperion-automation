# -*- coding: utf-8 -*-
"""문의 담당자 미배정 배정 독려 안내 (배9206 · GM 지시 2026-07-23)

GM 지시: "미배정건 각 팀장분들한테 좋게 푸시해서 배정 다 채울 수 있도록."

무엇을 하나
  - 담당자가 아직 정해지지 않은 강습 문의를 종목별로 묶고, 오래 기다린 순으로
    상위 몇 건을 이름과 함께 보여준 뒤, 배정 화면 링크로 바로 갈 수 있게 안내한다.
  - 어조는 독촉이 아니라 부탁·감사 (GM "좋게 푸시").

왜 별도 모듈인가
  - 22:30 일일보고(report_stream_1_impl)의 '📌 누적 미배정' 한 줄은 참고 표기라
    행동을 끌어내지 못한다. 이 모듈은 '무엇을·어디서·어떻게' 까지 준다.
  - 판정 기준은 새로 만들지 않고 report_stream_1_impl 의 것을 그대로 쓴다
    (약속 L01 한 곳만 본다 — 미배정 정의가 두 벌이 되면 숫자가 갈린다).

게이트
  - 기본 = dry-run(출력만). 실제 발송은 --send 를 명시해야 한다.
  - --to gm(기본, GM 개인 봇방) / --to staff(문의알림방 실무진).
    실무진 발송은 되돌릴 수 없으므로 GM 확인 후 전환한다(배9253 과 동일 절차).
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import report_stream_1_impl as R  # noqa: E402  (미배정 판정 단일 출처)

# 방 — daily_scheduler 와 같은 값(.env 우선, 폴백 동일). 여기서 새 값을 만들지 않는다.
GM_CHAT_ID = 8254867551
STAFF_CHAT_ID = int(os.environ.get("TELEGRAM_INQUIRY_CHAT_ID") or -5516675010)

# 배정 화면 — 멤버십과 강습이 화면이 갈린다(GM 2026-07-23 지적: 멤버십 링크만 주면 강습은 못 간다).
# lesson.html 은 membership.html?manage=lesson 으로 넘겨주는 정식 강습 진입 주소다.
_BASE = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/"
ASSIGN_URL_LESSON = _BASE + "lesson.html"
ASSIGN_URL_MEMBERSHIP = _BASE + "membership.html"

# 화면 입장 코드 — GM 2026-07-23 제공. 실무진이 코드를 몰라 못 들어가는 일이 없게 안내에 포함.
ENTRY_CODE = "1200"

# 오래 기다린 순 상위 몇 명까지 이름을 적을지 — 너무 길면 안 읽는다.
TOP_N = 6
STALE_MIN_DAYS = 3
STALE_MAX_DAYS = 30


def collect_unassigned(today: str) -> list[dict]:
    """담당자 미배정 + 활성 강습 문의를 경과일 내림차순으로."""
    sources = {
        "성인강습": R._fetch_list("lesson_inquiry_list", type="성인강습"),
        "유소년강습": R._fetch_list("lesson_inquiry_list", type="유소년강습"),
    }
    out: list[dict] = []
    for label, rows in sources.items():
        for r in rows:
            if R._is_test_row(r):
                continue
            days = R._days_since(str(r.get("timestamp", "") or ""), today)
            if not (STALE_MIN_DAYS <= days <= STALE_MAX_DAYS):
                continue
            if not R._is_unassigned_active(r, True):
                continue
            out.append({
                "type": label,
                "sport": str(r.get("sport", "") or "-").strip() or "-",
                "name": str(r.get("name", "") or "-").strip() or "-",
                "days": days,
            })
    out.sort(key=lambda x: -x["days"])
    return out


def _sport_short(sport: str) -> str:
    """종목명을 세부 옵션 앞부분으로 정규화.

    원본이 '성인 수영 (개인레슨 / 단체레슨)'·'뮤지컬 (Brad Little Star Academy)' 처럼
    괄호 안 세부가 붙어 오는데, 그대로 세면 같은 종목이 여러 줄로 쪼개진다(실제 발생).
    """
    return sport.split("(")[0].strip() or "-"


def _sport_lines(items: list[dict], label: str) -> list[str]:
    counts = Counter(_sport_short(i["sport"]) for i in items if i["type"] == label)
    if not counts:
        return []
    total = sum(counts.values())
    parts = [f"■ {label} {total}건"]
    ranked = counts.most_common()
    head = ranked[:3]
    rest = sum(c for _, c in ranked[3:])
    body = " · ".join(f"{s} {c}" for s, c in head)
    if rest:
        body += f" · 그 외 {rest}"
    parts.append(f"  {body}")
    return parts


def build_message(today: str | None = None) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    items = collect_unassigned(today)
    if not items:
        return "✅ 담당자 미배정 문의 0건 — 모두 배정 완료되었습니다. 감사합니다 🙏"

    lines = [
        f"🤝 문의 담당 배정 부탁드립니다 — {len(items)}건",
        "",
        "요즘 강습 문의가 꾸준히 들어오고 있습니다.",
        "아래 건들이 아직 담당자가 정해지지 않아 안내드립니다.",
        "",
    ]
    for label in ("성인강습", "유소년강습"):
        lines += _sport_lines(items, label)
    lines.append("")

    lines.append("⏳ 오래 기다리신 분부터")
    for it in items[:TOP_N]:
        sport = it["sport"].split("(")[0].strip()
        lines.append(f"  · {it['name']} · {sport} ({it['days']}일째)")
    if len(items) > TOP_N:
        lines.append(f"  · 외 {len(items) - TOP_N}건")
    lines.append("")

    buckets = defaultdict(int)
    for it in items:
        if it["days"] <= 7:
            buckets["3~7일"] += 1
        elif it["days"] <= 14:
            buckets["8~14일"] += 1
        else:
            buckets["15일 이상"] += 1
    lines.append(
        "기다린 기간: "
        + " · ".join(f"{k} {buckets[k]}건" for k in ("3~7일", "8~14일", "15일 이상") if buckets[k])
    )
    lines.append("")
    lines.append("👉 배정하기 (화면이 갈려 있어 주소를 따로 드립니다)")
    lines.append(f"  · 강습: {ASSIGN_URL_LESSON}")
    lines.append(f"  · 멤버십: {ASSIGN_URL_MEMBERSHIP}")
    lines.append(f"  🔑 입장 코드 {ENTRY_CODE}")
    lines.append("   이름 옆 담당자 칸에서 고르시면 바로 반영됩니다.")
    lines.append("")
    lines.append("한 분씩만 맡아주셔도 금방 정리됩니다. 늘 감사합니다 🙏")
    return "\n".join(lines)


def send(text: str, chat_id: int) -> dict:
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "wellperion-agents"))
    from telegram_notifier import TelegramNotifier  # noqa: E402

    notifier = TelegramNotifier()
    # TelegramNotifier.send() 는 생성 시 잡힌 self.chat_id 로만 보낸다(방 인자 없음).
    # 방을 바꿔 보내려면 이 속성을 갈아끼우는 게 유일한 경로다.
    notifier.chat_id = str(chat_id)
    resp = notifier.send(text)
    return {"ok": bool(resp.get("ok")), "chat_id": chat_id, "resp": resp}


def main() -> int:
    p = argparse.ArgumentParser(description="문의 담당자 미배정 배정 독려 안내")
    p.add_argument("--send", action="store_true",
                   help="실제 발송(기본은 출력만 — 실무진 발송은 되돌릴 수 없다)")
    p.add_argument("--to", choices=("gm", "staff"), default="gm",
                   help="gm=GM 개인 봇방(기본) / staff=문의알림방 실무진")
    p.add_argument("--today", default=None, help="기준일(YYYY-MM-DD, 기본 오늘)")
    args = p.parse_args()

    text = build_message(args.today)
    chat_id = GM_CHAT_ID if args.to == "gm" else STAFF_CHAT_ID

    if not args.send:
        print(f"[dry-run] 발송 안 함 · 대상={args.to}({chat_id})")
        print("-" * 56)
        print(text)
        print("-" * 56)
        return 0

    result = send(text, chat_id)
    print(f"[발송] 대상={args.to}({chat_id}) ok={result['ok']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
