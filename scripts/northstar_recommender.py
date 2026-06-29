#!/usr/bin/env python3
"""일일 북극성 추천기 — 1단계: 두뇌 드라이런 엔진 (northstar_recommender.py)

매일(2단계에서 06:30) 전 C-Level의 **북극성(목표)** 대비 현재 위치를 읽어,
북극성↔오늘을 잇는 과정(브릿지)을 밟게 하는 **'오늘의 다음 한 수' 전사 top3 후보**를 제안한다.

설계 정본:
  - 스펙   : .omc/specs/deep-interview-daily-northstar-recommender.md
  - 설계서 : status/briefs/CTO-2026-06-29-NORTHSTAR-RECOMMENDER-DESIGN.md
  - 배     : status/_queue.json  CTO-2026-06-29-NORTHSTAR-RECOMMENDER (ship 213)

GM 잠금 결정(2026-06-29):
  - G1: 상태 파일 = status/northstar_pending.json (git 추적)
  - G2: 미승인 추천 = 다음날 새 추천 생성 시 자동 보류(만료)
  - G3: 대상 = 처음부터 전 C-Level(7역할 ceo·cmo·coo·cto·cpo·cfo·chro, gm 제외).
        웰리가 7역할 가로질러 전사 top3 선정 + 각 후보에 역할·북극성 태그.

두뇌(웰리 추천 로직):
  - 1순위: claude CLI (model_router 폴백 경유 — ai_learning_proposer 와 동일 결, API 크레딧 0)
  - 2순위: 규칙기반 폴백 — CLI 불가 시 최소동작 보장(신호 기반 후보 생성)
  [규칙] 신호 3종: ①북극성 갭 ②KPI 미달 ③다음 한 걸음. 우선순위=북극성 직접기여 > KPI 시급 > 브릿지 연속성.
         다양성(서로 다른 신호/역할), 중복방지(_queue active 배 제외), 전사 top3.

★ 1단계 안전 원칙 (라이브 부작용 0):
  - 입력 수집 + 두뇌 호출 + status/northstar_pending.json 쓰기 + 콘솔 출력만.
  - 텔레그램 전송 없음. Task Scheduler 등록 없음. 봇 핸들러 변경 없음. (전부 2단계)

사용법:
  python scripts/northstar_recommender.py            # 드라이런(기본): 콘솔 출력 + northstar_pending.json 기록
  python scripts/northstar_recommender.py --stdout-only   # 파일 기록 없이 콘솔만
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
MATRIX_FILE = BASE_DIR / "3. 웰페리온 가이드" / "coo" / "bootsetup_matrix.json"
QUEUE_FILE = BASE_DIR / "status" / "_queue.json"
KPI_FILE = BASE_DIR / "status" / "kpi_values.json"
PENDING_FILE = BASE_DIR / "status" / "northstar_pending.json"

# ── 대상 역할 (gm 제외, 전 C-Level 7역할) ──
TARGET_ROLES = ["ceo", "cmo", "coo", "cto", "cpo", "cfo", "chro"]

# ── 난이도 배 ──
DIFFICULTY_BOATS = ["⛵돛단배", "⛴️여객선", "🛳️크루즈"]
ACTIVE_STATUSES = ("PENDING", "IN_PROGRESS")


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

    return f"""당신은 웰페리온(하이엔드 스포츠클럽 멤버십 커뮤니티) AI CEO '웰리'입니다.
당신의 본업은 7명의 C-Level을 가로질러 전사를 북극성으로 이끄는 오케스트레이션입니다.

아래는 전 C-Level(7역할)의 북극성·KPI·소유·진행상황 현황입니다:
---{roles_block}
---

위 현황을 바탕으로, 각 C-Level이 '북극성'으로 나아가는 **최상급 과정(브릿지)**을 밟게 하는
**'오늘의 다음 한 수'를 전사 관점에서 단 3개(top3)** 선정하세요.

[추천 규칙]
- 신호 3종 중 각기 다른 근거로: ①북극성 갭(북극성 서술 대비 비어있는 다음 걸음·owns/ideas 참고) ②KPI 미달(KPI 현재치가 목표·정의 밑) ③다음 한 걸음(완료건 next 중 미착수).
- 우선순위 가중: 북극성 직접기여 > KPI 미달 시급 > 브릿지 연속성.
- 다양성: 3개는 가능하면 서로 다른 역할/신호.
- 중복방지: 이미 active 인 배와 겹치는 추천 금지.
- 전사 top3: 7역할 전체에서 가장 가치 높은 3개만(특정 역할 편중 지양).

각 후보는 반드시 아래 JSON 배열 형식으로만 응답하세요 (설명문·마크다운·코드블록 없이 순수 JSON만):
[
  {{
    "role": "cmo",
    "title": "오늘의 한 수 (한 줄, 구체적·실행가능)",
    "path_map": "북극성 → [브릿지 단계들] → 지금 여기 → 오늘 이 한 수",
    "rationale": "근거 — 어느 신호(①/②/③)·어느 갭/지표인지 명시",
    "difficulty": "⛵돛단배 또는 ⛴️여객선 또는 🛳️크루즈",
    "signal": "신호① 또는 신호② 또는 신호③"
  }}
]

규칙:
- role 은 반드시 ceo/cmo/coo/cto/cpo/cfo/chro 중 하나
- difficulty 는 반드시 ⛵돛단배/⛴️여객선/🛳️크루즈 중 하나
- 정확히 3개. 순수 JSON 배열만 출력(```json 코드블록도 없이)."""


def brain_claude_cli(inputs: dict) -> list | None:
    """claude CLI(model_router 폴백)로 전사 top3 후보 생성. 실패 시 None."""
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
    """규칙기반 — 신호 3종으로 서로 다른 역할 후보 3개 생성(최소동작 보장)."""
    cands = []
    used_roles = set()

    # 신호③ — 완료건 next 중 미착수(active 제목과 안 겹치는 것)
    for r in inputs["roles"]:
        if r["id"] in used_roles:
            continue
        active_titles = " ".join(s["title"] for s in r["active_ships"])
        for nxt in r["next_steps"]:
            core = re.sub(r"^[🔗🌀⚓🏁\s]+", "", nxt)[:80]
            if core and core[:12] not in active_titles:
                cands.append({
                    "role": r["id"],
                    "title": f"{core}",
                    "path_map": f"{r['northstar'][:40]} → 진행 브릿지 → 지금(완료건 next 미착수) → 오늘 이 다음 걸음",
                    "rationale": f"신호③ 다음 한 걸음 — [{r['id']}] 완료건 next 미착수: '{core[:50]}'",
                    "difficulty": "⛴️여객선",
                    "signal": "신호③",
                })
                used_roles.add(r["id"])
                break
        if len(cands) >= 1:
            break

    # 신호② — KPI 미달 역할
    for r in _kpi_gap_roles(inputs):
        if r["id"] in used_roles:
            continue
        kv = r["kpi_values"]
        wan = kv.get("완결률")
        wan_s = f"{wan:.0%}" if isinstance(wan, (int, float)) else "집계없음"
        cands.append({
            "role": r["id"],
            "title": f"{r['title']} 활성 배 {kv.get('활성',0)}건 중 1건 완주 — 완결률 끌어올리기",
            "path_map": f"{r['northstar'][:40]} → KPI({r['kpi_def'][:30]}) → 지금(완결률 {wan_s}) → 오늘 완주 1건",
            "rationale": f"신호② KPI 미달 — [{r['id']}] 완결률 {wan_s}, 활성 {kv.get('활성',0)} / 완료 {kv.get('완료',0)}",
            "difficulty": "⛵돛단배",
            "signal": "신호②",
        })
        used_roles.add(r["id"])
        break

    # 신호① — 북극성 갭(아직 안 쓴 역할 중 ideas/owns 있는 곳 우선)
    for r in inputs["roles"]:
        if r["id"] in used_roles:
            continue
        cands.append({
            "role": r["id"],
            "title": f"{r['title']} 북극성 '{r['northstar'][:30]}' 향한 다음 브릿지 한 칸 설계",
            "path_map": f"{r['northstar'][:40]} → 미배치 브릿지 → 지금(active {len(r['active_ships'])}건) → 오늘 북극성 갭 한 칸",
            "rationale": f"신호① 북극성 갭 — [{r['id']}] 북극성 서술 대비 비어있는 다음 걸음(소유: {', '.join(r['owns'][:2]) or '없음'})",
            "difficulty": "🛳️크루즈",
            "signal": "신호①",
        })
        used_roles.add(r["id"])
        break

    return cands[:3]


# ═══════════════════════════════════════════
#  후보 정규화
# ═══════════════════════════════════════════
def normalize_candidates(raw: list) -> list:
    out = []
    for c in raw[:3]:
        if not isinstance(c, dict):
            continue
        role = (c.get("role") or "").lower()
        if role not in TARGET_ROLES:
            role = "ceo"
        diff = c.get("difficulty", "")
        if diff not in DIFFICULTY_BOATS:
            diff = "⛴️여객선"
        out.append({
            "role": role,
            "title": str(c.get("title", "")).strip(),
            "path_map": str(c.get("path_map", "")).strip(),
            "rationale": str(c.get("rationale", "")).strip(),
            "difficulty": diff,
            "signal": str(c.get("signal", "")).strip(),
        })
    return out


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def run(stdout_only: bool = False):
    print(f"[시작] 일일 북극성 추천기 (드라이런) — {now_str()}")
    print("  ★ 라이브 부작용 0: 텔레그램 전송 없음 · 스케줄러 등록 없음 (전부 2단계)\n")

    # 1. 입력 수집
    inputs = collect_inputs()
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
    if len(candidates) < 3:
        # 부족분 규칙폴백으로 보충(전사 top3 보장)
        for c in brain_fallback(inputs):
            if len(candidates) >= 3:
                break
            if c["role"] not in {x["role"] for x in candidates}:
                candidates.append(c)
        candidates = candidates[:3]
        if brain == "ClaudeCLI":
            brain = "ClaudeCLI+폴백보충"

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
    }

    # 콘솔 출력
    print(f"\n{'='*60}")
    print(f"  🧭 전사 북극성 추천 — 전사 top3  (생성두뇌={brain})")
    print(f"{'='*60}")
    for i, c in enumerate(candidates, 1):
        print(f"\n┌ 후보 {i} {c['difficulty']}  [{c['role']}]")
        print(f"│ 제목: {c['title']}")
        print(f"│ 경로: {c['path_map']}")
        print(f"│ 근거: {c['rationale']}  ({c['signal']})")
        print("└")
    print(f"\n{'='*60}")
    print("  (1단계 드라이런 — 텔레그램 카드·승인콜백·스케줄러는 2단계)")

    if stdout_only:
        print("\n[--stdout-only] 파일 기록 생략")
        return pending

    PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[3/3] 기록 완료: {PENDING_FILE}")
    print(f"[완료] ({now_str()})")
    return pending


def main():
    parser = argparse.ArgumentParser(
        description="일일 북극성 추천기 1단계 — 두뇌 드라이런 엔진(전 C-Level·전사 top3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="드라이런(기본 동작) — 콘솔 + northstar_pending.json 기록. 라이브 부작용 없음")
    parser.add_argument("--stdout-only", action="store_true", dest="stdout_only",
                        help="파일 기록 없이 콘솔 출력만")
    args = parser.parse_args()
    # --dry-run 은 기본 동작(1단계는 항상 드라이런). 플래그는 명시성용.
    run(stdout_only=args.stdout_only)


if __name__ == "__main__":
    main()
