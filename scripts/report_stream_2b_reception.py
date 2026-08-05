# -*- coding: utf-8 -*-
"""[스트림 #2b] 종합접수 현황 + 미처리 적체 리마인드 — 프로덕션 (CTO 2026-07-22).

GM 2026-07-22 지시: 배9424(2026-07-21)의 '종합접수 현황 → 점검현황방 병합'을 되돌림.
종합접수(VOC 6종: 분실물·시설물고장·청결·칭찬·쓴소리·컴플레인)는 점검(시설·지원·주차)과
분리해 별도 종합접수방으로 단독 발송한다. 점검 현황은 scripts/report_stream_2_check.py 참조.

통일 포맷 [하루 일과 정리]:
  ① 오늘 신규 접수 요약
  ━━━━━━━━━━
  ② 미처리 적체 리마인드 — 카테고리별 SLA(apps_script_voc.js REG_CATEGORIES가 SSOT)를
     넘긴 미처리 건을 담당자별로 묶어 매일 밤 상기(GM 신설 지시). 방치된 접수건이
     하루하루 다이제스트에 묻히지 않도록 '오늘 신규'와 별개로 매번 재노출한다 — 의도적
     크로스데이 억제 없음(리마인드 목적상 반복 노출이 맞다). 칭찬(slaHours=null)은
     SLA 개념이 없어 적체 집계에서 제외.

  ※ 2026-07-27 웰리 정정: 커밋 c33a79ac7에서 이 블록을 GAS reg_sla_check(전환 즉시
     통지)로의 이관을 이유로 제거했으나, 전환 알림이 **라이브 배포되어 실제 발신이
     확인된 뒤에만** 이 블록을 제거한다 — 대체가 살아있기 전에 원본을 지워 공백이
     생겼다(그날 밤부터 SLA 초과를 알려주는 경로가 전무). 복구.

텔레그램: 종합접수방(TELEGRAM_RECEPTION_CHAT_ID, -5065206276) 단일 발송.
발사 시각: 매일 22:30 (daily_scheduler.py run_daily_digest 경유) / 독립 실행 가능.
카카오톡: 이 모듈 자체는 텔레그램만 다룬다(build_digest만 노출). ★운영+시설+지원+주차 방
발송은 daily_scheduler.py run_daily_digest()가 이 모듈의 build_digest() 결과를 그대로
재사용해 처리한다(점검현황과 별도 메시지로 분리 — GM 2026-07-22 go, KAKAO_GO_STREAM2 게이트).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from collectors.ops_shared import RECEPTION_EXEC_URL, gas_get, reception_elapsed_days  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402
from tg_outbound_log import send as tg_send  # noqa: E402

TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_RECEPTION_CHAT_ID") or -5065206276)  # 종합접수방
DASHBOARD_URL = "https://wellperion-cao.github.io/wellperion-automation/coo/reception/종합접수처_현황.html"
_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]
_DIVIDER = "━" * 10

# 카테고리(reg_list의 category=한글 라벨) → SLA 시간. SSOT=coo/reception/apps_script_reception.js
# REG_CATEGORIES(:38-43). 보드·다른 소비자에 하드코딩 복사 금지 원칙과 동일하게 이 표는
# GAS 응답 라벨 그대로를 키로 쓴다(코드 재구현 없이 라벨 정확일치). None=SLA 없음(집계 제외).
_SLA_HOURS: dict[str, int | None] = {
    "분실물 접수": 720,  # 30일 — GM 확정 2026-07-28(구 168h/7일). 사유=apps_script_reception.js 주석
    "시설물 고장 접수": 24,
    "청결 이슈 접수": 12,
    "직원·강사 칭찬합니다": None,
    "직원·강사 쓴소리합니다": 72,
    "컴플레인 접수": 48,
}


def _fetch_rows() -> list[dict] | None:
    resp = gas_get(RECEPTION_EXEC_URL, {"action": "reg_list"}, timeout=20, label="stream2b-reception")
    if resp is None:
        return None
    try:
        data = resp.json()
        return data.get("data", []) if data.get("ok") else None
    except Exception:
        return None


def _parse_created(s) -> datetime | None:
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _today_section(rows: list[dict], today: str) -> str:
    """오늘 신규 접수 요약(카테고리별 건수 + 미처리)."""
    today_rows = [r for r in rows if str(r.get("createdAt", "")).startswith(today)]
    if not today_rows:
        return "📮 오늘 신규 접수 없음."
    cat_cnt: dict[str, int] = {}
    undone_today = 0
    for r in today_rows:
        cat = str(r.get("category") or "기타").strip()
        cat_cnt[cat] = cat_cnt.get(cat, 0) + 1
        if str(r.get("status", "")) != "완료":
            undone_today += 1
    cat_str = " · ".join(f"{c}:{n}" for c, n in sorted(cat_cnt.items(), key=lambda x: -x[1]))
    return f"📮 오늘 신규 접수 {len(today_rows)}건 (미처리 {undone_today}건)  {cat_str}"


def _fmt_age(days: int, elapsed_h: float) -> str:
    # ★일수는 reception_elapsed_days(정본=ops_shared) 그대로 씀 — 여기서 elapsed_h/24로
    # 다시 계산하면 소수점(28.8일)이 나와 ops_daily_digest의 정수 "N일째"와 갈라진다
    # (GM 2026-08-05 실측 지적, 약속 L01). 만 하루 미만만 시간 단위로 보여준다.
    return f"{days}일" if days >= 1 else f"{elapsed_h:.1f}시간"


def _aging_block(rows: list[dict], now: datetime | None = None) -> str:
    """기한(SLA) 넘긴 미처리 건 — 담당자별 그룹(미배정 별도) + 오래된 순 상세."""
    now = now or datetime.now()
    undone = [r for r in rows if str(r.get("status", "")) != "완료"]

    overdue: list[dict] = []
    for r in undone:
        cat = str(r.get("category") or "").strip()
        sla = _SLA_HOURS.get(cat)
        if sla is None:  # 칭찬 등 SLA 없음 — 적체 집계 제외
            continue
        created = _parse_created(r.get("createdAt"))
        if created is None:
            continue
        elapsed_h = (now - created).total_seconds() / 3600.0
        if elapsed_h > sla:
            overdue.append({
                "regId": str(r.get("regId") or ""),
                "cat": cat,
                # 서버가 통일해 준 담당자 표기를 그대로 쓴다(2026-07-31 웰리).
                # ★여기서 이름을 다시 판정하지 않는다 — 규칙이 두 벌이 되면 또 갈라진다(약속 L01).
                #   서버가 아직 그 값을 안 주면(옛 배포) 원문으로 떨어져 지금 동작을 유지한다.
                "owners": [str(x).strip() for x in (r.get("assigneeCanon") or []) if str(x).strip()]
                          or ([str(r.get("assignee") or "").strip()] if str(r.get("assignee") or "").strip() else []),
                "content": " ".join(str(r.get("content") or "").split())[:28],  # 개행 제거 — 1건 1줄 유지
                "elapsed_h": elapsed_h,
                "days": reception_elapsed_days(r, now),  # 표시용 "N일째" 정본(SLA 판정은 elapsed_h 유지)
                "sla": sla,
            })

    lines = ["⏰ 미처리 적체 리마인드", f"미처리 {len(undone)}건 · 기한초과 {len(overdue)}건"]
    if not overdue:
        lines.append("기한 초과 건 없음.")
        return "\n".join(lines)

    def _fmt_item(it: dict) -> str:
        ratio = it["elapsed_h"] / it["sla"] if it["sla"] else 0.0
        flag = "🔴" if ratio >= 3 else "⚠️"
        return f"  {flag} [{it['cat']}] {it['content']} — {_fmt_age(it['days'], it['elapsed_h'])} 경과 ({it['regId']})"

    # 한 건에 담당이 둘이면 양쪽 목록에 모두 띄운다 — 그 전엔 '이경연/ 임정은' 이 제3의
    # 사람처럼 잡혀 두 사람 어느 쪽 목록에도 안 떴다(2026-07-31 실측).
    by_owner: dict[str, list[dict]] = {}
    for it in overdue:
        for owner in (it["owners"] or ["미배정"]):
            by_owner.setdefault(owner, []).append(it)

    # 미배정을 맨 위(별도 표기)로 두고, 이후 담당자는 최고령 건 기준 오래된 순.
    if "미배정" in by_owner:
        items = sorted(by_owner.pop("미배정"), key=lambda x: -x["elapsed_h"])
        lines.append(f"\n👤 미배정 ({len(items)}건)")
        for it in items:
            lines.append(_fmt_item(it))

    for owner in sorted(by_owner, key=lambda o: -max(i["elapsed_h"] for i in by_owner[o])):
        items = sorted(by_owner[owner], key=lambda x: -x["elapsed_h"])
        lines.append(f"\n👤 {owner} ({len(items)}건)")
        for it in items:
            lines.append(_fmt_item(it))

    lines.append(f"\n👉 상세: {DASHBOARD_URL}")
    return "\n".join(lines)


def _score_block() -> str:
    """🏆 이번 주 점수판 — 접수 1점 + 처리 완료 1점 (GM 지시 2026-07-28).

    왜 여기에 붙나: 접수한 사람이 곧 처리까지 떠안는 구조라 '적을수록 손해'가 되어
    아예 안 적게 된다. 적는 행위 자체에 점수를 붙이고, 그걸 같이 보며 칭찬한다.
    ▸새 발송·새 예약을 만들지 않는다(약속 L21) — 이미 매일 밤 같은 방으로 나가는
      이 메시지 끝에 얹는다. 알림이 하나 더 늘면 그만큼 안 읽힌다.
    ▸셈법은 서버(reg_scoreboard) 한 곳뿐 — 여기서 다시 세지 않는다. 화면과 이 발표의
      숫자가 갈라지면 아무도 점수를 안 믿는다.
    """
    resp = gas_get(RECEPTION_EXEC_URL, {"action": "reg_scoreboard", "period": "week"},
                   timeout=20, label="stream2b-score")
    if resp is None:
        return ""
    try:
        data = resp.json()
        board = data.get("board", []) if data.get("ok") else []
    except Exception:
        return ""
    if not board:
        return (f"{_DIVIDER}\n🏆 이번 주 점수판 (접수 1점 + 완료 1점)\n\n"
                "아직 점수가 없습니다. 접수하시거나 처리를 끝내시면 쌓입니다.")

    lines = [_DIVIDER, "🏆 이번 주 점수판 (접수 1점 + 완료 1점)", ""]
    top = board[0]["total"]
    for x in board[:5]:
        mark = "🎉" if x["total"] == top else "▪"
        lines.append(f"{mark} {x['rank']}위 {x['name']} — {x['total']}점")
        lines.append(f"   접수 {x['intake']} · 완료 {x['done']}")
    winners = [x["name"] for x in board if x["total"] == top]
    lines.append("")
    lines.append(f"🎊 {' · '.join(winners)}님 수고하셨습니다! 이번 주 1위입니다 🎊")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# 부서 톡방 처리완료 통보(2026-08-01 GM 지시) — 개인 회신이 아니라 부서 단위로.
# GM: "접수한 사람으로 하는것보단, 톡방(부서 단위)으로 하는게 좋을 것 같아" — 접수자가
# 익명 회원인 접수도 많아 개인 회신 자체가 불가능하고, 처리도 팀 단위로 움직인다.
# 새 방·새 발신 경로를 만들지 않는다(약속 L21) — 이 다이제스트 본문에 블록 하나만 얹어
# 기존 배선(텔레그램 종합접수처방 + kakao-ops-stream2가 재사용하는 ★운영+시설+지원+주차
# 카톡방)을 그대로 탄다. 킬스위치=status/dept_completion_notify.json{"enabled":false}
# (기본 꺼짐 — GM go 전 실무진·부서 방 노출 금지). 완료건에 처리시각 칸이 없어(시트에
# completedAt 없음) "며칠 전 완료"를 못 구하는 대신, 직전 발신 이후 새로 status='완료'가
# 된 건만 골라 부서별로 묶는다(멱등 커서=reception_seen_done_ids, 매 실행 갱신) — 그래서
# 한 번에 최대 _COMPLETION_CAP건만 보이고 나머지는 "…외 N건"으로 접는다(폭주 방지).
# ══════════════════════════════════════════════════════════════════════════
COMPLETION_STATE_PATH = REPO_ROOT / "status" / "dept_completion_notify.json"
_COMPLETION_CAP = 6  # 한 회차 최대 노출 건수(10줄 예산 안)


def _load_completion_state() -> dict:
    try:
        if COMPLETION_STATE_PATH.exists():
            return json.loads(COMPLETION_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"enabled": False, "reception_seen_done_ids": [], "inquiry_seen_keys": []}


# ★2026-08-05 시토 — 커서를 '보낸 뒤에' 파일에 쓴다.
#   전에는 _completion_block 이 문구를 만드는 그 자리에서 곧바로 파일에 커서를 적었다.
#   그런데 발송은 그 다음 단계라, 텔레그램이 실패하면(토큰 만료·429·방 권한 등) 아무 방에도
#   안 갔는데 커서만 전진해 있었다 — 그 완료건들은 다음 날에도 '이미 통보함'으로 걸러져
#   영영 통보되지 않는다. 조용히 사라지는 종류의 사고라 아무도 모른다.
#   그래서 문구를 만들 때는 메모리의 state 만 갱신해 두고(같은 실행 안에서의 멱등은 그대로),
#   실제 파일 쓰기는 발송 성공을 확인한 호출자가 commit_completion_cursor() 로 한 번 한다.
#   발송이 실패하면 커서가 안 움직이므로 다음 회차에 다시 통보된다(잃는 것보다 겹치는 게 낫다).
_pending_state: dict | None = None


def commit_completion_cursor() -> bool:
    """처리완료 통보가 실제로 나간 뒤 호출 — 대기 중인 커서를 파일에 확정한다.
    대기분이 없으면 아무것도 하지 않고 False."""
    global _pending_state
    if _pending_state is None:
        return False
    _save_completion_state(_pending_state)
    _pending_state = None
    return True


def _save_completion_state(state: dict) -> None:
    try:
        COMPLETION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMPLETION_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _completion_block(rows: list[dict], state: dict | None = None, persist: bool = True) -> str:
    """새로 완료된 종합접수 건을 부서별로 묶어 알림 블록으로 렌더. state 미지정 시 파일에서
    읽는다. persist=False면 커서를 갱신하지 않는다(검증·시뮬레이션에서 반복 실행해도 같은
    결과가 나와야 하므로 — 실제 22:30 다이제스트 발신 시에만 persist=True로 커서를 전진)."""
    state = state if state is not None else _load_completion_state()
    if not state.get("enabled"):
        return ""
    seen = set(state.get("reception_seen_done_ids") or [])
    done_now = [r for r in rows if str(r.get("status", "")) == "완료" and str(r.get("regId") or "")]
    new_done = [r for r in done_now if str(r["regId"]) not in seen]
    if persist:
        global _pending_state
        state["reception_seen_done_ids"] = sorted({str(r["regId"]) for r in done_now})
        _pending_state = state   # 파일 확정은 발송 성공 뒤 commit_completion_cursor()
    if not new_done:
        return ""

    remain_by_dept: dict[str, int] = {}
    for r in rows:
        if str(r.get("status", "")) != "완료":
            dept = str(r.get("dept") or "기타").strip() or "기타"
            remain_by_dept[dept] = remain_by_dept.get(dept, 0) + 1

    def _fmt(r: dict) -> str:
        dept = str(r.get("dept") or "기타").strip() or "기타"
        cat = str(r.get("category") or "").strip()
        content = " ".join(str(r.get("content") or "").split())[:24]
        # 서버가 통일해 준 표기(handlerCanon/assigneeCanon)를 쓴다(2026-08-01) — 원문을 여기서
        # 다시 판정하면 '최준용'/'최준용M' 이 또 갈라진다(약속 L01, _aging_block과 동일 원칙).
        # 서버가 아직 그 값을 안 주면(옛 배포) 원문으로 떨어져 지금 동작을 유지한다.
        who_list = ([str(x).strip() for x in (r.get("handlerCanon") or []) if str(x).strip()]
                    or [str(x).strip() for x in (r.get("assigneeCanon") or []) if str(x).strip()])
        who = "/".join(who_list) if who_list else (
            str(r.get("handler") or r.get("assignee") or "").strip() or "담당")
        remain = remain_by_dept.get(dept, 0)
        return f"✅ [{dept}] {cat} {content} · 처리 {who} · 남은 미처리 {remain}건"

    shown = new_done[:_COMPLETION_CAP]
    lines = [f"{_DIVIDER}\n✅ 처리 완료 알림 {len(new_done)}건"]
    lines += [_fmt(r) for r in shown]
    if len(new_done) > _COMPLETION_CAP:
        lines.append(f"  …외 {len(new_done) - _COMPLETION_CAP}건 더")
    return "\n".join(lines)


def build_digest(today: str | None = None, persist_completion: bool = True) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    # 보낸이를 밝힌다(2026-07-31 GM 지시 "웰리가 보냈다는 것도 인지시켜야 하고").
    # 실무진 방에 뜨는 메시지가 누가 보낸 것인지 모르면 답할 곳도 모른다.
    header = (f"📊 [하루 일과 정리] {today}({weekday})\n📮 종합접수 현황\n"
              "— 웰페리온 AI 운영지원 '웰리'가 정리해 보내드립니다.")
    rows = _fetch_rows()
    if rows is None:
        return f"{header}\n\n조회 실패 (GAS 응답 없음)"
    # 2026-07-31 GM 지시 — 점수판을 맨 위로 올린다.
    #   "점수 랭킹하는 걸 상단에 알림으로 올려주고, 더 활성화될 수 있게."
    #   맨 아래에 있으면 스크롤 끝까지 내려야 보인다 = 사실상 없는 것과 같았다. 접수를 피할
    #   이유를 없애려고 만든 장치라, 방을 열자마자 눈에 들어와야 제 일을 한다.
    score = _score_block()
    parts = [header]
    if score:
        parts.append(score.lstrip("\n").removeprefix(_DIVIDER).strip())
    parts.append(f"{_DIVIDER}\n{_today_section(rows, today)}")
    parts.append(f"{_DIVIDER}\n{_aging_block(rows)}")
    completion = _completion_block(rows, persist=persist_completion)
    if completion:
        parts.append(completion)
    return "\n\n".join(parts)


def seed_completion_cursor() -> int:
    """처리완료 통보를 켜기(enabled:true) 직전 1회 실행 — 지금 이미 '완료'인 건 전부를
    커서에 채워 넣어, 켜는 첫 회차에 오래된 완료건(현재 실측 43건)이 한꺼번에 '신규
    완료'로 통보되는 것을 막는다(활성화 당일 백로그 통보 방지 — 진짜 새 완료건만
    그 다음부터 나간다). enabled 값 자체는 건드리지 않는다(그건 GM go 별도 승인)."""
    rows = _fetch_rows() or []
    state = _load_completion_state()
    done_ids = {str(r["regId"]) for r in rows
                if str(r.get("status", "")) == "완료" and str(r.get("regId") or "")}
    state["reception_seen_done_ids"] = sorted(done_ids)
    _save_completion_state(state)
    return len(done_ids)


def run(today: str | None = None, dry_run: bool = True) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    text = build_digest(today, persist_completion=not dry_run)
    if dry_run:
        print(f"[stream2b] DRY-RUN — chat_id={TELEGRAM_CHAT_ID} 발송 안 함", flush=True)
        return text
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[stream2b] TELEGRAM_BOT_TOKEN 미설정", flush=True)
        return text
    # 전역 페이싱·429 재시도·로깅 = tg_outbound_log.send() 경유(플러드 방어, 개별 requests 금지).
    ok = tg_send(token, TELEGRAM_CHAT_ID, text, source="report_stream_2b_reception")
    print(f"[stream2b] 텔레그램 {'완료' if ok else '실패'} → {TELEGRAM_CHAT_ID}", flush=True)
    if ok:
        commit_completion_cursor()   # 실제로 나간 뒤에만 커서 전진(실패 시 다음 회차 재통보)
    return text


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="스트림 #2b 종합접수 현황+미처리 적체 리마인드 보고")
    p.add_argument("--live", action="store_true", help="실발송")
    p.add_argument("--today", default=None, help="날짜 YYYY-MM-DD (기본=오늘)")
    p.add_argument("--seed-completion", action="store_true",
                    help="처리완료 통보 커서 시딩(enabled:true 켜기 직전 1회 — 백로그 통보 방지)")
    a = p.parse_args()
    if a.seed_completion:
        n = seed_completion_cursor()
        print(f"[stream2b] 완료 커서 시딩 완료 — 현재 완료 {n}건을 '이미 통보됨'으로 표시")
        sys.exit(0)
    result = run(today=a.today, dry_run=not a.live)
    print("\n=== 렌더 ===")
    print(result)
