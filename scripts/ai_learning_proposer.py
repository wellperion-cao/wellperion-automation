#!/usr/bin/env python3
"""AI 자기학습 ②단계 — 개선제안 생성기 (ai_learning_proposer.py)

latest_summary.json 을 읽어 C-Level 운영 개선제안 카드 N개를 생성하고
status/learning_proposals.json 에 누적 저장 + 텔레그램 1줄 알림.

★ 안전 원칙:
  - 읽기 + 제안 생성 + learning_proposals.json 쓰기만.
  - 메모리(~/.claude/**), 프롬프트, 에이전트 정의, CLAUDE.md 절대 수정 금지.
  - 모든 카드 status="제안" 고정. 반영은 승인 후(③단계) 별도.

LLM 연동:
  - ANTHROPIC_API_KEY_PRIMARY (.env) 가 있으면 Anthropic SDK 로 생성
    (anthropic 패키지 미설치 시 규칙기반 폴백).
  - 없으면 규칙기반 폴백으로 최소동작.
  → 폴백 동작 시 보고에 'LLM 연동 GM/시토 결정 필요' 표시.

사용법:
  python scripts/ai_learning_proposer.py               # 제안 생성 + 저장 + 텔레그램
  python scripts/ai_learning_proposer.py --dry-run     # 콘솔 출력만 (저장·발송 없음)
  python scripts/ai_learning_proposer.py --max 5       # 제안 수 지정 (기본 3)
"""
import argparse
import json
import sys
import io
import re
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
#  LLM 제안 생성 (Anthropic SDK)
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


def generate_proposals_llm(summary_text: str, max_proposals: int, api_key: str) -> list | None:
    """Anthropic SDK로 제안 생성. 실패 시 None 반환."""
    try:
        import anthropic  # type: ignore
    except ImportError:
        print("[WARN] anthropic 패키지 미설치 — 규칙기반 폴백 사용")
        print("  → pip install anthropic 으로 설치하면 LLM 제안으로 업그레이드됩니다")
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
        # JSON 파싱 (코드블록 제거 방어)
        raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        proposals_raw = json.loads(raw)
        if not isinstance(proposals_raw, list):
            raise ValueError("응답이 배열이 아님")
        return proposals_raw
    except json.JSONDecodeError as e:
        print(f"[WARN] LLM 응답 JSON 파싱 실패: {e} — 규칙기반 폴백")
        return None
    except Exception as e:
        print(f"[WARN] LLM 호출 실패: {type(e).__name__}: {e} — 규칙기반 폴백")
        return None


# ═══════════════════════════════════════════
#  규칙기반 폴백 제안 생성
# ═══════════════════════════════════════════
def generate_proposals_fallback(summary: dict, max_proposals: int) -> list:
    """LLM 불가 시 요약 항목을 규칙 변환하여 최소동작 제안 생성."""
    text = summary.get("text", "")
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("=")]
    # 소스별 주요 항목 추출
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
def assemble_cards(raw_proposals: list, summary: dict, used_llm: bool) -> list:
    cards = []
    for p in raw_proposals:
        card = {
            "id": make_proposal_id(),
            "생성일": today_str(),
            "생성시각": now_str(),
            "생성방법": "LLM(claude-sonnet-4-6)" if used_llm else "규칙기반폴백",
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
def save_proposals(new_cards: list) -> tuple[list, int]:
    """기존 proposals 로드 후 중복 없이 누적. (id 기준) 반환: (전체목록, 신규추가수)"""
    existing = []
    if PROPOSALS_FILE.exists():
        try:
            existing = json.loads(PROPOSALS_FILE.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []

    existing_ids = {c["id"] for c in existing if "id" in c}
    added = [c for c in new_cards if c["id"] not in existing_ids]
    all_cards = existing + added

    PROPOSALS_FILE.write_text(
        json.dumps(all_cards, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
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
#  메인 파이프라인
# ═══════════════════════════════════════════
def run(max_proposals: int = 3, dry_run: bool = False):
    print(f"[시작] AI 학습 개선제안 생성기 ({now_str()})")
    print(f"  dry-run={dry_run}  max={max_proposals}\n")

    # 1. 요약 로드
    summary = load_summary()
    print(f"[1/4] 요약 로드 완료: {summary.get('generated_at', '?')} "
          f"(소스 {summary.get('source_count', 0)}개, 항목 {summary.get('total_items', 0)}건)")

    # 2. 제안 생성 (LLM 우선, 폴백)
    env = load_env()
    api_key = env.get("ANTHROPIC_API_KEY_PRIMARY", "")
    used_llm = False
    llm_note = ""

    if api_key:
        print("[2/4] Anthropic API 키 확인 — LLM 제안 생성 시도")
        raw_proposals = generate_proposals_llm(summary.get("text", ""), max_proposals, api_key)
        if raw_proposals is not None:
            used_llm = True
            print(f"  → LLM 생성 성공: {len(raw_proposals)}개")
        else:
            raw_proposals = generate_proposals_fallback(summary, max_proposals)
            llm_note = "⚠️ LLM 폴백(anthropic 패키지 미설치 또는 호출 실패) — GM/시토 결정 필요"
            print(f"  → 규칙기반 폴백: {len(raw_proposals)}개")
    else:
        print("[2/4] API 키 없음 — 규칙기반 폴백 사용")
        raw_proposals = generate_proposals_fallback(summary, max_proposals)
        llm_note = "⚠️ LLM 미연동(ANTHROPIC_API_KEY_PRIMARY 없음) — GM/시토 결정 필요"

    # 3. 카드 조립
    cards = assemble_cards(raw_proposals, summary, used_llm)
    print(f"[3/4] 제안 카드 {len(cards)}개 조립 완료")

    # 콘솔 출력 (dry-run 포함 항상)
    print("\n" + "=" * 50)
    print(f"  개선제안 카드 ({len(cards)}개)")
    print("=" * 50)
    for i, card in enumerate(cards, 1):
        print(f"\n[제안 {i}] id: {card['id']}")
        print(f"  대상: {card['대상_clevel']} | 위치: {card['반영위치']} | 생성: {card['생성방법']}")
        print(f"  무엇을: {card['무엇을']}")
        print(f"  근거: {card['왜_근거']}")
        print(f"  효과: {card['예상효과']}")
        print(f"  위험: {card['위험']}")
        print(f"  status: {card['status']}")
    print("=" * 50)

    if llm_note:
        print(f"\n{llm_note}")

    if dry_run:
        print("\n[dry-run] 파일 저장·텔레그램 발송 생략")
        return

    # 4. 저장 + 텔레그램
    all_cards, added_count = save_proposals(cards)
    print(f"\n[4/4] 저장 완료: {PROPOSALS_FILE} (누적 {len(all_cards)}개, 신규 {added_count}개)")

    if added_count > 0:
        tg_msg = (
            f"🤖 [시토] AI 자기학습 개선제안 {added_count}건 생성\n"
            f"생성방법: {'LLM(claude-sonnet-4-6)' if used_llm else '규칙기반폴백'}\n"
            f"학습기준: {summary.get('generated_at', '?')}\n"
            f"저장위치: status/learning_proposals.json (누적 {len(all_cards)}개)\n"
        )
        if llm_note:
            tg_msg += f"{llm_note}\n"
        tg_msg += "→ 반영은 GM 승인 후 ③단계에서 별도 실행"
        send_telegram(tg_msg)
    else:
        print("[INFO] 신규 제안 없음 (중복) — 텔레그램 생략")

    print(f"\n[완료] ({now_str()})")


# ═══════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="AI 자기학습 ②단계 — 개선제안 생성기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  %(prog)s                # 제안 생성 + 저장 + 텔레그램\n"
            "  %(prog)s --dry-run      # 콘솔 출력만 (저장·발송 없음)\n"
            "  %(prog)s --max 5        # 제안 5개 생성\n"
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="미리보기 (저장·발송 없음)")
    parser.add_argument("--max", type=int, default=3, metavar="N", help="제안 수 (기본 3)")
    args = parser.parse_args()

    if args.max < 1 or args.max > 10:
        print("[ERROR] --max 는 1~10 사이")
        sys.exit(1)

    run(max_proposals=args.max, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
