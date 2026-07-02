#!/usr/bin/env python3
"""AI 자기학습 ②단계 — 개선제안 생성기 + ③단계 — 승인→반영 경로 관리
(ai_learning_proposer.py)

latest_summary.json 을 읽어 C-Level 운영 개선제안 카드 N개를 생성하고
status/learning_proposals.json 에 누적 저장 + 텔레그램 1줄 알림.

★ 안전 원칙:
  - 읽기 + 제안 생성 + learning_proposals.json 쓰기/상태전이만.
  - 메모리(~/.claude/**), 프롬프트, 에이전트 정의, CLAUDE.md 절대 수정 금지.
  - 모든 신규 카드 status="제안" 고정.
  - 반영(메모리/프롬프트/코드 수정)은 승인 후 웰리(사람·AI 세션)가 수동 실행.
  - 이 스크립트에 메모리/프롬프트/CLAUDE.md 등 쓰기 코드 없음.

두뇌(LLM) 우선순위 (GM 결정 2026-06-23):
  1순위: claude CLI (claude -p <프롬프트>) — 이미 구독 중인 Claude Code 재사용, API 크레딧 0
  2순위: 규칙기반 폴백 — CLI 불가 시 최소동작 보장
  비활성: Anthropic SDK 직접호출 — 크레딧 소모, 기본 경로에서 제외(ENV 활성화 시만)

사용법:
  python scripts/ai_learning_proposer.py               # 제안 생성 + 저장 + 텔레그램
  python scripts/ai_learning_proposer.py --dry-run     # 콘솔 출력만 (저장·발송 없음)
  python scripts/ai_learning_proposer.py --max 5       # 제안 수 지정 (기본 3)

  python scripts/ai_learning_proposer.py --list                     # 전체 카드 목록
  python scripts/ai_learning_proposer.py --list --status 제안        # 상태별 필터
  python scripts/ai_learning_proposer.py --approve <id>             # 승인
  python scripts/ai_learning_proposer.py --reject <id> [--reason 사유]  # 거부
  python scripts/ai_learning_proposer.py --mark-applied <id>        # 반영완료
"""
import argparse
import json
import os
import sys
import io
import re
import subprocess
import uuid
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
ENV_FILE = BASE_DIR / "telegram_bot" / ".env"
SUMMARY_FILE = BASE_DIR / "scripts" / "_education_data" / "latest_summary.json"
PROPOSALS_FILE = BASE_DIR / "status" / "learning_proposals.json"
# 신규 입력 — 스킬 인벤토리(skill_inventory.py) + 최근 작업 맥락 소스
QUEUE_FILE = BASE_DIR / "status" / "_queue.json"
GM_LEDGER_FILE = BASE_DIR / "status" / "gm_observation_ledger.jsonl"

# ── C-Level 목록 (제안 배분용) ──
CLEVELS = ["시토", "시우", "시모", "시포", "시로", "시뽀", "웰리"]

# ── 개선제안 대상 카테고리 ──
IMPROVEMENT_AREAS = [
    {"area": "메모리", "desc": "에이전트 메모리 파일 구조·키워드·정보 최신화"},
    {"area": "프롬프트", "desc": "C-Level 시스템 프롬프트 강화·명확화"},
    {"area": "자동화코드", "desc": "스크립트·파이프라인 개선·신규 자동화"},
    {"area": "보고체계", "desc": "텔레그램·G1 보고 형식·주기 개선"},
    {"area": "운영프로세스", "desc": "일일 워크플로우·루틴 효율화"},
    {"area": "스킬·플러그인 활용", "desc": "설치된 스킬·플러그인을 우리 워크플로에 활용"},
]

# ── 허용 status 값 ──
VALID_STATUSES = ["제안", "승인", "거부", "반영"]

# ── 허용 효과 값 ──
VALID_EFFECTS = ["효과있음", "효과없음", "미확인"]


# ═══════════════════════════════════════════
#  유틸
# ═══════════════════════════════════════════
def load_env() -> dict:
    out = {}
    if not ENV_FILE.exists():
        return out
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def make_proposal_id() -> str:
    return f"prop_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def load_proposals() -> list:
    """proposals.json 로드. 효과 필드 없는 기존 카드에 기본값 채움."""
    if not PROPOSALS_FILE.exists():
        return []
    try:
        data = json.loads(PROPOSALS_FILE.read_text(encoding="utf-8"))
        cards = data if isinstance(data, list) else []
        # 기존 카드에 효과 필드 기본값 채움 (신규 스키마 호환)
        for c in cards:
            if "효과" not in c:
                c["효과"] = "미확인"
            if "효과근거" not in c:
                c["효과근거"] = ""
            if "효과일자" not in c:
                c["효과일자"] = ""
        return cards
    except Exception:
        return []


def save_proposals_file(cards: list):
    PROPOSALS_FILE.write_text(
        json.dumps(cards, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ═══════════════════════════════════════════
#  요약 로드
# ═══════════════════════════════════════════
def load_summary() -> dict:
    if not SUMMARY_FILE.exists():
        print(f"[ERROR] 요약 파일 없음: {SUMMARY_FILE}")
        print("  → ai_education_auto_learner.py --summary 먼저 실행 필요")
        sys.exit(1)
    return json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════
#  ② LLM 제안 생성 — 1순위: claude CLI
# ═══════════════════════════════════════════
def _build_effect_feedback(limit: int = 12) -> str:
    """자기학습 환류 — 지난 '반영' 제안의 효과 이력을 요약해 다음 제안 생성에 먹인다.
    효과있던 방향은 강화, 효과없던 방향은 피하라는 신호. 이력 없으면 빈 문자열."""
    try:
        cards = load_proposals()
    except Exception:
        return ""
    applied = [c for c in cards if c.get("status") == "반영"]
    if not applied:
        return ""
    applied = applied[-limit:]
    lines = []
    for c in applied:
        eff = c.get("효과", "미확인") or "미확인"
        icon = {"효과있음": "✅", "효과없음": "❌", "미확인": "❔"}.get(eff, "❔")
        what = str(c.get("무엇을", ""))[:70]
        why = str(c.get("효과근거", ""))[:45]
        lines.append(f"  {icon} [{c.get('대상_clevel','')}] {what} → {eff}{(' · '+why) if why else ''}")
    return (
        "\n[자기학습 환류 — 지난 개선의 실제 효과 이력]\n"
        "아래는 과거 반영한 개선과 그 측정 효과다. ✅효과있음 방향은 강화하고, "
        "❌효과없음 방향은 피하며, ❔미확인은 효과를 가늠할 수 있게 더 측정가능한 형태로 제안하라:\n"
        + "\n".join(lines) + "\n"
    )


def _load_skill_inventory() -> dict | None:
    """skill_inventory.py 를 import 해 설치 스킬 인벤토리를 얻는다. best-effort(read-only).
    실패 시 None — 스킬 영역 없이 기존 5영역만 정상 동작."""
    try:
        try:
            from skill_inventory import build_inventory
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from skill_inventory import build_inventory
        return build_inventory()
    except Exception as e:
        print(f"[WARN] 스킬 인벤토리 수집 실패({type(e).__name__}) — 스킬 영역 생략")
        return None


def _recent_work_context(ledger_limit: int = 6, queue_limit: int = 8) -> str:
    """최근 작업 맥락 — gm_observation_ledger.jsonl 최근 몇 건 + _queue.json 최근 제목.
    '이 작업엔 이 스킬' 활용제안을 우리 실제 맥락에 붙이기 위한 신호. read-only·best-effort."""
    lines = []
    # 최근 GM 관측/결정
    try:
        if GM_LEDGER_FILE.exists():
            raw = GM_LEDGER_FILE.read_text(encoding="utf-8").splitlines()
            recent = [l for l in raw if l.strip()][-ledger_limit:]
            obs = []
            for l in recent:
                try:
                    rec = json.loads(l)
                    obs.append(str(rec.get("summary", ""))[:90])
                except Exception:
                    continue
            if obs:
                lines.append("최근 GM 관측·결정:")
                lines += [f"  - {o}" for o in obs if o]
    except Exception:
        pass
    # 최근 큐 제목 (PENDING·IN_PROGRESS 우선)
    try:
        if QUEUE_FILE.exists():
            data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else []
            active = [it for it in items if str(it.get("status", "")).upper() in ("PENDING", "IN_PROGRESS")]
            picked = (active or items)[:queue_limit]
            titles = [str(it.get("title", ""))[:90] for it in picked if it.get("title")]
            if titles:
                lines.append("최근·진행중 업무(큐):")
                lines += [f"  - {t}" for t in titles]
    except Exception:
        pass
    return "\n".join(lines)


def _build_skill_and_context_block() -> str:
    """LLM 프롬프트에 주입할 [스킬 인벤토리 + 최근 작업 맥락] 블록. 없으면 빈 문자열."""
    inv = _load_skill_inventory()
    ctx = _recent_work_context()
    if not inv and not ctx:
        return ""
    parts = ["\n[설치된 스킬·플러그인 인벤토리 + 최근 작업 맥락 — 활용제안 생성용]"]
    if inv:
        from_prompt = None
        try:
            from skill_inventory import format_for_prompt
            from_prompt = format_for_prompt(inv)
        except Exception:
            from_prompt = None
        if from_prompt:
            parts.append(from_prompt)
        parts.append(
            "\n위는 이미 설치돼 바로 쓸 수 있는 스킬 목록이다(✨=아직 우리 워크플로에 미활용). "
            "미활용 스킬 중 우리 최근 작업에 실제로 도움될 것을 골라, '이 작업엔 이 스킬을 이렇게 쓴다'를 "
            "반영위치=\"스킬·플러그인 활용\" 카드로 최소 1개 제안하라."
        )
    if ctx:
        parts.append("\n" + ctx)
    return "\n".join(parts) + "\n"


def _build_llm_prompt(summary_text: str, max_proposals: int) -> str:
    return f"""당신은 웰페리온(하이엔드 스포츠클럽 멤버십 커뮤니티) AI 운영팀의 기술 자문입니다.

아래는 최신 AI 기술·사례 학습 요약입니다:
---
{summary_text}
---
{_build_effect_feedback()}
{_build_skill_and_context_block()}
위 학습 요약 + (있다면) 지난 개선의 효과 이력 + 설치 스킬 인벤토리·최근 작업 맥락을 함께
바탕으로, 웰페리온 C-Level AI 에이전트(AI CEO·CFO·CHRO·CMO·COO·CPO·CTO) 운영에서
개선할 수 있는 제안을 정확히 {max_proposals}개 생성하세요.
(스킬 인벤토리가 제공됐다면 그중 최소 1개는 반영위치="스킬·플러그인 활용" 카드로.)

각 제안은 반드시 아래 JSON 배열 형식으로만 응답하세요 (설명문·마크다운 없이 순수 JSON만):
[
  {{
    "대상_clevel": "시토",
    "무엇을": "구체적 개선 내용 (1~2문장)",
    "왜_근거": "위 학습 요약의 어떤 내용에서 착안했는지",
    "반영위치": "메모리 또는 프롬프트 또는 자동화코드 또는 보고체계 또는 운영프로세스 또는 스킬·플러그인 활용",
    "예상효과": "기대되는 구체적 효과",
    "위험": "도입 시 주의사항 또는 부작용 (없으면 '없음')",
    "구현_초안": "바로 착수 가능한 실행 초안. ▸대상 파일/위치(예: scripts/xxx.py · S2 cto탭) ▸구체적 변경(핵심 코드·텍스트 스니펫 또는 정확한 수정점) ▸검증법(예: py_compile·라이브 확인). 모르면 '미상'이 아니라 합리적 초안을 제시."
  }}
]

규칙:
- 대상_clevel 은 반드시 시토/시우/시모/시포/시로/시뽀/웰리 중 하나
- 반영위치 는 반드시 메모리/프롬프트/자동화코드/보고체계/운영프로세스/스킬·플러그인 활용 중 하나
- 중복 대상_clevel 최소화 (여러 C-Level 분산)
- 구현_초안 은 '설명'이 아니라 담당 AI가 그대로 착수할 수 있는 구체 초안(파일·변경·검증)으로. 추상적 방향만 적지 말 것
- 순수 JSON 배열만 출력 (```json 코드블록도 없이)"""


def generate_proposals_claude_cli(summary_text: str, max_proposals: int) -> list | None:
    """claude CLI (claude -p) 로 제안 생성. 실패 시 None 반환.
    GM 결정(2026-06-23): API 크레딧 미사용, Claude Code 구독 재사용.
    """
    prompt = _build_llm_prompt(summary_text, max_proposals)
    # 모델 라우팅 폴백 경유(model_router) — 단일 모델 차단·장애 시 대체 모델 자동 강등 + 텔레그램 경보.
    # 정본 = scripts/model_router.py (제안 prop_20260623_185611_d79017, GM 승인 2026-06-23).
    try:
        from model_router import run_claude  # same scripts/ 디렉터리
    except ImportError:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from model_router import run_claude

    raw, used_model = run_claude(prompt, label="learning-proposer")
    if raw is None:
        print("[WARN] 전 모델 폴백 실패 — 규칙기반 폴백")
        return None
    try:
        # 코드블록 제거 방어
        raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        proposals_raw = json.loads(raw)
        if not isinstance(proposals_raw, list):
            raise ValueError("응답이 배열이 아님")
        print(f"[INFO] 제안 생성 모델 = {used_model}")
        return proposals_raw
    except json.JSONDecodeError as e:
        print(f"[WARN] LLM 응답 JSON 파싱 실패(model={used_model}): {e} — 규칙기반 폴백")
        return None
    except Exception as e:
        print(f"[WARN] 제안 파싱 중 예외: {type(e).__name__}: {e} — 규칙기반 폴백")
        return None


def generate_proposals_anthropic_sdk(summary_text: str, max_proposals: int, api_key: str) -> list | None:
    """Anthropic SDK 직접호출 (비활성 옵션, 크레딧 소모).
    USE_ANTHROPIC_API=true 환경변수 또는 .env 설정 시에만 활성화.
    기본 경로에서는 호출하지 않음 (GM 결정 2026-06-23).
    """
    try:
        import anthropic  # type: ignore
    except ImportError:
        print("[WARN] anthropic 패키지 미설치 — SDK 폴백 불가")
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = _build_llm_prompt(summary_text, max_proposals)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        proposals_raw = json.loads(raw)
        if not isinstance(proposals_raw, list):
            raise ValueError("응답이 배열이 아님")
        return proposals_raw
    except Exception as e:
        print(f"[WARN] Anthropic SDK 호출 실패: {type(e).__name__}: {e}")
        return None


# ═══════════════════════════════════════════
#  규칙기반 폴백 제안 생성
# ═══════════════════════════════════════════
def generate_proposals_fallback(summary: dict, max_proposals: int) -> list:
    """LLM 불가 시 요약 항목을 규칙 변환하여 최소동작 제안 생성.
    ★ 스킬·플러그인 활용 영역 최소 1개 포함 보장(설계 요구)."""
    text = summary.get("text", "")
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("=")]
    items = [l for l in lines if l and l[0].isdigit() and ". " in l]
    items = [re.sub(r"^\d+\.\s*", "", i) for i in items]

    SKILL_AREA = "스킬·플러그인 활용"
    ALLOWED_LOC = ["메모리", "프롬프트", "자동화코드", "보고체계", "운영프로세스", SKILL_AREA]

    # 스킬 영역이 반드시 슬롯 하나를 차지하도록 영역 목록 구성
    non_skill = [a for a in IMPROVEMENT_AREAS if a["area"] != SKILL_AREA]
    skill_area = next((a for a in IMPROVEMENT_AREAS if a["area"] == SKILL_AREA),
                      {"area": SKILL_AREA, "desc": "설치된 스킬·플러그인을 우리 워크플로에 활용"})
    if max_proposals <= 1:
        areas = [skill_area]
    else:
        areas = non_skill[:max_proposals - 1] + [skill_area]

    clevels = CLEVELS

    # 스킬 영역 카드용 — 실제 미활용 스킬 몇 개를 근거로
    inv = _load_skill_inventory()
    unused_hint = ""
    if inv and inv.get("unused"):
        unused_hint = ", ".join(inv["unused"][:5])

    proposals = []
    for i, area_info in enumerate(areas):
        ref = items[i] if i < len(items) else "최신 AI 동향"
        is_skill = area_info["area"] == SKILL_AREA
        if is_skill:
            what = (f"{SKILL_AREA} 개선: 설치된 스킬 중 미활용분을 워크플로에 편입"
                    + (f" (미활용 예: {unused_hint})" if unused_hint else ""))
            why = (f"skill_inventory 인벤토리 — 미활용 스킬 {inv.get('unused_count', '?')}개 발굴"
                   if inv else "설치 스킬 인벤토리 기반")
            draft = ("▸skill_inventory.py 로 미활용 스킬 확인 "
                     "▸해당 스킬을 우리 실제 작업에 시범 적용 ▸효과 확인 후 docs/skill_cheatsheet.md 박제")
        else:
            what = f"{area_info['area']} 개선: {area_info['desc']}"
            why = f"학습 요약 참조 항목: '{ref}'"
            draft = "(규칙폴백 — 자동 초안 없음, 담당 AI 수동 설계 필요)"
        loc = area_info["area"] if area_info["area"] in ALLOWED_LOC else "자동화코드"
        proposals.append({
            "대상_clevel": clevels[i % len(clevels)],
            "무엇을": what,
            "왜_근거": why,
            "반영위치": loc,
            "예상효과": "운영 효율 향상 및 최신 AI 기법·도구 반영",
            "위험": "기존 동작 회귀 가능성 — 반영 전 GM 승인 필수",
            "구현_초안": draft,
        })

    return proposals[:max_proposals]


# ═══════════════════════════════════════════
#  제안 카드 조립
# ═══════════════════════════════════════════
def assemble_cards(raw_proposals: list, summary: dict, brain: str) -> list:
    """brain: 'ClaudeCLI' | '규칙폴백' | 'AnthropicSDK'"""
    cards = []
    for p in raw_proposals:
        card = {
            "id": make_proposal_id(),
            "생성일": today_str(),
            "생성시각": now_str(),
            "생성=": brain,  # ② 어떤 두뇌로 생성됐는지 표기
            "학습소스": f"latest_summary ({summary.get('generated_at', '?')})",
            "대상_clevel": p.get("대상_clevel", "웰리"),
            "무엇을": p.get("무엇을", ""),
            "왜_근거": p.get("왜_근거", ""),
            "반영위치": p.get("반영위치", ""),
            "예상효과": p.get("예상효과", ""),
            "위험": p.get("위험", "없음"),
            "구현_초안": p.get("구현_초안", ""),  # ② 실체화: 바로 착수 가능한 실행 초안
            "status": "제안",
            "효과": "미확인",
            "효과근거": "",
            "효과일자": "",
        }
        cards.append(card)
    return cards


# ═══════════════════════════════════════════
#  proposals.json 누적 저장
# ═══════════════════════════════════════════
def append_new_cards(new_cards: list) -> tuple[list, int, list]:
    """기존 proposals 로드 후 중복 없이 누적. (id 기준) 반환: (전체목록, 신규추가수, 신규카드목록)"""
    existing = load_proposals()
    existing_ids = {c["id"] for c in existing if "id" in c}
    added = [c for c in new_cards if c["id"] not in existing_ids]
    all_cards = existing + added
    save_proposals_file(all_cards)
    return all_cards, len(added), added


# ═══════════════════════════════════════════
#  텔레그램 알림
# ═══════════════════════════════════════════
def send_telegram(message: str) -> bool:
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[WARN] 텔레그램 설정 없음 — 발송 생략")
        return False

    if len(message) > 4000:
        message = message[:3990] + "\n...(잘림)"

    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = json.loads(resp.read().decode()).get("ok", False)
            print(f"[텔레그램 {'발송 성공' if ok else '발송 실패'}]")
            return ok
    except Exception as e:
        print(f"[ERROR] 텔레그램 발송 실패: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════
#  ③ 승인→반영 경로 — 상태전이 함수들
#  안전: learning_proposals.json 상태전이만.
#  실제 반영(메모리/프롬프트/코드 수정)은 절대 하지 않음.
# ═══════════════════════════════════════════

def cmd_list(status_filter: str | None):
    """카드 목록 출력 (사람이 읽기 좋게)."""
    cards = load_proposals()
    if not cards:
        print("[정보] 제안 카드 없음. python scripts/ai_learning_proposer.py --dry-run 으로 생성 미리보기")
        return

    filtered = cards
    if status_filter:
        if status_filter not in VALID_STATUSES:
            print(f"[ERROR] --status 는 {VALID_STATUSES} 중 하나")
            sys.exit(1)
        filtered = [c for c in cards if c.get("status") == status_filter]

    label = f"(상태={status_filter})" if status_filter else "(전체)"
    print(f"\n{'='*60}")
    print(f"  AI 자기학습 제안 카드 목록 {label}  총 {len(filtered)}건")
    print(f"{'='*60}")

    if not filtered:
        print("  해당 상태의 카드 없음")
        return

    for card in filtered:
        sid = card.get("id", "?")
        st = card.get("status", "?")
        brain = card.get("생성=", "?")
        target = card.get("대상_clevel", "?")
        what = card.get("무엇을", "")
        loc = card.get("반영위치", "?")
        created = card.get("생성일", "?")

        status_icon = {"제안": "💡", "승인": "✅", "거부": "❌", "반영": "🏁"}.get(st, "?")
        print(f"\n{status_icon} [{st}] {sid}")
        print(f"  대상: {target}  |  위치: {loc}  |  생성두뇌: {brain}  |  생성일: {created}")
        print(f"  무엇을: {what}")
        draft = card.get("구현_초안", "")
        if draft:
            print(f"  🛠 구현 초안: {draft}")

        if st == "승인":
            print(f"  승인일시: {card.get('승인일시', '?')}")
        elif st == "거부":
            print(f"  거부일시: {card.get('거부일시', '?')}  |  사유: {card.get('거부사유', '없음')}")
        elif st == "반영":
            effect = card.get("효과", "미확인")
            effect_icon = {"효과있음": "✅효과있음", "효과없음": "효과없음", "미확인": "⏳미확인"}.get(effect, effect)
            effect_note = card.get("효과근거", "")
            effect_date = card.get("효과일자", "")
            print(f"  반영일시: {card.get('반영일시', '?')}  |  효과: {effect_icon}", end="")
            if effect_date:
                print(f"  (기록일: {effect_date})", end="")
            print()
            if effect_note:
                print(f"  효과근거: {effect_note}")

    print(f"\n{'='*60}")
    print("  명령: --approve <id>  |  --reject <id> [--reason 사유]  |  --mark-applied <id>")
    print("         --record-effect <id> --effect <효과있음|효과없음|미확인> [--note 근거]")
    print(f"{'='*60}\n")


def cmd_approve(card_id: str, dry_run: bool):
    """카드 status='승인' 전이. 실제 반영은 하지 않음."""
    cards = load_proposals()
    target = next((c for c in cards if c.get("id") == card_id), None)
    if not target:
        print(f"[ERROR] 카드 ID 없음: {card_id}")
        sys.exit(1)

    current = target.get("status")
    if current == "승인":
        print(f"[정보] 이미 승인된 카드: {card_id}")
        return
    if current in ("거부", "반영"):
        print(f"[ERROR] {current} 상태는 승인 불가. 현재 status={current}")
        sys.exit(1)

    print(f"\n[승인] {card_id}")
    print(f"  대상: {target.get('대상_clevel')}  |  무엇을: {target.get('무엇을')}")
    print(f"  {current} → 승인")
    print("  ★ 실제 반영(메모리/프롬프트/코드 수정)은 웰리가 수동으로 별도 실행")

    if dry_run:
        print("  [dry-run] 저장 생략")
        return

    target["status"] = "승인"
    target["승인일시"] = now_str()
    save_proposals_file(cards)
    print(f"  저장 완료: {PROPOSALS_FILE}")


def cmd_reject(card_id: str, reason: str, dry_run: bool):
    """카드 status='거부' 전이. 사유 기록으로 반복제안 방지."""
    cards = load_proposals()
    target = next((c for c in cards if c.get("id") == card_id), None)
    if not target:
        print(f"[ERROR] 카드 ID 없음: {card_id}")
        sys.exit(1)

    current = target.get("status")
    if current == "거부":
        print(f"[정보] 이미 거부된 카드: {card_id}")
        return
    if current == "반영":
        print(f"[ERROR] 이미 반영된 카드는 거부 불가")
        sys.exit(1)

    print(f"\n[거부] {card_id}")
    print(f"  대상: {target.get('대상_clevel')}  |  무엇을: {target.get('무엇을')}")
    print(f"  {current} → 거부  |  사유: {reason or '(없음)'}")

    if dry_run:
        print("  [dry-run] 저장 생략")
        return

    target["status"] = "거부"
    target["거부일시"] = now_str()
    target["거부사유"] = reason or ""
    save_proposals_file(cards)
    print(f"  저장 완료: {PROPOSALS_FILE}")


def cmd_record_effect(card_id: str, effect: str, note: str, dry_run: bool):
    """반영된 카드에 효과 기록. status='반영'인 카드에만 허용."""
    if effect not in VALID_EFFECTS:
        print(f"[ERROR] --effect 는 {VALID_EFFECTS} 중 하나")
        sys.exit(1)

    cards = load_proposals()
    target = next((c for c in cards if c.get("id") == card_id), None)
    if not target:
        print(f"[ERROR] 카드 ID 없음: {card_id}")
        sys.exit(1)

    current = target.get("status")
    if current != "반영":
        print(f"[ERROR] 효과 기록은 status='반영' 카드에만 가능. 현재 status={current}")
        print("  → 먼저 --mark-applied 로 반영 완료 표시 후 기록하세요.")
        sys.exit(1)

    print(f"\n[효과 기록] {card_id}")
    print(f"  대상: {target.get('대상_clevel')}  |  무엇을: {target.get('무엇을', '')[:50]}")
    print(f"  효과: {effect}  |  근거: {note or '(없음)'}  |  기록일: {today_str()}")
    print("  ★ 자기수정 아님 — learning_proposals.json 효과 필드만 갱신")

    if dry_run:
        print("  [dry-run] 저장 생략")
        return

    target["효과"] = effect
    target["효과근거"] = note or ""
    target["효과일자"] = today_str()
    save_proposals_file(cards)
    print(f"  저장 완료: {PROPOSALS_FILE}")


def cmd_mark_applied(card_id: str, dry_run: bool):
    """카드 status='반영' 전이. 반영은 이미 수동으로 완료된 후 호출."""
    cards = load_proposals()
    target = next((c for c in cards if c.get("id") == card_id), None)
    if not target:
        print(f"[ERROR] 카드 ID 없음: {card_id}")
        sys.exit(1)

    current = target.get("status")
    if current == "반영":
        print(f"[정보] 이미 반영 완료된 카드: {card_id}")
        return
    if current != "승인":
        print(f"[ERROR] 반영완료는 '승인' 상태에서만 가능. 현재 status={current}")
        sys.exit(1)

    print(f"\n[반영완료] {card_id}")
    print(f"  대상: {target.get('대상_clevel')}  |  무엇을: {target.get('무엇을')}")
    print(f"  승인 → 반영")

    if dry_run:
        print("  [dry-run] 저장 생략")
        return

    target["status"] = "반영"
    target["반영일시"] = now_str()
    save_proposals_file(cards)
    print(f"  저장 완료: {PROPOSALS_FILE}")

    # ④ 효과 측정 고리 자동 트리거(박제) — 반영 직후 측정해 루프를 닫는다.
    #    증거 있을 때만 효과있음 격상, 없으면 미확인 유지(허위 금지). best-effort.
    try:
        try:
            from learning_effect_meter import measure_all
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from learning_effect_meter import measure_all
        measure_all(only_id=card_id)
    except Exception as e:
        print(f"  [효과측정] 자동 트리거 실패({type(e).__name__}) — 수동 측정 가능")


# ═══════════════════════════════════════════
#  메인 파이프라인 (제안 생성)
# ═══════════════════════════════════════════
def run(max_proposals: int = 3, dry_run: bool = False):
    print(f"[시작] AI 학습 개선제안 생성기 ({now_str()})")
    print(f"  dry-run={dry_run}  max={max_proposals}\n")

    # 1. 요약 로드
    summary = load_summary()
    print(f"[1/4] 요약 로드 완료: {summary.get('generated_at', '?')} "
          f"(소스 {summary.get('source_count', 0)}개, 항목 {summary.get('total_items', 0)}건)")

    # 2. 제안 생성 — 두뇌 우선순위: ClaudeCLI > 규칙폴백 (API 직접호출 기본 비활성)
    env = load_env()
    use_anthropic_api = env.get("USE_ANTHROPIC_API", "").lower() == "true"

    summary_text = summary.get("text", "")
    raw_proposals = None
    brain = "규칙폴백"

    # 1순위: claude CLI (Claude Code 구독 재사용, GM 결정 2026-06-23)
    print("[2/4] claude CLI (claude -p) 로 제안 생성 시도...")
    raw_proposals = generate_proposals_claude_cli(summary_text, max_proposals)
    if raw_proposals is not None:
        brain = "ClaudeCLI"
        print(f"  → ClaudeCLI 생성 성공: {len(raw_proposals)}개")
    else:
        # 2순위: 규칙기반 폴백
        print("  → claude CLI 실패 — 규칙기반 폴백")

        # 비활성 옵션: Anthropic SDK (USE_ANTHROPIC_API=true 명시 시에만)
        if use_anthropic_api:
            api_key = env.get("ANTHROPIC_API_KEY_PRIMARY", "")
            if api_key:
                print("  [비활성옵션] USE_ANTHROPIC_API=true — Anthropic SDK 시도 (크레딧 소모)")
                raw_proposals = generate_proposals_anthropic_sdk(summary_text, max_proposals, api_key)
                if raw_proposals is not None:
                    brain = "AnthropicSDK"
                    print(f"  → AnthropicSDK 생성 성공: {len(raw_proposals)}개")

        if raw_proposals is None:
            raw_proposals = generate_proposals_fallback(summary, max_proposals)
            brain = "규칙폴백"
            print(f"  → 규칙기반 폴백: {len(raw_proposals)}개")

    # 3. 카드 조립
    cards = assemble_cards(raw_proposals, summary, brain)
    print(f"[3/4] 제안 카드 {len(cards)}개 조립 완료 (생성={brain})")

    # 콘솔 출력 (dry-run 포함 항상)
    print("\n" + "=" * 55)
    print(f"  개선제안 카드 ({len(cards)}개)  생성두뇌={brain}")
    print("=" * 55)
    for i, card in enumerate(cards, 1):
        print(f"\n[제안 {i}] id: {card['id']}")
        print(f"  대상: {card['대상_clevel']} | 위치: {card['반영위치']} | 생성={card['생성=']}")
        print(f"  무엇을: {card['무엇을']}")
        print(f"  근거: {card['왜_근거']}")
        print(f"  효과: {card['예상효과']}")
        print(f"  위험: {card['위험']}")
        print(f"  status: {card['status']}")
    print("=" * 55)

    if brain == "규칙폴백":
        print("\n[INFO] 생성두뇌=규칙폴백 — claude CLI 재확인 권장")

    if dry_run:
        print("\n[dry-run] 파일 저장·텔레그램 발송 생략")
        return

    # 4. 저장 + 텔레그램
    all_cards, added_count, added_cards = append_new_cards(cards)
    print(f"\n[4/4] 저장 완료: {PROPOSALS_FILE} (누적 {len(all_cards)}개, 신규 {added_count}개)")

    if added_count > 0:
        # 신규 카드 번호목록: "N. 대상: 무엇을 앞부분(30자)"
        def _short(text: str, limit: int = 30) -> str:
            text = text.strip()
            # '—' 또는 첫 문장 끝까지 자르기
            for sep in ("—", "－", " — ", ". ", ".\n"):
                idx = text.find(sep)
                if 0 < idx <= limit + 10:
                    text = text[:idx].strip()
                    break
            return text[:limit] if len(text) > limit else text

        lines = []
        for i, card in enumerate(added_cards, 1):
            clevel = card.get("대상_clevel", "?")
            what = _short(card.get("무엇을", ""))
            lines.append(f"{i}. {clevel}: {what}")
        card_list = "\n".join(lines)

        tg_msg = (
            f"[시토] AI 자기학습 — 개선제안 {added_count}건 (검토 대기)\n"
            f"{card_list}\n"
            f"생성두뇌: {brain} · 학습기준: {summary.get('generated_at', '?')}\n"
            f"👉 G1 'AI 자기학습 제안' 섹션에서 확인\n"
            f"승인: python scripts/ai_learning_proposer.py --approve <id>"
        )
        send_telegram(tg_msg)
    else:
        print("[INFO] 신규 제안 없음 (중복) — 텔레그램 생략")

    # 관측 리포트 자동 갱신 — 일요일 자동사이클이 돌 때마다 루프 건강도 산출물 새로고침.
    try:
        cmd_health(write=True)
    except Exception as e:
        print(f"[WARN] 건강도 리포트 생성 실패: {type(e).__name__}: {e}")

    print(f"\n[완료] ({now_str()})")


def cmd_health(write: bool = True) -> dict:
    """자기학습 루프 관측 리포트 — 제안수·전환율·효과있음률 요약 + status/learning_health.md 산출.
    측정 못한 효과(미확인)는 효과있음률 분모에서 제외(정직). 콘솔 출력 + 마크다운 저장."""
    cards = load_proposals()
    from collections import Counter
    st = Counter(c.get("status", "?") for c in cards)
    total = len(cards)
    approved = st.get("승인", 0)
    applied = [c for c in cards if c.get("status") == "반영"]
    nap = len(applied)
    conv = (nap / (approved + nap) * 100) if (approved + nap) else 0.0
    eff = Counter(c.get("효과", "미확인") or "미확인" for c in applied)
    measured = eff.get("효과있음", 0) + eff.get("효과없음", 0)
    eff_rate = (eff.get("효과있음", 0) / measured * 100) if measured else 0.0
    by_clevel = Counter(c.get("대상_clevel", "?") for c in cards)

    print("\n🧠 AI 자기학습 — 루프 건강도")
    print(f"  제안 총 {total}건  (제안 {st.get('제안',0)} · 승인 {approved} · 거부 {st.get('거부',0)} · 반영 {nap})")
    print(f"  승인→반영 전환율: {conv:.0f}%   효과있음률(측정분): {eff_rate:.0f}%  (미확인 {eff.get('미확인',0)}건 측정대기)")
    print(f"  대상별: " + " · ".join(f"{k} {v}" for k, v in by_clevel.most_common()))

    if write:
        lines = [
            "# 🧠 AI 자기학습 — 루프 건강도",
            f"_갱신: {today_str()} · 자동 산출(ai_learning_proposer --health)_",
            "",
            "## 한눈에",
            f"- 제안 총 **{total}건** — 제안 {st.get('제안',0)} · 승인 {approved} · 거부 {st.get('거부',0)} · **반영 {nap}**",
            f"- 승인→반영 전환율: **{conv:.0f}%**",
            f"- 효과있음률(측정된 반영 기준): **{eff_rate:.0f}%** — 효과있음 {eff.get('효과있음',0)} / 측정 {measured}건 · 미확인 {eff.get('미확인',0)}건 측정대기",
            "",
            "## 반영·효과",
            "| 대상 | 반영위치 | 효과 | 근거 |",
            "|---|---|---|---|",
        ]
        for c in applied:
            ic = {"효과있음": "✅", "효과없음": "❌", "미확인": "❔"}.get(c.get("효과", "미확인"), "❔")
            lines.append(
                f"| {c.get('대상_clevel','')} | {c.get('반영위치','')} | {ic}{c.get('효과','미확인')} | {str(c.get('효과근거',''))[:50]} |"
            )
        lines += ["", "## 대상별 제안", "| C-Level | 건수 |", "|---|---|"]
        for k, v in by_clevel.most_common():
            lines.append(f"| {k} | {v} |")
        out = PROPOSALS_FILE.parent / "learning_health.md"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  📄 리포트 저장: {out}")
    return {"total": total, "applied": nap, "conv": conv, "eff_rate": eff_rate}


# ═══════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="AI 자기학습 ②두뇌교체(ClaudeCLI) + ③승인→반영 경로 관리",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "제안 생성:\n"
            "  %(prog)s                      # 생성 + 저장 + 텔레그램\n"
            "  %(prog)s --dry-run            # 콘솔 미리보기 (저장·발송 없음)\n"
            "  %(prog)s --max 5              # 제안 5개 생성\n\n"
            "상태 관리 (③승인→반영 경로):\n"
            "  %(prog)s --list               # 전체 카드 목록\n"
            "  %(prog)s --list --status 제안  # 상태별 필터\n"
            "  %(prog)s --approve <id>       # 승인\n"
            "  %(prog)s --reject <id> [--reason 사유]  # 거부\n"
            "  %(prog)s --mark-applied <id>  # 반영완료 표시\n"
        ),
    )
    # 제안 생성 옵션
    parser.add_argument("--dry-run", action="store_true", help="미리보기 (저장·발송 없음)")
    parser.add_argument("--max", type=int, default=3, metavar="N", help="제안 수 (기본 3)")

    # ③ 상태관리 서브커맨드
    parser.add_argument("--list", action="store_true", help="카드 목록 보기")
    parser.add_argument("--status", type=str, metavar="STATUS", help="--list 필터 (제안|승인|거부|반영)")
    parser.add_argument("--approve", type=str, metavar="ID", help="카드 승인")
    parser.add_argument("--reject", type=str, metavar="ID", help="카드 거부")
    parser.add_argument("--reason", type=str, metavar="TEXT", help="--reject 사유")
    parser.add_argument("--mark-applied", type=str, metavar="ID", dest="mark_applied",
                        help="반영완료 표시")
    parser.add_argument("--record-effect", type=str, metavar="ID", dest="record_effect",
                        help="반영된 카드에 효과 기록 (status=반영 필수)")
    parser.add_argument("--effect", type=str, metavar="EFFECT",
                        help="--record-effect 효과값: 효과있음|효과없음|미확인")
    parser.add_argument("--note", type=str, metavar="TEXT",
                        help="--record-effect 효과 근거 (선택)")
    parser.add_argument("--health", action="store_true",
                        help="자기학습 루프 건강도 리포트(제안수·전환율·효과있음률) + status/learning_health.md 산출")

    args = parser.parse_args()

    # 상태관리 분기
    if args.health:
        cmd_health()
        return

    if args.list:
        cmd_list(args.status)
        return

    if args.approve:
        cmd_approve(args.approve, dry_run=args.dry_run)
        return

    if args.reject:
        cmd_reject(args.reject, reason=args.reason or "", dry_run=args.dry_run)
        return

    if args.mark_applied:
        cmd_mark_applied(args.mark_applied, dry_run=args.dry_run)
        return

    if args.record_effect:
        if not args.effect:
            print("[ERROR] --record-effect 사용 시 --effect <효과있음|효과없음|미확인> 필수")
            sys.exit(1)
        cmd_record_effect(args.record_effect, args.effect, args.note or "", dry_run=args.dry_run)
        return

    # 제안 생성 모드
    if args.max < 1 or args.max > 10:
        print("[ERROR] --max 는 1~10 사이")
        sys.exit(1)

    run(max_proposals=args.max, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
