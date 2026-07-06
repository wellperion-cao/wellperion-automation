#!/usr/bin/env python3
"""일일 북극성 추천기 — 1단계: 두뇌 드라이런 엔진 (northstar_recommender.py)

매일(2단계에서 06:30) 전 C-Level의 **북극성(목표)** 대비 현재 위치를 읽어,
북극성↔오늘을 잇는 과정(브릿지)을 밟게 하는 **'오늘의 다음 한 수' — 웰리 단일 추천 1개**를 제안한다.

설계 정본:
  - 스펙   : .omc/specs/deep-interview-daily-northstar-recommender.md
  - 설계서 : status/briefs/CTO-2026-06-29-NORTHSTAR-RECOMMENDER-DESIGN.md
  - 배     : status/_queue.json  CTO-2026-06-29-NORTHSTAR-RECOMMENDER (ship 213)

GM 잠금 결정(2026-06-29):
  - G1: 상태 파일 = status/northstar_pending.json (git 추적)
  - G2: 미승인 추천 = 다음날 새 추천 생성 시 자동 보류(만료)
  - G3: 대상 = 처음부터 전 C-Level(7역할 ceo·cmo·coo·cto·cpo·cfo·chro, gm 제외).
        웰리가 7역할 가로질러 웰리 단일 추천 1개 선정 + 해당 후보에 역할·북극성 태그.
        ※ G3 대상범위 수정(2026-07-03 GM): cfo·chro 는 나우열M 실무 담당 도메인이라
          AI 항로 배 대상이 아님 → top3 후보 선정 대상에서 제외. 남는 대상 = ceo·cmo·coo·cto·cpo(5역할).
          상세 = .omc/specs/deep-interview-daily-northstar-recommender.md G3.

두뇌(웰리 추천 로직):
  - 1순위: claude CLI (model_router 폴백 경유 — ai_learning_proposer 와 동일 결, API 크레딧 0)
  - 2순위: 규칙기반 폴백 — CLI 불가 시 최소동작 보장(신호 기반 후보 생성)
  [규칙] 신호 3종: ①북극성 갭 ②KPI 미달 ③다음 한 걸음. 우선순위=북극성 직접기여 > KPI 시급 > 브릿지 연속성.
         중복방지(_queue active 배 제외), 웰리 단일 추천 1개(RECOMMEND_COUNT).

★ 1단계 안전 원칙 (라이브 부작용 0):
  - 입력 수집 + 두뇌 호출 + status/northstar_pending.json 쓰기 + 콘솔 출력만.
  - 텔레그램 전송 없음. Task Scheduler 등록 없음. 봇 핸들러 변경 없음. (전부 2단계)

사용법:
  python scripts/northstar_recommender.py            # 드라이런(기본): 콘솔 출력 + northstar_pending.json 기록
  python scripts/northstar_recommender.py --stdout-only   # 파일 기록 없이 콘솔만
  python scripts/northstar_recommender.py --send     # 2단계 라이브: G2 만료 + 기록 + 텔레그램 카드 발송 + 폐루프 로그 (06:30 예약 진입점)

2단계(2026-06-29 라이브):
  - GM 보강: 후보별 3줄 브릿지(🌟 북극성 → 📍 지금 → 👉 오늘 한 수)를 path_map 에 담고
             northstar·progress 필드도 함께 저장(2b 추적용).
  - 06:30 Task Scheduler → launchers/northstar_recommender.vbs → scripts/northstar_recommender.bat → --send
  - 카드 [승인]/[보류] 회신 → telegram_bot/bot.py 가 _queue.json PENDING 배 등록 + pending status 갱신.
  - G2: 새 추천 생성 시 이전 'proposed' 미승인 건 자동 만료(expired) — northstar_log.jsonl 기록.
"""
from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
MATRIX_FILE = BASE_DIR / "3. 웰페리온 가이드" / "coo" / "bootsetup_matrix.json"
QUEUE_FILE = BASE_DIR / "status" / "_queue.json"
KPI_FILE = BASE_DIR / "status" / "kpi_values.json"
PENDING_FILE = BASE_DIR / "status" / "northstar_pending.json"
LOG_FILE = BASE_DIR / "status" / "northstar_log.jsonl"
ENV_FILE = BASE_DIR / "telegram_bot" / ".env"  # 텔레그램 토큰·챗ID 단일출처(INC-004)

# ── 대상 역할 (gm 제외) ──
# 2026-07-03 GM 결정: cfo·chro 는 나우열M 실무 담당 도메인 — top3 후보 선정 대상에서 제외.
# 남는 대상 = ceo·cmo·coo·cto·cpo (5역할). 상세 = .omc/specs/deep-interview-daily-northstar-recommender.md G3.
TARGET_ROLES = ["ceo", "cmo", "coo", "cto", "cpo"]

RECOMMEND_COUNT = 1  # 웰리 단일 추천(2026-07-06 GM). 후보 수 = 이 값 하나로 조절

# ── 역할 닉네임 (카드 1줄 표기용) ──
ROLE_NICK = {
    "ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
    "coo": "시우", "cpo": "시포", "cto": "시토",
}

# ── 웹 풀표 페이지 (Pages 발행루트=가이드폴더 → URL 접두사 없음·ASCII) ──
# 2026-07-03(AI CTO): 구 northstar_today.html 은 자율현황.html 상단 "🧭 오늘의 항로 top3" 라이브 섹션으로
# 병합·흡수(중복정리). 카드 하단 링크도 자율현황.html 로 교체. 구 URL은 meta refresh 리다이렉트 스텁으로 안전 유지.
# 본 스크립트는 06:30 Task Scheduler가 매회 새 프로세스로 실행 → 다음 실행부터 즉시 반영(봇 재기동 불필요).
NORTHSTAR_WEB_URL = "https://wellperion-cao.github.io/wellperion-automation/%EC%9E%90%EC%9C%A8%ED%98%84%ED%99%A9.html"

# ── 난이도 배 ──
DIFFICULTY_BOATS = ["⛵돛단배", "⛴️여객선", "🛳️크루즈"]
ACTIVE_STATUSES = ("PENDING", "IN_PROGRESS")
# 중요건 필터(GM 확정 2026-07-04 ③): 이 난이도이거나 신호①/②면 '중요'. ⛵ low·단순 노이즈 컷.
IMPORTANT_BOATS = ("🛳️크루즈", "⛴️여객선")

# ── 공유 모듈 매퍼 (배→북극성 모듈 단일 소스 — 재구축 금지) ──
try:
    import voyage_module_map as vmm  # same scripts/ 디렉터리
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import voyage_module_map as vmm


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ═══════════════════════════════════════════
#  입력 수집
# ═══════════════════════════════════════════
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] 로드 실패 {path.name}: {type(e).__name__}: {e}")
        return default


def collect_inputs() -> dict:
    """matrix(7 C-Level 북극성/KPI/owns/ideas) + _queue(active·next) + kpi_values 수집."""
    matrix = load_json(MATRIX_FILE, {"roles": []})
    queue = load_json(QUEUE_FILE, [])
    kpi = load_json(KPI_FILE, {"roles": {}})

    roles_by_id = {r.get("id"): r for r in matrix.get("roles", [])}
    kpi_roles = kpi.get("roles", {}) if isinstance(kpi, dict) else {}

    # _queue 를 역할별로 분류
    active_by_role: dict[str, list] = {r: [] for r in TARGET_ROLES}
    next_by_role: dict[str, list] = {r: [] for r in TARGET_ROLES}
    if isinstance(queue, list):
        for ship in queue:
            role = (ship.get("clevel") or "").lower()
            if role not in active_by_role:
                continue
            if ship.get("status") in ACTIVE_STATUSES:
                active_by_role[role].append({
                    "title": ship.get("title", ""),
                    "status": ship.get("status", ""),
                    "ship_no": ship.get("ship_no"),
                })
            nxt = (ship.get("next") or "").strip()
            if nxt:
                next_by_role[role].append(nxt)

    roles_data = []
    for rid in TARGET_ROLES:
        r = roles_by_id.get(rid, {})
        dims = r.get("dims", []) if isinstance(r, dict) else []
        roles_data.append({
            "id": rid,
            "name": r.get("name", rid),
            "title": r.get("title", rid),
            "northstar": dims[0] if len(dims) > 0 else "",
            "kpi_def": dims[3] if len(dims) > 3 else "",
            "owns": [o.get("label", "") for o in r.get("owns", []) if isinstance(o, dict)],
            "ideas": r.get("ideas", ""),
            "kpi_values": kpi_roles.get(rid, {}),
            "active_ships": active_by_role.get(rid, []),
            "next_steps": next_by_role.get(rid, []),
        })

    return {
        "roles": roles_data,
        "matrix_updated_at": matrix.get("updated_at", "?"),
        "kpi_generated_at": kpi.get("generated_at", "?") if isinstance(kpi, dict) else "?",
    }


# ═══════════════════════════════════════════
#  두뇌 ① — claude CLI (model_router 폴백)
# ═══════════════════════════════════════════
def _build_prompt(inputs: dict) -> str:
    lines = []
    for r in inputs["roles"]:
        kv = r["kpi_values"]
        kv_str = ", ".join(f"{k}={v}" for k, v in kv.items() if not k.startswith("_")) or "(집계없음)"
        active = "; ".join(f"#{s['ship_no']} {s['title'][:40]}" for s in r["active_ships"]) or "(없음)"
        nexts = " / ".join(n[:70] for n in r["next_steps"][:3]) or "(없음)"
        lines.append(
            f"\n■ [{r['id']}] {r['title']}({r['name']})\n"
            f"  · 북극성: {r['northstar'][:200]}\n"
            f"  · KPI 정의: {r['kpi_def'][:160]}\n"
            f"  · KPI 현재치: {kv_str}\n"
            f"  · 소유(owns): {', '.join(r['owns']) or '(없음)'}\n"
            f"  · 확장아이디어(ideas): {r['ideas'][:120] or '(없음)'}\n"
            f"  · 현재 진행중 배(active·중복금지): {active}\n"
            f"  · 완료건 다음 한 걸음(next): {nexts}"
        )
    roles_block = "\n".join(lines)

    role_list_str = "/".join(TARGET_ROLES)
    nick_map_str = ", ".join(f"{rid}={ROLE_NICK.get(rid, rid.upper())}" for rid in TARGET_ROLES)

    return f"""당신은 웰페리온(하이엔드 스포츠클럽 멤버십 커뮤니티) AI CEO '웰리'입니다.
당신의 본업은 C-Level을 가로질러 전사를 북극성으로 이끄는 오케스트레이션입니다.

아래는 대상 C-Level({role_list_str})의 북극성·KPI·소유·진행상황 현황입니다:
---{roles_block}
---

위 현황을 바탕으로, 각 C-Level이 '북극성'으로 나아가는 **최상급 과정(브릿지)**을 밟게 하는
**'오늘의 다음 한 수'를 전사 관점에서 단 1개**(웰리가 북극성에 가장 맞는 '오늘의 한 수' 하나만 스스로 선정) 선정하세요.

[추천 규칙]
- 신호 3종 중 가장 적합한 근거로: ①북극성 갭(북극성 서술 대비 비어있는 다음 걸음·owns/ideas 참고) ②KPI 미달(KPI 현재치가 목표·정의 밑) ③다음 한 걸음(완료건 next 중 미착수).
- 우선순위 가중: 북극성 직접기여 > KPI 미달 시급 > 브릿지 연속성.
- 중복방지: 이미 active 인 배와 겹치는 추천 금지.
- 대상 역할({role_list_str}) 전체에서 **가장 가치 높은 단 하나**만(웰리의 판단으로 결정).
- **반드시 1순위 하나를 명확히 고르고** rank=1로 표시한 뒤, 왜 1순위인지 one_reason에 한 줄로 적는다.

닉네임 매핑(owner 필드에 사용): {nick_map_str}.

후보 1개만 담은 JSON 배열로 응답하세요 (설명문·마크다운·코드블록 없이 순수 JSON만):
[
  {{
    "rank": 1,
    "role": "cmo",
    "owner": "시모",
    "title": "오늘의 한 수 (한 줄, 구체적·실행가능)",
    "first_action": "승인 직후 담당이 바로 할 첫 행동 1줄",
    "expected": "예상 산출·효과 1줄 (구체 수치 또는 결과물)",
    "path_map": "북극성 → [브릿지 단계들] → 지금 여기 → 오늘 이 한 수",
    "rationale": "근거 — 어느 신호(①/②/③)·어느 갭/지표인지 명시",
    "one_reason": "왜 이게 1순위인지 한 줄(rank=1만 필수, 2·3은 빈칸 가능)",
    "difficulty": "⛵돛단배 또는 ⛴️여객선 또는 🛳️크루즈",
    "signal": "신호① 또는 신호② 또는 신호③"
  }}
]

규칙:
- rank 는 1 (단일 추천이므로 항상 1)
- role 은 반드시 {role_list_str} 중 하나
- owner 는 위 닉네임 매핑 그대로
- difficulty 는 반드시 ⛵돛단배/⛴️여객선/🛳️크루즈 중 하나
- 정확히 1개. 순수 JSON 배열만 출력(```json 코드블록도 없이)."""


def brain_claude_cli(inputs: dict) -> list | None:
    """claude CLI(model_router 폴백)로 웰리 단일 추천 1개 후보 생성. 실패 시 None."""
    prompt = _build_prompt(inputs)
    try:
        from model_router import run_claude  # same scripts/ 디렉터리
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from model_router import run_claude

    raw, used_model = run_claude(prompt, label="northstar-recommender")
    if raw is None:
        print("[WARN] 전 모델 폴백 실패 — 규칙기반 폴백")
        return None
    try:
        raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        cands = json.loads(raw)
        if not isinstance(cands, list) or not cands:
            raise ValueError("응답이 비어있거나 배열이 아님")
        print(f"[INFO] 추천 생성 모델 = {used_model}")
        return cands
    except json.JSONDecodeError as e:
        print(f"[WARN] LLM 응답 JSON 파싱 실패(model={used_model}): {e} — 규칙기반 폴백")
        return None
    except Exception as e:
        print(f"[WARN] 후보 파싱 중 예외: {type(e).__name__}: {e} — 규칙기반 폴백")
        return None


# ═══════════════════════════════════════════
#  두뇌 ② — 규칙기반 폴백 (claude CLI 불가 시 최소동작)
# ═══════════════════════════════════════════
def _kpi_gap_roles(inputs: dict) -> list:
    """완결률 낮은(또는 활성 많은데 완료 0) 역할을 신호② 후보로."""
    scored = []
    for r in inputs["roles"]:
        kv = r["kpi_values"]
        wan = kv.get("완결률")
        active = kv.get("활성", 0) or 0
        done = kv.get("완료", 0) or 0
        # 미달 점수: 활성 있는데 완결률 낮을수록 높음
        if active and (wan is None or wan < 0.5):
            scored.append((active - done, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored]


def brain_fallback(inputs: dict) -> list:
    """규칙기반 — 신호 3종으로 서로 다른 역할 후보 3개 생성(최소동작 보장).
    rank 우선순위: 신호①(북극성 갭)=1 > 신호②(KPI 미달)=2 > 신호③(다음 한 걸음)=3."""
    sig1: dict | None = None  # 북극성 갭 — rank 1
    sig2: dict | None = None  # KPI 미달 — rank 2
    sig3: dict | None = None  # 완료건 next 미착수 — rank 3
    used_roles: set = set()

    # 신호① — 북극성 갭(ideas/owns 있는 역할 우선)
    for r in inputs["roles"]:
        if r["id"] in used_roles:
            continue
        nick = ROLE_NICK.get(r["id"], r["id"].upper())
        sig1 = {
            "rank": 1,
            "role": r["id"],
            "owner": nick,
            "title": f"{r['title']} 북극성 '{r['northstar'][:30]}' 향한 다음 브릿지 한 칸 설계",
            "first_action": f"{nick}가 북극성 갭 분석 후 다음 브릿지 배 1척 _queue 등록",
            "expected": f"북극성 연결고리 +1칸 — {', '.join(r['owns'][:2]) or '소유항목'} 진전",
            "path_map": f"{r['northstar'][:40]} → 미배치 브릿지 → 지금(active {len(r['active_ships'])}건) → 오늘 북극성 갭 한 칸",
            "rationale": f"신호① 북극성 갭 — [{r['id']}] 북극성 서술 대비 비어있는 다음 걸음(소유: {', '.join(r['owns'][:2]) or '없음'})",
            "one_reason": f"북극성 직접기여 신호 — 전사 방향성에 직결되므로 1순위",
            "difficulty": "🛳️크루즈",
            "signal": "신호①",
        }
        used_roles.add(r["id"])
        break

    # 신호② — KPI 미달 역할
    for r in _kpi_gap_roles(inputs):
        if r["id"] in used_roles:
            continue
        kv = r["kpi_values"]
        wan = kv.get("완결률")
        wan_s = f"{wan:.0%}" if isinstance(wan, (int, float)) else "집계없음"
        nick = ROLE_NICK.get(r["id"], r["id"].upper())
        sig2 = {
            "rank": 2,
            "role": r["id"],
            "owner": nick,
            "title": f"{r['title']} 활성 배 {kv.get('활성',0)}건 중 1건 완주 — 완결률 끌어올리기",
            "first_action": f"{nick}가 활성 배 중 가장 가까운 완료 가능 배 1척 집중 완주",
            "expected": f"완결률 {wan_s} → 1건 완료로 KPI 개선, 표류 방지",
            "path_map": f"{r['northstar'][:40]} → KPI({r['kpi_def'][:30]}) → 지금(완결률 {wan_s}) → 오늘 완주 1건",
            "rationale": f"신호② KPI 미달 — [{r['id']}] 완결률 {wan_s}, 활성 {kv.get('활성',0)} / 완료 {kv.get('완료',0)}",
            "one_reason": "",
            "difficulty": "⛵돛단배",
            "signal": "신호②",
        }
        used_roles.add(r["id"])
        break

    # 신호③ — 완료건 next 중 미착수(active 제목과 안 겹치는 것)
    for r in inputs["roles"]:
        if r["id"] in used_roles:
            continue
        active_titles = " ".join(s["title"] for s in r["active_ships"])
        nick = ROLE_NICK.get(r["id"], r["id"].upper())
        for nxt in r["next_steps"]:
            core = re.sub(r"^[🔗🌀⚓🏁\s]+", "", nxt)[:80]
            if core and core[:12] not in active_titles:
                sig3 = {
                    "rank": 3,
                    "role": r["id"],
                    "owner": nick,
                    "title": f"{core}",
                    "first_action": f"{nick}가 해당 next 배 _queue 등록 후 착수",
                    "expected": "완료건 브릿지 연속성 확보 — 표류 방지",
                    "path_map": f"{r['northstar'][:40]} → 진행 브릿지 → 지금(완료건 next 미착수) → 오늘 이 다음 걸음",
                    "rationale": f"신호③ 다음 한 걸음 — [{r['id']}] 완료건 next 미착수: '{core[:50]}'",
                    "one_reason": "",
                    "difficulty": "⛴️여객선",
                    "signal": "신호③",
                }
                used_roles.add(r["id"])
                break
        if sig3:
            break

    # 반환: rank 순(①>②>③), None 제거
    cands = [c for c in [sig1, sig2, sig3] if c is not None]
    return cands[:RECOMMEND_COUNT]


# ═══════════════════════════════════════════
#  후보 정규화
# ═══════════════════════════════════════════
def normalize_candidates(raw: list) -> list:
    out = []
    for i, c in enumerate(raw[:RECOMMEND_COUNT], 1):
        if not isinstance(c, dict):
            continue
        role = (c.get("role") or "").lower()
        if role not in TARGET_ROLES:
            role = "ceo"
        diff = c.get("difficulty", "")
        if diff not in DIFFICULTY_BOATS:
            diff = "⛴️여객선"
        # rank: LLM/폴백이 제공하면 그대로, 없으면 순서로 대체
        try:
            rank = int(c.get("rank", i))
        except (ValueError, TypeError):
            rank = i
        # owner: LLM이 주면 그대로, 없으면 ROLE_NICK 매핑
        owner = str(c.get("owner", "") or "").strip() or ROLE_NICK.get(role, role.upper())
        out.append({
            "rank": rank,
            "role": role,
            "owner": owner,
            "title": str(c.get("title", "")).strip(),
            "first_action": str(c.get("first_action", "")).strip(),
            "expected": str(c.get("expected", "")).strip(),
            "path_map": str(c.get("path_map", "")).strip(),
            "rationale": str(c.get("rationale", "")).strip(),
            "one_reason": str(c.get("one_reason", "")).strip(),
            "difficulty": diff,
            "signal": str(c.get("signal", "")).strip(),
        })
    # rank=1이 index 0이 되도록 정렬 → [승인 1] = 1순위 보존
    out.sort(key=lambda x: x.get("rank", 99))
    return out


# ═══════════════════════════════════════════
#  3줄 브릿지 보강 (GM 2026-06-29 — 북극성↔지금↔오늘 한눈)
# ═══════════════════════════════════════════
def _role_progress(rd: dict) -> str:
    """역할의 '지금(진행 현황)' 한 줄 — 활성 배 수·완료건 next·KPI 현재값. 수집 입력만 사용."""
    n_active = len(rd.get("active_ships", []))
    n_next = len(rd.get("next_steps", []))
    kv = rd.get("kpi_values", {}) or {}
    kv_str = ", ".join(f"{k}={v}" for k, v in kv.items() if not k.startswith("_"))
    parts = [f"활성 {n_active}척"]
    parts.append(f"완료건 next {n_next}건" if n_next else "완료건 next 없음(표류)")
    parts.append(f"KPI {kv_str}" if kv_str else "KPI 집계없음")
    return " · ".join(parts)


def enrich_candidates(candidates: list, roles_by_id: dict) -> list:
    """각 후보에 northstar·progress 필드 + 3줄 브릿지 path_map 부여(이미 수집한 입력만).
    🌟 북극성(dims0) → 📍 지금(활성·next·KPI) → 👉 오늘 한 수(제목+근거신호)."""
    for c in candidates:
        rd = roles_by_id.get(c.get("role"), {})
        ns = (rd.get("northstar") or "").strip()[:80]
        progress = _role_progress(rd) if rd else "(현황 없음)"
        c["northstar"] = ns
        c["progress"] = progress
        c["path_map"] = (
            f"🌟 북극성: {ns or '(미정)'}\n"
            f"📍 지금: {progress}\n"
            f"👉 오늘 한 수: {c.get('title', '')} ({c.get('signal', '')})"
        )
    return candidates


# ═══════════════════════════════════════════
#  모듈 그룹핑 보강 (GM 확정 2026-07-04 ① — 페이지=수단, 프로젝트=목적)
# ═══════════════════════════════════════════
def enrich_modules(candidates: list, roles_by_id: dict) -> list:
    """각 후보에 module·module_label·page_url·serves 부여(공유 매퍼 vmm 단일 소스).
    serves = '돕는 실무라인 프로젝트 → 북극성' 한 줄(페이지=수단, 프로젝트=목적)."""
    for c in candidates:
        role = c.get("role", "")
        ship = {"clevel": role, "title": c.get("title", ""),
                "note": c.get("rationale", "")}
        m = vmm.module_for_ship(ship, role_id=role)
        # 북극성·모듈 설명은 여러 줄일 수 있음 → serves 한 줄용으로 공백 정규화 후 절단
        ns = re.sub(r"\s+", " ", (roles_by_id.get(role, {}).get("northstar") or "")).strip()[:50]
        proj = re.sub(r"\s+", " ", (m.get("desc") or m["label"] or "")).strip()[:60]
        c["module"] = m["id"]
        c["module_label"] = m["label"]
        c["page_url"] = m.get("page_url", "")
        c["serves"] = f"{proj} → 🌟 {ns or '(북극성 미정)'}"
    return candidates


# ═══════════════════════════════════════════
#  중요건 필터 (GM 확정 2026-07-04 ③ — ⛵ low·단순 노이즈 컷)
# ═══════════════════════════════════════════
def filter_important(candidates: list) -> list:
    """중요건만 남긴다: 난이도 🛳️/⛴️ 또는 신호①(북극성 갭)/②(KPI 미달) 또는 rank=1.
    전부 컷되면(전멸 방지) rank 최상위 1건은 보존."""
    kept = []
    for c in candidates:
        diff = c.get("difficulty", "")
        sig = c.get("signal", "")
        is_important = (
            diff in IMPORTANT_BOATS
            or "①" in sig or "②" in sig
            or int(c.get("rank", 99)) == 1
        )
        if is_important:
            kept.append(c)
    if not kept and candidates:
        kept = [min(candidates, key=lambda x: int(x.get("rank", 99)))]
    return kept


# ═══════════════════════════════════════════
#  C레벨 병렬 배 (GM 확정 2026-07-04 ③ — depends_on 없는 독립 중요 배)
# ═══════════════════════════════════════════
def collect_parallel_ships(exclude_titles: set | None = None, cap: int = 6) -> list:
    """_queue 에서 '독립(depends_on 없음)·중요(🛳️/⛴️)·활성' 배를 모듈별로 수집.
    추천 후보와 병렬로 담당 C레벨이 동시에 밀 수 있는 배 → GM 상황인지용(버튼 없음)."""
    exclude_titles = exclude_titles or set()
    queue = load_json(QUEUE_FILE, [])
    if not isinstance(queue, list):
        return []
    out = []
    for ship in queue:
        role = (ship.get("clevel") or "").lower()
        if role not in TARGET_ROLES:
            continue
        if ship.get("status") not in ACTIVE_STATUSES:
            continue
        dep = str(ship.get("depends_on") or "").strip()
        if dep:  # 독립 배만(의존 있으면 병렬 불가)
            continue
        if ship.get("priority", "") not in IMPORTANT_BOATS:
            continue
        title = str(ship.get("title", "")).strip()
        if title[:20] in exclude_titles:
            continue
        m = vmm.module_for_ship(ship, role_id=role)
        out.append({
            "role": role,
            "owner": ROLE_NICK.get(role, role.upper()),
            "ship_no": ship.get("ship_no"),
            "title": title,
            "priority": ship.get("priority", ""),
            "module": m["id"],
            "module_label": m["label"],
        })
    # 모듈 라벨 → 배 오름차순, cap 개까지
    out.sort(key=lambda x: (x["role"], str(x["module"])))
    return out[:cap]


# ═══════════════════════════════════════════
#  텔레그램 발송 (.env 직독 · INC-004) + 카드
# ═══════════════════════════════════════════
def _env_val(key: str) -> str:
    """환경변수 → telegram_bot/.env 순서로 값 로드(토큰·챗ID 단일출처)."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


def build_card(pending: dict) -> str:
    """텔레그램 GM 결재 카드 — 북극성 모듈 그룹핑 + 탭 인라인버튼(GM 확정 2026-07-04·배420).

    candidates 배열은 rank 순 정렬(0번=rank 1=1순위 → 버튼 'ns:0:approve').
    포맷: 후보를 (역할·모듈) 그룹으로 묶어 렌더 — 각 모듈 헤더에 대표 페이지 URL(수단) +
    serves(돕는 프로젝트 → 북극성, 목적) 한 줄. 승인은 텍스트 [승인N] 폐기 → 하단 인라인버튼.
    웰리 단일 추천(RECOMMEND_COUNT=1)이라 '⚓ 병렬 진행 가능(독립 배)' 참고 섹션은 렌더하지 않음.

    ※ 표시 포맷은 이 함수에 격리 — 교체 시 여기만 수정(데이터·콜백 로직 불변)."""
    e = html.escape
    d = pending.get("date", today_str())
    try:
        wd = ["월", "화", "수", "목", "금", "토", "일"][datetime.strptime(d, "%Y-%m-%d").weekday()]
    except Exception:
        wd = ""
    cands = pending.get("candidates", [])
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    lines = [
        "🧭 <b>웰리의 오늘의 북극성 한 수</b>",
        f"📅 {e(d)} ({wd})  ·  웰리 추천 1건",
        "",
    ]

    # ── 후보를 (역할·모듈) 순서 유지 그룹핑 (rank 순 보존) ──
    seen_group: dict[str, list] = {}
    order: list = []
    for idx, c in enumerate(cands):
        gk = f"{c.get('role','')}|{c.get('module','')}"
        if gk not in seen_group:
            seen_group[gk] = []
            order.append(gk)
        seen_group[gk].append((idx, c))

    for gk in order:
        first = seen_group[gk][0][1]
        owner = e(first.get("owner", ""))
        mod_label = e(first.get("module_label", first.get("module", "")))
        page = first.get("page_url", "")
        serves = e(first.get("serves", ""))
        # 모듈 헤더: 대표 페이지(수단) + serves(프로젝트→북극성, 목적)
        head = f"📦 <b>{mod_label}</b> <i>({owner})</i>"
        if page:
            head += f" · <a href=\"{page}\">대표 페이지</a>"
        lines.append(head)
        if serves:
            lines.append(f"   🎯 {serves}")
        # 그룹 내 후보들 (단일 추천이면 메달 생략 — title 강조 우선)
        for idx, c in seen_group[gk]:
            medal = "" if len(cands) <= 1 else medals.get(idx + 1, f"{idx+1}.")
            title = e(c.get("title", ""))
            diff = c.get("difficulty", "")
            fa = e(c.get("first_action", ""))
            exp = e(c.get("expected", ""))
            why = e(c.get("one_reason", "")) if idx == 0 else ""
            lines.append(f"{medal} <b>{title}</b> {diff}".strip())
            if fa:
                lines.append(f"     👉 첫 행동: {fa}")
            if exp:
                lines.append(f"     📈 예상 효과: {exp}")
            if why:
                lines.append(f"     ★ 왜 1순위: {why}")
        lines.append("")

    # ── 회신 안내(버튼) ──
    lines.append("👉 아래 버튼으로 승인하세요 — 승인 시 그 배가 G1 큐(_queue)에 등록·즉시 착수.")
    lines.append(f"📊 표로 자세히: {NORTHSTAR_WEB_URL}")
    return "\n".join(lines)


def build_keyboard(pending: dict) -> dict:
    """탭 인라인 승인버튼(M5 검수카드 패턴 이식). callback_data 규약 ns:<idx>:approve / ns:hold.
    idx = pending.candidates 배열 인덱스(rank 순) → 봇 CallbackQueryHandler(^ns:) 가 처리."""
    cands = pending.get("candidates", [])
    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    single = len(cands) <= 1
    approve_row = []
    for idx, c in enumerate(cands):
        text = "✅ 승인" if single else f"{medals.get(idx, f'{idx+1}.')} {idx+1}순위 승인"
        approve_row.append({
            "text": text,
            "callback_data": f"ns:{idx}:approve",  # 규약·짧음(<64B)
        })
    rows = []
    # 한 행 최대 3버튼(가독성) — 승인 버튼 행 + 보류 행
    for i in range(0, len(approve_row), 3):
        rows.append(approve_row[i:i + 3])
    rows.append([{"text": "⚓ 보류" if single else "⚓ 전체 보류", "callback_data": "ns:hold"}])
    return {"inline_keyboard": rows}


def send_card(pending: dict) -> bool:
    """북극성 추천 카드를 .env TELEGRAM_CHAT_ID 로 발송(탭 인라인버튼 포함). 성공 True."""
    token = _env_val("TELEGRAM_BOT_TOKEN")
    chat_id = _env_val("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[WARN] 텔레그램 토큰/챗ID 미설정(.env) — 카드 발송 생략")
        return False
    text = build_card(pending)
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "reply_markup": json.dumps(build_keyboard(pending)),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = resp.status == 200
            print(f"[INFO] 북극성 카드 발송 {'성공' if ok else '실패'}")
            return ok
    except Exception:
        print("[WARN] 카드 발송 실패 (토큰 trace 노출 방지로 상세 미출력)")
        return False


# ═══════════════════════════════════════════
#  폐루프 로그 + G2 만료
# ═══════════════════════════════════════════
def log_event(event: str, **fields) -> None:
    """status/northstar_log.jsonl 1행 append (적중률·기여 추적 v1)."""
    rec = {"event": event, "logged_at": now_str(), **fields}
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] 로그 기록 실패: {e}")


def expire_previous() -> None:
    """새 추천 생성 시점에 이전 'proposed' 미승인 건을 자동 만료(G2). 당일 자정 아님."""
    if not PENDING_FILE.exists():
        return
    try:
        prev = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    if str(prev.get("status")) == "proposed":
        cands = prev.get("candidates", [])
        log_event(
            "expired",
            date=prev.get("date"),
            candidate_count=len(cands),
            reason="새 추천 생성으로 자동 보류(G2)",
        )
        print(f"[G2] 이전 미승인 추천({prev.get('date')}) {len(cands)}건 → expired 처리")


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def run(stdout_only: bool = False, send: bool = False):
    mode = "라이브 발송(--send)" if send else "드라이런"
    print(f"[시작] 일일 북극성 추천기 ({mode}) — {now_str()}")
    if send:
        print("  ★ 2단계 라이브: 텔레그램 카드 발송 + G2 만료 + 폐루프 로그\n")
    else:
        print("  ★ 드라이런: 콘솔 + northstar_pending.json 기록만 (텔레그램 발송 없음)\n")

    # 1. 입력 수집
    inputs = collect_inputs()
    roles_by_id = {r["id"]: r for r in inputs["roles"]}
    print(f"[1/3] 입력 수집 완료 — 대상 {len(inputs['roles'])}역할 "
          f"(matrix {inputs['matrix_updated_at']} · kpi {inputs['kpi_generated_at']})")

    # 2. 두뇌 — claude CLI 우선, 실패 시 규칙폴백
    print("[2/3] 웰리 두뇌(claude CLI · model_router 폴백) 호출...")
    brain = "ClaudeCLI"
    raw = brain_claude_cli(inputs)
    if raw is None:
        brain = "규칙폴백"
        raw = brain_fallback(inputs)
        print(f"  → 규칙기반 폴백 동작: {len(raw)}개 (claude CLI 미가용 — 정상 강등)")
    else:
        print(f"  → ClaudeCLI 생성: {len(raw)}개")

    candidates = normalize_candidates(raw)
    if len(candidates) < RECOMMEND_COUNT:
        # 부족분 규칙폴백으로 보충(웰리 단일 추천 보장)
        for c in brain_fallback(inputs):
            if len(candidates) >= RECOMMEND_COUNT:
                break
            if c["role"] not in {x["role"] for x in candidates}:
                candidates.append(c)
        candidates = candidates[:RECOMMEND_COUNT]
        if brain == "ClaudeCLI":
            brain = "ClaudeCLI+폴백보충"

    # 2-b. 3줄 브릿지 보강 (GM 2026-06-29) — northstar·progress·path_map(3줄)
    candidates = enrich_candidates(candidates, roles_by_id)

    # 2-c. 중요건 필터 + 모듈 그룹핑 보강 (GM 확정 2026-07-04·배420)
    candidates = filter_important(candidates)
    candidates = enrich_modules(candidates, roles_by_id)
    excl = {str(c.get("title", ""))[:20] for c in candidates}
    parallel_ships = collect_parallel_ships(exclude_titles=excl)
    print(f"[2c] 중요건 필터 후 {len(candidates)}개 · 병렬 독립배 {len(parallel_ships)}척 첨부")

    # 3. 결과 조립
    pending = {
        "date": today_str(),
        "generated_at": now_str(),
        "generated_by": brain,
        "status": "proposed",
        "source": {
            "matrix_updated_at": inputs["matrix_updated_at"],
            "kpi_generated_at": inputs["kpi_generated_at"],
        },
        "candidates": candidates,
        "parallel_ships": parallel_ships,
    }

    # 콘솔 출력 — 3줄 브릿지(북극성→지금→오늘) 그대로 노출
    print(f"\n{'='*60}")
    print(f"  🧭 전사 북극성 추천 — 웰리 단일 추천 1개  (생성두뇌={brain})")
    print(f"{'='*60}")
    for i, c in enumerate(candidates, 1):
        print(f"\n┌ 후보 {i} {c['difficulty']}  [{c['role']}]")
        print(f"│ {c['path_map']}".replace("\n", "\n│ "))
        print(f"│ 근거: {c['rationale']}  ({c['signal']})")
        print("└")
    print(f"\n{'='*60}")

    # 발송 모드 — G2 만료(이전 미승인) → 파일 기록 → 카드 발송 → 폐루프 로그
    if send:
        expire_previous()
        PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
        sent = send_card(pending)
        log_event(
            "proposed",
            date=pending["date"],
            generated_by=brain,
            sent=sent,
            roles=[c["role"] for c in candidates],
            titles=[c["title"][:60] for c in candidates],
        )
        print(f"\n[3/3] 기록·발송 완료: {PENDING_FILE} (텔레그램 {'발송' if sent else '미발송'})")
        print(f"[완료] ({now_str()})")
        return pending

    # 드라이런
    print("  (드라이런 — 텔레그램 카드·승인콜백은 --send / 봇)")

    # 샘플 카드 미리보기 — 실발송 없이 카드 텍스트 + 버튼 레이아웃을 파일로 출력(발효 전 GM 검토용)
    try:
        card_text = build_card(pending)
        keyboard = build_keyboard(pending)
        sample = (
            "# 북극성 추천 카드 샘플 (드라이런 · 실발송 아님)\n"
            f"생성: {now_str()} · 두뇌={brain} · 대상={'/'.join(TARGET_ROLES)}\n"
            f"발효 게이트: 텔레그램 send·cron·봇 재기동 전부 금지 — GM go 별건.\n\n"
            "## 카드 본문(텔레그램 HTML parse_mode)\n"
            "```\n" + card_text + "\n```\n\n"
            "## 인라인 버튼 레이아웃(reply_markup)\n"
            "```json\n" + json.dumps(keyboard, ensure_ascii=False, indent=2) + "\n```\n"
        )
        SAMPLE_FILE = BASE_DIR / "status" / "northstar_card_sample.md"
        SAMPLE_FILE.write_text(sample, encoding="utf-8")
        print(f"[샘플] 카드 미리보기 기록: {SAMPLE_FILE}")
    except Exception as e:
        print(f"[WARN] 샘플 카드 생성 실패: {type(e).__name__}: {e}")

    if stdout_only:
        print("\n[--stdout-only] 파일 기록 생략")
        return pending

    PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[3/3] 기록 완료: {PENDING_FILE}")
    print(f"[완료] ({now_str()})")
    return pending


def main():
    parser = argparse.ArgumentParser(
        description="일일 북극성 추천기 1단계 — 두뇌 드라이런 엔진(전 C-Level·웰리 단일 추천 1개)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="드라이런(기본 동작) — 콘솔 + northstar_pending.json 기록. 라이브 부작용 없음")
    parser.add_argument("--stdout-only", action="store_true", dest="stdout_only",
                        help="파일 기록 없이 콘솔 출력만")
    parser.add_argument("--send", action="store_true",
                        help="2단계 라이브 — 단일 후보 생성 + G2 만료 + northstar_pending.json 기록 "
                             "+ 텔레그램 카드 발송 + 폐루프 로그 (06:30 예약 진입점)")
    args = parser.parse_args()
    # --dry-run 은 기본 동작. --send 는 라이브 발송(06:30 가동).
    run(stdout_only=args.stdout_only, send=args.send)


if __name__ == "__main__":
    main()
