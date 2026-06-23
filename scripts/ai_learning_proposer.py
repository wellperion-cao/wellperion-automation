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

# ── C-Level 목록 (제안 배분용) ──
CLEVELS = ["시토", "시우", "시모", "시포", "시로", "시뽀", "웰리"]

# ── 개선제안 대상 카테고리 ──
IMPROVEMENT_AREAS = [
    {"area": "메모리", "desc": "에이전트 메모리 파일 구조·키워드·정보 최신화"},
    {"area": "프롬프트", "desc": "C-Level 시스템 프롬프트 강화·명확화"},
    {"area": "자동화코드", "desc": "스크립트·파이프라인 개선·신규 자동화"},
    {"area": "보고체계", "desc": "텔레그램·G1 보고 형식·주기 개선"},
    {"area": "운영프로세스", "desc": "일일 워크플로우·루틴 효율화"},
]

# ── 허용 status 값 ──
VALID_STATUSES = ["제안", "승인", "거부", "반영"]


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
    if not PROPOSALS_FILE.exists():
        return []
    try:
        data = json.loads(PROPOSALS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
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
def _build_llm_prompt(summary_text: str, max_proposals: int) -> str:
    return f"""당신은 웰페리온(하이엔드 스포츠클럽 멤버십 커뮤니티) AI 운영팀의 기술 자문입니다.

아래는 최신 AI 기술·사례 학습 요약입니다:
---
{summary_text}
---

위 내용을 바탕으로 웰페리온 C-Level AI 에이전트(AI CEO·CFO·CHRO·CMO·COO·CPO·CTO) 운영에서
개선할 수 있는 제안을 정확히 {max_proposals}개 생성하세요.

각 제안은 반드시 아래 JSON 배열 형식으로만 응답하세요 (설명문·마크다운 없이 순수 JSON만):
[
  {{
    "대상_clevel": "시토",
    "무엇을": "구체적 개선 내용 (1~2문장)",
    "왜_근거": "위 학습 요약의 어떤 내용에서 착안했는지",
    "반영위치": "메모리 또는 프롬프트 또는 자동화코드 또는 보고체계 또는 운영프로세스",
    "예상효과": "기대되는 구체적 효과",
    "위험": "도입 시 주의사항 또는 부작용 (없으면 '없음')"
  }}
]

규칙:
- 대상_clevel 은 반드시 시토/시우/시모/시포/시로/시뽀/웰리 중 하나
- 반영위치 는 반드시 메모리/프롬프트/자동화코드/보고체계/운영프로세스 중 하나
- 중복 대상_clevel 최소화 (여러 C-Level 분산)
- 순수 JSON 배열만 출력 (```json 코드블록도 없이)"""


def generate_proposals_claude_cli(summary_text: str, max_proposals: int) -> list | None:
    """claude CLI (claude -p) 로 제안 생성. 실패 시 None 반환.
    GM 결정(2026-06-23): API 크레딧 미사용, Claude Code 구독 재사용.
    """
    prompt = _build_llm_prompt(summary_text, max_proposals)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else ""
            print(f"[WARN] claude CLI 실패 (exit {result.returncode}): {stderr[:200]}")
            return None

        raw = result.stdout.strip()
        if not raw:
            print("[WARN] claude CLI 빈 응답 — 규칙기반 폴백")
            return None

        # 코드블록 제거 방어
        raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        proposals_raw = json.loads(raw)
        if not isinstance(proposals_raw, list):
            raise ValueError("응답이 배열이 아님")
        return proposals_raw

    except subprocess.TimeoutExpired:
        print("[WARN] claude CLI 타임아웃(120s) — 규칙기반 폴백")
        return None
    except FileNotFoundError:
        print("[WARN] claude CLI 미설치 — 규칙기반 폴백")
        return None
    except json.JSONDecodeError as e:
        print(f"[WARN] claude CLI 응답 JSON 파싱 실패: {e} — 규칙기반 폴백")
        return None
    except Exception as e:
        print(f"[WARN] claude CLI 호출 중 예외: {type(e).__name__}: {e} — 규칙기반 폴백")
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
    """LLM 불가 시 요약 항목을 규칙 변환하여 최소동작 제안 생성."""
    text = summary.get("text", "")
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("=")]
    items = [l for l in lines if l and l[0].isdigit() and ". " in l]
    items = [re.sub(r"^\d+\.\s*", "", i) for i in items]

    proposals = []
    areas = IMPROVEMENT_AREAS[:max_proposals]
    clevels = CLEVELS[:max_proposals]

    for i, area_info in enumerate(areas):
        ref = items[i] if i < len(items) else "최신 AI 동향"
        proposal = {
            "대상_clevel": clevels[i % len(clevels)],
            "무엇을": f"{area_info['area']} 개선: {area_info['desc']}",
            "왜_근거": f"학습 요약 참조 항목: '{ref}'",
            "반영위치": area_info["area"] if area_info["area"] in ["메모리", "프롬프트"] else "자동화코드",
            "예상효과": "운영 효율 향상 및 최신 AI 기법 반영",
            "위험": "기존 동작 회귀 가능성 — 반영 전 GM 승인 필수",
        }
        proposals.append(proposal)

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
            "status": "제안",
        }
        cards.append(card)
    return cards


# ═══════════════════════════════════════════
#  proposals.json 누적 저장
# ═══════════════════════════════════════════
def append_new_cards(new_cards: list) -> tuple[list, int]:
    """기존 proposals 로드 후 중복 없이 누적. (id 기준) 반환: (전체목록, 신규추가수)"""
    existing = load_proposals()
    existing_ids = {c["id"] for c in existing if "id" in c}
    added = [c for c in new_cards if c["id"] not in existing_ids]
    all_cards = existing + added
    save_proposals_file(all_cards)
    return all_cards, len(added)


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

        if st == "승인":
            print(f"  승인일시: {card.get('승인일시', '?')}")
        elif st == "거부":
            print(f"  거부일시: {card.get('거부일시', '?')}  |  사유: {card.get('거부사유', '없음')}")
        elif st == "반영":
            print(f"  반영일시: {card.get('반영일시', '?')}")

    print(f"\n{'='*60}")
    print("  명령: --approve <id>  |  --reject <id> [--reason 사유]  |  --mark-applied <id>")
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
    all_cards, added_count = append_new_cards(cards)
    print(f"\n[4/4] 저장 완료: {PROPOSALS_FILE} (누적 {len(all_cards)}개, 신규 {added_count}개)")

    if added_count > 0:
        tg_msg = (
            f"[시토] AI 자기학습 개선제안 {added_count}건 생성\n"
            f"생성두뇌: {brain}\n"
            f"학습기준: {summary.get('generated_at', '?')}\n"
            f"저장위치: status/learning_proposals.json (누적 {len(all_cards)}개)\n"
            f"→ 반영은 GM 승인 후 별도 수동 실행"
        )
        send_telegram(tg_msg)
    else:
        print("[INFO] 신규 제안 없음 (중복) — 텔레그램 생략")

    print(f"\n[완료] ({now_str()})")


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

    args = parser.parse_args()

    # 상태관리 분기
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

    # 제안 생성 모드
    if args.max < 1 or args.max > 10:
        print("[ERROR] --max 는 1~10 사이")
        sys.exit(1)

    run(max_proposals=args.max, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
