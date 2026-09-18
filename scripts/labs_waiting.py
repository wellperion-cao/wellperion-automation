#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""labs_waiting.py — 랩스가 기다리는 답 한 표 (GM 2026-09-17 「기다리지 않아도 확인할 수 있게 셋팅해줘, 랩스에서」).

시보가 채팅에 「기다리는 것 = …」이라 적던 것을 화면 한 표로 — 원천 파일을 읽어 status/labs_waiting.json 을 만들고
랩스 관리(erp/admin/index.html 파트너사 관리)가 그 표를 그린다. 사람이 손으로 적는 칸은 없다.

원천(정본은 각 파일 · 여기는 읽기만):
  파트너 설문 답     server/counselbot/tenants/{t}_qa.json (answer 빈 번호 · asked_on)
  인스타 임시안 답   status/partner_instagram/{c}.json (await_ok · published_at)
  GM 손 한 줄        status/gm_asks.json (role cbo · answered_at 빈 것)
  화면 지도 확인     status/screen_bins.json (bin=확인)
예약 = 07:20(partner_instagram_daily.bat) · 22:10(counsel_questions.bat) 끝에 한 줄. 손 실행:
  C:/Python314/python.exe scripts/labs_waiting.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "status" / "labs_waiting.json"
KST = timezone(timedelta(hours=9))
TENANTS = {"jo": ("3_gocheokgolf", "3호 고척 · 조재오 지점장님", 19), "dc": ("2_dietcamp", "2호 다캠 · 이승기 대표님", 20)}   # 번호 설문 시작 번호


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _days(since: str, now: datetime) -> int:
    try:
        d = datetime.fromisoformat(since[:19])
        return max(0, (now.replace(tzinfo=None) - d).days)
    except Exception:  # noqa: BLE001
        return 0


def survey_items(now: datetime) -> list[dict]:
    out = []
    for key, (tenant, who, floor) in TENANTS.items():
        qa = _load(ROOT / "server" / "counselbot" / "tenants" / f"{tenant}_qa.json", [])
        rows = [r for r in qa if (r.get("partner_no") or 0) >= floor and r.get("asked_on")]
        open_ = [r for r in rows if not (r.get("answer") or "").strip()]
        if not rows:
            continue
        asked = max((r.get("asked_on") or "") for r in rows)
        out.append({
            "who": who, "what": f"번호 설문 {len(rows)}문(카톡 한 통)", "since": asked, "via": "카톡 번호 질문",
            "state": "답 옴 — 전부 반영" if not open_ else f"답 없는 번호 {len(open_)}개 · {_days(asked, now)}일째",
            "detail": "" if not open_ else " · ".join(str(r["partner_no"]) for r in open_[:12]) + ("…" if len(open_) > 12 else ""),
            "then": "답 온 번호부터 사실 정본 → 화면 → 상담봇(같은 날)", "done": not open_,
        })
    return out


def instagram_items(now: datetime) -> list[dict]:
    out = []
    for key, (tenant, who, _) in TENANTS.items():
        st = _load(ROOT / "status" / "partner_instagram" / f"{key}.json", {})
        runs = [r for r in st.get("runs", []) if r.get("folder")]
        if not runs:
            continue
        r = runs[-1]
        # 2026-09-18 부터 파트너 승낙 없이 06:30 바로 게시(GM) — 기다리는 것은 「올려요」가 아니라 발행 세션(사람 손 1회)뿐
        done = bool(r.get("published_at"))
        if done:
            out.append({"who": who, "what": "인스타 자동 게시", "since": r.get("at", ""), "via": "—",
                        "state": "게시함 " + r["published_at"][:16], "detail": r.get("post_url") or Path(r["folder"]).name,
                        "then": "다음 날 06:30 자동", "done": True})
        elif not (ROOT / "profiles" / "instagram" / key).exists():
            out.append({"who": who, "what": "인스타 발행 세션(로그인 1회 · 사람 손)", "since": r.get("at", ""), "via": "—",
                        "state": "세션 없음 — 임시안만 쌓임", "detail": Path(r["folder"]).name, "then": "세션 뒤 06:30 자동 게시", "done": False})
        elif r.get("publish_rc") is not None:
            out.append({"who": who, "what": "인스타 자동 게시 실패(재시도 없음)", "since": r.get("at", ""), "via": "—",
                        "state": f"rc={r['publish_rc']} · 세션 만료면 재로그인 1회 뒤 --retry", "detail": Path(r["folder"]).name,
                        "then": "logs/partner_instagram_daily.log", "done": False})
    return out


def gm_items(now: datetime) -> list[dict]:
    out = []
    asks = _load(ROOT / "status" / "gm_asks.json", {}).get("asks", [])
    seen: set[str] = set()
    for a in asks:
        if a.get("role") == "cbo" and not a.get("answered_at"):
            t = a.get("title", "")
            if "101" in t and "296" in t:        # 화면 지도 확인 번호는 아래 screen_bins 줄이 정본
                continue
            k = "다캠세션" if "다캠 인스타" in t and "세션" in t else t[:10]   # 훅이 같은 👉 줄을 여러 번 모은 것 합침
            if k in seen:
                continue
            seen.add(k)
            out.append({"who": "GM 손", "what": a.get("title", ""), "since": a.get("at", ""), "via": "아침 한 줄(gm_asks)",
                        "state": f"{_days(a.get('at', ''), now)}일째", "detail": f"#{a.get('id')}", "then": "끝나면 시보에게 「됐다」", "done": False})
    bins = _load(ROOT / "status" / "screen_bins.json", {}).get("bins", {})
    chk = sorted((v for v in bins.values() if v.get("bin") == "확인"), key=lambda v: v.get("no", 0))
    if chk:
        out.append({"who": "GM 답", "what": "화면 지도 1차 분류 「확인」 번호 답", "since": "2026-09-17T15:28", "via": "채팅 번호",
                    "state": f"{len(chk)}건 대기", "detail": " · ".join(f"{v['no']} {v.get('title', '')[:14]}" for v in chk),
                    "then": "screen_bins OVERRIDES 에 박고 화면 지도 갱신", "done": False})
    out.append({"who": "GM 답", "what": "랩스 요금표 ① 99,000/199,000 ② v2 149,000/249,000+셋업 300,000", "since": "2026-09-16T17:00", "via": "로드맵 §9 결정 2",
                "state": f"{_days('2026-09-16T17:00', now)}일째", "detail": "소개서엔 금액 뺀 채", "then": "소개서 §5 · 로드맵 §5 숫자 확정", "done": False})
    return out


def build() -> dict:
    now = datetime.now(KST)
    items = survey_items(now) + instagram_items(now) + gm_items(now)
    return {"_about": "랩스가 기다리는 답 — scripts/labs_waiting.py 가 원천 파일에서 만든다. 손으로 고치지 않는다.",
            "generated_at": now.isoformat(timespec="seconds"), "open": sum(1 for i in items if not i["done"]), "items": items}


if __name__ == "__main__":
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"labs_waiting {d['open']} 열림 / {len(d['items'])}건 → {OUT.name}")
    for i in d["items"]:
        print(("  ✔ " if i["done"] else "  ⏳ ") + i["who"] + " | " + i["what"] + " | " + i["state"])
